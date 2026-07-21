"""Build the canonical, leakage-free three-class dataset.

Paper and plastic retain the official TrashNet train/validation/test split.
Organic images are deduplicated by decoded RGB content before deterministic
sampling.  The result is written through a staging directory so an interrupted
run cannot leave a half-built DATASET directory.
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
import shutil
import uuid

from PIL import Image, ImageOps, UnidentifiedImageError

try:
    from .config import AI_DIR, CLASS_TO_INDEX, LABELS, REPOSITORY_DIR, SPLITS
except ImportError:
    from config import (  # type: ignore
        AI_DIR,
        CLASS_TO_INDEX,
        LABELS,
        REPOSITORY_DIR,
        SPLITS,
    )


IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}
TRASHNET_CLASS_IDS = {2: "paper", 4: "plastic"}
TRASHNET_MANIFESTS = {
    "train": "one-indexed-files-notrash_train.txt",
    "validation": "one-indexed-files-notrash_val.txt",
    "test": "one-indexed-files-notrash_test.txt",
}
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


@dataclass(frozen=True)
class SourceImage:
    path: Path
    source_split: str
    source_sha256: str
    content_sha256: str


@dataclass(frozen=True)
class OutputRow:
    relative_path: str
    split: str
    label: str
    label_id: int
    source: str
    source_split: str
    source_sha256: str
    output_sha256: str
    width: int
    height: int


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trashnet-data", default=str(AI_DIR / "trashnet" / "data"))
    parser.add_argument("--organic-train", default=None)
    parser.add_argument("--organic-test", default=None)
    parser.add_argument("--out", default=str(AI_DIR / "DATASET"))
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--jpeg-quality", type=int, default=95)
    parser.add_argument(
        "--force",
        action="store_true",
        help="Replace an existing output directory after staging succeeds.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not 80 <= args.jpeg_quality <= 100:
        raise ValueError("--jpeg-quality must be between 80 and 100")

    trashnet_data = Path(args.trashnet_data).expanduser().resolve()
    target = Path(args.out).expanduser().resolve()
    _assert_safe_target(target)
    if target.exists() and not args.force:
        raise FileExistsError(f"Output already exists; pass --force to replace it: {target}")

    trashnet_root = _find_trashnet_image_root(trashnet_data)
    legacy_root = target if target.is_dir() else None
    organic_train = _find_organic_source(
        args.organic_train,
        "train",
        legacy_root,
    )
    organic_test = _find_organic_source(
        args.organic_test,
        "test",
        legacy_root,
    )

    known_by_split = _read_trashnet_split(trashnet_data, trashnet_root)
    organic_targets = {
        split: len(known_by_split[split]["plastic"]) for split in SPLITS
    }

    print(f"Scanning and hashing organic train source: {organic_train}")
    organic_train_images = _scan_organic(organic_train, "official_train")
    print(f"Scanning and hashing organic test source: {organic_test}")
    organic_test_images = _scan_organic(organic_test, "official_test")

    unique_train, train_duplicate_count = _deduplicate(organic_train_images)
    train_content_hashes = {item.content_sha256 for item in unique_train}
    test_without_train = [
        item for item in organic_test_images if item.content_sha256 not in train_content_hashes
    ]
    cross_split_removed = len(organic_test_images) - len(test_without_train)
    unique_test, test_duplicate_count = _deduplicate(test_without_train)

    if len(unique_train) < organic_targets["train"]:
        raise RuntimeError(
            f"Not enough unique organic train images: {len(unique_train)} < "
            f"{organic_targets['train']}"
        )
    needed_eval = organic_targets["validation"] + organic_targets["test"]
    if len(unique_test) < needed_eval:
        raise RuntimeError(
            f"Not enough leakage-free organic test images: {len(unique_test)} < {needed_eval}"
        )

    ranked_train = _rank_candidates(unique_train, args.seed, "organic-train")
    ranked_eval = _rank_candidates(unique_test, args.seed, "organic-eval")

    staging = target.parent / f".{target.name}.staging-{uuid.uuid4().hex}"
    backup = target.parent / f".{target.name}.backup"
    _assert_safe_temporary(staging, target.parent)
    _assert_safe_temporary(backup, target.parent)
    if staging.exists():
        _remove_tree(staging, target.parent)
    staging.mkdir(parents=True)

    rows: list[OutputRow] = []
    output_hashes: set[str] = set()
    try:
        for split in SPLITS:
            for label in LABELS:
                (staging / split / label).mkdir(parents=True, exist_ok=False)

        for split in SPLITS:
            for label in ("paper", "plastic"):
                for source in known_by_split[split][label]:
                    rows.append(
                        _write_canonical_image(
                            source=source,
                            destination=staging / split / label / source.name,
                            root=staging,
                            split=split,
                            label=label,
                            source_split=f"trashnet_{split}",
                            jpeg_quality=args.jpeg_quality,
                            output_hashes=output_hashes,
                        )
                    )

        train_rows, _ = _write_ranked_organic(
            ranked_train,
            start=0,
            count=organic_targets["train"],
            split="train",
            staging=staging,
            jpeg_quality=args.jpeg_quality,
            output_hashes=output_hashes,
        )
        rows.extend(train_rows)

        validation_rows, next_index = _write_ranked_organic(
            ranked_eval,
            start=0,
            count=organic_targets["validation"],
            split="validation",
            staging=staging,
            jpeg_quality=args.jpeg_quality,
            output_hashes=output_hashes,
        )
        rows.extend(validation_rows)
        test_rows, _ = _write_ranked_organic(
            ranked_eval,
            start=next_index,
            count=organic_targets["test"],
            split="test",
            staging=staging,
            jpeg_quality=args.jpeg_quality,
            output_hashes=output_hashes,
        )
        rows.extend(test_rows)

        rows.sort(key=lambda row: (SPLITS.index(row.split), row.label_id, row.relative_path))
        manifest_path = staging / "manifest.csv"
        _write_manifest(manifest_path, rows)
        dataset_sha256 = _sha256_file(manifest_path)
        counts = _count_rows(rows)
        stats = {
            "schema_version": 1,
            "created_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            "seed": args.seed,
            "labels": list(LABELS),
            "class_to_index": CLASS_TO_INDEX,
            "counts": counts,
            "total": len(rows),
            "dataset_sha256": dataset_sha256,
            "canonical_format": {
                "encoding": "JPEG",
                "mode": "RGB",
                "quality": args.jpeg_quality,
                "exif_orientation": "applied_and_removed",
                "resize": "not_applied; performed by the model pipeline",
            },
            "sources": {
                "trashnet_data": _display_path(trashnet_data),
                "trashnet_images": _display_path(trashnet_root),
                "organic_train": _display_path(organic_train),
                "organic_test": _display_path(organic_test),
            },
            "organic_deduplication": {
                "train_candidates": len(organic_train_images),
                "test_candidates": len(organic_test_images),
                "train_duplicates_removed": train_duplicate_count,
                "test_duplicates_removed_after_cross_split_filter": test_duplicate_count,
                "test_images_matching_train_removed": cross_split_removed,
                "key": "sha256(width || height || decoded_exif_corrected_rgb_bytes)",
            },
        }
        (staging / "stats.json").write_text(
            json.dumps(stats, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        (staging / "README.md").write_text(
            _dataset_readme(counts, dataset_sha256, args.seed),
            encoding="utf-8",
            newline="\n",
        )

        _validate_staging(staging, rows, dataset_sha256)
        _install_staging(staging, target, backup, args.force)
    except BaseException:
        if staging.exists():
            _remove_tree(staging, target.parent)
        raise

    print(json.dumps(stats, indent=2, ensure_ascii=False))
    print(f"Canonical dataset installed at: {target}")


def _find_trashnet_image_root(data: Path) -> Path:
    candidates = (
        data / "dataset-resized" / "dataset-resized",
        data / "dataset-resized",
        data,
    )
    for candidate in candidates:
        if (candidate / "paper").is_dir() and (candidate / "plastic").is_dir():
            return candidate.resolve()
    raise FileNotFoundError(f"Cannot find TrashNet paper/plastic directories under {data}")


def _find_organic_source(
    explicit: str | None,
    split: str,
    legacy_root: Path | None,
) -> Path:
    folder = "TRAIN" if split == "train" else "TEST"
    legacy_folder = "Train" if split == "train" else "Test"
    candidates: list[Path] = []
    if explicit:
        candidates.append(Path(explicit).expanduser())
    if legacy_root is not None:
        candidates.append(legacy_root / legacy_folder / "O")
    candidates.extend(
        [
            AI_DIR / "archive" / "DATASET" / folder / "O",
            AI_DIR / "archive" / "DATASET" / "DATASET" / folder / "O",
        ]
    )
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved.is_dir():
            return resolved
    raise FileNotFoundError(
        f"Cannot find raw organic {split} source. Checked: "
        + ", ".join(str(path.resolve()) for path in candidates)
    )


def _read_trashnet_split(
    data: Path,
    image_root: Path,
) -> dict[str, dict[str, list[Path]]]:
    result = {
        split: {"paper": [], "plastic": []} for split in SPLITS
    }
    seen: set[str] = set()
    for split, manifest_name in TRASHNET_MANIFESTS.items():
        manifest = data / manifest_name
        if not manifest.is_file():
            raise FileNotFoundError(f"Missing TrashNet split manifest: {manifest}")
        for line_number, raw_line in enumerate(
            manifest.read_text(encoding="utf-8").splitlines(), start=1
        ):
            line = raw_line.strip()
            if not line:
                continue
            fields = line.split()
            if len(fields) != 2:
                raise ValueError(f"Malformed {manifest}:{line_number}: {raw_line!r}")
            name, raw_class_id = fields
            class_id = int(raw_class_id)
            label = TRASHNET_CLASS_IDS.get(class_id)
            if label is None:
                continue
            if name in seen:
                raise ValueError(f"TrashNet image occurs in multiple splits: {name}")
            seen.add(name)
            source = image_root / label / name
            if not source.is_file():
                raise FileNotFoundError(f"TrashNet manifest image is missing: {source}")
            result[split][label].append(source.resolve())

    for split in SPLITS:
        for label in ("paper", "plastic"):
            result[split][label].sort(key=lambda path: path.name)
            if not result[split][label]:
                raise RuntimeError(f"TrashNet split is empty: {split}/{label}")
    return result


def _scan_organic(root: Path, source_split: str) -> list[SourceImage]:
    paths = sorted(
        path.resolve()
        for path in root.rglob("*")
        if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES
    )
    if not paths:
        raise RuntimeError(f"Organic source contains no supported images: {root}")
    images: list[SourceImage] = []
    for index, path in enumerate(paths, start=1):
        source_sha = _sha256_file(path)
        try:
            with Image.open(path) as opened:
                rgb = ImageOps.exif_transpose(opened).convert("RGB")
                content_digest = hashlib.sha256()
                content_digest.update(rgb.width.to_bytes(4, "little"))
                content_digest.update(rgb.height.to_bytes(4, "little"))
                content_digest.update(rgb.tobytes())
        except (OSError, UnidentifiedImageError) as exc:
            raise ValueError(f"Cannot decode organic image {path}: {exc}") from exc
        images.append(
            SourceImage(path, source_split, source_sha, content_digest.hexdigest())
        )
        if index % 1000 == 0 or index == len(paths):
            print(f"  decoded {index}/{len(paths)}", flush=True)
    return images


def _deduplicate(images: list[SourceImage]) -> tuple[list[SourceImage], int]:
    canonical: dict[str, SourceImage] = {}
    for image in images:
        current = canonical.get(image.content_sha256)
        if current is None or image.path.as_posix() < current.path.as_posix():
            canonical[image.content_sha256] = image
    unique = sorted(canonical.values(), key=lambda item: item.path.as_posix())
    return unique, len(images) - len(unique)


def _rank_candidates(
    images: list[SourceImage], seed: int, namespace: str
) -> list[SourceImage]:
    def priority(item: SourceImage) -> str:
        payload = f"{namespace}\0{seed}\0{item.content_sha256}\0{item.path.name}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    return sorted(images, key=lambda item: (priority(item), item.path.as_posix()))


def _write_ranked_organic(
    ranked: list[SourceImage],
    *,
    start: int,
    count: int,
    split: str,
    staging: Path,
    jpeg_quality: int,
    output_hashes: set[str],
) -> tuple[list[OutputRow], int]:
    rows: list[OutputRow] = []
    index = start
    while len(rows) < count and index < len(ranked):
        source = ranked[index]
        index += 1
        destination = staging / split / "organic" / f"organic_{len(rows) + 1:04d}.jpg"
        try:
            row = _write_canonical_image(
                source=source.path,
                destination=destination,
                root=staging,
                split=split,
                label="organic",
                source_split=source.source_split,
                jpeg_quality=jpeg_quality,
                output_hashes=output_hashes,
                expected_source_sha256=source.source_sha256,
                allow_duplicate_output=False,
            )
        except DuplicateCanonicalImage:
            destination.unlink(missing_ok=True)
            continue
        rows.append(row)
    if len(rows) != count:
        raise RuntimeError(f"Could only write {len(rows)}/{count} unique organic {split} images")
    return rows, index


class DuplicateCanonicalImage(RuntimeError):
    pass


def _write_canonical_image(
    *,
    source: Path,
    destination: Path,
    root: Path,
    split: str,
    label: str,
    source_split: str,
    jpeg_quality: int,
    output_hashes: set[str],
    expected_source_sha256: str | None = None,
    allow_duplicate_output: bool = False,
) -> OutputRow:
    source_sha = _sha256_file(source)
    if expected_source_sha256 is not None and source_sha != expected_source_sha256:
        raise RuntimeError(f"Source changed while building dataset: {source}")
    try:
        with Image.open(source) as opened:
            rgb = ImageOps.exif_transpose(opened).convert("RGB")
            width, height = rgb.size
            rgb.save(
                destination,
                format="JPEG",
                quality=jpeg_quality,
                subsampling=0,
                optimize=False,
                progressive=False,
            )
    except (OSError, UnidentifiedImageError) as exc:
        raise ValueError(f"Cannot canonicalize image {source}: {exc}") from exc
    output_sha = _sha256_file(destination)
    if output_sha in output_hashes and not allow_duplicate_output:
        raise DuplicateCanonicalImage(f"Canonical output duplicates another image: {source}")
    if output_sha in output_hashes:
        raise RuntimeError(f"Canonical duplicate in required TrashNet split: {source}")
    output_hashes.add(output_sha)
    return OutputRow(
        relative_path=destination.relative_to(root).as_posix(),
        split=split,
        label=label,
        label_id=CLASS_TO_INDEX[label],
        source=_display_path(source),
        source_split=source_split,
        source_sha256=source_sha,
        output_sha256=output_sha,
        width=width,
        height=height,
    )


def _write_manifest(path: Path, rows: list[OutputRow]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=MANIFEST_FIELDS, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "relative_path": row.relative_path,
                    "split": row.split,
                    "label": row.label,
                    "label_id": row.label_id,
                    "source": row.source,
                    "source_split": row.source_split,
                    "source_sha256": row.source_sha256,
                    "output_sha256": row.output_sha256,
                    "width": row.width,
                    "height": row.height,
                }
            )


def _count_rows(rows: list[OutputRow]) -> dict[str, dict[str, int]]:
    counts: dict[str, dict[str, int]] = {}
    for split in SPLITS:
        split_counts = {
            label: sum(row.split == split and row.label == label for row in rows)
            for label in LABELS
        }
        split_counts["total"] = sum(split_counts.values())
        counts[split] = split_counts
    return counts


def _validate_staging(staging: Path, rows: list[OutputRow], dataset_sha256: str) -> None:
    if _sha256_file(staging / "manifest.csv") != dataset_sha256:
        raise RuntimeError("Manifest changed during dataset validation")
    seen_output_hashes: set[str] = set()
    for row in rows:
        path = staging.joinpath(*row.relative_path.split("/"))
        if not path.is_file() or _sha256_file(path) != row.output_sha256:
            raise RuntimeError(f"Output hash validation failed: {path}")
        if row.output_sha256 in seen_output_hashes:
            raise RuntimeError(f"Duplicate canonical output survived validation: {path}")
        seen_output_hashes.add(row.output_sha256)
        with Image.open(path) as image:
            image.load()
            if image.format != "JPEG" or image.mode != "RGB":
                raise RuntimeError(f"Non-canonical output image: {path}")
    discovered = {
        path.relative_to(staging).as_posix()
        for split in SPLITS
        for label in LABELS
        for path in (staging / split / label).glob("*.jpg")
    }
    indexed = {row.relative_path for row in rows}
    if discovered != indexed:
        raise RuntimeError("Dataset files and manifest rows do not match")


def _install_staging(staging: Path, target: Path, backup: Path, force: bool) -> None:
    if backup.exists():
        _remove_tree(backup, target.parent)
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
        _remove_tree(backup, target.parent)


def _assert_safe_target(target: Path) -> None:
    ai_root = AI_DIR.resolve()
    try:
        relative = target.relative_to(ai_root)
    except ValueError as exc:
        raise ValueError(f"Output must stay under {ai_root}: {target}") from exc
    if not relative.parts or target == ai_root or target.parent != ai_root:
        raise ValueError(f"Output must be a direct child of {ai_root}: {target}")
    if target.is_symlink():
        raise ValueError(f"Refusing to replace symlink output: {target}")


def _assert_safe_temporary(path: Path, parent: Path) -> None:
    resolved_parent = parent.resolve()
    if path.parent.resolve() != resolved_parent or not path.name.startswith("."):
        raise ValueError(f"Unsafe temporary path: {path}")


def _remove_tree(path: Path, expected_parent: Path) -> None:
    resolved = path.resolve()
    if resolved.parent != expected_parent.resolve() or not resolved.name.startswith("."):
        raise ValueError(f"Refusing recursive removal of unsafe path: {resolved}")
    shutil.rmtree(resolved)


def _sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _display_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(REPOSITORY_DIR.resolve()).as_posix()
    except ValueError:
        return resolved.as_posix()


def _dataset_readme(
    counts: dict[str, dict[str, int]], dataset_sha256: str, seed: int
) -> str:
    table = "\n".join(
        f"| {split} | {values['paper']} | {values['plastic']} | "
        f"{values['organic']} | {values['total']} |"
        for split, values in counts.items()
    )
    return f"""# Canonical three-class dataset

This directory is generated by `python -m src.prepare_dataset --force`.
Do not add images directly to a split without regenerating `manifest.csv`.

| Split | paper | plastic | organic | Total |
|---|---:|---:|---:|---:|
{table}

- Labels are fixed as `paper=0`, `plastic=1`, `organic=2`.
- Paper/plastic retain the official TrashNet split.
- Organic train images come only from the raw TRAIN source.
- Organic validation/test images come only from the raw TEST source after
  removing decoded-content hashes seen in TRAIN.
- Every output is an EXIF-corrected RGB JPEG; resize is deferred to training
  and firmware preprocessing.
- Selection seed: `{seed}`.
- Manifest SHA-256: `{dataset_sha256}`.
"""


if __name__ == "__main__":
    main()
