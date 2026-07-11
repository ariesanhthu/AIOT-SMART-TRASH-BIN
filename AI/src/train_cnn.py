from __future__ import annotations

import argparse
import json
from pathlib import Path
import random
import time

import numpy as np
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix
from sklearn.metrics import f1_score, recall_score
import tensorflow as tf

try:
    from .dataset_cnn import (
        ID_TO_LABEL,
        load_dataset_splits,
        load_images,
        make_tf_dataset,
    )
    from .model_tiny_cnn import build_deploy_model, build_tiny_cnn
except ImportError:
    from dataset_cnn import ID_TO_LABEL, load_dataset_splits, load_images, make_tf_dataset
    from model_tiny_cnn import build_deploy_model, build_tiny_cnn


class MacroF1Checkpoint(tf.keras.callbacks.Callback):
    def __init__(
        self,
        x_validation: np.ndarray,
        y_validation: np.ndarray,
        best_path: Path,
        batch_size: int,
    ) -> None:
        super().__init__()
        self.x_validation = x_validation
        self.y_validation = y_validation
        self.best_path = best_path
        self.batch_size = batch_size
        self.best_macro_f1 = -1.0

    def on_epoch_end(self, epoch: int, logs: dict | None = None) -> None:
        logs = logs or {}
        logits = self.model.predict(
            self.x_validation, batch_size=self.batch_size, verbose=0
        )
        y_pred = np.argmax(logits, axis=1)
        macro_f1 = float(
            f1_score(
                self.y_validation,
                y_pred,
                labels=sorted(ID_TO_LABEL),
                average="macro",
                zero_division=0,
            )
        )
        recalls = recall_score(
            self.y_validation,
            y_pred,
            labels=sorted(ID_TO_LABEL),
            average=None,
            zero_division=0,
        )
        logs["val_macro_f1"] = macro_f1
        logs["val_recall_paper"] = float(recalls[0])
        logs["val_recall_plastic"] = float(recalls[1])
        print(
            f" - val_macro_f1: {macro_f1:.4f}"
            f" - val_recall_paper: {recalls[0]:.4f}"
            f" - val_recall_plastic: {recalls[1]:.4f}"
        )
        if macro_f1 > self.best_macro_f1:
            self.best_macro_f1 = macro_f1
            self.model.save(self.best_path, include_optimizer=False)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train the Tiny CNN trash classifier.")
    parser.add_argument("--data", default="trashnet/data")
    parser.add_argument("--image-size", type=int, default=96)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--epochs", type=int, default=100)
    parser.add_argument("--patience", type=int, default=15)
    parser.add_argument("--learning-rate", type=float, default=0.001)
    parser.add_argument("--weight-decay", type=float, default=0.0001)
    parser.add_argument("--label-smoothing", type=float, default=0.05)
    parser.add_argument("--out", default="artifacts")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--no-augment", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    set_reproducible_seed(args.seed)
    started_at = time.perf_counter()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_path = out_dir / "model_best.keras"
    model_path = out_dir / "model_float.keras"

    splits = load_dataset_splits(args.data, seed=args.seed)
    print(json.dumps(splits.manifest(), indent=2, ensure_ascii=False))

    x_train, y_train, skipped_train = load_images(
        splits.train_known, args.image_size, verbose=True
    )
    x_val, y_val, skipped_val = load_images(
        splits.validation_known, args.image_size, verbose=True
    )
    x_test, y_test, skipped_test = load_images(
        splits.test_known, args.image_size, verbose=True
    )

    train_ds = make_tf_dataset(
        x_train,
        y_train,
        args.batch_size,
        shuffle=True,
        augment=not args.no_augment,
        seed=args.seed,
    )
    val_ds = make_tf_dataset(
        x_val,
        y_val,
        args.batch_size,
        shuffle=False,
        augment=False,
        seed=args.seed,
    )

    model = build_tiny_cnn(args.image_size, num_classes=len(ID_TO_LABEL))
    optimizer = build_optimizer(args.learning_rate, args.weight_decay)
    loss = tf.keras.losses.SparseCategoricalCrossentropy(
        from_logits=True,
        ignore_class=None,
        reduction="sum_over_batch_size",
    )
    if args.label_smoothing > 0:
        loss = sparse_loss_with_label_smoothing(args.label_smoothing)

    model.compile(
        optimizer=optimizer,
        loss=loss,
        metrics=[tf.keras.metrics.SparseCategoricalAccuracy(name="accuracy")],
    )
    model.summary()

    callbacks = [
        MacroF1Checkpoint(x_val, y_val, checkpoint_path, args.batch_size),
        tf.keras.callbacks.EarlyStopping(
            monitor="val_loss",
            patience=args.patience,
            restore_best_weights=True,
        ),
        tf.keras.callbacks.ReduceLROnPlateau(
            monitor="val_loss",
            factor=0.5,
            patience=max(4, args.patience // 3),
            min_lr=1e-5,
        ),
    ]

    history = model.fit(
        train_ds,
        validation_data=val_ds,
        epochs=args.epochs,
        callbacks=callbacks,
        verbose=2,
    )

    best_model = (
        tf.keras.models.load_model(checkpoint_path, compile=False)
        if checkpoint_path.is_file()
        else model
    )
    deploy_model = build_deploy_model(best_model)
    deploy_model.save(model_path, include_optimizer=False)

    val_metrics = evaluate_logits_model(best_model, x_val, y_val)
    test_metrics = evaluate_logits_model(best_model, x_test, y_test)

    metrics = {
        "model_version": "tinycnn-v1-float",
        "dataset": splits.manifest(),
        "seed": args.seed,
        "image_size": args.image_size,
        "batch_size": args.batch_size,
        "epochs_ran": len(history.history.get("loss", [])),
        "training_seconds": round(time.perf_counter() - started_at, 3),
        "skipped_images": skipped_train + skipped_val + skipped_test,
        "validation": val_metrics,
        "test": test_metrics,
    }

    write_json(out_dir / "labels.json", {str(key): value for key, value in ID_TO_LABEL.items()})
    write_json(out_dir / "training_config.json", vars(args))
    write_json(out_dir / "metrics_float.json", metrics)
    write_json(out_dir / "metrics.json", {"float": metrics})

    print_metric_summary("VALIDATION", val_metrics)
    print_metric_summary("TEST", test_metrics)
    print(f"Saved float deploy model: {model_path}")
    print(f"Saved metrics: {out_dir / 'metrics_float.json'}")


def sparse_loss_with_label_smoothing(label_smoothing: float):
    categorical_loss = tf.keras.losses.CategoricalCrossentropy(
        from_logits=True,
        label_smoothing=label_smoothing,
    )

    def loss(y_true, y_pred):
        y_true = tf.cast(tf.reshape(y_true, [-1]), tf.int32)
        y_true = tf.one_hot(y_true, depth=len(ID_TO_LABEL))
        return categorical_loss(y_true, y_pred)

    return loss


def build_optimizer(learning_rate: float, weight_decay: float):
    if hasattr(tf.keras.optimizers, "AdamW"):
        return tf.keras.optimizers.AdamW(
            learning_rate=learning_rate, weight_decay=weight_decay
        )
    return tf.keras.optimizers.Adam(learning_rate=learning_rate)


def evaluate_logits_model(
    model: tf.keras.Model,
    x: np.ndarray,
    y: np.ndarray,
) -> dict:
    logits = model.predict(x, batch_size=32, verbose=0)
    predicted = np.argmax(logits, axis=1)
    labels = sorted(ID_TO_LABEL)
    target_names = [ID_TO_LABEL[index] for index in labels]
    report = classification_report(
        y,
        predicted,
        labels=labels,
        target_names=target_names,
        output_dict=True,
        zero_division=0,
    )
    return {
        "accuracy": float(accuracy_score(y, predicted)),
        "macro_f1": float(
            f1_score(y, predicted, labels=labels, average="macro", zero_division=0)
        ),
        "recall_paper": float(report["paper"]["recall"]),
        "recall_plastic": float(report["plastic"]["recall"]),
        "classification_report": report,
        "confusion_matrix": confusion_matrix(y, predicted, labels=labels).tolist(),
    }


def print_metric_summary(name: str, metrics: dict) -> None:
    print(f"\n===== {name} =====")
    print(f"Accuracy: {metrics['accuracy']:.4f}")
    print(f"Macro F1: {metrics['macro_f1']:.4f}")
    print(f"Recall paper: {metrics['recall_paper']:.4f}")
    print(f"Recall plastic: {metrics['recall_plastic']:.4f}")
    print("Confusion matrix [paper, plastic]:")
    print(np.asarray(metrics["confusion_matrix"]))


def set_reproducible_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    tf.keras.utils.set_random_seed(seed)


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
