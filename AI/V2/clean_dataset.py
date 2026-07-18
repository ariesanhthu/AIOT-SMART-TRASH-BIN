"""Remove verified empty capture frames from AI/DATASET without touching other images."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


AI_DIR = Path(__file__).resolve().parents[1]
DATASET_DIR = AI_DIR / "DATASET"
LOG_PATH = Path(__file__).resolve().parent / "dataset_cleanup.json"

EMPTY_FRAMES = {
    "train/paper/paper_001.jpg": "d5c23e3867448c48355ee98c59b498ceb7c064a01b78fd99898daef486e6a966",
    "train/paper/paper_002.jpg": "220f4020fdca280a2aa913f6d6d012d74cd058aa7bdd9069bf8612c31b0033f7",
    "train/paper/paper_004.jpg": "7c61622602a1cd99e7d4f10c827eded3a4ccb474020003bac4505a1be096258a",
    "train/paper/paper_014.jpg": "ba464906e08997796f02effb864073bc39928304ee0c8104129ade802ea9c046",
    "train/paper/paper_020.jpg": "4795585cbf6ce0a8f66635a9dd3f40e36dfb98186d34767501d4a0a5efae149e",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=DATASET_DIR)
    parser.add_argument("--log", type=Path, default=LOG_PATH)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    dataset_dir = args.data.expanduser().resolve()
    log_path = args.log.expanduser().resolve()
    removed: list[dict[str, str]] = []
    already_absent: list[str] = []
    for relative, expected_sha256 in EMPTY_FRAMES.items():
        path = dataset_dir.joinpath(*relative.split("/")).resolve()
        if dataset_dir not in path.parents:
            raise RuntimeError(f"Unsafe cleanup path: {path}")
        if not path.exists():
            already_absent.append(relative)
            continue
        actual_sha256 = _sha256(path)
        if actual_sha256 != expected_sha256:
            raise RuntimeError(
                f"Refusing to remove changed file {path}: "
                f"expected {expected_sha256}, got {actual_sha256}"
            )
        path.unlink()
        removed.append(
            {
                "relative_path": relative,
                "sha256": actual_sha256,
                "reason": "empty capture: no waste object visible",
            }
        )

    payload = {
        "dataset": str(dataset_dir),
        "verified_empty_frames": [
            {
                "relative_path": relative,
                "sha256": sha256,
                "reason": "empty capture: no waste object visible",
            }
            for relative, sha256 in EMPTY_FRAMES.items()
        ],
        "verified_empty_count": len(EMPTY_FRAMES),
        "removed": removed,
        "already_absent": already_absent,
        "policy": "Empty camera frames are not labeled as paper in a three-waste-class model.",
    }
    log_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(payload, indent=2, ensure_ascii=False))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    main()
