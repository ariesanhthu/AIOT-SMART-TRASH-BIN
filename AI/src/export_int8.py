"""Export TinyCNN v2 as a verified full-integer TFLite model."""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
from typing import Any

import numpy as np
import tensorflow as tf

try:
    from .config import (
        DEFAULT_DATA_DIR,
        DEFAULT_FLOAT_MODEL,
        DEFAULT_INT8_MODEL,
        DEFAULT_METADATA,
        IMAGE_CHANNELS,
        IMAGE_SIZE,
        LABELS,
        MAX_TFLITE_SIZE_BYTES,
        resolve_input_path,
        resolve_output_path,
    )
    from .dataset import (
        load_dataset_index,
        preprocess_file,
        stratified_representative_samples,
    )
    from .metadata import (
        read_json,
        sha256_file,
        utc_now_iso,
        validate_metadata_contract,
        verify_artifact_hash,
        write_bytes_atomic,
        write_json_atomic,
    )
    from .model import validate_model_contract
except ImportError:
    from config import (  # type: ignore
        DEFAULT_DATA_DIR,
        DEFAULT_FLOAT_MODEL,
        DEFAULT_INT8_MODEL,
        DEFAULT_METADATA,
        IMAGE_CHANNELS,
        IMAGE_SIZE,
        LABELS,
        MAX_TFLITE_SIZE_BYTES,
        resolve_input_path,
        resolve_output_path,
    )
    from dataset import (  # type: ignore
        load_dataset_index,
        preprocess_file,
        stratified_representative_samples,
    )
    from metadata import (  # type: ignore
        read_json,
        sha256_file,
        utc_now_iso,
        validate_metadata_contract,
        verify_artifact_hash,
        write_bytes_atomic,
        write_json_atomic,
    )
    from model import validate_model_contract  # type: ignore


ALLOWED_TFLITE_MICRO_OPS = frozenset(
    {
        "ADD",
        "CONV_2D",
        "DEPTHWISE_CONV_2D",
        "FULLY_CONNECTED",
        "MEAN",
        "RESHAPE",
    }
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default=str(DEFAULT_FLOAT_MODEL))
    parser.add_argument("--data", default=str(DEFAULT_DATA_DIR))
    parser.add_argument("--metadata", default=str(DEFAULT_METADATA))
    parser.add_argument("--out", default=str(DEFAULT_INT8_MODEL))
    parser.add_argument("--quantization-out", default=None)
    parser.add_argument("--representative-per-class", type=int, default=100)
    parser.add_argument("--max-model-bytes", type=int, default=MAX_TFLITE_SIZE_BYTES)
    parser.add_argument("--seed", type=int, default=42)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.representative_per_class < 1 or args.max_model_bytes < 1:
        raise ValueError("representative-per-class and max-model-bytes must be positive")

    model_path = resolve_input_path(args.model)
    data_path = resolve_input_path(args.data)
    metadata_path = resolve_input_path(args.metadata)
    out_path = resolve_output_path(args.out)
    quantization_path = (
        resolve_output_path(args.quantization_out)
        if args.quantization_out
        else out_path.parent / "quantization.json"
    )

    metadata = read_json(metadata_path)
    validate_metadata_contract(metadata)
    verify_artifact_hash(metadata, "float_model", model_path)

    index = load_dataset_index(data_path)
    expected_dataset_hash = metadata.get("dataset", {}).get("dataset_sha256")
    if expected_dataset_hash != index.dataset_sha256:
        raise ValueError(
            "Training and representative datasets differ: "
            f"metadata={expected_dataset_hash}, current={index.dataset_sha256}"
        )

    model = tf.keras.models.load_model(model_path, compile=False)
    validate_model_contract(model)
    representative = stratified_representative_samples(
        index,
        per_class=args.representative_per_class,
        seed=args.seed,
    )

    converter = tf.lite.TFLiteConverter.from_keras_model(model)
    converter.optimizations = [tf.lite.Optimize.DEFAULT]
    converter.representative_dataset = _representative_generator(representative)
    converter.target_spec.supported_ops = [tf.lite.OpsSet.TFLITE_BUILTINS_INT8]
    converter.inference_input_type = tf.int8
    converter.inference_output_type = tf.int8
    tflite_bytes = converter.convert()
    write_bytes_atomic(out_path, tflite_bytes)

    inspection = inspect_tflite_model(out_path, max_model_bytes=args.max_model_bytes)
    inspection["representative_samples"] = {
        "dataset_images": len(representative),
        "converter_samples": len(representative) + 2,
        "per_class": dict(Counter(sample.label for sample in representative)),
        "range_anchors": [0.0, 1.0],
        "split": "train",
        "dataset_sha256": index.dataset_sha256,
        "seed": args.seed,
    }
    write_json_atomic(quantization_path, inspection)

    metadata["exported_utc"] = utc_now_iso()
    metadata["input"]["tflite_dtype"] = inspection["input"]["dtype"]
    metadata["input"]["tflite_name"] = inspection["input"]["name"]
    metadata["input"]["quantization"] = inspection["input"]["quantization"]
    metadata["output"]["tflite_dtype"] = inspection["output"]["dtype"]
    metadata["output"]["tflite_name"] = inspection["output"]["name"]
    metadata["output"]["quantization"] = inspection["output"]["quantization"]
    metadata["tflite"] = {
        "operators": inspection["operators"],
        "full_integer": inspection["full_integer"],
        "max_model_bytes": args.max_model_bytes,
    }
    metadata["artifacts"]["int8_model"] = {
        "file": out_path.name,
        "size_bytes": out_path.stat().st_size,
        "sha256": sha256_file(out_path),
    }
    write_json_atomic(metadata_path, metadata)

    print(json.dumps(inspection, indent=2, ensure_ascii=False))
    print(f"Saved verified INT8 model: {out_path}")


def _representative_generator(samples):
    def generator():
        # Anchor the known [0, 1] preprocessing range. This makes the input
        # contract exactly scale=1/255 and zero_point=-128 for the ESP32 LUT.
        yield [np.zeros((1, IMAGE_SIZE, IMAGE_SIZE, IMAGE_CHANNELS), dtype=np.float32)]
        yield [np.ones((1, IMAGE_SIZE, IMAGE_SIZE, IMAGE_CHANNELS), dtype=np.float32)]
        for sample in samples:
            image = preprocess_file(sample.path)
            yield [image[np.newaxis, ...].astype(np.float32, copy=False)]

    return generator


def inspect_tflite_model(
    model_path: str | Path,
    *,
    max_model_bytes: int = MAX_TFLITE_SIZE_BYTES,
) -> dict[str, Any]:
    path = Path(model_path)
    size_bytes = path.stat().st_size
    if size_bytes > max_model_bytes:
        raise ValueError(
            f"TFLite model is {size_bytes} bytes; limit is {max_model_bytes} bytes"
        )

    interpreter = tf.lite.Interpreter(model_path=str(path))
    interpreter.allocate_tensors()
    inputs = interpreter.get_input_details()
    outputs = interpreter.get_output_details()
    if len(inputs) != 1 or len(outputs) != 1:
        raise ValueError(
            f"Deployment model must have one input and one output; got {len(inputs)}/{len(outputs)}"
        )
    input_detail, output_detail = inputs[0], outputs[0]
    expected_input = [1, IMAGE_SIZE, IMAGE_SIZE, IMAGE_CHANNELS]
    expected_output = [1, len(LABELS)]
    if input_detail["shape"].tolist() != expected_input:
        raise ValueError(f"Unexpected TFLite input shape: {input_detail['shape'].tolist()}")
    if output_detail["shape"].tolist() != expected_output:
        raise ValueError(f"Unexpected TFLite output shape: {output_detail['shape'].tolist()}")
    if input_detail["dtype"] != np.int8 or output_detail["dtype"] != np.int8:
        raise ValueError("TFLite input and output must both be int8")
    input_scale, input_zero_point = input_detail["quantization"]
    if not np.isclose(input_scale, 1.0 / 255.0, rtol=0.0, atol=1e-6):
        raise ValueError(
            f"Input quantization scale must be 1/255 for firmware, got {input_scale}"
        )
    if int(input_zero_point) != -128:
        raise ValueError(
            f"Input zero_point must be -128 for firmware, got {input_zero_point}"
        )

    float_tensors = [
        detail["name"]
        for detail in interpreter.get_tensor_details()
        if np.issubdtype(np.dtype(detail["dtype"]), np.floating)
    ]
    if float_tensors:
        raise ValueError(f"Full-integer gate failed; float tensors: {float_tensors}")

    get_ops = getattr(interpreter, "_get_ops_details", None)
    if get_ops is None:
        raise RuntimeError("TensorFlow Lite interpreter cannot expose operator details")
    operators = [
        detail["op_name"] for detail in get_ops() if detail["op_name"] != "DELEGATE"
    ]
    unsupported = sorted(set(operators) - ALLOWED_TFLITE_MICRO_OPS)
    if unsupported:
        raise ValueError(f"Unsupported TFLite Micro operators: {unsupported}")

    return {
        "model_size_bytes": size_bytes,
        "sha256": sha256_file(path),
        "full_integer": True,
        "input": _tensor_summary(input_detail),
        "output": _tensor_summary(output_detail),
        "operators": operators,
        "unique_operators": sorted(set(operators)),
        "unsupported_operators": unsupported,
        "float_tensors": float_tensors,
    }


def _tensor_summary(detail: dict[str, Any]) -> dict[str, Any]:
    scale, zero_point = detail["quantization"]
    return {
        "name": detail["name"],
        "shape": [int(value) for value in detail["shape"]],
        "dtype": np.dtype(detail["dtype"]).name,
        "quantization": {
            "scale": float(scale),
            "zero_point": int(zero_point),
        },
    }


if __name__ == "__main__":
    main()
