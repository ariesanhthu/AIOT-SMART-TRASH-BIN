from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import tensorflow as tf

try:
    from .dataset_cnn import ID_TO_LABEL, OTHER_LABEL, load_dataset_splits, load_images
    from .dataset_cnn import samples_from_class_dirs
except ImportError:
    from dataset_cnn import ID_TO_LABEL, OTHER_LABEL, load_dataset_splits, load_images
    from dataset_cnn import samples_from_class_dirs


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Calibrate PAPER/PLASTIC rejection.")
    parser.add_argument("--model", default="artifacts/model_float.keras")
    parser.add_argument("--data", default="trashnet/data")
    parser.add_argument("--known", default=None)
    parser.add_argument("--other", default=None)
    parser.add_argument("--image-size", type=int, default=96)
    parser.add_argument("--out", default="artifacts")
    parser.add_argument("--target-other-false-accept", type=float, default=0.10)
    parser.add_argument("--min-known-recall", type=float, default=0.85)
    parser.add_argument("--seed", type=int, default=42)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    model = tf.keras.models.load_model(args.model, compile=False)
    splits = load_dataset_splits(args.data, seed=args.seed)

    train_samples = splits.train_known
    known_samples = (
        samples_from_class_dirs(
            args.known, split="validation", include_known=True, include_other=False
        )
        if args.known
        else splits.validation_known
    )
    other_samples = (
        samples_from_class_dirs(
            args.other, split="validation", include_known=False, include_other=True
        )
        if args.other
        else splits.validation_other
    )

    x_train, y_train, _ = load_images(train_samples, args.image_size)
    x_known, y_known, _ = load_images(known_samples, args.image_size)
    x_other, y_other, _ = load_images(other_samples, args.image_size)
    y_other = np.full_like(y_other, OTHER_LABEL)

    train_logits, train_embeddings = predict_logits_embeddings(model, x_train)
    train_prob = softmax(train_logits)
    train_pred = np.argmax(train_prob, axis=1)
    centroids = compute_centroids(train_embeddings, y_train, train_pred)

    known_logits, known_embeddings = predict_logits_embeddings(model, x_known)
    other_logits, other_embeddings = predict_logits_embeddings(model, x_other)
    known_stats = build_stats(known_logits, known_embeddings, centroids)
    other_stats = build_stats(other_logits, other_embeddings, centroids)

    thresholds, calibration_metrics = search_thresholds(
        y_known,
        known_stats,
        y_other,
        other_stats,
        target_other_false_accept=args.target_other_false_accept,
        min_known_recall=args.min_known_recall,
    )

    thresholds_payload = {
        "confidence_min": thresholds["confidence_min"],
        "margin_min": thresholds["margin_min"],
        "paper_distance_max": thresholds["paper_distance_max"],
        "plastic_distance_max": thresholds["plastic_distance_max"],
        "use_embedding_distance": True,
    }
    centroids_payload = {
        ID_TO_LABEL[label]: centroids[label].astype(float).tolist()
        for label in sorted(ID_TO_LABEL)
    }

    write_json(out_dir / "thresholds.json", thresholds_payload)
    write_json(out_dir / "centroids.json", centroids_payload)
    write_json(
        out_dir / "calibration_metrics.json",
        {
            "model": str(args.model),
            "target_other_false_accept": args.target_other_false_accept,
            "min_known_recall": args.min_known_recall,
            "known_samples": len(known_samples),
            "other_samples": len(other_samples),
            "thresholds": thresholds_payload,
            "metrics": calibration_metrics,
        },
    )

    print(json.dumps(thresholds_payload, indent=2))
    print(json.dumps(calibration_metrics, indent=2))


def predict_logits_embeddings(
    model: tf.keras.Model,
    x: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    outputs = model.predict(x, batch_size=32, verbose=0)
    if isinstance(outputs, (list, tuple)):
        return identify_outputs(outputs)

    embedding_model = tf.keras.Model(
        inputs=model.input,
        outputs=model.get_layer("embedding").output,
    )
    embeddings = embedding_model.predict(x, batch_size=32, verbose=0)
    return np.asarray(outputs), np.asarray(embeddings)


def identify_outputs(outputs: list[np.ndarray] | tuple[np.ndarray, ...]) -> tuple[np.ndarray, np.ndarray]:
    logits = None
    embeddings = None
    for output in outputs:
        array = np.asarray(output)
        if array.shape[-1] == 2:
            logits = array
        elif array.shape[-1] == 32:
            embeddings = array
    if logits is None or embeddings is None:
        raise RuntimeError("Model must expose logits(2) and embedding(32)")
    return logits, embeddings


def compute_centroids(
    embeddings: np.ndarray,
    y_true: np.ndarray,
    y_pred: np.ndarray,
) -> dict[int, np.ndarray]:
    centroids: dict[int, np.ndarray] = {}
    for label in sorted(ID_TO_LABEL):
        mask = (y_true == label) & (y_pred == label)
        if not np.any(mask):
            mask = y_true == label
        centroids[label] = embeddings[mask].mean(axis=0)
    return centroids


def build_stats(
    logits: np.ndarray,
    embeddings: np.ndarray,
    centroids: dict[int, np.ndarray],
) -> dict[str, np.ndarray]:
    probabilities = softmax(logits)
    predicted = np.argmax(probabilities, axis=1)
    confidence = np.max(probabilities, axis=1)
    sorted_prob = np.sort(probabilities, axis=1)
    margin = sorted_prob[:, -1] - sorted_prob[:, -2]
    distance = np.asarray(
        [
            np.linalg.norm(embeddings[index] - centroids[int(predicted[index])])
            for index in range(len(predicted))
        ],
        dtype=np.float32,
    )
    return {
        "predicted": predicted,
        "confidence": confidence,
        "margin": margin,
        "distance": distance,
    }


def search_thresholds(
    known_true: np.ndarray,
    known_stats: dict[str, np.ndarray],
    other_true: np.ndarray,
    other_stats: dict[str, np.ndarray],
    *,
    target_other_false_accept: float,
    min_known_recall: float,
) -> tuple[dict[str, float], dict]:
    confidence_candidates = np.unique(
        np.concatenate(
            [
                np.linspace(0.50, 0.99, 50),
                np.quantile(known_stats["confidence"], np.linspace(0, 1, 11)),
                np.quantile(other_stats["confidence"], np.linspace(0, 1, 11)),
            ]
        )
    )
    margin_candidates = np.unique(
        np.concatenate(
            [
                np.linspace(0.00, 0.95, 40),
                np.quantile(known_stats["margin"], np.linspace(0, 1, 11)),
                np.quantile(other_stats["margin"], np.linspace(0, 1, 11)),
            ]
        )
    )
    paper_distance_candidates = _distance_candidates(known_true, known_stats, 0)
    plastic_distance_candidates = _distance_candidates(known_true, known_stats, 1)

    best_feasible_thresholds = None
    best_feasible_metrics = None
    best_feasible_score = -1e9
    best_relaxed_thresholds = None
    best_relaxed_metrics = None
    best_relaxed_score = -1e9

    for confidence_min in confidence_candidates:
        for margin_min in margin_candidates:
            for paper_distance in paper_distance_candidates:
                for plastic_distance in plastic_distance_candidates:
                    thresholds = {
                        "confidence_min": float(confidence_min),
                        "margin_min": float(margin_min),
                        "paper_distance_max": float(paper_distance),
                        "plastic_distance_max": float(plastic_distance),
                    }
                    metrics = evaluate_thresholds(
                        known_true,
                        known_stats,
                        other_true,
                        other_stats,
                        thresholds,
                    )
                    feasible = (
                        metrics["other_false_accept_rate"] <= target_other_false_accept
                        and metrics["paper_recall"] >= min_known_recall
                        and metrics["plastic_recall"] >= min_known_recall
                    )
                    recall_gap = abs(metrics["paper_recall"] - metrics["plastic_recall"])
                    feasible_score = (
                        metrics["macro_recall"]
                        + metrics["known_accuracy"]
                        + min(metrics["paper_recall"], metrics["plastic_recall"])
                        - 0.2 * recall_gap
                    )
                    if feasible:
                        if feasible_score > best_feasible_score:
                            best_feasible_score = feasible_score
                            best_feasible_thresholds = thresholds
                            best_feasible_metrics = metrics | {
                                "feasible": True,
                                "selection_policy": "all_targets_met",
                            }

                    recall_floor = min(metrics["paper_recall"], metrics["plastic_recall"])
                    recall_shortfall = max(0.0, min_known_recall - recall_floor)
                    relaxed_score = (
                        -metrics["other_false_accept_rate"]
                        - 4.0 * recall_shortfall
                        + 0.25 * metrics["known_accuracy"]
                        - 0.10 * metrics["known_reject_rate"]
                        - 0.10 * recall_gap
                    )
                    if relaxed_score > best_relaxed_score:
                        best_relaxed_score = relaxed_score
                        best_relaxed_thresholds = thresholds
                        best_relaxed_metrics = metrics | {
                            "feasible": False,
                            "selection_policy": "best_tradeoff_no_feasible_threshold",
                        }

    if best_feasible_thresholds is not None and best_feasible_metrics is not None:
        return best_feasible_thresholds, best_feasible_metrics

    if best_relaxed_thresholds is None or best_relaxed_metrics is None:
        raise RuntimeError("Could not calibrate rejection thresholds")
    return best_relaxed_thresholds, best_relaxed_metrics


def evaluate_thresholds(
    known_true: np.ndarray,
    known_stats: dict[str, np.ndarray],
    other_true: np.ndarray,
    other_stats: dict[str, np.ndarray],
    thresholds: dict[str, float],
) -> dict:
    known_pred = apply_thresholds(known_stats, thresholds)
    other_pred = apply_thresholds(other_stats, thresholds)

    paper_mask = known_true == 0
    plastic_mask = known_true == 1
    paper_recall = float(np.mean(known_pred[paper_mask] == 0)) if np.any(paper_mask) else 0.0
    plastic_recall = (
        float(np.mean(known_pred[plastic_mask] == 1)) if np.any(plastic_mask) else 0.0
    )
    other_false_accept = float(np.mean(other_pred != OTHER_LABEL)) if len(other_pred) else 0.0
    other_recall = 1.0 - other_false_accept
    return {
        "known_accuracy": float(np.mean(known_pred == known_true)),
        "known_reject_rate": float(np.mean(known_pred == OTHER_LABEL)),
        "paper_recall": paper_recall,
        "plastic_recall": plastic_recall,
        "other_false_accept_rate": other_false_accept,
        "macro_recall": float((paper_recall + plastic_recall + other_recall) / 3.0),
    }


def apply_thresholds(stats: dict[str, np.ndarray], thresholds: dict[str, float]) -> np.ndarray:
    predicted = stats["predicted"].astype(np.int64)
    distance_limit = np.where(
        predicted == 0,
        thresholds["paper_distance_max"],
        thresholds["plastic_distance_max"],
    )
    accepted = (
        (stats["confidence"] >= thresholds["confidence_min"])
        & (stats["margin"] >= thresholds["margin_min"])
        & (stats["distance"] <= distance_limit)
    )
    return np.where(accepted, predicted, OTHER_LABEL)


def _distance_candidates(
    y_true: np.ndarray,
    stats: dict[str, np.ndarray],
    label: int,
) -> np.ndarray:
    mask = (y_true == label) & (stats["predicted"] == label)
    distances = stats["distance"][mask]
    if len(distances) == 0:
        distances = stats["distance"][y_true == label]
    if len(distances) == 0:
        return np.asarray([0.0], dtype=np.float32)
    return np.unique(np.quantile(distances, [0.70, 0.80, 0.85, 0.90, 0.95, 0.98, 1.0]))


def softmax(logits: np.ndarray) -> np.ndarray:
    logits = np.asarray(logits, dtype=np.float32)
    logits = logits - np.max(logits, axis=1, keepdims=True)
    exp = np.exp(logits)
    return exp / np.sum(exp, axis=1, keepdims=True)


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
