"""Small dependency-light classification metrics for V7."""

from __future__ import annotations

import numpy as np

from V7.config import CLASS_NAMES


def confusion_matrix(y_true: np.ndarray, y_pred: np.ndarray) -> np.ndarray:
    truth = np.asarray(y_true, dtype=np.int64)
    predicted = np.asarray(y_pred, dtype=np.int64)
    if truth.shape != predicted.shape:
        raise ValueError(
            f"Prediction shape mismatch: {truth.shape} vs {predicted.shape}"
        )
    matrix = np.zeros((len(CLASS_NAMES), len(CLASS_NAMES)), dtype=np.int64)
    for expected, actual in zip(truth, predicted, strict=True):
        if not 0 <= expected < len(CLASS_NAMES) or not 0 <= actual < len(CLASS_NAMES):
            raise ValueError("V7 classification index outside [0,2]")
        matrix[expected, actual] += 1
    return matrix


def classification_metrics(y_true: np.ndarray, probabilities: np.ndarray) -> dict:
    truth = np.asarray(y_true, dtype=np.int64)
    scores = np.asarray(probabilities, dtype=np.float64)
    if scores.shape != (len(truth), len(CLASS_NAMES)):
        raise ValueError(
            f"Expected V7 scores {(len(truth), len(CLASS_NAMES))}, got {scores.shape}"
        )
    predicted = np.argmax(scores, axis=1)
    matrix = confusion_matrix(truth, predicted)
    recalls: list[float] = []
    precisions: list[float] = []
    f1_scores: list[float] = []
    per_class: dict[str, dict[str, float | int]] = {}
    for index, label in enumerate(CLASS_NAMES):
        true_positive = int(matrix[index, index])
        support = int(matrix[index].sum())
        predicted_count = int(matrix[:, index].sum())
        recall = true_positive / support if support else 0.0
        precision = true_positive / predicted_count if predicted_count else 0.0
        f1 = (
            2.0 * precision * recall / (precision + recall)
            if precision + recall
            else 0.0
        )
        recalls.append(recall)
        precisions.append(precision)
        f1_scores.append(f1)
        per_class[label] = {
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "support": support,
        }
    sorted_scores = np.sort(scores, axis=1)
    confidence = sorted_scores[:, -1]
    margin = sorted_scores[:, -1] - sorted_scores[:, -2]
    return {
        "accuracy": float(np.mean(predicted == truth)),
        "macro_precision": float(np.mean(precisions)),
        "macro_recall": float(np.mean(recalls)),
        "macro_f1": float(np.mean(f1_scores)),
        "minimum_class_recall": float(np.min(recalls)),
        "mean_confidence": float(np.mean(confidence)),
        "mean_margin": float(np.mean(margin)),
        "per_class": per_class,
        "confusion_matrix": matrix.tolist(),
    }
