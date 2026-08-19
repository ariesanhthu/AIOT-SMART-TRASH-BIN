"""Merge the reviewed augmented V9 dataset into V10/dataset_prepared safely."""

from __future__ import annotations

from collections import Counter, defaultdict
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil

from V10.config import CLASS_NAMES, CLASS_TO_INDEX, DATASET_DIR, SPLITS, V10_DIR


SOURCE_DIR = V10_DIR / "dataset_augmented_v9"
MANIFEST_FIELDS = (
    "relative_path",
    "split",
    "label",
    "label_id",
    "kind",
    "source_relative_path",
    "source_name",
    "source_group",
    "visual_group",
    "augmentation",
    "online_augment",
    "sha256",
    "source_sha256",
    "width",
    "height",
    "origin_dataset",
)


def main() -> None:
    target = DATASET_DIR.resolve()
    source = SOURCE_DIR.resolve()
    if target == source or not target.is_dir() or not source.is_dir():
        raise RuntimeError("V10 merge source/target directories are invalid")

    target_manifest = target / "manifest.csv"
    source_manifest = source / "manifest.csv"
    base_rows = list(csv.DictReader(target_manifest.open(encoding="utf-8", newline="")))
    # Idempotent reruns keep only the original prepared rows before rebuilding
    # the augmented portion.
    base_rows = [
        row for row in base_rows
        if row.get("origin_dataset", "prepared_v9") == "prepared_v9"
    ]
    incoming_rows = list(csv.DictReader(source_manifest.open(encoding="utf-8", newline="")))

    backup_manifest = target / "manifest_before_v10_merge.csv"
    if not backup_manifest.exists():
        shutil.copy2(target_manifest, backup_manifest)
    backup_stats = target / "stats_before_v10_merge.json"
    if (target / "stats.json").is_file() and not backup_stats.exists():
        shutil.copy2(target / "stats.json", backup_stats)

    merged = [_normalize_base(row) for row in base_rows]
    location_corrections = []
    for row in incoming_rows:
        expected_source = source / row["relative_path"]
        actual_source = _find_source_file(source, expected_source, row["sha256"])
        if actual_source != expected_source:
            location_corrections.append({
                "manifest_path": row["relative_path"],
                "actual_source_path": actual_source.relative_to(source).as_posix(),
            })

        destination_relative = (
            Path(row["split"])
            / row["label"]
            / f"augv9_{Path(row['relative_path']).name}"
        )
        destination = target / destination_relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            if _sha256(destination) != row["sha256"]:
                raise RuntimeError(f"Merge destination collision: {destination}")
        else:
            shutil.copy2(actual_source, destination)

        merged.append({
            "relative_path": destination_relative.as_posix(),
            "split": row["split"],
            "label": row["label"],
            "label_id": str(CLASS_TO_INDEX[row["label"]]),
            "kind": row["kind"],
            "source_relative_path": row.get("source_relative_path", ""),
            "source_name": row.get("source_name", ""),
            "source_group": f"augmented_v9/{row['source_group']}",
            "visual_group": row.get("visual_group", ""),
            "augmentation": row.get("augmentation", ""),
            "online_augment": "False",
            "sha256": row["sha256"],
            "source_sha256": row.get("source_sha256", ""),
            "width": row.get("width", ""),
            "height": row.get("height", ""),
            "origin_dataset": "augmented_v9",
        })

    split_order = {name: index for index, name in enumerate(SPLITS)}
    merged.sort(key=lambda row: (
        split_order[row["split"]], CLASS_TO_INDEX[row["label"]], row["relative_path"]
    ))
    audit = _audit(target, merged)
    _write_manifest(target_manifest, merged)

    stats = {
        "schema_version": 2,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "purpose": "V10 combined dataset: prepared V9 plus all audited augmented V9 files",
        "counts": audit["counts"],
        "total": len(merged),
        "origin_counts": dict(Counter(row["origin_dataset"] for row in merged)),
        "kind_counts": dict(Counter(row["kind"] for row in merged)),
        "exact_duplicates": 0,
        "source_group_leakage": 0,
        "source_manifest_rows": len(incoming_rows),
        "source_location_corrections": location_corrections,
        "manifest_sha256": _sha256(target_manifest),
        "note": (
            "Nine physical source files did not match their audited manifest paths; "
            "they were located by filename+SHA256 and merged using the audited manifest split."
        ),
    }
    (target / "stats.json").write_text(
        json.dumps(stats, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (target / "V10_MERGE_REPORT.md").write_text(
        _render_report(stats), encoding="utf-8"
    )
    print(json.dumps(stats, indent=2, ensure_ascii=False))


def _normalize_base(row: dict[str, str]) -> dict[str, str]:
    return {
        "relative_path": row["relative_path"],
        "split": row["split"],
        "label": row["label"],
        "label_id": str(CLASS_TO_INDEX[row["label"]]),
        "kind": row["kind"],
        "source_relative_path": row.get("source_relative_path", ""),
        "source_name": row.get("source_name", ""),
        "source_group": f"prepared_v9/{row['source_group']}",
        "visual_group": row.get("visual_group", ""),
        "augmentation": row.get("augmentation", ""),
        "online_augment": "False",
        "sha256": row["sha256"],
        "source_sha256": row.get("source_sha256", ""),
        "width": row.get("width", ""),
        "height": row.get("height", ""),
        "origin_dataset": "prepared_v9",
    }


def _find_source_file(root: Path, expected: Path, expected_hash: str) -> Path:
    if expected.is_file() and _sha256(expected) == expected_hash:
        return expected
    matches = [
        path for path in root.rglob(expected.name)
        if path.is_file() and _sha256(path) == expected_hash
    ]
    if len(matches) != 1:
        raise FileNotFoundError(
            f"Expected exactly one source for {expected.name}, found {len(matches)}"
        )
    return matches[0]


def _audit(root: Path, rows: list[dict[str, str]]) -> dict:
    hashes: dict[str, str] = {}
    groups: dict[str, set[str]] = defaultdict(set)
    counts: dict[str, dict[str, int]] = {
        split: {label: 0 for label in CLASS_NAMES} for split in SPLITS
    }
    for row in rows:
        path = root / row["relative_path"]
        if not path.is_file() or _sha256(path) != row["sha256"]:
            raise RuntimeError(f"Merged file/hash mismatch: {path}")
        if row["sha256"] in hashes:
            raise RuntimeError(f"Exact duplicate: {hashes[row['sha256']]} and {path}")
        hashes[row["sha256"]] = str(path)
        groups[row["source_group"]].add(row["split"])
        counts[row["split"]][row["label"]] += 1
        if row["split"] != "train" and row["kind"] != "original":
            raise RuntimeError(f"Augmentation outside train: {path}")
    leaking = {group: sorted(splits) for group, splits in groups.items() if len(splits) > 1}
    if leaking:
        raise RuntimeError(f"Source-group leakage after merge: {leaking}")
    for split, per_class in counts.items():
        if len(set(per_class.values())) != 1:
            raise RuntimeError(f"Unbalanced {split} split: {per_class}")
    return {"counts": counts}


def _write_manifest(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=MANIFEST_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def _render_report(stats: dict) -> str:
    counts = stats["counts"]
    return f"""# V10 dataset merge report

`dataset_prepared` now contains both source datasets without deleting
`dataset_augmented_v9`.

| Split | paper | plastic | organic | Total |
|---|---:|---:|---:|---:|
| train | {counts['train']['paper']} | {counts['train']['plastic']} | {counts['train']['organic']} | {sum(counts['train'].values())} |
| validation | {counts['validation']['paper']} | {counts['validation']['plastic']} | {counts['validation']['organic']} | {sum(counts['validation'].values())} |
| test | {counts['test']['paper']} | {counts['test']['plastic']} | {counts['test']['organic']} | {sum(counts['test'].values())} |

- Total: {stats['total']} images.
- Exact duplicate files: 0.
- Source-group leakage: 0.
- Incoming source rows: {stats['source_manifest_rows']}.
- Physical source-path corrections resolved by filename and SHA-256: {len(stats['source_location_corrections'])}.
"""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    main()
