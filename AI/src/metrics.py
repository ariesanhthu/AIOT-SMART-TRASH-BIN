"""Metrics shared by training and float/INT8 evaluation."""

from __future__ import annotations

from typing import Any

import numpy as np
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
)

try:
    from .config import LABELS
except ImportError:
    from config import LABELS  # type: ignore


def classification_metrics(y_true: np.ndarray, logits: np.ndarray) -> dict[str, Any]:
    labels = np.arange(len(LABELS), dtype=np.int64)
    truth = np.asarray(y_true, dtype=np.int64).reshape(-1)
    scores = np.asarray(logits, dtype=np.float32)
    if scores.ndim != 2 or scores.shape[1] != len(LABELS):
        raise ValueError(
            f"Expected logits shaped [N,{len(LABELS)}], got {scores.shape}"
        )
    if len(truth) != len(scores) or len(truth) == 0:
        raise ValueError("Metrics require equally sized, non-empty labels and logits")
    predictions = np.argmax(scores, axis=1).astype(np.int64)
    report = classification_report(
        truth,
        predictions,
        labels=labels,
        target_names=list(LABELS),
        output_dict=True,
        zero_division=0,
    )
    return {
        "samples": int(len(truth)),
        "accuracy": float(accuracy_score(truth, predictions)),
        "balanced_accuracy": float(balanced_accuracy_score(truth, predictions)),
        "macro_precision": float(
            precision_score(truth, predictions, labels=labels, average="macro", zero_division=0)
        ),
        "macro_recall": float(
            recall_score(truth, predictions, labels=labels, average="macro", zero_division=0)
        ),
        "macro_f1": float(
            f1_score(truth, predictions, labels=labels, average="macro", zero_division=0)
        ),
        "per_class": {label: report[label] for label in LABELS},
        "confusion_matrix": confusion_matrix(
            truth, predictions, labels=labels
        ).astype(int).tolist(),
    }


def stable_softmax(logits: np.ndarray) -> np.ndarray:
    scores = np.asarray(logits, dtype=np.float32)
    scores = scores - np.max(scores, axis=-1, keepdims=True)
    exponentials = np.exp(scores)
    return exponentials / np.sum(exponentials, axis=-1, keepdims=True)
