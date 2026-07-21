"""Materialize deterministic training augmentations directly in AI/DATASET/train."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import random
import re

import numpy as np
from PIL import Image, ImageEnhance, ImageFilter, ImageOps


AI_DIR = Path(__file__).resolve().parents[1]
DEFAULT_DATASET = AI_DIR / "DATASET"
LABELS = ("paper", "plastic", "organic")
IMAGE_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png"})
GENERATED_PATTERN = re.compile(r"^(?P<stem>.+)__aug_v2_(?P<index>\d{2})\.jpg$")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--augmentations-per-image", type=int, default=9)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    summary = augment_dataset(
        data_dir=args.data,
        augmentations_per_image=args.augmentations_per_image,
        seed=args.seed,
        force=args.force,
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))


def augment_dataset(
    *,
    data_dir: str | Path,
    augmentations_per_image: int,
    seed: int,
    force: bool,
) -> dict:
    root = Path(data_dir).expanduser().resolve()
    train_root = root / "train"
    validation_root = root / "validation"
    if augmentations_per_image < 1:
        raise ValueError("augmentations-per-image must be positive")
    for split_root in (train_root, validation_root):
        for label in LABELS:
            if not (split_root / label).is_dir():
                raise FileNotFoundError(f"Missing dataset directory: {split_root / label}")

    originals = {
        label: sorted(
            path
            for path in (train_root / label).iterdir()
            if path.is_file()
            and path.suffix.lower() in IMAGE_EXTENSIONS
            and GENERATED_PATTERN.fullmatch(path.name) is None
        )
        for label in LABELS
    }
    source_fingerprint = _source_fingerprint(root, originals)
    stats_path = root / "augmentation_stats.json"
    existing_generated = sorted(
        path
        for label in LABELS
        for path in (train_root / label).iterdir()
        if path.is_file() and GENERATED_PATTERN.fullmatch(path.name)
    )
    if existing_generated and not force:
        if stats_path.is_file():
            existing = json.loads(stats_path.read_text(encoding="utf-8"))
            if (
                existing.get("source_fingerprint") == source_fingerprint
                and existing.get("augmentations_per_image") == augmentations_per_image
                and existing.get("seed") == seed
                and existing.get("generated_total") == len(existing_generated)
            ):
                return existing
        raise FileExistsError(
            "Generated V2 images already exist but do not match the requested config; "
            "pass --force to rebuild only __aug_v2_ files."
        )
    if force:
        for path in existing_generated:
            _safe_unlink_generated(path, train_root)

    manifest_rows: list[dict[str, str | int]] = []
    for label in LABELS:
        for source_path in originals[label]:
            source_relative = source_path.relative_to(root).as_posix()
            source_sha256 = _sha256_file(source_path)
            for index in range(1, augmentations_per_image + 1):
                variant_seed = _variant_seed(seed, source_relative, index)
                output_name = f"{source_path.stem}__aug_v2_{index:02d}.jpg"
                output_path = source_path.with_name(output_name)
                with Image.open(source_path) as image:
                    augmented = _augment(image.convert("RGB"), variant_seed)
                    augmented.save(
                        output_path,
                        format="JPEG",
                        quality=92,
                        optimize=True,
                    )
                manifest_rows.append(
                    {
                        "relative_path": output_path.relative_to(root).as_posix(),
                        "label": label,
                        "source_relative_path": source_relative,
                        "source_sha256": source_sha256,
                        "variant_index": index,
                        "seed": variant_seed,
                        "output_sha256": _sha256_file(output_path),
                    }
                )

    manifest_path = root / "augmentation_manifest.csv"
    _write_manifest(manifest_path, manifest_rows)
    generated_counts = {
        label: sum(row["label"] == label for row in manifest_rows) for label in LABELS
    }
    validation_counts = {
        label: sum(
            path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
            for path in (validation_root / label).iterdir()
        )
        for label in LABELS
    }
    summary = {
        "dataset": str(root),
        "augmentation_location": str(train_root),
        "seed": seed,
        "augmentations_per_image": augmentations_per_image,
        "source_fingerprint": source_fingerprint,
        "train_original_counts": {
            label: len(originals[label]) for label in LABELS
        },
        "generated_counts": generated_counts,
        "generated_total": len(manifest_rows),
        "train_total_after_augmentation": sum(len(paths) for paths in originals.values())
        + len(manifest_rows),
        "validation_original_counts": validation_counts,
        "validation_augmented": False,
        "generated_name_pattern": "<source_stem>__aug_v2_<01..N>.jpg",
        "manifest": str(manifest_path),
    }
    stats_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return summary


def _augment(image: Image.Image, seed: int) -> Image.Image:
    rng = random.Random(seed)
    width, height = image.size
    fill = tuple(int(value) for value in np.asarray(image).reshape(-1, 3).mean(axis=0))
    if rng.random() < 0.5:
        image = ImageOps.mirror(image)

    scale = rng.uniform(0.90, 1.10)
    translate_x = rng.uniform(-0.08, 0.08) * width
    translate_y = rng.uniform(-0.08, 0.08) * height
    inverse_scale = 1.0 / scale
    affine = (
        inverse_scale,
        0.0,
        width * (1.0 - inverse_scale) / 2.0 - translate_x,
        0.0,
        inverse_scale,
        height * (1.0 - inverse_scale) / 2.0 - translate_y,
    )
    image = image.transform(
        image.size,
        Image.Transform.AFFINE,
        affine,
        resample=Image.Resampling.BILINEAR,
        fillcolor=fill,
    )
    image = image.rotate(
        rng.uniform(-15.0, 15.0),
        resample=Image.Resampling.BILINEAR,
        expand=False,
        fillcolor=fill,
    )
    image = ImageEnhance.Brightness(image).enhance(rng.uniform(0.82, 1.18))
    image = ImageEnhance.Contrast(image).enhance(rng.uniform(0.82, 1.18))
    image = ImageEnhance.Color(image).enhance(rng.uniform(0.90, 1.10))
    if rng.random() < 0.30:
        image = image.filter(ImageFilter.GaussianBlur(radius=rng.uniform(0.2, 0.8)))
    if rng.random() < 0.45:
        array = np.asarray(image, dtype=np.int16)
        noise_rng = np.random.default_rng(seed)
        noise = noise_rng.normal(0.0, rng.uniform(1.0, 4.0), size=array.shape)
        image = Image.fromarray(np.clip(array + noise, 0, 255).astype(np.uint8), "RGB")
    return image


def _safe_unlink_generated(path: Path, train_root: Path) -> None:
    resolved = path.resolve()
    if train_root.resolve() not in resolved.parents:
        raise RuntimeError(f"Refusing to remove outside train dataset: {resolved}")
    if GENERATED_PATTERN.fullmatch(resolved.name) is None:
        raise RuntimeError(f"Refusing to remove non-generated image: {resolved}")
    resolved.unlink()


def _source_fingerprint(root: Path, originals: dict[str, list[Path]]) -> str:
    digest = hashlib.sha256()
    for label in LABELS:
        for path in originals[label]:
            digest.update(path.relative_to(root).as_posix().encode("utf-8"))
            digest.update(b"\0")
            digest.update(_sha256_file(path).encode("ascii"))
            digest.update(b"\n")
    return digest.hexdigest()


def _variant_seed(seed: int, source_relative: str, index: int) -> int:
    payload = f"{seed}\0{source_relative}\0{index}".encode("utf-8")
    return int.from_bytes(hashlib.sha256(payload).digest()[:4], "big")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_manifest(path: Path, rows: list[dict[str, str | int]]) -> None:
    fieldnames = [
        "relative_path",
        "label",
        "source_relative_path",
        "source_sha256",
        "variant_index",
        "seed",
        "output_sha256",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    main()
