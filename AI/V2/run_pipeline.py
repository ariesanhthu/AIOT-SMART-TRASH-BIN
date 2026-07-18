"""Run V2 cleanup, direct augmentation, train, INT8 export, audit and report."""

from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys
import time


AI_DIR = Path(__file__).resolve().parents[1]
V2_DIR = Path(__file__).resolve().parent
DEFAULT_SOURCE = AI_DIR / "DATASET"
DEFAULT_DATA = V2_DIR / "dataset_augmented"
DEFAULT_ARTIFACTS = V2_DIR / "artifacts"
DEFAULT_ESP32_MODEL = V2_DIR / "esp32_model"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--out", type=Path, default=DEFAULT_ARTIFACTS)
    parser.add_argument("--augmentations-per-image", type=int, default=9)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--epochs", type=int, default=100)
    parser.add_argument("--patience", type=int, default=15)
    parser.add_argument("--plastic-weight-multiplier", type=float, default=1.0)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--force-prepare", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    source = args.source.resolve()
    data = args.data.resolve()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)

    _run(
        [
            "V2.clean_dataset",
            "--data",
            str(source),
            "--log",
            str(V2_DIR / "dataset_cleanup.json"),
        ]
    )
    augment = [
        "V2.augment_dataset",
        "--data",
        str(source),
        "--augmentations-per-image",
        str(args.augmentations_per_image),
        "--seed",
        str(args.seed),
    ]
    if args.force_prepare:
        augment.append("--force")
    _run(augment)

    prepare = [
        "V2.prepare_dataset",
        "--source",
        str(source),
        "--out",
        str(data),
        "--internal-validation-ratio",
        "0.20",
        "--seed",
        str(args.seed),
    ]
    if args.force_prepare:
        prepare.append("--force")
    _run(prepare)

    _run(
        [
            "V2.train",
            "--data",
            str(data),
            "--out",
            str(out),
            "--batch-size",
            str(args.batch_size),
            "--epochs",
            str(args.epochs),
            "--patience",
            str(args.patience),
            "--plastic-weight-multiplier",
            str(args.plastic_weight_multiplier),
            "--seed",
            str(args.seed),
        ]
    )
    float_model = out / "model_float.keras"
    int8_model = out / "model_int8.tflite"
    metadata = out / "model_metadata.json"
    _run(
        [
            "src.export_int8",
            "--model",
            str(float_model),
            "--data",
            str(data),
            "--metadata",
            str(metadata),
            "--out",
            str(int8_model),
            "--quantization-out",
            str(out / "quantization.json"),
            "--representative-per-class",
            "100",
            "--seed",
            str(args.seed),
        ]
    )
    # Evaluation writes metrics before raising when a quality target is missed.
    # Keep those honest FAIL results and continue to package the model/report.
    _run_evaluation(
        [
            "src.evaluate_model",
            "--float-model",
            str(float_model),
            "--int8-model",
            str(int8_model),
            "--metadata",
            str(metadata),
            "--data",
            str(data),
            "--out",
            str(out),
            "--min-agreement",
            "0.95",
            "--min-macro-f1",
            "0.80",
            "--min-class-recall",
            "0.80",
            "--max-accuracy-drop",
            "0.03",
            "--seed",
            str(args.seed),
        ],
        out,
    )
    for destination in (out, DEFAULT_ESP32_MODEL):
        _run(
            [
                "src.convert_to_c_array",
                "--model",
                str(int8_model),
                "--metadata",
                str(metadata),
                "--header",
                str(destination / "model_data.h"),
                "--source",
                str(destination / "model_data.cc"),
            ]
        )
    _run(
        [
            "V2.audit_originals",
            "--dataset",
            str(source),
            "--prepared",
            str(data),
            "--artifacts",
            str(out),
        ]
    )
    _run(
        [
            "V2.make_report",
            "--artifacts",
            str(out),
            "--dataset-stats",
            str(data / "stats.json"),
            "--augmentation-stats",
            str(source / "augmentation_stats.json"),
            "--cleanup",
            str(V2_DIR / "dataset_cleanup.json"),
            "--out",
            str(V2_DIR / "TRAINING_RESULT.md"),
        ]
    )
    print(f"V2 pipeline completed: {V2_DIR}")


def _run(arguments: list[str]) -> None:
    module, *module_args = arguments
    subprocess.run(
        [sys.executable, "-m", module, *module_args],
        cwd=AI_DIR,
        check=True,
    )


def _run_evaluation(arguments: list[str], out_dir: Path) -> None:
    module, *module_args = arguments
    started_ns = time.time_ns()
    completed = subprocess.run(
        [sys.executable, "-m", module, *module_args],
        cwd=AI_DIR,
        check=False,
    )
    required = (
        out_dir / "metrics_float.json",
        out_dir / "metrics_int8.json",
        out_dir / "comparison.json",
    )
    fresh = all(path.is_file() and path.stat().st_mtime_ns >= started_ns for path in required)
    if completed.returncode != 0 and not fresh:
        raise subprocess.CalledProcessError(completed.returncode, completed.args)
    if completed.returncode != 0:
        print("Quality targets were not met; packaging continues with FAIL in the report.")


if __name__ == "__main__":
    main()
