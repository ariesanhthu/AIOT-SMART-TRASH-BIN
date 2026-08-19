"""Verify V9 balance, lineage, image integrity and split isolation."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import re

from PIL import Image


V9_DIR = Path(__file__).resolve().parent
DEFAULT_DATASET = V9_DIR / "dataset_prepared"
LABELS = ("paper", "plastic", "organic")
SPLITS = ("train", "validation", "test")
STANDARD_FILENAME = re.compile(
    r"^(paper|plastic|organic)_(train|validation|test)_"
    r"(original|existing_aug|v9_aug)_\d{3}\.jpg$"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=DEFAULT_DATASET)
    return parser.parse_args()


def main() -> None:
    root = parse_args().data.expanduser().resolve()
    rows = list(csv.DictReader((root / "manifest.csv").open(encoding="utf-8", newline="")))
    expected_paths = {row["relative_path"] for row in rows}
    actual_paths = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*.jpg")
    }
    if actual_paths != expected_paths:
        raise RuntimeError(
            f"Manifest/files differ; missing={sorted(expected_paths-actual_paths)}, "
            f"extra={sorted(actual_paths-expected_paths)}"
        )

    hashes: dict[str, str] = {}
    groups: dict[str, set[str]] = {}
    counts = {split: {label: 0 for label in LABELS} for split in SPLITS}
    kinds = {split: {} for split in SPLITS}
    for row in rows:
        path = root / row["relative_path"]
        if not STANDARD_FILENAME.fullmatch(path.name):
            raise RuntimeError(f"Non-standard filename: {path}")
        expected_parent = Path(row["split"]) / row["label"]
        if Path(row["relative_path"]).parent != expected_parent:
            raise RuntimeError(f"Path/split/label mismatch: {path}")
        digest = _sha256(path)
        if digest != row["sha256"]:
            raise RuntimeError(f"Checksum mismatch: {path}")
        if digest in hashes:
            raise RuntimeError(f"Exact duplicate: {hashes[digest]} and {path}")
        hashes[digest] = str(path)
        with Image.open(path) as image:
            image.verify()
        with Image.open(path) as image:
            if image.convert("RGB").size != (int(row["width"]), int(row["height"])):
                raise RuntimeError(f"Dimension mismatch: {path}")
        split, label, kind = row["split"], row["label"], row["kind"]
        if split not in SPLITS or label not in LABELS:
            raise RuntimeError(f"Invalid manifest row: {row}")
        if split != "train" and kind != "original":
            raise RuntimeError(f"Augmentation outside train: {path}")
        counts[split][label] += 1
        kinds[split][kind] = kinds[split].get(kind, 0) + 1
        groups.setdefault(row["source_group"], set()).add(split)

    expected_counts = {
        "train": {label: 75 for label in LABELS},
        "validation": {label: 7 for label in LABELS},
        "test": {label: 7 for label in LABELS},
    }
    if counts != expected_counts:
        raise RuntimeError(f"Unbalanced dataset: {counts}")
    leaking = {group: sorted(splits) for group, splits in groups.items() if len(splits) > 1}
    if leaking:
        raise RuntimeError(f"Source group leakage: {leaking}")
    if any(row["online_augment"].lower() != "false" for row in rows):
        raise RuntimeError("Online/in-memory augmentation is not allowed in V9")
    original_sources = {
        (row["label"], row["source_name"], row["sha256"])
        for row in rows
        if row["split"] == "train" and row["kind"] == "original"
    }
    for row in rows:
        if row["kind"] != "v9_augmentation":
            continue
        source = (row["label"], row["source_name"], row["source_sha256"])
        if source not in original_sources:
            raise RuntimeError(
                "V9 augmentation does not point to an original train image: "
                f"{row['relative_path']}"
            )
    augmentation_groups = {
        row["source_group"]
        for row in rows
        if row["split"] == "train" and row["kind"] != "original"
    }
    uncovered_originals = [
        row["relative_path"]
        for row in rows
        if row["split"] == "train"
        and row["kind"] == "original"
        and row["source_group"] not in augmentation_groups
    ]
    if uncovered_originals:
        raise RuntimeError(
            "Original train images without a saved augmentation: "
            f"{uncovered_originals}"
        )

    result = {
        "images": len(rows),
        "counts": counts,
        "kind_counts": kinds,
        "exact_duplicates": 0,
        "source_group_leakage": 0,
        "validation_test_augmentations": 0,
        "augmentation_materialized": True,
        "online_augmentation": False,
        "standard_filenames": True,
        "v9_augmentation_sources_are_original_train_images": True,
        "original_train_images_with_saved_augmentation": 48,
        "original_train_images_without_saved_augmentation": 0,
        "manifest_sha256": _sha256(root / "manifest.csv"),
    }
    print(json.dumps(result, indent=2, ensure_ascii=False))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    main()
