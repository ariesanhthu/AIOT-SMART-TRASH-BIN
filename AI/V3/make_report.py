"""Generate V3 evaluation charts and a Vietnamese Markdown report."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


V3_DIR = Path(__file__).resolve().parent
DEFAULT_ARTIFACTS = V3_DIR / "artifacts"
DEFAULT_STATS = V3_DIR / "dataset_prepared" / "stats.json"
DEFAULT_REPORT = V3_DIR / "EVALUATION_REPORT.md"
DEFAULT_CHARTS = V3_DIR / "charts"
LABELS = ("paper", "plastic", "organic")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifacts", type=Path, default=DEFAULT_ARTIFACTS)
    parser.add_argument("--dataset-stats", type=Path, default=DEFAULT_STATS)
    parser.add_argument("--out", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--charts", type=Path, default=DEFAULT_CHARTS)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    artifacts = args.artifacts.resolve()
    charts = args.charts.resolve()
    charts.mkdir(parents=True, exist_ok=True)

    stats = _read_json(args.dataset_stats)
    training = _read_json(artifacts / "training_metrics.json")
    history = _read_json(artifacts / "training_history.json")
    float_payload = _read_json(artifacts / "metrics_float.json")
    int8_payload = _read_json(artifacts / "metrics_int8.json")
    comparison = _read_json(artifacts / "comparison.json")
    quantization = _read_json(artifacts / "quantization.json")
    metadata = _read_json(artifacts / "model_metadata.json")

    _plot_distribution(stats, charts / "data_distribution.png")
    _plot_confusion(
        int8_payload["metrics"]["confusion_matrix"],
        charts / "confusion_matrix_int8.png",
    )
    _plot_history(history, charts / "training_history.png")
    report = _render_report(
        stats=stats,
        training=training,
        float_metrics=float_payload["metrics"],
        int8_metrics=int8_payload["metrics"],
        comparison=comparison,
        quantization=quantization,
        metadata=metadata,
        float_size=(artifacts / "model_float.keras").stat().st_size,
        int8_size=(artifacts / "model_int8.tflite").stat().st_size,
    )
    args.out.resolve().write_text(report, encoding="utf-8", newline="\n")
    print(f"Saved report: {args.out.resolve()}")


def _read_json(path: Path) -> dict:
    payload = json.loads(path.resolve().read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return payload


def _plot_distribution(stats: dict, path: Path) -> None:
    original = stats["source_train_original_counts"]
    augmented = stats["source_train_augmentation_counts"]
    validation = stats["source_validation_original_counts"]
    test = stats["prepared_original_split_counts"]["test"]
    x = np.arange(len(LABELS))
    width = 0.20
    fig, ax = plt.subplots(figsize=(9, 5.4))
    series = (
        ("Train gốc", original, -1.5 * width),
        ("Train augment", augmented, -0.5 * width),
        ("Validation gốc", validation, 0.5 * width),
        ("Test holdout gốc", test, 1.5 * width),
    )
    for name, values, offset in series:
        bars = ax.bar(x + offset, [values[label] for label in LABELS], width, label=name)
        ax.bar_label(bars, padding=2, fontsize=8)
    ax.set_title("Phân bố dữ liệu V3 theo lớp")
    ax.set_ylabel("Số ảnh")
    ax.set_xticks(x, LABELS)
    ax.legend()
    ax.grid(axis="y", alpha=0.2)
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def _plot_confusion(matrix: list[list[int]], path: Path) -> None:
    values = np.asarray(matrix, dtype=np.int64)
    fig, ax = plt.subplots(figsize=(6.4, 5.6))
    image = ax.imshow(values, cmap="Blues")
    fig.colorbar(image, ax=ax, fraction=0.046, pad=0.04)
    ax.set(
        title="Confusion matrix - Full INT8 trên test holdout",
        xlabel="Nhãn dự đoán",
        ylabel="Nhãn thật",
        xticks=np.arange(len(LABELS)),
        yticks=np.arange(len(LABELS)),
        xticklabels=LABELS,
        yticklabels=LABELS,
    )
    threshold = values.max() / 2 if values.size else 0
    for row in range(values.shape[0]):
        for column in range(values.shape[1]):
            ax.text(
                column, row, str(values[row, column]),
                ha="center", va="center",
                color="white" if values[row, column] > threshold else "black",
                fontsize=13,
            )
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def _plot_history(history: dict, path: Path) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.4))
    epochs = np.arange(1, len(history.get("loss", [])) + 1)
    axes[0].plot(epochs, history.get("loss", []), label="train loss")
    axes[0].plot(epochs, history.get("val_loss", []), label="validation loss")
    axes[0].set(title="Loss", xlabel="Epoch", ylabel="Loss")
    axes[0].legend()
    axes[0].grid(alpha=0.2)
    axes[1].plot(epochs, history.get("accuracy", []), label="train accuracy")
    axes[1].plot(epochs, history.get("val_accuracy", []), label="validation accuracy")
    if "val_macro_f1" in history:
        axes[1].plot(epochs, history["val_macro_f1"], label="validation macro-F1")
    axes[1].set(title="Accuracy / F1", xlabel="Epoch", ylabel="Score", ylim=(0, 1.05))
    axes[1].legend()
    axes[1].grid(alpha=0.2)
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def _percent(value: float) -> str:
    return f"{100.0 * float(value):.2f}%"


def _size(value: int) -> str:
    return f"{value:,} byte ({value / 1024:.2f} KiB)"


def _render_report(*, stats, training, float_metrics, int8_metrics, comparison,
                   quantization, metadata, float_size, int8_size) -> str:
    original = stats["source_train_original_counts"]
    augmented = stats["source_train_augmentation_counts"]
    prepared_original = stats["prepared_original_split_counts"]
    prepared = stats["prepared_counts"]
    confusion = int8_metrics["confusion_matrix"]
    gate = "PASS" if comparison["passed"] else "FAIL"
    failed = [name.replace("_passed", "") for name, passed in comparison["gates"].items() if not passed]
    failed_text = ", ".join(failed) if failed else "không có"
    rows = "\n".join(
        f"| {label} | {original[label]} | {augmented[label]} | "
        f"{prepared_original['train'][label]} | {prepared['train'][label]} | "
        f"{prepared_original['validation'][label]} | {prepared_original['test'][label]} |"
        for label in LABELS
    )
    metric_rows = "\n".join(
        f"| {label} | {_percent(int8_metrics['per_class'][label]['precision'])} | "
        f"{_percent(int8_metrics['per_class'][label]['recall'])} | "
        f"{_percent(int8_metrics['per_class'][label]['f1-score'])} | "
        f"{int(int8_metrics['per_class'][label]['support'])} |"
        for label in LABELS
    )
    return f"""# Báo cáo huấn luyện và đánh giá model V3

## Tóm tắt

- Model: TinyCNN V3, đầu vào `96x96x3`, đầu ra 3 logits theo thứ tự `paper`, `plastic`, `organic`.
- Dữ liệu nguồn: `AI/DATASET`; tổng **{sum(original.values())} ảnh train gốc**, **{sum(augmented.values())} ảnh augment** và **{sum(stats['source_validation_original_counts'].values())} ảnh validation gốc**.
- Test độc lập là holdout theo nhóm ảnh gốc: **{sum(prepared_original['test'].values())} ảnh**. Mọi biến thể augment của ảnh test đều bị loại khỏi train.
- Full INT8 trên test: accuracy **{_percent(int8_metrics['accuracy'])}**, balanced accuracy **{_percent(int8_metrics['balanced_accuracy'])}**, macro-F1 **{_percent(int8_metrics['macro_f1'])}**.
- Quality gate triển khai: **{gate}**. Gate chưa đạt: `{failed_text}`.

![Phân bố dữ liệu](charts/data_distribution.png)

## Phân bố và cách chia dữ liệu

| Lớp | Train gốc nguồn | Ảnh augment nguồn | Train gốc đã dùng | Tổng prepared train | Validation gốc | Test holdout gốc |
|---|---:|---:|---:|---:|---:|---:|
{rows}

`validation` được dùng để chọn checkpoint nên không được gọi là test. `test` được tách từ ảnh train gốc với seed `{stats['seed']}`; ảnh gốc và các bản augment luôn ở cùng một phía để chống rò rỉ dữ liệu.

## Quá trình huấn luyện

- So với V2, V3 tăng độ rộng/sâu từ 4 lên 5 block convolution (53,387 tham số) và dùng class-weight nghịch đảo tần suất đầy đủ (`paper` 0.591, `plastic` 1.625, `organic` 1.444) để giảm ảnh hưởng của mất cân bằng dữ liệu.
- Không so sánh trực tiếp phần trăm V2 và V3 như cùng một benchmark: V3 được train sau khi `AI/DATASET` tăng từ 61 lên 97 ảnh train gốc và holdout cũng đã thay đổi.
- Tham số model: **{training['model_parameters']:,}**.
- Epoch tốt nhất / epoch đã chạy: **{training['best_epoch']} / {training['epochs_ran']}**.
- Thời gian train: **{training['training_seconds']:.2f} giây** trên môi trường hiện tại.
- Validation tại checkpoint tốt nhất: accuracy **{_percent(training['validation']['accuracy'])}**, macro-F1 **{_percent(training['validation']['macro_f1'])}**.

![Lịch sử huấn luyện](charts/training_history.png)

## Kết quả eval và test

| Model | Accuracy | Balanced accuracy | Macro-F1 |
|---|---:|---:|---:|
| Float Keras | {_percent(float_metrics['accuracy'])} | {_percent(float_metrics['balanced_accuracy'])} | {_percent(float_metrics['macro_f1'])} |
| Full INT8 TFLite | {_percent(int8_metrics['accuracy'])} | {_percent(int8_metrics['balanced_accuracy'])} | {_percent(int8_metrics['macro_f1'])} |

### Chỉ số từng lớp của model INT8

| Lớp | Precision | Recall | F1 | Support |
|---|---:|---:|---:|---:|
{metric_rows}

### Confusion matrix

Hàng là nhãn thật, cột là nhãn dự đoán; thứ tự `paper, plastic, organic`.

```text
{confusion[0]}
{confusion[1]}
{confusion[2]}
```

![Confusion matrix INT8](charts/confusion_matrix_int8.png)

## Kiểm tra lượng tử hóa và artefact

- Float → INT8 agreement: **{_percent(comparison['float_int8_class_agreement'])}**.
- Float model: `{_size(float_size)}`.
- INT8 model: **`{_size(int8_size)}`**, full integer = `{str(quantization['full_integer']).lower()}`.
- INT8 input: `{quantization['input']['dtype']}` `{quantization['input']['shape']}`, scale `{quantization['input']['quantization']['scale']}`, zero point `{quantization['input']['quantization']['zero_point']}`.
- TFLite operators: `{', '.join(quantization['unique_operators'])}`.
- SHA-256 INT8: `{metadata['artifacts']['int8_model']['sha256']}`.
- Số liệu máy đọc được nằm trong `artifacts/training_metrics.json`, `metrics_float.json`, `metrics_int8.json`, `comparison.json`; confusion matrix dạng bảng nằm ở `artifacts/confusion_matrix_int8.csv`.

## Giới hạn

Test holdout chỉ có {sum(prepared_original['test'].values())} ảnh gốc và nhiều ảnh có thể được chụp liên tiếp trong cùng bối cảnh. Vì vậy kết quả này phù hợp để so sánh V2/V3 và kiểm tra pipeline, nhưng chưa thay thế một test set thực địa hoàn toàn mới. Nên thu thêm ảnh plastic và organic đa dạng về vật thể, góc, ánh sáng và nền; giữ riêng tập đó cho lần đánh giá cuối.
"""


if __name__ == "__main__":
    main()
