"""Train TinyCNN V5 with balanced sampling and environment randomization."""

from __future__ import annotations

import argparse
import json
import os
import platform
from pathlib import Path
import random
import time

from V5.runtime import LABELS, MODEL_VERSION, configure_shared_contract

configure_shared_contract()

import numpy as np  # noqa: E402
import tensorflow as tf  # noqa: E402

from src.dataset import load_dataset_index, make_dataset  # noqa: E402
from src.metadata import base_model_metadata, sha256_file, write_json_atomic  # noqa: E402
from src.metrics import classification_metrics  # noqa: E402
from V5.data_pipeline import (  # noqa: E402
    balanced_steps_per_epoch,
    make_balanced_training_dataset,
    make_environment_validation_dataset,
)
from V5.model import build_tiny_cnn_v5  # noqa: E402


V5_DIR = Path(__file__).resolve().parent
DEFAULT_DATA = V5_DIR / "dataset_prepared"
DEFAULT_OUT = V5_DIR / "artifacts"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--epochs", type=int, default=100)
    parser.add_argument("--patience", type=int, default=18)
    parser.add_argument("--learning-rate", type=float, default=5e-4)
    parser.add_argument("--weight-decay", type=float, default=1e-4)
    parser.add_argument("--label-smoothing", type=float, default=0.02)
    parser.add_argument("--focal-gamma", type=float, default=1.5)
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
    raw_train_counts = {
        label: sum(sample.label == label for sample in train_samples) for label in LABELS
    }
    steps_per_epoch = balanced_steps_per_epoch(train_samples, args.batch_size)
    effective_per_class = max(raw_train_counts.values())

    train_dataset = make_balanced_training_dataset(
        train_samples, batch_size=args.batch_size, seed=args.seed
    )
    validation_dataset = make_dataset(
        validation_samples,
        batch_size=args.batch_size,
        training=False,
        seed=args.seed,
    ).cache()
    environment_validation_dataset = make_environment_validation_dataset(
        validation_samples, batch_size=args.batch_size
    )
    test_dataset = make_dataset(
        test_samples,
        batch_size=args.batch_size,
        training=False,
        seed=args.seed,
    )

    model = build_tiny_cnn_v5()
    model.compile(
        optimizer=tf.keras.optimizers.AdamW(
            learning_rate=args.learning_rate,
            weight_decay=args.weight_decay,
            global_clipnorm=5.0,
        ),
        loss=_balanced_focal_loss(args.label_smoothing, args.focal_gamma),
        metrics=[tf.keras.metrics.SparseCategoricalAccuracy(name="accuracy")],
    )
    model.summary()

    validation_truth = np.asarray(
        [sample.label_id for sample in validation_samples], dtype=np.int64
    )
    selector = ValidationSelectionMetrics(
        validation_dataset,
        validation_truth,
        environment_validation_dataset=environment_validation_dataset,
        environment_truth=np.tile(validation_truth, 4),
    )
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
            restore_best_weights=False,
            verbose=1,
        ),
        tf.keras.callbacks.ReduceLROnPlateau(
            monitor="val_loss",
            mode="min",
            factor=0.5,
            patience=max(4, args.patience // 3),
            min_lr=8e-6,
            verbose=1,
        ),
        tf.keras.callbacks.TerminateOnNaN(),
    ]
    history = model.fit(
        train_dataset,
        validation_data=validation_dataset,
        steps_per_epoch=steps_per_epoch,
        epochs=args.epochs,
        callbacks=callbacks,
        verbose=2,
    )
    if not checkpoint_path.is_file():
        raise RuntimeError("Training did not produce a best checkpoint")
    model.load_weights(checkpoint_path)

    deployment_model = build_tiny_cnn_v5()
    deployment_model.set_weights(model.get_weights())
    deployment_model.save(float_model_path)

    validation_metrics = classification_metrics(
        validation_truth, _predict(deployment_model, validation_dataset)
    )
    test_truth = np.asarray([sample.label_id for sample in test_samples], dtype=np.int64)
    test_logits = _predict(deployment_model, test_dataset)
    test_metrics = classification_metrics(test_truth, test_logits)
    organic_id = LABELS.index("organic")
    paper_id = LABELS.index("paper")
    test_predictions = np.argmax(test_logits, axis=1)
    organic_mask = test_truth == organic_id
    organic_to_paper = int(np.sum(organic_mask & (test_predictions == paper_id)))

    config = {
        **vars(args),
        "data": str(data_dir),
        "out": str(out_dir),
        "labels": list(LABELS),
        "model_version": MODEL_VERSION,
        "deployment_contract_version": MODEL_VERSION,
        "raw_train_counts": raw_train_counts,
        "balance_strategy": "exact round-robin class sampling",
        "effective_samples_per_class_per_epoch": effective_per_class,
        "effective_total_per_epoch": effective_per_class * len(LABELS),
        "steps_per_epoch": steps_per_epoch,
        "online_environment_augmentation": {
            "geometry": "flip, rotation +/-25deg, scale, translation, shear",
            "lighting": (
                "gamma, exposure, dedicated 35% clipped-overexposure/glare branch, "
                "contrast, saturation, hue, explicit warm/cool RGB gains, shadow"
            ),
            "sensor": "blur, low-resolution, RGB565 quantization, Gaussian noise",
            "validation_test_augmented": False,
            "checkpoint_environment_profiles": (
                "overexposed, warm_cast, cool_cast, low_light"
            ),
        },
        "class_weights": None,
        "python_version": platform.python_version(),
        "tensorflow_version": tf.__version__,
        "numpy_version": np.__version__,
    }
    config = {
        key: str(value) if isinstance(value, Path) else value for key, value in config.items()
    }
    metrics = {
        "model_version": MODEL_VERSION,
        "dataset": index.summary(),
        "model_parameters": int(deployment_model.count_params()),
        "best_epoch": int(selector.best_epoch + 1),
        "epochs_ran": len(history.history.get("loss", [])),
        "training_seconds": round(time.perf_counter() - started, 3),
        "validation": validation_metrics,
        "test": test_metrics,
        "targeted_error": {
            "organic_total": int(np.sum(organic_mask)),
            "organic_predicted_as_paper": organic_to_paper,
            "organic_to_paper_rate": float(organic_to_paper / np.sum(organic_mask)),
        },
    }
    history_payload = {
        key: [float(value) for value in values] for key, values in history.history.items()
    }
    metadata = base_model_metadata(index.summary(), args.seed)
    metadata["training_variant"] = (
        "AI/V5 canonical four-class TinyCNN with exact class-balanced sampling "
        "and train-only environmental augmentation"
    )
    metadata["environment_invariance"] = config["online_environment_augmentation"]
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
    write_json_atomic(out_dir / "training_config.json", config)
    write_json_atomic(out_dir / "training_history.json", history_payload)
    write_json_atomic(out_dir / "training_metrics.json", metrics)
    write_json_atomic(out_dir / "model_metadata.json", metadata)
    checkpoint_path.unlink(missing_ok=True)
    print(json.dumps(metrics, indent=2, ensure_ascii=False))


class ValidationSelectionMetrics(tf.keras.callbacks.Callback):
    """Select checkpoints symmetrically on clean and environmental quality."""

    def __init__(
        self,
        dataset: tf.data.Dataset,
        truth: np.ndarray,
        *,
        environment_validation_dataset: tf.data.Dataset | None = None,
        environment_truth: np.ndarray | None = None,
    ) -> None:
        super().__init__()
        self.dataset = dataset
        self.truth = truth
        self.environment_validation_dataset = environment_validation_dataset
        self.environment_truth = environment_truth
        if (environment_validation_dataset is None) != (environment_truth is None):
            raise ValueError("Environmental dataset and truth must be supplied together")
        self.best_score = -np.inf
        self.best_epoch = 0

    def on_epoch_end(self, epoch: int, logs: dict | None = None) -> None:
        if self.model is None:
            raise RuntimeError("Validation callback is not attached to a model")
        logits = _predict_in_callback(self.model, self.dataset)
        metrics = classification_metrics(self.truth, logits)
        predictions = np.argmax(logits, axis=1)
        recalls = [float(metrics["per_class"][label]["recall"]) for label in LABELS]
        precisions = [
            float(metrics["per_class"][label]["precision"]) for label in LABELS
        ]
        organic_id = LABELS.index("organic")
        paper_id = LABELS.index("paper")
        organic_mask = self.truth == organic_id
        organic_to_paper_rate = float(
            np.mean(predictions[organic_mask] == paper_id) if np.any(organic_mask) else 1.0
        )
        macro_f1 = float(metrics["macro_f1"])
        min_recall = min(recalls)
        min_precision = min(precisions)
        organic_recall = recalls[organic_id]
        organic_precision = precisions[organic_id]
        clean_quality = 0.65 * macro_f1 + 0.25 * min_recall + 0.10 * min_precision
        environment_macro_f1 = macro_f1
        environment_min_recall = min_recall
        environment_min_precision = min_precision
        environment_quality = clean_quality
        if self.environment_validation_dataset is not None:
            environment_logits = _predict_in_callback(
                self.model, self.environment_validation_dataset
            )
            environment_metrics = classification_metrics(
                self.environment_truth, environment_logits
            )
            environment_macro_f1 = float(environment_metrics["macro_f1"])
            environment_recalls = [
                float(environment_metrics["per_class"][label]["recall"])
                for label in LABELS
            ]
            environment_precisions = [
                float(environment_metrics["per_class"][label]["precision"])
                for label in LABELS
            ]
            environment_min_recall = min(environment_recalls)
            environment_min_precision = min(environment_precisions)
            environment_quality = (
                0.65 * environment_macro_f1
                + 0.25 * environment_min_recall
                + 0.10 * environment_min_precision
            )
        current_logs = logs if logs is not None else {}
        validation_loss = min(float(current_logs.get("val_loss", 10.0)), 10.0)
        score = 0.65 * clean_quality + 0.35 * environment_quality - 0.002 * validation_loss
        if score > self.best_score:
            self.best_score = score
            self.best_epoch = epoch
        current_logs["val_macro_f1"] = macro_f1
        current_logs["val_min_recall"] = min_recall
        current_logs["val_min_precision"] = min_precision
        current_logs["val_organic_recall"] = organic_recall
        current_logs["val_organic_precision"] = organic_precision
        current_logs["val_organic_to_paper_rate"] = organic_to_paper_rate
        current_logs["val_environment_macro_f1"] = environment_macro_f1
        current_logs["val_environment_min_recall"] = environment_min_recall
        current_logs["val_environment_min_precision"] = environment_min_precision
        current_logs["val_selection_score"] = score
        print(
            f" - val_macro_f1: {macro_f1:.4f}"
            f" - val_min_recall: {min_recall:.4f}"
            f" - val_min_precision: {min_precision:.4f}"
            f" - val_organic_P/R: {organic_precision:.4f}/{organic_recall:.4f}"
            f" - val_organic_to_paper: {organic_to_paper_rate:.4f}"
            f" - val_env_macro_f1: {environment_macro_f1:.4f}"
            f" - val_env_min_recall: {environment_min_recall:.4f}"
            f" - val_selection_score: {score:.4f}"
        )


def _balanced_focal_loss(label_smoothing: float, gamma: float):
    """Return focal cross entropy for exact-balanced batches."""

    def loss(y_true, logits):
        labels = tf.cast(tf.reshape(y_true, [-1]), tf.int32)
        one_hot = tf.one_hot(labels, depth=len(LABELS), dtype=tf.float32)
        smoothed = one_hot * (1.0 - label_smoothing) + label_smoothing / len(LABELS)
        cross_entropy = tf.nn.softmax_cross_entropy_with_logits(
            labels=smoothed, logits=logits
        )
        true_probability = tf.reduce_sum(
            one_hot * tf.nn.softmax(logits, axis=-1), axis=-1
        )
        modulation = tf.pow(tf.maximum(1.0 - true_probability, 1e-6), gamma)
        return modulation * cross_entropy

    return loss


def _predict(model: tf.keras.Model, dataset: tf.data.Dataset) -> np.ndarray:
    images = dataset.map(
        lambda image, _label: image,
        num_parallel_calls=tf.data.AUTOTUNE,
        deterministic=True,
    )
    return np.asarray(model.predict(images, verbose=0), dtype=np.float32)


def _predict_in_callback(
    model: tf.keras.Model, dataset: tf.data.Dataset
) -> np.ndarray:
    """Run eager inference without nesting a Keras predict loop inside fit."""

    batches = [
        np.asarray(model(images, training=False), dtype=np.float32)
        for images, _labels in dataset
    ]
    if not batches:
        raise ValueError("Validation dataset produced no batches")
    return np.concatenate(batches, axis=0)


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
    if args.focal_gamma < 0:
        raise ValueError("focal-gamma must be non-negative")


if __name__ == "__main__":
    main()
