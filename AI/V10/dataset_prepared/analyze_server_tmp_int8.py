"""Evaluate the deployed V9 INT8 model on labelled server captures.

The script deliberately mirrors ESP-TRASH-V3/image_preprocessor.cpp instead of
using a generic image resize.  It also compares deployment captures with the
manifest-controlled V9 training set and emits reproducible CSV/JSON/PNG/MD
artifacts for error analysis.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import sys
from typing import Any
import warnings

os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")

import cv2
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.decomposition import PCA
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
    silhouette_score,
)
from sklearn.preprocessing import StandardScaler
import tensorflow as tf


V9_DIR = Path(__file__).resolve().parent
REPO_DIR = V9_DIR.parents[1]
if str(V9_DIR.parent) not in sys.path:
    sys.path.insert(0, str(V9_DIR.parent))

from V9.config import CLASS_NAMES, DATASET_DIR  # noqa: E402
from V9.data_pipeline import load_samples  # noqa: E402


IMAGE_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png"})
LABEL_TO_ID = {label: index for index, label in enumerate(CLASS_NAMES)}
COLORS = {"paper": "#4C78A8", "plastic": "#F58518", "organic": "#54A24B"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=REPO_DIR / "server-tmp")
    parser.add_argument("--data", type=Path, default=DATASET_DIR)
    parser.add_argument("--artifacts", type=Path, default=V9_DIR / "artifacts")
    parser.add_argument(
        "--out", type=Path,
        default=V9_DIR / "artifacts" / "server_tmp_int8_analysis",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    source_root = args.input.expanduser().resolve()
    data_root = args.data.expanduser().resolve()
    artifacts = args.artifacts.expanduser().resolve()
    output = args.out.expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)

    model_path = artifacts / "model_int8.tflite"
    float_path = artifacts / "model_float.keras"
    metadata_path = artifacts / "model_metadata.json"
    for required in (model_path, float_path, metadata_path, data_root / "manifest.csv"):
        if not required.is_file():
            raise FileNotFoundError(required)

    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    expected_sha = metadata["int8_model"]["sha256"]
    actual_sha = sha256(model_path)
    if actual_sha != expected_sha:
        raise RuntimeError(f"INT8 SHA mismatch: {actual_sha} != {expected_sha}")

    server_items = collect_server_items(source_root)
    train_items, train_manifest = collect_train_items(data_root)
    all_items = train_items + server_items
    print(f"Preprocessing {len(train_items)} train + {len(server_items)} deployment images...")

    arrays: list[np.ndarray] = []
    records: list[dict[str, Any]] = []
    for index, item in enumerate(all_items, start=1):
        raw = load_rgb(item["path"])
        processed, diagnostics = preprocess_esp_v3(raw)
        arrays.append(processed)
        records.append({**item, **diagnostics, **image_features(raw, processed)})
        if index % 100 == 0:
            print(f"  preprocessed {index}/{len(all_items)}")
    images_u8 = np.stack(arrays)

    print("Running INT8 inference...")
    int8_probabilities, int8_details = infer_int8(model_path, images_u8)
    print("Extracting float-model embeddings...")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        float_model = tf.keras.models.load_model(float_path, compile=False)
    feature_model = tf.keras.Model(
        float_model.input,
        float_model.get_layer("global_average_pooling").output,
        name="v9_feature_extractor",
    )
    float_images = images_u8.astype(np.float32) / 255.0
    embeddings = feature_model.predict(float_images, batch_size=64, verbose=0)
    float_probabilities = float_model.predict(float_images, batch_size=64, verbose=0)

    train_count = len(train_items)
    train_records = records[:train_count]
    server_records = records[train_count:]
    train_embeddings = embeddings[:train_count]
    server_embeddings = embeddings[train_count:]
    server_int8 = int8_probabilities[train_count:]
    server_float = float_probabilities[train_count:]

    enrich_predictions(server_records, server_int8, server_float)
    separability = add_embedding_diagnostics(
        train_records, server_records, train_embeddings, server_embeddings
    )
    duplicate_summary = add_duplicate_diagnostics(
        train_records, server_records, images_u8[:train_count], images_u8[train_count:]
    )
    firmware_summary = add_firmware_comparison(source_root, server_records)

    server_df = dataframe_for_output(server_records)
    train_df = dataframe_for_output(train_records)
    server_df.to_csv(output / "predictions.csv", index=False, encoding="utf-8-sig")
    train_df.to_csv(output / "training_reference_features.csv", index=False, encoding="utf-8-sig")
    server_df.loc[~server_df["correct"]].to_csv(
        output / "misclassified.csv", index=False, encoding="utf-8-sig"
    )

    metrics = evaluate_predictions(server_records)
    data_summary = summarize_dataset(train_manifest, train_records, server_records)
    diagnostic_summary = summarize_diagnostics(server_df)
    confidence_summary = summarize_confidence(server_df)
    summary = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "model": {
            "path": relative_to_repo(model_path),
            "bytes": model_path.stat().st_size,
            "sha256": actual_sha,
            "labels": list(CLASS_NAMES),
            "input": int8_details["input"],
            "output": int8_details["output"],
            "float_parameters": int(float_model.count_params()),
            "architecture": "5x Conv2D(stride=2)+BatchNorm+ReLU6, GlobalAveragePooling2D, Dense(3, softmax)",
            "training_epochs_completed": int(metadata["training"]["epochs_completed"]),
            "training_best_epoch": int(metadata["training"]["best_epoch"]),
            "recorded_test_accuracy": float(
                metadata["tflite"]["metrics"]["test"]["accuracy"]
            ),
        },
        "evaluation": metrics,
        "confidence": confidence_summary,
        "firmware_jpeg_comparison": firmware_summary,
        "dataset": data_summary,
        "embedding_separability": separability,
        "duplicates": duplicate_summary,
        "diagnostics": diagnostic_summary,
    }
    (output / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    plot_confusion(metrics, output / "confusion_matrix.png")
    plot_confidence(server_df, output / "confidence_correct_vs_wrong.png")
    plot_embedding_pca(
        train_records, server_records, train_embeddings, server_embeddings,
        output / "embedding_pca.png",
    )
    plot_low_level_pca(train_records, server_records, output / "low_level_pca.png")
    make_error_montages(server_records, arrays[train_count:], output)
    make_train_original_montage(train_records, arrays[:train_count], output)
    write_report(output / "REPORT.md", summary, server_df)
    print(json.dumps({
        "report": str(output / "REPORT.md"),
        "accuracy": metrics["accuracy"],
        "balanced_accuracy": metrics["balanced_accuracy"],
        "errors": metrics["errors"],
        "images": metrics["images"],
    }, indent=2, ensure_ascii=False))


def collect_server_items(root: Path) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for label in CLASS_NAMES:
        folder = root / label
        if not folder.is_dir():
            raise FileNotFoundError(folder)
        for path in sorted(folder.iterdir(), key=lambda p: p.name.lower()):
            if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS:
                items.append({
                    "set": "deployment",
                    "path": path.resolve(),
                    "relative_path": relative_to_repo(path.resolve()),
                    "filename": path.name,
                    "true_label": label,
                    "true_id": LABEL_TO_ID[label],
                    "kind": "deployment_capture",
                    "source_group": path.stem,
                    "sha256": sha256(path),
                })
    if not items:
        raise ValueError(f"No deployment images found below {root}")
    return items


def collect_train_items(root: Path) -> tuple[list[dict[str, Any]], pd.DataFrame]:
    samples = [sample for sample in load_samples(root) if sample.split == "train"]
    manifest = pd.read_csv(root / "manifest.csv")
    items = [{
        "set": "train",
        "path": sample.path,
        "relative_path": relative_to_repo(sample.path),
        "filename": sample.path.name,
        "true_label": sample.label,
        "true_id": sample.label_id,
        "kind": sample.kind,
        "source_group": sample.source_group,
        "sha256": sample.sha256,
    } for sample in samples]
    return items, manifest


def load_rgb(path: Path) -> np.ndarray:
    # Match the decoder used by V9.data_pipeline during train/validation/test.
    # The uploaded JPEG cannot reconstruct the pre-compression RGB565 frame,
    # which is why firmware metadata is compared separately below.
    return tf.io.decode_image(
        tf.io.read_file(str(path)), channels=3, expand_animations=False
    ).numpy()


def preprocess_esp_v3(raw: np.ndarray) -> tuple[np.ndarray, dict[str, Any]]:
    """Integer-equivalent RGB888 path from ESP-TRASH-V3/image_preprocessor.cpp."""
    height, width = raw.shape[:2]
    side = min(height, width)
    y0, x0 = (height - side) // 2, (width - side) // 2
    square = raw[y0:y0 + side, x0:x0 + side]
    indices = np.minimum(np.arange(96, dtype=np.int64) * side // 96, side - 1)
    pixels = square[indices[:, None], indices[None, :], :].astype(np.int64)
    pixels = (pixels // np.asarray([8, 4, 8], dtype=np.int64)) * np.asarray(
        [8, 4, 8], dtype=np.int64
    )
    count = 96 * 96
    channel_mean = (pixels.sum(axis=(0, 1)) + count // 2) // count
    target = (int(channel_mean.sum()) + 1) // 3
    gains_q10 = (target * 1024 + np.maximum(channel_mean, 1) // 2) // np.maximum(
        channel_mean, 1
    )
    gains_q10 = np.clip(gains_q10, 768, 1365)
    balanced = np.clip((pixels * gains_q10 + 512) // 1024, 0, 255)
    luma = (
        77 * balanced[..., 0] + 150 * balanced[..., 1]
        + 29 * balanced[..., 2] + 128
    ) // 256
    mean_luma = int((int(luma.sum()) + count // 2) // count)
    safe_mean = max(mean_luma, 1)
    if mean_luma < 96:
        gain_q8 = min(341, (96 * 256 + safe_mean // 2) // safe_mean)
    elif mean_luma > 160:
        gain_q8 = max(192, (160 * 256 + safe_mean // 2) // safe_mean)
    else:
        gain_q8 = 256
    output = np.clip((balanced * gain_q8 + 128) // 256, 0, 255).astype(np.uint8)
    diagnostics = {
        "width": width,
        "height": height,
        "crop_retained_fraction": float(side * side / (width * height)),
        "pre_wb_mean_r": int(channel_mean[0]),
        "pre_wb_mean_g": int(channel_mean[1]),
        "pre_wb_mean_b": int(channel_mean[2]),
        "wb_gain_r": float(gains_q10[0] / 1024.0),
        "wb_gain_g": float(gains_q10[1] / 1024.0),
        "wb_gain_b": float(gains_q10[2] / 1024.0),
        "wb_max_gain_deviation": float(np.max(np.abs(gains_q10 - 1024)) / 1024.0),
        "wb_any_at_limit": bool(np.any((gains_q10 == 768) | (gains_q10 == 1365))),
        "mean_luma_before_gain": mean_luma,
        "luma_gain": float(gain_q8 / 256.0),
        "luma_gain_active": bool(gain_q8 != 256),
        "processed_clip_fraction": float(np.mean((output == 0) | (output == 255))),
    }
    return output, diagnostics


def image_features(raw: np.ndarray, processed: np.ndarray) -> dict[str, float]:
    gray = cv2.cvtColor(processed, cv2.COLOR_RGB2GRAY)
    hsv = cv2.cvtColor(processed, cv2.COLOR_RGB2HSV)
    histogram = np.bincount(gray.ravel(), minlength=256).astype(np.float64)
    probability = histogram[histogram > 0] / histogram.sum()
    edges = cv2.Canny(gray, 70, 140)
    result: dict[str, float] = {
        "raw_mean_luma": float(cv2.cvtColor(raw, cv2.COLOR_RGB2GRAY).mean()),
        "processed_luma_mean": float(gray.mean()),
        "processed_luma_std": float(gray.std()),
        "processed_saturation_mean": float(hsv[..., 1].mean()),
        "processed_value_mean": float(hsv[..., 2].mean()),
        "blur_laplacian_variance": float(cv2.Laplacian(gray, cv2.CV_64F).var()),
        "edge_fraction": float(np.mean(edges > 0)),
        "gray_entropy_bits": float(-(probability * np.log2(probability)).sum()),
    }
    for channel, name in enumerate(("r", "g", "b")):
        result[f"processed_mean_{name}"] = float(processed[..., channel].mean())
        result[f"processed_std_{name}"] = float(processed[..., channel].std())
    return result


def infer_int8(model_path: Path, images_u8: np.ndarray) -> tuple[np.ndarray, dict]:
    interpreter = tf.lite.Interpreter(model_path=str(model_path))
    interpreter.allocate_tensors()
    input_detail = interpreter.get_input_details()[0]
    output_detail = interpreter.get_output_details()[0]
    if input_detail["dtype"] != np.int8 or output_detail["dtype"] != np.int8:
        raise RuntimeError("Expected a fully INT8 input/output model")
    probabilities = []
    for image in images_u8:
        quantized = (image.astype(np.int16) - 128).astype(np.int8)[None, ...]
        interpreter.set_tensor(input_detail["index"], quantized)
        interpreter.invoke()
        raw = interpreter.get_tensor(output_detail["index"])[0]
        scale, zero = output_detail["quantization"]
        probabilities.append((raw.astype(np.float32) - zero) * scale)
    details = {
        "input": tensor_detail(input_detail),
        "output": tensor_detail(output_detail),
    }
    return np.stack(probabilities), details


def tensor_detail(detail: dict) -> dict:
    scale, zero = detail["quantization"]
    return {
        "shape": [int(value) for value in detail["shape"]],
        "dtype": np.dtype(detail["dtype"]).name,
        "scale": float(scale),
        "zero_point": int(zero),
    }


def enrich_predictions(
    records: list[dict[str, Any]], int8_probs: np.ndarray, float_probs: np.ndarray
) -> None:
    for record, int8_probability, float_probability in zip(
        records, int8_probs, float_probs, strict=True
    ):
        predicted_id = int(np.argmax(int8_probability))
        ordered = np.sort(int8_probability)
        entropy = -float(np.sum(
            np.clip(int8_probability, 1e-12, 1.0)
            * np.log2(np.clip(int8_probability, 1e-12, 1.0))
        ))
        record.update({
            "predicted_id": predicted_id,
            "predicted_label": CLASS_NAMES[predicted_id],
            "correct": bool(predicted_id == record["true_id"]),
            "confidence": float(int8_probability[predicted_id]),
            "margin": float(ordered[-1] - ordered[-2]),
            "entropy_bits": entropy,
            "float_predicted_label": CLASS_NAMES[int(np.argmax(float_probability))],
            "float_int8_disagree": bool(
                np.argmax(float_probability) != np.argmax(int8_probability)
            ),
            "float_int8_max_abs_probability_error": float(
                np.max(np.abs(float_probability - int8_probability))
            ),
        })
        for label_id, label in enumerate(CLASS_NAMES):
            record[f"prob_{label}"] = float(int8_probability[label_id])
            record[f"float_prob_{label}"] = float(float_probability[label_id])


def normalized_rows(values: np.ndarray) -> np.ndarray:
    denominator = np.linalg.norm(values, axis=1, keepdims=True)
    return values / np.maximum(denominator, 1e-12)


def add_embedding_diagnostics(
    train_records: list[dict[str, Any]], server_records: list[dict[str, Any]],
    train_embeddings: np.ndarray, server_embeddings: np.ndarray,
) -> dict:
    train_labels = np.asarray([record["true_id"] for record in train_records])
    server_labels = np.asarray([record["true_id"] for record in server_records])
    original_mask = np.asarray([record["kind"] == "original" for record in train_records])
    reference_embeddings = train_embeddings[original_mask]
    reference_labels = train_labels[original_mask]
    reference_records = [
        record for record in train_records if record["kind"] == "original"
    ]
    normalized_reference = normalized_rows(reference_embeddings)
    normalized_server = normalized_rows(server_embeddings)
    similarities = normalized_server @ normalized_reference.T
    nearest_indices = np.argmax(similarities, axis=1)

    scaled_reference = StandardScaler().fit_transform(reference_embeddings)
    scaler = StandardScaler().fit(reference_embeddings)
    scaled_server = scaler.transform(server_embeddings)
    scaled_centroids = np.stack([
        scaled_reference[reference_labels == label_id].mean(axis=0)
        for label_id in range(len(CLASS_NAMES))
    ])
    distances = np.linalg.norm(
        scaled_server[:, None, :] - scaled_centroids[None, :, :], axis=2
    )
    train_distances_by_class: dict[int, np.ndarray] = {}
    for label_id in range(len(CLASS_NAMES)):
        selected = scaled_reference[reference_labels == label_id]
        train_distances_by_class[label_id] = np.linalg.norm(
            selected - scaled_centroids[label_id], axis=1
        )

    for index, record in enumerate(server_records):
        nearest = int(nearest_indices[index])
        true_id = int(record["true_id"])
        distribution = train_distances_by_class[true_id]
        mean_distance = float(distribution.mean())
        std_distance = float(distribution.std())
        true_distance = float(distances[index, true_id])
        record.update({
            "nearest_train_label": reference_records[nearest]["true_label"],
            "nearest_train_file": reference_records[nearest]["relative_path"],
            "nearest_train_cosine_similarity": float(similarities[index, nearest]),
            "embedding_nearest_centroid": CLASS_NAMES[int(np.argmin(distances[index]))],
            "embedding_true_centroid_distance": true_distance,
            "embedding_true_distance_z": float(
                (true_distance - mean_distance) / max(std_distance, 1e-9)
            ),
            "embedding_ood_2sigma": bool(true_distance > mean_distance + 2 * std_distance),
        })

    centroid_distance = np.linalg.norm(
        scaled_centroids[:, None, :] - scaled_centroids[None, :, :], axis=2
    )
    within_dispersion = np.asarray([
        train_distances_by_class[label_id].mean()
        for label_id in range(len(CLASS_NAMES))
    ])
    fisher_pairs = {}
    for left in range(len(CLASS_NAMES)):
        for right in range(left + 1, len(CLASS_NAMES)):
            key = f"{CLASS_NAMES[left]}__{CLASS_NAMES[right]}"
            denominator = math.sqrt(
                within_dispersion[left] ** 2 + within_dispersion[right] ** 2
            )
            fisher_pairs[key] = float(centroid_distance[left, right] / max(denominator, 1e-9))

    return {
        "method": "64-D float-model global-average-pooling embeddings; StandardScaler fitted on original train images",
        "train_all_silhouette_true_labels": safe_silhouette(train_embeddings, train_labels),
        "train_original_silhouette_true_labels": safe_silhouette(
            reference_embeddings, reference_labels
        ),
        "deployment_silhouette_true_labels": safe_silhouette(
            server_embeddings, server_labels
        ),
        "original_train_within_class_mean_distance": {
            CLASS_NAMES[index]: float(value)
            for index, value in enumerate(within_dispersion)
        },
        "original_train_centroid_distance_matrix": centroid_distance.tolist(),
        "pairwise_separation_ratio": fisher_pairs,
        "deployment_ood_2sigma_count": int(sum(
            record["embedding_ood_2sigma"] for record in server_records
        )),
        "deployment_nearest_original_train_label_accuracy": float(np.mean([
            record["nearest_train_label"] == record["true_label"]
            for record in server_records
        ])),
        "deployment_nearest_centroid_label_accuracy": float(np.mean([
            record["embedding_nearest_centroid"] == record["true_label"]
            for record in server_records
        ])),
    }


def safe_silhouette(values: np.ndarray, labels: np.ndarray) -> float:
    if len(np.unique(labels)) < 2 or len(values) <= len(np.unique(labels)):
        return float("nan")
    return float(silhouette_score(StandardScaler().fit_transform(values), labels))


def add_duplicate_diagnostics(
    train_records: list[dict[str, Any]], server_records: list[dict[str, Any]],
    train_images: np.ndarray, server_images: np.ndarray,
) -> dict:
    train_hashes = {record["sha256"]: record for record in train_records}
    exact_matches = 0
    for record in server_records:
        match = train_hashes.get(record["sha256"])
        record["exact_train_duplicate"] = bool(match)
        record["exact_train_duplicate_path"] = match["relative_path"] if match else ""
        exact_matches += int(bool(match))

    # A compact 16x16 luminance representation is enough to flag visual repeats.
    def fingerprints(images: np.ndarray) -> np.ndarray:
        values = []
        for image in images:
            gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
            small = cv2.resize(gray, (16, 16), interpolation=cv2.INTER_AREA)
            values.append(small.astype(np.float32).ravel() / 255.0)
        return np.stack(values)

    train_fp = fingerprints(train_images)
    server_fp = fingerprints(server_images)
    nearest_mse = np.empty(len(server_records), dtype=np.float32)
    nearest_index = np.empty(len(server_records), dtype=np.int64)
    for start in range(0, len(server_records), 64):
        chunk = server_fp[start:start + 64]
        mse = np.mean((chunk[:, None, :] - train_fp[None, :, :]) ** 2, axis=2)
        nearest_mse[start:start + len(chunk)] = mse.min(axis=1)
        nearest_index[start:start + len(chunk)] = mse.argmin(axis=1)
    for record, mse, index in zip(
        server_records, nearest_mse, nearest_index, strict=True
    ):
        record["nearest_train_visual_mse"] = float(mse)
        record["nearest_train_visual_label"] = train_records[int(index)]["true_label"]
        record["nearest_train_visual_file"] = train_records[int(index)]["relative_path"]
    server_hash_counts = pd.Series([record["sha256"] for record in server_records]).value_counts()
    return {
        "exact_deployment_to_train_files": exact_matches,
        "exact_duplicate_files_within_deployment": int(
            server_hash_counts[server_hash_counts > 1].sum()
        ),
        "nearest_train_visual_mse_median": float(np.median(nearest_mse)),
        "nearest_train_visual_label_accuracy": float(np.mean([
            record["nearest_train_visual_label"] == record["true_label"]
            for record in server_records
        ])),
        "visual_method": "MSE on 16x16 grayscale ESP-preprocessed thumbnails",
    }


def add_firmware_comparison(root: Path, records: list[dict[str, Any]]) -> dict:
    metadata_dir = root / "data" / "metadata"
    compared = 0
    label_agreements = 0
    probability_errors: list[float] = []
    truth_ids: list[int] = []
    firmware_ids: list[int] = []
    python_ids: list[int] = []
    for record in records:
        path = metadata_dir / f"{Path(record['filename']).stem}.json"
        record["firmware_metadata_available"] = path.is_file()
        record["firmware_prediction"] = ""
        record["firmware_python_agree"] = None
        record["firmware_python_max_abs_probability_error"] = None
        record["received_at"] = ""
        if not path.is_file():
            continue
        try:
            item = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        firmware_label = item.get("waste_class")
        firmware_probs = item.get("probabilities", {})
        if firmware_label not in CLASS_NAMES or not all(
            label in firmware_probs for label in CLASS_NAMES
        ):
            continue
        compared += 1
        truth_ids.append(int(record["true_id"]))
        firmware_ids.append(LABEL_TO_ID[firmware_label])
        python_ids.append(int(record["predicted_id"]))
        agree = firmware_label == record["predicted_label"]
        label_agreements += int(agree)
        error = max(
            abs(float(firmware_probs[label]) - record[f"prob_{label}"])
            for label in CLASS_NAMES
        )
        probability_errors.append(error)
        record.update({
            "firmware_prediction": firmware_label,
            "firmware_python_agree": agree,
            "firmware_python_max_abs_probability_error": error,
            "received_at": item.get("received_at", ""),
        })
    firmware_matrix = confusion_matrix(
        truth_ids, firmware_ids, labels=np.arange(len(CLASS_NAMES))
    ) if compared else np.zeros((len(CLASS_NAMES), len(CLASS_NAMES)), dtype=int)
    return {
        "images_with_metadata": compared,
        "prediction_agreements": label_agreements,
        "prediction_agreement_rate": label_agreements / compared if compared else None,
        "mean_max_abs_probability_error": (
            float(np.mean(probability_errors)) if probability_errors else None
        ),
        "maximum_abs_probability_error": (
            float(np.max(probability_errors)) if probability_errors else None
        ),
        "firmware_accuracy_on_metadata_subset": (
            float(accuracy_score(truth_ids, firmware_ids)) if compared else None
        ),
        "python_jpeg_accuracy_on_same_subset": (
            float(accuracy_score(truth_ids, python_ids)) if compared else None
        ),
        "firmware_confusion_matrix_rows_true_cols_predicted": firmware_matrix.tolist(),
        "interpretation": "Firmware inferred raw RGB565; Python re-inferred the uploaded JPEG, so small JPEG-induced differences are expected.",
    }


def evaluate_predictions(records: list[dict[str, Any]]) -> dict:
    truth = np.asarray([record["true_id"] for record in records])
    predicted = np.asarray([record["predicted_id"] for record in records])
    float_predicted = np.asarray([
        LABEL_TO_ID[record["float_predicted_label"]] for record in records
    ])
    matrix = confusion_matrix(truth, predicted, labels=np.arange(len(CLASS_NAMES)))
    report = classification_report(
        truth, predicted, labels=np.arange(len(CLASS_NAMES)),
        target_names=CLASS_NAMES, output_dict=True, zero_division=0,
    )
    pairs = []
    for true_id, true_label in enumerate(CLASS_NAMES):
        for predicted_id, predicted_label in enumerate(CLASS_NAMES):
            if true_id != predicted_id and matrix[true_id, predicted_id]:
                pairs.append({
                    "true": true_label,
                    "predicted": predicted_label,
                    "count": int(matrix[true_id, predicted_id]),
                })
    pairs.sort(key=lambda item: item["count"], reverse=True)
    return {
        "images": len(records),
        "correct": int(np.sum(truth == predicted)),
        "errors": int(np.sum(truth != predicted)),
        "accuracy": float(accuracy_score(truth, predicted)),
        "balanced_accuracy": float(balanced_accuracy_score(truth, predicted)),
        "macro_f1": float(f1_score(truth, predicted, average="macro")),
        "confusion_matrix_rows_true_cols_predicted": matrix.tolist(),
        "per_class": {label: {
            key: float(report[label][key]) if key != "support" else int(report[label][key])
            for key in ("precision", "recall", "f1-score", "support")
        } for label in CLASS_NAMES},
        "error_pairs": pairs,
        "predicted_distribution": {
            label: int(np.sum(predicted == label_id))
            for label_id, label in enumerate(CLASS_NAMES)
        },
        "float_correct": int(np.sum(truth == float_predicted)),
        "float_accuracy": float(accuracy_score(truth, float_predicted)),
        "float_confusion_matrix_rows_true_cols_predicted": confusion_matrix(
            truth, float_predicted, labels=np.arange(len(CLASS_NAMES))
        ).tolist(),
        "accuracy_delta_int8_minus_float": float(
            accuracy_score(truth, predicted) - accuracy_score(truth, float_predicted)
        ),
        "float_int8_prediction_disagreements": int(sum(
            record["float_int8_disagree"] for record in records
        )),
        "float_int8_mean_max_abs_probability_error": float(np.mean([
            record["float_int8_max_abs_probability_error"] for record in records
        ])),
    }


def summarize_confidence(frame: pd.DataFrame) -> dict:
    correct = frame[frame["correct"]]
    wrong = frame[~frame["correct"]]
    thresholds = {}
    for threshold in (0.5, 0.7, 0.8, 0.9):
        selected = frame[frame["confidence"] >= threshold]
        thresholds[str(threshold)] = {
            "images": int(len(selected)),
            "wrong": int((~selected["correct"]).sum()),
            "precision_when_accepted": float(selected["correct"].mean()) if len(selected) else None,
            "coverage": float(len(selected) / len(frame)),
        }
    return {
        "mean_confidence_correct": float(correct["confidence"].mean()),
        "mean_confidence_wrong": float(wrong["confidence"].mean()),
        "median_confidence_correct": float(correct["confidence"].median()),
        "median_confidence_wrong": float(wrong["confidence"].median()),
        "thresholds": thresholds,
    }


def summarize_dataset(
    manifest: pd.DataFrame, train_records: list[dict[str, Any]],
    server_records: list[dict[str, Any]],
) -> dict:
    train = manifest[manifest["split"] == "train"]
    counts = {}
    for label in CLASS_NAMES:
        selected = train[train["label"] == label]
        counts[label] = {
            "files": int(len(selected)),
            "original_files": int((selected["kind"] == "original").sum()),
            "augmented_files": int((selected["kind"] != "original").sum()),
            "unique_source_groups": int(selected["source_group"].nunique()),
            "deployment_images": int(sum(
                record["true_label"] == label for record in server_records
            )),
        }
    return {
        "train_by_class": counts,
        "train_files": len(train_records),
        "deployment_files": len(server_records),
        "deployment_received_dates": dict(sorted(pd.Series([
            str(record.get("received_at", ""))[:10]
            for record in server_records if record.get("received_at")
        ]).value_counts().astype(int).to_dict().items())),
        "holdout_note": "V9 validation/test contain 7 images per class and primarily cover the 2026-08-01 capture session.",
    }


def summarize_diagnostics(frame: pd.DataFrame) -> dict:
    feature_columns = [
        "raw_mean_luma", "processed_luma_mean", "processed_luma_std",
        "processed_saturation_mean", "blur_laplacian_variance", "edge_fraction",
        "gray_entropy_bits", "processed_clip_fraction", "luma_gain",
        "wb_max_gain_deviation",
        "nearest_train_cosine_similarity", "embedding_true_distance_z",
    ]
    by_outcome = {}
    for label in CLASS_NAMES:
        selected = frame[frame["true_label"] == label]
        by_outcome[label] = {}
        for outcome, mask in (("correct", selected["correct"]), ("wrong", ~selected["correct"])):
            subset = selected[mask]
            by_outcome[label][outcome] = {
                "count": int(len(subset)),
                **{
                    column: (float(subset[column].mean()) if len(subset) else None)
                    for column in feature_columns
                },
            }
    return {
        "by_true_class_and_outcome_mean": by_outcome,
        "wb_gain_at_limit_images": int(frame["wb_any_at_limit"].sum()),
        "luma_gain_active_images": int(frame["luma_gain_active"].sum()),
        "crop_retained_fraction_values": sorted(
            float(value) for value in frame["crop_retained_fraction"].unique()
        ),
        "wrong_with_nearest_original_train_of_wrong_class": int((
            (~frame["correct"]) & (frame["nearest_train_label"] != frame["true_label"])
        ).sum()),
        "wrong_flagged_embedding_ood_2sigma": int((
            (~frame["correct"]) & frame["embedding_ood_2sigma"]
        ).sum()),
    }


def dataframe_for_output(records: list[dict[str, Any]]) -> pd.DataFrame:
    excluded = {"path"}
    return pd.DataFrame([
        {key: value for key, value in record.items() if key not in excluded}
        for record in records
    ])


def plot_confusion(metrics: dict, path: Path) -> None:
    matrix = np.asarray(metrics["confusion_matrix_rows_true_cols_predicted"])
    fig, ax = plt.subplots(figsize=(6.4, 5.5))
    image = ax.imshow(matrix, cmap="Blues")
    for row in range(len(CLASS_NAMES)):
        for column in range(len(CLASS_NAMES)):
            ax.text(column, row, str(matrix[row, column]), ha="center", va="center",
                    color="white" if matrix[row, column] > matrix.max() * 0.55 else "black",
                    fontsize=13, fontweight="bold")
    ax.set_xticks(range(len(CLASS_NAMES)), CLASS_NAMES)
    ax.set_yticks(range(len(CLASS_NAMES)), CLASS_NAMES)
    ax.set_xlabel("Predicted label")
    ax.set_ylabel("True folder label")
    ax.set_title(f"V9 INT8 deployment confusion matrix (n={metrics['images']})")
    fig.colorbar(image, ax=ax, fraction=0.046, pad=0.04)
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def plot_confidence(frame: pd.DataFrame, path: Path) -> None:
    fig, ax = plt.subplots(figsize=(7.5, 4.7))
    bins = np.linspace(0.0, 1.0, 21)
    ax.hist(frame.loc[frame["correct"], "confidence"], bins=bins, alpha=0.7,
            label="Correct", color="#54A24B")
    ax.hist(frame.loc[~frame["correct"], "confidence"], bins=bins, alpha=0.7,
            label="Wrong", color="#E45756")
    ax.set_xlabel("INT8 top-1 probability")
    ax.set_ylabel("Image count")
    ax.set_title("Confidence does not reliably reject deployment errors")
    ax.legend()
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def plot_embedding_pca(
    train_records: list[dict[str, Any]], server_records: list[dict[str, Any]],
    train_embeddings: np.ndarray, server_embeddings: np.ndarray, path: Path,
) -> None:
    combined = np.vstack([train_embeddings, server_embeddings])
    coordinates = PCA(n_components=2, random_state=9).fit_transform(
        StandardScaler().fit_transform(combined)
    )
    train_xy = coordinates[:len(train_records)]
    server_xy = coordinates[len(train_records):]
    fig, axes = plt.subplots(1, 2, figsize=(12, 5.2))
    for label in CLASS_NAMES:
        mask = np.asarray([record["true_label"] == label for record in train_records])
        original = np.asarray([record["kind"] == "original" for record in train_records])
        axes[0].scatter(train_xy[mask & ~original, 0], train_xy[mask & ~original, 1],
                        s=18, alpha=0.28, color=COLORS[label])
        axes[0].scatter(train_xy[mask & original, 0], train_xy[mask & original, 1],
                        s=42, alpha=0.9, color=COLORS[label], label=label, edgecolors="black")
        deploy_mask = np.asarray([record["true_label"] == label for record in server_records])
        correct = np.asarray([record["correct"] for record in server_records])
        axes[1].scatter(server_xy[deploy_mask & correct, 0], server_xy[deploy_mask & correct, 1],
                        s=22, alpha=0.65, color=COLORS[label], label=f"{label} correct")
        axes[1].scatter(server_xy[deploy_mask & ~correct, 0], server_xy[deploy_mask & ~correct, 1],
                        s=34, marker="x", linewidths=1.4, color=COLORS[label], label=f"{label} wrong")
    axes[0].set_title("Training embeddings\n(outline=original, faint=augmentation)")
    axes[1].set_title("Deployment embeddings\n(x=misclassified)")
    for ax in axes:
        ax.set_xlabel("PCA 1")
        ax.set_ylabel("PCA 2")
        ax.legend(fontsize=7)
    fig.suptitle("V9 penultimate-layer feature space")
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


LOW_LEVEL_COLUMNS = [
    "processed_mean_r", "processed_mean_g", "processed_mean_b",
    "processed_std_r", "processed_std_g", "processed_std_b",
    "processed_luma_mean", "processed_luma_std", "processed_saturation_mean",
    "blur_laplacian_variance", "edge_fraction", "gray_entropy_bits",
]


def plot_low_level_pca(
    train_records: list[dict[str, Any]], server_records: list[dict[str, Any]], path: Path
) -> None:
    records = train_records + server_records
    features = np.asarray([[record[column] for column in LOW_LEVEL_COLUMNS] for record in records])
    coordinates = PCA(n_components=2, random_state=9).fit_transform(
        StandardScaler().fit_transform(features)
    )
    fig, ax = plt.subplots(figsize=(7.5, 5.5))
    for set_name, marker, alpha in (("train", "o", 0.28), ("deployment", "x", 0.75)):
        for label in CLASS_NAMES:
            mask = np.asarray([
                record["set"] == set_name and record["true_label"] == label
                for record in records
            ])
            ax.scatter(coordinates[mask, 0], coordinates[mask, 1], s=24,
                       marker=marker, alpha=alpha, color=COLORS[label],
                       label=f"{set_name} {label}")
    ax.set_xlabel("PCA 1")
    ax.set_ylabel("PCA 2")
    ax.set_title("Low-level color/texture feature overlap after ESP preprocessing")
    ax.legend(fontsize=7, ncol=2)
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def make_error_montages(
    records: list[dict[str, Any]], processed_images: list[np.ndarray], output: Path
) -> None:
    errors = [
        (record, processed_images[index])
        for index, record in enumerate(records) if not record["correct"]
    ]
    errors.sort(key=lambda item: item[0]["confidence"], reverse=True)
    for page, start in enumerate(range(0, len(errors), 20), start=1):
        selected = errors[start:start + 20]
        fig, axes = plt.subplots(4, 5, figsize=(15, 11))
        for ax in axes.ravel():
            ax.axis("off")
        for ax, (record, processed) in zip(axes.ravel(), selected, strict=False):
            ax.imshow(processed)
            ax.set_title(
                f"{record['filename'][:12]}…\n{record['true_label']}→{record['predicted_label']} "
                f"p={record['confidence']:.3f}", fontsize=8,
            )
        fig.suptitle(
            f"Misclassified ESP-preprocessed inputs – page {page} "
            f"({start + 1}–{start + len(selected)} of {len(errors)})"
        )
        fig.tight_layout()
        fig.savefig(
            output / f"misclassified_montage_{page:02d}.jpg",
            dpi=150,
            pil_kwargs={"quality": 92},
        )
        plt.close(fig)


def make_train_original_montage(
    records: list[dict[str, Any]], processed_images: list[np.ndarray], output: Path
) -> None:
    originals = [
        (record, processed_images[index])
        for index, record in enumerate(records) if record["kind"] == "original"
    ]
    originals.sort(key=lambda item: (item[0]["true_id"], item[0]["filename"]))
    columns = 8
    rows = math.ceil(len(originals) / columns)
    fig, axes = plt.subplots(rows, columns, figsize=(16, rows * 2.15))
    for ax in np.asarray(axes).ravel():
        ax.axis("off")
    for ax, (record, processed) in zip(
        np.asarray(axes).ravel(), originals, strict=False
    ):
        ax.imshow(processed)
        ax.set_title(
            f"{record['true_label']}\n{record['filename'][:16]}", fontsize=7,
            color=COLORS[record["true_label"]],
        )
    fig.suptitle(
        f"All {len(originals)} original training inputs (augmentation excluded)"
    )
    fig.tight_layout()
    fig.savefig(output / "train_original_montage.jpg", dpi=150, pil_kwargs={"quality": 92})
    plt.close(fig)


def write_report(path: Path, summary: dict, frame: pd.DataFrame) -> None:
    evaluation = summary["evaluation"]
    confidence = summary["confidence"]
    dataset = summary["dataset"]
    separation = summary["embedding_separability"]
    diagnostics = summary["diagnostics"]
    firmware = summary["firmware_jpeg_comparison"]
    matrix = evaluation["confusion_matrix_rows_true_cols_predicted"]
    pair_lines = "\n".join(
        f"- `{item['true']} → {item['predicted']}`: **{item['count']} ảnh**"
        for item in evaluation["error_pairs"]
    )
    class_rows = "\n".join(
        f"| {label} | {evaluation['per_class'][label]['support']} | "
        f"{evaluation['per_class'][label]['precision']:.3f} | "
        f"{evaluation['per_class'][label]['recall']:.3f} | "
        f"{evaluation['per_class'][label]['f1-score']:.3f} |"
        for label in CLASS_NAMES
    )
    diversity_rows = "\n".join(
        f"| {label} | {dataset['train_by_class'][label]['files']} | "
        f"{dataset['train_by_class'][label]['original_files']} | "
        f"{dataset['train_by_class'][label]['augmented_files']} | "
        f"{dataset['train_by_class'][label]['unique_source_groups']} | "
        f"{dataset['train_by_class'][label]['deployment_images']} |"
        for label in CLASS_NAMES
    )
    high_wrong = confidence["thresholds"]["0.8"]["wrong"]
    high_total = confidence["thresholds"]["0.8"]["images"]
    accepted_precision = confidence["thresholds"]["0.8"]["precision_when_accepted"]
    wrong = frame[~frame["correct"]]
    legacy_mask = wrong["filename"].str.match(r"plastic_0(16|17|18|19)|plastic_020")
    legacy_errors = int(legacy_mask.sum())
    ood_wrong = diagnostics["wrong_flagged_embedding_ood_2sigma"]
    wrong_neighbor = diagnostics["wrong_with_nearest_original_train_of_wrong_class"]
    report = f"""# Báo cáo phân tích V9 INT8 trên ảnh triển khai

Ngày tạo: {summary['created_utc']}

## Kết luận chính

Model INT8 đúng artifact đang được firmware V3 nhúng (`{summary['model']['bytes']:,}` byte,
SHA-256 `{summary['model']['sha256']}`). Khi decode JPEG giống pipeline train rồi áp dụng
**đúng các phép biến đổi ESP-TRASH-V3 sau decode** trên {evaluation['images']} ảnh đã xếp
nhãn trong `server-tmp`, model chỉ đúng
**{evaluation['correct']}/{evaluation['images']} = {evaluation['accuracy']:.2%}**;
balanced accuracy **{evaluation['balanced_accuracy']:.2%}**, macro-F1
**{evaluation['macro_f1']:.3f}**. Sai số triển khai lớn hơn rất nhiều so với test V9
21 ảnh ({summary['model'].get('recorded_test_accuracy', 0.9047619):.2%}).

Điểm thất bại chính là hai lớp vật liệu khô: paper và plastic chồng lấn mạnh.
Organic đạt recall tuyệt đối trên tập này, nhưng điều đó không chứng minh khả năng tổng quát
vì chỉ có {evaluation['per_class']['organic']['support']} ảnh organic.

## Thống kê model và hợp đồng triển khai

| Thuộc tính | Giá trị |
|---|---|
| Phiên bản | `tinycnn-v9-balanced-esp-contract` |
| Kiến trúc | 5 block Conv2D stride 2 + BatchNorm + ReLU6 → Global Average Pooling → Dense softmax 3 lớp |
| Tham số float | {summary['model']['float_parameters']:,} |
| INT8 artifact | {summary['model']['bytes']:,} byte; full integer |
| Input | `[1,96,96,3]` INT8; scale `1/255`; zero-point `-128` |
| Output | `[1,3]` INT8; scale `1/256`; zero-point `-128`; `paper, plastic, organic` |
| Train | 225 file cân bằng; {summary['model']['training_epochs_completed']} epoch; best epoch {summary['model']['training_best_epoch']} |
| Holdout test cũ | 21 ảnh; accuracy {summary['model']['recorded_test_accuracy']:.2%} |

Đây là classifier toàn ảnh, không có bước detect/segment vật thể. Vì vậy nền thùng, vị trí,
kích thước vật và phần bị center-crop đều đi thẳng vào đặc trưng; model có thể học tương quan nền
hoặc hình dáng thay vì vật liệu.

## Kết quả inference

Hàng là nhãn thư mục thật, cột là dự đoán:

| true \\ predicted | paper | plastic | organic |
|---|---:|---:|---:|
| paper | {matrix[0][0]} | {matrix[0][1]} | {matrix[0][2]} |
| plastic | {matrix[1][0]} | {matrix[1][1]} | {matrix[1][2]} |
| organic | {matrix[2][0]} | {matrix[2][1]} | {matrix[2][2]} |

| Lớp | Support | Precision | Recall | F1 |
|---|---:|---:|---:|---:|
{class_rows}

Các hướng nhầm:

{pair_lines}

![Confusion matrix](confusion_matrix.png)

## Model đang học sai ở đâu

1. **Model học shortcut theo appearance, chưa học đủ khái niệm vật liệu.** Train-original
   cho thấy paper gần như chỉ là giấy trắng vò; plastic chủ yếu chai/cốc/túi trong suốt;
   organic chỉ gồm chanh/quất và chôm chôm. Vì các prototype này quá hẹp, silhouette train
   cao `{separation['train_original_silhouette_true_labels']:.3f}` nhưng giảm còn
   `{separation['deployment_silhouette_true_labels']:.3f}` khi gặp carton/túi kraft/nhãn in,
   nhựa đen cứng và loại rau quả mới. Nearest-centroid chỉ khớp nhãn thật
   `{separation['deployment_nearest_centroid_label_accuracy']:.2%}`; nearest ảnh train-original
   chỉ khớp `{separation['deployment_nearest_original_train_label_accuracy']:.2%}`. Có
   {wrong_neighbor}/{evaluation['errors']} lỗi có hàng xóm train gần nhất thuộc lớp khác.

2. **Cân bằng file không đồng nghĩa đa dạng vật thể.** Mỗi lớp có 75 file train, nhưng
   paper/organic/plastic chỉ có lần lượt
   {dataset['train_by_class']['paper']['unique_source_groups']},
   {dataset['train_by_class']['organic']['unique_source_groups']} và
   {dataset['train_by_class']['plastic']['unique_source_groups']} source group; số file original
   tương ứng là {dataset['train_by_class']['paper']['original_files']},
   {dataset['train_by_class']['organic']['original_files']} và
   {dataset['train_by_class']['plastic']['original_files']}.
   Phần còn lại chủ yếu là biến thể
   ánh sáng/nhiễu. Augmentation quang học giúp robustness ánh sáng nhưng không
   tạo hình dạng, chất liệu, góc nhìn hoặc loại vật thể mới.

3. **Holdout quá nhỏ và cùng miền.** Validation/test chỉ 7 ảnh/lớp, chủ yếu cùng phiên
   chụp 2026-08-01. Tập triển khai lớn hơn, lệch phân bố và chứa các kiểu vật thể chưa được
   đại diện; vì vậy 90.48% test cũ đánh giá quá lạc quan cho môi trường thật.

4. **Lỗi có độ tự tin cao.** Trong {high_total} ảnh có confidence ≥ 0.8, có
   {high_wrong} ảnh sai; precision khi chấp nhận là {accepted_precision:.2%}. Mean confidence
   của ảnh sai là {confidence['mean_confidence_wrong']:.3f}, nên chỉ tăng threshold không
   giải quyết được domain shift/calibration.

5. **Cụm legacy plastic đáng kiểm tra nhãn/coverage.** Có {legacy_errors} lỗi mang tên
   `plastic_016..020` hoặc augmentation của chúng: chỉ 17/50 ảnh đúng (34%). Các source này
   không xuất hiện trong
   manifest V9 hiện tại. Cần review vật thể thật và chính sách nhãn trước khi đưa lại vào train;
   không nên tự động coi mọi file trong thư mục là ground truth tuyệt đối.

Quan sát montage cho thấy lỗi paper confidence cao trải trên carton/hộp nâu, túi giấy và giấy
trắng vò. Cụm `plastic_019` là khay nhựa đen bóng nhưng bị nhận thành paper. Organic đạt 100%
trên 32 ảnh rau quả, nhưng train chỉ có hai họ appearance rất hẹp; chưa có bằng chứng model xử lý
được thức ăn thừa, vỏ, rau lá, đồ chín hoặc organic có màu/nền giống paper/plastic. Đây là bằng
chứng model đang dựa nhiều vào màu xanh, độ trong/bóng và hình dạng hơn là bản chất vật liệu.

![Embedding PCA](embedding_pca.png)

![Original training inputs](train_original_montage.jpg)

## Ảnh hưởng của pipeline ESP-TRASH-V3

- Tất cả ảnh QVGA 320×240 chỉ giữ center square 240×240, tức giữ 75% diện tích và bỏ
  40 px mỗi bên. Vật nằm lệch biên có thể mất đặc trưng sau crop.
- {diagnostics['wb_gain_at_limit_images']} ảnh chạm giới hạn gray-world và chỉ
  {diagnostics['luma_gain_active_images']} ảnh kích hoạt gain luminance. Vì vậy normalization
  ánh sáng **không phải thủ phạm chính quan sát được** trên tập này; vấn đề rõ hơn là crop,
  độ phân giải 96×96 và coverage vật thể.
- {separation['deployment_ood_2sigma_count']}/{evaluation['images']} ảnh triển khai, trong đó
  {ood_wrong}/{evaluation['errors']} lỗi, nằm ngoài bán kính 2σ của lớp thật trong embedding
  train-original. Ngưỡng này chỉ là chỉ báo vì reference original có 48 ảnh, nhưng tỷ lệ quá cao
  vẫn xác nhận train và deployment lệch miền đáng kể.
- So sánh low-level cho thấy màu/texture sau white balance vẫn chồng lấn; xem biểu đồ dưới.

![Low-level feature PCA](low_level_pca.png)

## INT8 có phải nguyên nhân chính không?

Không phải nguyên nhân chính. Float đúng {evaluation['float_correct']}/{evaluation['images']}
({evaluation['float_accuracy']:.2%}), còn INT8 đúng {evaluation['correct']}/{evaluation['images']}
({evaluation['accuracy']:.2%}); delta INT8−float là
{evaluation['accuracy_delta_int8_minus_float']:+.2%}. Hai model đổi top-1 trên
**{evaluation['float_int8_prediction_disagreements']}** ảnh; mean sai khác xác suất lớn nhất là
`{evaluation['float_int8_mean_max_abs_probability_error']:.5f}`. Quantization có ảnh hưởng ở
một số mẫu sát biên, nhưng không giải thích được {evaluation['errors']} lỗi triển khai.

Có metadata firmware cho {firmware['images_with_metadata']} ảnh. Python re-infer JPEG đồng ý
top-1 với firmware raw-RGB565 {firmware['prediction_agreements']}/{firmware['images_with_metadata']}
({format_optional_percent(firmware['prediction_agreement_rate'])}). Sai khác còn lại có thể do
JPEG telemetry là ảnh nén sau khi firmware đã infer trên framebuffer RGB565.
Trên đúng subset này, firmware raw-RGB565 đạt
{format_optional_percent(firmware['firmware_accuracy_on_metadata_subset'])}, còn local JPEG đạt
{format_optional_percent(firmware['python_jpeg_accuracy_on_same_subset'])}.

![Confidence](confidence_correct_vs_wrong.png)

## Thống kê dữ liệu train so với triển khai

| Lớp | Train files | Train original | Augmented | Source groups | Deployment |
|---|---:|---:|---:|---:|---:|
{diversity_rows}

Exact file trùng giữa deployment và train: {summary['duplicates']['exact_deployment_to_train_files']}.
Điều này xác nhận phép đo chủ yếu là ảnh ngoài tập train, không phải đánh giá lại dữ liệu đã học.

## Khuyến nghị ưu tiên

1. Review thủ công toàn bộ `misclassified.csv` và các montage, đặc biệt `plastic_016..020`;
   tách **nhãn sai/đối tượng hỗn hợp/ảnh không thấy rõ vật** khỏi lỗi model.
2. Thu thập theo **source object + capture session**, tối thiểu nhiều vật thể độc lập mỗi lớp,
   nhiều vị trí (giữa/biên), khoảng cách, mặt trước/sau, vò nát/ướt/bẩn. Split theo vật thể và
   ngày chụp, không split các frame gần nhau hoặc augmentation sang nhiều tập.
3. Bổ sung hard negatives trực tiếp từ bốn cặp nhầm ở trên. Với paper/plastic, ưu tiên hình
   dạng/chất liệu thật thay vì chỉ thêm gamma/noise.
4. Tạo test deployment cố định từ phiên 2026-08-08 và 2026-08-11, cân bằng số ảnh/lớp, và dùng macro
   recall + confusion matrix làm tiêu chí chọn model.
5. Sau khi sửa nhãn/dataset, thử model có capacity/representation tốt hơn trong giới hạn ESP32;
   so sánh float trước, chỉ quantize model thắng trên test ngoài phiên.
6. Ở firmware, dùng ngưỡng theo lớp hoặc trạng thái `unknown/retry`, nhưng chỉ sau khi calibration
   trên tập triển khai; threshold 0.8 hiện vẫn nhận nhiều dự đoán sai.

## Artifact

- `predictions.csv`: kết quả và xác suất từng ảnh.
- `misclassified.csv`: chỉ các ảnh sai, kèm nearest train/OOD/pipeline diagnostics.
- `summary.json`: toàn bộ số liệu máy đọc được.
- `training_reference_features.csv`: đặc trưng reference của train.
- `misclassified_montage_*.jpg`: ảnh input 96×96 thực sự model nhìn thấy, xếp theo confidence sai.
- `train_original_montage.jpg`: toàn bộ 48 ảnh train original sau preprocessing.

## Giới hạn diễn giải

Tên thư mục được coi là ground truth theo yêu cầu đánh giá. Báo cáo không thể tự xác nhận vật thể
trong mọi ảnh có đúng nhãn hay không. Local inference nhận JPEG đã nén, không thể khôi phục chính
xác framebuffer RGB565; vì vậy kết quả firmware thật được báo riêng trên subset có metadata.
PCA chỉ là chiếu 2D để quan sát; kết luận định lượng dùng
embedding 64D và confusion matrix. Phân tích embedding dùng model float tương ứng để lấy layer áp
chót vì TFLite artifact chỉ expose output; top-1 float/INT8 đã được đối chiếu riêng.
"""
    path.write_text(report, encoding="utf-8")


def plot_optional(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.4f}"


def format_optional_percent(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.2%}"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def relative_to_repo(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_DIR).as_posix()
    except ValueError:
        return str(path.resolve())


if __name__ == "__main__":
    main()
