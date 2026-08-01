"""Prepare, train, fine-tune, quantize, audit and optionally embed TinyCNN V6."""

from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys


AI_DIR = Path(__file__).resolve().parents[1]
V6_DIR = Path(__file__).resolve().parent
DEFAULT_V4_DATA = AI_DIR / "V4" / "dataset_prepared"
DEFAULT_NEW_DATA = V6_DIR / "dataset_prepared"
DEFAULT_DATA = V6_DIR / "dataset_indexed"
DEFAULT_BASE_ARTIFACTS = V6_DIR / "artifacts"
DEFAULT_TUNED_ARTIFACTS = V6_DIR / "artifacts_tuned"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--v4-data", type=Path, default=DEFAULT_V4_DATA)
    parser.add_argument("--new-data", type=Path, default=DEFAULT_NEW_DATA)
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--base-out", type=Path, default=DEFAULT_BASE_ARTIFACTS)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--epochs", type=int, default=25)
    parser.add_argument("--patience", type=int, default=25)
    parser.add_argument("--fine-tune-epochs", type=int, default=30)
    parser.add_argument("--fine-tune-patience", type=int, default=9)
    parser.add_argument("--fine-tune-seed", type=int, default=314159)
    parser.add_argument("--evaluation-seed", type=int, default=314159)
    parser.add_argument("--representative-per-class", type=int, default=170)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--force-prepare", action="store_true")
    parser.add_argument("--skip-prepare", action="store_true")
    parser.add_argument("--skip-train", action="store_true")
    parser.add_argument(
        "--fine-tune",
        action="store_true",
        help="Optionally run the extra fine-tune stage into artifacts_tuned",
    )
    parser.add_argument("--embed", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    v4_data = args.v4_data.resolve()
    new_data = args.new_data.resolve()
    data = args.data.resolve()
    base_out = args.base_out.resolve()
    default_out = DEFAULT_TUNED_ARTIFACTS if args.fine_tune else base_out
    out = (args.out if args.out is not None else default_out).resolve()
    base_out.mkdir(parents=True, exist_ok=True)
    out.mkdir(parents=True, exist_ok=True)

    if not args.skip_prepare:
        prepare = [
            "V6.prepare_dataset",
            "--v4-data",
            str(v4_data),
            "--new-data",
            str(new_data),
            "--out",
            str(data),
            "--seed",
            str(args.seed),
        ]
        if args.force_prepare:
            prepare.append("--force")
        _run(prepare)
    if not args.skip_train:
        _run(
            [
                "V6.train",
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

    if args.fine_tune:
        _run(
            [
                "V6.fine_tune",
                "--data",
                str(data),
                "--model",
                str(base_out / "model_float.keras"),
                "--metadata",
                str(base_out / "model_metadata.json"),
                "--out",
                str(out),
                "--batch-size",
                str(args.batch_size),
                "--epochs",
                str(args.fine_tune_epochs),
                "--patience",
                str(args.fine_tune_patience),
                "--seed",
                str(args.fine_tune_seed),
            ]
        )

    float_model = out / "model_float.keras"
    int8_model = out / "model_int8.tflite"
    metadata = out / "model_metadata.json"
    _run(
        [
            "V6.export_int8",
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
            str(args.representative_per_class),
            "--seed",
            str(args.seed),
        ]
    )
    _run_allow_quality_failure(
        [
            "V6.evaluate_model",
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
            "0.90",
            "--min-class-recall",
            "0.70",
            "--max-accuracy-drop",
            "0.03",
            "--seed",
            str(args.evaluation_seed),
        ],
        required=(out / "comparison.json", out / "metrics_int8.json"),
    )
    robustness = [
        "V6.evaluate_robustness",
        "--data",
        str(data),
        "--float-model",
        str(float_model),
        "--int8-model",
        str(int8_model),
        "--out",
        str(out),
        "--seed",
        str(args.evaluation_seed),
        "--min-clean-macro-f1",
        "0.90",
        "--min-class-recall",
        "0.70",
        "--min-stress-macro-f1",
        "0.50",
        "--max-organic-to-paper",
        "0.15",
    ]
    v4_baseline = AI_DIR / "V4" / "artifacts_tuned" / "model_int8.tflite"
    if not v4_baseline.is_file():
        v4_baseline = AI_DIR / "V4" / "artifacts" / "model_int8.tflite"
    if v4_baseline.is_file():
        robustness.extend(["--baseline-model", str(v4_baseline)])
    _run(robustness)
    if args.embed:
        _run(["V6.deploy_esp32", "--artifacts", str(out)])
    print(f"V6 pipeline completed: {V6_DIR}")


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
        print("V6 clean INT8 gate failed; robustness audit will still run.")


if __name__ == "__main__":
    main()
