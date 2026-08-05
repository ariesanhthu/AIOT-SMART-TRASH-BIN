"""Persist every V9 training augmentation and disable in-memory augmentation.

The script is idempotent: it compares the desired per-source variant counts in
``prepare_dataset.NEW_AUGMENTATIONS`` with ``manifest.csv`` and creates only
missing files. Augmentation sources must be original train images.
"""

from __future__ import annotations

import csv
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import uuid

from PIL import Image

from V9.prepare_dataset import (
    DEFAULT_DATASET,
    LABELS,
    MANIFEST_FIELDS,
    NEW_AUGMENTATIONS,
    SPLITS,
    _safe_remove,
    _save_photometric_augmentation,
    _sha256,
    _validate_temporary,
    _variant_seed,
)


SEED = 9


def main() -> None:
    root = DEFAULT_DATASET.resolve()
    rows = list(csv.DictReader((root / "manifest.csv").open(encoding="utf-8", newline="")))
    staging = root.parent / f".{root.name}.materialized-{uuid.uuid4().hex}"
    backup = root.parent / f".{root.name}.backup-{uuid.uuid4().hex}"
    _validate_temporary(staging, root.parent)
    _validate_temporary(backup, root.parent)
    shutil.copytree(root, staging)
    added = []
    removed = []
    try:
        for label in LABELS:
            v9_numbers = [
                int(Path(row["relative_path"]).stem.rsplit("_", 1)[-1])
                for row in rows
                if row["split"] == "train"
                and row["label"] == label
                and row["kind"] == "v9_augmentation"
            ]
            v9_counter = max(v9_numbers, default=0)
            for source_name, desired_count in NEW_AUGMENTATIONS[label]:
                originals = [
                    row for row in rows
                    if row["split"] == "train"
                    and row["label"] == label
                    and row["kind"] == "original"
                    and row["source_name"] == source_name
                ]
                if len(originals) != 1:
                    raise ValueError(
                        f"Expected one original source for {label}/{source_name}, "
                        f"got {len(originals)}"
                    )
                source_row = originals[0]
                existing_rows = sorted(
                    (
                        row for row in rows
                        if row["label"] == label
                        and row["kind"] == "v9_augmentation"
                        and row["source_name"] == source_name
                    ),
                    key=lambda row: row["relative_path"],
                )
                for obsolete in existing_rows[desired_count:]:
                    obsolete_path = staging / obsolete["relative_path"]
                    obsolete_path.unlink()
                    rows.remove(obsolete)
                    removed.append(obsolete["relative_path"])
                existing = sum(
                    row["label"] == label
                    and row["kind"] == "v9_augmentation"
                    and row["source_name"] == source_name
                    for row in rows
                )
                source_path = root / source_row["relative_path"]
                for variant in range(existing + 1, desired_count + 1):
                    v9_counter += 1
                    filename = f"{label}_train_v9_aug_{v9_counter:03d}.jpg"
                    destination = staging / "train" / label / filename
                    variant_seed = _variant_seed(
                        SEED, source_row["sha256"], variant
                    )
                    _save_photometric_augmentation(source_path, destination, variant_seed)
                    with Image.open(destination) as image:
                        width, height = image.size
                    row = {
                        "relative_path": destination.relative_to(staging).as_posix(),
                        "split": "train",
                        "label": label,
                        "label_id": source_row["label_id"],
                        "kind": "v9_augmentation",
                        "source_relative_path": source_row["source_relative_path"],
                        "source_name": source_name,
                        "source_group": source_row["source_group"],
                        "visual_group": source_row["visual_group"],
                        "online_augment": "False",
                        "sha256": _sha256(destination),
                        "source_sha256": source_row["sha256"],
                        "width": width,
                        "height": height,
                    }
                    rows.append(row)
                    added.append(row["relative_path"])
            if sum(
                row["split"] == "train" and row["label"] == label for row in rows
            ) != 75:
                raise ValueError(f"Materialized train count is not 75 for {label}")

        for row in rows:
            row["online_augment"] = "False"
        _validate(rows, staging)
        _write_manifest(staging / "manifest.csv", rows)
        stats_path = staging / "stats.json"
        stats = json.loads(stats_path.read_text(encoding="utf-8"))
        _update_stats(stats, rows, staging / "manifest.csv")
        stats_path.write_text(
            json.dumps(stats, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        os.replace(root, backup)
        try:
            os.replace(staging, root)
        except BaseException:
            os.replace(backup, root)
            raise
        _safe_remove(backup, root.parent)
    except BaseException:
        if staging.exists():
            _safe_remove(staging, root.parent)
        if backup.exists() and not root.exists():
            os.replace(backup, root)
        raise
    print(json.dumps({
        "added": len(added),
        "removed": len(removed),
        "materialized_v9_total": sum(row["kind"] == "v9_augmentation" for row in rows),
        "train_per_class": 75,
        "online_augmentation": False,
    }, indent=2))


def _validate(rows: list[dict], root: Path) -> None:
    counts = {
        split: {
            label: sum(row["split"] == split and row["label"] == label for row in rows)
            for label in LABELS
        }
        for split in SPLITS
    }
    expected = {
        "train": {label: 75 for label in LABELS},
        "validation": {label: 7 for label in LABELS},
        "test": {label: 7 for label in LABELS},
    }
    if counts != expected:
        raise ValueError(f"Unexpected materialized counts: {counts}")
    hashes = {}
    groups = {}
    for row in rows:
        path = root / row["relative_path"]
        digest = _sha256(path)
        if digest != row["sha256"]:
            raise ValueError(f"Checksum mismatch: {path}")
        if digest in hashes:
            raise ValueError(f"Exact duplicate: {hashes[digest]} and {path}")
        hashes[digest] = str(path)
        groups.setdefault(row["source_group"], set()).add(row["split"])
        if row["online_augment"].lower() != "false":
            raise ValueError(f"Online augmentation remains enabled: {path}")
        if row["split"] != "train" and row["kind"] != "original":
            raise ValueError(f"Augmentation outside train: {path}")
    leaking = {group: splits for group, splits in groups.items() if len(splits) > 1}
    if leaking:
        raise ValueError(f"Source-group leakage: {leaking}")


def _write_manifest(path: Path, rows: list[dict]) -> None:
    rows.sort(key=lambda row: (SPLITS.index(row["split"]), row["label"], row["relative_path"]))
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=MANIFEST_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _update_stats(stats: dict, rows: list[dict], manifest: Path) -> None:
    # Older prepared copies used an ambiguous key. These counts describe the
    # reviewed files before adding V9 variants, not the final physical files.
    if "visual_distribution" in stats:
        stats["pre_v9_reviewed_visual_distribution"] = stats.pop(
            "visual_distribution"
        )
    counts = {
        split: {
            label: sum(row["split"] == split and row["label"] == label for row in rows)
            for label in LABELS
        }
        for split in SPLITS
    }
    total = len(rows)
    stats.update({
        "updated_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "counts": counts,
        "total": total,
        "split_percent": {
            split: round(100.0 * sum(counts[split].values()) / total, 4)
            for split in SPLITS
        },
        "class_total": {
            label: sum(counts[split][label] for split in SPLITS) for label in LABELS
        },
        "kind_counts": {
            split: {
                kind: sum(row["split"] == split and row["kind"] == kind for row in rows)
                for kind in ("original", "existing_augmentation", "v9_augmentation")
            }
            for split in SPLITS
        },
        "unique_source_images_preserved": 176,
        "new_v9_augmentations": sum(row["kind"] == "v9_augmentation" for row in rows),
        "online_augmentation_eligible": 0,
        "augmentation_materialized": True,
        "dataset_manifest_sha256": _sha256(manifest),
    })


if __name__ == "__main__":
    main()
