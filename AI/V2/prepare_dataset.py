"""Build leakage-safe train/validation/test views from augmented AI/DATASET."""

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
V2_DIR = Path(__file__).resolve().parent
DEFAULT_SOURCE = AI_DIR / "DATASET"
DEFAULT_OUTPUT = V2_DIR / "dataset_augmented"
LABELS = ("paper", "plastic", "organic")
SPLITS = ("train", "validation", "test")
IMAGE_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png"})
GENERATED_PATTERN = re.compile(r"^(?P<stem>.+)__aug_v2_(?P<index>\d{2})\.jpg$")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--internal-validation-ratio", type=float, default=0.20)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    summary = prepare_dataset(
        source=args.source,
        output=args.out,
        internal_validation_ratio=args.internal_validation_ratio,
        seed=args.seed,
        force=args.force,
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))


def prepare_dataset(
    *,
    source: str | Path,
    output: str | Path,
    internal_validation_ratio: float,
    seed: int,
    force: bool,
) -> dict:
    source_root = Path(source).expanduser().resolve()
    output_root = Path(output).expanduser().resolve()
    if not 0.0 < internal_validation_ratio < 0.5:
        raise ValueError("internal-validation-ratio must be between 0 and 0.5")
    if source_root == output_root or source_root in output_root.parents:
        raise ValueError("Prepared output cannot be inside the source dataset")

    train_originals, variants = _scan_training_source(source_root)
    external_test = _scan_external_validation(source_root)
    group_split = _split_original_groups(
        train_originals,
        validation_ratio=internal_validation_ratio,
        seed=seed,
    )

    if output_root.exists():
        if not force:
            raise FileExistsError(f"Output exists; pass --force: {output_root}")
        _safe_remove_prepared(output_root)
    temporary = output_root.with_name(f".{output_root.name}.tmp")
    if temporary.exists():
        _safe_remove_prepared(temporary)
    for split in SPLITS:
        for label in LABELS:
            (temporary / split / label).mkdir(parents=True, exist_ok=True)

    lineage_rows: list[dict[str, str | int]] = []
    try:
        for label in LABELS:
            for original in group_split["train"][label]:
                copied = _copy_image(original, temporary / "train" / label)
                lineage_rows.append(
                    _lineage_row(source_root, copied, original, "train", label, "original")
                )
                for variant in variants[label][original.stem]:
                    copied_variant = _copy_image(variant, temporary / "train" / label)
                    lineage_rows.append(
                        _lineage_row(
                            source_root,
                            copied_variant,
                            original,
                            "train",
                            label,
                            "augmentation",
                        )
                    )

            for original in group_split["validation"][label]:
                copied = _copy_image(original, temporary / "test" / label)
                lineage_rows.append(
                    _lineage_row(
                        source_root,
                        copied,
                        original,
                        "test",
                        label,
                        "original",
                    )
                )

            for original in external_test[label]:
                copied = _copy_image(original, temporary / "validation" / label)
                lineage_rows.append(
                    _lineage_row(
                        source_root,
                        copied,
                        original,
                        "validation",
                        label,
                        "original",
                    )
                )

        _write_lineage(temporary / "lineage.csv", lineage_rows)
        summary = _summary(
            source_root,
            output_root,
            train_originals,
            variants,
            external_test,
            group_split,
            lineage_rows,
            internal_validation_ratio,
            seed,
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
    return summary


def _scan_training_source(
    root: Path,
) -> tuple[dict[str, list[Path]], dict[str, dict[str, list[Path]]]]:
    originals: dict[str, list[Path]] = {}
    variants: dict[str, dict[str, list[Path]]] = {}
    for label in LABELS:
        class_dir = root / "train" / label
        if not class_dir.is_dir():
            raise FileNotFoundError(f"Missing training class directory: {class_dir}")
        images = sorted(
            path
            for path in class_dir.iterdir()
            if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
        )
        originals[label] = [
            path for path in images if GENERATED_PATTERN.fullmatch(path.name) is None
        ]
        variants[label] = {path.stem: [] for path in originals[label]}
        for path in images:
            match = GENERATED_PATTERN.fullmatch(path.name)
            if match is None:
                continue
            source_stem = match.group("stem")
            if source_stem not in variants[label]:
                raise ValueError(f"Augmentation has no source original: {path}")
            variants[label][source_stem].append(path)
        for original in originals[label]:
            if not variants[label][original.stem]:
                raise ValueError(f"Training original has no direct augmentation: {original}")
            variants[label][original.stem].sort()
    return originals, variants


def _scan_external_validation(root: Path) -> dict[str, list[Path]]:
    result: dict[str, list[Path]] = {}
    for label in LABELS:
        class_dir = root / "validation" / label
        if not class_dir.is_dir():
            raise FileNotFoundError(f"Missing validation class directory: {class_dir}")
        result[label] = sorted(
            path
            for path in class_dir.iterdir()
            if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
        )
        if not result[label]:
            raise ValueError(f"External validation class is empty: {class_dir}")
        if any(GENERATED_PATTERN.fullmatch(path.name) for path in result[label]):
            raise ValueError("AI/DATASET/validation must contain original images only")
    return result


def _split_original_groups(
    originals: dict[str, list[Path]],
    *,
    validation_ratio: float,
    seed: int,
) -> dict[str, dict[str, list[Path]]]:
    result = {
        "train": {label: [] for label in LABELS},
        "validation": {label: [] for label in LABELS},
    }
    for label_index, label in enumerate(LABELS):
        paths = list(originals[label])
        random.Random(seed + 1009 * label_index).shuffle(paths)
        validation_count = max(1, round(len(paths) * validation_ratio))
        if validation_count >= len(paths):
            raise ValueError(f"Not enough training originals for class '{label}'")
        result["validation"][label] = sorted(paths[:validation_count])
        result["train"][label] = sorted(paths[validation_count:])
    return result


def _copy_image(source: Path, destination_dir: Path) -> Path:
    destination = destination_dir / source.name
    shutil.copy2(source, destination)
    return destination


def _lineage_row(
    source_root: Path,
    copied: Path,
    original: Path,
    prepared_split: str,
    label: str,
    kind: str,
) -> dict[str, str | int]:
    return {
        "prepared_relative_path": copied.relative_to(copied.parents[2]).as_posix(),
        "prepared_split": prepared_split,
        "label": label,
        "kind": kind,
        "source_relative_path": (
            original.with_name(copied.name).relative_to(source_root).as_posix()
            if kind == "augmentation"
            else original.relative_to(source_root).as_posix()
        ),
        "original_relative_path": original.relative_to(source_root).as_posix(),
    }


def _write_lineage(path: Path, rows: list[dict[str, str | int]]) -> None:
    fieldnames = [
        "prepared_relative_path",
        "prepared_split",
        "label",
        "kind",
        "source_relative_path",
        "original_relative_path",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _summary(
    source: Path,
    output: Path,
    train_originals: dict[str, list[Path]],
    variants: dict[str, dict[str, list[Path]]],
    external_test: dict[str, list[Path]],
    group_split: dict[str, dict[str, list[Path]]],
    rows: list[dict[str, str | int]],
    validation_ratio: float,
    seed: int,
) -> dict:
    prepared_counts = {
        split: {
            label: sum(
                row["prepared_split"] == split and row["label"] == label for row in rows
            )
            for label in LABELS
        }
        for split in SPLITS
    }
    return {
        "source": str(source),
        "output": str(output),
        "seed": seed,
        "labels": list(LABELS),
        "internal_validation_ratio": validation_ratio,
        "source_train_original_counts": {
            label: len(train_originals[label]) for label in LABELS
        },
        "source_train_augmentation_counts": {
            label: sum(len(items) for items in variants[label].values())
            for label in LABELS
        },
        "source_external_validation_counts": {
            label: len(external_test[label]) for label in LABELS
        },
        "prepared_original_split_counts": {
            "train": {
                label: len(group_split["train"][label]) for label in LABELS
            },
            "validation": {
                label: len(external_test[label]) for label in LABELS
            },
            "test": {
                label: len(group_split["validation"][label]) for label in LABELS
            },
        },
        "prepared_counts": prepared_counts,
        "prepared_total": len(rows),
        "leakage_control": (
            "Augmented variants follow their source original into train; external "
            "validation and internal test contain originals only."
        ),
        "validation_semantics": (
            "AI/DATASET/validation is used for checkpoint selection and contains "
            "all original validation samples."
        ),
        "test_semantics": (
            "Internal holdout of AI/DATASET/train originals; their augmentations "
            "are excluded from training."
        ),
    }


def _safe_remove_prepared(path: Path) -> None:
    resolved = path.resolve()
    if resolved.parent != V2_DIR.resolve() or resolved.name not in {
        "dataset_augmented",
        ".dataset_augmented.tmp",
    }:
        raise RuntimeError(f"Refusing to remove unexpected path: {resolved}")
    shutil.rmtree(resolved)


if __name__ == "__main__":
    main()
