"""Full V10 analysis for labelled ESP folders and unlabelled server data."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
from typing import Iterable

os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")
os.environ.setdefault("MPLBACKEND", "Agg")

import cv2
import matplotlib.pyplot as plt
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from sklearn.decomposition import PCA
import tensorflow as tf

from V10.config import (
    ARTIFACTS_DIR,
    CLASS_NAMES,
    DATASET_DIR,
    REPOSITORY_DIR,
)
from V10.data_pipeline import preprocess_file_tensor
from V10.metrics import classification_metrics


EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp"}
EXPOSURE_ORDER = (
    "exact_train_file",
    "train_lineage",
    "heldout_validation",
    "heldout_test",
    "unseen",
)


@dataclass(frozen=True)
class ImageRecord:
    path: Path
    relative_path: str
    digest: str
    label_id: int | None
    label: str | None
    metadata: dict | None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--server-root", type=Path, default=REPOSITORY_DIR / "server-tmp")
    parser.add_argument("--artifacts", type=Path, default=ARTIFACTS_DIR)
    parser.add_argument(
        "--out", type=Path, default=ARTIFACTS_DIR / "esp_data_analysis"
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    server_root = args.server_root.resolve()
    artifacts = args.artifacts.resolve()
    output = args.out.resolve()
    output.mkdir(parents=True, exist_ok=True)

    metadata = _load_metadata(server_root / "data" / "metadata")
    gt_records = _collect_gt(server_root, metadata)
    no_gt_records = _collect_no_gt(server_root, metadata)
    manifest_rows = list(csv.DictReader(
        (DATASET_DIR / "manifest.csv").open(encoding="utf-8", newline="")
    ))
    exposure_index = _build_exposure_index(manifest_rows)

    float_model = tf.keras.models.load_model(
        artifacts / "model_float.keras", compile=False
    )
    gt_images = _preprocess_records(gt_records)
    no_gt_images = _preprocess_records(no_gt_records)
    gt_float = float_model.predict(gt_images, batch_size=16, verbose=0)
    no_gt_float = float_model.predict(no_gt_images, batch_size=16, verbose=0)

    interpreter = tf.lite.Interpreter(model_path=str(artifacts / "model_int8.tflite"))
    interpreter.allocate_tensors()
    gt_int8 = _run_int8(interpreter, gt_images)
    no_gt_int8 = _run_int8(interpreter, no_gt_images)

    gt_truth = np.asarray([record.label_id for record in gt_records], dtype=np.int64)
    gt_prediction = gt_int8.argmax(axis=1)
    gt_correct = gt_prediction == gt_truth
    no_gt_prediction = no_gt_int8.argmax(axis=1)
    gt_metrics = classification_metrics(gt_truth, gt_int8)
    gt_float_metrics = classification_metrics(gt_truth, gt_float)
    gt_quality = [_quality_features(image) for image in gt_images]
    no_gt_quality = [_quality_features(image) for image in no_gt_images]

    v9_local = _run_v9_local(gt_records)
    v9_local_metrics = classification_metrics(gt_truth, v9_local)
    firmware_subset = [index for index, record in enumerate(gt_records)
                       if _has_firmware_prediction(record)]
    firmware_truth = gt_truth[firmware_subset]
    firmware_probabilities = np.stack([
        _metadata_probabilities(gt_records[index].metadata)
        for index in firmware_subset
    ])
    firmware_metrics = classification_metrics(firmware_truth, firmware_probabilities)
    v10_firmware_subset_metrics = classification_metrics(
        firmware_truth, gt_int8[firmware_subset]
    )

    training_records, training_images, training_embeddings = _training_reference(
        manifest_rows, float_model
    )
    feature_model = tf.keras.Model(
        float_model.input,
        float_model.get_layer("global_average_pooling").output,
        name="v10_feature_extractor",
    )
    gt_embeddings = _normalize_rows(
        feature_model.predict(gt_images, batch_size=16, verbose=0)
    )
    no_gt_embeddings = _normalize_rows(
        feature_model.predict(no_gt_images, batch_size=16, verbose=0)
    )
    embedding_analysis = _embedding_analysis(
        training_records,
        training_embeddings,
        gt_records,
        gt_embeddings,
        no_gt_records,
        no_gt_embeddings,
        no_gt_prediction,
    )

    gt_hashes = {record.digest for record in gt_records}
    no_gt_hashes = {record.digest for record in no_gt_records}
    exact_overlap = gt_hashes & no_gt_hashes
    gt_exposure = [
        _exposure_for_hash(exposure_index, record.digest) for record in gt_records
    ]
    no_gt_exposure = [
        _exposure_for_hash(exposure_index, record.digest) for record in no_gt_records
    ]

    firmware_no_gt = np.stack([
        _metadata_probabilities(record.metadata) for record in no_gt_records
    ])
    firmware_no_gt_prediction = firmware_no_gt.argmax(axis=1)
    transition = np.zeros((len(CLASS_NAMES), len(CLASS_NAMES)), dtype=np.int64)
    for old, new in zip(firmware_no_gt_prediction, no_gt_prediction):
        transition[old, new] += 1

    gt_rows = _build_gt_rows(
        gt_records,
        gt_float,
        gt_int8,
        v9_local,
        gt_exposure,
        gt_quality,
        embedding_analysis["gt"],
    )
    no_gt_rows = _build_no_gt_rows(
        no_gt_records,
        no_gt_float,
        no_gt_int8,
        firmware_no_gt,
        no_gt_exposure,
        no_gt_quality,
        embedding_analysis["no_gt"],
        exact_overlap,
    )

    calibration = _calibration(gt_truth, gt_int8)
    thresholds = _selective_metrics(gt_truth, gt_int8)
    training_stats = _training_stats(manifest_rows)
    model_metadata = json.loads(
        (artifacts / "model_metadata.json").read_text(encoding="utf-8")
    )
    quantization = json.loads(
        (artifacts / "quantization.json").read_text(encoding="utf-8")
    )

    summary = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "protocol": {
            "gt_source": [f"server-tmp/{label}" for label in CLASS_NAMES],
            "no_gt_source": "server-tmp/data/images",
            "no_gt_correctness_evaluated": False,
            "v10_execution": (
                "offline on ESP JPEG telemetry using the exact deterministic V10 "
                "training preprocessing contract"
            ),
            "firmware_metadata_model": sorted({
                record.metadata.get("ai_model_version", "unknown")
                for record in no_gt_records if record.metadata
            }),
        },
        "inventory": {
            "gt_images": len(gt_records),
            "gt_counts": dict(Counter(record.label for record in gt_records)),
            "no_gt_images": len(no_gt_records),
            "metadata_files": len(metadata),
            "exact_gt_no_gt_overlap": len(exact_overlap),
            "gt_only": len(gt_hashes - no_gt_hashes),
            "no_gt_only": len(no_gt_hashes - gt_hashes),
            "exact_duplicates_within_gt": len(gt_records) - len(gt_hashes),
            "exact_duplicates_within_no_gt": len(no_gt_records) - len(no_gt_hashes),
        },
        "dataset_training": training_stats,
        "gt": {
            "float_v10": gt_float_metrics,
            "int8_v10": gt_metrics,
            "v9_local_int8": v9_local_metrics,
            "v9_firmware_subset": {
                "images": len(firmware_subset),
                "metrics": firmware_metrics,
            },
            "v10_on_v9_firmware_subset": {
                "images": len(firmware_subset),
                "metrics": v10_firmware_subset_metrics,
            },
            "float_int8_top1_disagreements": int(np.sum(
                gt_float.argmax(axis=1) != gt_prediction
            )),
            "calibration": calibration,
            "selective_metrics": thresholds,
            "exposure": dict(Counter(gt_exposure)),
            "errors": [row for row in gt_rows if row["v10_int8_correct"] == "False"],
        },
        "no_gt": {
            "correctness": "NOT_EVALUATED",
            "v10_prediction_distribution": dict(Counter(
                CLASS_NAMES[index] for index in no_gt_prediction
            )),
            "v9_firmware_prediction_distribution": dict(Counter(
                CLASS_NAMES[index] for index in firmware_no_gt_prediction
            )),
            "v9_v10_top1_agreement": float(np.mean(
                firmware_no_gt_prediction == no_gt_prediction
            )),
            "v9_v10_top1_agreement_images": int(np.sum(
                firmware_no_gt_prediction == no_gt_prediction
            )),
            "transition_v9_rows_v10_columns": transition.tolist(),
            "confidence": _confidence_summary(no_gt_int8),
            "exposure": dict(Counter(no_gt_exposure)),
            "embedding_predicted_class_ood": int(sum(
                row["embedding_ood_for_predicted_class"] == "True"
                for row in no_gt_rows
            )),
        },
        "embedding": embedding_analysis["summary"],
        "model": {
            "version": model_metadata["model_version"],
            "parameters": int(float_model.count_params()),
            "int8_bytes": quantization["size_bytes"],
            "int8_sha256": quantization["sha256"],
            "input": quantization["input"],
            "output": quantization["output"],
            "operators": quantization["unique_operators"],
            "full_integer": quantization["full_integer"],
            "float_tensors": quantization["float_tensors"],
        },
    }

    _write_csv(output / "gt_predictions.csv", gt_rows)
    _write_csv(
        output / "gt_misclassified.csv",
        [row for row in gt_rows if row["v10_int8_correct"] == "False"],
    )
    _write_csv(output / "no_gt_predictions.csv", no_gt_rows)
    _write_csv(
        output / "no_gt_low_confidence.csv",
        sorted(
            [row for row in no_gt_rows if float(row["v10_int8_confidence"]) < 0.8],
            key=lambda row: float(row["v10_int8_confidence"]),
        ),
    )
    _write_csv(
        output / "no_gt_v9_v10_disagreements.csv",
        [row for row in no_gt_rows if row["v9_v10_top1_agree"] == "False"],
    )
    (output / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    _plot_confusion(output / "confusion_matrix_v10.png", gt_metrics["confusion_matrix"])
    _plot_transition(output / "no_gt_v9_v10_transition.png", transition)
    _plot_confidence(
        output / "confidence_analysis.png", gt_truth, gt_int8, no_gt_int8
    )
    _plot_selective(output / "selective_accuracy.png", thresholds)
    _plot_model_comparison(
        output / "model_comparison.png",
        v9_local_metrics,
        firmware_metrics,
        v10_firmware_subset_metrics,
        gt_metrics,
    )
    _plot_training_distribution(
        output / "training_distribution.png", training_stats
    )
    _plot_no_gt_distribution(
        output / "no_gt_prediction_distribution.png",
        firmware_no_gt_prediction,
        no_gt_prediction,
    )
    _plot_embedding_pca(
        output / "embedding_pca.png",
        training_records,
        training_embeddings,
        gt_records,
        gt_embeddings,
        gt_correct,
    )
    error_indices = np.where(~gt_correct)[0].tolist()
    _error_montage(
        output / "gt_error_montage.jpg", gt_records, gt_images, gt_rows, error_indices
    )
    low_confidence_indices = np.argsort(np.max(no_gt_int8, axis=1))[:24].tolist()
    _tile_montage(
        output / "no_gt_low_confidence_montage.jpg",
        no_gt_records,
        no_gt_rows,
        low_confidence_indices,
        mode="low_confidence",
    )
    disagreement_indices = np.where(
        firmware_no_gt_prediction != no_gt_prediction
    )[0]
    disagreement_indices = sorted(
        disagreement_indices,
        key=lambda index: float(np.max(no_gt_int8[index])),
        reverse=True,
    )[:24]
    _tile_montage(
        output / "no_gt_v9_v10_disagreement_montage.jpg",
        no_gt_records,
        no_gt_rows,
        disagreement_indices,
        mode="disagreement",
    )
    (output / "REPORT.md").write_text(
        _render_report(summary, gt_rows, no_gt_rows), encoding="utf-8"
    )
    print(json.dumps({
        "report": str(output / "REPORT.md"),
        "gt_accuracy": gt_metrics["accuracy"],
        "gt_errors": int(np.sum(~gt_correct)),
        "no_gt_images": len(no_gt_records),
        "no_gt_accuracy": "NOT_EVALUATED",
        "v9_v10_no_gt_agreement": summary["no_gt"]["v9_v10_top1_agreement"],
    }, indent=2, ensure_ascii=False))


def _load_metadata(root: Path) -> dict[str, dict]:
    result = {}
    for path in sorted(root.glob("*.json")):
        item = json.loads(path.read_text(encoding="utf-8"))
        result[path.stem] = item
    return result


def _collect_gt(root: Path, metadata: dict[str, dict]) -> list[ImageRecord]:
    records = []
    for label_id, label in enumerate(CLASS_NAMES):
        folder = root / label
        for path in sorted(folder.iterdir()):
            if path.is_file() and path.suffix.lower() in EXTENSIONS:
                records.append(ImageRecord(
                    path=path.resolve(),
                    relative_path=path.relative_to(root).as_posix(),
                    digest=_sha256(path),
                    label_id=label_id,
                    label=label,
                    metadata=metadata.get(path.stem),
                ))
    if not records:
        raise RuntimeError("No labelled ESP images found")
    return records


def _collect_no_gt(root: Path, metadata: dict[str, dict]) -> list[ImageRecord]:
    records = []
    folder = root / "data" / "images"
    for path in sorted(folder.iterdir()):
        if path.is_file() and path.suffix.lower() in EXTENSIONS:
            if path.stem not in metadata:
                raise RuntimeError(f"No metadata for no-GT image: {path}")
            records.append(ImageRecord(
                path=path.resolve(),
                relative_path=path.relative_to(root).as_posix(),
                digest=_sha256(path),
                label_id=None,
                label=None,
                metadata=metadata[path.stem],
            ))
    if not records:
        raise RuntimeError("No unlabelled ESP data images found")
    return records


def _preprocess_records(records: Iterable[ImageRecord]) -> np.ndarray:
    return np.stack([
        preprocess_file_tensor(tf.constant(str(record.path))).numpy()
        for record in records
    ])


def _run_int8(interpreter, images: np.ndarray) -> np.ndarray:
    input_detail = interpreter.get_input_details()[0]
    output_detail = interpreter.get_output_details()[0]
    input_scale, input_zero = input_detail["quantization"]
    output_scale, output_zero = output_detail["quantization"]
    probabilities = []
    for image in images:
        quantized = np.clip(
            np.rint(image / input_scale) + input_zero, -128, 127
        ).astype(np.int8)[None, ...]
        interpreter.set_tensor(input_detail["index"], quantized)
        interpreter.invoke()
        raw = interpreter.get_tensor(output_detail["index"])[0]
        probabilities.append(
            (raw.astype(np.float32) - output_zero) * output_scale
        )
    return np.asarray(probabilities)


def _run_v9_local(records: list[ImageRecord]) -> np.ndarray:
    from V9.data_pipeline import preprocess_file_tensor as preprocess_v9

    interpreter = tf.lite.Interpreter(
        model_path=str(REPOSITORY_DIR / "AI" / "V9" / "artifacts" / "model_int8.tflite")
    )
    interpreter.allocate_tensors()
    images = np.stack([
        preprocess_v9(tf.constant(str(record.path))).numpy() for record in records
    ])
    return _run_int8(interpreter, images)


def _training_reference(manifest_rows: list[dict], float_model):
    records = [
        row for row in manifest_rows
        if row["split"] == "train" and row["kind"] == "original"
    ]
    images = np.stack([
        preprocess_file_tensor(
            tf.constant(str((DATASET_DIR / row["relative_path"]).resolve()))
        ).numpy()
        for row in records
    ])
    feature_model = tf.keras.Model(
        float_model.input,
        float_model.get_layer("global_average_pooling").output,
        name="v10_training_reference_extractor",
    )
    embeddings = _normalize_rows(
        feature_model.predict(images, batch_size=16, verbose=0)
    )
    return records, images, embeddings


def _embedding_analysis(
    training_records,
    training_embeddings,
    gt_records,
    gt_embeddings,
    no_gt_records,
    no_gt_embeddings,
    no_gt_prediction,
):
    train_labels = np.asarray([int(row["label_id"]) for row in training_records])
    thresholds = {}
    for label_id, label in enumerate(CLASS_NAMES):
        selected = np.where(train_labels == label_id)[0]
        values = training_embeddings[selected]
        distances = 1.0 - values @ values.T
        np.fill_diagonal(distances, np.inf)
        thresholds[label] = float(np.quantile(np.min(distances, axis=1), 0.95))

    gt_result = []
    for record, embedding in zip(gt_records, gt_embeddings):
        all_distances = 1.0 - training_embeddings @ embedding
        nearest_index = int(np.argmin(all_distances))
        true_indices = np.where(train_labels == record.label_id)[0]
        true_local = int(np.argmin(all_distances[true_indices]))
        true_index = int(true_indices[true_local])
        distance = float(all_distances[true_index])
        gt_result.append({
            "nearest_train_path": training_records[nearest_index]["relative_path"],
            "nearest_train_label": training_records[nearest_index]["label"],
            "nearest_train_cosine_distance": float(all_distances[nearest_index]),
            "nearest_true_class_train_path": training_records[true_index]["relative_path"],
            "nearest_true_class_cosine_distance": distance,
            "embedding_ood_for_true_class": bool(distance > thresholds[record.label]),
        })

    no_gt_result = []
    for predicted, embedding in zip(no_gt_prediction, no_gt_embeddings):
        all_distances = 1.0 - training_embeddings @ embedding
        nearest_index = int(np.argmin(all_distances))
        predicted_indices = np.where(train_labels == predicted)[0]
        predicted_local = int(np.argmin(all_distances[predicted_indices]))
        predicted_index = int(predicted_indices[predicted_local])
        distance = float(all_distances[predicted_index])
        no_gt_result.append({
            "nearest_train_path": training_records[nearest_index]["relative_path"],
            "nearest_train_label": training_records[nearest_index]["label"],
            "nearest_train_cosine_distance": float(all_distances[nearest_index]),
            "nearest_predicted_class_train_path": training_records[predicted_index]["relative_path"],
            "nearest_predicted_class_cosine_distance": distance,
            "embedding_ood_for_predicted_class": bool(
                distance > thresholds[CLASS_NAMES[predicted]]
            ),
        })
    return {
        "gt": gt_result,
        "no_gt": no_gt_result,
        "summary": {
            "reference": "train originals only, L2-normalized 96D GAP embedding",
            "reference_images": len(training_records),
            "class_95pct_nearest_neighbor_cosine_threshold": thresholds,
            "gt_true_class_ood": int(sum(
                item["embedding_ood_for_true_class"] for item in gt_result
            )),
            "no_gt_predicted_class_ood": int(sum(
                item["embedding_ood_for_predicted_class"] for item in no_gt_result
            )),
        },
    }


def _build_exposure_index(rows: list[dict]) -> dict[str, dict[str, set[str]]]:
    result = defaultdict(lambda: {"exact": set(), "lineage": set()})
    for row in rows:
        result[row["sha256"]]["exact"].add(row["split"])
        if row.get("source_sha256"):
            result[row["source_sha256"]]["lineage"].add(row["split"])
    return result


def _exposure_for_hash(index, digest: str) -> str:
    item = index.get(digest)
    if not item:
        return "unseen"
    if "train" in item["exact"]:
        return "exact_train_file"
    if "train" in item["lineage"]:
        return "train_lineage"
    if "validation" in item["exact"] | item["lineage"]:
        return "heldout_validation"
    if "test" in item["exact"] | item["lineage"]:
        return "heldout_test"
    return "unseen"


def _build_gt_rows(
    records, float_probabilities, int8_probabilities, v9_probabilities,
    exposure, quality, embedding,
):
    rows = []
    float_prediction = float_probabilities.argmax(axis=1)
    int8_prediction = int8_probabilities.argmax(axis=1)
    v9_prediction = v9_probabilities.argmax(axis=1)
    for index, record in enumerate(records):
        metadata_prediction = (
            record.metadata.get("waste_class") if _has_firmware_prediction(record)
            else "UNAVAILABLE"
        )
        row = {
            "path": record.relative_path,
            "sha256": record.digest,
            "ground_truth": record.label,
            "v10_float_prediction": CLASS_NAMES[int(float_prediction[index])],
            "v10_int8_prediction": CLASS_NAMES[int(int8_prediction[index])],
            "v10_int8_correct": str(bool(int8_prediction[index] == record.label_id)),
            "v10_int8_confidence": float(np.max(int8_probabilities[index])),
            "v9_local_prediction": CLASS_NAMES[int(v9_prediction[index])],
            "v9_firmware_prediction": metadata_prediction,
            "training_exposure": exposure[index],
            **{
                f"v10_int8_{label}": float(int8_probabilities[index, label_id])
                for label_id, label in enumerate(CLASS_NAMES)
            },
            **quality[index],
            **embedding[index],
        }
        rows.append(_stringify_bools(row))
    return rows


def _build_no_gt_rows(
    records, float_probabilities, int8_probabilities, firmware_probabilities,
    exposure, quality, embedding, exact_gt_overlap,
):
    rows = []
    float_prediction = float_probabilities.argmax(axis=1)
    int8_prediction = int8_probabilities.argmax(axis=1)
    firmware_prediction = firmware_probabilities.argmax(axis=1)
    for index, record in enumerate(records):
        item = record.metadata or {}
        row = {
            "path": record.relative_path,
            "sha256": record.digest,
            "ground_truth": "UNKNOWN",
            "correctness": "NOT_EVALUATED",
            "has_exact_copy_in_gt_folders": str(record.digest in exact_gt_overlap),
            "v10_float_prediction": CLASS_NAMES[int(float_prediction[index])],
            "v10_int8_prediction": CLASS_NAMES[int(int8_prediction[index])],
            "v10_int8_confidence": float(np.max(int8_probabilities[index])),
            "v9_firmware_prediction": CLASS_NAMES[int(firmware_prediction[index])],
            "v9_firmware_confidence": float(item.get("confidence", np.nan)),
            "v9_v10_top1_agree": str(bool(
                firmware_prediction[index] == int8_prediction[index]
            )),
            "received_at": item.get("received_at", ""),
            "inference_us_v9_firmware": item.get("inference_us", ""),
            "metadata_model_version": item.get("ai_model_version", ""),
            "training_exposure": exposure[index],
            **{
                f"v10_int8_{label}": float(int8_probabilities[index, label_id])
                for label_id, label in enumerate(CLASS_NAMES)
            },
            **quality[index],
            **embedding[index],
        }
        rows.append(_stringify_bools(row))
    return rows


def _quality_features(image: np.ndarray) -> dict[str, float]:
    pixels = np.rint(np.clip(image, 0.0, 1.0) * 255.0).astype(np.uint8)
    luma = cv2.cvtColor(pixels, cv2.COLOR_RGB2GRAY)
    hsv = cv2.cvtColor(pixels, cv2.COLOR_RGB2HSV)
    laplacian = cv2.Laplacian(luma, cv2.CV_32F)
    edges = cv2.Canny(luma, 64, 128)
    return {
        "mean_luma": float(np.mean(luma)),
        "std_luma": float(np.std(luma)),
        "mean_saturation": float(np.mean(hsv[..., 1])),
        "laplacian_variance": float(np.var(laplacian)),
        "edge_fraction": float(np.mean(edges > 0)),
        "dark_fraction": float(np.mean(luma < 48)),
        "bright_fraction": float(np.mean(luma > 208)),
    }


def _calibration(truth: np.ndarray, probabilities: np.ndarray) -> dict:
    clipped = np.clip(probabilities, 1e-7, 1.0)
    predicted = probabilities.argmax(axis=1)
    confidence = probabilities.max(axis=1)
    correct = predicted == truth
    one_hot = np.eye(probabilities.shape[1])[truth]
    bins = np.linspace(0.0, 1.0, 11)
    ece = 0.0
    details = []
    for lower, upper in zip(bins[:-1], bins[1:]):
        mask = (confidence >= lower) & (
            confidence <= upper if upper == 1.0 else confidence < upper
        )
        if not np.any(mask):
            continue
        bin_accuracy = float(np.mean(correct[mask]))
        bin_confidence = float(np.mean(confidence[mask]))
        fraction = float(np.mean(mask))
        ece += fraction * abs(bin_accuracy - bin_confidence)
        details.append({
            "range": [float(lower), float(upper)],
            "images": int(np.sum(mask)),
            "accuracy": bin_accuracy,
            "mean_confidence": bin_confidence,
        })
    return {
        "negative_log_likelihood": float(-np.mean(np.log(clipped[np.arange(len(truth)), truth]))),
        "brier_score": float(np.mean(np.sum((probabilities - one_hot) ** 2, axis=1))),
        "expected_calibration_error_10_bins": float(ece),
        "mean_confidence_correct": float(np.mean(confidence[correct])),
        "mean_confidence_wrong": float(np.mean(confidence[~correct])) if np.any(~correct) else None,
        "bins": details,
    }


def _selective_metrics(truth: np.ndarray, probabilities: np.ndarray) -> list[dict]:
    predicted = probabilities.argmax(axis=1)
    confidence = probabilities.max(axis=1)
    result = []
    for threshold in np.arange(0.0, 0.951, 0.05):
        accepted = confidence >= threshold
        result.append({
            "threshold": float(round(threshold, 2)),
            "accepted": int(np.sum(accepted)),
            "coverage": float(np.mean(accepted)),
            "accuracy": float(np.mean(predicted[accepted] == truth[accepted]))
            if np.any(accepted) else None,
        })
    return result


def _confidence_summary(probabilities: np.ndarray) -> dict:
    confidence = probabilities.max(axis=1)
    sorted_probabilities = np.sort(probabilities, axis=1)
    margin = sorted_probabilities[:, -1] - sorted_probabilities[:, -2]
    entropy = -np.sum(
        np.clip(probabilities, 1e-7, 1.0) *
        np.log(np.clip(probabilities, 1e-7, 1.0)), axis=1
    ) / math.log(probabilities.shape[1])
    return {
        "mean": float(np.mean(confidence)),
        "median": float(np.median(confidence)),
        "minimum": float(np.min(confidence)),
        "below_0_6": int(np.sum(confidence < 0.6)),
        "below_0_8": int(np.sum(confidence < 0.8)),
        "at_least_0_9": int(np.sum(confidence >= 0.9)),
        "mean_top1_top2_margin": float(np.mean(margin)),
        "mean_normalized_entropy": float(np.mean(entropy)),
    }


def _training_stats(rows: list[dict]) -> dict:
    train = [row for row in rows if row["split"] == "train"]
    kind_by_class = {
        label: dict(Counter(row["kind"] for row in train if row["label"] == label))
        for label in CLASS_NAMES
    }
    source_groups = {
        label: len({row["source_group"] for row in train if row["label"] == label})
        for label in CLASS_NAMES
    }
    return {
        "images": len(train),
        "per_class": dict(Counter(row["label"] for row in train)),
        "kind_by_class": kind_by_class,
        "source_groups_per_class": source_groups,
        "originals_per_class": {
            label: sum(
                row["label"] == label and row["kind"] == "original" for row in train
            ) for label in CLASS_NAMES
        },
    }


def _metadata_probabilities(metadata: dict | None) -> np.ndarray:
    if not metadata:
        raise ValueError("Firmware metadata is unavailable")
    probabilities = metadata["probabilities"]
    return np.asarray([probabilities[label] for label in CLASS_NAMES], np.float32)


def _has_firmware_prediction(record: ImageRecord) -> bool:
    return bool(
        record.metadata
        and record.metadata.get("ai_model_version") == "tinycnn-v9-balanced-esp-contract"
        and all(label in record.metadata.get("probabilities", {}) for label in CLASS_NAMES)
    )


def _plot_confusion(path: Path, matrix) -> None:
    matrix = np.asarray(matrix)
    fig, ax = plt.subplots(figsize=(6.2, 5.3))
    image = ax.imshow(matrix, cmap="Blues")
    for row in range(len(CLASS_NAMES)):
        for column in range(len(CLASS_NAMES)):
            ax.text(column, row, str(matrix[row, column]), ha="center", va="center",
                    color="white" if matrix[row, column] > matrix.max() / 2 else "black")
    ax.set_xticks(range(len(CLASS_NAMES)), CLASS_NAMES)
    ax.set_yticks(range(len(CLASS_NAMES)), CLASS_NAMES)
    ax.set_xlabel("V10 INT8 prediction")
    ax.set_ylabel("Ground truth folder")
    ax.set_title("V10 INT8 on labelled ESP images (n=259)")
    fig.colorbar(image, ax=ax, fraction=0.046)
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def _plot_transition(path: Path, matrix: np.ndarray) -> None:
    fig, ax = plt.subplots(figsize=(6.2, 5.3))
    image = ax.imshow(matrix, cmap="Purples")
    for row in range(len(CLASS_NAMES)):
        for column in range(len(CLASS_NAMES)):
            ax.text(column, row, str(matrix[row, column]), ha="center", va="center",
                    color="white" if matrix[row, column] > matrix.max() / 2 else "black")
    ax.set_xticks(range(len(CLASS_NAMES)), CLASS_NAMES)
    ax.set_yticks(range(len(CLASS_NAMES)), CLASS_NAMES)
    ax.set_xlabel("Offline V10 prediction")
    ax.set_ylabel("Firmware V9 metadata prediction")
    ax.set_title("No-GT data: prediction transition only (not correctness)")
    fig.colorbar(image, ax=ax, fraction=0.046)
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def _plot_confidence(path, truth, gt_probabilities, no_gt_probabilities):
    gt_predicted = gt_probabilities.argmax(axis=1)
    gt_confidence = gt_probabilities.max(axis=1)
    correct = gt_predicted == truth
    no_gt_confidence = no_gt_probabilities.max(axis=1)
    bins = np.linspace(0.3, 1.0, 15)
    fig, ax = plt.subplots(figsize=(8, 4.8))
    ax.hist(gt_confidence[correct], bins=bins, alpha=0.65,
            label=f"GT correct (n={np.sum(correct)})")
    ax.hist(gt_confidence[~correct], bins=bins, alpha=0.85,
            label=f"GT wrong by folder label (n={np.sum(~correct)})")
    ax.hist(no_gt_confidence, bins=bins, histtype="step", linewidth=2.2,
            label=f"No-GT predictions (n={len(no_gt_confidence)})")
    ax.set_xlabel("V10 INT8 confidence")
    ax.set_ylabel("Images")
    ax.set_title("Confidence distributions; no-GT has no correctness meaning")
    ax.legend()
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def _plot_selective(path: Path, rows: list[dict]) -> None:
    threshold = [row["threshold"] for row in rows]
    coverage = [row["coverage"] for row in rows]
    accuracy = [np.nan if row["accuracy"] is None else row["accuracy"] for row in rows]
    fig, ax = plt.subplots(figsize=(7.5, 4.8))
    ax.plot(threshold, coverage, marker="o", label="Coverage")
    ax.plot(threshold, accuracy, marker="s", label="Accepted accuracy")
    ax.set_ylim(0.0, 1.03)
    ax.set_xlabel("Confidence threshold")
    ax.set_ylabel("Fraction")
    ax.set_title("Selective prediction on labelled folders")
    ax.grid(alpha=0.25)
    ax.legend()
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def _plot_model_comparison(path, v9_local, firmware, v10_subset, v10_all):
    names = ["V9 local\n259", "V9 firmware\n209", "V10 same\n209", "V10 all GT\n259"]
    values = [v9_local["accuracy"], firmware["accuracy"],
              v10_subset["accuracy"], v10_all["accuracy"]]
    fig, ax = plt.subplots(figsize=(7.5, 4.8))
    bars = ax.bar(names, values, color=["#a36a00", "#cf8e00", "#2878b5", "#165a8a"])
    for bar, value in zip(bars, values):
        ax.text(bar.get_x() + bar.get_width()/2, value + 0.015, f"{value:.2%}", ha="center")
    ax.set_ylim(0, 1.08)
    ax.set_ylabel("Accuracy")
    ax.set_title("V9/V10 comparison on labelled ESP images")
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def _plot_training_distribution(path: Path, stats: dict) -> None:
    kinds = sorted({kind for values in stats["kind_by_class"].values() for kind in values})
    x = np.arange(len(CLASS_NAMES))
    bottom = np.zeros(len(CLASS_NAMES))
    fig, ax = plt.subplots(figsize=(8, 5))
    for kind in kinds:
        values = np.asarray([stats["kind_by_class"][label].get(kind, 0) for label in CLASS_NAMES])
        ax.bar(x, values, bottom=bottom, label=kind)
        bottom += values
    ax.set_xticks(x, CLASS_NAMES)
    ax.set_ylabel("Training files")
    ax.set_title("V10 training composition: originals and augmentations")
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def _plot_no_gt_distribution(path, firmware_prediction, v10_prediction):
    old = np.bincount(firmware_prediction, minlength=len(CLASS_NAMES))
    new = np.bincount(v10_prediction, minlength=len(CLASS_NAMES))
    x = np.arange(len(CLASS_NAMES))
    fig, ax = plt.subplots(figsize=(7.5, 4.8))
    ax.bar(x - 0.2, old, width=0.4, label="Firmware V9 metadata")
    ax.bar(x + 0.2, new, width=0.4, label="Offline V10")
    ax.set_xticks(x, CLASS_NAMES)
    ax.set_ylabel("Predicted images (no GT)")
    ax.set_title("Prediction distribution; not an accuracy chart")
    ax.legend()
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def _plot_embedding_pca(path, train_records, train_embeddings, gt_records, gt_embeddings, gt_correct):
    combined = np.vstack([train_embeddings, gt_embeddings])
    points = PCA(n_components=2, random_state=10).fit_transform(combined)
    train_points = points[:len(train_records)]
    gt_points = points[len(train_records):]
    train_labels = np.asarray([int(row["label_id"]) for row in train_records])
    colors = ["#2878b5", "#f28e2b", "#59a14f"]
    fig, ax = plt.subplots(figsize=(8, 6))
    for label_id, label in enumerate(CLASS_NAMES):
        mask = train_labels == label_id
        ax.scatter(train_points[mask, 0], train_points[mask, 1], s=14, alpha=0.28,
                   color=colors[label_id], label=f"train-original {label}")
        gt_mask = np.asarray([record.label_id == label_id for record in gt_records]) & gt_correct
        ax.scatter(gt_points[gt_mask, 0], gt_points[gt_mask, 1], s=18, alpha=0.45,
                   marker="x", color=colors[label_id])
    wrong = ~gt_correct
    ax.scatter(gt_points[wrong, 0], gt_points[wrong, 1], s=100, facecolors="none",
               edgecolors="red", linewidths=2, label="folder-label error")
    ax.set_title("V10 96D embedding PCA (visual projection only)")
    ax.set_xlabel("PC1")
    ax.set_ylabel("PC2")
    ax.legend(fontsize=7, ncol=2)
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def _error_montage(path, records, images, rows, indices):
    if not indices:
        return
    width, row_height = 760, 300
    canvas = Image.new("RGB", (width, row_height * len(indices)), "white")
    draw = ImageDraw.Draw(canvas)
    font = ImageFont.load_default()
    for output_row, index in enumerate(indices):
        y0 = output_row * row_height
        raw = Image.open(records[index].path).convert("RGB").resize((320, 240))
        processed = Image.fromarray(
            np.rint(images[index] * 255).astype(np.uint8)
        ).resize((320, 240))
        canvas.paste(raw, (10, y0 + 48))
        canvas.paste(processed, (340, y0 + 48))
        row = rows[index]
        text = (
            f"{records[index].path.name} | GT={row['ground_truth']} | "
            f"V10={row['v10_int8_prediction']} {float(row['v10_int8_confidence']):.3f} | "
            f"exposure={row['training_exposure']}"
        )
        draw.text((10, y0 + 8), text, fill="black", font=font)
        draw.text((10, y0 + 32), "ESP JPEG", fill="black", font=font)
        draw.text((340, y0 + 32), "actual 128x96 model input", fill="black", font=font)
    canvas.save(path, quality=92)


def _tile_montage(path, records, rows, indices, mode):
    if not indices:
        return
    columns, tile_w, tile_h = 4, 300, 245
    line_h = 42
    rows_count = math.ceil(len(indices) / columns)
    canvas = Image.new("RGB", (columns * tile_w, rows_count * (tile_h + line_h)), "white")
    draw = ImageDraw.Draw(canvas)
    font = ImageFont.load_default()
    for slot, index in enumerate(indices):
        x = (slot % columns) * tile_w
        y = (slot // columns) * (tile_h + line_h)
        image = Image.open(records[index].path).convert("RGB")
        image.thumbnail((tile_w - 8, tile_h - 8))
        canvas.paste(image, (x + 4, y + 4))
        row = rows[index]
        if mode == "disagreement":
            text = (
                f"{records[index].path.stem[:8]} V9={row['v9_firmware_prediction']} "
                f"V10={row['v10_int8_prediction']} ({float(row['v10_int8_confidence']):.2f})"
            )
        else:
            text = (
                f"{records[index].path.stem[:8]} V10={row['v10_int8_prediction']} "
                f"conf={float(row['v10_int8_confidence']):.2f} GT=UNKNOWN"
            )
        draw.text((x + 4, y + tile_h + 3), text, fill="black", font=font)
    canvas.save(path, quality=90)


def _render_report(summary: dict, gt_rows: list[dict], no_gt_rows: list[dict]) -> str:
    gt = summary["gt"]["int8_v10"]
    v9 = summary["gt"]["v9_local_int8"]
    firmware = summary["gt"]["v9_firmware_subset"]
    same_subset = summary["gt"]["v10_on_v9_firmware_subset"]
    inventory = summary["inventory"]
    no_gt = summary["no_gt"]
    calibration = summary["gt"]["calibration"]
    errors = [row for row in gt_rows if row["v10_int8_correct"] == "False"]
    confusion = gt["confusion_matrix"]
    confidence = no_gt["confidence"]
    transition = no_gt["transition_v9_rows_v10_columns"]
    high_threshold = next(row for row in summary["gt"]["selective_metrics"]
                          if abs(row["threshold"] - 0.8) < 1e-6)
    low_no_gt = sorted(no_gt_rows, key=lambda row: float(row["v10_int8_confidence"]))[:10]
    top_disagreements = sorted(
        [row for row in no_gt_rows if row["v9_v10_top1_agree"] == "False"],
        key=lambda row: float(row["v10_int8_confidence"]), reverse=True,
    )[:10]

    error_notes = {
        "ae41156a-aa81-46b1-97d7-fb8f22cfdad6.jpg": (
            "Ảnh cho thấy chai/bao bì nhựa trong suốt. File đã bị audit loại khỏi "
            "dataset vì nghi gán nhãn paper sai; dự đoán plastic 98.44% phù hợp review trực quan."
        ),
        "d6c607ff-e54d-4b58-9170-290051e6d6cf.jpg": (
            "Thùng carton nâu chiếm gần toàn khung nhưng model nghiêng organic. Đây là lỗi model "
            "thật theo GT hiện tại; màu nâu/texture phẳng và ít biên phân biệt là hard case."
        ),
        "6a300772-f7c2-4905-a435-fbda86b5e7df.jpg": (
            "Bao bì nhựa trong có nhãn giấy in lớn. Đây là vật liệu hỗn hợp về appearance; model "
            "bám vùng nhãn giấy và dự đoán paper."
        ),
    }
    error_lines = []
    for row in errors:
        name = Path(row["path"]).name
        probabilities = ", ".join(
            f"{label}={float(row[f'v10_int8_{label}']):.3f}" for label in CLASS_NAMES
        )
        error_lines.append(
            f"### `{row['path']}`\n\n"
            f"- Folder GT: `{row['ground_truth']}`; V10: `{row['v10_int8_prediction']}`; "
            f"{probabilities}.\n"
            f"- Exposure: `{row['training_exposure']}`; nearest train: "
            f"`{row['nearest_train_path']}` ({row['nearest_train_label']}, cosine "
            f"{float(row['nearest_train_cosine_distance']):.4f}).\n"
            f"- Phân tích: {error_notes.get(name, 'Cần review thủ công thêm.')}\n"
        )

    low_table = "\n".join(
        f"| `{Path(row['path']).name}` | {row['v10_int8_prediction']} | "
        f"{float(row['v10_int8_confidence']):.3f} | {row['v9_firmware_prediction']} |"
        for row in low_no_gt
    )
    disagreement_table = "\n".join(
        f"| `{Path(row['path']).name}` | {row['v9_firmware_prediction']} | "
        f"{row['v10_int8_prediction']} | {float(row['v10_int8_confidence']):.3f} |"
        for row in top_disagreements
    )

    return f"""# Báo cáo phân tích V10 trên ảnh từ ESP32-CAM

Ngày tạo: {summary['created_utc']}

## Kết luận chính

V10 INT8 đạt **{round(gt['accuracy'] * 259)}/259 = {gt['accuracy']:.2%}** trên ba
thư mục có ground truth `paper/plastic/organic`, macro-recall **{gt['macro_recall']:.2%}**
và macro-F1 **{gt['macro_f1']:.3f}**. Theo nhãn thư mục có 3 lỗi, nhưng review trực
quan cho thấy một lỗi là ảnh chai nhựa rất có khả năng bị đặt nhầm trong `paper`.
Hai hard case còn lại là carton nâu bị đoán organic và nhựa trong có nhãn giấy lớn
bị đoán paper.

**Không tính accuracy cho `server-tmp/data/images`.** {inventory['no_gt_images']} ảnh
ở đó không có GT theo protocol của dự án. Báo cáo chỉ thống kê prediction, confidence,
drift và mức đồng thuận V9/V10; các dòng CSV đều ghi `correctness=NOT_EVALUATED`.

Ngoài ra, đây là chạy V10 **offline trên JPEG telemetry do ESP chụp**. Metadata của cả
{inventory['no_gt_images']} ảnh vẫn là `{summary['protocol']['firmware_metadata_model'][0]}`;
chưa phải bằng chứng V10 đã infer raw RGB565 trực tiếp trên board.

## 1. Protocol và kiểm kê dữ liệu

| Nhóm | Số ảnh | Có GT? | Cách dùng |
|---|---:|---|---|
| `server-tmp/paper` | {summary['inventory']['gt_counts'].get('paper', 0)} | Có | Accuracy/confusion/error analysis |
| `server-tmp/plastic` | {summary['inventory']['gt_counts'].get('plastic', 0)} | Có | Accuracy/confusion/error analysis |
| `server-tmp/organic` | {summary['inventory']['gt_counts'].get('organic', 0)} | Có | Accuracy/confusion/error analysis |
| `server-tmp/data/images` | {inventory['no_gt_images']} | **Không** | Prediction/confidence/agreement only |

- Exact overlap giữa GT và no-GT: **{inventory['exact_gt_no_gt_overlap']}** ảnh.
- Chỉ có trong các thư mục GT: **{inventory['gt_only']}** ảnh.
- Chỉ có trong `data/images`: **{inventory['no_gt_only']}** ảnh.
- Exact duplicate nội bộ GT/no-GT: {inventory['exact_duplicates_within_gt']}/
  {inventory['exact_duplicates_within_no_gt']}.

209 ảnh overlap vẫn được đánh giá từ bản nằm trong thư mục GT; bản `data/images`
không tự nhận GT. Quy tắc này tránh lỗi phương pháp từng coi prediction trên data là
đúng/sai dù chưa có nhãn.

## 2. Kết quả V10 trên ảnh có GT

| Model/chế độ | N | Accuracy | Macro recall | Min class recall |
|---|---:|---:|---:|---:|
| V9 INT8 local, crop 96x96 | 259 | {v9['accuracy']:.2%} | {v9['macro_recall']:.2%} | {v9['minimum_class_recall']:.2%} |
| V9 firmware metadata subset | {firmware['images']} | {firmware['metrics']['accuracy']:.2%} | {firmware['metrics']['macro_recall']:.2%} | {firmware['metrics']['minimum_class_recall']:.2%} |
| V10 offline trên cùng subset | {same_subset['images']} | {same_subset['metrics']['accuracy']:.2%} | {same_subset['metrics']['macro_recall']:.2%} | {same_subset['metrics']['minimum_class_recall']:.2%} |
| **V10 INT8 toàn bộ GT** | **259** | **{gt['accuracy']:.2%}** | **{gt['macro_recall']:.2%}** | **{gt['minimum_class_recall']:.2%}** |

Hàng firmware V9 và V10 subset dùng cùng {firmware['images']} ảnh có metadata, nhưng
không hoàn toàn cùng representation: firmware V9 infer framebuffer RGB565, V10 local
infer JPEG đã nén rồi mô phỏng RGB565 truncation.

| true \\ predicted | paper | plastic | organic |
|---|---:|---:|---:|
| paper | {confusion[0][0]} | {confusion[0][1]} | {confusion[0][2]} |
| plastic | {confusion[1][0]} | {confusion[1][1]} | {confusion[1][2]} |
| organic | {confusion[2][0]} | {confusion[2][1]} | {confusion[2][2]} |

![Confusion matrix](confusion_matrix_v10.png)

![Model comparison](model_comparison.png)

## 3. Ba trường hợp khác nhãn GT

![GT error montage](gt_error_montage.jpg)

{''.join(error_lines)}

Nếu sửa riêng ảnh nghi gán nhãn sai từ paper sang plastic, V10 sẽ đạt 257/259 =
99.23%. Con số này chỉ là sensitivity analysis, **không thay thế metric chính thức**
cho đến khi người phụ trách dữ liệu xác nhận nhãn.

## 4. Leakage và độ tin cậy của phép đo

GT exposure theo manifest V10:

{_bullet_counts(summary['gt']['exposure'])}

222/259 ảnh GT là exact train file. Chỉ có một ảnh `unseen`, và đó chính là ảnh nghi
gán nhãn paper sai. Vì vậy 98.84% chủ yếu xác nhận model đã fit dữ liệu đã đưa vào
pipeline và preprocessing chạy nhất quán; nó **không đo generalization deployment**.

Train có {summary['dataset_training']['images']} file: originals mỗi lớp
{summary['dataset_training']['originals_per_class']}, còn lại là augmentation đã lưu.
Số source-group train theo lớp là {summary['dataset_training']['source_groups_per_class']}.
Source-group hiện tách theo capture/file lineage, chưa bảo đảm tách theo vật thể vật lý
hoặc phiên chụp độc lập.

![Training distribution](training_distribution.png)

## 5. Confidence, calibration và reject threshold

- Mean confidence ảnh đúng: {calibration['mean_confidence_correct']:.3f}.
- Mean confidence ảnh khác GT: {calibration['mean_confidence_wrong']:.3f}.
- NLL: {calibration['negative_log_likelihood']:.4f}; Brier:
  {calibration['brier_score']:.4f}; ECE 10-bin: {calibration['expected_calibration_error_10_bins']:.4f}.
- Threshold 0.8 nhận {high_threshold['accepted']}/259 ảnh
  ({high_threshold['coverage']:.2%}) với accuracy {high_threshold['accuracy']:.2%}.

ECE và selective accuracy cũng bị lạc quan do train overlap. Không được chọn threshold
production từ tập này; cần calibration set độc lập. Ảnh nghi nhãn sai còn cho thấy
"high-confidence error" có thể là lỗi annotation chứ không phải lỗi model.

![Confidence analysis](confidence_analysis.png)

![Selective accuracy](selective_accuracy.png)

## 6. Phân tích 285 ảnh no-GT trong `data/images`

### Prediction distribution — không phải accuracy

| Nguồn prediction | paper | plastic | organic |
|---|---:|---:|---:|
| Firmware V9 metadata | {no_gt['v9_firmware_prediction_distribution'].get('paper', 0)} | {no_gt['v9_firmware_prediction_distribution'].get('plastic', 0)} | {no_gt['v9_firmware_prediction_distribution'].get('organic', 0)} |
| Offline V10 | {no_gt['v10_prediction_distribution'].get('paper', 0)} | {no_gt['v10_prediction_distribution'].get('plastic', 0)} | {no_gt['v10_prediction_distribution'].get('organic', 0)} |

V9 và V10 đồng ý top-1 trên **{no_gt['v9_v10_top1_agreement_images']}/285 =
{no_gt['v9_v10_top1_agreement']:.2%}**. Không thể nói model nào đúng trên các ảnh
không có nhãn. Chuyển dịch lớn nhất là V9 plastic -> V10 paper ({transition[1][0]}) và
V9 organic -> V10 paper ({transition[2][0]}), phù hợp việc V10 đã được train lại bằng
nhiều ảnh carton/giấy trong chính miền ESP.

![No-GT prediction distribution](no_gt_prediction_distribution.png)

![V9 to V10 transition](no_gt_v9_v10_transition.png)

Confidence V10 trên no-GT: mean {confidence['mean']:.3f}, median
{confidence['median']:.3f}, minimum {confidence['minimum']:.3f};
{confidence['below_0_6']} ảnh <0.6, {confidence['below_0_8']} ảnh <0.8 và
{confidence['at_least_0_9']} ảnh >=0.9. Confidence cao không chứng minh đúng khi
không có GT.

10 prediction no-GT confidence thấp nhất:

| File | V10 prediction | V10 confidence | V9 prediction |
|---|---|---:|---|
{low_table}

![No-GT low confidence](no_gt_low_confidence_montage.jpg)

10 bất đồng V9/V10 có confidence V10 cao nhất:

| File | V9 | V10 | V10 confidence |
|---|---|---|---:|
{disagreement_table}

![No-GT disagreements](no_gt_v9_v10_disagreement_montage.jpg)

Review montage cho thấy nhiều frame no-GT là **thùng trống, tay người, vật chỉ lọt
một phần khung hoặc vật trắng/trong suốt rất ít texture**. Vì classifier chỉ có ba
lớp bắt buộc, nó vẫn phải trả `paper/plastic/organic` ngay cả khi không có vật hợp lệ.
Đáng chú ý, montage bất đồng có cả frame chủ yếu là bàn tay nhưng V10 vẫn trả `paper`
với confidence gần 1.0. Đây không được tính là prediction sai do chưa có GT, nhưng là
bằng chứng rõ rằng confidence hiện tại **không phải object-presence score** và model
thiếu lớp/gate `empty-background-invalid`.

Quan sát định tính cũng cho thấy nhiều chuyển dịch V9 -> V10 confidence cao là carton
hoặc giấy vò được V10 đưa về paper, còn một số chai trong được đưa về plastic. Pattern
này hợp lý về mặt thị giác nhưng vẫn cần gán nhãn để xác nhận. Trong 285 ảnh no-GT có
172 exact train file, 18 validation, 18 test và 77 unseen theo manifest; vì vậy ngay cả
phân bố confidence no-GT cũng chịu ảnh hưởng mạnh của dữ liệu đã thấy.

## 7. Embedding, coverage và giới hạn mô hình

Embedding dùng vector 96D sau global-average-pooling và {summary['embedding']['reference_images']}
train-original reference. Có {summary['embedding']['gt_true_class_ood']} ảnh GT ngoài
ngưỡng nearest-neighbor 95% của lớp thật, và {summary['embedding']['no_gt_predicted_class_ood']}
ảnh no-GT ngoài ngưỡng lớp dự đoán. Đây chỉ là diagnostic: exact train overlap tạo rất
nhiều khoảng cách bằng 0 và làm threshold thiên lệch.

![Embedding PCA](embedding_pca.png)

V10 vẫn là whole-image classifier, không detect/segment vật thể. Nó có thể học nền,
màu, silhouette và nhãn in. Coverage organic hiện thiên về cucumber/lime/chili/small
fruit; chưa chứng minh tốt trên thức ăn thừa, vỏ bẩn, rau lá, đồ chín hoặc vật liệu hỗn
hợp. Nhựa trong có nhãn giấy và carton nâu là hai failure mode đã quan sát trực tiếp.

## 8. Kết luận kỹ thuật và hành động ưu tiên

1. **Giữ một phiên ESP mới hoàn toàn độc lập**: không đưa ảnh, frame gần kề hoặc
   augmentation lineage vào train; split theo vật thể vật lý + ngày chụp.
2. **Xác nhận lại nhãn** `paper/ae41156a-...jpg`. Nếu là chai nhựa, sửa GT và ghi
   audit trail; không âm thầm đổi để tăng metric.
3. **Gán nhãn 76 ảnh chỉ có trong `data/images`** trước khi dùng chúng để so accuracy.
   `no_gt_predictions.csv` là queue review, không phải bảng lỗi.
4. Bổ sung hard cases: carton nâu/ướt/bẩn; nhựa trong có label; bao bì composite;
   vật nhỏ/lệch mép; nền và ánh sáng mới; organic ngoài rau quả xanh.
5. Thêm trạng thái `unknown/retry`, nhưng chỉ calibrate threshold trên validation độc
   lập. Các ảnh <0.6 và bất đồng V9/V10 là ưu tiên review/active learning tốt.
6. Thêm **object-presence gate hoặc lớp `empty/background/invalid`** và hard negative
   gồm thùng trống, tay người, ảnh che camera, vật ngoài khung. Threshold softmax của
   classifier ba lớp không giải quyết được trường hợp không có vật.
7. Flash V10 lên board và thu phiên mới có metadata hash
   `{summary['model']['int8_sha256']}`. Đối chiếu raw-RGB565 firmware với offline JPEG
   để đo riêng sai khác codec/preprocessing.
8. Báo cáo production nên dùng macro recall, per-class recall, confusion, calibration
   và session-level bootstrap; không chỉ dùng accuracy file-level.

## 9. Artifact

- `gt_predictions.csv`: toàn bộ ảnh có GT và prediction V9/V10.
- `gt_misclassified.csv`: ba trường hợp khác folder label.
- `no_gt_predictions.csv`: prediction no-GT, mọi dòng ghi `NOT_EVALUATED`.
- `no_gt_low_confidence.csv`: queue review theo confidence.
- `no_gt_v9_v10_disagreements.csv`: queue review theo model disagreement.
- `summary.json`: toàn bộ số liệu máy đọc được.
- Các PNG/JPG: confusion, transition, confidence, threshold, PCA và montage.

## 10. Giới hạn diễn giải

- Folder name được coi là GT theo yêu cầu, nhưng báo cáo không tự xác minh mọi nhãn.
- V10 chạy local trên JPEG nén, không phải framebuffer RGB565 gốc.
- No-GT tuyệt đối không có accuracy/error rate trong báo cáo.
- PCA là chiếu 2D để quan sát, không phải bằng chứng phân lớp.
- Kết quả GT bị train exposure rất lớn; không dùng 98.84% làm deployment claim.
"""


def _bullet_counts(values: dict) -> str:
    order = [key for key in EXPOSURE_ORDER if key in values]
    order.extend(sorted(set(values) - set(order)))
    return "\n".join(f"- `{key}`: **{values[key]}**" for key in order)


def _write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _normalize_rows(values: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(values, axis=1, keepdims=True)
    return values / np.maximum(norms, 1e-12)


def _stringify_bools(values: dict) -> dict:
    return {
        key: str(value) if isinstance(value, (bool, np.bool_)) else value
        for key, value in values.items()
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    main()
