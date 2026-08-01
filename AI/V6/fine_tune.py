"""Fine-tune the robust V6 checkpoint on mild balanced camera views."""

from __future__ import annotations

import argparse
import copy
import json
import os
from pathlib import Path
import random
import time

from V6.runtime import LABELS, MODEL_VERSION, configure_shared_contract

configure_shared_contract()

import numpy as np  # noqa: E402
import tensorflow as tf  # noqa: E402

from src.dataset import load_dataset_index, make_dataset  # noqa: E402
from src.metadata import read_json, sha256_file, write_json_atomic  # noqa: E402
from src.metrics import classification_metrics  # noqa: E402
from V6.data_pipeline import (  # noqa: E402
    ENVIRONMENT_PROFILE_COUNT,
    balanced_steps_per_epoch,
    make_balanced_calibration_dataset,
    make_environment_validation_dataset,
)
from V6.model import validate_model_contract  # noqa: E402
from V6.train import (  # noqa: E402
    ValidationSelectionMetrics,
    balanced_organic_aware_loss,
    organic_paper_metrics,
    predict_logits,
)


V6_DIR = Path(__file__).resolve().parent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=V6_DIR / "dataset_indexed")
    parser.add_argument(
        "--model", type=Path, default=V6_DIR / "artifacts" / "model_float.keras"
    )
    parser.add_argument(
        "--metadata",
        type=Path,
        default=V6_DIR / "artifacts" / "model_metadata.json",
    )
    parser.add_argument("--out", type=Path, default=V6_DIR / "artifacts_tuned")
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--epochs", type=int, default=30)
    parser.add_argument("--patience", type=int, default=9)
    parser.add_argument("--learning-rate", type=float, default=1e-4)
    parser.add_argument("--weight-decay", type=float, default=5e-5)
    parser.add_argument("--label-smoothing", type=float, default=0.02)
    parser.add_argument("--organic-paper-penalty", type=float, default=0.08)
    parser.add_argument("--paper-multiplier", type=float, default=1.18)
    parser.add_argument("--plastic-multiplier", type=float, default=1.12)
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
    checkpoint = out_dir / ".best.weights.h5"
    output_model = out_dir / "model_float.keras"

    index = load_dataset_index(data_dir)
    metadata = read_json(metadata_path)
    if metadata.get("model_version") != MODEL_VERSION:
        raise ValueError("Base metadata is not V6")
    if metadata.get("dataset", {}).get("dataset_sha256") != index.dataset_sha256:
        raise ValueError("Fine-tune dataset differs from base model metadata")
    expected_hash = metadata.get("artifacts", {}).get("float_model", {}).get("sha256")
    if expected_hash != sha256_file(model_path):
        raise ValueError("Base float model hash differs from metadata")

    train_samples = index.for_split("train")
    validation_samples = index.for_split("validation")
    test_samples = index.for_split("test")
    train_dataset = make_balanced_calibration_dataset(
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

    model = tf.keras.models.load_model(model_path, compile=False)
    validate_model_contract(model)
    class_multipliers = (
        args.paper_multiplier,
        args.plastic_multiplier,
        0.96,
        0.96,
    )
    model.compile(
        optimizer=tf.keras.optimizers.AdamW(
            learning_rate=args.learning_rate,
            weight_decay=args.weight_decay,
            global_clipnorm=5.0,
        ),
        loss=balanced_organic_aware_loss(
            label_smoothing=args.label_smoothing,
            organic_paper_penalty=args.organic_paper_penalty,
            organic_paper_margin=0.20,
            class_multipliers=class_multipliers,
        ),
        metrics=[tf.keras.metrics.SparseCategoricalAccuracy(name="accuracy")],
    )
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
        steps_per_epoch=balanced_steps_per_epoch(train_samples, args.batch_size),
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
    )
    if not checkpoint.is_file():
        raise RuntimeError("Fine-tuning did not produce a checkpoint")
    model.load_weights(checkpoint)
    model.save(output_model)

    validation_logits = predict_logits(model, validation_dataset)
    test_truth = np.asarray(
        [sample.label_id for sample in test_samples], dtype=np.int64
    )
    test_logits = predict_logits(model, test_dataset)
    config = {
        **vars(args),
        "data": str(data_dir),
        "model": str(model_path),
        "metadata": str(metadata_path),
        "out": str(out_dir),
        "model_version": MODEL_VERSION,
        "base_float_sha256": sha256_file(model_path),
        "balance_strategy": "exact round-robin class sampling",
        "augmentation": "mild camera calibration with 22% extreme-light retention",
        "class_multipliers": dict(zip(LABELS, class_multipliers, strict=True)),
    }
    metrics = {
        "model_version": MODEL_VERSION,
        "stage": "mild_balanced_camera_fine_tune",
        "dataset": index.summary(),
        "model_parameters": int(model.count_params()),
        "best_epoch": int(selector.best_epoch + 1),
        "epochs_ran": len(history.history.get("loss", [])),
        "training_seconds": round(time.perf_counter() - started, 3),
        "validation": classification_metrics(validation_truth, validation_logits),
        "test": classification_metrics(test_truth, test_logits),
        "targeted_error": organic_paper_metrics(test_truth, test_logits),
    }
    tuned_metadata = copy.deepcopy(metadata)
    tuned_metadata["training_variant"] = (
        "AI/V6 robust base followed by mild balanced camera fine-tuning"
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
    checkpoint.unlink(missing_ok=True)
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


if __name__ == "__main__":
    main()

