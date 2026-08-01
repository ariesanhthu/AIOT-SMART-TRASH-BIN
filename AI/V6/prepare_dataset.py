"""Build V6 from the prepared V4 splits plus new ESP32-CAM captures only.

V4 is the sole base dataset. New camera images may use arbitrary names, but
when they share the mixed ``V6/dataset_prepared`` folders only files beginning
with ``esp32-cam-`` are admitted. Existing V4 validation/test splits are kept
unchanged and every new camera burst remains in train to prevent leakage.
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import uuid

from PIL import Image, ImageOps

from V6.runtime import LABELS


V6_DIR = Path(__file__).resolve().parent
AI_DIR = V6_DIR.parent
DEFAULT_V4_DATA = AI_DIR / "V4" / "dataset_prepared"
DEFAULT_NEW_DATA = V6_DIR / "dataset_prepared"
DEFAULT_OUTPUT = V6_DIR / "dataset_indexed"
SPLITS = ("train", "validation", "test")
IMAGE_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png"})
CLASS_TO_INDEX = {label: index for index, label in enumerate(LABELS)}
CAMERA_PREFIX = "esp32-cam-"
MANIFEST_FIELDS = (
    "relative_path",
    "split",
    "label",
    "label_id",
    "source",
    "source_split",
    "source_sha256",
    "output_sha256",
    "width",
    "height",
    "group_id",
    "source_kind",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--v4-data", type=Path, default=DEFAULT_V4_DATA)
    parser.add_argument("--new-data", type=Path, default=DEFAULT_NEW_DATA)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    summary = prepare_dataset(
        v4_data=args.v4_data,
        new_data=args.new_data,
        output=args.out,
        seed=args.seed,
        force=args.force,
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))


def prepare_dataset(
    *,
    v4_data: str | Path,
    new_data: str | Path,
    output: str | Path,
    seed: int,
    force: bool,
) -> dict:
    v4_root = Path(v4_data).expanduser().resolve()
    new_root = Path(new_data).expanduser().resolve()
    output_root = Path(output).expanduser().resolve()
    _validate_roots(v4_root, new_root, output_root)

    records = _discover_v4(v4_root)
    v4_total = len(records)
    camera_records = _discover_camera_captures(new_root)
    records.extend(camera_records)
    _validate_records(records)

    if output_root.exists() and not force:
        raise FileExistsError(f"Output exists; pass --force: {output_root}")
    staging = output_root.parent / f".{output_root.name}.staging-{uuid.uuid4().hex}"
    backup = output_root.parent / f".{output_root.name}.backup"
    _validate_temporary(staging, output_root.parent)
    _validate_temporary(backup, output_root.parent)

    rows: list[dict[str, str | int]] = []
    try:
        for split in SPLITS:
            for label in LABELS:
                (staging / split / label).mkdir(parents=True, exist_ok=False)

        for record in sorted(
            records,
            key=lambda item: (
                SPLITS.index(item["split"]),
                CLASS_TO_INDEX[item["label"]],
                item["source_kind"],
                item["source"].as_posix(),
            ),
        ):
            source: Path = record["source"]
            destination = (
                staging
                / record["split"]
                / record["label"]
                / _canonical_name(record)
            )
            if destination.exists():
                raise ValueError(f"Destination collision: {destination}")
            shutil.copy2(source, destination)
            output_hash = _sha256_file(destination)
            if output_hash != record["sha256"]:
                raise RuntimeError(f"Copy integrity failure: {source}")
            rows.append(
                {
                    "relative_path": destination.relative_to(staging).as_posix(),
                    "split": record["split"],
                    "label": record["label"],
                    "label_id": CLASS_TO_INDEX[record["label"]],
                    "source": str(source),
                    "source_split": record["source_split"],
                    "source_sha256": record["sha256"],
                    "output_sha256": output_hash,
                    "width": record["width"],
                    "height": record["height"],
                    "group_id": record["group_id"],
                    "source_kind": record["source_kind"],
                }
            )

        _write_manifest(staging / "manifest.csv", rows)
        dataset_hash = _sha256_file(staging / "manifest.csv")
        counts = _counts(rows)
        effective_per_class = max(counts["train"][label] for label in LABELS)
        new_counts = {
            label: sum(record["label"] == label for record in camera_records)
            for label in LABELS
        }
        summary = {
            "schema_version": 2,
            "created_utc": datetime.now(timezone.utc)
            .replace(microsecond=0)
            .isoformat(),
            "seed": seed,
            "labels": list(LABELS),
            "class_to_index": CLASS_TO_INDEX,
            "v4_source": str(v4_root),
            "new_camera_source": str(new_root),
            "output": str(output_root),
            "source_policy": (
                "V4 dataset_prepared is the only base dataset; only esp32-cam-* "
                "files are added from V6 dataset_prepared"
            ),
            "counts": counts,
            "prepared_total": len(rows),
            "v4_images": v4_total,
            "new_camera_images": len(camera_records),
            "new_camera_counts": new_counts,
            "dataset_sha256": dataset_hash,
            "balance_strategy": {
                "method": "exact round-robin class sampling with online augmentation",
                "effective_samples_per_class_per_epoch": effective_per_class,
                "effective_total_per_epoch": effective_per_class * len(LABELS),
                "stored_duplicates_created": 0,
            },
            "leakage_control": (
                "V4 train/validation/test splits are preserved exactly; all new "
                "same-session ESP32 captures are train-only"
            ),
        }
        (staging / "stats.json").write_text(
            json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        _install(staging, output_root, backup, force)
    except BaseException:
        if staging.exists():
            _safe_remove(staging, output_root.parent)
        raise
    return summary


def _discover_v4(root: Path) -> list[dict]:
    records: list[dict] = []
    for split in SPLITS:
        for label in LABELS:
            class_dir = root / split / label
            if not class_dir.is_dir():
                raise FileNotFoundError(f"Missing V4 class directory: {class_dir}")
            images = [path for path in sorted(class_dir.rglob("*")) if _is_image(path)]
            if not images:
                raise FileNotFoundError(f"V4 split/class is empty: {class_dir}")
            for path in images:
                records.append(
                    _inspect(
                        path,
                        split=split,
                        label=label,
                        source_split=f"v4_{split}",
                        source_kind="v4_prepared",
                    )
                )
    return records


def _discover_camera_captures(root: Path) -> list[dict]:
    records: list[dict] = []
    for label in LABELS:
        class_dir = root / "train" / label
        if not class_dir.is_dir():
            if label == "other":
                continue
            raise FileNotFoundError(f"Missing new-camera class directory: {class_dir}")
        for path in sorted(class_dir.rglob("*")):
            if not _is_image(path) or not path.name.lower().startswith(CAMERA_PREFIX):
                continue
            records.append(
                _inspect(
                    path,
                    split="train",
                    label=label,
                    source_split="new_camera_train",
                    source_kind="esp32_capture",
                )
            )
    if not records:
        raise ValueError(f"No {CAMERA_PREFIX}* images found under {root / 'train'}")
    return records


def _inspect(
    path: Path,
    *,
    split: str,
    label: str,
    source_split: str,
    source_kind: str,
) -> dict:
    try:
        with Image.open(path) as image:
            image.verify()
        with Image.open(path) as image:
            oriented = ImageOps.exif_transpose(image)
            width, height = oriented.size
            oriented.convert("RGB").getpixel((0, 0))
    except Exception as exc:
        raise ValueError(f"Unreadable image {path}: {exc}") from exc
    digest = _sha256_file(path)
    return {
        "source": path.resolve(),
        "split": split,
        "label": label,
        "source_split": source_split,
        "sha256": digest,
        "width": width,
        "height": height,
        "source_kind": source_kind,
        "group_id": f"{source_kind}/{label}/{digest[:24]}",
    }


def _validate_records(records: list[dict]) -> None:
    hashes: dict[str, dict] = {}
    locations: set[tuple[str, str, str]] = set()
    for record in records:
        duplicate = hashes.get(record["sha256"])
        if duplicate is not None:
            raise ValueError(
                "Exact duplicate image content is not allowed: "
                f"{duplicate['source']} and {record['source']}"
            )
        hashes[record["sha256"]] = record
        key = (record["split"], record["label"], _canonical_name(record).lower())
        if key in locations:
            raise ValueError(f"Case-insensitive destination collision: {key}")
        locations.add(key)
    for split in SPLITS:
        for label in LABELS:
            if not any(
                record["split"] == split and record["label"] == label
                for record in records
            ):
                raise ValueError(f"V6 split/class is empty: {split}/{label}")


def _canonical_name(record: dict) -> str:
    suffix = record["source"].suffix.lower()
    prefix = "camera" if record["source_kind"] == "esp32_capture" else "v4"
    return f"{prefix}_{record['label']}_{record['sha256'][:24]}{suffix}"


def _counts(rows: list[dict[str, str | int]]) -> dict[str, dict[str, int]]:
    result: dict[str, dict[str, int]] = {}
    for split in SPLITS:
        per_class = {
            label: sum(row["split"] == split and row["label"] == label for row in rows)
            for label in LABELS
        }
        per_class["total"] = sum(per_class.values())
        result[split] = per_class
    return result


def _write_manifest(path: Path, rows: list[dict[str, str | int]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=MANIFEST_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _validate_roots(v4: Path, new: Path, output: Path) -> None:
    if not v4.is_dir():
        raise NotADirectoryError(v4)
    if not new.is_dir():
        raise NotADirectoryError(new)
    if v4 == new:
        raise ValueError("V4 base and new-camera source must be different directories")
    if output in {v4, new} or v4 in output.parents or new in output.parents:
        raise ValueError("Generated output must not overwrite a source directory")
    if output.parent != V6_DIR.resolve() or output.name != DEFAULT_OUTPUT.name:
        raise ValueError(f"V6 generated dataset must be {DEFAULT_OUTPUT.resolve()}")
    if output.is_symlink():
        raise ValueError(f"Refusing to replace symlink: {output}")


def _validate_temporary(path: Path, parent: Path) -> None:
    if path.parent.resolve() != parent.resolve() or not path.name.startswith("."):
        raise ValueError(f"Unsafe temporary path: {path}")


def _install(staging: Path, target: Path, backup: Path, force: bool) -> None:
    if backup.exists():
        _safe_remove(backup, target.parent)
    moved_old = False
    try:
        if target.exists():
            if not force:
                raise FileExistsError(target)
            os.replace(target, backup)
            moved_old = True
        os.replace(staging, target)
    except BaseException:
        if moved_old and backup.exists() and not target.exists():
            os.replace(backup, target)
        raise
    if backup.exists():
        _safe_remove(backup, target.parent)


def _safe_remove(path: Path, expected_parent: Path) -> None:
    resolved = path.resolve()
    if resolved.parent != expected_parent.resolve() or not resolved.name.startswith("."):
        raise ValueError(f"Refusing to remove unsafe path: {resolved}")
    shutil.rmtree(resolved)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _is_image(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS


if __name__ == "__main__":
    main()
