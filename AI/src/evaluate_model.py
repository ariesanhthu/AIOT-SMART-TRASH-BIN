"""Evaluate float and INT8 models and enforce deployment parity gates."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import tensorflow as tf

try:
    from .config import (
        DEFAULT_ARTIFACT_DIR,
        DEFAULT_DATA_DIR,
        DEFAULT_FLOAT_MODEL,
        DEFAULT_INT8_MODEL,
        DEFAULT_METADATA,
        IMAGE_CHANNELS,
        IMAGE_SIZE,
        LABELS,
        MAX_INT8_ACCURACY_DROP,
        MAX_TFLITE_SIZE_BYTES,
        MIN_FLOAT_INT8_AGREEMENT,
        MIN_INT8_CLASS_RECALL,
        MIN_INT8_MACRO_F1,
        resolve_input_path,
        resolve_output_path,
    )
    from .dataset import load_dataset_index, make_dataset
    from .export_int8 import inspect_tflite_model
    from .metadata import (
        read_json,
        sha256_file,
        validate_metadata_contract,
        verify_artifact_hash,
        write_json_atomic,
        write_text_atomic,
    )
    from .metrics import classification_metrics
    from .model import validate_model_contract
except ImportError:
    from config import (  # type: ignore
        DEFAULT_ARTIFACT_DIR,
        DEFAULT_DATA_DIR,
        DEFAULT_FLOAT_MODEL,
        DEFAULT_INT8_MODEL,
        DEFAULT_METADATA,
        IMAGE_CHANNELS,
        IMAGE_SIZE,
        LABELS,
        MAX_INT8_ACCURACY_DROP,
        MAX_TFLITE_SIZE_BYTES,
        MIN_FLOAT_INT8_AGREEMENT,
        MIN_INT8_CLASS_RECALL,
        MIN_INT8_MACRO_F1,
        resolve_input_path,
        resolve_output_path,
    )
    from dataset import load_dataset_index, make_dataset  # type: ignore
    from export_int8 import inspect_tflite_model  # type: ignore
    from metadata import (  # type: ignore
        read_json,
        sha256_file,
        validate_metadata_contract,
        verify_artifact_hash,
        write_json_atomic,
        write_text_atomic,
    )
    from metrics import classification_metrics  # type: ignore
    from model import validate_model_contract  # type: ignore


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--float-model", default=str(DEFAULT_FLOAT_MODEL))
    parser.add_argument("--int8-model", default=str(DEFAULT_INT8_MODEL))
    parser.add_argument("--metadata", default=str(DEFAULT_METADATA))
    parser.add_argument("--data", default=str(DEFAULT_DATA_DIR))
    parser.add_argument("--out", default=str(DEFAULT_ARTIFACT_DIR))
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument(
        "--max-accuracy-drop", type=float, default=MAX_INT8_ACCURACY_DROP
    )
    parser.add_argument(
        "--min-agreement", type=float, default=MIN_FLOAT_INT8_AGREEMENT
    )
    parser.add_argument("--max-model-bytes", type=int, default=MAX_TFLITE_SIZE_BYTES)
    parser.add_argument("--min-macro-f1", type=float, default=MIN_INT8_MACRO_F1)
    parser.add_argument(
        "--min-class-recall", type=float, default=MIN_INT8_CLASS_RECALL
    )
    parser.add_argument("--seed", type=int, default=42)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.batch_size < 1 or args.max_accuracy_drop < 0:
        raise ValueError("batch-size must be positive and max-accuracy-drop non-negative")
    for argument_name in ("min_agreement", "min_macro_f1", "min_class_recall"):
        value = getattr(args, argument_name)
        if not 0.0 <= value <= 1.0:
            raise ValueError(f"{argument_name.replace('_', '-')} must be between 0 and 1")

    float_path = resolve_input_path(args.float_model)
    int8_path = resolve_input_path(args.int8_model)
    metadata_path = resolve_input_path(args.metadata)
    data_path = resolve_input_path(args.data)
    out_dir = resolve_output_path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    metadata = read_json(metadata_path)
    validate_metadata_contract(metadata)
    verify_artifact_hash(metadata, "float_model", float_path)
    verify_artifact_hash(metadata, "int8_model", int8_path)
    tflite_inspection = inspect_tflite_model(
        int8_path, max_model_bytes=args.max_model_bytes
    )
    _validate_quantization_metadata(metadata, tflite_inspection)

    index = load_dataset_index(data_path)
    expected_dataset_hash = metadata.get("dataset", {}).get("dataset_sha256")
    if expected_dataset_hash != index.dataset_sha256:
        raise ValueError(
            "Evaluation dataset differs from training metadata: "
            f"metadata={expected_dataset_hash}, current={index.dataset_sha256}"
        )
    test_samples = index.for_split("test")
    test_dataset = make_dataset(
        test_samples,
        batch_size=args.batch_size,
        training=False,
        seed=args.seed,
    )
    truth = np.asarray([sample.label_id for sample in test_samples], dtype=np.int64)

    float_predictor = KerasPredictor(float_path)
    int8_predictor = TFLitePredictor(int8_path)
    float_logits = float_predictor.predict_dataset(test_dataset)
    int8_logits = int8_predictor.predict_dataset(test_dataset)
    float_metrics = classification_metrics(truth, float_logits)
    int8_metrics = classification_metrics(truth, int8_logits)

    float_predictions = np.argmax(float_logits, axis=1)
    int8_predictions = np.argmax(int8_logits, axis=1)
    accuracy_drop = float(float_metrics["accuracy"] - int8_metrics["accuracy"])
    agreement = float(np.mean(float_predictions == int8_predictions))
    int8_min_class_recall = min(
        float(int8_metrics["per_class"][label]["recall"]) for label in LABELS
    )
    comparison = {
        "samples": len(test_samples),
        "float_int8_class_agreement": agreement,
        "accuracy_drop": accuracy_drop,
        "max_accuracy_drop": args.max_accuracy_drop,
        "min_agreement": args.min_agreement,
        "min_macro_f1": args.min_macro_f1,
        "min_class_recall": args.min_class_recall,
        "int8_macro_f1": float(int8_metrics["macro_f1"]),
        "int8_min_class_recall": int8_min_class_recall,
        "gates": {
            "accuracy_drop_passed": accuracy_drop <= args.max_accuracy_drop,
            "agreement_passed": agreement >= args.min_agreement,
            "model_size_passed": int8_path.stat().st_size <= args.max_model_bytes,
            "macro_f1_passed": int8_metrics["macro_f1"] >= args.min_macro_f1,
            "class_recall_passed": int8_min_class_recall >= args.min_class_recall,
        },
    }
    comparison["passed"] = all(comparison["gates"].values())

    float_payload = {
        "model": str(float_path),
        "sha256": sha256_file(float_path),
        "dataset_sha256": index.dataset_sha256,
        "split": "test",
        "metrics": float_metrics,
    }
    int8_payload = {
        "model": str(int8_path),
        "sha256": sha256_file(int8_path),
        "dataset_sha256": index.dataset_sha256,
        "split": "test",
        "inspection": tflite_inspection,
        "metrics": int8_metrics,
    }
    write_json_atomic(out_dir / "metrics_float.json", float_payload)
    write_json_atomic(out_dir / "metrics_int8.json", int8_payload)
    write_json_atomic(out_dir / "comparison.json", comparison)
    _write_confusion_csv(
        out_dir / "confusion_matrix_int8.csv",
        int8_metrics["confusion_matrix"],
    )

    print(json.dumps({"float": float_payload, "int8": int8_payload, "comparison": comparison}, indent=2, ensure_ascii=False))
    if not comparison["passed"]:
        failed = [name for name, passed in comparison["gates"].items() if not passed]
        raise RuntimeError(f"INT8 deployment gates failed: {failed}")


class KerasPredictor:
    def __init__(self, model_path: str | Path) -> None:
        self.model = tf.keras.models.load_model(model_path, compile=False)
        validate_model_contract(self.model)

    def predict_dataset(self, dataset: tf.data.Dataset) -> np.ndarray:
        images = dataset.map(
            lambda image, _label: image,
            num_parallel_calls=tf.data.AUTOTUNE,
            deterministic=True,
        )
        return np.asarray(self.model.predict(images, verbose=0), dtype=np.float32)

    def predict_one(self, image: np.ndarray) -> np.ndarray:
        batch = np.asarray(image, dtype=np.float32)[np.newaxis, ...]
        return np.asarray(self.model.predict(batch, verbose=0), dtype=np.float32)[0]


class TFLitePredictor:
    def __init__(self, model_path: str | Path) -> None:
        self.interpreter = tf.lite.Interpreter(model_path=str(model_path))
        self.interpreter.allocate_tensors()
        inputs = self.interpreter.get_input_details()
        outputs = self.interpreter.get_output_details()
        if len(inputs) != 1 or len(outputs) != 1:
            raise ValueError("TFLite model must have one input and one output")
        self.input_detail = inputs[0]
        self.output_detail = outputs[0]
        expected_input = [1, IMAGE_SIZE, IMAGE_SIZE, IMAGE_CHANNELS]
        expected_output = [1, len(LABELS)]
        if self.input_detail["shape"].tolist() != expected_input:
            raise ValueError("TFLite input shape does not match the preprocessing contract")
        if self.output_detail["shape"].tolist() != expected_output:
            raise ValueError("TFLite output is not a three-logit tensor")
        if self.input_detail["dtype"] != np.int8 or self.output_detail["dtype"] != np.int8:
            raise ValueError("TFLite predictor requires int8 input and output")

    def predict_dataset(self, dataset: tf.data.Dataset) -> np.ndarray:
        rows: list[np.ndarray] = []
        for images, _labels in dataset:
            for image in images.numpy():
                rows.append(self.predict_one(image))
        if not rows:
            raise ValueError("Cannot predict an empty dataset")
        return np.vstack(rows).astype(np.float32, copy=False)

    def predict_one(self, image: np.ndarray) -> np.ndarray:
        quantized = self._quantize(image)
        self.interpreter.set_tensor(
            self.input_detail["index"], quantized[np.newaxis, ...]
        )
        self.interpreter.invoke()
        output = self.interpreter.get_tensor(self.output_detail["index"])[0]
        scale, zero_point = self.output_detail["quantization"]
        if scale <= 0:
            raise ValueError("TFLite output has invalid quantization scale")
        return (output.astype(np.float32) - zero_point) * scale

    def _quantize(self, image: np.ndarray) -> np.ndarray:
        scale, zero_point = self.input_detail["quantization"]
        if scale <= 0:
            raise ValueError("TFLite input has invalid quantization scale")
        values = np.rint(np.asarray(image, dtype=np.float32) / scale + zero_point)
        return np.clip(values, -128, 127).astype(np.int8)


def load_predictor(model_path: str | Path):
    path = Path(model_path)
    return TFLitePredictor(path) if path.suffix.lower() == ".tflite" else KerasPredictor(path)


def _validate_quantization_metadata(
    metadata: dict, inspection: dict
) -> None:
    for tensor_name in ("input", "output"):
        stored = metadata.get(tensor_name, {}).get("quantization")
        actual = inspection[tensor_name]["quantization"]
        if not stored:
            raise ValueError(f"Metadata is missing {tensor_name} quantization")
        if int(stored.get("zero_point")) != int(actual["zero_point"]):
            raise ValueError(f"Metadata {tensor_name} zero_point does not match model")
        if not np.isclose(
            float(stored.get("scale")),
            float(actual["scale"]),
            rtol=1e-7,
            atol=1e-9,
        ):
            raise ValueError(f"Metadata {tensor_name} scale does not match model")
    if metadata.get("tflite", {}).get("operators") != inspection["operators"]:
        raise ValueError("Metadata operator list does not match the INT8 model")


def _write_confusion_csv(path: Path, matrix: list[list[int]]) -> None:
    rows = [["actual/predicted", *LABELS]]
    rows.extend([[label, *matrix[index]] for index, label in enumerate(LABELS)])
    content = "\n".join(
        ",".join(str(value) for value in row) for row in rows
    ) + "\n"
    write_text_atomic(path, content)


if __name__ == "__main__":
    main()
