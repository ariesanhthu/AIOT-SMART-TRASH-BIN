"""Evaluate float and INT8 models on every original image, including all plastic."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import numpy as np

from src.config import CLASS_TO_INDEX, LABELS
from src.dataset import preprocess_file
from src.evaluate_model import KerasPredictor, TFLitePredictor
from src.metrics import classification_metrics, stable_softmax
from src.metadata import write_json_atomic, write_text_atomic


V2_DIR = Path(__file__).resolve().parent
AI_DIR = V2_DIR.parent
DEFAULT_DATASET = AI_DIR / "DATASET"
DEFAULT_PREPARED = V2_DIR / "dataset_augmented"
DEFAULT_ARTIFACTS = V2_DIR / "artifacts"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--prepared", type=Path, default=DEFAULT_PREPARED)
    parser.add_argument("--artifacts", type=Path, default=DEFAULT_ARTIFACTS)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    dataset = args.dataset.resolve()
    artifacts = args.artifacts.resolve()
    originals = _read_original_lineage(args.prepared.resolve() / "lineage.csv")
    float_predictor = KerasPredictor(artifacts / "model_float.keras")
    int8_predictor = TFLitePredictor(artifacts / "model_int8.tflite")

    rows: list[dict[str, object]] = []
    truths: list[int] = []
    float_logits: list[np.ndarray] = []
    int8_logits: list[np.ndarray] = []
    for item in originals:
        source_relative = str(item["source_relative_path"])
        image = preprocess_file(dataset.joinpath(*source_relative.split("/")))
        float_scores = float_predictor.predict_one(image)
        int8_scores = int8_predictor.predict_one(image)
        float_probabilities = stable_softmax(float_scores)
        int8_probabilities = stable_softmax(int8_scores)
        truth = CLASS_TO_INDEX[str(item["label"])]
        float_prediction = int(np.argmax(float_scores))
        int8_prediction = int(np.argmax(int8_scores))
        truths.append(truth)
        float_logits.append(float_scores)
        int8_logits.append(int8_scores)
        rows.append(
            {
                "source_relative_path": source_relative,
                "prepared_split": item["prepared_split"],
                "label": item["label"],
                "float_prediction": LABELS[float_prediction],
                "float_confidence": float(float_probabilities[float_prediction]),
                "float_correct": float_prediction == truth,
                "int8_prediction": LABELS[int8_prediction],
                "int8_confidence": float(int8_probabilities[int8_prediction]),
                "int8_correct": int8_prediction == truth,
                "float_int8_agree": float_prediction == int8_prediction,
            }
        )

    truth_array = np.asarray(truths, dtype=np.int64)
    float_array = np.vstack(float_logits)
    int8_array = np.vstack(int8_logits)
    audit = {
        "dataset": str(dataset),
        "original_samples": len(rows),
        "scope": "Every non-augmented image listed in prepared lineage.",
        "split_meanings": {
            "train": "original was included in training (metrics are not independent)",
            "test": "independent internal holdout from AI/DATASET/train",
            "validation": "AI/DATASET/validation used for checkpoint selection",
        },
        "float": _summarize(rows, truth_array, float_array, "float"),
        "int8": _summarize(rows, truth_array, int8_array, "int8"),
        "float_int8_agreement": float(
            np.mean(np.argmax(float_array, axis=1) == np.argmax(int8_array, axis=1))
        ),
    }
    write_json_atomic(artifacts / "original_audit.json", audit)
    write_text_atomic(artifacts / "original_predictions.csv", _rows_to_csv(rows))
    print(json.dumps(audit, indent=2, ensure_ascii=False))


def _read_original_lineage(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = [
            dict(row)
            for row in csv.DictReader(handle)
            if row.get("kind") == "original"
        ]
    if not rows:
        raise ValueError(f"No original rows found in {path}")
    paths = [row["source_relative_path"] for row in rows]
    if len(paths) != len(set(paths)):
        raise ValueError("Original lineage contains duplicate source paths")
    return sorted(rows, key=lambda row: row["source_relative_path"])


def _summarize(
    rows: list[dict[str, object]],
    truth: np.ndarray,
    logits: np.ndarray,
    model_prefix: str,
) -> dict:
    groups: dict[str, dict] = {}
    for split in ("train", "test", "validation"):
        indices = np.asarray(
            [index for index, row in enumerate(rows) if row["prepared_split"] == split],
            dtype=np.int64,
        )
        groups[split] = classification_metrics(truth[indices], logits[indices])
    groups["all_originals"] = classification_metrics(truth, logits)

    plastic: dict[str, dict[str, object]] = {}
    for name, split in (
        ("train_seen", "train"),
        ("internal_test", "test"),
        ("external_validation", "validation"),
        ("all_plastic_originals", None),
    ):
        selected = [
            row
            for row in rows
            if row["label"] == "plastic"
            and (split is None or row["prepared_split"] == split)
        ]
        prediction_key = f"{model_prefix}_prediction"
        predicted_counts = {
            label: sum(row[prediction_key] == label for row in selected)
            for label in LABELS
        }
        correct = sum(bool(row[f"{model_prefix}_correct"]) for row in selected)
        plastic[name] = {
            "samples": len(selected),
            "correct": correct,
            "accuracy": correct / len(selected),
            "predicted_counts": predicted_counts,
        }
    return {"groups": groups, "plastic": plastic}


def _rows_to_csv(rows: list[dict[str, object]]) -> str:
    if not rows:
        raise ValueError("Cannot write an empty prediction table")
    from io import StringIO

    output = StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()


if __name__ == "__main__":
    main()
