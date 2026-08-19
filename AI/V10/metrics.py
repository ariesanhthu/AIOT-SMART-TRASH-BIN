"""Classification metrics shared by float and INT8 evaluation."""

import numpy as np


def classification_metrics(truth: np.ndarray, probabilities: np.ndarray) -> dict:
    truth = np.asarray(truth, dtype=np.int64)
    probabilities = np.asarray(probabilities, dtype=np.float32)
    predicted = probabilities.argmax(axis=1)
    classes = probabilities.shape[1]
    matrix = np.zeros((classes, classes), dtype=np.int64)
    for actual, guess in zip(truth, predicted):
        matrix[actual, guess] += 1
    recalls = []
    precisions = []
    f1_scores = []
    for index in range(classes):
        tp = int(matrix[index, index])
        recall = float(tp / max(1, matrix[index, :].sum()))
        precision = float(tp / max(1, matrix[:, index].sum()))
        recalls.append(recall)
        precisions.append(precision)
        f1_scores.append(
            0.0 if recall + precision == 0.0 else 2.0 * recall * precision / (recall + precision)
        )
    return {
        "accuracy": float(np.mean(predicted == truth)),
        "macro_recall": float(np.mean(recalls)),
        "macro_precision": float(np.mean(precisions)),
        "macro_f1": float(np.mean(f1_scores)),
        "minimum_class_recall": float(np.min(recalls)),
        "recall_per_class": recalls,
        "precision_per_class": precisions,
        "confusion_matrix": matrix.tolist(),
    }
