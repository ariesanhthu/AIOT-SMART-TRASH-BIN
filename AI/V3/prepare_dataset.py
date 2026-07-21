"""Create leakage-safe V3 train/validation/test splits from AI/DATASET."""

from __future__ import annotations

import argparse
import csv
import json
import os
from pathlib import Path
import random
import re
import shutil


AI_DIR = Path(__file__).resolve().parents[1]
V3_DIR = Path(__file__).resolve().parent
DEFAULT_SOURCE = AI_DIR / "DATASET"
DEFAULT_OUTPUT = V3_DIR / "dataset_prepared"
LABELS = ("paper", "plastic", "organic")
SPLITS = ("train", "validation", "test")
IMAGE_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png"})
AUGMENTED_PATTERN = re.compile(r"^(?P<stem>.+)__aug_v2_(?P<index>\d{2})\.jpg$")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--test-ratio", type=float, default=0.20)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    summary = prepare_dataset(
        source=args.source,
        output=args.out,
        test_ratio=args.test_ratio,
        seed=args.seed,
        force=args.force,
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))


def prepare_dataset(
    *, source: str | Path, output: str | Path, test_ratio: float, seed: int, force: bool
) -> dict:
    source_root = Path(source).expanduser().resolve()
    output_root = Path(output).expanduser().resolve()
    if not 0.0 < test_ratio < 0.5:
        raise ValueError("test-ratio must be between 0 and 0.5")
    if source_root == output_root or source_root in output_root.parents:
        raise ValueError("Prepared output cannot be inside the source dataset")

    originals, variants = _scan_training_source(source_root)
    external_validation = _scan_external_validation(source_root)
    grouped = _split_original_groups(originals, test_ratio=test_ratio, seed=seed)

    if output_root.exists():
        if not force:
            raise FileExistsError(f"Output exists; pass --force: {output_root}")
        _safe_remove(output_root)
    temporary = output_root.with_name(f".{output_root.name}.tmp")
    if temporary.exists():
        _safe_remove(temporary)
    for split in SPLITS:
        for label in LABELS:
            (temporary / split / label).mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, str]] = []
    try:
        for label in LABELS:
            for original in grouped["train"][label]:
                _copy_and_record(source_root, temporary, original, original, "train", label, "original", rows)
                for variant in variants[label][original.stem]:
                    _copy_and_record(source_root, temporary, variant, original, "train", label, "augmentation", rows)
            for original in grouped["test"][label]:
                _copy_and_record(source_root, temporary, original, original, "test", label, "original", rows)
            for original in external_validation[label]:
                _copy_and_record(source_root, temporary, original, original, "validation", label, "original", rows)

        _write_lineage(temporary / "lineage.csv", rows)
        summary = _build_summary(
            source_root, output_root, originals, variants, external_validation,
            grouped, rows, test_ratio, seed,
        )
        (temporary / "stats.json").write_text(
            json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        os.replace(temporary, output_root)
    except Exception:
        if temporary.exists():
            _safe_remove(temporary)
        raise
    return summary


def _scan_training_source(root: Path):
    originals: dict[str, list[Path]] = {}
    variants: dict[str, dict[str, list[Path]]] = {}
    for label in LABELS:
        class_dir = root / "train" / label
        if not class_dir.is_dir():
            raise FileNotFoundError(f"Missing training class directory: {class_dir}")
        images = sorted(
            path for path in class_dir.iterdir()
            if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
        )
        originals[label] = [path for path in images if AUGMENTED_PATTERN.fullmatch(path.name) is None]
        variants[label] = {path.stem: [] for path in originals[label]}
        for path in images:
            match = AUGMENTED_PATTERN.fullmatch(path.name)
            if match is None:
                continue
            source_stem = match.group("stem")
            if source_stem not in variants[label]:
                raise ValueError(f"Augmentation has no source original: {path}")
            variants[label][source_stem].append(path)
        for original in originals[label]:
            if not variants[label][original.stem]:
                raise ValueError(f"Training original has no augmentation: {original}")
            variants[label][original.stem].sort()
    return originals, variants


def _scan_external_validation(root: Path) -> dict[str, list[Path]]:
    result: dict[str, list[Path]] = {}
    for label in LABELS:
        class_dir = root / "validation" / label
        if not class_dir.is_dir():
            raise FileNotFoundError(f"Missing validation class directory: {class_dir}")
        result[label] = sorted(
            path for path in class_dir.iterdir()
            if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
        )
        if not result[label]:
            raise ValueError(f"Validation class is empty: {class_dir}")
        if any(AUGMENTED_PATTERN.fullmatch(path.name) for path in result[label]):
            raise ValueError("AI/DATASET/validation must contain original images only")
    return result


def _split_original_groups(originals: dict[str, list[Path]], *, test_ratio: float, seed: int):
    result = {"train": {label: [] for label in LABELS}, "test": {label: [] for label in LABELS}}
    for label_index, label in enumerate(LABELS):
        paths = list(originals[label])
        random.Random(seed + 1009 * label_index).shuffle(paths)
        test_count = max(1, round(len(paths) * test_ratio))
        if test_count >= len(paths):
            raise ValueError(f"Not enough originals for class '{label}'")
        result["test"][label] = sorted(paths[:test_count])
        result["train"][label] = sorted(paths[test_count:])
    return result


def _copy_and_record(
    source_root: Path, temporary: Path, source: Path, original: Path,
    split: str, label: str, kind: str, rows: list[dict[str, str]],
) -> None:
    destination = temporary / split / label / source.name
    shutil.copy2(source, destination)
    rows.append({
        "prepared_relative_path": destination.relative_to(temporary).as_posix(),
        "prepared_split": split,
        "label": label,
        "kind": kind,
        "source_relative_path": source.relative_to(source_root).as_posix(),
        "original_relative_path": original.relative_to(source_root).as_posix(),
    })


def _write_lineage(path: Path, rows: list[dict[str, str]]) -> None:
    fieldnames = [
        "prepared_relative_path", "prepared_split", "label", "kind",
        "source_relative_path", "original_relative_path",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _build_summary(source, output, originals, variants, external_validation, grouped, rows, test_ratio, seed):
    prepared_counts = {
        split: {
            label: sum(row["prepared_split"] == split and row["label"] == label for row in rows)
            for label in LABELS
        }
        for split in SPLITS
    }
    return {
        "source": str(source),
        "output": str(output),
        "seed": seed,
        "labels": list(LABELS),
        "test_ratio": test_ratio,
        "source_train_original_counts": {label: len(originals[label]) for label in LABELS},
        "source_train_augmentation_counts": {
            label: sum(len(items) for items in variants[label].values()) for label in LABELS
        },
        "source_validation_original_counts": {
            label: len(external_validation[label]) for label in LABELS
        },
        "prepared_original_split_counts": {
            "train": {label: len(grouped["train"][label]) for label in LABELS},
            "validation": {label: len(external_validation[label]) for label in LABELS},
            "test": {label: len(grouped["test"][label]) for label in LABELS},
        },
        "prepared_counts": prepared_counts,
        "prepared_total": len(rows),
        "leakage_control": (
            "An original and all of its augmented variants stay in train together; "
            "validation and test contain original images only."
        ),
        "validation_semantics": "AI/DATASET/validation is used only for checkpoint selection.",
        "test_semantics": (
            "Independent grouped holdout from AI/DATASET/train; its augmentations are excluded."
        ),
    }


def _safe_remove(path: Path) -> None:
    resolved = path.resolve()
    expected_parent = V3_DIR.resolve()
    if resolved.parent != expected_parent or resolved.name not in {
        "dataset_prepared", ".dataset_prepared.tmp"
    }:
        raise RuntimeError(f"Refusing to remove unexpected path: {resolved}")
    shutil.rmtree(resolved)


if __name__ == "__main__":
    main()

