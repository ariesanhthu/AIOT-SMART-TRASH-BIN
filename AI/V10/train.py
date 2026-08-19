"""Train the balanced V10 classifier and evaluate the selected float model."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import random
import time

os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")

import numpy as np
import tensorflow as tf

from V10.config import (
    ARTIFACTS_DIR,
    AUGMENTATION_CONFIG,
    CLASS_NAMES,
    DATASET_DIR,
    MODEL_CONFIG,
    MODEL_VERSION,
    PREPROCESSING_CONFIG,
)
from V10.data_pipeline import (
    load_samples,
    make_evaluation_dataset,
    make_training_dataset,
    samples_for_split,
    steps_per_epoch,
)
from V10.metrics import classification_metrics
from V10.model import build_model


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=DATASET_DIR)
    parser.add_argument("--out", type=Path, default=ARTIFACTS_DIR)
    parser.add_argument("--epochs", type=int, default=60)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--views-per-source", type=int, default=1)
    parser.add_argument("--patience", type=int, default=10)
    parser.add_argument("--learning-rate", type=float, default=1e-3)
    parser.add_argument("--dropout", type=float, default=0.22)
    parser.add_argument("--seed", type=int, default=10)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    _validate_args(args)
    _set_seed(args.seed)
    started = time.perf_counter()
    output = args.out.expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)

    samples = load_samples(args.data)
    train_samples = samples_for_split(samples, "train")
    validation_samples = samples_for_split(samples, "validation")
    test_samples = samples_for_split(samples, "test")
    train_ds = make_training_dataset(
        train_samples, batch_size=args.batch_size, seed=args.seed
    )
    validation_ds = make_evaluation_dataset(
        validation_samples, batch_size=args.batch_size
    )
    test_ds = make_evaluation_dataset(test_samples, batch_size=args.batch_size)
    steps = steps_per_epoch(train_samples, args.batch_size, args.views_per_source)

    validation_truth = np.asarray([sample.label_id for sample in validation_samples])
    selector = ValidationMetrics(validation_ds, validation_truth)
    checkpoint = output / ".best.weights.h5"
    model = build_model(args.dropout)
    model.compile(
        optimizer=tf.keras.optimizers.Adam(args.learning_rate),
        loss=tf.keras.losses.SparseCategoricalCrossentropy(),
        metrics=[tf.keras.metrics.SparseCategoricalAccuracy(name="accuracy")],
    )
    model.summary()
    history = model.fit(
        train_ds,
        steps_per_epoch=steps,
        validation_data=validation_ds,
        epochs=args.epochs,
        callbacks=[
            selector,
            tf.keras.callbacks.ModelCheckpoint(
                checkpoint,
                monitor="val_selection_score",
                mode="max",
                save_best_only=True,
                save_weights_only=True,
                verbose=1,
            ),
            tf.keras.callbacks.EarlyStopping(
                monitor="val_selection_score",
                mode="max",
                patience=args.patience,
                verbose=1,
            ),
            tf.keras.callbacks.ReduceLROnPlateau(
                monitor="val_selection_score",
                mode="max",
                factor=0.5,
                patience=max(3, args.patience // 2),
                min_lr=1e-5,
                verbose=1,
            ),
            tf.keras.callbacks.TerminateOnNaN(),
        ],
        verbose=2,
    )
    if not checkpoint.is_file():
        raise RuntimeError("Training did not create a best checkpoint")
    model.load_weights(checkpoint)
    checkpoint.unlink(missing_ok=True)
    model_path = output / "model_float.keras"
    model.save(model_path)

    validation_metrics = _evaluate(model, validation_ds, validation_samples)
    test_metrics = _evaluate(model, test_ds, test_samples)
    history_data = {
        key: [float(value) for value in values]
        for key, values in history.history.items()
    }
    (output / "training_history.json").write_text(
        json.dumps(history_data, indent=2) + "\n", encoding="utf-8"
    )
    best_epoch = int(np.argmax(history_data["val_selection_score"])) + 1
    manifest_path = args.data.resolve() / "manifest.csv"
    metadata = {
        "model_version": MODEL_VERSION,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "labels": list(CLASS_NAMES),
        "class_to_index": {name: index for index, name in enumerate(CLASS_NAMES)},
        "dataset_root": str(args.data.resolve()),
        "dataset_manifest_sha256": _sha256(manifest_path),
        "dataset_counts": _counts(samples),
        "preprocessing": PREPROCESSING_CONFIG,
        "augmentation": AUGMENTATION_CONFIG,
        "model_config": MODEL_CONFIG,
        "training": {
            "balanced_round_robin": True,
            "epochs_requested": args.epochs,
            "epochs_completed": len(history.epoch),
            "best_epoch": best_epoch,
            "batch_size": args.batch_size,
            "views_per_source": args.views_per_source,
            "steps_per_epoch": steps,
            "seed": args.seed,
            "duration_seconds": time.perf_counter() - started,
        },
        "float_validation_metrics": validation_metrics,
        "float_test_metrics": test_metrics,
        "environment": {
            "python": platform.python_version(),
            "tensorflow": tf.__version__,
            "devices": [device.name for device in tf.config.list_physical_devices()],
        },
        "float_model": {
            "file": model_path.name,
            "bytes": model_path.stat().st_size,
            "sha256": _sha256(model_path),
        },
    }
    (output / "model_metadata.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (output / "labels.json").write_text(
        json.dumps(list(CLASS_NAMES), indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({
        "model": str(model_path),
        "best_epoch": best_epoch,
        "validation": validation_metrics,
        "test": test_metrics,
    }, indent=2))


class ValidationMetrics(tf.keras.callbacks.Callback):
    def __init__(self, dataset: tf.data.Dataset, truth: np.ndarray):
        super().__init__()
        self.dataset = dataset
        self.truth = truth

    def on_epoch_end(self, epoch: int, logs: dict | None = None) -> None:
        del epoch
        if logs is None or self.model is None:
            return
        metrics = classification_metrics(
            self.truth, self.model.predict(self.dataset, verbose=0)
        )
        loss = min(float(logs.get("val_loss", 10.0)), 10.0)
        score = (
            0.55 * metrics["macro_recall"]
            + 0.30 * metrics["accuracy"]
            + 0.15 * metrics["minimum_class_recall"]
            - 0.001 * loss
        )
        logs["val_macro_recall"] = metrics["macro_recall"]
        logs["val_minimum_class_recall"] = metrics["minimum_class_recall"]
        logs["val_selection_score"] = score
        print(
            f" - val_macro_recall: {metrics['macro_recall']:.4f}"
            f" - val_min_recall: {metrics['minimum_class_recall']:.4f}"
            f" - val_selection_score: {score:.4f}"
        )


def _evaluate(model, dataset, samples) -> dict:
    truth = np.asarray([sample.label_id for sample in samples])
    probabilities = model.predict(dataset, verbose=0)
    return classification_metrics(truth, probabilities)


def _counts(samples) -> dict:
    return {
        split: {
            label: sum(sample.split == split and sample.label == label for sample in samples)
            for label in CLASS_NAMES
        }
        for split in ("train", "validation", "test")
    }


def _validate_args(args: argparse.Namespace) -> None:
    for name in ("epochs", "batch_size", "views_per_source", "patience"):
        if getattr(args, name) < 1:
            raise ValueError(f"--{name.replace('_', '-')} must be positive")
    if not 0.0 < args.learning_rate < 1.0:
        raise ValueError("--learning-rate must be between zero and one")
    if not 0.0 <= args.dropout < 1.0:
        raise ValueError("--dropout must be in [0,1)")


def _set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    tf.keras.utils.set_random_seed(seed)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    main()
