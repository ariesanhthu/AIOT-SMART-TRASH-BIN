"""Quantize V9 to a full-INT8, ESP32-compatible TFLite model."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path

os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")

import numpy as np
import tensorflow as tf

from V9.config import ARTIFACTS_DIR, CLASS_NAMES, DATASET_DIR, IMAGE_CHANNELS, IMAGE_SIZE
from V9.data_pipeline import load_samples, preprocess_file_tensor, samples_for_split
from V9.metrics import classification_metrics


ALLOWED_TFLM_OPERATORS = {"CONV_2D", "MEAN", "FULLY_CONNECTED", "SOFTMAX"}
MAX_MODEL_BYTES = 256 * 1024


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=DATASET_DIR)
    parser.add_argument("--artifacts", type=Path, default=ARTIFACTS_DIR)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    artifacts = args.artifacts.expanduser().resolve()
    model_path = artifacts / "model_float.keras"
    if not model_path.is_file():
        raise FileNotFoundError(f"V9 float model not found: {model_path}")
    model = tf.keras.models.load_model(model_path, compile=False)
    samples = load_samples(args.data)
    train_samples = samples_for_split(samples, "train")

    def representative_dataset():
        # Force the exact [0,1] deployment range, then calibrate on deterministic
        # preprocessing only. Stochastic augmentation is never used here.
        yield [np.zeros((1, IMAGE_SIZE, IMAGE_SIZE, IMAGE_CHANNELS), np.float32)]
        yield [np.ones((1, IMAGE_SIZE, IMAGE_SIZE, IMAGE_CHANNELS), np.float32)]
        for sample in train_samples:
            image = preprocess_file_tensor(tf.constant(str(sample.path))).numpy()
            yield [image[None, ...].astype(np.float32)]

    converter = tf.lite.TFLiteConverter.from_keras_model(model)
    converter.optimizations = [tf.lite.Optimize.DEFAULT]
    converter.representative_dataset = representative_dataset
    converter.target_spec.supported_ops = [tf.lite.OpsSet.TFLITE_BUILTINS_INT8]
    converter.inference_input_type = tf.int8
    converter.inference_output_type = tf.int8
    data = converter.convert()
    output_path = artifacts / "model_int8.tflite"
    output_path.write_bytes(data)
    inspection = inspect_and_evaluate(output_path, samples)
    inspection["representative_dataset"] = {
        "split": "train",
        "images": len(train_samples),
        "per_class": dict(Counter(sample.label for sample in train_samples)),
        "range_anchors": [0.0, 1.0],
        "stochastic_augmentation": False,
    }
    (artifacts / "quantization.json").write_text(
        json.dumps(inspection, indent=2) + "\n", encoding="utf-8"
    )

    metadata_path = artifacts / "model_metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["int8_model"] = {
        "file": output_path.name,
        "bytes": len(data),
        "sha256": inspection["sha256"],
    }
    metadata["tflite"] = inspection
    metadata_path.write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(inspection, indent=2))


def inspect_and_evaluate(path: Path, samples) -> dict:
    if path.stat().st_size > MAX_MODEL_BYTES:
        raise RuntimeError(f"INT8 model is too large for ESP32: {path.stat().st_size}")
    interpreter = tf.lite.Interpreter(model_path=str(path))
    interpreter.allocate_tensors()
    input_detail = interpreter.get_input_details()[0]
    output_detail = interpreter.get_output_details()[0]
    if input_detail["shape"].tolist() != [1, IMAGE_SIZE, IMAGE_SIZE, IMAGE_CHANNELS]:
        raise RuntimeError(f"Unexpected input shape: {input_detail['shape']}")
    if output_detail["shape"].tolist() != [1, len(CLASS_NAMES)]:
        raise RuntimeError(f"Unexpected output shape: {output_detail['shape']}")
    if input_detail["dtype"] != np.int8 or output_detail["dtype"] != np.int8:
        raise RuntimeError("Deployment input/output must both be INT8")
    floating = [
        detail["name"] for detail in interpreter.get_tensor_details()
        if np.issubdtype(np.dtype(detail["dtype"]), np.floating)
    ]
    if floating:
        raise RuntimeError(f"Full-INT8 conversion left float tensors: {floating}")
    operators = [
        detail["op_name"] for detail in interpreter._get_ops_details()
        if detail["op_name"] != "DELEGATE"
    ]
    unsupported = sorted(set(operators) - ALLOWED_TFLM_OPERATORS)
    if unsupported:
        raise RuntimeError(f"Unsupported TFLM operators: {unsupported}")

    input_scale, input_zero = input_detail["quantization"]
    output_scale, output_zero = output_detail["quantization"]
    if not np.isclose(input_scale, 1.0 / 255.0, atol=1e-6, rtol=0.0):
        raise RuntimeError(f"Input scale is not 1/255: {input_scale}")
    if int(input_zero) != -128:
        raise RuntimeError(f"Input zero point is not -128: {input_zero}")

    metrics = {}
    for split in ("validation", "test"):
        selected = samples_for_split(samples, split)
        truth, probabilities = _run_int8(
            interpreter, input_detail, output_detail, selected
        )
        metrics[split] = classification_metrics(truth, probabilities)

    flat = (
        np.arange(IMAGE_SIZE * IMAGE_SIZE * IMAGE_CHANNELS, dtype=np.uint32) * 191 + 7
    ) & 255
    self_test_input = (flat.astype(np.int16) - 128).astype(np.int8).reshape(
        1, IMAGE_SIZE, IMAGE_SIZE, IMAGE_CHANNELS
    )
    interpreter.set_tensor(input_detail["index"], self_test_input)
    interpreter.invoke()
    self_test_raw = interpreter.get_tensor(output_detail["index"])[0].astype(int)
    order = np.argsort(self_test_raw)
    return {
        "file": path.name,
        "size_bytes": path.stat().st_size,
        "sha256": _sha256(path),
        "full_integer": True,
        "input": _tensor_summary(input_detail),
        "output": _tensor_summary(output_detail),
        "operators": operators,
        "unique_operators": sorted(set(operators)),
        "float_tensors": floating,
        "metrics": metrics,
        "self_test": {
            "multiplier": 191,
            "offset": 7,
            "raw_output": self_test_raw.tolist(),
            "expected_class_index": int(order[-1]),
            "minimum_raw_margin": int(self_test_raw[order[-1]] - self_test_raw[order[-2]]),
        },
    }


def _run_int8(interpreter, input_detail, output_detail, samples):
    input_scale, input_zero = input_detail["quantization"]
    output_scale, output_zero = output_detail["quantization"]
    truth, probabilities = [], []
    for sample in samples:
        image = preprocess_file_tensor(tf.constant(str(sample.path))).numpy()
        quantized = np.clip(
            np.rint(image / input_scale) + input_zero, -128, 127
        ).astype(np.int8)[None, ...]
        interpreter.set_tensor(input_detail["index"], quantized)
        interpreter.invoke()
        raw = interpreter.get_tensor(output_detail["index"])[0]
        probabilities.append((raw.astype(np.float32) - output_zero) * output_scale)
        truth.append(sample.label_id)
    return np.asarray(truth), np.asarray(probabilities)


def _tensor_summary(detail: dict) -> dict:
    scale, zero_point = detail["quantization"]
    return {
        "name": str(detail["name"]),
        "shape": [int(value) for value in detail["shape"]],
        "dtype": np.dtype(detail["dtype"]).name,
        "quantization": {"scale": float(scale), "zero_point": int(zero_point)},
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    main()
