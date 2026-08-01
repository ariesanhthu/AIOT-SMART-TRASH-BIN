"""Train the V4-style V7 classifier on balanced raw ESP32 capture streams."""

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

import numpy as np
import tensorflow as tf

from V7.config import (
    ARTIFACTS_DIR,
    CLASS_NAMES,
    MODEL_VERSION,
    PREPARED_DATA_DIR,
    PREPROCESSING_CONFIG,
)
from V7.data_pipeline import (
    balanced_steps_per_epoch,
    load_samples,
    make_balanced_training_dataset,
    make_evaluation_dataset,
    samples_for_split,
)
from V7.metrics import classification_metrics
from V7.model import build_tiny_cnn_v7


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=PREPARED_DATA_DIR)
    parser.add_argument("--out", type=Path, default=ARTIFACTS_DIR)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--epochs", type=int, default=40)
    parser.add_argument("--patience", type=int, default=10)
    parser.add_argument("--learning-rate", type=float, default=1e-3)
    parser.add_argument("--dropout", type=float, default=0.0)
    parser.add_argument("--seed", type=int, default=7)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = train_model(
        data=args.data,
        output=args.out,
        batch_size=args.batch_size,
        epochs=args.epochs,
        patience=args.patience,
        learning_rate=args.learning_rate,
        dropout=args.dropout,
        seed=args.seed,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))


def train_model(
    *,
    data: str | Path = PREPARED_DATA_DIR,
    output: str | Path = ARTIFACTS_DIR,
    batch_size: int = 16,
    epochs: int = 40,
    patience: int = 10,
    learning_rate: float = 1e-3,
    dropout: float = 0.0,
    seed: int = 7,
) -> dict:
    if batch_size < 1 or epochs < 1 or patience < 1 or learning_rate <= 0:
        raise ValueError("Invalid positive V7 training hyperparameter")
    _set_seed(seed)
    started = time.perf_counter()
    output_dir = Path(output).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    checkpoint = output_dir / ".best.weights.h5"
    model_path = output_dir / "model_float.keras"

    samples = load_samples(data)
    train_samples = samples_for_split(samples, "train")
    validation_samples = samples_for_split(samples, "validation")
    test_samples = samples_for_split(samples, "test")
    train_dataset = make_balanced_training_dataset(
        train_samples, batch_size=batch_size, seed=seed
    )
    validation_dataset = make_evaluation_dataset(
        validation_samples, batch_size=batch_size
    )
    test_dataset = make_evaluation_dataset(test_samples, batch_size=batch_size)
    steps = balanced_steps_per_epoch(train_samples, batch_size)

    validation_truth = np.asarray(
        [sample.label_id for sample in validation_samples], dtype=np.int64
    )
    selector = ValidationSelectionMetrics(validation_dataset, validation_truth)
    model = build_tiny_cnn_v7(dropout=dropout)
    model.compile(
        optimizer=tf.keras.optimizers.Adam(learning_rate=learning_rate),
        loss=tf.keras.losses.SparseCategoricalCrossentropy(),
        metrics=[tf.keras.metrics.SparseCategoricalAccuracy(name="accuracy")],
    )
    model.summary()
    callbacks = [
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
            patience=patience,
            restore_best_weights=False,
            verbose=1,
        ),
        tf.keras.callbacks.ReduceLROnPlateau(
            monitor="val_selection_score",
            mode="max",
            factor=0.5,
            patience=max(3, patience // 2),
            min_lr=1e-5,
            verbose=1,
        ),
        tf.keras.callbacks.TerminateOnNaN(),
    ]
    history = model.fit(
        train_dataset,
        steps_per_epoch=steps,
        validation_data=validation_dataset,
        epochs=epochs,
        callbacks=callbacks,
        verbose=2,
    )
    if not checkpoint.is_file():
        raise RuntimeError("V7 training did not create a best checkpoint")
    model.load_weights(checkpoint)
    model.save(model_path)

    validation_probabilities = model.predict(validation_dataset, verbose=0)
    test_probabilities = model.predict(test_dataset, verbose=0)
    validation_metrics = classification_metrics(
        validation_truth, validation_probabilities
    )
    test_truth = np.asarray(
        [sample.label_id for sample in test_samples], dtype=np.int64
    )
    test_metrics = classification_metrics(test_truth, test_probabilities)
    serializable_history = {
        key: [float(value) for value in values]
        for key, values in history.history.items()
    }
    (output_dir / "training_history.json").write_text(
        json.dumps(serializable_history, indent=2) + "\n", encoding="utf-8"
    )

    best_epoch = int(np.argmax(serializable_history["val_selection_score"])) + 1
    metadata = {
        "schema_version": 1,
        "model_version": MODEL_VERSION,
        "created_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "labels": list(CLASS_NAMES),
        "class_to_index": {label: index for index, label in enumerate(CLASS_NAMES)},
        "output_semantic": "probabilities",
        "preprocessing": PREPROCESSING_CONFIG,
        "dataset": {
            "root": str(Path(data).resolve()),
            "manifest_sha256": _sha256(Path(data).resolve() / "manifest.csv"),
            "counts": _split_counts(samples),
            "source_policy": "raw AI/V7/data esp32-cam-*.jpg only",
            "trashnet_used": False,
            "stored_augmentation_used": False,
        },
        "training": {
            "balanced_sampling": True,
            "class_weights": False,
            "augmentation": "online_train_only",
            "batch_size": batch_size,
            "requested_epochs": epochs,
            "completed_epochs": len(history.epoch),
            "best_epoch": best_epoch,
            "steps_per_epoch": steps,
            "patience": patience,
            "learning_rate": learning_rate,
            "dropout": dropout,
            "seed": seed,
            "duration_seconds": time.perf_counter() - started,
        },
        "selection": {
            "metric": (
                "0.65*validation_macro_recall + 0.35*validation_accuracy "
                "- 0.001*validation_loss (tie-break)"
            ),
            "uses_test_split": False,
        },
        "validation_metrics": validation_metrics,
        "test_metrics": test_metrics,
        "environment": {
            "python": platform.python_version(),
            "tensorflow": tf.__version__,
            "platform": platform.platform(),
        },
        "artifacts": {
            "float_model": {
                "file": model_path.name,
                "size_bytes": model_path.stat().st_size,
                "sha256": _sha256(model_path),
            }
        },
    }
    (output_dir / "model_metadata.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    checkpoint.unlink(missing_ok=True)
    return {
        "model": str(model_path),
        "best_epoch": best_epoch,
        "completed_epochs": len(history.epoch),
        "validation": validation_metrics,
        "test": test_metrics,
    }


class ValidationSelectionMetrics(tf.keras.callbacks.Callback):
    def __init__(self, dataset: tf.data.Dataset, truth: np.ndarray):
        super().__init__()
        self.dataset = dataset
        self.truth = truth

    def on_epoch_end(self, epoch: int, logs: dict | None = None) -> None:
        if logs is None or self.model is None:
            return
        probabilities = self.model.predict(self.dataset, verbose=0)
        metrics = classification_metrics(self.truth, probabilities)
        # The tiny validation split makes recall/accuracy discrete. The small
        # loss tie-break selects the better-calibrated checkpoint when top-1
        # metrics are equal without letting loss outweigh any classification.
        validation_loss = min(float(logs.get("val_loss", 10.0)), 10.0)
        score = (
            0.65 * metrics["macro_recall"]
            + 0.35 * metrics["accuracy"]
            - 0.001 * validation_loss
        )
        logs["val_macro_recall"] = float(metrics["macro_recall"])
        logs["val_minimum_class_recall"] = float(metrics["minimum_class_recall"])
        logs["val_selection_score"] = float(score)
        print(
            f" - val_macro_recall: {metrics['macro_recall']:.4f}"
            f" - val_min_recall: {metrics['minimum_class_recall']:.4f}"
            f" - val_selection_score: {score:.4f}"
        )


def _set_seed(seed: int) -> None:
    os.environ.setdefault("PYTHONHASHSEED", str(seed))
    random.seed(seed)
    np.random.seed(seed)
    tf.keras.utils.set_random_seed(seed)


def _split_counts(samples) -> dict:
    return {
        split: {
            label: sum(
                sample.split == split and sample.label == label for sample in samples
            )
            for label in CLASS_NAMES
        }
        for split in ("train", "validation", "test")
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    main()
