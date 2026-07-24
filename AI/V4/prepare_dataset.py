"""Build V4 from the leakage-safe V3 splits and a balanced TrashNet other class."""

from __future__ import annotations

import argparse
import csv
import json
import os
from pathlib import Path
import random
import shutil

import numpy as np
from PIL import Image, ImageEnhance, ImageFilter

from V4.runtime import LABELS


V4_DIR = Path(__file__).resolve().parent
AI_DIR = V4_DIR.parent
DEFAULT_V3_DATA = AI_DIR / "V3" / "dataset_prepared"
DEFAULT_TRASHNET = AI_DIR / "trashnet" / "data" / "dataset-resized" / "dataset-resized"
DEFAULT_OUTPUT = V4_DIR / "dataset_prepared"
SPLITS = ("train", "validation", "test")
V3_LABELS = LABELS[:-1]
IMAGE_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png"})
OTHER_COUNTS = {
    "train": {"cardboard": 130, "metal": 130},
    "validation": {"cardboard": 5, "metal": 4},
    "test": {"cardboard": 3, "metal": 3},
}
ESP_SIMULATION_FRACTION = 0.25


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--v3-data", type=Path, default=DEFAULT_V3_DATA)
    parser.add_argument("--trashnet", type=Path, default=DEFAULT_TRASHNET)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    summary = prepare_dataset(
        v3_data=args.v3_data,
        trashnet=args.trashnet,
        output=args.out,
        seed=args.seed,
        force=args.force,
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))


def prepare_dataset(
    *, v3_data: str | Path, trashnet: str | Path, output: str | Path,
    seed: int, force: bool,
) -> dict:
    v3_root = Path(v3_data).expanduser().resolve()
    trashnet_root = Path(trashnet).expanduser().resolve()
    output_root = Path(output).expanduser().resolve()
    _validate_sources(v3_root, trashnet_root)

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
    selected = _select_other_sources(trashnet_root, seed)
    train_other = selected["train"]
    degraded_paths = set(
        random.Random(seed + 7919).sample(
            train_other,
            round(len(train_other) * ESP_SIMULATION_FRACTION),
        )
    )
    rng = random.Random(seed + 104729)

    try:
        for split in SPLITS:
            for label in V3_LABELS:
                for source in sorted((v3_root / split / label).iterdir()):
                    if not _is_image(source):
                        continue
                    destination = temporary / split / label / source.name
                    shutil.copy2(source, destination)
                    rows.append(_lineage_row(
                        destination, temporary, source, "v3_prepared", split,
                        label, "preserved", "",
                    ))

        other_index = 1
        for split in SPLITS:
            for source in selected[split]:
                origin = source.parent.name
                degraded = split == "train" and source in degraded_paths
                suffix = "__esp_sim" if degraded else ""
                file_name = f"other_{origin}_{other_index:04d}{suffix}.jpg"
                destination = temporary / split / "other" / file_name
                if degraded:
                    parameters = _save_esp_simulated(source, destination, rng)
                    kind = "esp_simulated"
                else:
                    _save_rgb_jpeg(source, destination)
                    parameters = "none"
                    kind = "original"
                rows.append(_lineage_row(
                    destination, temporary, source, "trashnet", split,
                    "other", kind, parameters,
                ))
                other_index += 1

        _write_lineage(temporary / "lineage.csv", rows)
        summary = _build_summary(
            v3_root, trashnet_root, output_root, rows, selected, degraded_paths, seed
        )
        (temporary / "stats.json").write_text(
            json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, output_root)
    except Exception:
        if temporary.exists():
            _safe_remove(temporary)
        raise
    return summary


def _validate_sources(v3_root: Path, trashnet_root: Path) -> None:
    for split in SPLITS:
        for label in V3_LABELS:
            directory = v3_root / split / label
            if not directory.is_dir() or not any(_is_image(path) for path in directory.iterdir()):
                raise FileNotFoundError(f"Missing V3 prepared images: {directory}")
    for origin in ("cardboard", "metal"):
        directory = trashnet_root / origin
        required = sum(OTHER_COUNTS[split][origin] for split in SPLITS)
        available = sum(_is_image(path) for path in directory.iterdir()) if directory.is_dir() else 0
        if available < required:
            raise ValueError(f"Need {required} {origin} images, found {available}: {directory}")


def _select_other_sources(root: Path, seed: int) -> dict[str, list[Path]]:
    selected = {split: [] for split in SPLITS}
    for origin_index, origin in enumerate(("cardboard", "metal")):
        images = sorted(path for path in (root / origin).iterdir() if _is_image(path))
        random.Random(seed + 3571 * origin_index).shuffle(images)
        cursor = 0
        for split in SPLITS:
            count = OTHER_COUNTS[split][origin]
            selected[split].extend(images[cursor : cursor + count])
            cursor += count
    for split_index, split in enumerate(SPLITS):
        random.Random(seed + 65537 * split_index).shuffle(selected[split])
    flat = [path for split in SPLITS for path in selected[split]]
    if len(flat) != len(set(flat)):
        raise RuntimeError("TrashNet source leakage detected across V4 splits")
    return selected


def _save_rgb_jpeg(source: Path, destination: Path) -> None:
    with Image.open(source) as image:
        image.convert("RGB").save(destination, format="JPEG", quality=95, subsampling=0)


def _save_esp_simulated(
    source: Path, destination: Path, rng: random.Random,
) -> str:
    with Image.open(source) as opened:
        image = opened.convert("RGB").resize((320, 240), Image.Resampling.BILINEAR)

    brightness = rng.uniform(0.84, 1.04)
    contrast = rng.uniform(0.86, 1.08)
    saturation = rng.uniform(0.76, 0.98)
    red_gain = rng.uniform(0.92, 1.04)
    green_gain = rng.uniform(0.95, 1.03)
    blue_gain = rng.uniform(0.90, 1.05)
    noise_sigma = rng.uniform(1.5, 4.0)
    blur_radius = rng.uniform(0.20, 0.65)
    jpeg_quality = rng.randint(55, 76)

    image = ImageEnhance.Brightness(image).enhance(brightness)
    image = ImageEnhance.Contrast(image).enhance(contrast)
    image = ImageEnhance.Color(image).enhance(saturation)
    array = np.asarray(image, dtype=np.float32)
    array *= np.asarray([red_gain, green_gain, blue_gain], dtype=np.float32)
    noise_seed = rng.randrange(0, 2**32)
    noise = np.random.default_rng(noise_seed).normal(0.0, noise_sigma, array.shape)
    array = np.clip(np.rint(array + noise), 0, 255).astype(np.uint8)

    # Match the firmware's RGB565 channel expansion: low bits are discarded.
    array[..., 0] &= 0xF8
    array[..., 1] &= 0xFC
    array[..., 2] &= 0xF8
    simulated = Image.fromarray(array, mode="RGB").filter(
        ImageFilter.GaussianBlur(radius=blur_radius)
    )
    simulated.save(
        destination,
        format="JPEG",
        quality=jpeg_quality,
        subsampling=2,
        optimize=False,
    )
    return (
        f"qvga=320x240;rgb565=true;brightness={brightness:.4f};"
        f"contrast={contrast:.4f};saturation={saturation:.4f};"
        f"rgb_gain={red_gain:.4f}/{green_gain:.4f}/{blue_gain:.4f};"
        f"noise_sigma={noise_sigma:.4f};noise_seed={noise_seed};"
        f"blur_radius={blur_radius:.4f};jpeg_quality={jpeg_quality}"
    )


def _lineage_row(
    destination: Path, root: Path, source: Path, source_dataset: str,
    split: str, label: str, kind: str, parameters: str,
) -> dict[str, str]:
    return {
        "prepared_relative_path": destination.relative_to(root).as_posix(),
        "split": split,
        "label": label,
        "kind": kind,
        "source_dataset": source_dataset,
        "source_path": str(source.resolve()),
        "transform_parameters": parameters,
    }


def _write_lineage(path: Path, rows: list[dict[str, str]]) -> None:
    fieldnames = [
        "prepared_relative_path", "split", "label", "kind",
        "source_dataset", "source_path", "transform_parameters",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _build_summary(v3_root, trashnet_root, output_root, rows, selected,
                   degraded_paths, seed) -> dict:
    counts = {
        split: {
            label: sum(row["split"] == split and row["label"] == label for row in rows)
            for label in LABELS
        }
        for split in SPLITS
    }
    other_origins = {
        split: {
            origin: sum(path.parent.name == origin for path in selected[split])
            for origin in ("cardboard", "metal")
        }
        for split in SPLITS
    }
    train_counts = list(counts["train"].values())
    return {
        "v3_source": str(v3_root),
        "trashnet_source": str(trashnet_root),
        "output": str(output_root),
        "seed": seed,
        "labels": list(LABELS),
        "prepared_counts": counts,
        "prepared_total": len(rows),
        "other_source_counts": other_origins,
        "other_selection": (
            "Train other count equals the arithmetic mean of the three V3 train "
            "class counts; validation and test approximate their split means."
        ),
        "train_balance": {
            "minimum": min(train_counts),
            "maximum": max(train_counts),
            "other_vs_existing_mean": counts["train"]["other"] /
            (sum(counts["train"][label] for label in V3_LABELS) / len(V3_LABELS)),
        },
        "esp_simulation": {
            "split": "train_only",
            "count": len(degraded_paths),
            "fraction_of_other_train": len(degraded_paths) / len(selected["train"]),
            "resolution": [320, 240],
            "color": "RGB565-like low-bit truncation plus mild sensor color/noise variation",
            "validation_and_test_modified": False,
        },
        "leakage_control": (
            "All V3 splits are preserved. Each selected TrashNet source appears in "
            "exactly one split; ESP simulation replaces only its train copy."
        ),
    }


def _is_image(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS


def _safe_remove(path: Path) -> None:
    resolved = path.resolve()
    expected_parent = V4_DIR.resolve()
    if resolved.parent != expected_parent or resolved.name not in {
        "dataset_prepared", ".dataset_prepared.tmp"
    }:
        raise RuntimeError(f"Refusing to remove unexpected path: {resolved}")
    shutil.rmtree(resolved)


if __name__ == "__main__":
    main()

