"""Materialize labeled ESP edge-case augmentations into the V10 train split.

The source directory is ``V10/data/<label>``.  Every eligible source is copied
to the train split and receives the same set of deterministic, physically saved
variants.  A source already assigned to validation/test is deliberately skipped
to prevent source leakage.
"""

from __future__ import annotations

from collections import Counter
import csv
from datetime import datetime, timezone
import hashlib
from io import BytesIO
import json
from pathlib import Path
import shutil

import numpy as np
from PIL import Image, ImageEnhance, ImageFilter, ImageOps, ImageStat

from V10.config import CLASS_NAMES, CLASS_TO_INDEX, DATASET_DIR, SPLITS, V10_DIR
from V10.merge_datasets import MANIFEST_FIELDS


SOURCE_DIR = V10_DIR / "data"
ORIGIN_DATASET = "v10_labeled_esp_data"
KIND_ORIGINAL = "esp_data_original"
KIND_AUGMENTED = "esp_data_augmentation"
SEED = 1010
OUTPUT_SIZE = (320, 240)
SUPPORTED_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
VARIANT_NAMES = (
    "resize_lowres",
    "rotate_left",
    "rotate_right",
    "jpeg_quality_20",
    "gaussian_blur",
    "sensor_noise",
    "color_warm",
    "color_cool",
    "color_desaturated",
    "light_bright",
    "light_dark",
    "edge_dark_blur_noise",
)


def main() -> None:
    root = DATASET_DIR.resolve()
    source_root = SOURCE_DIR.resolve()
    manifest_path = root / "manifest.csv"
    if not source_root.is_dir() or not manifest_path.is_file():
        raise FileNotFoundError("V10 source data or dataset manifest is missing")
    if root == source_root or root not in (root / "train").parents:
        raise RuntimeError("Unsafe V10 augmentation paths")

    existing_rows = list(
        csv.DictReader(manifest_path.open(encoding="utf-8", newline=""))
    )
    old_generated = [
        row for row in existing_rows if row.get("origin_dataset") == ORIGIN_DATASET
    ]
    base_rows = [
        row for row in existing_rows if row.get("origin_dataset") != ORIGIN_DATASET
    ]
    _remove_previous_outputs(root, old_generated)

    backup = root / "manifest_before_data_augmentation.csv"
    if not backup.exists():
        shutil.copy2(manifest_path, backup)
    stats_path = root / "stats.json"
    stats_backup = root / "stats_before_data_augmentation.json"
    if stats_path.is_file() and not stats_backup.exists():
        shutil.copy2(stats_path, stats_backup)

    rows = [_normalize_row(row) for row in base_rows]
    sources = _discover_sources(source_root)
    added: list[dict[str, str]] = []
    skipped: list[dict[str, object]] = []
    for label, source in sources:
        source_hash = _sha256(source)
        related = [
            row
            for row in base_rows
            if row.get("sha256") == source_hash
            or row.get("source_sha256") == source_hash
        ]
        held_out = sorted({row["split"] for row in related if row["split"] != "train"})
        if held_out:
            skipped.append({
                "source": source.relative_to(V10_DIR).as_posix(),
                "label": label,
                "sha256": source_hash,
                "reason": "source already belongs to held-out split",
                "held_out_splits": held_out,
                "matched_paths": [row["relative_path"] for row in related],
            })
            continue

        existing_train = next(
            (
                row
                for row in related
                if row["split"] == "train" and row.get("sha256") == source_hash
            ),
            None,
        )
        group = (
            existing_train["source_group"]
            if existing_train
            else f"{ORIGIN_DATASET}/{label}/{source.stem}"
        )
        source_rel = source.relative_to(V10_DIR).as_posix()
        if existing_train is None:
            destination_rel = Path("train") / label / f"v10data_{source.stem}_original.jpg"
            destination = root / destination_rel
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            original_row = _row(
                destination=destination,
                root=root,
                label=label,
                kind=KIND_ORIGINAL,
                source_rel=source_rel,
                source_name=source.stem,
                source_group=group,
                augmentation="original",
                source_hash=source_hash,
            )
            rows.append(original_row)
            added.append(original_row)

        with Image.open(source) as opened:
            image = ImageOps.exif_transpose(opened).convert("RGB")
        if image.size != OUTPUT_SIZE:
            image = ImageOps.fit(image, OUTPUT_SIZE, method=Image.Resampling.LANCZOS)
        for variant_name in VARIANT_NAMES:
            variant = _augment(image, variant_name, _variant_seed(source_hash, variant_name))
            destination_rel = (
                Path("train") / label / f"v10data_{source.stem}_{variant_name}.jpg"
            )
            destination = root / destination_rel
            _save_jpeg(variant, destination)
            row = _row(
                destination=destination,
                root=root,
                label=label,
                kind=KIND_AUGMENTED,
                source_rel=source_rel,
                source_name=source.stem,
                source_group=group,
                augmentation=variant_name,
                source_hash=source_hash,
            )
            rows.append(row)
            added.append(row)

    rows.sort(
        key=lambda row: (
            SPLITS.index(row["split"]),
            CLASS_TO_INDEX[row["label"]],
            row["relative_path"],
        )
    )
    _audit(root, rows)
    _write_manifest(manifest_path, rows)
    result = _build_stats(rows, sources, added, skipped, manifest_path)
    stats_path.write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    report_path = root / "DATA_AUGMENTATION_REPORT.md"
    report_path.write_text(_render_report(result), encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))


def _discover_sources(root: Path) -> list[tuple[str, Path]]:
    sources: list[tuple[str, Path]] = []
    for label in CLASS_NAMES:
        folder = root / label
        if not folder.is_dir():
            raise FileNotFoundError(f"Missing labeled source folder: {folder}")
        for path in sorted(folder.iterdir()):
            if path.is_file() and path.suffix.lower() in SUPPORTED_SUFFIXES:
                sources.append((label, path.resolve()))
    if not sources:
        raise ValueError("No labeled V10/data images found")
    return sources


def _augment(image: Image.Image, name: str, seed: int) -> Image.Image:
    rng = np.random.default_rng(seed)
    if name == "resize_lowres":
        return image.resize((96, 72), Image.Resampling.BILINEAR).resize(
            OUTPUT_SIZE, Image.Resampling.NEAREST
        )
    if name in {"rotate_left", "rotate_right"}:
        angle = -7.0 if name == "rotate_left" else 7.0
        fill = tuple(int(round(value)) for value in ImageStat.Stat(image).median)
        return image.rotate(
            angle, resample=Image.Resampling.BILINEAR, expand=False, fillcolor=fill
        )
    if name == "jpeg_quality_20":
        buffer = BytesIO()
        image.save(buffer, format="JPEG", quality=20, optimize=False)
        buffer.seek(0)
        with Image.open(buffer) as decoded:
            return decoded.convert("RGB").copy()
    if name == "gaussian_blur":
        return image.filter(ImageFilter.GaussianBlur(radius=1.6))
    if name == "sensor_noise":
        return _noise(image, rng, sigma=13.0)
    if name == "color_warm":
        pixels = np.asarray(image, dtype=np.float32)
        pixels *= np.asarray([1.24, 1.02, 0.76], dtype=np.float32)
        return _from_array(pixels)
    if name == "color_cool":
        pixels = np.asarray(image, dtype=np.float32)
        pixels *= np.asarray([0.76, 1.02, 1.24], dtype=np.float32)
        return _from_array(pixels)
    if name == "color_desaturated":
        return ImageEnhance.Color(image).enhance(0.22)
    if name == "light_bright":
        bright = ImageEnhance.Brightness(image).enhance(1.55)
        return ImageEnhance.Contrast(bright).enhance(0.88)
    if name == "light_dark":
        dark = ImageEnhance.Brightness(image).enhance(0.52)
        return ImageEnhance.Contrast(dark).enhance(1.12)
    if name == "edge_dark_blur_noise":
        edge = ImageEnhance.Brightness(image).enhance(0.62)
        edge = edge.filter(ImageFilter.GaussianBlur(radius=1.1))
        edge = _noise(edge, rng, sigma=9.0)
        buffer = BytesIO()
        edge.save(buffer, format="JPEG", quality=28, optimize=False)
        buffer.seek(0)
        with Image.open(buffer) as decoded:
            return decoded.convert("RGB").copy()
    raise ValueError(f"Unknown augmentation: {name}")


def _noise(image: Image.Image, rng: np.random.Generator, sigma: float) -> Image.Image:
    pixels = np.asarray(image, dtype=np.float32)
    return _from_array(pixels + rng.normal(0.0, sigma, pixels.shape))


def _from_array(pixels: np.ndarray) -> Image.Image:
    return Image.fromarray(np.clip(np.rint(pixels), 0, 255).astype(np.uint8), "RGB")


def _save_jpeg(image: Image.Image, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    image.convert("RGB").save(
        temporary, format="JPEG", quality=92, subsampling=2, optimize=False
    )
    temporary.replace(destination)


def _row(
    *,
    destination: Path,
    root: Path,
    label: str,
    kind: str,
    source_rel: str,
    source_name: str,
    source_group: str,
    augmentation: str,
    source_hash: str,
) -> dict[str, str]:
    with Image.open(destination) as image:
        width, height = image.size
    return {
        "relative_path": destination.relative_to(root).as_posix(),
        "split": "train",
        "label": label,
        "label_id": str(CLASS_TO_INDEX[label]),
        "kind": kind,
        "source_relative_path": source_rel,
        "source_name": source_name,
        "source_group": source_group,
        "visual_group": "labeled_esp_edge_case",
        "augmentation": augmentation,
        "online_augment": "False",
        "sha256": _sha256(destination),
        "source_sha256": source_hash,
        "width": str(width),
        "height": str(height),
        "origin_dataset": ORIGIN_DATASET,
    }


def _normalize_row(row: dict[str, str]) -> dict[str, str]:
    return {field: row.get(field, "") for field in MANIFEST_FIELDS}


def _remove_previous_outputs(root: Path, rows: list[dict[str, str]]) -> None:
    train_root = (root / "train").resolve()
    for row in rows:
        path = (root / row["relative_path"]).resolve()
        if train_root not in path.parents or not path.name.startswith("v10data_"):
            raise RuntimeError(f"Refusing to remove unexpected augmentation path: {path}")
        if path.exists():
            path.unlink()


def _audit(root: Path, rows: list[dict[str, str]]) -> None:
    hashes: dict[str, str] = {}
    groups: dict[str, set[str]] = {}
    counts = {split: Counter() for split in SPLITS}
    for row in rows:
        path = root / row["relative_path"]
        digest = _sha256(path)
        if digest != row["sha256"]:
            raise ValueError(f"Checksum mismatch: {path}")
        if digest in hashes:
            raise ValueError(f"Exact duplicate: {hashes[digest]} and {path}")
        hashes[digest] = str(path)
        groups.setdefault(row["source_group"], set()).add(row["split"])
        counts[row["split"]][row["label"]] += 1
        if row["split"] != "train" and row["kind"] != "original":
            raise ValueError(f"Augmentation outside train: {path}")
    leaking = {group: splits for group, splits in groups.items() if len(splits) > 1}
    if leaking:
        raise ValueError(f"Source-group leakage: {leaking}")
    for split in SPLITS:
        if any(counts[split][label] == 0 for label in CLASS_NAMES):
            raise ValueError(f"Empty class in {split}: {dict(counts[split])}")
    for split in ("validation", "test"):
        if len({counts[split][label] for label in CLASS_NAMES}) != 1:
            raise ValueError(f"Held-out split is not balanced: {dict(counts[split])}")


def _write_manifest(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=MANIFEST_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _build_stats(rows, sources, added, skipped, manifest_path: Path) -> dict:
    counts = {
        split: {
            label: sum(row["split"] == split and row["label"] == label for row in rows)
            for label in CLASS_NAMES
        }
        for split in SPLITS
    }
    return {
        "schema_version": 3,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "purpose": "V10 combined dataset plus saved labeled-ESP edge-case augmentation",
        "counts": counts,
        "total": len(rows),
        "origin_counts": dict(Counter(row["origin_dataset"] for row in rows)),
        "kind_counts": dict(Counter(row["kind"] for row in rows)),
        "augmentation_counts": dict(
            Counter(row["augmentation"] for row in added if row["kind"] == KIND_AUGMENTED)
        ),
        "source_images_found": len(sources),
        "source_images_used": len({row["source_sha256"] for row in added}),
        "source_images_skipped": skipped,
        "new_files_added": len(added),
        "new_originals_added": sum(row["kind"] == KIND_ORIGINAL for row in added),
        "new_augmentations_added": sum(row["kind"] == KIND_AUGMENTED for row in added),
        "saved_output_size": [OUTPUT_SIZE[0], OUTPUT_SIZE[1]],
        "variant_names": list(VARIANT_NAMES),
        "exact_duplicates": 0,
        "source_group_leakage": 0,
        "validation_test_unchanged": True,
        "manifest_sha256": _sha256(manifest_path),
    }


def _render_report(stats: dict) -> str:
    counts = stats["counts"]
    skipped = stats["source_images_skipped"]
    skipped_lines = "\n".join(
        f"- `{item['source']}`: {item['reason']} ({', '.join(item['held_out_splits'])})."
        for item in skipped
    ) or "- None."
    variants = "\n".join(f"- `{name}`" for name in stats["variant_names"])
    return f"""# V10 labeled ESP data augmentation report

All generated files are physically saved under `dataset_prepared/train/<label>`.
Validation and test were not augmented or changed.

| Split | paper | plastic | organic | Total |
|---|---:|---:|---:|---:|
| train | {counts['train']['paper']} | {counts['train']['plastic']} | {counts['train']['organic']} | {sum(counts['train'].values())} |
| validation | {counts['validation']['paper']} | {counts['validation']['plastic']} | {counts['validation']['organic']} | {sum(counts['validation'].values())} |
| test | {counts['test']['paper']} | {counts['test']['plastic']} | {counts['test']['organic']} | {sum(counts['test'].values())} |

- Source images found: {stats['source_images_found']}.
- Source images used: {stats['source_images_used']}.
- New originals: {stats['new_originals_added']}.
- New saved augmentations: {stats['new_augmentations_added']}.
- Saved dimensions: {stats['saved_output_size'][0]}x{stats['saved_output_size'][1]}.
- Exact duplicate files: 0.
- Source-group leakage: 0.

## Saved variants

{variants}

## Skipped leakage risks

{skipped_lines}
"""


def _variant_seed(source_hash: str, variant: str) -> int:
    digest = hashlib.sha256(f"{SEED}:{source_hash}:{variant}".encode()).digest()
    return int.from_bytes(digest[:8], "big")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    main()
