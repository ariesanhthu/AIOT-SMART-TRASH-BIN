"""Train the V2 TinyCNN on the offline-augmented new camera dataset."""

from __future__ import annotations

import argparse
import json
import os
import platform
from pathlib import Path
import random
import time

import numpy as np
import tensorflow as tf

from src.config import LABELS, MODEL_VERSION
from src.dataset import compute_class_weights, load_dataset_index, make_dataset
from src.metadata import base_model_metadata, sha256_file, write_json_atomic
from src.metrics import classification_metrics
from V2.model import build_tiny_cnn_v2


V2_DIR = Path(__file__).resolve().parent
DEFAULT_DATA = V2_DIR / "dataset_augmented"
DEFAULT_OUT = V2_DIR / "artifacts"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--epochs", type=int, default=100)
    parser.add_argument("--patience", type=int, default=15)
    parser.add_argument("--learning-rate", type=float, default=1e-3)
    parser.add_argument("--weight-decay", type=float, default=1e-4)
    parser.add_argument("--label-smoothing", type=float, default=0.05)
    parser.add_argument(
        "--plastic-weight-multiplier",
        type=float,
        default=1.0,
        help="Extra loss weight for transparent plastic, which is easily confused with paper.",
    )
    parser.add_argument("--seed", type=int, default=42)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    _validate_args(args)
    _set_reproducible_seed(args.seed)
    started = time.perf_counter()

    data_dir = args.data.expanduser().resolve()
    out_dir = args.out.expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_path = out_dir / ".best.weights.h5"
    float_model_path = out_dir / "model_float.keras"

    index = load_dataset_index(data_dir)
    train_samples = index.for_split("train")
    validation_samples = index.for_split("validation")
    test_samples = index.for_split("test")
    class_weights = compute_class_weights(train_samples)
    plastic_index = LABELS.index("plastic")
    class_weights[plastic_index] *= args.plastic_weight_multiplier

    # Augmentation was materialized before training. It is deliberately disabled here
    # so the generated dataset and every training run remain directly auditable.
    train_dataset = make_dataset(
        train_samples,
        batch_size=args.batch_size,
        training=True,
        seed=args.seed,
        augment=False,
    )
    validation_dataset = make_dataset(
        validation_samples,
        batch_size=args.batch_size,
        training=False,
        seed=args.seed,
    )
    test_dataset = make_dataset(
        test_samples,
        batch_size=args.batch_size,
        training=False,
        seed=args.seed,
    )

    model = build_tiny_cnn_v2()
    model.compile(
        optimizer=_build_optimizer(args.learning_rate, args.weight_decay),
        loss=_sparse_loss_with_label_smoothing(args.label_smoothing),
        metrics=[tf.keras.metrics.SparseCategoricalAccuracy(name="accuracy")],
    )
    model.summary()

    validation_truth = np.asarray(
        [sample.label_id for sample in validation_samples], dtype=np.int64
    )
    selector = ValidationSelectionMetrics(validation_dataset, validation_truth)
    callbacks = [
        selector,
        tf.keras.callbacks.ModelCheckpoint(
            checkpoint_path,
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
            monitor="val_loss",
            mode="min",
            factor=0.5,
            patience=max(3, args.patience // 3),
            min_lr=1e-5,
            verbose=1,
        ),
        tf.keras.callbacks.TerminateOnNaN(),
    ]
    history = model.fit(
        train_dataset,
        validation_data=validation_dataset,
        epochs=args.epochs,
        class_weight=class_weights,
        callbacks=callbacks,
        verbose=2,
    )
    if not checkpoint_path.is_file():
        raise RuntimeError("Training did not produce a best checkpoint")
    model.load_weights(checkpoint_path)

    deployment_model = build_tiny_cnn_v2()
    deployment_model.set_weights(model.get_weights())
    deployment_model.save(float_model_path)

    validation_logits = _predict(deployment_model, validation_dataset)
    test_logits = _predict(deployment_model, test_dataset)
    test_truth = np.asarray([sample.label_id for sample in test_samples], dtype=np.int64)
    validation_metrics = classification_metrics(validation_truth, validation_logits)
    test_metrics = classification_metrics(test_truth, test_logits)

    training_config = {
        **vars(args),
        "data": str(data_dir),
        "out": str(out_dir),
        "labels": list(LABELS),
        "model_version": MODEL_VERSION,
        "offline_augmentation": True,
        "online_augmentation": False,
        "class_weights": {str(key): value for key, value in class_weights.items()},
        "python_version": platform.python_version(),
        "tensorflow_version": tf.__version__,
        "numpy_version": np.__version__,
    }
    training_config = {
        key: str(value) if isinstance(value, Path) else value
        for key, value in training_config.items()
    }
    training_metrics = {
        "model_version": MODEL_VERSION,
        "dataset": index.summary(),
        "model_parameters": int(deployment_model.count_params()),
        "best_epoch": int(selector.best_epoch + 1),
        "epochs_ran": len(history.history.get("loss", [])),
        "training_seconds": round(time.perf_counter() - started, 3),
        "validation": validation_metrics,
        "test": test_metrics,
    }
    history_payload = {
        key: [float(value) for value in values]
        for key, values in history.history.items()
    }
    metadata = base_model_metadata(index.summary(), args.seed)
    metadata["training_variant"] = "AI/V2 new ESP32-CAM dataset"
    metadata["artifacts"]["float_model"] = {
        "file": float_model_path.name,
        "size_bytes": float_model_path.stat().st_size,
        "sha256": sha256_file(float_model_path),
    }

    write_json_atomic(
        out_dir / "labels.json",
        {
            "labels": list(LABELS),
            "class_to_index": {label: index for index, label in enumerate(LABELS)},
        },
    )
    write_json_atomic(out_dir / "training_config.json", training_config)
    write_json_atomic(out_dir / "training_history.json", history_payload)
    write_json_atomic(out_dir / "training_metrics.json", training_metrics)
    write_json_atomic(out_dir / "model_metadata.json", metadata)
    checkpoint_path.unlink(missing_ok=True)

    print(json.dumps(training_metrics, indent=2, ensure_ascii=False))
    print(f"Saved V2 float model: {float_model_path}")


class ValidationSelectionMetrics(tf.keras.callbacks.Callback):
    """Select a checkpoint by macro F1 while protecting the weakest class."""

    def __init__(self, dataset: tf.data.Dataset, truth: np.ndarray) -> None:
        super().__init__()
        self.dataset = dataset
        self.truth = truth
        self.best_score = -1.0
        self.best_epoch = 0

    def on_epoch_end(self, epoch: int, logs: dict | None = None) -> None:
        if self.model is None:
            raise RuntimeError("Validation callback is not attached to a model")
        metrics = classification_metrics(self.truth, _predict(self.model, self.dataset))
        recalls = [float(metrics["per_class"][label]["recall"]) for label in LABELS]
        macro_f1 = float(metrics["macro_f1"])
        min_recall = min(recalls)
        selection_score = 0.75 * macro_f1 + 0.25 * min_recall
        if selection_score > self.best_score:
            self.best_score = selection_score
            self.best_epoch = epoch
        current_logs = logs if logs is not None else {}
        current_logs["val_macro_f1"] = macro_f1
        current_logs["val_min_recall"] = min_recall
        current_logs["val_selection_score"] = selection_score
        print(
            f" - val_macro_f1: {macro_f1:.4f}"
            f" - val_min_recall: {min_recall:.4f}"
            f" - val_selection_score: {selection_score:.4f}"
        )


def _predict(model: tf.keras.Model, dataset: tf.data.Dataset) -> np.ndarray:
    images = dataset.map(
        lambda image, _label: image,
        num_parallel_calls=tf.data.AUTOTUNE,
        deterministic=True,
    )
    return np.asarray(model.predict(images, verbose=0), dtype=np.float32)


def _sparse_loss_with_label_smoothing(label_smoothing: float):
    if label_smoothing == 0.0:
        return tf.keras.losses.SparseCategoricalCrossentropy(from_logits=True)
    categorical_loss = tf.keras.losses.CategoricalCrossentropy(
        from_logits=True,
        label_smoothing=label_smoothing,
    )

    def loss(y_true, y_pred):
        labels = tf.cast(tf.reshape(y_true, [-1]), tf.int32)
        one_hot = tf.one_hot(labels, depth=len(LABELS))
        return categorical_loss(one_hot, y_pred)

    return loss


def _build_optimizer(learning_rate: float, weight_decay: float):
    if hasattr(tf.keras.optimizers, "AdamW"):
        return tf.keras.optimizers.AdamW(
            learning_rate=learning_rate,
            weight_decay=weight_decay,
        )
    return tf.keras.optimizers.Adam(learning_rate=learning_rate)


def _set_reproducible_seed(seed: int) -> None:
    os.environ.setdefault("TF_DETERMINISTIC_OPS", "1")
    random.seed(seed)
    np.random.seed(seed)
    tf.keras.utils.set_random_seed(seed)
    try:
        tf.config.experimental.enable_op_determinism()
    except (AttributeError, RuntimeError):
        pass


def _validate_args(args: argparse.Namespace) -> None:
    if args.batch_size < 1 or args.epochs < 1 or args.patience < 1:
        raise ValueError("batch-size, epochs and patience must be positive")
    if args.learning_rate <= 0 or args.weight_decay < 0:
        raise ValueError("learning-rate must be positive and weight-decay non-negative")
    if not 0.0 <= args.label_smoothing < 1.0:
        raise ValueError("label-smoothing must be in [0, 1)")
    if args.plastic_weight_multiplier <= 0:
        raise ValueError("plastic-weight-multiplier must be positive")


if __name__ == "__main__":
    main()
