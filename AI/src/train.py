from __future__ import annotations

import argparse
import json
from pathlib import Path
import time

import joblib
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

try:
    from .dataset import ID_TO_LABEL, TrashNetDataset
    from .features import FEATURE_NAMES, extract_features
except ImportError:
    from dataset import ID_TO_LABEL, TrashNetDataset
    from features import FEATURE_NAMES, extract_features


def build_feature_matrix(
    dataset: TrashNetDataset,
    samples: list,
) -> tuple[np.ndarray, np.ndarray, list[str]]:
    features: list[np.ndarray] = []
    labels: list[int] = []
    skipped: list[str] = []

    for index, (sample, encoded_image) in enumerate(
        dataset.iter_encoded(samples), start=1
    ):
        try:
            features.append(extract_features(encoded_image))
            labels.append(sample.label)
        except Exception as exc:
            skipped.append(f"{sample.name}: {exc}")
            print(f"[WARN] Skipping {sample.name}: {exc}")

        if index % 100 == 0 or index == len(samples):
            print(f"Processed {index}/{len(samples)} images")

    if not features:
        raise RuntimeError("No image could be decoded")
    return np.vstack(features), np.asarray(labels, dtype=np.int64), skipped


def evaluate(model: Pipeline, x: np.ndarray, y: np.ndarray) -> dict:
    predicted = model.predict(x)
    target_names = [ID_TO_LABEL[index] for index in sorted(ID_TO_LABEL)]
    return {
        "accuracy": float(accuracy_score(y, predicted)),
        "classification_report": classification_report(
            y,
            predicted,
            labels=sorted(ID_TO_LABEL),
            target_names=target_names,
            output_dict=True,
            zero_division=0,
        ),
        "confusion_matrix": confusion_matrix(
            y, predicted, labels=sorted(ID_TO_LABEL)
        ).tolist(),
    }


def print_evaluation(name: str, metrics: dict) -> None:
    print(f"\n===== {name} =====")
    print(f"Accuracy: {metrics['accuracy']:.4f}")
    print("Confusion matrix [paper, plastic]:")
    print(np.asarray(metrics["confusion_matrix"]))
    for label in ("paper", "plastic"):
        values = metrics["classification_report"][label]
        print(
            f"{label:7s} precision={values['precision']:.4f} "
            f"recall={values['recall']:.4f} f1={values['f1-score']:.4f}"
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Train a lightweight TrashNet paper/plastic classifier."
    )
    parser.add_argument(
        "--data",
        default="trashnet/data/dataset-resized.zip",
        help="TrashNet ZIP or extracted dataset directory.",
    )
    parser.add_argument("--out", default="artifacts", help="Artifact directory.")
    parser.add_argument("--threshold", type=float, default=0.65)
    parser.add_argument(
        "--max-per-class",
        type=int,
        default=None,
        help="Use a reproducible subset per class for a quick sample run.",
    )
    parser.add_argument("--seed", type=int, default=42)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not 0.5 <= args.threshold <= 1.0:
        raise ValueError("--threshold must be between 0.5 and 1.0")

    started_at = time.perf_counter()
    dataset = TrashNetDataset(args.data)
    samples = dataset.collect(args.max_per_class, args.seed)
    print(f"Dataset: {dataset.source}")
    print(f"Selected images: {len(samples)}")

    x, y, skipped = build_feature_matrix(dataset, samples)
    class_counts = {
        ID_TO_LABEL[label_id]: int(np.sum(y == label_id)) for label_id in ID_TO_LABEL
    }
    print(f"Usable class counts: {class_counts}")

    x_train, x_temp, y_train, y_temp = train_test_split(
        x, y, test_size=0.30, random_state=args.seed, stratify=y
    )
    x_val, x_test, y_val, y_test = train_test_split(
        x_temp,
        y_temp,
        test_size=0.50,
        random_state=args.seed,
        stratify=y_temp,
    )

    model = Pipeline(
        [
            ("scaler", StandardScaler()),
            (
                "classifier",
                LogisticRegression(
                    max_iter=2000,
                    class_weight="balanced",
                    solver="lbfgs",
                    random_state=args.seed,
                ),
            ),
        ]
    )
    model.fit(x_train, y_train)

    val_metrics = evaluate(model, x_val, y_val)
    test_metrics = evaluate(model, x_test, y_test)
    print_evaluation("VALIDATION", val_metrics)
    print_evaluation("TEST", test_metrics)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    artifact = {
        "model": model,
        "labels": ID_TO_LABEL,
        "feature_names": FEATURE_NAMES,
        "confidence_threshold": args.threshold,
        "image_size": 64,
    }
    model_path = out_dir / "light_trashnet_model.joblib"
    joblib.dump(artifact, model_path)

    metrics = {
        "dataset": str(dataset.source),
        "seed": args.seed,
        "max_per_class": args.max_per_class,
        "class_counts": class_counts,
        "split_counts": {
            "train": len(y_train), "validation": len(y_val), "test": len(y_test)
        },
        "skipped_images": skipped,
        "validation": val_metrics,
        "test": test_metrics,
        "training_seconds": round(time.perf_counter() - started_at, 3),
    }
    metrics_path = out_dir / "metrics.json"
    metrics_path.write_text(
        json.dumps(metrics, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    print(f"\nSaved model: {model_path}")
    print(f"Saved metrics: {metrics_path}")


if __name__ == "__main__":
    main()
