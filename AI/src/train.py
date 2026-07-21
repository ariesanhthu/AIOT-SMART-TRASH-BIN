"""Train TinyCNN v2 directly on paper, plastic, and organic images."""

from __future__ import annotations

import argparse
import json
import os
import platform
import random
import time

import numpy as np
import tensorflow as tf

try:
    from .config import (
        DEFAULT_ARTIFACT_DIR,
        DEFAULT_DATA_DIR,
        LABELS,
        MODEL_VERSION,
        resolve_input_path,
        resolve_output_path,
    )
    from .dataset import compute_class_weights, load_dataset_index, make_dataset
    from .metadata import base_model_metadata, sha256_file, write_json_atomic
    from .metrics import classification_metrics
    from .model import build_tiny_cnn_v2
except ImportError:
    from config import (  # type: ignore
        DEFAULT_ARTIFACT_DIR,
        DEFAULT_DATA_DIR,
        LABELS,
        MODEL_VERSION,
        resolve_input_path,
        resolve_output_path,
    )
    from dataset import compute_class_weights, load_dataset_index, make_dataset  # type: ignore
    from metadata import base_model_metadata, sha256_file, write_json_atomic  # type: ignore
    from metrics import classification_metrics  # type: ignore
    from model import build_tiny_cnn_v2  # type: ignore


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", default=str(DEFAULT_DATA_DIR))
    parser.add_argument("--out", default=str(DEFAULT_ARTIFACT_DIR))
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--epochs", type=int, default=100)
    parser.add_argument("--patience", type=int, default=15)
    parser.add_argument("--learning-rate", type=float, default=1e-3)
    parser.add_argument("--weight-decay", type=float, default=1e-4)
    parser.add_argument("--label-smoothing", type=float, default=0.05)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--no-augment", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    validate_args(args)
    set_reproducible_seed(args.seed)
    started = time.perf_counter()

    data_dir = resolve_input_path(args.data)
    out_dir = resolve_output_path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_path = out_dir / ".best.weights.h5"
    float_model_path = out_dir / "model_float.keras"

    index = load_dataset_index(data_dir)
    train_samples = index.for_split("train")
    validation_samples = index.for_split("validation")
    test_samples = index.for_split("test")
    class_weights = compute_class_weights(train_samples)

    train_dataset = make_dataset(
        train_samples,
        batch_size=args.batch_size,
        training=True,
        seed=args.seed,
        augment=not args.no_augment,
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
    optimizer = _build_optimizer(args.learning_rate, args.weight_decay)
    loss = tf.keras.losses.SparseCategoricalCrossentropy(from_logits=True)
    if args.label_smoothing > 0.0:
        loss = sparse_loss_with_label_smoothing(args.label_smoothing)
    model.compile(
        optimizer=optimizer,
        loss=loss,
        metrics=[tf.keras.metrics.SparseCategoricalAccuracy(name="accuracy")],
    )
    model.summary()

    validation_truth = np.asarray(
        [sample.label_id for sample in validation_samples], dtype=np.int64
    )
    callbacks = [
        ValidationSelectionMetrics(validation_dataset, validation_truth),
        tf.keras.callbacks.ModelCheckpoint(
            filepath=checkpoint_path,
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
            restore_best_weights=False,
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
        class_weight=class_weights,
        epochs=args.epochs,
        callbacks=callbacks,
        verbose=2,
    )
    if not checkpoint_path.is_file():
        raise RuntimeError("Training completed without producing a checkpoint")
    model.load_weights(checkpoint_path)
    # Save a fresh, uncompiled deployment graph so the artifact contains no
    # optimizer state or custom training loss that TFLite/firmware never use.
    deploy_model = build_tiny_cnn_v2()
    deploy_model.set_weights(model.get_weights())
    deploy_model.save(float_model_path)

    validation_logits = _predict_images(deploy_model, validation_dataset)
    test_logits = _predict_images(deploy_model, test_dataset)
    test_truth = np.asarray([sample.label_id for sample in test_samples], dtype=np.int64)
    validation_metrics = classification_metrics(validation_truth, validation_logits)
    test_metrics = classification_metrics(test_truth, test_logits)

    training_config = {
        **vars(args),
        "data": str(data_dir),
        "out": str(out_dir),
        "labels": list(LABELS),
        "model_version": MODEL_VERSION,
        "class_weights": {str(key): value for key, value in class_weights.items()},
        "python_version": platform.python_version(),
        "tensorflow_version": tf.__version__,
        "numpy_version": np.__version__,
    }
    training_metrics = {
        "model_version": MODEL_VERSION,
        "dataset": index.summary(),
        "model_parameters": int(deploy_model.count_params()),
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
    print(f"Saved float model: {float_model_path}")


def _predict_images(model: tf.keras.Model, dataset: tf.data.Dataset) -> np.ndarray:
    images = dataset.map(
        lambda image, _label: image,
        num_parallel_calls=tf.data.AUTOTUNE,
        deterministic=True,
    )
    return np.asarray(model.predict(images, verbose=0), dtype=np.float32)


class ValidationSelectionMetrics(tf.keras.callbacks.Callback):
    """Select checkpoints by macro F1 while protecting the weakest class."""

    def __init__(self, dataset: tf.data.Dataset, truth: np.ndarray) -> None:
        super().__init__()
        self.dataset = dataset
        self.truth = truth

    def on_epoch_end(self, epoch: int, logs: dict | None = None) -> None:
        del epoch
        if self.model is None:
            raise RuntimeError("Validation callback is not attached to a model")
        metrics = classification_metrics(
            self.truth,
            _predict_images(self.model, self.dataset),
        )
        recalls = [float(metrics["per_class"][label]["recall"]) for label in LABELS]
        macro_f1 = float(metrics["macro_f1"])
        min_recall = min(recalls)
        # Macro F1 is primary; the smaller term prevents a high aggregate score
        # from hiding a weak paper/plastic/organic route on the physical bin.
        selection_score = 0.75 * macro_f1 + 0.25 * min_recall
        current_logs = logs if logs is not None else {}
        current_logs["val_macro_f1"] = macro_f1
        current_logs["val_min_recall"] = min_recall
        current_logs["val_selection_score"] = selection_score
        print(
            " - val_macro_f1: "
            f"{macro_f1:.4f} - val_min_recall: {min_recall:.4f}"
            f" - val_selection_score: {selection_score:.4f}"
        )


def sparse_loss_with_label_smoothing(label_smoothing: float):
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


def set_reproducible_seed(seed: int) -> None:
    os.environ.setdefault("TF_DETERMINISTIC_OPS", "1")
    random.seed(seed)
    np.random.seed(seed)
    tf.keras.utils.set_random_seed(seed)
    try:
        tf.config.experimental.enable_op_determinism()
    except (AttributeError, RuntimeError):
        pass


def validate_args(args: argparse.Namespace) -> None:
    if args.batch_size < 1 or args.epochs < 1 or args.patience < 1:
        raise ValueError("batch-size, epochs, and patience must be positive")
    if args.learning_rate <= 0 or args.weight_decay < 0:
        raise ValueError("learning-rate must be positive and weight-decay non-negative")
    if not 0.0 <= args.label_smoothing < 1.0:
        raise ValueError("label-smoothing must be in [0, 1)")


if __name__ == "__main__":
    main()
