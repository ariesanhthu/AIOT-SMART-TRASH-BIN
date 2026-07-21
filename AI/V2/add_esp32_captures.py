"""Add ESP32-CAM captures to the DATASET/paper class.

Steps:
1. Read all .jpg files from the source capture directory.
2. Group images by capture time clusters (to stratify the split).
3. Split ~80/20 into train/validation, ensuring each time-cluster is
   represented in both splits.
4. Copy & rename as paper_025 .. paper_069 (continuing from the existing
   highest index in the dataset, which is paper_024).
5. Generate 9 augmented variants per train image, matching the existing
   augmentation pipeline (augment_dataset.py _augment function).
6. Re-run augment_dataset.py --force to regenerate manifest/stats for all
   originals (cleanest approach).
"""

from __future__ import annotations

import argparse
import re
import shutil
from pathlib import Path

AI_DIR = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = AI_DIR / "esp32-cam-captures-2026-07-21T06-42-54-018Z"
DEFAULT_DATASET = AI_DIR / "DATASET"
IMAGE_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png"})
GENERATED_PATTERN = re.compile(r"^(?P<stem>.+)__aug_v2_(?P<index>\d{2})\.jpg$")


def find_max_paper_index(dataset_dir: Path) -> int:
    """Find the highest paper_NNN index across train and validation."""
    max_idx = 0
    pattern = re.compile(r"^paper_(\d{3})\.jpg$")
    for split in ("train", "validation"):
        paper_dir = dataset_dir / split / "paper"
        if not paper_dir.is_dir():
            continue
        for f in paper_dir.iterdir():
            m = pattern.match(f.name)
            if m:
                max_idx = max(max_idx, int(m.group(1)))
    return max_idx


def group_by_time_cluster(files: list[Path], gap_seconds: float = 10.0) -> list[list[Path]]:
    """Group files by time clusters based on filename timestamps.
    
    Files are sorted by name. A new cluster starts when there is a gap
    > gap_seconds between consecutive timestamps.
    """
    import re as _re
    from datetime import datetime

    ts_pattern = _re.compile(
        r"esp32-cam-(\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}-\d{3}Z)\.jpg$"
    )

    def parse_ts(path: Path) -> datetime:
        m = ts_pattern.search(path.name)
        if not m:
            raise ValueError(f"Cannot parse timestamp from {path.name}")
        ts_str = m.group(1)
        # Convert 2026-07-21T06-38-22-515Z -> 2026-07-21T06:38:22.515Z
        ts_str = (
            ts_str[:13].replace("-", ":", 1)  # hour
            .replace("-", ":")  # This doesn't work well, let's be explicit
        )
        # More explicit parsing
        raw = m.group(1)  # e.g. 2026-07-21T06-38-22-515Z
        parts = raw.rstrip("Z").split("T")
        date_part = parts[0]  # 2026-07-21
        time_raw = parts[1]   # 06-38-22-515
        time_parts = time_raw.split("-")
        h, mi, s, ms = time_parts[0], time_parts[1], time_parts[2], time_parts[3]
        return datetime.fromisoformat(f"{date_part}T{h}:{mi}:{s}.{ms}")

    sorted_files = sorted(files, key=lambda p: parse_ts(p))
    if not sorted_files:
        return []

    clusters: list[list[Path]] = [[sorted_files[0]]]
    for i in range(1, len(sorted_files)):
        prev_ts = parse_ts(sorted_files[i - 1])
        curr_ts = parse_ts(sorted_files[i])
        diff = (curr_ts - prev_ts).total_seconds()
        if diff > gap_seconds:
            clusters.append([])
        clusters[-1].append(sorted_files[i])

    return clusters


def split_balanced(
    clusters: list[list[Path]], val_ratio: float = 0.20, seed: int = 42
) -> tuple[list[Path], list[Path]]:
    """Split clusters into train/val, taking ~val_ratio from each cluster.
    
    Ensures at least 1 image from each cluster goes to validation (if cluster
    has >= 2 images), and the rest to train.
    """
    import random

    rng = random.Random(seed)
    train_files: list[Path] = []
    val_files: list[Path] = []

    for cluster in clusters:
        shuffled = list(cluster)
        rng.shuffle(shuffled)
        n_val = max(1, round(len(shuffled) * val_ratio))
        if len(shuffled) <= 1:
            # Only 1 image: put in train (augmentation will help)
            train_files.extend(shuffled)
        else:
            val_files.extend(shuffled[:n_val])
            train_files.extend(shuffled[n_val:])

    return train_files, val_files


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        type=Path,
        default=DEFAULT_SOURCE,
        help="Directory containing ESP32-CAM capture images",
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        default=DEFAULT_DATASET,
        help="Root dataset directory (has train/ and validation/ subdirs)",
    )
    parser.add_argument("--val-ratio", type=float, default=0.20)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--dry-run", action="store_true", help="Print plan without copying")
    args = parser.parse_args()

    source_dir = args.source.resolve()
    dataset_dir = args.dataset.resolve()

    # 1. Collect source images
    source_images = sorted(
        p for p in source_dir.iterdir()
        if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS
    )
    print(f"Found {len(source_images)} images in {source_dir}")

    # 2. Group by time clusters
    clusters = group_by_time_cluster(source_images, gap_seconds=10.0)
    print(f"Identified {len(clusters)} time clusters:")
    for i, c in enumerate(clusters):
        print(f"  Cluster {i+1}: {len(c)} images")

    # 3. Split balanced
    train_files, val_files = split_balanced(clusters, val_ratio=args.val_ratio, seed=args.seed)
    print(f"\nSplit: {len(train_files)} train, {len(val_files)} validation")

    # 4. Find max index
    max_idx = find_max_paper_index(dataset_dir)
    print(f"Current max paper index: paper_{max_idx:03d}")
    next_idx = max_idx + 1

    # 5. Copy & rename
    train_paper_dir = dataset_dir / "train" / "paper"
    val_paper_dir = dataset_dir / "validation" / "paper"

    print(f"\n--- TRAIN ({len(train_files)} images) ---")
    train_mapping: list[tuple[Path, Path]] = []
    idx = next_idx
    for src in train_files:
        dst = train_paper_dir / f"paper_{idx:03d}.jpg"
        train_mapping.append((src, dst))
        print(f"  {src.name} -> {dst.name}")
        idx += 1

    print(f"\n--- VALIDATION ({len(val_files)} images) ---")
    val_mapping: list[tuple[Path, Path]] = []
    for src in val_files:
        dst = val_paper_dir / f"paper_{idx:03d}.jpg"
        val_mapping.append((src, dst))
        print(f"  {src.name} -> {dst.name}")
        idx += 1

    if args.dry_run:
        print("\n[DRY RUN] No files copied.")
        return

    # Actually copy
    for src, dst in train_mapping:
        shutil.copy2(src, dst)
    for src, dst in val_mapping:
        shutil.copy2(src, dst)

    total_copied = len(train_mapping) + len(val_mapping)
    print(f"\n[OK] Copied {total_copied} images (paper_{next_idx:03d} .. paper_{idx-1:03d})")
    print(f"  Train: {len(train_mapping)} images")
    print(f"  Validation: {len(val_mapping)} images")
    print(f"\nNext step: Run augmentation to generate augmented variants:")
    print(f"  python V2/augment_dataset.py --force")


if __name__ == "__main__":
    main()
