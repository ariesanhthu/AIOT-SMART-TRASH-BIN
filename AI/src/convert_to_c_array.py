from __future__ import annotations

import argparse
from pathlib import Path
import re


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Convert a TFLite model to C array.")
    parser.add_argument("--model", default="artifacts/model_int8.tflite")
    parser.add_argument("--header", default="artifacts/model_data.h")
    parser.add_argument("--source", default="artifacts/model_data.cc")
    parser.add_argument("--array-name", default="g_model")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    model_path = Path(args.model)
    header_path = Path(args.header)
    source_path = Path(args.source)
    data = model_path.read_bytes()

    header_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.parent.mkdir(parents=True, exist_ok=True)

    guard = make_include_guard(header_path.name)
    header_path.write_text(
        "\n".join(
            [
                f"#ifndef {guard}",
                f"#define {guard}",
                "",
                "#include <cstddef>",
                "#include <cstdint>",
                "",
                f"extern const unsigned char {args.array_name}[];",
                f"extern const int {args.array_name}_len;",
                "",
                f"#endif  // {guard}",
                "",
            ]
        ),
        encoding="utf-8",
    )

    source_path.write_text(
        "\n".join(
            [
                f'#include "{header_path.name}"',
                "",
                f"alignas(16) const unsigned char {args.array_name}[] = {{",
                format_bytes(data),
                "};",
                f"const int {args.array_name}_len = {len(data)};",
                "",
            ]
        ),
        encoding="utf-8",
    )

    print(f"Saved header: {header_path}")
    print(f"Saved source: {source_path}")
    print(f"Model bytes: {len(data)}")


def format_bytes(data: bytes, columns: int = 12) -> str:
    rows = []
    for start in range(0, len(data), columns):
        chunk = data[start : start + columns]
        rows.append("  " + ", ".join(f"0x{value:02x}" for value in chunk) + ",")
    return "\n".join(rows)


def make_include_guard(file_name: str) -> str:
    guard = re.sub(r"[^A-Za-z0-9]", "_", file_name).upper()
    return f"AIOT_{guard}_"


if __name__ == "__main__":
    main()
