"""Run the reproducible train -> INT8 -> evaluate -> C-array pipeline."""

from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys

try:
    from .config import (
        DEFAULT_ARTIFACT_DIR,
        DEFAULT_DATA_DIR,
        DEFAULT_FIRMWARE_MODEL_DIR,
    )
    from .config import resolve_input_path, resolve_output_path
except ImportError:
    from config import (  # type: ignore
        DEFAULT_ARTIFACT_DIR,
        DEFAULT_DATA_DIR,
        DEFAULT_FIRMWARE_MODEL_DIR,
        resolve_input_path,
        resolve_output_path,
    )


CLEAN_ALLOWLIST = frozenset(
    {
        ".best.weights.h5",
        "calibration_metrics.json",
        "centroids.json",
        "comparison.json",
        "confusion_matrix_int8.csv",
        "labels.json",
        "light_trashnet_model.joblib",
        "metrics.json",
        "metrics_float.json",
        "metrics_float_eval.json",
        "metrics_int8.json",
        "model_best.keras",
        "model_data.cc",
        "model_data.h",
        "model_float.keras",
        "model_int8.tflite",
        "model_metadata.json",
        "quantization.json",
        "thresholds.json",
        "training_config.json",
        "training_history.json",
        "training_metrics.json",
    }
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", default=str(DEFAULT_DATA_DIR))
    parser.add_argument("--out", default=str(DEFAULT_ARTIFACT_DIR))
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--epochs", type=int, default=100)
    parser.add_argument("--patience", type=int, default=15)
    parser.add_argument("--learning-rate", type=float, default=1e-3)
    parser.add_argument("--weight-decay", type=float, default=1e-4)
    parser.add_argument("--label-smoothing", type=float, default=0.05)
    parser.add_argument("--representative-per-class", type=int, default=100)
    parser.add_argument("--max-accuracy-drop", type=float, default=0.03)
    parser.add_argument("--min-agreement", type=float, default=0.95)
    parser.add_argument("--min-macro-f1", type=float, default=0.80)
    parser.add_argument("--min-class-recall", type=float, default=0.80)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--no-augment", action="store_true")
    parser.add_argument("--no-clean", action="store_true")
    parser.add_argument(
        "--firmware-model-dir",
        default=str(DEFAULT_FIRMWARE_MODEL_DIR),
        help="Write the verified C array directly into the ESP-IDF component.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    data_dir = resolve_input_path(args.data)
    out_dir = resolve_output_path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    if not args.no_clean:
        clean_generated_artifacts(out_dir)

    float_model = out_dir / "model_float.keras"
    int8_model = out_dir / "model_int8.tflite"
    metadata = out_dir / "model_metadata.json"

    train_command = [
        "src.train",
        "--data",
        str(data_dir),
        "--out",
        str(out_dir),
        "--batch-size",
        str(args.batch_size),
        "--epochs",
        str(args.epochs),
        "--patience",
        str(args.patience),
        "--learning-rate",
        str(args.learning_rate),
        "--weight-decay",
        str(args.weight_decay),
        "--label-smoothing",
        str(args.label_smoothing),
        "--seed",
        str(args.seed),
    ]
    if args.no_augment:
        train_command.append("--no-augment")
    _run_module(train_command)

    _run_module(
        [
            "src.export_int8",
            "--model",
            str(float_model),
            "--data",
            str(data_dir),
            "--metadata",
            str(metadata),
            "--out",
            str(int8_model),
            "--representative-per-class",
            str(args.representative_per_class),
            "--seed",
            str(args.seed),
        ]
    )
    _run_module(
        [
            "src.evaluate_model",
            "--float-model",
            str(float_model),
            "--int8-model",
            str(int8_model),
            "--metadata",
            str(metadata),
            "--data",
            str(data_dir),
            "--out",
            str(out_dir),
            "--max-accuracy-drop",
            str(args.max_accuracy_drop),
            "--min-agreement",
            str(args.min_agreement),
            "--min-macro-f1",
            str(args.min_macro_f1),
            "--min-class-recall",
            str(args.min_class_recall),
            "--seed",
            str(args.seed),
        ]
    )
    _run_module(
        [
            "src.convert_to_c_array",
            "--model",
            str(int8_model),
            "--metadata",
            str(metadata),
            "--header",
            str(out_dir / "model_data.h"),
            "--source",
            str(out_dir / "model_data.cc"),
        ]
    )
    firmware_model_dir = resolve_output_path(args.firmware_model_dir)
    _run_module(
        [
            "src.convert_to_c_array",
            "--model",
            str(int8_model),
            "--metadata",
            str(metadata),
            "--header",
            str(firmware_model_dir / "model_data.h"),
            "--source",
            str(firmware_model_dir / "model_data.cc"),
        ]
    )
    print(f"Pipeline completed successfully: {out_dir}")


def clean_generated_artifacts(out_dir: Path) -> None:
    resolved = out_dir.resolve()
    for file_name in sorted(CLEAN_ALLOWLIST):
        candidate = (resolved / file_name).resolve()
        if candidate.parent != resolved:
            raise RuntimeError(f"Refusing to clean outside artifact directory: {candidate}")
        if candidate.is_file():
            candidate.unlink()


def _run_module(arguments: list[str]) -> None:
    module, *module_args = arguments
    command = [sys.executable, "-m", module, *module_args]
    subprocess.run(command, cwd=Path(__file__).resolve().parents[1], check=True)


if __name__ == "__main__":
    main()
