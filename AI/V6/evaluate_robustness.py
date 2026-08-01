"""Evaluate V6 on clean and deterministic environmental stress profiles."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

from V6.runtime import LABELS, configure_shared_contract

configure_shared_contract()

import numpy as np  # noqa: E402
from PIL import Image, ImageFilter  # noqa: E402
import tensorflow as tf  # noqa: E402

from src.dataset import (  # noqa: E402
    apply_input_contract_u8,
    load_dataset_index,
    preprocess_file_raw,
    simulate_rgb565_u8,
)
from src.evaluate_model import KerasPredictor, TFLitePredictor  # noqa: E402
from src.metadata import write_json_atomic  # noqa: E402
from src.metrics import classification_metrics  # noqa: E402


V6_DIR = Path(__file__).resolve().parent
DEFAULT_DATA = V6_DIR / "dataset_indexed"
DEFAULT_ARTIFACTS = V6_DIR / "artifacts"
PROFILE_NAMES = (
    "clean",
    "low_light",
    "overexposed",
    "warm_cast",
    "cool_cast",
    "angle_plus20",
    "angle_minus20",
    "shadow_rgb565",
    "combined_hard",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA)
    parser.add_argument(
        "--float-model", type=Path, default=DEFAULT_ARTIFACTS / "model_float.keras"
    )
    parser.add_argument(
        "--int8-model", type=Path, default=DEFAULT_ARTIFACTS / "model_int8.tflite"
    )
    parser.add_argument("--baseline-model", type=Path, default=None)
    parser.add_argument("--out", type=Path, default=DEFAULT_ARTIFACTS)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--min-clean-macro-f1", type=float, default=0.75)
    parser.add_argument("--min-class-recall", type=float, default=0.70)
    parser.add_argument("--min-stress-macro-f1", type=float, default=0.58)
    parser.add_argument("--max-organic-to-paper", type=float, default=0.15)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    for name in (
        "min_clean_macro_f1",
        "min_class_recall",
        "min_stress_macro_f1",
        "max_organic_to_paper",
    ):
        if not 0.0 <= getattr(args, name) <= 1.0:
            raise ValueError(f"{name} must be between 0 and 1")

    index = load_dataset_index(args.data.expanduser().resolve())
    samples = index.for_split("test")
    truth = np.asarray([sample.label_id for sample in samples], dtype=np.int64)
    raw_images = [preprocess_file_raw(sample.path) for sample in samples]
    raw_profile_images = {
        profile: np.stack(
            [
                apply_profile(
                    image,
                    profile,
                    _sample_seed(args.seed, sample.relative_path, profile),
                )
                for image, sample in zip(raw_images, samples, strict=True)
            ]
        ).astype(np.float32)
        for profile in PROFILE_NAMES
    }

    float_predictor = KerasPredictor(args.float_model.expanduser().resolve())
    int8_predictor = TFLitePredictor(args.int8_model.expanduser().resolve())
    models: dict[str, object] = {
        "v6_float": float_predictor,
        "v6_int8": int8_predictor,
    }
    if args.baseline_model is not None:
        models["v4_int8_baseline"] = TFLitePredictor(
            args.baseline_model.expanduser().resolve()
        )

    output: dict[str, dict] = {}
    prediction_rows: list[dict[str, str | int | float]] = []
    for model_name, predictor in models.items():
        contract = _apply_v4_input_contract if model_name == "v4_int8_baseline" else _apply_input_contract
        profile_results: dict[str, dict] = {}
        for profile, raw_profile in raw_profile_images.items():
            images = np.stack([contract(image) for image in raw_profile])
            logits = _predict_images(predictor, images)
            profile_results[profile] = _profile_metrics(truth, logits)
            probabilities = _softmax(logits)
            predictions = np.argmax(logits, axis=1)
            for sample, predicted, confidence in zip(
                samples, predictions, np.max(probabilities, axis=1), strict=True
            ):
                prediction_rows.append(
                    {
                        "model": model_name,
                        "profile": profile,
                        "relative_path": sample.relative_path,
                        "actual": sample.label,
                        "predicted": LABELS[int(predicted)],
                        "confidence": float(confidence),
                    }
                )
        stress = [profile_results[name] for name in PROFILE_NAMES if name != "clean"]
        profile_results["summary"] = {
            "stress_profile_count": len(stress),
            "mean_stress_accuracy": float(np.mean([row["accuracy"] for row in stress])),
            "mean_stress_macro_f1": float(np.mean([row["macro_f1"] for row in stress])),
            "worst_stress_macro_f1": float(np.min([row["macro_f1"] for row in stress])),
            "mean_stress_organic_recall": float(
                np.mean([row["per_class"]["organic"]["recall"] for row in stress])
            ),
            "mean_stress_organic_to_paper_rate": float(
                np.mean([row["organic_to_paper_rate"] for row in stress])
            ),
        }
        output[model_name] = profile_results

    v6 = output["v6_int8"]
    clean_min_recall = min(
        float(v6["clean"]["per_class"][label]["recall"]) for label in LABELS
    )
    gates = {
        "clean_macro_f1_passed": v6["clean"]["macro_f1"] >= args.min_clean_macro_f1,
        "clean_min_recall_passed": clean_min_recall >= args.min_class_recall,
        "mean_stress_macro_f1_passed": (
            v6["summary"]["mean_stress_macro_f1"] >= args.min_stress_macro_f1
        ),
        "clean_organic_to_paper_passed": (
            v6["clean"]["organic_to_paper_rate"] <= args.max_organic_to_paper
        ),
        "stress_organic_to_paper_passed": (
            v6["summary"]["mean_stress_organic_to_paper_rate"]
            <= args.max_organic_to_paper
        ),
    }
    payload = {
        "dataset_sha256": index.dataset_sha256,
        "test_samples": len(samples),
        "labels": list(LABELS),
        "profiles": list(PROFILE_NAMES),
        "profile_semantics": (
            "Deterministic transformations of the untouched V6 test split; useful "
            "for relative robustness, not a substitute for new physical-camera images. "
            "V6 uses RGB565 plus luma normalization; the V4 baseline uses RGB565 only."
        ),
        "models": output,
        "thresholds": {
            "min_clean_macro_f1": args.min_clean_macro_f1,
            "min_clean_class_recall": args.min_class_recall,
            "min_mean_stress_macro_f1": args.min_stress_macro_f1,
            "max_organic_to_paper_rate": args.max_organic_to_paper,
        },
        "gates": gates,
        "passed": all(gates.values()),
    }
    out_dir = args.out.expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    write_json_atomic(out_dir / "environmental_robustness.json", payload)
    _write_predictions(out_dir / "environmental_predictions.csv", prediction_rows)
    _write_profile_chart(out_dir / "environmental_robustness.png", output)
    print(json.dumps(payload, indent=2, ensure_ascii=False))


def apply_profile(image: np.ndarray, profile: str, seed: int) -> np.ndarray:
    values = np.clip(np.asarray(image, dtype=np.float32), 0.0, 1.0)
    rng = np.random.default_rng(seed)
    if profile == "clean":
        return values
    if profile == "low_light":
        return np.clip(np.power(values, 1.55) * 0.72, 0.0, 1.0)
    if profile == "overexposed":
        return np.clip(np.power(values, 0.72) * 1.16 + 0.055, 0.0, 1.0)
    if profile == "warm_cast":
        return np.clip(values * np.asarray([1.18, 1.02, 0.78]), 0.0, 1.0)
    if profile == "cool_cast":
        return np.clip(values * np.asarray([0.80, 0.98, 1.18]), 0.0, 1.0)
    if profile == "angle_plus20":
        return _rotate(values, 20.0)
    if profile == "angle_minus20":
        return _rotate(values, -20.0)
    if profile == "shadow_rgb565":
        ramp = np.linspace(0.46, 1.0, values.shape[1], dtype=np.float32)[None, :, None]
        transformed = values * ramp
        transformed = _rgb565(transformed)
        return np.clip(transformed + rng.normal(0.0, 0.014, transformed.shape), 0.0, 1.0)
    if profile == "combined_hard":
        transformed = _rotate(values, float(rng.uniform(-25.0, 25.0)))
        gamma = float(rng.choice([0.66, 1.48]))
        transformed = np.power(np.clip(transformed, 0.0, 1.0), gamma)
        gains = rng.uniform(0.78, 1.20, size=(1, 1, 3))
        transformed = np.clip(transformed * gains, 0.0, 1.0)
        pil = Image.fromarray(np.rint(transformed * 255.0).astype(np.uint8), "RGB")
        pil = pil.resize((62, 62), Image.Resampling.BILINEAR).filter(
            ImageFilter.GaussianBlur(radius=0.45)
        )
        pil = pil.resize((96, 96), Image.Resampling.NEAREST)
        transformed = np.asarray(pil, dtype=np.float32) / 255.0
        transformed = _rgb565(transformed)
        return np.clip(transformed + rng.normal(0.0, 0.022, transformed.shape), 0.0, 1.0)
    raise ValueError(f"Unknown profile: {profile}")


def _apply_input_contract(image: np.ndarray) -> np.ndarray:
    pixels = np.rint(np.clip(image, 0.0, 1.0) * 255.0).astype(np.uint8)
    contracted = apply_input_contract_u8(tf.convert_to_tensor(pixels))
    return contracted.numpy().astype(np.float32) / 255.0


def _apply_v4_input_contract(image: np.ndarray) -> np.ndarray:
    """Match the deployed V4 camera path without V6 luma normalization."""

    pixels = np.rint(np.clip(image, 0.0, 1.0) * 255.0).astype(np.uint8)
    contracted = simulate_rgb565_u8(tf.convert_to_tensor(pixels))
    return contracted.numpy().astype(np.float32) / 255.0


def _rotate(image: np.ndarray, degrees: float) -> np.ndarray:
    array = np.rint(np.clip(image, 0.0, 1.0) * 255.0).astype(np.uint8)
    fill = tuple(int(value) for value in np.median(array.reshape(-1, 3), axis=0))
    rotated = Image.fromarray(array, "RGB").rotate(
        degrees,
        resample=Image.Resampling.BILINEAR,
        expand=False,
        fillcolor=fill,
    )
    return np.asarray(rotated, dtype=np.float32) / 255.0


def _rgb565(image: np.ndarray) -> np.ndarray:
    levels = np.asarray([31.0, 63.0, 31.0], dtype=np.float32)
    return np.floor(np.clip(image, 0.0, 1.0) * levels) / levels


def _predict_images(predictor: object, images: np.ndarray) -> np.ndarray:
    if isinstance(predictor, KerasPredictor):
        return np.asarray(predictor.model.predict(images, batch_size=64, verbose=0))
    if isinstance(predictor, TFLitePredictor):
        return np.vstack([predictor.predict_one(image) for image in images])
    raise TypeError(f"Unsupported predictor: {type(predictor)}")


def _profile_metrics(truth: np.ndarray, logits: np.ndarray) -> dict:
    metrics = classification_metrics(truth, logits)
    predictions = np.argmax(logits, axis=1)
    organic_id = LABELS.index("organic")
    paper_id = LABELS.index("paper")
    organic_mask = truth == organic_id
    organic_to_paper = int(np.sum(organic_mask & (predictions == paper_id)))
    metrics["organic_predicted_as_paper"] = organic_to_paper
    metrics["organic_to_paper_rate"] = float(organic_to_paper / np.sum(organic_mask))
    return metrics


def _softmax(logits: np.ndarray) -> np.ndarray:
    shifted = logits - np.max(logits, axis=1, keepdims=True)
    exponentials = np.exp(shifted)
    return exponentials / np.sum(exponentials, axis=1, keepdims=True)


def _sample_seed(seed: int, relative_path: str, profile: str) -> int:
    payload = f"{seed}\0{relative_path}\0{profile}".encode("utf-8")
    return int.from_bytes(hashlib.sha256(payload).digest()[:8], "big")


def _write_predictions(path: Path, rows: list[dict[str, str | int | float]]) -> None:
    fieldnames = ["model", "profile", "relative_path", "actual", "predicted", "confidence"]
    temporary = path.with_name(f".{path.name}.tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def _write_profile_chart(path: Path, results: dict[str, dict]) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    names = list(PROFILE_NAMES)
    x = np.arange(len(names))
    width = 0.8 / len(results)
    fig, axis = plt.subplots(figsize=(13, 6))
    for index, (model_name, profiles) in enumerate(results.items()):
        values = [profiles[name]["macro_f1"] for name in names]
        axis.bar(x + (index - (len(results) - 1) / 2) * width, values, width, label=model_name)
    axis.set_ylim(0.0, 1.02)
    axis.set_ylabel("Macro-F1")
    axis.set_title("Clean and environmental robustness (untouched V6 test split)")
    axis.set_xticks(x, [name.replace("_", "\n") for name in names])
    axis.grid(axis="y", alpha=0.25)
    axis.legend()
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)


if __name__ == "__main__":
    main()
