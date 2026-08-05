"""Export the trained V8 Keras model as an ESP32-compatible full-INT8 model."""

from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path

import numpy as np
import tensorflow as tf

from V8.config import ARTIFACTS_DIR, CLASS_NAMES, DATASET_DIR, IMAGE_CHANNELS, IMAGE_SIZE
from V8.data_pipeline import load_samples, preprocess_file_tensor, samples_for_split
from V8.metrics import classification_metrics


ALLOWED_TFLM_OPERATORS = {"CONV_2D", "MEAN", "FULLY_CONNECTED", "SOFTMAX"}
MAX_MODEL_BYTES = 256 * 1024


def main() -> None:
    model_path = ARTIFACTS_DIR / "model_float.keras"
    if not model_path.is_file():
        raise FileNotFoundError(f"V8 trained model not found: {model_path}")
    model = tf.keras.models.load_model(model_path, compile=False)
    samples = load_samples(DATASET_DIR)
    train_samples = samples_for_split(samples, "train")

    def representative_dataset():
        # Preserve the exact firmware input range even when the small capture
        # set does not contain both extrema.
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
    output_path = ARTIFACTS_DIR / "model_int8.tflite"
    output_path.write_bytes(data)
    inspection = inspect_and_evaluate(output_path, samples)
    inspection["representative_dataset"] = {
        "split": "train",
        "images": len(train_samples),
        "per_class": dict(Counter(sample.label for sample in train_samples)),
        "range_anchors": [0.0, 1.0],
    }
    (ARTIFACTS_DIR / "quantization.json").write_text(
        json.dumps(inspection, indent=2) + "\n", encoding="utf-8"
    )

    metadata_path = ARTIFACTS_DIR / "model_metadata.json"
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
        raise RuntimeError("V8 deployment input/output must both be INT8")
    floating = [
        item["name"] for item in interpreter.get_tensor_details()
        if np.issubdtype(np.dtype(item["dtype"]), np.floating)
    ]
    if floating:
        raise RuntimeError(f"Full-INT8 conversion left float tensors: {floating}")
    operators = [
        item["op_name"] for item in interpreter._get_ops_details()
        if item["op_name"] != "DELEGATE"
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
        probabilities = []
        truth = []
        for sample in selected:
            image = preprocess_file_tensor(tf.constant(str(sample.path))).numpy()
            quantized = np.clip(
                np.rint(image / input_scale) + input_zero, -128, 127
            ).astype(np.int8)[None, ...]
            interpreter.set_tensor(input_detail["index"], quantized)
            interpreter.invoke()
            raw = interpreter.get_tensor(output_detail["index"])[0]
            probabilities.append((raw.astype(np.float32) - output_zero) * output_scale)
            truth.append(sample.label_id)
        metrics[split] = classification_metrics(np.asarray(truth), np.asarray(probabilities))

    # Same deterministic bytes used by the firmware startup self-test.
    flat = (np.arange(IMAGE_SIZE * IMAGE_SIZE * IMAGE_CHANNELS, dtype=np.uint32) * 191 + 7) & 255
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
