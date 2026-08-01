"""Run the complete V5 data, train, INT8, robustness and report pipeline."""

from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys


AI_DIR = Path(__file__).resolve().parents[1]
V5_DIR = Path(__file__).resolve().parent
DEFAULT_DATA = V5_DIR / "dataset_prepared"
DEFAULT_BASE_ARTIFACTS = V5_DIR / "artifacts"
DEFAULT_TUNED_ARTIFACTS = V5_DIR / "artifacts_tuned"
DEFAULT_ARTIFACTS = V5_DIR / "artifacts_tuned2"
DEFAULT_ESP32 = V5_DIR / "esp32_model"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--out", type=Path, default=DEFAULT_ARTIFACTS)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--epochs", type=int, default=100)
    parser.add_argument("--patience", type=int, default=18)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--force-prepare", action="store_true")
    parser.add_argument("--skip-prepare", action="store_true")
    parser.add_argument("--skip-train", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    data = args.data.resolve()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    base_out = DEFAULT_BASE_ARTIFACTS.resolve()
    tuned_out = DEFAULT_TUNED_ARTIFACTS.resolve()

    if not args.skip_prepare:
        prepare = ["V5.prepare_dataset", "--out", str(data), "--seed", str(args.seed)]
        if args.force_prepare:
            prepare.append("--force")
        _run(prepare)
    if not args.skip_train:
        _run(
            [
                "V5.train",
                "--data",
                str(data),
                "--out",
                str(base_out),
                "--batch-size",
                str(args.batch_size),
                "--epochs",
                str(args.epochs),
                "--patience",
                str(args.patience),
                "--seed",
                str(args.seed),
            ]
        )
        _run(
            [
                "V5.fine_tune",
                "--data",
                str(data),
                "--model",
                str(base_out / "model_float.keras"),
                "--metadata",
                str(base_out / "model_metadata.json"),
                "--out",
                str(tuned_out),
                "--epochs",
                "15",
                "--patience",
                "5",
                "--learning-rate",
                "0.0001",
                "--seed",
                "314159",
            ]
        )
        _run(
            [
                "V5.fine_tune",
                "--data",
                str(data),
                "--model",
                str(tuned_out / "model_float.keras"),
                "--metadata",
                str(tuned_out / "model_metadata.json"),
                "--out",
                str(out),
                "--epochs",
                "15",
                "--patience",
                "5",
                "--learning-rate",
                "0.00005",
                "--seed",
                "271828",
            ]
        )

    float_model = out / "model_float.keras"
    int8_model = out / "model_int8.tflite"
    metadata = out / "model_metadata.json"
    _run(
        [
            "V5.export_int8",
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
            "347",
            "--seed",
            str(args.seed),
        ]
    )
    _run_allow_quality_failure(
        [
            "V5.evaluate_model",
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
            "0.75",
            "--max-accuracy-drop",
            "0.03",
            "--seed",
            str(args.seed),
        ],
        required=(out / "metrics_float.json", out / "metrics_int8.json", out / "comparison.json"),
    )
    robustness = [
        "V5.evaluate_robustness",
        "--data",
        str(data),
        "--float-model",
        str(float_model),
        "--int8-model",
        str(int8_model),
        "--out",
        str(out),
        "--seed",
        str(args.seed),
    ]
    v4_baseline = AI_DIR / "V4" / "artifacts" / "model_int8.tflite"
    if v4_baseline.is_file():
        robustness.extend(["--baseline-model", str(v4_baseline)])
    _run(robustness)

    for destination in (out, DEFAULT_ESP32):
        _run(
            [
                "V5.convert_to_c_array",
                "--model",
                str(int8_model),
                "--metadata",
                str(metadata),
                "--header",
                str(destination / "model_data.h"),
                "--source",
                str(destination / "model_data.cpp"),
            ]
        )
    _run(
        [
            "V5.make_report",
            "--artifacts",
            str(out),
            "--stats",
            str(data / "stats.json"),
            "--charts",
            str(V5_DIR / "charts"),
            "--out",
            str(V5_DIR / "EVALUATION_REPORT.md"),
        ]
    )
    print(f"V5 pipeline completed: {V5_DIR}")


def _run(arguments: list[str]) -> None:
    module, *module_args = arguments
    subprocess.run(
        [sys.executable, "-m", module, *module_args], cwd=AI_DIR, check=True
    )


def _run_allow_quality_failure(
    arguments: list[str], *, required: tuple[Path, ...]
) -> None:
    module, *module_args = arguments
    completed = subprocess.run(
        [sys.executable, "-m", module, *module_args], cwd=AI_DIR, check=False
    )
    if completed.returncode != 0 and not all(path.is_file() for path in required):
        raise subprocess.CalledProcessError(completed.returncode, completed.args)
    if completed.returncode != 0:
        print("Clean INT8 quality gate failed; robustness/report stages continue.")


if __name__ == "__main__":
    main()
