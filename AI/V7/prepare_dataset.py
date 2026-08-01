"""Create a leakage-aware V7 split using only raw ESP32-CAM captures."""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
from typing import Iterable

from PIL import Image

from V7.config import (
    BURST_GAP_SECONDS,
    CLASS_NAMES,
    CLASS_TO_INDEX,
    FORBIDDEN_SOURCE_TOKENS,
    IMAGE_EXTENSIONS,
    PREPARED_DATA_DIR,
    PREPROCESSING_CONFIG,
    REPOSITORY_DIR,
    SOURCE_DATA_DIR,
    SPLITS,
    SPLIT_TARGETS,
    STORED_AUGMENTATION_TOKEN,
    V7_DIR,
)


CAPTURE_PATTERN = re.compile(
    r"^esp32-cam-(?P<timestamp>\d{4}-\d{2}-\d{2}T"
    r"\d{2}-\d{2}-\d{2}-\d{3}Z)\.jpg$",
    flags=re.IGNORECASE,
)
MANIFEST_FIELDS = (
    "relative_path",
    "split",
    "label",
    "label_id",
    "source",
    "source_relative_path",
    "source_sha256",
    "output_sha256",
    "width",
    "height",
    "captured_at_utc",
    "capture_session",
    "burst_id",
)


@dataclass(frozen=True)
class Capture:
    path: Path
    label: str
    label_id: int
    captured_at: datetime
    width: int
    height: int
    sha256: str


@dataclass(frozen=True)
class Burst:
    burst_id: str
    captures: tuple[Capture, ...]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true")
    parser.add_argument(
        "--source",
        type=Path,
        default=SOURCE_DATA_DIR,
        help="Must resolve to AI/V7/data; external roots are rejected.",
    )
    parser.add_argument("--out", type=Path, default=PREPARED_DATA_DIR)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    summary = prepare_dataset(args.source, args.out, force=args.force)
    print(json.dumps(summary, indent=2, ensure_ascii=False))


def prepare_dataset(
    source: str | Path = SOURCE_DATA_DIR,
    output: str | Path = PREPARED_DATA_DIR,
    *,
    force: bool = False,
) -> dict:
    source_root = Path(source).expanduser().resolve()
    output_root = Path(output).expanduser().resolve()
    _validate_canonical_paths(source_root, output_root)
    _validate_firmware_label_order()

    captures, audit_rows = _scan_source(source_root)
    assignments: dict[Path, tuple[str, str]] = {}
    burst_summary: dict[str, dict[str, object]] = {}
    for label in CLASS_NAMES:
        bursts = _build_bursts([item for item in captures if item.label == label])
        split_bursts = _split_bursts(bursts)
        burst_summary[label] = {
            split: {
                "bursts": [burst.burst_id for burst in split_bursts[split]],
                "images": sum(len(burst.captures) for burst in split_bursts[split]),
            }
            for split in SPLITS
        }
        for split, selected_bursts in split_bursts.items():
            for burst in selected_bursts:
                for capture in burst.captures:
                    assignments[capture.path] = (split, burst.burst_id)

    if len(assignments) != len(captures):
        raise RuntimeError("Not every admitted capture received exactly one split")
    if output_root.exists():
        if not force:
            raise FileExistsError(f"Output exists; pass --force: {output_root}")
        _safe_remove_prepared(output_root)

    temporary = output_root.with_name(f".{output_root.name}.tmp")
    if temporary.exists():
        _safe_remove_prepared(temporary)
    for split in SPLITS:
        for label in CLASS_NAMES:
            (temporary / split / label).mkdir(parents=True, exist_ok=True)

    manifest_rows: list[dict[str, object]] = []
    try:
        for capture in sorted(
            captures, key=lambda item: (item.label_id, item.captured_at)
        ):
            split, burst_id = assignments[capture.path]
            relative_path = Path(split) / capture.label / capture.path.name
            destination = temporary / relative_path
            shutil.copy2(capture.path, destination)
            output_hash = _sha256(destination)
            if output_hash != capture.sha256:
                raise RuntimeError(f"Copy verification failed: {capture.path}")
            manifest_rows.append(
                {
                    "relative_path": relative_path.as_posix(),
                    "split": split,
                    "label": capture.label,
                    "label_id": capture.label_id,
                    "source": "v7_esp32_raw",
                    "source_relative_path": capture.path.relative_to(
                        source_root
                    ).as_posix(),
                    "source_sha256": capture.sha256,
                    "output_sha256": output_hash,
                    "width": capture.width,
                    "height": capture.height,
                    "captured_at_utc": capture.captured_at.isoformat().replace(
                        "+00:00", "Z"
                    ),
                    "capture_session": capture.captured_at.date().isoformat(),
                    "burst_id": burst_id,
                }
            )

        _write_csv(temporary / "manifest.csv", manifest_rows, MANIFEST_FIELDS)
        summary = _build_summary(
            source_root, output_root, manifest_rows, audit_rows, burst_summary
        )
        (temporary / "stats.json").write_text(
            json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, output_root)
    except Exception:
        if temporary.exists():
            _safe_remove_prepared(temporary)
        raise

    # User-facing immutable admissions list and complete rejection audit.
    _write_csv(V7_DIR / "dataset_manifest.csv", manifest_rows, MANIFEST_FIELDS)
    _write_csv(
        V7_DIR / "source_audit.csv",
        audit_rows,
        ("source_relative_path", "label", "admitted", "reason"),
    )
    (V7_DIR / "class_names.json").write_text(
        json.dumps(list(CLASS_NAMES), indent=2) + "\n", encoding="utf-8"
    )
    (V7_DIR / "preprocessing_config.json").write_text(
        json.dumps(PREPROCESSING_CONFIG, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return summary


def _validate_canonical_paths(source_root: Path, output_root: Path) -> None:
    canonical_source = SOURCE_DATA_DIR.resolve()
    if source_root != canonical_source:
        raise RuntimeError(
            "V7 refuses non-canonical data roots. Expected exactly: "
            f"{canonical_source}; received: {source_root}"
        )
    allowed_outputs = {
        PREPARED_DATA_DIR.resolve(),
        PREPARED_DATA_DIR.with_name(f".{PREPARED_DATA_DIR.name}.tmp").resolve(),
    }
    if output_root not in allowed_outputs:
        raise RuntimeError(
            f"V7 refuses output outside its prepared directory: {output_root}"
        )

    normalized = source_root.as_posix().lower()
    for token in FORBIDDEN_SOURCE_TOKENS:
        if token in normalized:
            raise RuntimeError(f"Forbidden V7 source token '{token}' in {source_root}")


def _validate_firmware_label_order() -> None:
    contract = REPOSITORY_DIR / "ESP-TRASH" / "model_contract.h"
    if not contract.is_file():
        raise FileNotFoundError(f"Firmware class contract not found: {contract}")
    content = contract.read_text(encoding="utf-8")
    match = re.search(r"kLabels\s*=\s*\{(?P<body>.*?)\};", content, re.DOTALL)
    if match is None:
        raise RuntimeError("Cannot read kLabels from ESP-TRASH/model_contract.h")
    firmware_labels = re.findall(r'"([^"]+)"', match.group("body"))
    if tuple(firmware_labels[: len(CLASS_NAMES)]) != CLASS_NAMES:
        raise RuntimeError(
            "V7/Firmware label mismatch: "
            f"V7={CLASS_NAMES}, firmware prefix={tuple(firmware_labels)}"
        )


def _scan_source(source_root: Path) -> tuple[list[Capture], list[dict[str, str]]]:
    if not source_root.is_dir():
        raise FileNotFoundError(f"V7 data directory not found: {source_root}")
    class_directories = sorted(
        path.name for path in source_root.iterdir() if path.is_dir()
    )
    if class_directories != sorted(CLASS_NAMES):
        raise RuntimeError(
            f"Expected exactly class directories {list(CLASS_NAMES)}, found {class_directories}"
        )

    captures: list[Capture] = []
    audit: list[dict[str, str]] = []
    seen_hashes: dict[str, Path] = {}
    for label in CLASS_NAMES:
        directory = source_root / label
        for path in sorted(directory.iterdir()):
            if not path.is_file() or path.suffix.lower() not in IMAGE_EXTENSIONS:
                continue
            relative = path.relative_to(source_root).as_posix()
            lower_name = path.name.lower()
            match = CAPTURE_PATTERN.fullmatch(path.name)
            admitted = match is not None and STORED_AUGMENTATION_TOKEN not in lower_name
            if not admitted:
                reason = (
                    "stored_augmentation_excluded"
                    if STORED_AUGMENTATION_TOKEN in lower_name
                    else "legacy_or_non_esp32_filename_excluded"
                )
                audit.append(
                    {
                        "source_relative_path": relative,
                        "label": label,
                        "admitted": "false",
                        "reason": reason,
                    }
                )
                continue

            resolved = path.resolve()
            if not resolved.is_relative_to(source_root):
                raise RuntimeError(f"Source file escapes AI/V7/data: {path}")
            normalized = resolved.as_posix().lower()
            if any(token in normalized for token in FORBIDDEN_SOURCE_TOKENS):
                raise RuntimeError(f"Forbidden dataset source detected: {resolved}")

            captured_at = datetime.strptime(
                match.group("timestamp"), "%Y-%m-%dT%H-%M-%S-%fZ"
            ).replace(tzinfo=timezone.utc)
            with Image.open(path) as image:
                image.verify()
                width, height = image.size
            if width < 1 or height < 1:
                raise ValueError(f"Invalid image dimensions: {path}")
            digest = _sha256(path)
            if digest in seen_hashes:
                raise RuntimeError(
                    f"Duplicate image content crosses V7 records: {seen_hashes[digest]} and {path}"
                )
            seen_hashes[digest] = path
            captures.append(
                Capture(
                    path,
                    label,
                    CLASS_TO_INDEX[label],
                    captured_at,
                    width,
                    height,
                    digest,
                )
            )
            audit.append(
                {
                    "source_relative_path": relative,
                    "label": label,
                    "admitted": "true",
                    "reason": "raw_esp32_capture",
                }
            )

    for label in CLASS_NAMES:
        count = sum(item.label == label for item in captures)
        if count < 3:
            raise RuntimeError(
                f"Need at least three raw captures for class '{label}', found {count}"
            )
    return captures, audit


def _build_bursts(captures: Iterable[Capture]) -> tuple[Burst, ...]:
    ordered = sorted(captures, key=lambda item: item.captured_at)
    if not ordered:
        return ()
    groups: list[list[Capture]] = [[ordered[0]]]
    for capture in ordered[1:]:
        gap = (capture.captured_at - groups[-1][-1].captured_at).total_seconds()
        if gap <= BURST_GAP_SECONDS:
            groups[-1].append(capture)
        else:
            groups.append([capture])
    label = ordered[0].label
    date = ordered[0].captured_at.strftime("%Y%m%d")
    return tuple(
        Burst(f"{label}-{date}-b{index:03d}", tuple(group))
        for index, group in enumerate(groups, start=1)
    )


def _split_bursts(bursts: tuple[Burst, ...]) -> dict[str, tuple[Burst, ...]]:
    """Choose two chronological boundaries without splitting adjacent bursts."""

    if len(bursts) < 3:
        raise RuntimeError(
            f"Need at least three capture bursts for train/validation/test, found {len(bursts)}"
        )
    total = sum(len(burst.captures) for burst in bursts)
    target_counts = [SPLIT_TARGETS[split] * total for split in SPLITS]
    best: tuple[float, int, int] | None = None
    for train_end in range(1, len(bursts) - 1):
        for validation_end in range(train_end + 1, len(bursts)):
            counts = [
                sum(len(burst.captures) for burst in bursts[:train_end]),
                sum(len(burst.captures) for burst in bursts[train_end:validation_end]),
                sum(len(burst.captures) for burst in bursts[validation_end:]),
            ]
            error = sum(
                ((count - target) / total) ** 2
                for count, target in zip(counts, target_counts, strict=True)
            )
            candidate = (error, train_end, validation_end)
            if best is None or candidate < best:
                best = candidate
    if best is None:
        raise RuntimeError("Unable to create chronological burst split")
    _, train_end, validation_end = best
    return {
        "train": bursts[:train_end],
        "validation": bursts[train_end:validation_end],
        "test": bursts[validation_end:],
    }


def _build_summary(
    source_root: Path,
    output_root: Path,
    rows: list[dict[str, object]],
    audit_rows: list[dict[str, str]],
    bursts: dict[str, dict[str, object]],
) -> dict:
    counts = {
        split: {
            label: sum(row["split"] == split and row["label"] == label for row in rows)
            for label in CLASS_NAMES
        }
        for split in SPLITS
    }
    admitted_hash = hashlib.sha256()
    for row in sorted(rows, key=lambda item: str(item["relative_path"])):
        admitted_hash.update(str(row["relative_path"]).encode("utf-8"))
        admitted_hash.update(str(row["source_sha256"]).encode("ascii"))
    return {
        "source_root": str(source_root),
        "output_root": str(output_root),
        "labels": list(CLASS_NAMES),
        "class_to_index": CLASS_TO_INDEX,
        "allowed_source": "only esp32-cam-*.jpg under AI/V7/data/<class>",
        "external_dataset_used": False,
        "trashnet_used": False,
        "stored_augmentation_used": False,
        "split_strategy": (
            "chronological per-class burst split; adjacent captures within "
            f"{BURST_GAP_SECONDS:g}s stay together; latest bursts form test"
        ),
        "counts": counts,
        "admitted_total": len(rows),
        "excluded_total": sum(row["admitted"] == "false" for row in audit_rows),
        "admitted_dataset_sha256": admitted_hash.hexdigest(),
        "bursts": bursts,
        "sealed_test_warning": (
            "All current raw captures are from one UTC date. Test is a chronological "
            "burst holdout, not an independent recapture session. Capture a new session "
            "with the same objects before claiming final real-world accuracy."
        ),
    }


def _write_csv(
    path: Path, rows: list[dict[str, object]], fields: tuple[str, ...]
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_remove_prepared(path: Path) -> None:
    resolved = path.resolve()
    allowed = {
        PREPARED_DATA_DIR.resolve(),
        PREPARED_DATA_DIR.with_name(f".{PREPARED_DATA_DIR.name}.tmp").resolve(),
    }
    if resolved not in allowed or resolved.parent != V7_DIR.resolve():
        raise RuntimeError(f"Refusing to remove unexpected path: {resolved}")
    shutil.rmtree(resolved)


if __name__ == "__main__":
    main()
