"""Small dependency-free classification metric helpers."""

import numpy as np


def classification_metrics(truth: np.ndarray, probabilities: np.ndarray) -> dict:
    truth = np.asarray(truth, dtype=np.int64)
    predicted = np.asarray(probabilities).argmax(axis=1)
    classes = probabilities.shape[1]
    matrix = np.zeros((classes, classes), dtype=np.int64)
    for actual, guess in zip(truth, predicted):
        matrix[actual, guess] += 1
    recalls = []
    precisions = []
    for index in range(classes):
        tp = matrix[index, index]
        recalls.append(float(tp / max(1, matrix[index, :].sum())))
        precisions.append(float(tp / max(1, matrix[:, index].sum())))
    accuracy = float(np.mean(predicted == truth))
    return {
        "accuracy": accuracy,
        "macro_recall": float(np.mean(recalls)),
        "minimum_class_recall": float(np.min(recalls)),
        "recall_per_class": recalls,
        "precision_per_class": precisions,
        "confusion_matrix": matrix.tolist(),
    }

