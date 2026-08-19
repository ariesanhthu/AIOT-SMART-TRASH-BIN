"""Rebuild the reviewed V9 dataset with balanced, leakage-safe splits.

This script is intentionally conservative: it only uses images already present
in ``AI/V9/dataset_prepared``. Exact duplicates are collapsed, every known V2
augmentation stays in train, and the validation/test assignments below are the
result of a visual review of every image rather than a filename slice.
"""

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
import uuid

import numpy as np
from PIL import Image, ImageEnhance, ImageOps


V9_DIR = Path(__file__).resolve().parent
DEFAULT_DATASET = V9_DIR / "dataset_prepared"
LABELS = ("paper", "plastic", "organic")
SPLITS = ("train", "validation", "test")
CLASS_TO_INDEX = {label: index for index, label in enumerate(LABELS)}
IMAGE_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png"})
OLD_AUGMENTATION = re.compile(r"^(?P<source>.+)__aug_v2_\d{2}$")

# V6 renamed V4 files to v4_<class>_<sha-prefix>. The values below recover
# their actual V2 source identity. This prevents augmenting an augmentation.
V4_LINEAGE = {
    "v4_paper_c181c1c138736cd4e9f9bffc": "paper_048",
    "v4_paper_c60cff60ecd71ff980a5921a": "paper_043__aug_v2_05",
    "v4_paper_c69d7f7a3f888135f4ea88c7": "paper_031__aug_v2_08",
    "v4_paper_c71d8eeda805285d3b65adcc": "paper_009",
    "v4_paper_c9a27b6690ad2bc9c0d108fa": "paper_040__aug_v2_06",
    "v4_plastic_07ca2504f8f62955d37b1de1": "plastic_007__aug_v2_08",
    "v4_plastic_0bbaa267affad6daf4b364c8": "plastic_002__aug_v2_03",
    "v4_plastic_0d141ec360175d25f115774e": "plastic_008",
    "v4_plastic_1f7ed4ad5065986e3219262b": "plastic_009__aug_v2_06",
    "v4_plastic_2e4aba0dbc630ef3a71f0ddb": "plastic_007__aug_v2_05",
    "v4_plastic_3a3c479b3539a02e4362299f": "plastic_004__aug_v2_03",
    "v4_plastic_4d5bd92723384ff9a55858b1": "plastic_009__aug_v2_05",
    "v4_plastic_5af8c58a37ddae081a0620c7": "plastic_007__aug_v2_09",
    "v4_plastic_5b648dbb2927744cf98a8e4b": "plastic_009__aug_v2_04",
    "v4_plastic_5dfb20110fb486442f1851a6": "plastic_004__aug_v2_02",
    "v4_plastic_6f3e40fe110b1817c9813f9b": "plastic_001__aug_v2_09",
    "v4_plastic_7ab9b575f43f9749a557beb7": "plastic_001__aug_v2_03",
    "v4_plastic_7c8bfc79fbfa23ccf2343572": "plastic_014__aug_v2_03",
}

# Manual holdouts chosen after reviewing all 188 files. Each split contains a
# mix of object sizes, counts and positions that also has analogues in train.
VALIDATION = {
    "paper": {
        "esp32-cam-2026-08-01T09-20-56-169Z",
        "esp32-cam-2026-08-01T09-21-08-060Z",
        "esp32-cam-2026-08-01T09-21-26-275Z",
        "esp32-cam-2026-08-01T09-21-32-945Z",
        "esp32-cam-2026-08-01T09-21-41-368Z",
        "esp32-cam-2026-08-01T09-21-48-763Z",
        "esp32-cam-2026-08-01T09-22-42-501Z",
    },
    "plastic": {
        "esp32-cam-2026-08-01T09-18-27-447Z",
        "esp32-cam-2026-08-01T09-18-35-939Z",
        "esp32-cam-2026-08-01T09-18-49-442Z",
        "esp32-cam-2026-08-01T09-19-22-225Z",
        "esp32-cam-2026-08-01T09-19-29-965Z",
        "esp32-cam-2026-08-01T09-19-34-536Z",
        "esp32-cam-2026-08-01T09-19-43-238Z",
    },
    "organic": {
        "esp32-cam-2026-08-01T09-23-38-834Z",
        "esp32-cam-2026-08-01T09-24-01-064Z",
        "esp32-cam-2026-08-01T09-24-19-364Z",
        "esp32-cam-2026-08-01T09-25-06-442Z",
        "esp32-cam-2026-08-01T09-25-15-394Z",
        "esp32-cam-2026-08-01T09-25-45-682Z",
        "esp32-cam-2026-08-01T09-26-13-328Z",
    },
}

TEST = {
    "paper": {
        "esp32-cam-2026-08-01T09-20-58-823Z",
        "esp32-cam-2026-08-01T09-21-17-077Z",
        "esp32-cam-2026-08-01T09-21-43-340Z",
        "esp32-cam-2026-08-01T09-21-49-767Z",
        "esp32-cam-2026-08-01T09-21-51-510Z",
        "esp32-cam-2026-08-01T09-22-44-117Z",
        "v4_paper_c71d8eeda805285d3b65adcc",
    },
    "plastic": {
        "esp32-cam-2026-08-01T09-18-11-451Z",
        "esp32-cam-2026-08-01T09-18-18-049Z",
        "esp32-cam-2026-08-01T09-18-50-193Z",
        "esp32-cam-2026-08-01T09-19-49-152Z",
        "esp32-cam-2026-08-01T09-20-01-299Z",
        "esp32-cam-2026-08-01T09-20-08-360Z",
        "esp32-cam-2026-08-01T09-20-14-018Z",
    },
    "organic": {
        "esp32-cam-2026-08-01T09-23-52-181Z",
        "esp32-cam-2026-08-01T09-24-26-277Z",
        "esp32-cam-2026-08-01T09-25-07-397Z",
        "esp32-cam-2026-08-01T09-25-16-967Z",
        "esp32-cam-2026-08-01T09-25-33-360Z",
        "esp32-cam-2026-08-01T09-26-02-308Z",
        "esp32-cam-2026-08-01T09-26-34-723Z",
    },
}

# Only reviewed original train captures are sources for V9 files; augmentation
# outputs are never augmented again. Counts are chosen so each train class has
# exactly 75 saved files. Every original train case without a stored variant
# receives at least one; selected sources receive additional photometric/noise
# variants to balance the classes without deleting unique inputs.
NEW_AUGMENTATIONS = {
    "paper": (
        ("esp32-cam-2026-08-01T09-20-57-593Z", 5),
        ("esp32-cam-2026-08-01T09-21-24-094Z", 6),
        ("esp32-cam-2026-08-01T09-21-33-812Z", 6),
        ("esp32-cam-2026-08-01T09-21-42-352Z", 6),
        ("esp32-cam-2026-08-01T09-21-50-789Z", 6),
        ("esp32-cam-2026-08-01T09-22-43-217Z", 5),
        ("v4_paper_c181c1c138736cd4e9f9bffc", 1),
    ),
    "plastic": (
        ("camera_plastic_21270466c954512fef8852ef", 1),
        ("camera_plastic_42bf63f8f4178ebcc50108ee", 1),
        ("camera_plastic_43a0bd2c3b192c8511726f69", 1),
        ("camera_plastic_49eed3b3c6942bf9809b38bb", 1),
        ("camera_plastic_6a96988ff82ed609e7d8eaf8", 1),
        ("camera_plastic_7d11f7973f60a22846f00611", 1),
        ("camera_plastic_ad8a8c8f63e854fb7b85f45e", 1),
        ("camera_plastic_bf4dca5a81e0fd325a9beb95", 1),
        ("camera_plastic_ed2238a3646e5789a015111d", 1),
        ("camera_plastic_ef2717566d8f1daf32e59a8d", 1),
        ("esp32-cam-2026-08-01T09-18-00-256Z", 1),
        ("esp32-cam-2026-08-01T09-18-01-210Z", 1),
        ("esp32-cam-2026-08-01T09-18-02-172Z", 1),
        ("esp32-cam-2026-08-01T09-18-08-932Z", 1),
        ("esp32-cam-2026-08-01T09-18-09-510Z", 1),
        ("esp32-cam-2026-08-01T09-18-10-482Z", 1),
        ("esp32-cam-2026-08-01T09-18-19-008Z", 1),
        ("esp32-cam-2026-08-01T09-18-19-765Z", 1),
        ("esp32-cam-2026-08-01T09-18-25-982Z", 1),
        ("esp32-cam-2026-08-01T09-18-28-587Z", 1),
        ("esp32-cam-2026-08-01T09-18-34-428Z", 1),
        ("esp32-cam-2026-08-01T09-18-35-112Z", 1),
        ("esp32-cam-2026-08-01T09-18-48-725Z", 1),
        ("esp32-cam-2026-08-01T09-18-51-779Z", 1),
        ("esp32-cam-2026-08-01T09-19-16-734Z", 1),
        ("esp32-cam-2026-08-01T09-20-15-163Z", 1),
        ("v4_plastic_0d141ec360175d25f115774e", 1),
    ),
    "organic": (
        ("esp32-cam-2026-08-01T09-23-33-165Z", 5),
        ("esp32-cam-2026-08-01T09-23-46-307Z", 5),
        ("esp32-cam-2026-08-01T09-23-59-242Z", 5),
        ("esp32-cam-2026-08-01T09-24-07-057Z", 5),
        ("esp32-cam-2026-08-01T09-24-14-272Z", 5),
        ("esp32-cam-2026-08-01T09-25-50-582Z", 4),
    ),
}

ORGANIC_OBJECT_COUNT = {
    "esp32-cam-2026-08-01T09-23-33-165Z": 5,
    "esp32-cam-2026-08-01T09-23-38-834Z": 4,
    "esp32-cam-2026-08-01T09-23-46-307Z": 4,
    "esp32-cam-2026-08-01T09-23-52-181Z": 2,
    "esp32-cam-2026-08-01T09-23-59-242Z": 2,
    "esp32-cam-2026-08-01T09-24-01-064Z": 2,
    "esp32-cam-2026-08-01T09-24-07-057Z": 3,
    "esp32-cam-2026-08-01T09-24-14-272Z": 1,
    "esp32-cam-2026-08-01T09-24-19-364Z": 1,
    "esp32-cam-2026-08-01T09-24-26-277Z": 2,
    "esp32-cam-2026-08-01T09-25-06-442Z": 2,
    "esp32-cam-2026-08-01T09-25-07-397Z": 2,
    "esp32-cam-2026-08-01T09-25-15-394Z": 3,
    "esp32-cam-2026-08-01T09-25-16-967Z": 3,
    "esp32-cam-2026-08-01T09-25-33-360Z": 4,
    "esp32-cam-2026-08-01T09-25-45-682Z": 1,
    "esp32-cam-2026-08-01T09-25-50-582Z": 1,
    "esp32-cam-2026-08-01T09-26-02-308Z": 1,
    "esp32-cam-2026-08-01T09-26-13-328Z": 1,
    "esp32-cam-2026-08-01T09-26-34-723Z": 1,
}

MANIFEST_FIELDS = (
    "relative_path", "split", "label", "label_id", "kind",
    "source_relative_path", "source_name", "source_group", "visual_group",
    "online_augment", "sha256", "source_sha256", "width", "height",
)


@dataclass(frozen=True)
class SourceImage:
    path: Path
    relative_path: str
    label: str
    name: str
    sha256: str
    width: int
    height: int
    kind: str
    source_group: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--seed", type=int, default=9)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    root = args.data.expanduser().resolve()
    if (root / "manifest.csv").is_file() and not args.force:
        raise FileExistsError(
            f"V9 dataset is already prepared: {root}. Use audit_dataset.py to verify it."
        )
    result = prepare_dataset(root, seed=args.seed)
    print(json.dumps(result, indent=2, ensure_ascii=False))


def prepare_dataset(root: Path, *, seed: int) -> dict:
    if root != DEFAULT_DATASET.resolve() or not root.is_dir():
        raise ValueError(f"V9 dataset must be {DEFAULT_DATASET.resolve()}")
    sources, duplicates = _scan_and_deduplicate(root)
    _validate_manual_assignments(sources)

    staging = root.parent / f".{root.name}.staging-{uuid.uuid4().hex}"
    backup = root.parent / f".{root.name}.backup-{uuid.uuid4().hex}"
    _validate_temporary(staging, root.parent)
    _validate_temporary(backup, root.parent)
    for split in SPLITS:
        for label in LABELS:
            (staging / split / label).mkdir(parents=True, exist_ok=False)

    rows: list[dict[str, str | int | bool]] = []
    source_to_row: dict[tuple[str, str], dict[str, str | int | bool]] = {}
    counters: dict[tuple[str, str, str], int] = {}
    try:
        for source in sorted(
            sources, key=lambda item: (item.label, item.source_group, item.name, item.sha256)
        ):
            split = _assigned_split(source)
            kind_name = "existing_aug" if source.kind == "existing_augmentation" else "original"
            key = (split, source.label, kind_name)
            counters[key] = counters.get(key, 0) + 1
            filename = (
                f"{source.label}_{split}_{kind_name}_{counters[key]:03d}.jpg"
            )
            destination = staging / split / source.label / filename
            shutil.copy2(source.path, destination)
            output_hash = _sha256(destination)
            if output_hash != source.sha256:
                raise RuntimeError(f"Copy verification failed: {source.path}")
            row: dict[str, str | int | bool] = {
                "relative_path": destination.relative_to(staging).as_posix(),
                "split": split,
                "label": source.label,
                "label_id": CLASS_TO_INDEX[source.label],
                "kind": source.kind,
                "source_relative_path": source.relative_path,
                "source_name": source.name,
                "source_group": source.source_group,
                "visual_group": _visual_group(source),
                "online_augment": False,
                "sha256": output_hash,
                "source_sha256": source.sha256,
                "width": source.width,
                "height": source.height,
            }
            rows.append(row)
            source_to_row[(source.label, source.name)] = row

        for label in LABELS:
            for source_name, variants in NEW_AUGMENTATIONS[label]:
                source = _find_source(sources, label, source_name)
                source_row = source_to_row[(label, source_name)]
                if source.kind != "original" or source_row["split"] != "train":
                    raise ValueError(f"Invalid V9 augmentation source: {source.path}")
                for variant in range(1, variants + 1):
                    key = ("train", label, "v9_aug")
                    counters[key] = counters.get(key, 0) + 1
                    filename = f"{label}_train_v9_aug_{counters[key]:03d}.jpg"
                    destination = staging / "train" / label / filename
                    variant_seed = _variant_seed(seed, source.sha256, variant)
                    _save_photometric_augmentation(source.path, destination, variant_seed)
                    with Image.open(destination) as image:
                        width, height = image.size
                    rows.append({
                        "relative_path": destination.relative_to(staging).as_posix(),
                        "split": "train",
                        "label": label,
                        "label_id": CLASS_TO_INDEX[label],
                        "kind": "v9_augmentation",
                        "source_relative_path": source.relative_path,
                        "source_name": source.name,
                        "source_group": source.source_group,
                        "visual_group": _visual_group(source),
                        "online_augment": False,
                        "sha256": _sha256(destination),
                        "source_sha256": source.sha256,
                        "width": width,
                        "height": height,
                    })

        for row in rows:
            row["online_augment"] = False

        _validate_rows(rows)
        _write_manifest(staging / "manifest.csv", rows)
        stats = _build_stats(root, rows, duplicates, seed)
        stats["dataset_manifest_sha256"] = _sha256(staging / "manifest.csv")
        (staging / "stats.json").write_text(
            json.dumps(stats, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        _install(staging, root, backup)
    except BaseException:
        if staging.exists():
            _safe_remove(staging, root.parent)
        if backup.exists() and not root.exists():
            os.replace(backup, root)
        raise
    return stats


def _scan_and_deduplicate(root: Path) -> tuple[list[SourceImage], list[dict]]:
    by_hash: dict[str, list[SourceImage]] = {}
    for split in SPLITS:
        for label in LABELS:
            class_dir = root / split / label
            if not class_dir.is_dir():
                raise FileNotFoundError(class_dir)
            for path in sorted(class_dir.iterdir()):
                if not path.is_file() or path.suffix.lower() not in IMAGE_EXTENSIONS:
                    continue
                with Image.open(path) as opened:
                    image = ImageOps.exif_transpose(opened).convert("RGB")
                    width, height = image.size
                    image.getpixel((0, 0))
                kind, group = _lineage(path.stem, label)
                item = SourceImage(
                    path=path.resolve(),
                    relative_path=path.relative_to(root).as_posix(),
                    label=label,
                    name=path.stem.replace(" copy", ""),
                    sha256=_sha256(path),
                    width=width,
                    height=height,
                    kind=kind,
                    source_group=f"{label}/{group}",
                )
                by_hash.setdefault(item.sha256, []).append(item)

    unique: list[SourceImage] = []
    duplicates: list[dict] = []
    for digest, items in sorted(by_hash.items()):
        labels = {item.label for item in items}
        if len(labels) != 1:
            raise ValueError(f"Same image has conflicting labels: {items}")
        chosen = sorted(items, key=_dedup_priority)[0]
        unique.append(chosen)
        for duplicate in items:
            if duplicate.path != chosen.path:
                duplicates.append({
                    "sha256": digest,
                    "kept": chosen.relative_path,
                    "removed": duplicate.relative_path,
                })
    return unique, duplicates


def _lineage(stem: str, label: str) -> tuple[str, str]:
    recovered = V4_LINEAGE.get(stem, stem)
    match = OLD_AUGMENTATION.fullmatch(recovered)
    if match is not None:
        return "existing_augmentation", match.group("source")
    match = OLD_AUGMENTATION.fullmatch(stem)
    if match is not None:
        return "existing_augmentation", match.group("source")
    if stem.startswith("v4_") and stem not in V4_LINEAGE:
        raise ValueError(f"Unknown V4 lineage: {stem}")
    return "original", recovered if stem.startswith("v4_") else stem


def _dedup_priority(item: SourceImage) -> tuple[int, int, str]:
    return (
        1 if " copy" in item.path.stem else 0,
        1 if item.path.stem.startswith("v4_") else 0,
        item.relative_path,
    )


def _assigned_split(source: SourceImage) -> str:
    if source.kind == "existing_augmentation":
        return "train"
    if source.name in VALIDATION[source.label]:
        return "validation"
    if source.name in TEST[source.label]:
        return "test"
    return "train"


def _validate_manual_assignments(sources: list[SourceImage]) -> None:
    for label in LABELS:
        available = {
            source.name for source in sources
            if source.label == label and source.kind == "original"
        }
        overlap = VALIDATION[label] & TEST[label]
        if overlap:
            raise ValueError(f"Validation/test assignment overlap: {overlap}")
        missing = (VALIDATION[label] | TEST[label]) - available
        if missing:
            raise ValueError(f"Missing reviewed {label} holdouts: {sorted(missing)}")
        if len(VALIDATION[label]) != 7 or len(TEST[label]) != 7:
            raise ValueError(f"Each {label} holdout must contain exactly seven images")


def _find_source(sources: list[SourceImage], label: str, name: str) -> SourceImage:
    matches = [source for source in sources if source.label == label and source.name == name]
    if len(matches) != 1:
        raise ValueError(f"Expected one source for {label}/{name}, got {len(matches)}")
    return matches[0]


def _visual_group(source: SourceImage) -> str:
    if source.label == "organic":
        if source.name in ORGANIC_OBJECT_COUNT:
            count = ORGANIC_OBJECT_COUNT[source.name]
            return "lime_1" if count == 1 else ("lime_2" if count == 2 else "lime_3_plus")
        if source.source_group.endswith(("organic_019", "organic_020")):
            return "rambutan"
        return "lime_legacy"
    if source.label == "plastic":
        return "plastic_bottle"
    if source.name.startswith("esp32-cam-"):
        return "paper_esp32_varied_pose"
    return "paper_legacy_varied_pose"


def _save_photometric_augmentation(source: Path, destination: Path, seed: int) -> None:
    rng = np.random.default_rng(seed)
    with Image.open(source) as opened:
        image = ImageOps.exif_transpose(opened).convert("RGB")

    # No geometric operation is used here. Resize/rescale belongs to the shared
    # train/evaluation/firmware preprocessing contract. These additions cover
    # sensor noise and warm/cool/mixed lighting only.
    gamma = float(rng.uniform(0.72, 1.38))
    exposure = float(rng.uniform(0.72, 1.32))
    contrast = float(rng.uniform(0.82, 1.22))
    pixels = np.asarray(image, dtype=np.float32) / 255.0
    pixels = np.power(np.clip(pixels, 0.0, 1.0), gamma) * exposure
    mean = pixels.mean(axis=(0, 1), keepdims=True)
    pixels = (pixels - mean) * contrast + mean
    channel_gain = rng.uniform(0.82, 1.20, size=(1, 1, 3)).astype(np.float32)
    pixels *= channel_gain
    noise_sigma = float(rng.uniform(2.0, 6.0)) / 255.0
    pixels += rng.normal(0.0, noise_sigma, size=pixels.shape).astype(np.float32)
    output = Image.fromarray(
        np.rint(np.clip(pixels, 0.0, 1.0) * 255.0).astype(np.uint8), "RGB"
    )
    output = ImageEnhance.Sharpness(output).enhance(float(rng.uniform(0.9, 1.1)))
    output.save(destination, format="JPEG", quality=95, optimize=True)


def _validate_rows(rows: list[dict[str, str | int | bool]]) -> None:
    hashes: dict[str, str] = {}
    for row in rows:
        digest = str(row["sha256"])
        if digest in hashes:
            raise ValueError(
                f"Prepared exact duplicate: {hashes[digest]} and {row['relative_path']}"
            )
        hashes[digest] = str(row["relative_path"])
        if row["split"] != "train" and row["kind"] != "original":
            raise ValueError(f"Augmentation outside train: {row['relative_path']}")
    counts = _counts(rows)
    expected = {
        "train": {label: 75 for label in LABELS},
        "validation": {label: 7 for label in LABELS},
        "test": {label: 7 for label in LABELS},
    }
    if counts != expected:
        raise ValueError(f"Unexpected V9 counts: {counts}; expected {expected}")
    group_splits: dict[str, set[str]] = {}
    for row in rows:
        group_splits.setdefault(str(row["source_group"]), set()).add(str(row["split"]))
    leaking = {group: splits for group, splits in group_splits.items() if len(splits) > 1}
    if leaking:
        raise ValueError(f"Source-group leakage detected: {leaking}")


def _build_stats(root: Path, rows: list[dict], duplicates: list[dict], seed: int) -> dict:
    counts = _counts(rows)
    kinds = {
        split: {
            kind: sum(row["split"] == split and row["kind"] == kind for row in rows)
            for kind in ("original", "existing_augmentation", "v9_augmentation")
        }
        for split in SPLITS
    }
    visual = {
        split: {
            label: {
                group: sum(
                    row["split"] == split
                    and row["label"] == label
                    and row["visual_group"] == group
                    for row in rows
                )
                for group in sorted({
                    str(row["visual_group"]) for row in rows if row["label"] == label
                })
            }
            for label in LABELS
        }
        for split in SPLITS
    }
    total = len(rows)
    return {
        "schema_version": 1,
        "created_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "source_root": str(root),
        "labels": list(LABELS),
        "class_to_index": CLASS_TO_INDEX,
        "seed": seed,
        "split_strategy": (
            "manual per-image visual review; balanced object count/size/position; "
            "all stored augmentations train-only; no chronological slicing"
        ),
        "counts": counts,
        "total": total,
        "split_percent": {
            split: round(100.0 * sum(counts[split].values()) / total, 4)
            for split in SPLITS
        },
        "class_total": {
            label: sum(counts[split][label] for split in SPLITS) for label in LABELS
        },
        "kind_counts": kinds,
        "pre_v9_reviewed_visual_distribution": visual,
        "exact_duplicates_removed": len(duplicates),
        "duplicate_resolution": duplicates,
        "unique_source_images_preserved": total - 91,
        "new_v9_augmentations": 91,
        "new_image_categories_added": 0,
        "validation_test_augmented": False,
        "source_group_leakage": 0,
        "exact_hash_leakage": 0,
        "online_augmentation_eligible": 0,
        "augmentation_materialized": True,
        "dataset_manifest_sha256": "",
        "limitation": (
            "All ESP32 captures still come from the same 2026-08-01 session; "
            "collect a later independent session before claiming deployment accuracy."
        ),
    }


def _counts(rows: list[dict]) -> dict[str, dict[str, int]]:
    return {
        split: {
            label: sum(row["split"] == split and row["label"] == label for row in rows)
            for label in LABELS
        }
        for split in SPLITS
    }


def _write_manifest(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=MANIFEST_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _install(staging: Path, target: Path, backup: Path) -> None:
    os.replace(target, backup)
    try:
        os.replace(staging, target)
    except BaseException:
        os.replace(backup, target)
        raise
    _safe_remove(backup, target.parent)


def _validate_temporary(path: Path, expected_parent: Path) -> None:
    if path.parent.resolve() != expected_parent.resolve() or not path.name.startswith("."):
        raise ValueError(f"Unsafe temporary directory: {path}")


def _safe_remove(path: Path, expected_parent: Path) -> None:
    resolved = path.resolve()
    if resolved.parent != expected_parent.resolve() or not resolved.name.startswith("."):
        raise ValueError(f"Refusing unsafe removal: {resolved}")
    shutil.rmtree(resolved)


def _variant_seed(seed: int, source_hash: str, variant: int) -> int:
    payload = f"{seed}\0{source_hash}\0{variant}".encode("ascii")
    return int.from_bytes(hashlib.sha256(payload).digest()[:8], "big")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    main()
