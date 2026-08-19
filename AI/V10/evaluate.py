"""Evaluate V10 float and quantized models on the exact same held-out images."""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import json
import os
from pathlib import Path

os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")

import numpy as np
import tensorflow as tf

from V10.config import ARTIFACTS_DIR, CLASS_NAMES, DATASET_DIR
from V10.data_pipeline import load_samples, preprocess_file_tensor, samples_for_split
from V10.metrics import classification_metrics


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=DATASET_DIR)
    parser.add_argument("--artifacts", type=Path, default=ARTIFACTS_DIR)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    artifacts = args.artifacts.expanduser().resolve()
    float_path = artifacts / "model_float.keras"
    int8_path = artifacts / "model_int8.tflite"
    if not float_path.is_file() or not int8_path.is_file():
        raise FileNotFoundError("Both model_float.keras and model_int8.tflite are required")
    samples = load_samples(args.data)
    float_model = tf.keras.models.load_model(float_path, compile=False)
    interpreter = tf.lite.Interpreter(model_path=str(int8_path))
    interpreter.allocate_tensors()
    input_detail = interpreter.get_input_details()[0]
    output_detail = interpreter.get_output_details()[0]

    all_rows = []
    results = {}
    for split in ("validation", "test"):
        selected = samples_for_split(samples, split)
        truth = np.asarray([sample.label_id for sample in selected])
        images = np.stack([
            preprocess_file_tensor(tf.constant(str(sample.path))).numpy()
            for sample in selected
        ])
        float_probabilities = float_model.predict(images, verbose=0)
        int8_probabilities = np.stack([
            _invoke_int8(interpreter, input_detail, output_detail, image)
            for image in images
        ])
        float_metrics = classification_metrics(truth, float_probabilities)
        int8_metrics = classification_metrics(truth, int8_probabilities)
        float_predicted = float_probabilities.argmax(axis=1)
        int8_predicted = int8_probabilities.argmax(axis=1)
        results[split] = {
            "images": len(selected),
            "float": float_metrics,
            "int8": int8_metrics,
            "accuracy_delta_int8_minus_float": (
                int8_metrics["accuracy"] - float_metrics["accuracy"]
            ),
            "prediction_disagreements": int(np.sum(float_predicted != int8_predicted)),
            "maximum_probability_absolute_error": float(
                np.max(np.abs(float_probabilities - int8_probabilities))
            ),
            "mean_probability_absolute_error": float(
                np.mean(np.abs(float_probabilities - int8_probabilities))
            ),
        }
        for index, sample in enumerate(selected):
            all_rows.append({
                "split": split,
                "relative_path": sample.relative_path,
                "truth": sample.label,
                "float_prediction": CLASS_NAMES[int(float_predicted[index])],
                "int8_prediction": CLASS_NAMES[int(int8_predicted[index])],
                "float_correct": bool(float_predicted[index] == sample.label_id),
                "int8_correct": bool(int8_predicted[index] == sample.label_id),
                **{
                    f"float_{label}": float(float_probabilities[index, label_id])
                    for label_id, label in enumerate(CLASS_NAMES)
                },
                **{
                    f"int8_{label}": float(int8_probabilities[index, label_id])
                    for label_id, label in enumerate(CLASS_NAMES)
                },
            })

    report = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "labels": list(CLASS_NAMES),
        "preprocessing": "V10 deterministic ESP-TRASH-V3 128x96 contract for both models",
        "same_images_for_float_and_int8": True,
        "results": results,
    }
    (artifacts / "evaluation_comparison.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    _write_predictions(artifacts / "evaluation_predictions.csv", all_rows)
    print(json.dumps(report, indent=2, ensure_ascii=False))


def _invoke_int8(interpreter, input_detail, output_detail, image: np.ndarray) -> np.ndarray:
    input_scale, input_zero = input_detail["quantization"]
    output_scale, output_zero = output_detail["quantization"]
    quantized = np.clip(
        np.rint(image / input_scale) + input_zero, -128, 127
    ).astype(np.int8)[None, ...]
    interpreter.set_tensor(input_detail["index"], quantized)
    interpreter.invoke()
    raw = interpreter.get_tensor(output_detail["index"])[0]
    return (raw.astype(np.float32) - output_zero) * output_scale


def _write_predictions(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    main()
