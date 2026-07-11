from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import numpy as np
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix
from sklearn.metrics import f1_score
import tensorflow as tf

try:
    from .dataset_cnn import (
        ID_TO_LABEL,
        OTHER_LABEL,
        THREE_WAY_LABELS,
        load_dataset_splits,
        load_images,
        samples_from_class_dirs,
    )
except ImportError:
    from dataset_cnn import (
        ID_TO_LABEL,
        OTHER_LABEL,
        THREE_WAY_LABELS,
        load_dataset_splits,
        load_images,
        samples_from_class_dirs,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate float or INT8 model.")
    parser.add_argument("--model", default="artifacts/model_int8.tflite")
    parser.add_argument("--data", default="trashnet/data")
    parser.add_argument("--thresholds", default="artifacts/thresholds.json")
    parser.add_argument("--centroids", default="artifacts/centroids.json")
    parser.add_argument("--image-size", type=int, default=96)
    parser.add_argument("--out", default="artifacts")
    parser.add_argument("--seed", type=int, default=42)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    known_samples, other_samples = load_eval_samples(args.data, args.seed)
    x_known, y_known, skipped_known = load_images(known_samples, args.image_size)
    if other_samples:
        x_other, y_other, skipped_other = load_images(other_samples, args.image_size)
        y_other = np.full_like(y_other, OTHER_LABEL)
    else:
        x_other = np.empty((0, args.image_size, args.image_size, 3), dtype=np.float32)
        y_other = np.empty((0,), dtype=np.int64)
        skipped_other = []

    predictor = load_predictor(args.model)
    known_logits, known_embeddings = predictor.predict(x_known)
    other_logits, other_embeddings = predictor.predict(x_other) if len(x_other) else (
        np.empty((0, 2), dtype=np.float32),
        np.empty((0, 32), dtype=np.float32),
    )

    thresholds = load_json(args.thresholds) if Path(args.thresholds).is_file() else None
    centroids = load_centroids(args.centroids) if Path(args.centroids).is_file() else None

    plain_metrics = evaluate_plain_known(known_logits, y_known)
    rejection_metrics = evaluate_with_rejection(
        y_known,
        known_logits,
        known_embeddings,
        y_other,
        other_logits,
        other_embeddings,
        thresholds,
        centroids,
    )

    metrics = {
        "model": str(args.model),
        "model_type": predictor.kind,
        "known_samples": len(known_samples),
        "other_samples": len(other_samples),
        "skipped_images": skipped_known + skipped_other,
        "plain_known": plain_metrics,
        "with_rejection": rejection_metrics,
    }

    suffix = "int8" if predictor.kind == "tflite" else "float_eval"
    metrics_path = out_dir / f"metrics_{suffix}.json"
    metrics_path.write_text(
        json.dumps(metrics, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    if predictor.kind == "tflite":
        write_confusion_csv(
            out_dir / "confusion_matrix_int8.csv",
            rejection_metrics["confusion_matrix"],
        )
        update_aggregate_metrics(out_dir / "metrics.json", "int8", metrics)

    print(json.dumps(metrics, indent=2, ensure_ascii=False))
    print(f"Saved metrics: {metrics_path}")


class KerasPredictor:
    kind = "keras"

    def __init__(self, model_path: str) -> None:
        self.model = tf.keras.models.load_model(model_path, compile=False)

    def predict(self, x: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        if len(x) == 0:
            return np.empty((0, 2), dtype=np.float32), np.empty((0, 32), dtype=np.float32)
        outputs = self.model.predict(x, batch_size=32, verbose=0)
        if isinstance(outputs, (list, tuple)):
            return identify_outputs(outputs)
        embedding_model = tf.keras.Model(
            inputs=self.model.input,
            outputs=self.model.get_layer("embedding").output,
        )
        embeddings = embedding_model.predict(x, batch_size=32, verbose=0)
        return np.asarray(outputs), np.asarray(embeddings)


class TFLitePredictor:
    kind = "tflite"

    def __init__(self, model_path: str) -> None:
        self.interpreter = tf.lite.Interpreter(model_path=model_path)
        self.interpreter.allocate_tensors()
        self.input_detail = self.interpreter.get_input_details()[0]
        self.output_details = self.interpreter.get_output_details()

    def predict(self, x: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        logits_rows: list[np.ndarray] = []
        embedding_rows: list[np.ndarray] = []
        for image in x:
            quantized = self.quantize_input(image[np.newaxis, ...])
            self.interpreter.set_tensor(self.input_detail["index"], quantized)
            self.interpreter.invoke()
            outputs = [
                self.dequantize_output(detail, self.interpreter.get_tensor(detail["index"]))
                for detail in self.output_details
            ]
            logits, embedding = identify_outputs(outputs)
            logits_rows.append(logits[0])
            embedding_rows.append(embedding[0])
        if not logits_rows:
            return np.empty((0, 2), dtype=np.float32), np.empty((0, 32), dtype=np.float32)
        return np.vstack(logits_rows), np.vstack(embedding_rows)

    def quantize_input(self, image: np.ndarray) -> np.ndarray:
        scale, zero_point = self.input_detail["quantization"]
        dtype = self.input_detail["dtype"]
        if scale == 0:
            return image.astype(dtype)
        values = np.round(image / scale + zero_point)
        info = np.iinfo(dtype)
        return np.clip(values, info.min, info.max).astype(dtype)

    @staticmethod
    def dequantize_output(detail: dict, values: np.ndarray) -> np.ndarray:
        scale, zero_point = detail["quantization"]
        if scale == 0:
            return values.astype(np.float32)
        return (values.astype(np.float32) - zero_point) * scale


def load_predictor(model_path: str):
    return TFLitePredictor(model_path) if model_path.endswith(".tflite") else KerasPredictor(model_path)


def load_eval_samples(data: str, seed: int):
    path = Path(data)
    try:
        splits = load_dataset_splits(path, seed=seed)
        return splits.test_known, splits.test_other
    except Exception:
        known = samples_from_class_dirs(
            path, split="test", include_known=True, include_other=False
        )
        other = samples_from_class_dirs(
            path, split="test", include_known=False, include_other=True
        )
        return known, other


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


def evaluate_plain_known(logits: np.ndarray, y_true: np.ndarray) -> dict:
    y_pred = np.argmax(logits, axis=1)
    labels = sorted(ID_TO_LABEL)
    target_names = [ID_TO_LABEL[index] for index in labels]
    report = classification_report(
        y_true,
        y_pred,
        labels=labels,
        target_names=target_names,
        output_dict=True,
        zero_division=0,
    )
    return {
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "macro_f1": float(
            f1_score(y_true, y_pred, labels=labels, average="macro", zero_division=0)
        ),
        "recall_paper": float(report["paper"]["recall"]),
        "recall_plastic": float(report["plastic"]["recall"]),
        "classification_report": report,
        "confusion_matrix": confusion_matrix(y_true, y_pred, labels=labels).tolist(),
    }


def evaluate_with_rejection(
    y_known: np.ndarray,
    known_logits: np.ndarray,
    known_embeddings: np.ndarray,
    y_other: np.ndarray,
    other_logits: np.ndarray,
    other_embeddings: np.ndarray,
    thresholds: dict | None,
    centroids: dict[int, np.ndarray] | None,
) -> dict:
    known_pred = reject_predictions(known_logits, known_embeddings, thresholds, centroids)
    other_pred = reject_predictions(other_logits, other_embeddings, thresholds, centroids)

    y_true = np.concatenate([y_known, y_other])
    y_pred = np.concatenate([known_pred, other_pred])
    labels = [0, 1, 2]
    names = [THREE_WAY_LABELS[index] for index in labels]
    report = classification_report(
        y_true,
        y_pred,
        labels=labels,
        target_names=names,
        output_dict=True,
        zero_division=0,
    )
    other_false_accept = float(np.mean(other_pred != OTHER_LABEL)) if len(other_pred) else 0.0
    return {
        "accuracy": float(accuracy_score(y_true, y_pred)) if len(y_true) else 0.0,
        "macro_f1": float(
            f1_score(y_true, y_pred, labels=labels, average="macro", zero_division=0)
        )
        if len(y_true)
        else 0.0,
        "paper_recall": float(report["paper"]["recall"]),
        "plastic_recall": float(report["plastic"]["recall"]),
        "other_false_accept_rate": other_false_accept,
        "known_reject_rate": float(np.mean(known_pred == OTHER_LABEL)) if len(known_pred) else 0.0,
        "classification_report": report,
        "confusion_matrix": confusion_matrix(y_true, y_pred, labels=labels).tolist(),
    }


def reject_predictions(
    logits: np.ndarray,
    embeddings: np.ndarray,
    thresholds: dict | None,
    centroids: dict[int, np.ndarray] | None,
) -> np.ndarray:
    if len(logits) == 0:
        return np.empty((0,), dtype=np.int64)
    probabilities = softmax(logits)
    predicted = np.argmax(probabilities, axis=1).astype(np.int64)
    if thresholds is None:
        return predicted

    confidence = np.max(probabilities, axis=1)
    sorted_prob = np.sort(probabilities, axis=1)
    margin = sorted_prob[:, -1] - sorted_prob[:, -2]
    accepted = (
        (confidence >= float(thresholds["confidence_min"]))
        & (margin >= float(thresholds["margin_min"]))
    )

    if thresholds.get("use_embedding_distance", False) and centroids is not None:
        distances = np.asarray(
            [
                np.linalg.norm(embeddings[index] - centroids[int(predicted[index])])
                for index in range(len(predicted))
            ]
        )
        distance_limit = np.where(
            predicted == 0,
            float(thresholds["paper_distance_max"]),
            float(thresholds["plastic_distance_max"]),
        )
        accepted &= distances <= distance_limit

    return np.where(accepted, predicted, OTHER_LABEL).astype(np.int64)


def softmax(logits: np.ndarray) -> np.ndarray:
    logits = np.asarray(logits, dtype=np.float32)
    logits = logits - np.max(logits, axis=1, keepdims=True)
    exp = np.exp(logits)
    return exp / np.sum(exp, axis=1, keepdims=True)


def load_json(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_centroids(path: str) -> dict[int, np.ndarray]:
    payload = load_json(path)
    return {
        0: np.asarray(payload["paper"], dtype=np.float32),
        1: np.asarray(payload["plastic"], dtype=np.float32),
    }


def write_confusion_csv(path: Path, matrix: list[list[int]]) -> None:
    labels = ["actual/predicted", "paper", "plastic", "other"]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(labels)
        for index, row in enumerate(matrix):
            writer.writerow([THREE_WAY_LABELS[index], *row])


def update_aggregate_metrics(path: Path, key: str, payload: dict) -> None:
    aggregate = {}
    if path.is_file():
        aggregate = json.loads(path.read_text(encoding="utf-8"))
    aggregate[key] = payload
    path.write_text(json.dumps(aggregate, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
