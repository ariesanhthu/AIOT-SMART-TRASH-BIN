"""Convert the verified INT8 FlatBuffer into an aligned ESP32 C++ array."""

from __future__ import annotations

import argparse
import re

try:
    from .config import DEFAULT_ARTIFACT_DIR, DEFAULT_INT8_MODEL, DEFAULT_METADATA
    from .config import resolve_input_path, resolve_output_path
    from .metadata import (
        read_json,
        sha256_file,
        validate_metadata_contract,
        verify_artifact_hash,
        write_json_atomic,
        write_text_atomic,
    )
except ImportError:
    from config import (  # type: ignore
        DEFAULT_ARTIFACT_DIR,
        DEFAULT_INT8_MODEL,
        DEFAULT_METADATA,
        resolve_input_path,
        resolve_output_path,
    )
    from metadata import (  # type: ignore
        read_json,
        sha256_file,
        validate_metadata_contract,
        verify_artifact_hash,
        write_json_atomic,
        write_text_atomic,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default=str(DEFAULT_INT8_MODEL))
    parser.add_argument("--metadata", default=str(DEFAULT_METADATA))
    parser.add_argument("--header", default=str(DEFAULT_ARTIFACT_DIR / "model_data.h"))
    parser.add_argument("--source", default=str(DEFAULT_ARTIFACT_DIR / "model_data.cc"))
    parser.add_argument("--array-name", default="g_model")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", args.array_name):
        raise ValueError(f"Invalid C++ identifier: {args.array_name}")

    model_path = resolve_input_path(args.model)
    metadata_path = resolve_input_path(args.metadata)
    header_path = resolve_output_path(args.header)
    source_path = resolve_output_path(args.source)
    metadata = read_json(metadata_path)
    validate_metadata_contract(metadata)
    model_hash = verify_artifact_hash(metadata, "int8_model", model_path)
    model_bytes = model_path.read_bytes()

    guard = _include_guard(header_path.name)
    length_name = f"{args.array_name}_len"
    hash_name = f"{args.array_name}_sha256"
    header = "\n".join(
        [
            f"#ifndef {guard}",
            f"#define {guard}",
            "",
            "#include <cstddef>",
            "#include <cstdint>",
            "",
            f"extern const unsigned char {args.array_name}[];",
            f"extern const int {length_name};",
            f"extern const char {hash_name}[65];",
            "",
            f"#endif  // {guard}",
            "",
        ]
    )
    source = "\n".join(
        [
            f'#include "{header_path.name}"',
            "",
            "#if defined(ARDUINO_ARCH_ESP32)",
            "#include <pgmspace.h>",
            "#define AIOT_MODEL_STORAGE PROGMEM",
            "#else",
            "#define AIOT_MODEL_STORAGE",
            "#endif",
            "",
            f"alignas(16) const unsigned char {args.array_name}[] AIOT_MODEL_STORAGE = {{",
            _format_bytes(model_bytes),
            "};",
            f"const int {length_name} = {len(model_bytes)};",
            f'const char {hash_name}[65] = "{model_hash}";',
            "",
            "#undef AIOT_MODEL_STORAGE",
            "",
        ]
    )
    write_text_atomic(header_path, header)
    write_text_atomic(source_path, source)
    metadata["artifacts"]["model_header"] = {
        "file": header_path.name,
        "size_bytes": header_path.stat().st_size,
        "sha256": sha256_file(header_path),
    }
    metadata["artifacts"]["model_source"] = {
        "file": source_path.name,
        "size_bytes": source_path.stat().st_size,
        "sha256": sha256_file(source_path),
    }
    write_json_atomic(metadata_path, metadata)
    print(f"Saved C++ header: {header_path}")
    print(f"Saved C++ source: {source_path}")
    print(f"Model bytes: {len(model_bytes)}; SHA256: {model_hash}")


def _format_bytes(data: bytes, columns: int = 12) -> str:
    return "\n".join(
        "  " + ", ".join(f"0x{value:02x}" for value in data[start : start + columns]) + ","
        for start in range(0, len(data), columns)
    )


def _include_guard(file_name: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9]", "_", file_name).upper()
    return f"AIOT_{normalized}_"


if __name__ == "__main__":
    main()
