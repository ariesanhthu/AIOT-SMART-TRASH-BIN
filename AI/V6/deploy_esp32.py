"""Verify V6 quality, embed its INT8 bytes, and update the ESP32 contract."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re

from V6.runtime import LABELS, MODEL_VERSION, configure_shared_contract

configure_shared_contract()

import numpy as np  # noqa: E402
import tensorflow as tf  # noqa: E402

from src.export_int8 import inspect_tflite_model  # noqa: E402
from src.metadata import (  # noqa: E402
    read_json,
    sha256_file,
    validate_metadata_contract,
    verify_artifact_hash,
    write_text_atomic,
)


V6_DIR = Path(__file__).resolve().parent
REPOSITORY_DIR = V6_DIR.parents[1]
DEFAULT_ARTIFACTS = V6_DIR / "artifacts"
DEFAULT_ESP32 = REPOSITORY_DIR / "ESP-TRASH"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifacts", type=Path, default=DEFAULT_ARTIFACTS)
    parser.add_argument("--esp32", type=Path, default=DEFAULT_ESP32)
    parser.add_argument("--allow-failed-quality", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    artifacts = args.artifacts.expanduser().resolve()
    esp32 = args.esp32.expanduser().resolve()
    _validate_destination(esp32)
    metadata_path = artifacts / "model_metadata.json"
    model_path = artifacts / "model_int8.tflite"
    metadata = read_json(metadata_path)
    validate_metadata_contract(metadata)
    verify_artifact_hash(metadata, "int8_model", model_path)
    _verify_quality(artifacts, allow_failed=args.allow_failed_quality)

    inspection = inspect_tflite_model(model_path)
    model_bytes = model_path.read_bytes()
    model_hash = sha256_file(model_path)
    self_test = _find_self_test(model_path)

    destinations = (esp32, V6_DIR / "esp32_model")
    for destination in destinations:
        destination.mkdir(parents=True, exist_ok=True)
        _write_model_array(destination, model_bytes, model_hash)
    _update_contract(
        esp32 / "model_contract.h",
        inspection=inspection,
        model_bytes=len(model_bytes),
        model_hash=model_hash,
        self_test=self_test,
    )

    payload = {
        "model_version": MODEL_VERSION,
        "model": str(model_path),
        "model_bytes": len(model_bytes),
        "sha256": model_hash,
        "input": inspection["input"],
        "output": inspection["output"],
        "operators": inspection["operators"],
        "self_test": self_test,
        "destinations": [str(path) for path in destinations],
    }
    (artifacts / "esp32_deployment.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(payload, indent=2, ensure_ascii=False))


def _verify_quality(artifacts: Path, *, allow_failed: bool) -> None:
    required = (artifacts / "comparison.json", artifacts / "environmental_robustness.json")
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"Quality reports are missing: {missing}")
    failed = [
        path.name
        for path in required
        if not bool(read_json(path).get("passed"))
    ]
    if failed and not allow_failed:
        raise RuntimeError(
            "Refusing ESP32 deployment because quality gates failed: " + ", ".join(failed)
        )


def _find_self_test(model_path: Path) -> dict[str, int | str | list[int]]:
    interpreter = tf.lite.Interpreter(model_path=str(model_path))
    interpreter.allocate_tensors()
    input_detail = interpreter.get_input_details()[0]
    output_detail = interpreter.get_output_details()[0]
    shape = tuple(int(value) for value in input_detail["shape"])
    element_count = int(np.prod(shape))
    indices = np.arange(element_count, dtype=np.uint32)
    best: tuple[int, int, int, np.ndarray] | None = None
    multipliers = (17, 31, 47, 73, 97, 127, 159, 191, 223, 251)
    offsets = (7, 19, 37, 59, 91, 127, 173, 211)
    for multiplier in multipliers:
        for offset in offsets:
            pixels = ((indices * multiplier + offset) & 0xFF).astype(np.int16)
            tensor = (pixels - 128).astype(np.int8).reshape(shape)
            interpreter.set_tensor(input_detail["index"], tensor)
            interpreter.invoke()
            raw = interpreter.get_tensor(output_detail["index"])[0].astype(np.int16)
            order = np.argsort(raw)
            margin = int(raw[order[-1]] - raw[order[-2]])
            if best is None or margin > best[0]:
                best = (margin, multiplier, offset, raw.copy())
    if best is None:
        raise RuntimeError("Could not generate an ESP32 model self-test")
    margin, multiplier, offset, raw = best
    expected_index = int(np.argmax(raw))
    if margin < 16:
        raise RuntimeError(f"No stable model self-test pattern; best raw margin={margin}")
    return {
        "multiplier": multiplier,
        "offset": offset,
        "expected_class": LABELS[expected_index],
        "expected_class_index": expected_index,
        "reference_raw_output": [int(value) for value in raw],
        "reference_raw_margin": margin,
        "minimum_raw_margin": max(12, min(64, margin // 2)),
    }


def _write_model_array(destination: Path, model: bytes, model_hash: str) -> None:
    header = "\n".join(
        [
            "#ifndef AIOT_MODEL_DATA_H_",
            "#define AIOT_MODEL_DATA_H_",
            "",
            "#include <cstddef>",
            "#include <cstdint>",
            "",
            "extern const unsigned char g_model[];",
            "extern const int g_model_len;",
            "extern const char g_model_sha256[65];",
            "",
            "#endif  // AIOT_MODEL_DATA_H_",
            "",
        ]
    )
    rows = [
        "  " + ", ".join(f"0x{value:02x}" for value in model[start : start + 12]) + ","
        for start in range(0, len(model), 12)
    ]
    source = "\n".join(
        [
            '#include "model_data.h"',
            "",
            "#if defined(ARDUINO_ARCH_ESP32)",
            "#include <pgmspace.h>",
            "#define AIOT_MODEL_STORAGE PROGMEM",
            "#else",
            "#define AIOT_MODEL_STORAGE",
            "#endif",
            "",
            "alignas(16) const unsigned char g_model[] AIOT_MODEL_STORAGE = {",
            *rows,
            "};",
            f"const int g_model_len = {len(model)};",
            f'const char g_model_sha256[65] = "{model_hash}";',
            "",
            "#undef AIOT_MODEL_STORAGE",
            "",
        ]
    )
    write_text_atomic(destination / "model_data.h", header)
    write_text_atomic(destination / "model_data.cpp", source)


def _update_contract(
    path: Path,
    *,
    inspection: dict,
    model_bytes: int,
    model_hash: str,
    self_test: dict,
) -> None:
    content = path.read_text(encoding="utf-8")
    output_quantization = inspection["output"]["quantization"]
    reference_output = ", ".join(str(value) for value in self_test["reference_raw_output"])
    reference_margin = int(self_test["reference_raw_margin"])
    replacements = (
        (
            r"(kExpectedOutputScale\s*=\s*)[^;]+;",
            rf"\g<1>{float(output_quantization['scale']):.17g}F;",
        ),
        (
            r"(kExpectedOutputZeroPoint\s*=\s*)-?\d+;",
            rf"\g<1>{int(output_quantization['zero_point'])};",
        ),
        (r"(kExpectedModelBytes\s*=\s*)\d+;", rf"\g<1>{model_bytes};"),
        (
            r'(kExpectedModelSha256\[\]\s*=\s*)"[0-9a-f]{64}";',
            rf'\g<1>"{model_hash}";',
        ),
        (
            r"(kSelfTestMultiplier\s*=\s*)\d+U;",
            rf"\g<1>{self_test['multiplier']}U;",
        ),
        (
            r"(kSelfTestOffset\s*=\s*)\d+U;",
            rf"\g<1>{self_test['offset']}U;",
        ),
        (
            r"(kSelfTestExpectedClass\s*=\s*WasteClass::)k[A-Za-z]+;",
            rf"\g<1>k{str(self_test['expected_class']).title()};",
        ),
        (
            r"(kSelfTestMinimumRawMargin\s*=\s*)\d+;",
            rf"\g<1>{self_test['minimum_raw_margin']};",
        ),
        (
            r"(// \[)[^\]]+(\], whose top class is )[a-z]+( with raw margin )\d+(\.)",
            rf"\g<1>{reference_output}\g<2>{self_test['expected_class']}"
            rf"\g<3>{reference_margin}\g<4>",
        ),
    )
    for pattern, replacement in replacements:
        content, count = re.subn(pattern, replacement, content, count=1)
        if count != 1:
            raise RuntimeError(f"ESP32 contract field not found: {pattern}")
    write_text_atomic(path, content)


def _validate_destination(path: Path) -> None:
    if path != DEFAULT_ESP32.resolve() or not path.is_dir():
        raise ValueError(f"ESP32 destination must be {DEFAULT_ESP32.resolve()}")


if __name__ == "__main__":
    main()
