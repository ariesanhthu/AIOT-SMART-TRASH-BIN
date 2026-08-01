"""Export and verify V7 TFLite FP32 and full-INT8 models."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import random
from typing import Any, Callable, Iterator

import numpy as np
import tensorflow as tf

from V7.config import (
    ARTIFACTS_DIR,
    CLASS_NAMES,
    IMAGE_CHANNELS,
    IMAGE_SIZE,
    PREPARED_DATA_DIR,
)
from V7.data_pipeline import Sample, load_samples, preprocess_file, samples_for_split
from V7.model import validate_model_contract


ALLOWED_TFLM_OPERATORS = frozenset({"CONV_2D", "MEAN", "FULLY_CONNECTED", "SOFTMAX"})
MAX_MODEL_BYTES = 256 * 1024


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--model", type=Path, default=ARTIFACTS_DIR / "model_float.keras"
    )
    parser.add_argument("--data", type=Path, default=PREPARED_DATA_DIR)
    parser.add_argument("--out", type=Path, default=ARTIFACTS_DIR)
    parser.add_argument("--representative-per-class", type=int, default=50)
    parser.add_argument("--seed", type=int, default=7)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = export_models(
        model_path=args.model,
        data=args.data,
        output=args.out,
        representative_per_class=args.representative_per_class,
        seed=args.seed,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))


def export_models(
    *,
    model_path: str | Path = ARTIFACTS_DIR / "model_float.keras",
    data: str | Path = PREPARED_DATA_DIR,
    output: str | Path = ARTIFACTS_DIR,
    representative_per_class: int = 50,
    seed: int = 7,
) -> dict:
    if representative_per_class < 1:
        raise ValueError("representative_per_class must be positive")
    model_file = Path(model_path).expanduser().resolve()
    output_dir = Path(output).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    if not model_file.is_file():
        raise FileNotFoundError(f"Trained V7 model not found: {model_file}")
    model = tf.keras.models.load_model(model_file, compile=False)
    validate_model_contract(model)

    float_path = output_dir / "model_float.tflite"
    float_converter = tf.lite.TFLiteConverter.from_keras_model(model)
    float_path.write_bytes(float_converter.convert())
    float_inspection = inspect_tflite(float_path, require_int8=False)

    samples = load_samples(data)
    representative = _balanced_representative_samples(
        samples_for_split(samples, "train"), representative_per_class, seed
    )
    int8_converter = tf.lite.TFLiteConverter.from_keras_model(model)
    int8_converter.optimizations = [tf.lite.Optimize.DEFAULT]
    int8_converter.representative_dataset = _representative_generator(representative)
    int8_converter.target_spec.supported_ops = [tf.lite.OpsSet.TFLITE_BUILTINS_INT8]
    int8_converter.inference_input_type = tf.int8
    int8_converter.inference_output_type = tf.int8
    int8_path = output_dir / "model_int8.tflite"
    int8_path.write_bytes(int8_converter.convert())
    int8_inspection = inspect_tflite(int8_path, require_int8=True)
    int8_inspection["representative_dataset"] = {
        "split": "train",
        "source": "AI/V7 raw ESP32 captures only",
        "dataset_images": len(representative),
        "per_class": dict(Counter(sample.label for sample in representative)),
        "range_anchors": [0.0, 1.0],
        "external_images": 0,
        "seed": seed,
    }
    quantization_path = output_dir / "quantization.json"
    quantization_path.write_text(
        json.dumps(int8_inspection, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    _update_metadata(
        output_dir, float_path, int8_path, float_inspection, int8_inspection
    )
    return {"float": float_inspection, "int8": int8_inspection}


def inspect_tflite(path: str | Path, *, require_int8: bool) -> dict[str, Any]:
    model_path = Path(path)
    if model_path.stat().st_size > MAX_MODEL_BYTES:
        raise RuntimeError(
            f"V7 model exceeds ESP32 limit: {model_path.stat().st_size} > {MAX_MODEL_BYTES}"
        )
    interpreter = tf.lite.Interpreter(model_path=str(model_path))
    interpreter.allocate_tensors()
    inputs, outputs = interpreter.get_input_details(), interpreter.get_output_details()
    if len(inputs) != 1 or len(outputs) != 1:
        raise RuntimeError("V7 deployment model must have one input and one output")
    input_detail, output_detail = inputs[0], outputs[0]
    if input_detail["shape"].tolist() != [1, IMAGE_SIZE, IMAGE_SIZE, IMAGE_CHANNELS]:
        raise RuntimeError(
            f"Unexpected V7 TFLite input: {input_detail['shape'].tolist()}"
        )
    if output_detail["shape"].tolist() != [1, len(CLASS_NAMES)]:
        raise RuntimeError(
            f"Unexpected V7 TFLite output: {output_detail['shape'].tolist()}"
        )

    get_ops = getattr(interpreter, "_get_ops_details", None)
    if get_ops is None:
        raise RuntimeError("TensorFlow Lite interpreter cannot expose operators")
    operators = [item["op_name"] for item in get_ops() if item["op_name"] != "DELEGATE"]
    if require_int8:
        if input_detail["dtype"] != np.int8 or output_detail["dtype"] != np.int8:
            raise RuntimeError("V7 INT8 model tensors must both be int8")
        floating = [
            detail["name"]
            for detail in interpreter.get_tensor_details()
            if np.issubdtype(np.dtype(detail["dtype"]), np.floating)
        ]
        if floating:
            raise RuntimeError(f"V7 full-integer gate failed: {floating}")
        input_scale, input_zero_point = input_detail["quantization"]
        if not np.isclose(input_scale, 1.0 / 255.0, rtol=0.0, atol=1e-6):
            raise RuntimeError(f"Firmware input scale must be 1/255, got {input_scale}")
        if int(input_zero_point) != -128:
            raise RuntimeError(
                f"Firmware input zero point must be -128, got {input_zero_point}"
            )
        unsupported = sorted(set(operators) - ALLOWED_TFLM_OPERATORS)
        if unsupported:
            raise RuntimeError(f"V7 uses unsupported TFLM operators: {unsupported}")
    else:
        floating = []
        unsupported = []
    return {
        "file": model_path.name,
        "size_bytes": model_path.stat().st_size,
        "sha256": _sha256(model_path),
        "full_integer": require_int8,
        "input": _tensor_summary(input_detail),
        "output": _tensor_summary(output_detail),
        "operators": operators,
        "unique_operators": sorted(set(operators)),
        "unsupported_operators": unsupported,
        "float_tensors": floating,
    }


def _balanced_representative_samples(
    samples: tuple[Sample, ...], requested_per_class: int, seed: int
) -> tuple[Sample, ...]:
    rng = random.Random(seed)
    by_class = [
        [sample for sample in samples if sample.label_id == label_id]
        for label_id in range(len(CLASS_NAMES))
    ]
    per_class = min(requested_per_class, *(len(items) for items in by_class))
    selected: list[Sample] = []
    for items in by_class:
        shuffled = list(items)
        rng.shuffle(shuffled)
        selected.extend(shuffled[:per_class])
    rng.shuffle(selected)
    return tuple(selected)


def _representative_generator(
    samples: tuple[Sample, ...],
) -> Callable[[], Iterator[list[np.ndarray]]]:
    def generator() -> Iterator[list[np.ndarray]]:
        # Range anchors define the already-documented [0,1] tensor contract;
        # all real calibration images come exclusively from V7/train.
        yield [np.zeros((1, IMAGE_SIZE, IMAGE_SIZE, IMAGE_CHANNELS), np.float32)]
        yield [np.ones((1, IMAGE_SIZE, IMAGE_SIZE, IMAGE_CHANNELS), np.float32)]
        for sample in samples:
            yield [preprocess_file(sample.path)[None, ...]]

    return generator


def _tensor_summary(detail: dict[str, Any]) -> dict[str, Any]:
    scale, zero_point = detail["quantization"]
    return {
        "name": str(detail["name"]),
        "shape": [int(value) for value in detail["shape"]],
        "dtype": np.dtype(detail["dtype"]).name,
        "quantization": {"scale": float(scale), "zero_point": int(zero_point)},
    }


def _update_metadata(
    output_dir: Path,
    float_path: Path,
    int8_path: Path,
    float_inspection: dict,
    int8_inspection: dict,
) -> None:
    metadata_path = output_dir / "model_metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["artifacts"]["float_tflite"] = {
        "file": float_path.name,
        "size_bytes": float_path.stat().st_size,
        "sha256": _sha256(float_path),
    }
    metadata["artifacts"]["int8_model"] = {
        "file": int8_path.name,
        "size_bytes": int8_path.stat().st_size,
        "sha256": _sha256(int8_path),
    }
    metadata["tflite"] = {
        "float": float_inspection,
        "int8": int8_inspection,
    }
    metadata_path.write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    main()
