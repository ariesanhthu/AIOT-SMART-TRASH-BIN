"""Train the V4 TinyCNN as V6 with balanced camera-domain inputs."""

from __future__ import annotations

import argparse
import json
import os
import platform
from pathlib import Path
import random
import time

from V6.runtime import LABELS, MODEL_VERSION, configure_shared_contract

configure_shared_contract()

import numpy as np  # noqa: E402
import tensorflow as tf  # noqa: E402

from src.dataset import load_dataset_index, make_dataset  # noqa: E402
from src.metadata import base_model_metadata, sha256_file, write_json_atomic  # noqa: E402
from src.metrics import classification_metrics  # noqa: E402
from V6.data_pipeline import (  # noqa: E402
    ENVIRONMENT_PROFILE_COUNT,
    balanced_steps_per_epoch,
    make_balanced_training_dataset,
    make_environment_validation_dataset,
)
from V6.model import build_tiny_cnn_v6  # noqa: E402


V6_DIR = Path(__file__).resolve().parent
DEFAULT_DATA = V6_DIR / "dataset_indexed"
DEFAULT_OUT = V6_DIR / "artifacts"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--epochs", type=int, default=90)
    parser.add_argument("--patience", type=int, default=16)
    parser.add_argument("--learning-rate", type=float, default=5e-4)
    parser.add_argument("--weight-decay", type=float, default=1e-4)
    parser.add_argument("--label-smoothing", type=float, default=0.025)
    parser.add_argument("--organic-paper-penalty", type=float, default=0.14)
    parser.add_argument("--organic-paper-margin", type=float, default=0.30)
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
    checkpoint = out_dir / ".best.weights.h5"
    float_model = out_dir / "model_float.keras"

    index = load_dataset_index(data_dir)
    train_samples = index.for_split("train")
    validation_samples = index.for_split("validation")
    test_samples = index.for_split("test")
    raw_counts = {
        label: sum(sample.label == label for sample in train_samples) for label in LABELS
    }
    steps_per_epoch = balanced_steps_per_epoch(train_samples, args.batch_size)
    effective_per_class = max(raw_counts.values())

    train_dataset = make_balanced_training_dataset(
        train_samples, batch_size=args.batch_size, seed=args.seed
    )
    validation_dataset = make_dataset(
        validation_samples,
        batch_size=args.batch_size,
        training=False,
        seed=args.seed,
    ).cache()
    environment_validation = make_environment_validation_dataset(
        validation_samples, batch_size=args.batch_size
    )
    test_dataset = make_dataset(
        test_samples,
        batch_size=args.batch_size,
        training=False,
        seed=args.seed,
    )

    model = build_tiny_cnn_v6()
    model.compile(
        optimizer=tf.keras.optimizers.AdamW(
            learning_rate=args.learning_rate,
            weight_decay=args.weight_decay,
            global_clipnorm=5.0,
        ),
        loss=balanced_organic_aware_loss(
            label_smoothing=args.label_smoothing,
            organic_paper_penalty=args.organic_paper_penalty,
            organic_paper_margin=args.organic_paper_margin,
        ),
        metrics=[tf.keras.metrics.SparseCategoricalAccuracy(name="accuracy")],
    )
    model.summary()

    validation_truth = np.asarray(
        [sample.label_id for sample in validation_samples], dtype=np.int64
    )
    selector = ValidationSelectionMetrics(
        validation_dataset,
        validation_truth,
        environment_validation,
        np.tile(validation_truth, ENVIRONMENT_PROFILE_COUNT),
    )
    history = model.fit(
        train_dataset,
        validation_data=validation_dataset,
        steps_per_epoch=steps_per_epoch,
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
        ],
        verbose=2,
    )
    if not checkpoint.is_file():
        raise RuntimeError("Training did not produce a best checkpoint")
    model.load_weights(checkpoint)
    deployment_model = build_tiny_cnn_v6()
    deployment_model.set_weights(model.get_weights())
    deployment_model.save(float_model)

    validation_metrics = classification_metrics(
        validation_truth, predict_logits(deployment_model, validation_dataset)
    )
    test_truth = np.asarray(
        [sample.label_id for sample in test_samples], dtype=np.int64
    )
    test_logits = predict_logits(deployment_model, test_dataset)
    test_metrics = classification_metrics(test_truth, test_logits)
    targeted = organic_paper_metrics(test_truth, test_logits)

    config = {
        **vars(args),
        "data": str(data_dir),
        "out": str(out_dir),
        "labels": list(LABELS),
        "model_version": MODEL_VERSION,
        "architecture": "V4 TinyCNN unchanged: Conv2D x5, Mean, Dense",
        "raw_train_counts": raw_counts,
        "balance_strategy": "exact round-robin class sampling",
        "effective_samples_per_class_per_epoch": effective_per_class,
        "effective_total_per_epoch": effective_per_class * len(LABELS),
        "steps_per_epoch": steps_per_epoch,
        "preprocessing": (
            "center crop, floor nearest resize, RGB565, bounded integer mean-luma gain"
        ),
        "augmentation": {
            "geometry": "flip, rotation +/-10deg, bounded scale/translation/shear",
            "lighting": (
                "mostly mild V4/camera views with rare overexposure, low light, "
                "small white-balance shifts and local shadow"
            ),
            "sensor": "rare mild blur/low resolution/noise plus exact RGB565",
            "scope": "train only; clean validation/test remain unchanged",
        },
        "python_version": platform.python_version(),
        "tensorflow_version": tf.__version__,
        "numpy_version": np.__version__,
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
        "targeted_error": targeted,
    }
    metadata = base_model_metadata(index.summary(), args.seed)
    metadata["training_variant"] = (
        "AI/V6 V4-compatible TinyCNN, exact-balanced sampling, luma-normalized "
        "camera-domain augmentation and organic-paper confusion penalty"
    )
    metadata["artifacts"]["float_model"] = {
        "file": float_model.name,
        "size_bytes": float_model.stat().st_size,
        "sha256": sha256_file(float_model),
    }
    write_json_atomic(
        out_dir / "labels.json",
        {
            "labels": list(LABELS),
            "class_to_index": {label: index for index, label in enumerate(LABELS)},
        },
    )
    write_json_atomic(out_dir / "training_config.json", config)
    write_json_atomic(
        out_dir / "training_history.json",
        {key: [float(value) for value in values] for key, values in history.history.items()},
    )
    write_json_atomic(out_dir / "training_metrics.json", metrics)
    write_json_atomic(out_dir / "model_metadata.json", metadata)
    checkpoint.unlink(missing_ok=True)
    print(json.dumps(metrics, indent=2, ensure_ascii=False))


class ValidationSelectionMetrics(tf.keras.callbacks.Callback):
    """Choose checkpoints on clean/stress macro quality and organic confusion."""

    def __init__(
        self,
        clean_dataset: tf.data.Dataset,
        clean_truth: np.ndarray,
        environment_dataset: tf.data.Dataset,
        environment_truth: np.ndarray,
    ) -> None:
        super().__init__()
        self.clean_dataset = clean_dataset
        self.clean_truth = clean_truth
        self.environment_dataset = environment_dataset
        self.environment_truth = environment_truth
        self.best_score = -np.inf
        self.best_epoch = 0

    def on_epoch_end(self, epoch: int, logs: dict | None = None) -> None:
        if self.model is None:
            raise RuntimeError("Validation callback is not attached to a model")
        clean_logits = predict_eager(self.model, self.clean_dataset)
        environment_logits = predict_eager(self.model, self.environment_dataset)
        clean = classification_metrics(self.clean_truth, clean_logits)
        environment = classification_metrics(self.environment_truth, environment_logits)
        clean_target = organic_paper_metrics(self.clean_truth, clean_logits)
        environment_target = organic_paper_metrics(
            self.environment_truth, environment_logits
        )
        clean_recalls = [clean["per_class"][label]["recall"] for label in LABELS]
        environment_recalls = [
            environment["per_class"][label]["recall"] for label in LABELS
        ]
        clean_quality = 0.72 * clean["macro_f1"] + 0.28 * min(clean_recalls)
        environment_quality = (
            0.72 * environment["macro_f1"] + 0.28 * min(environment_recalls)
        )
        score = (
            0.58 * clean_quality
            + 0.42 * environment_quality
            - 0.08 * clean_target["organic_to_paper_rate"]
            - 0.12 * environment_target["organic_to_paper_rate"]
        )
        if score > self.best_score:
            self.best_score = score
            self.best_epoch = epoch
        current = logs if logs is not None else {}
        current["val_macro_f1"] = float(clean["macro_f1"])
        current["val_min_recall"] = float(min(clean_recalls))
        current["val_organic_recall"] = float(
            clean["per_class"]["organic"]["recall"]
        )
        current["val_organic_to_paper_rate"] = clean_target[
            "organic_to_paper_rate"
        ]
        current["val_environment_macro_f1"] = float(environment["macro_f1"])
        current["val_environment_min_recall"] = float(min(environment_recalls))
        current["val_environment_organic_to_paper_rate"] = environment_target[
            "organic_to_paper_rate"
        ]
        current["val_selection_score"] = float(score)
        print(
            f" - val_macro_f1: {clean['macro_f1']:.4f}"
            f" - val_min_recall: {min(clean_recalls):.4f}"
            f" - val_organic_recall: {clean['per_class']['organic']['recall']:.4f}"
            f" - val_organic_to_paper: {clean_target['organic_to_paper_rate']:.4f}"
            f" - val_env_macro_f1: {environment['macro_f1']:.4f}"
            f" - val_env_min_recall: {min(environment_recalls):.4f}"
            f" - val_selection_score: {score:.4f}"
        )


def balanced_organic_aware_loss(
    *,
    label_smoothing: float,
    organic_paper_penalty: float,
    organic_paper_margin: float,
    class_multipliers: tuple[float, ...] | None = None,
):
    """Cross entropy plus a small margin only for organic->paper errors."""

    paper_id = LABELS.index("paper")
    organic_id = LABELS.index("organic")
    if class_multipliers is None:
        class_multipliers = tuple(1.0 for _ in LABELS)
    if len(class_multipliers) != len(LABELS) or any(
        value <= 0 for value in class_multipliers
    ):
        raise ValueError("class_multipliers must contain one positive value per class")
    multiplier_tensor = tf.constant(class_multipliers, dtype=tf.float32)

    def loss(y_true, logits):
        labels = tf.cast(tf.reshape(y_true, [-1]), tf.int32)
        one_hot = tf.one_hot(labels, depth=len(LABELS), dtype=tf.float32)
        smoothed = one_hot * (1.0 - label_smoothing) + label_smoothing / len(LABELS)
        cross_entropy = tf.nn.softmax_cross_entropy_with_logits(
            labels=smoothed, logits=logits
        )
        organic_mask = tf.cast(tf.equal(labels, organic_id), tf.float32)
        confused_margin = tf.nn.softplus(
            logits[:, paper_id] - logits[:, organic_id] + organic_paper_margin
        )
        per_sample = cross_entropy + organic_paper_penalty * organic_mask * confused_margin
        return per_sample * tf.gather(multiplier_tensor, labels)

    return loss


def organic_paper_metrics(truth: np.ndarray, logits: np.ndarray) -> dict:
    truth = np.asarray(truth, dtype=np.int64)
    predictions = np.argmax(logits, axis=1)
    organic_mask = truth == LABELS.index("organic")
    organic_total = int(np.sum(organic_mask))
    confused = int(np.sum(organic_mask & (predictions == LABELS.index("paper"))))
    return {
        "organic_total": organic_total,
        "organic_predicted_as_paper": confused,
        "organic_to_paper_rate": float(confused / organic_total),
    }


def predict_logits(model: tf.keras.Model, dataset: tf.data.Dataset) -> np.ndarray:
    images = dataset.map(
        lambda image, _label: image,
        num_parallel_calls=tf.data.AUTOTUNE,
        deterministic=True,
    )
    return np.asarray(model.predict(images, verbose=0), dtype=np.float32)


def predict_eager(model: tf.keras.Model, dataset: tf.data.Dataset) -> np.ndarray:
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
        raise ValueError("label-smoothing must be in [0,1)")
    if args.organic_paper_penalty < 0 or args.organic_paper_margin < 0:
        raise ValueError("organic-paper penalty and margin must be non-negative")


if __name__ == "__main__":
    main()
