"""Build the leakage-safe V5 four-class dataset from canonical sources.

The three physical-bin classes are copied from ``DATASET-V1-FULL``. Cardboard
and metal are added as ``other`` while preserving TrashNet's official
train/validation/test split. No validation or test image is augmented.
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

from PIL import Image

from V5.runtime import LABELS


V5_DIR = Path(__file__).resolve().parent
AI_DIR = V5_DIR.parent
DEFAULT_CANONICAL = AI_DIR / "DATASET-V1-FULL"
DEFAULT_TRASHNET_DATA = AI_DIR / "trashnet" / "data"
DEFAULT_OUTPUT = V5_DIR / "dataset_prepared"
SPLITS = ("train", "validation", "test")
PHYSICAL_LABELS = LABELS[:-1]
CLASS_TO_INDEX = {label: index for index, label in enumerate(LABELS)}
TRASHNET_MANIFESTS = {
    "train": "one-indexed-files-notrash_train.txt",
    "validation": "one-indexed-files-notrash_val.txt",
    "test": "one-indexed-files-notrash_test.txt",
}
OTHER_CLASS_IDS = {3: "cardboard", 5: "metal"}
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
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--canonical", type=Path, default=DEFAULT_CANONICAL)
    parser.add_argument("--trashnet-data", type=Path, default=DEFAULT_TRASHNET_DATA)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    summary = prepare_dataset(
        canonical=args.canonical,
        trashnet_data=args.trashnet_data,
        output=args.out,
        seed=args.seed,
        force=args.force,
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))


def prepare_dataset(
    *,
    canonical: str | Path,
    trashnet_data: str | Path,
    output: str | Path,
    seed: int,
    force: bool,
) -> dict:
    canonical_root = Path(canonical).expanduser().resolve()
    trashnet_data_root = Path(trashnet_data).expanduser().resolve()
    output_root = Path(output).expanduser().resolve()
    _validate_target(output_root)
    canonical_rows = _read_canonical_manifest(canonical_root)
    trashnet_image_root = _find_trashnet_image_root(trashnet_data_root)
    other_sources = _read_other_split(trashnet_data_root, trashnet_image_root)

    if output_root.exists() and not force:
        raise FileExistsError(f"Output exists; pass --force: {output_root}")
    staging = output_root.parent / f".{output_root.name}.staging-{uuid.uuid4().hex}"
    backup = output_root.parent / f".{output_root.name}.backup"
    _validate_temporary(staging, output_root.parent)
    _validate_temporary(backup, output_root.parent)
    if staging.exists():
        _safe_remove(staging, output_root.parent)

    rows: list[dict[str, str | int]] = []
    output_hashes: dict[str, str] = {}
    try:
        for split in SPLITS:
            for label in LABELS:
                (staging / split / label).mkdir(parents=True, exist_ok=False)

        for source_row in canonical_rows:
            split = source_row["split"]
            label = source_row["label"]
            relative = Path(source_row["relative_path"])
            source = canonical_root.joinpath(*relative.parts)
            destination = staging / split / label / source.name
            source_hash = _sha256_file(source)
            if source_hash != source_row["output_sha256"]:
                raise RuntimeError(f"Canonical source hash changed: {source}")
            shutil.copy2(source, destination)
            _register_hash(output_hashes, source_hash, destination, staging)
            rows.append(
                {
                    "relative_path": destination.relative_to(staging).as_posix(),
                    "split": split,
                    "label": label,
                    "label_id": CLASS_TO_INDEX[label],
                    "source": str(source.resolve()),
                    "source_split": f"canonical_{split}",
                    "source_sha256": source_hash,
                    "output_sha256": source_hash,
                    "width": int(source_row["width"]),
                    "height": int(source_row["height"]),
                }
            )

        for split in SPLITS:
            for origin, source in other_sources[split]:
                destination = staging / split / "other" / source.name
                source_hash = _sha256_file(source)
                shutil.copy2(source, destination)
                output_hash = _sha256_file(destination)
                if output_hash != source_hash:
                    raise RuntimeError(f"Copy integrity check failed: {source}")
                _register_hash(output_hashes, output_hash, destination, staging)
                with Image.open(destination) as image:
                    width, height = image.size
                rows.append(
                    {
                        "relative_path": destination.relative_to(staging).as_posix(),
                        "split": split,
                        "label": "other",
                        "label_id": CLASS_TO_INDEX["other"],
                        "source": str(source.resolve()),
                        "source_split": f"trashnet_{split}_{origin}",
                        "source_sha256": source_hash,
                        "output_sha256": output_hash,
                        "width": width,
                        "height": height,
                    }
                )

        rows.sort(
            key=lambda row: (
                SPLITS.index(str(row["split"])),
                int(row["label_id"]),
                str(row["relative_path"]),
            )
        )
        _write_manifest(staging / "manifest.csv", rows)
        dataset_sha256 = _sha256_file(staging / "manifest.csv")
        counts = _counts(rows)
        other_counts = {
            split: {
                origin: sum(item_origin == origin for item_origin, _ in other_sources[split])
                for origin in OTHER_CLASS_IDS.values()
            }
            for split in SPLITS
        }
        max_train_count = max(counts["train"][label] for label in LABELS)
        summary = {
            "schema_version": 1,
            "created_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            "seed": seed,
            "labels": list(LABELS),
            "class_to_index": CLASS_TO_INDEX,
            "canonical_source": str(canonical_root),
            "canonical_source_sha256": _sha256_file(canonical_root / "manifest.csv"),
            "trashnet_data": str(trashnet_data_root),
            "output": str(output_root),
            "counts": counts,
            "prepared_counts": {
                split: {label: counts[split][label] for label in LABELS}
                for split in SPLITS
            },
            "prepared_total": len(rows),
            "dataset_sha256": dataset_sha256,
            "other_source_counts": other_counts,
            "training_balance": {
                "strategy": "exact round-robin class sampling at training time",
                "effective_samples_per_class_per_epoch": max_train_count,
                "effective_total_per_epoch": max_train_count * len(LABELS),
                "materialized_augmentation": False,
            },
            "augmentation_policy": (
                "Online train-only geometric, exposure, white-balance, shadow, "
                "blur/noise, low-resolution and RGB565 simulation; clean "
                "validation/test remain unchanged."
            ),
            "leakage_control": (
                "All physical classes retain DATASET-V1-FULL splits; cardboard and "
                "metal retain official TrashNet splits; no validation/test augmentation."
            ),
        }
        (staging / "stats.json").write_text(
            json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        _validate_staging(staging, rows, dataset_sha256)
        _install(staging, output_root, backup, force)
    except BaseException:
        if staging.exists():
            _safe_remove(staging, output_root.parent)
        raise
    return summary


def _read_canonical_manifest(root: Path) -> list[dict[str, str]]:
    manifest = root / "manifest.csv"
    if not manifest.is_file():
        raise FileNotFoundError(f"Canonical manifest not found: {manifest}")
    rows: list[dict[str, str]] = []
    with manifest.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"relative_path", "split", "label", "output_sha256", "width", "height"}
        missing = required - set(reader.fieldnames or ())
        if missing:
            raise ValueError(f"Canonical manifest missing columns: {sorted(missing)}")
        for row in reader:
            if row["split"] not in SPLITS or row["label"] not in PHYSICAL_LABELS:
                raise ValueError(f"Unexpected canonical split/label: {row}")
            rows.append(row)
    if not rows:
        raise ValueError("Canonical manifest is empty")
    return rows


def _find_trashnet_image_root(data: Path) -> Path:
    for candidate in (
        data / "dataset-resized" / "dataset-resized",
        data / "dataset-resized",
        data,
    ):
        if all((candidate / origin).is_dir() for origin in OTHER_CLASS_IDS.values()):
            return candidate.resolve()
    raise FileNotFoundError(f"Cannot find TrashNet cardboard/metal under {data}")


def _read_other_split(
    data: Path, image_root: Path
) -> dict[str, list[tuple[str, Path]]]:
    result: dict[str, list[tuple[str, Path]]] = {split: [] for split in SPLITS}
    seen: set[str] = set()
    for split, manifest_name in TRASHNET_MANIFESTS.items():
        manifest = data / manifest_name
        if not manifest.is_file():
            raise FileNotFoundError(f"TrashNet split manifest not found: {manifest}")
        for line_number, raw in enumerate(
            manifest.read_text(encoding="utf-8").splitlines(), start=1
        ):
            fields = raw.strip().split()
            if not fields:
                continue
            if len(fields) != 2:
                raise ValueError(f"Malformed {manifest}:{line_number}: {raw!r}")
            name, raw_class_id = fields
            origin = OTHER_CLASS_IDS.get(int(raw_class_id))
            if origin is None:
                continue
            if name in seen:
                raise ValueError(f"TrashNet image occurs in multiple splits: {name}")
            seen.add(name)
            source = (image_root / origin / name).resolve()
            if not source.is_file():
                raise FileNotFoundError(f"TrashNet image is missing: {source}")
            result[split].append((origin, source))
    for split in SPLITS:
        result[split].sort(key=lambda item: item[1].name)
        if not result[split]:
            raise ValueError(f"No other-class images found for split {split}")
    return result


def _write_manifest(path: Path, rows: list[dict[str, str | int]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=MANIFEST_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


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


def _register_hash(
    seen: dict[str, str], digest: str, path: Path, root: Path
) -> None:
    relative = path.relative_to(root).as_posix()
    duplicate = seen.get(digest)
    if duplicate is not None:
        raise ValueError(f"Duplicate image content across V5 dataset: {duplicate}, {relative}")
    seen[digest] = relative


def _validate_staging(
    root: Path, rows: list[dict[str, str | int]], dataset_sha256: str
) -> None:
    if _sha256_file(root / "manifest.csv") != dataset_sha256:
        raise RuntimeError("V5 manifest changed during validation")
    indexed = {str(row["relative_path"]) for row in rows}
    discovered = {
        path.relative_to(root).as_posix()
        for split in SPLITS
        for label in LABELS
        for path in (root / split / label).glob("*")
        if path.is_file() and path.suffix.lower() in {".jpg", ".jpeg", ".png"}
    }
    if indexed != discovered:
        raise RuntimeError("V5 manifest and dataset files differ")


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


def _validate_target(path: Path) -> None:
    if path.parent != V5_DIR.resolve() or path.name != "dataset_prepared":
        raise ValueError(f"V5 dataset output must be {DEFAULT_OUTPUT.resolve()}: {path}")
    if path.is_symlink():
        raise ValueError(f"Refusing to replace symlink: {path}")


def _validate_temporary(path: Path, expected_parent: Path) -> None:
    if path.parent.resolve() != expected_parent.resolve() or not path.name.startswith("."):
        raise ValueError(f"Unsafe temporary path: {path}")


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


if __name__ == "__main__":
    main()
