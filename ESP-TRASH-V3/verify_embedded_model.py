"""Verify that ESP-TRASH-V3 embeds the exact current AI/V9 INT8 model."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re


ESP_DIR = Path(__file__).resolve().parent
REPOSITORY_DIR = ESP_DIR.parent
ARTIFACTS = REPOSITORY_DIR / "AI" / "V9" / "artifacts"
EXPECTED_LABELS = ["paper", "plastic", "organic"]
EXPECTED_MODEL_VERSION = "tinycnn-v9-balanced-esp-contract"


def main() -> None:
    model_path = ARTIFACTS / "model_int8.tflite"
    metadata_path = ARTIFACTS / "model_metadata.json"
    quantization_path = ARTIFACTS / "quantization.json"
    source_path = ESP_DIR / "model_data.cpp"
    contract_path = ESP_DIR / "model_contract.h"
    deployment_path = ESP_DIR / "deployment_contract.json"

    model = model_path.read_bytes()
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    quantization = json.loads(quantization_path.read_text(encoding="utf-8"))
    deployment = json.loads(deployment_path.read_text(encoding="utf-8"))
    expected_hash = hashlib.sha256(model).hexdigest()
    if metadata["int8_model"]["bytes"] != len(model):
        raise RuntimeError("V9 metadata model size does not match the TFLite file")
    if metadata["int8_model"]["sha256"] != expected_hash:
        raise RuntimeError("V9 metadata model hash does not match the TFLite file")
    if quantization["sha256"] != expected_hash or deployment["sha256"] != expected_hash:
        raise RuntimeError("V9 quantization/deployment model hash differs")
    if metadata.get("model_version") != EXPECTED_MODEL_VERSION:
        raise RuntimeError("V9 model version is invalid")
    if metadata.get("labels") != EXPECTED_LABELS or deployment["labels"] != EXPECTED_LABELS:
        raise RuntimeError("V9 label order is invalid")
    if quantization["input"]["shape"] != [1, 96, 96, 3]:
        raise RuntimeError("V9 input shape is invalid")
    if quantization["output"]["shape"] != [1, len(EXPECTED_LABELS)]:
        raise RuntimeError("V9 output shape is invalid")
    if quantization["float_tensors"]:
        raise RuntimeError("V9 deployment model contains floating tensors")

    source = source_path.read_text(encoding="utf-8")
    array_match = re.search(
        r"g_model\[\].*?=\s*\{(?P<body>.*?)\};", source, flags=re.DOTALL
    )
    if array_match is None:
        raise RuntimeError("Cannot find g_model byte array")
    embedded = bytes(
        int(value, 16)
        for value in re.findall(r"0x([0-9a-fA-F]{2})", array_match["body"])
    )
    embedded_length = int(_capture(source, r"g_model_len\s*=\s*(\d+)\s*;"))
    embedded_hash = _capture(
        source, r'g_model_sha256\[65\]\s*=\s*"([0-9a-f]{64})"\s*;'
    )
    if embedded != model:
        raise RuntimeError("Embedded byte array differs from AI/V9/model_int8.tflite")
    if embedded_length != len(model) or embedded_hash != expected_hash:
        raise RuntimeError("Embedded model length/hash declarations are inconsistent")

    contract = contract_path.read_text(encoding="utf-8")
    if int(_capture(contract, r"kExpectedModelBytes\s*=\s*(\d+)\s*;")) != len(model):
        raise RuntimeError("model_contract.h model length differs from V9")
    if _capture(
        contract, r'kExpectedModelSha256\[\]\s*=\s*\n?\s*"([0-9a-f]{64})"\s*;'
    ) != expected_hash:
        raise RuntimeError("model_contract.h model hash differs from V9")
    _verify_quantization(contract, "Input", quantization["input"]["quantization"])
    _verify_quantization(contract, "Output", quantization["output"]["quantization"])

    print(
        "Embedded V9 model verified: "
        f"{len(model)} bytes, SHA256={expected_hash}, "
        f"operators={','.join(quantization['unique_operators'])}"
    )


def _verify_quantization(contract: str, tensor_name: str, expected: dict) -> None:
    scale = float(_capture(
        contract, rf"kExpected{tensor_name}Scale\s*=\s*([0-9.eE+-]+)F\s*;"
    ))
    zero = int(_capture(
        contract, rf"kExpected{tensor_name}ZeroPoint\s*=\s*(-?\d+)\s*;"
    ))
    if abs(scale - float(expected["scale"])) > 1.0e-9 or zero != int(expected["zero_point"]):
        raise RuntimeError(f"model_contract.h {tensor_name.lower()} quantization differs")


def _capture(content: str, pattern: str) -> str:
    match = re.search(pattern, content)
    if match is None:
        raise RuntimeError(f"Expected declaration not found: {pattern}")
    return match.group(1)


if __name__ == "__main__":
    main()
