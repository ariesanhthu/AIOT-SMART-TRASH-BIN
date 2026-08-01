"""Fine-tune robust V5 features with mild balanced camera augmentation."""

from __future__ import annotations

import argparse
import copy
import json
import os
from pathlib import Path
import random
import time

from V5.runtime import LABELS, MODEL_VERSION, configure_shared_contract

configure_shared_contract()

import numpy as np  # noqa: E402
import tensorflow as tf  # noqa: E402

from src.dataset import load_dataset_index, make_dataset  # noqa: E402
from src.metadata import read_json, sha256_file, write_json_atomic  # noqa: E402
from src.metrics import classification_metrics  # noqa: E402
from V5.data_pipeline import (  # noqa: E402
    balanced_steps_per_epoch,
    make_balanced_calibration_dataset,
    make_balanced_training_dataset,
    make_environment_validation_dataset,
)
from V5.model import validate_model_contract  # noqa: E402
from V5.train import (  # noqa: E402
    ValidationSelectionMetrics,
    _balanced_focal_loss,
    _predict,
)


V5_DIR = Path(__file__).resolve().parent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=V5_DIR / "dataset_prepared")
    parser.add_argument(
        "--model", type=Path, default=V5_DIR / "artifacts" / "model_float.keras"
    )
    parser.add_argument(
        "--metadata", type=Path, default=V5_DIR / "artifacts" / "model_metadata.json"
    )
    parser.add_argument("--out", type=Path, default=V5_DIR / "artifacts_tuned")
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--epochs", type=int, default=30)
    parser.add_argument("--patience", type=int, default=8)
    parser.add_argument("--learning-rate", type=float, default=1e-4)
    parser.add_argument("--weight-decay", type=float, default=5e-5)
    parser.add_argument("--label-smoothing", type=float, default=0.02)
    parser.add_argument("--focal-gamma", type=float, default=1.0)
    parser.add_argument(
        "--augmentation", choices=("mild", "robust"), default="mild"
    )
    parser.add_argument("--seed", type=int, default=314159)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.batch_size < 1 or args.epochs < 1 or args.patience < 1:
        raise ValueError("batch-size, epochs and patience must be positive")
    _set_seed(args.seed)
    started = time.perf_counter()
    data_dir = args.data.expanduser().resolve()
    model_path = args.model.expanduser().resolve()
    metadata_path = args.metadata.expanduser().resolve()
    out_dir = args.out.expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_path = out_dir / ".best.weights.h5"
    output_model = out_dir / "model_float.keras"

    index = load_dataset_index(data_dir)
    metadata = read_json(metadata_path)
    if metadata.get("model_version") != MODEL_VERSION:
        raise ValueError("Base metadata is not V5")
    if metadata.get("dataset", {}).get("dataset_sha256") != index.dataset_sha256:
        raise ValueError("Fine-tune dataset differs from base model metadata")
    expected_hash = metadata.get("artifacts", {}).get("float_model", {}).get("sha256")
    if expected_hash != sha256_file(model_path):
        raise ValueError("Base float model hash differs from metadata")

    train_samples = index.for_split("train")
    validation_samples = index.for_split("validation")
    test_samples = index.for_split("test")
    balanced_train_samples = _balanced_samples(train_samples)
    if args.augmentation == "robust":
        train_dataset = make_balanced_training_dataset(
            train_samples, batch_size=args.batch_size, seed=args.seed
        )
    else:
        train_dataset = make_balanced_calibration_dataset(
            train_samples, batch_size=args.batch_size, seed=args.seed
        )
    validation_dataset = make_dataset(
        validation_samples, batch_size=args.batch_size, training=False, seed=args.seed
    ).cache()
    environment_validation_dataset = make_environment_validation_dataset(
        validation_samples, batch_size=args.batch_size
    )
    test_dataset = make_dataset(
        test_samples, batch_size=args.batch_size, training=False, seed=args.seed
    )
    model = tf.keras.models.load_model(model_path, compile=False)
    validate_model_contract(model)
    model.compile(
        optimizer=tf.keras.optimizers.AdamW(
            learning_rate=args.learning_rate,
            weight_decay=args.weight_decay,
            global_clipnorm=5.0,
        ),
        loss=_balanced_focal_loss(args.label_smoothing, args.focal_gamma),
        metrics=[tf.keras.metrics.SparseCategoricalAccuracy(name="accuracy")],
    )
    validation_truth = np.asarray(
        [sample.label_id for sample in validation_samples], dtype=np.int64
    )
    selector = ValidationSelectionMetrics(
        validation_dataset,
        validation_truth,
        environment_validation_dataset=environment_validation_dataset,
        environment_truth=np.tile(validation_truth, 4),
    )
    fit_options = {
        "steps_per_epoch": balanced_steps_per_epoch(train_samples, args.batch_size)
    }
    history = model.fit(
        train_dataset,
        validation_data=validation_dataset,
        epochs=args.epochs,
        callbacks=[
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
                patience=4,
                min_lr=8e-6,
                verbose=1,
            ),
            tf.keras.callbacks.TerminateOnNaN(),
        ],
        verbose=2,
        **fit_options,
    )
    model.load_weights(checkpoint_path)
    model.save(output_model)

    validation_logits = _predict(model, validation_dataset)
    test_truth = np.asarray([sample.label_id for sample in test_samples], dtype=np.int64)
    test_logits = _predict(model, test_dataset)
    validation_metrics = classification_metrics(validation_truth, validation_logits)
    test_metrics = classification_metrics(test_truth, test_logits)
    predictions = np.argmax(test_logits, axis=1)
    organic_id = LABELS.index("organic")
    paper_id = LABELS.index("paper")
    organic_mask = test_truth == organic_id
    organic_to_paper = int(np.sum(organic_mask & (predictions == paper_id)))

    config = {
        **vars(args),
        "data": str(data_dir),
        "model": str(model_path),
        "metadata": str(metadata_path),
        "out": str(out_dir),
        "model_version": MODEL_VERSION,
        "base_float_sha256": sha256_file(model_path),
        "balance_strategy": "exact round-robin class sampling",
        "augmentation": (
            "full environment randomization"
            if args.augmentation == "robust"
            else "mild balanced camera calibration with 20% overexposure/glare"
        ),
        "effective_samples_per_class_per_epoch": max(
            sum(sample.label == label for sample in train_samples) for label in LABELS
        ),
        "effective_total_per_epoch": len(balanced_train_samples),
    }
    metrics = {
        "model_version": MODEL_VERSION,
        "stage": (
            "robust_environment_refresh"
            if args.augmentation == "robust"
            else "mild_balanced_fine_tune"
        ),
        "dataset": index.summary(),
        "model_parameters": int(model.count_params()),
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
    tuned_metadata = copy.deepcopy(metadata)
    tuned_metadata["training_variant"] = (
        "AI/V5 robust training followed by mild balanced camera calibration"
    )
    tuned_metadata["fine_tune"] = config
    tuned_metadata["artifacts"] = {
        "float_model": {
            "file": output_model.name,
            "size_bytes": output_model.stat().st_size,
            "sha256": sha256_file(output_model),
        }
    }
    write_json_atomic(out_dir / "training_config.json", config)
    write_json_atomic(
        out_dir / "training_history.json",
        {key: [float(value) for value in values] for key, values in history.history.items()},
    )
    write_json_atomic(out_dir / "training_metrics.json", metrics)
    write_json_atomic(out_dir / "model_metadata.json", tuned_metadata)
    write_json_atomic(
        out_dir / "labels.json",
        {
            "labels": list(LABELS),
            "class_to_index": {label: index for index, label in enumerate(LABELS)},
        },
    )
    checkpoint_path.unlink(missing_ok=True)
    print(json.dumps(metrics, indent=2, ensure_ascii=False))


def _set_seed(seed: int) -> None:
    os.environ.setdefault("TF_DETERMINISTIC_OPS", "1")
    random.seed(seed)
    np.random.seed(seed)
    tf.keras.utils.set_random_seed(seed)
    try:
        tf.config.experimental.enable_op_determinism()
    except (AttributeError, RuntimeError):
        pass


def _balanced_samples(samples):
    """Repeat references deterministically until every class matches the largest."""

    per_class = [
        [sample for sample in samples if sample.label_id == label_id]
        for label_id in range(len(LABELS))
    ]
    if any(not group for group in per_class):
        raise ValueError("Cannot fine-tune with an empty class")
    target = max(len(group) for group in per_class)
    balanced = []
    for group in per_class:
        balanced.extend(group[index % len(group)] for index in range(target))
    return tuple(balanced)


if __name__ == "__main__":
    main()
