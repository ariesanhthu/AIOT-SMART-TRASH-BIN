"""Small helpers for reproducible model metadata and artifact integrity."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from typing import Any

try:
    from .config import (
        CLASS_TO_INDEX,
        IMAGE_CHANNELS,
        IMAGE_SIZE,
        LABELS,
        METADATA_SCHEMA_VERSION,
        MODEL_VERSION,
        PREPROCESSING_SPEC,
    )
except ImportError:  # Allow ``python src/<script>.py`` from AI/.
    from config import (  # type: ignore
        CLASS_TO_INDEX,
        IMAGE_CHANNELS,
        IMAGE_SIZE,
        LABELS,
        METADATA_SCHEMA_VERSION,
        MODEL_VERSION,
        PREPROCESSING_SPEC,
    )


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def sha256_file(path: str | Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected a JSON object in {path}")
    return payload


def write_json_atomic(path: str | Path, payload: Any) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, destination)


def write_text_atomic(path: str | Path, content: str) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.tmp")
    temporary.write_text(content, encoding="utf-8", newline="\n")
    os.replace(temporary, destination)


def write_bytes_atomic(path: str | Path, content: bytes) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.tmp")
    temporary.write_bytes(content)
    os.replace(temporary, destination)


def base_model_metadata(dataset: dict[str, Any], seed: int) -> dict[str, Any]:
    return {
        "schema_version": METADATA_SCHEMA_VERSION,
        "model_version": MODEL_VERSION,
        "created_utc": utc_now_iso(),
        "labels": list(LABELS),
        "class_to_index": CLASS_TO_INDEX,
        "input": {
            "shape": [1, IMAGE_SIZE, IMAGE_SIZE, IMAGE_CHANNELS],
            "layout": "NHWC",
            "keras_dtype": "float32",
        },
        "output": {
            "name": "logits",
            "shape": [1, len(LABELS)],
            "semantics": "unnormalized_class_logits",
        },
        "preprocessing": dict(PREPROCESSING_SPEC),
        "dataset": dataset,
        "seed": seed,
        "artifacts": {},
    }


def validate_metadata_contract(metadata: dict[str, Any]) -> None:
    if metadata.get("schema_version") != METADATA_SCHEMA_VERSION:
        raise ValueError("Unsupported model metadata schema")
    if metadata.get("labels") != list(LABELS):
        raise ValueError(
            f"Metadata labels must be {list(LABELS)}, got {metadata.get('labels')}"
        )
    if metadata.get("class_to_index") != CLASS_TO_INDEX:
        raise ValueError("Metadata class_to_index does not match the label contract")
    if metadata.get("model_version") != MODEL_VERSION:
        raise ValueError(
            f"Metadata model_version must be '{MODEL_VERSION}', "
            f"got {metadata.get('model_version')}"
        )
    expected_shape = [1, IMAGE_SIZE, IMAGE_SIZE, IMAGE_CHANNELS]
    if metadata.get("input", {}).get("shape") != expected_shape:
        raise ValueError(
            f"Metadata input shape must be {expected_shape}, "
            f"got {metadata.get('input', {}).get('shape')}"
        )
    if metadata.get("preprocessing") != PREPROCESSING_SPEC:
        raise ValueError("Metadata preprocessing does not match the firmware contract")
    if metadata.get("output", {}).get("shape") != [1, len(LABELS)]:
        raise ValueError("Metadata output must be one three-logit tensor")


def verify_artifact_hash(
    metadata: dict[str, Any], artifact_key: str, path: str | Path
) -> str:
    expected = metadata.get("artifacts", {}).get(artifact_key, {}).get("sha256")
    if not expected:
        raise ValueError(f"Metadata has no SHA256 for artifact '{artifact_key}'")
    actual = sha256_file(path)
    if actual != expected:
        raise ValueError(
            f"SHA256 mismatch for {path}: metadata={expected}, actual={actual}"
        )
    return actual
