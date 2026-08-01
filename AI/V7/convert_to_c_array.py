"""Export the verified V7 INT8 model and its firmware contract."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import tensorflow as tf

from V7.config import ARTIFACTS_DIR, CLASS_NAMES, ESP32_MODEL_DIR


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--model", type=Path, default=ARTIFACTS_DIR / "model_int8.tflite"
    )
    parser.add_argument("--out", type=Path, default=ESP32_MODEL_DIR)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = convert_model(args.model, args.out)
    print(json.dumps(result, indent=2, ensure_ascii=False))


def convert_model(
    model_path: str | Path = ARTIFACTS_DIR / "model_int8.tflite",
    output: str | Path = ESP32_MODEL_DIR,
) -> dict:
    path = Path(model_path).expanduser().resolve()
    output_dir = Path(output).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"V7 INT8 model not found: {path}")
    output_dir.mkdir(parents=True, exist_ok=True)
    model = path.read_bytes()
    digest = hashlib.sha256(model).hexdigest()
    interpreter = tf.lite.Interpreter(model_content=model)
    interpreter.allocate_tensors()
    input_detail = interpreter.get_input_details()[0]
    output_detail = interpreter.get_output_details()[0]
    input_scale, input_zero_point = input_detail["quantization"]
    output_scale, output_zero_point = output_detail["quantization"]
    if input_detail["dtype"] != np.int8 or output_detail["dtype"] != np.int8:
        raise RuntimeError("V7 firmware export requires int8 input and output")

    self_test = _run_self_test(interpreter, input_detail, output_detail)
    (output_dir / "model_data.h").write_text(_model_header(), encoding="utf-8")
    (output_dir / "model_data.cpp").write_text(
        _model_source(model, digest), encoding="utf-8"
    )
    (output_dir / "model_contract_v7.h").write_text(
        _contract_header(
            len(model),
            digest,
            float(input_scale),
            int(input_zero_point),
            float(output_scale),
            int(output_zero_point),
            self_test,
        ),
        encoding="utf-8",
    )
    result = {
        "model_bytes": len(model),
        "sha256": digest,
        "labels": list(CLASS_NAMES),
        "input_quantization": {
            "scale": float(input_scale),
            "zero_point": int(input_zero_point),
        },
        "output_quantization": {
            "scale": float(output_scale),
            "zero_point": int(output_zero_point),
        },
        "output_semantic": "probabilities",
        "required_unique_operators": ["CONV_2D", "MEAN", "FULLY_CONNECTED", "SOFTMAX"],
        "self_test": self_test,
    }
    (output_dir / "deployment_contract.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return result


def _run_self_test(interpreter, input_detail, output_detail) -> dict:
    count = int(np.prod(input_detail["shape"]))
    channel = ((np.arange(count, dtype=np.uint32) * 191 + 7) & 0xFF).astype(np.int16)
    tensor = (channel - 128).astype(np.int8).reshape(input_detail["shape"])
    interpreter.set_tensor(input_detail["index"], tensor)
    interpreter.invoke()
    raw = interpreter.get_tensor(output_detail["index"])[0].astype(np.int16)
    order = np.argsort(raw)
    top = int(order[-1])
    margin = int(raw[order[-1]] - raw[order[-2]])
    if margin < 2:
        raise RuntimeError(f"V7 self-test vector has insufficient raw margin: {margin}")
    return {
        "multiplier": 191,
        "offset": 7,
        "raw_output": [int(value) for value in raw],
        "expected_class": CLASS_NAMES[top],
        "expected_class_id": top,
        "observed_raw_margin": margin,
        "minimum_raw_margin": max(2, margin // 2),
    }


def _model_header() -> str:
    return """#pragma once

extern const unsigned char g_model[];
extern const int g_model_len;
extern const char g_model_sha256[65];
"""


def _model_source(model: bytes, digest: str) -> str:
    lines = []
    for offset in range(0, len(model), 12):
        values = ", ".join(f"0x{value:02x}" for value in model[offset : offset + 12])
        lines.append(f"  {values},")
    body = "\n".join(lines)
    return f"""#include \"model_data.h\"

alignas(16) const unsigned char g_model[] = {{
{body}
}};

const int g_model_len = {len(model)};
const char g_model_sha256[65] = \"{digest}\";
"""


def _contract_header(
    size: int,
    digest: str,
    input_scale: float,
    input_zero_point: int,
    output_scale: float,
    output_zero_point: int,
    self_test: dict,
) -> str:
    enum_name = {
        "paper": "kPaper",
        "plastic": "kPlastic",
        "organic": "kOrganic",
    }[self_test["expected_class"]]
    raw = ", ".join(str(value) for value in self_test["raw_output"])
    return f"""#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

namespace aiot::model_contract {{

inline constexpr int kInputBatch = 1;
inline constexpr int kInputHeight = 96;
inline constexpr int kInputWidth = 96;
inline constexpr int kInputChannels = 3;
inline constexpr int kClassCount = 3;

inline constexpr float kExpectedInputScale = {input_scale:.17g}F;
inline constexpr std::int32_t kExpectedInputZeroPoint = {input_zero_point};
inline constexpr float kExpectedOutputScale = {output_scale:.17g}F;
inline constexpr std::int32_t kExpectedOutputZeroPoint = {output_zero_point};
inline constexpr float kQuantizationTolerance = 1.0e-7F;

inline constexpr int kExpectedModelBytes = {size};
inline constexpr char kExpectedModelSha256[] = \"{digest}\";

enum class OutputSemantic : std::uint8_t {{ kLogits, kProbabilities }};
inline constexpr OutputSemantic kOutputSemantic = OutputSemantic::kProbabilities;

enum class WasteClass : std::uint8_t {{
  kPaper = 0,
  kPlastic = 1,
  kOrganic = 2,
}};
inline constexpr std::array<const char*, kClassCount> kLabels = {{
    \"paper\", \"plastic\", \"organic\"}};

// LiteRT deterministic startup reference raw output: [{raw}].
inline constexpr std::uint32_t kSelfTestMultiplier = 191U;
inline constexpr std::uint32_t kSelfTestOffset = 7U;
inline constexpr WasteClass kSelfTestExpectedClass = WasteClass::{enum_name};
inline constexpr int kSelfTestMinimumRawMargin = {self_test["minimum_raw_margin"]};

inline constexpr std::size_t kTensorArenaBytes = 256U * 1024U;

}}  // namespace aiot::model_contract
"""


if __name__ == "__main__":
    main()
