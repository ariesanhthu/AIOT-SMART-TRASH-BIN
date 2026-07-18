"""Evaluate the current V2 float and INT8 models on an external dataset split."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import numpy as np

from src.config import LABELS
from src.dataset import load_dataset_index, make_dataset
from src.evaluate_model import KerasPredictor, TFLitePredictor
from src.metadata import (
    read_json,
    sha256_file,
    verify_artifact_hash,
    write_json_atomic,
    write_text_atomic,
)
from src.metrics import classification_metrics, stable_softmax


V2_DIR = Path(__file__).resolve().parent
AI_DIR = V2_DIR.parent
DEFAULT_DATASET = AI_DIR / "DATASET-V1-FULL"
DEFAULT_ARTIFACTS = V2_DIR / "artifacts"
DEFAULT_OUT = DEFAULT_ARTIFACTS / "evaluation_dataset_v1_full"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=DEFAULT_DATASET)
    parser.add_argument(
        "--split",
        choices=("train", "validation", "test"),
        default="test",
    )
    parser.add_argument("--artifacts", type=Path, default=DEFAULT_ARTIFACTS)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--seed", type=int, default=42)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.batch_size < 1:
        raise ValueError("batch-size must be positive")

    data_dir = args.data.expanduser().resolve()
    artifacts = args.artifacts.expanduser().resolve()
    out_dir = args.out.expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    float_path = artifacts / "model_float.keras"
    int8_path = artifacts / "model_int8.tflite"
    metadata_path = artifacts / "model_metadata.json"

    metadata = read_json(metadata_path)
    verify_artifact_hash(metadata, "float_model", float_path)
    verify_artifact_hash(metadata, "int8_model", int8_path)
    index = load_dataset_index(data_dir)
    samples = index.for_split(args.split)
    dataset = make_dataset(
        samples,
        batch_size=args.batch_size,
        training=False,
        seed=args.seed,
    )
    truth = np.asarray([sample.label_id for sample in samples], dtype=np.int64)

    float_logits = KerasPredictor(float_path).predict_dataset(dataset)
    int8_logits = TFLitePredictor(int8_path).predict_dataset(dataset)
    float_metrics = classification_metrics(truth, float_logits)
    int8_metrics = classification_metrics(truth, int8_logits)
    float_predictions = np.argmax(float_logits, axis=1)
    int8_predictions = np.argmax(int8_logits, axis=1)
    agreement = float(np.mean(float_predictions == int8_predictions))
    comparison = {
        "samples": len(samples),
        "float_int8_class_agreement": agreement,
        "accuracy_change_float_to_int8": float(
            int8_metrics["accuracy"] - float_metrics["accuracy"]
        ),
    }
    common = {
        "dataset": str(data_dir),
        "dataset_sha256": index.dataset_sha256,
        "split": args.split,
        "class_order": list(LABELS),
        "samples": len(samples),
    }
    float_payload = {
        **common,
        "model": str(float_path),
        "model_sha256": sha256_file(float_path),
        "metrics": float_metrics,
    }
    int8_payload = {
        **common,
        "model": str(int8_path),
        "model_sha256": sha256_file(int8_path),
        "metrics": int8_metrics,
    }
    write_json_atomic(out_dir / "metrics_float.json", float_payload)
    write_json_atomic(out_dir / "metrics_int8.json", int8_payload)
    write_json_atomic(out_dir / "comparison.json", comparison)
    write_text_atomic(
        out_dir / "predictions.csv",
        _prediction_csv(
            samples,
            float_logits,
            int8_logits,
            float_predictions,
            int8_predictions,
        ),
    )
    write_text_atomic(
        out_dir / "RESULT.md",
        _render_report(common, float_metrics, int8_metrics, comparison),
    )
    print(
        json.dumps(
            {
                "float": float_metrics,
                "int8": int8_metrics,
                "comparison": comparison,
                "out": str(out_dir),
            },
            indent=2,
            ensure_ascii=False,
        )
    )


def _prediction_csv(
    samples,
    float_logits: np.ndarray,
    int8_logits: np.ndarray,
    float_predictions: np.ndarray,
    int8_predictions: np.ndarray,
) -> str:
    from io import StringIO

    float_probabilities = stable_softmax(float_logits)
    int8_probabilities = stable_softmax(int8_logits)
    output = StringIO(newline="")
    fieldnames = [
        "relative_path",
        "label",
        "float_prediction",
        "float_confidence",
        "float_correct",
        "int8_prediction",
        "int8_confidence",
        "int8_correct",
        "float_int8_agree",
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    for index, sample in enumerate(samples):
        float_prediction = int(float_predictions[index])
        int8_prediction = int(int8_predictions[index])
        writer.writerow(
            {
                "relative_path": sample.relative_path,
                "label": sample.label,
                "float_prediction": LABELS[float_prediction],
                "float_confidence": f"{float_probabilities[index, float_prediction]:.8f}",
                "float_correct": float_prediction == sample.label_id,
                "int8_prediction": LABELS[int8_prediction],
                "int8_confidence": f"{int8_probabilities[index, int8_prediction]:.8f}",
                "int8_correct": int8_prediction == sample.label_id,
                "float_int8_agree": float_prediction == int8_prediction,
            }
        )
    return output.getvalue()


def _render_report(
    common: dict,
    float_metrics: dict,
    int8_metrics: dict,
    comparison: dict,
) -> str:
    rows = "\n".join(
        f"| {label} | {int(int8_metrics['per_class'][label]['support'])} | "
        f"{100 * float_metrics['per_class'][label]['recall']:.2f}% | "
        f"{100 * int8_metrics['per_class'][label]['recall']:.2f}% |"
        for label in LABELS
    )
    confusion = int8_metrics["confusion_matrix"]
    return f"""# Test model V2 trên DATASET-V1-FULL

- Split: `{common['split']}`.
- Số ảnh: **{common['samples']}**.
- Thứ tự lớp: `paper, plastic, organic`.
- Dataset SHA-256: `{common['dataset_sha256']}`.

| Model | Accuracy | Balanced accuracy | Macro-F1 |
|---|---:|---:|---:|
| Float Keras | {100 * float_metrics['accuracy']:.2f}% | {100 * float_metrics['balanced_accuracy']:.2f}% | {100 * float_metrics['macro_f1']:.2f}% |
| INT8 deploy | {100 * int8_metrics['accuracy']:.2f}% | {100 * int8_metrics['balanced_accuracy']:.2f}% | {100 * int8_metrics['macro_f1']:.2f}% |

| Lớp | Số ảnh | Recall float | Recall INT8 |
|---|---:|---:|---:|
{rows}

- Độ đồng thuận float/INT8: **{100 * comparison['float_int8_class_agreement']:.2f}%**.
- Thay đổi accuracy float → INT8: **{100 * comparison['accuracy_change_float_to_int8']:+.2f} điểm phần trăm**.

Confusion matrix INT8 (hàng = nhãn thật, cột = dự đoán; `paper, plastic, organic`):

```text
{confusion[0]}
{confusion[1]}
{confusion[2]}
```

`predictions.csv` chứa kết quả của từng ảnh.
"""


if __name__ == "__main__":
    main()
