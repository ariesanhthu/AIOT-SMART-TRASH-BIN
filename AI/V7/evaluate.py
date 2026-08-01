"""Evaluate Keras, TFLite FP32, and TFLite INT8 on untouched V7 splits."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import tensorflow as tf

from V7.config import ARTIFACTS_DIR, CLASS_NAMES, PREPARED_DATA_DIR, V7_DIR
from V7.data_pipeline import (
    load_samples,
    make_evaluation_dataset,
    preprocess_file,
    samples_for_split,
)
from V7.metrics import classification_metrics


MODEL_NAMES = ("keras_fp32", "tflite_fp32", "tflite_int8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=PREPARED_DATA_DIR)
    parser.add_argument("--artifacts", type=Path, default=ARTIFACTS_DIR)
    parser.add_argument("--batch-size", type=int, default=16)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = evaluate_all(args.data, args.artifacts, batch_size=args.batch_size)
    print(json.dumps(result, indent=2, ensure_ascii=False))


def evaluate_all(
    data: str | Path = PREPARED_DATA_DIR,
    artifacts: str | Path = ARTIFACTS_DIR,
    *,
    batch_size: int = 16,
) -> dict:
    artifact_dir = Path(artifacts).expanduser().resolve()
    samples = load_samples(data)
    validation = samples_for_split(samples, "validation")
    test = samples_for_split(samples, "test")
    keras_model = tf.keras.models.load_model(
        artifact_dir / "model_float.keras", compile=False
    )
    predictors = {
        "keras_fp32": lambda selected: keras_model.predict(
            make_evaluation_dataset(selected, batch_size=batch_size), verbose=0
        ),
        "tflite_fp32": _tflite_predictor(artifact_dir / "model_float.tflite"),
        "tflite_int8": _tflite_predictor(artifact_dir / "model_int8.tflite"),
    }
    results: dict[str, dict] = {"validation": {}, "test": {}}
    test_probabilities: dict[str, np.ndarray] = {}
    validation_probabilities: dict[str, np.ndarray] = {}
    for split_name, split_samples, destination in (
        ("validation", validation, validation_probabilities),
        ("test", test, test_probabilities),
    ):
        truth = np.asarray(
            [sample.label_id for sample in split_samples], dtype=np.int64
        )
        for model_name, predictor in predictors.items():
            probabilities = np.asarray(predictor(split_samples), dtype=np.float32)
            destination[model_name] = probabilities
            results[split_name][model_name] = classification_metrics(
                truth, probabilities
            )

    keras_top = np.argmax(test_probabilities["keras_fp32"], axis=1)
    int8_top = np.argmax(test_probabilities["tflite_int8"], axis=1)
    results["agreement"] = {
        "keras_vs_int8_top1": float(np.mean(keras_top == int8_top)),
        "keras_vs_int8_max_probability_delta": float(
            np.max(
                np.abs(
                    test_probabilities["keras_fp32"] - test_probabilities["tflite_int8"]
                )
            )
        ),
        "int8_accuracy_drop": float(
            results["test"]["keras_fp32"]["accuracy"]
            - results["test"]["tflite_int8"]["accuracy"]
        ),
    }
    results["acceptance_thresholds"] = _derive_thresholds(
        np.asarray([sample.label_id for sample in validation], dtype=np.int64),
        validation_probabilities["tflite_int8"],
    )
    results["dataset_limit"] = (
        "Test is a chronological burst holdout from the same capture date, not a "
        "sealed independent recapture session."
    )

    metrics_path = artifact_dir / "evaluation_metrics.json"
    metrics_path.write_text(
        json.dumps(results, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    _write_predictions(artifact_dir / "test_predictions.csv", test, test_probabilities)
    _plot_confusions(artifact_dir / "confusion_matrices.png", results["test"])
    _write_golden_samples(artifact_dir, test, test_probabilities["tflite_int8"])
    _write_report(V7_DIR / "EVALUATION_REPORT.md", results, samples)
    _update_metadata(artifact_dir, results)
    return results


def _tflite_predictor(model_path: Path):
    if not model_path.is_file():
        raise FileNotFoundError(f"V7 TFLite model not found: {model_path}")

    def predict(samples) -> np.ndarray:
        interpreter = tf.lite.Interpreter(model_path=str(model_path))
        interpreter.allocate_tensors()
        input_detail = interpreter.get_input_details()[0]
        output_detail = interpreter.get_output_details()[0]
        output: list[np.ndarray] = []
        input_scale, input_zero_point = input_detail["quantization"]
        output_scale, output_zero_point = output_detail["quantization"]
        for sample in samples:
            image = preprocess_file(sample.path)[None, ...]
            if input_detail["dtype"] == np.int8:
                tensor = np.clip(
                    np.rint(image / input_scale) + input_zero_point, -128, 127
                ).astype(np.int8)
            else:
                tensor = image.astype(input_detail["dtype"])
            interpreter.set_tensor(input_detail["index"], tensor)
            interpreter.invoke()
            scores = interpreter.get_tensor(output_detail["index"])[0]
            if output_detail["dtype"] == np.int8:
                scores = (scores.astype(np.float32) - output_zero_point) * output_scale
            output.append(np.asarray(scores, dtype=np.float32))
        return np.stack(output)

    return predict


def _derive_thresholds(truth: np.ndarray, probabilities: np.ndarray) -> dict:
    predicted = np.argmax(probabilities, axis=1)
    sorted_scores = np.sort(probabilities, axis=1)
    confidence = sorted_scores[:, -1]
    margin = sorted_scores[:, -1] - sorted_scores[:, -2]
    correct = predicted == truth
    if not np.any(correct):
        return {
            "confidence": 0.75,
            "margin": 0.20,
            "basis": "fallback_no_correct_validation",
        }
    return {
        "confidence": float(max(0.50, np.quantile(confidence[correct], 0.10) - 0.02)),
        "margin": float(max(0.10, np.quantile(margin[correct], 0.10) - 0.02)),
        "basis": "10th percentile of correctly classified V7 validation samples minus 0.02",
        "warning": "Frame-quality rejection only; not an out-of-distribution detector.",
    }


def _write_predictions(
    path: Path, samples, probabilities: dict[str, np.ndarray]
) -> None:
    fields = ["relative_path", "label", "label_id"]
    for model_name in MODEL_NAMES:
        fields.extend(
            [
                f"{model_name}_prediction",
                *[f"{model_name}_{label}" for label in CLASS_NAMES],
            ]
        )
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for index, sample in enumerate(samples):
            row: dict[str, object] = {
                "relative_path": sample.relative_path,
                "label": sample.label,
                "label_id": sample.label_id,
            }
            for model_name in MODEL_NAMES:
                scores = probabilities[model_name][index]
                row[f"{model_name}_prediction"] = CLASS_NAMES[int(np.argmax(scores))]
                for class_index, label in enumerate(CLASS_NAMES):
                    row[f"{model_name}_{label}"] = f"{float(scores[class_index]):.8f}"
            writer.writerow(row)


def _plot_confusions(path: Path, metrics: dict[str, dict]) -> None:
    figure, axes = plt.subplots(1, 3, figsize=(11, 3.4), constrained_layout=True)
    for axis, model_name in zip(axes, MODEL_NAMES, strict=True):
        matrix = np.asarray(metrics[model_name]["confusion_matrix"])
        image = axis.imshow(matrix, cmap="Blues", vmin=0)
        for row in range(3):
            for column in range(3):
                axis.text(
                    column, row, str(matrix[row, column]), ha="center", va="center"
                )
        axis.set_title(model_name)
        axis.set_xticks(range(3), CLASS_NAMES, rotation=30, ha="right")
        axis.set_yticks(range(3), CLASS_NAMES)
        axis.set_xlabel("Predicted")
        axis.set_ylabel("Actual")
        figure.colorbar(image, ax=axis, fraction=0.046)
    figure.savefig(path, dpi=160)
    plt.close(figure)


def _write_golden_samples(
    artifact_dir: Path, samples, probabilities: np.ndarray
) -> None:
    golden_dir = artifact_dir / "golden_samples"
    golden_dir.mkdir(parents=True, exist_ok=True)
    interpreter = tf.lite.Interpreter(
        model_path=str(artifact_dir / "model_int8.tflite")
    )
    interpreter.allocate_tensors()
    detail = interpreter.get_input_details()[0]
    scale, zero_point = detail["quantization"]
    records = []
    for class_index, label in enumerate(CLASS_NAMES):
        selected_index = next(
            index
            for index, sample in enumerate(samples)
            if sample.label_id == class_index
        )
        sample = samples[selected_index]
        image = preprocess_file(sample.path)
        quantized = np.clip(np.rint(image / scale) + zero_point, -128, 127).astype(
            np.int8
        )
        binary_path = golden_dir / f"{label}_input_int8.bin"
        binary_path.write_bytes(quantized.tobytes())
        scores = probabilities[selected_index]
        records.append(
            {
                "label": label,
                "label_id": class_index,
                "source_relative_path": sample.relative_path,
                "input_file": binary_path.name,
                "input_sha256": hashlib.sha256(quantized.tobytes()).hexdigest(),
                "expected_top1": CLASS_NAMES[int(np.argmax(scores))],
                "expected_probabilities": {
                    name: float(scores[index]) for index, name in enumerate(CLASS_NAMES)
                },
            }
        )
    (golden_dir / "golden_samples.json").write_text(
        json.dumps(records, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def _write_report(path: Path, results: dict, samples) -> None:
    counts = {
        split: {
            label: sum(s.split == split and s.label == label for s in samples)
            for label in CLASS_NAMES
        }
        for split in ("train", "validation", "test")
    }
    lines = [
        "# V7 evaluation report",
        "",
        "V7 is a three-class closed-set model trained only from raw `AI/V7/data` ESP32-CAM captures.",
        "No TrashNet, external data, stored `__aug_v2_` image, or `other` class is used.",
        "",
        "## Contract",
        "",
        "- Labels: `0=paper`, `1=plastic`, `2=organic`.",
        "- Input: RGB 96×96.",
        "- Preprocessing: center-square crop → nearest-floor resize → RGB565 → bounded Q8 luma gain.",
        "- Split: chronological capture bursts; augmentation is online on train only.",
        f"- Counts: `{json.dumps(counts)}`.",
        "",
        "## Test results",
        "",
        "| Model | Accuracy | Macro recall | Paper recall | Plastic recall | Organic recall |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for model_name in MODEL_NAMES:
        metrics = results["test"][model_name]
        lines.append(
            f"| {model_name} | {metrics['accuracy']:.4f} | {metrics['macro_recall']:.4f} | "
            f"{metrics['per_class']['paper']['recall']:.4f} | "
            f"{metrics['per_class']['plastic']['recall']:.4f} | "
            f"{metrics['per_class']['organic']['recall']:.4f} |"
        )
    lines.extend(
        [
            "",
            "## Quantization parity",
            "",
            f"- Keras/INT8 top-1 agreement: `{results['agreement']['keras_vs_int8_top1']:.4f}`.",
            f"- INT8 accuracy drop: `{results['agreement']['int8_accuracy_drop']:.4f}`.",
            "",
            "## Limitation",
            "",
            results["dataset_limit"],
            "Capture a new ESP32 session with the same physical objects for a sealed final test before reporting deployment accuracy.",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def _update_metadata(artifact_dir: Path, results: dict) -> None:
    path = artifact_dir / "model_metadata.json"
    metadata = json.loads(path.read_text(encoding="utf-8"))
    metadata["evaluation"] = results
    path.write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
