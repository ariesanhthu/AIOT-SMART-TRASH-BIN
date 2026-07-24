"""Verify that ESP-TRASH embeds the exact current AI/V4 INT8 model."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re


ESP_DIR = Path(__file__).resolve().parent
REPOSITORY_DIR = ESP_DIR.parent
V4_ARTIFACTS = REPOSITORY_DIR / "AI" / "V4" / "artifacts"
EXPECTED_LABELS = ["paper", "plastic", "organic", "other"]


def main() -> None:
    model_path = V4_ARTIFACTS / "model_int8.tflite"
    metadata_path = V4_ARTIFACTS / "model_metadata.json"
    source_path = ESP_DIR / "model_data.cpp"
    contract_path = ESP_DIR / "model_contract.h"

    model = model_path.read_bytes()
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    expected_hash = hashlib.sha256(model).hexdigest()
    metadata_model = metadata["artifacts"]["int8_model"]
    if metadata_model["size_bytes"] != len(model):
        raise RuntimeError("V4 metadata model size does not match the TFLite file")
    if metadata_model["sha256"] != expected_hash:
        raise RuntimeError("V4 metadata model hash does not match the TFLite file")
    if metadata.get("labels") != EXPECTED_LABELS:
        raise RuntimeError("V4 metadata label order is invalid")
    if metadata.get("output", {}).get("shape") != [1, len(EXPECTED_LABELS)]:
        raise RuntimeError("V4 metadata output shape is invalid")

    source = source_path.read_text(encoding="utf-8")
    array_match = re.search(
        r"g_model\[\].*?=\s*\{(?P<body>.*?)\};",
        source,
        flags=re.DOTALL,
    )
    if array_match is None:
        raise RuntimeError("Cannot find g_model byte array")
    embedded = bytes(
        int(value, 16)
        for value in re.findall(r"0x([0-9a-fA-F]{2})", array_match["body"])
    )
    embedded_length = int(_capture(source, r"g_model_len\s*=\s*(\d+)\s*;"))
    embedded_hash = _capture(
        source,
        r'g_model_sha256\[65\]\s*=\s*"([0-9a-f]{64})"\s*;',
    )
    if embedded != model:
        raise RuntimeError("Embedded byte array differs from AI/V4 model_int8.tflite")
    if embedded_length != len(model) or embedded_hash != expected_hash:
        raise RuntimeError("Embedded model length/hash constants are inconsistent")

    contract = contract_path.read_text(encoding="utf-8")
    contract_length = int(
        _capture(contract, r"kExpectedModelBytes\s*=\s*(\d+)\s*;")
    )
    contract_hash = _capture(
        contract,
        r'kExpectedModelSha256\[\]\s*=\s*\n?\s*"([0-9a-f]{64})"\s*;',
    )
    output_scale = float(
        _capture(
            contract,
            r"kExpectedOutputScale\s*=\s*([0-9.eE+-]+)F\s*;",
        )
    )
    output_zero_point = int(
        _capture(contract, r"kExpectedOutputZeroPoint\s*=\s*(-?\d+)\s*;")
    )
    class_count = int(_capture(contract, r"kClassCount\s*=\s*(\d+)\s*;"))
    if contract_length != len(model) or contract_hash != expected_hash:
        raise RuntimeError("model_contract.h length/hash differs from AI/V4")
    if class_count != len(EXPECTED_LABELS):
        raise RuntimeError("model_contract.h class count differs from AI/V4")

    metadata_output = metadata["output"]["quantization"]
    if abs(output_scale - float(metadata_output["scale"])) > 1.0e-9:
        raise RuntimeError("model_contract.h output scale differs from AI/V4")
    if output_zero_point != int(metadata_output["zero_point"]):
        raise RuntimeError("model_contract.h output zero point differs from AI/V4")

    print(
        "Embedded model verified: "
        f"{len(model)} bytes, SHA256={expected_hash}, "
        f"output=({output_scale}, {output_zero_point})"
    )


def _capture(content: str, pattern: str) -> str:
    match = re.search(pattern, content)
    if match is None:
        raise RuntimeError(f"Expected declaration not found: {pattern}")
    return match.group(1)


if __name__ == "__main__":
    main()
