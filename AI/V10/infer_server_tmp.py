"""Evaluate V10 float and INT8 models on labelled server-tmp captures."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path

os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")

import numpy as np
import tensorflow as tf

from V10.config import ARTIFACTS_DIR, CLASS_NAMES, DATASET_DIR, REPOSITORY_DIR
from V10.data_pipeline import preprocess_file_tensor
from V10.metrics import classification_metrics


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--server-root", type=Path, default=REPOSITORY_DIR / "server-tmp")
    parser.add_argument("--artifacts", type=Path, default=ARTIFACTS_DIR)
    parser.add_argument(
        "--out", type=Path, default=ARTIFACTS_DIR / "server_tmp_int8_analysis"
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    server_root = args.server_root.resolve()
    artifacts = args.artifacts.resolve()
    output = args.out.resolve()
    output.mkdir(parents=True, exist_ok=True)

    labelled = []
    extensions = {".jpg", ".jpeg", ".png", ".bmp"}
    for label_id, label in enumerate(CLASS_NAMES):
        folder = server_root / label
        if not folder.is_dir():
            raise NotADirectoryError(folder)
        for path in sorted(folder.iterdir()):
            if path.is_file() and path.suffix.lower() in extensions:
                labelled.append((path, label_id, label, _sha256(path)))
    if not labelled:
        raise RuntimeError("No labelled server-tmp images were found")

    exposure = _load_exposure(DATASET_DIR / "manifest.csv")
    images = np.stack([
        preprocess_file_tensor(tf.constant(str(path))).numpy()
        for path, _, _, _ in labelled
    ])
    truth = np.asarray([label_id for _, label_id, _, _ in labelled], np.int64)

    float_model = tf.keras.models.load_model(
        artifacts / "model_float.keras", compile=False
    )
    float_probabilities = float_model.predict(images, batch_size=16, verbose=0)

    interpreter = tf.lite.Interpreter(model_path=str(artifacts / "model_int8.tflite"))
    interpreter.allocate_tensors()
    input_detail = interpreter.get_input_details()[0]
    output_detail = interpreter.get_output_details()[0]
    int8_probabilities = np.stack([
        _invoke_int8(interpreter, input_detail, output_detail, image)
        for image in images
    ])

    float_prediction = float_probabilities.argmax(axis=1)
    int8_prediction = int8_probabilities.argmax(axis=1)
    rows = []
    exposure_counts = Counter()
    for index, (path, label_id, label, digest) in enumerate(labelled):
        seen = _exposure_for_hash(exposure, digest)
        exposure_counts[seen] += 1
        row = {
            "path": path.relative_to(server_root).as_posix(),
            "sha256": digest,
            "truth": label,
            "float_prediction": CLASS_NAMES[int(float_prediction[index])],
            "int8_prediction": CLASS_NAMES[int(int8_prediction[index])],
            "float_correct": bool(float_prediction[index] == label_id),
            "int8_correct": bool(int8_prediction[index] == label_id),
            "int8_confidence": float(np.max(int8_probabilities[index])),
            "training_exposure": seen,
        }
        row.update({
            f"int8_{class_name}": float(int8_probabilities[index, class_id])
            for class_id, class_name in enumerate(CLASS_NAMES)
        })
        rows.append(row)

    float_metrics = classification_metrics(truth, float_probabilities)
    int8_metrics = classification_metrics(truth, int8_probabilities)
    unseen_indices = np.asarray([
        row["training_exposure"] == "unseen" for row in rows
    ])
    unseen_metrics = None
    if np.any(unseen_indices):
        unseen_metrics = classification_metrics(
            truth[unseen_indices], int8_probabilities[unseen_indices]
        )
    high_confidence = np.max(int8_probabilities, axis=1) >= 0.8
    high_confidence_accuracy = (
        float(np.mean(int8_prediction[high_confidence] == truth[high_confidence]))
        if np.any(high_confidence) else None
    )
    report = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "images": len(labelled),
        "labels": list(CLASS_NAMES),
        "counts": dict(Counter(label for _, _, label, _ in labelled)),
        "preprocessing": "exact V10/ESP-TRASH-V3 4:3 crop + 128x96 integer contract",
        "float": float_metrics,
        "int8": int8_metrics,
        "int8_minus_float_accuracy": int8_metrics["accuracy"] - float_metrics["accuracy"],
        "top1_disagreements": int(np.sum(float_prediction != int8_prediction)),
        "mean_probability_absolute_error": float(
            np.mean(np.abs(float_probabilities - int8_probabilities))
        ),
        "maximum_probability_absolute_error": float(
            np.max(np.abs(float_probabilities - int8_probabilities))
        ),
        "training_exposure": dict(exposure_counts),
        "unseen_int8": unseen_metrics,
        "confidence_at_least_0_8": {
            "images": int(np.sum(high_confidence)),
            "accuracy": high_confidence_accuracy,
        },
        "interpretation_limit": (
            "dataset_augmented_v9 was built from these server captures; metrics on exposed "
            "files/lineages measure memorization plus pipeline consistency, not independent generalization."
        ),
    }
    _write_csv(output / "predictions.csv", rows)
    _write_csv(
        output / "misclassified.csv", [row for row in rows if not row["int8_correct"]]
    )
    (output / "summary.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (output / "REPORT.md").write_text(_render_markdown(report), encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))


def _load_exposure(path: Path) -> dict[str, dict[str, set[str]]]:
    rows = list(csv.DictReader(path.open(encoding="utf-8", newline="")))
    result: dict[str, dict[str, set[str]]] = defaultdict(
        lambda: {"exact": set(), "lineage": set()}
    )
    for row in rows:
        result[row["sha256"]]["exact"].add(row["split"])
        source_hash = row.get("source_sha256", "")
        if source_hash:
            result[source_hash]["lineage"].add(row["split"])
    return result


def _exposure_for_hash(exposure: dict, digest: str) -> str:
    item = exposure.get(digest)
    if not item:
        return "unseen"
    if "train" in item["exact"]:
        return "exact_train_file"
    if "train" in item["lineage"]:
        return "train_lineage"
    heldout = sorted(item["exact"] | item["lineage"])
    return "heldout_" + "+".join(heldout) if heldout else "unseen"


def _invoke_int8(interpreter, input_detail, output_detail, image: np.ndarray) -> np.ndarray:
    input_scale, input_zero = input_detail["quantization"]
    output_scale, output_zero = output_detail["quantization"]
    quantized = np.clip(
        np.rint(image / input_scale) + input_zero, -128, 127
    ).astype(np.int8)[None, ...]
    interpreter.set_tensor(input_detail["index"], quantized)
    interpreter.invoke()
    raw = interpreter.get_tensor(output_detail["index"])[0]
    return (raw.astype(np.float32) - output_zero) * output_scale


def _write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _render_markdown(report: dict) -> str:
    metrics = report["int8"]
    confusion = metrics["confusion_matrix"]
    exposure_lines = "\n".join(
        f"- `{key}`: {value}" for key, value in report["training_exposure"].items()
    )
    unseen = report["unseen_int8"]
    unseen_text = (
        f"{unseen['accuracy']:.2%} trên {sum(sum(row) for row in unseen['confusion_matrix'])} ảnh"
        if unseen else "không có ảnh hoàn toàn unseen"
    )
    return f"""# V10 INT8 inference trên server-tmp

## Kết quả

- INT8 accuracy: **{metrics['accuracy']:.2%}** ({round(metrics['accuracy'] * report['images'])}/{report['images']}).
- Balanced/macro recall: **{metrics['macro_recall']:.2%}**.
- Macro-F1: **{metrics['macro_f1']:.3f}**.
- Float accuracy: **{report['float']['accuracy']:.2%}**.
- Float/INT8 đổi top-1: **{report['top1_disagreements']}** ảnh.
- Ảnh confidence >= 0.8: **{report['confidence_at_least_0_8']['images']}**, accuracy **{report['confidence_at_least_0_8']['accuracy']:.2%}**.

| true \\ predicted | paper | plastic | organic |
|---|---:|---:|---:|
| paper | {confusion[0][0]} | {confusion[0][1]} | {confusion[0][2]} |
| plastic | {confusion[1][0]} | {confusion[1][1]} | {confusion[1][2]} |
| organic | {confusion[2][0]} | {confusion[2][1]} | {confusion[2][2]} |

## Kiểm tra leakage/exposure

{exposure_lines}

Accuracy trên subset hoàn toàn unseen: {unseen_text}.

**Giới hạn diễn giải:** `dataset_augmented_v9` được tạo từ chính các ảnh
`server-tmp`. Vì vậy kết quả tổng ở trên xác nhận model và preprocessing mới xử lý
đúng tập dữ liệu đã đưa vào pipeline, nhưng không phải phép đo tổng quát hóa độc lập.
Hãy giữ một phiên chụp mới, chưa dùng làm source/augmentation, cho acceptance test cuối.
"""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    main()
