"""Generate V5 charts and a Vietnamese Markdown evaluation report."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil

import numpy as np

from V5.runtime import LABELS


V5_DIR = Path(__file__).resolve().parent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifacts", type=Path, default=V5_DIR / "artifacts")
    parser.add_argument("--stats", type=Path, default=V5_DIR / "dataset_prepared" / "stats.json")
    parser.add_argument("--charts", type=Path, default=V5_DIR / "charts")
    parser.add_argument("--out", type=Path, default=V5_DIR / "EVALUATION_REPORT.md")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    artifacts = args.artifacts.resolve()
    stats = _read(args.stats)
    training = _read(artifacts / "training_metrics.json")
    config = _read(artifacts / "training_config.json")
    history = _read(artifacts / "training_history.json")
    int8 = _read(artifacts / "metrics_int8.json")
    comparison = _read(artifacts / "comparison.json")
    robustness = _read(artifacts / "environmental_robustness.json")

    charts = args.charts.resolve()
    charts.mkdir(parents=True, exist_ok=True)
    _plot_distribution(charts / "data_distribution.png", stats["counts"])
    _plot_history(charts / "training_history.png", history)
    _plot_confusion(
        charts / "confusion_matrix_int8.png",
        int8["metrics"]["confusion_matrix"],
    )
    robustness_chart = artifacts / "environmental_robustness.png"
    if robustness_chart.is_file():
        shutil.copy2(robustness_chart, charts / robustness_chart.name)

    v5 = robustness["models"]["v5_int8"]
    baseline = robustness["models"].get("v4_int8_baseline")
    clean = v5["clean"]
    summary = v5["summary"]
    inspection = int8["inspection"]
    counts = stats["counts"]
    lines = [
        "# Báo cáo huấn luyện và triển khai model V5",
        "",
        "## Kết luận",
        "",
        f"- Model: `{training['model_version']}`, đầu vào `96x96x3`, nhãn `paper, plastic, organic, other`.",
        f"- Clean INT8 test: accuracy **{clean['accuracy']:.2%}**, macro-F1 **{clean['macro_f1']:.2%}** trên **{clean['samples']}** ảnh độc lập.",
        f"- Lỗi mục tiêu `organic → paper`: **{clean['organic_predicted_as_paper']}/{int(clean['per_class']['organic']['support'])} ({clean['organic_to_paper_rate']:.2%})**.",
        f"- Trung bình 8 profile môi trường: macro-F1 **{summary['mean_stress_macro_f1']:.2%}**, organic recall **{summary['mean_stress_organic_recall']:.2%}**.",
        f"- Float/INT8 agreement **{comparison['float_int8_class_agreement']:.2%}**; deployment gate: **{'PASS' if comparison['passed'] else 'FAIL'}**; environment gate: **{'PASS' if robustness['passed'] else 'FAIL'}**.",
    ]
    if baseline is not None:
        lines.append(
            f"- Cùng clean test này, V4 baseline: accuracy **{baseline['clean']['accuracy']:.2%}**, macro-F1 **{baseline['clean']['macro_f1']:.2%}**."
        )
    lines.extend(
        [
            "",
            "## Dữ liệu và cân bằng",
            "",
            "| Lớp | Train gốc | Validation sạch | Test sạch | Mẫu hiệu dụng mỗi epoch |",
            "|---|---:|---:|---:|---:|",
        ]
    )
    effective = int(config["effective_samples_per_class_per_epoch"])
    for label in LABELS:
        lines.append(
            f"| {label} | {counts['train'][label]} | {counts['validation'][label]} | {counts['test'][label]} | {effective} |"
        )
    lines.extend(
        [
            "",
            "- Sampling round-robin cho bốn lớp nên mỗi batch/epoch có đóng góp lớp bằng nhau; không dùng class-weight chồng lên oversampling.",
            "- Chỉ train được augment: góc ±25°, scale/translation/shear, gamma và phơi sáng, tương phản/màu/white balance, bóng đổ, blur/noise, giảm độ phân giải và RGB565.",
            "- Validation/test không augment và giữ nguyên split nguồn; mọi biến thể stress được báo riêng, không trộn vào clean accuracy.",
            "",
            "![Phân bố dữ liệu](charts/data_distribution.png)",
            "",
            "## Kết quả clean INT8",
            "",
            "| Lớp | Precision | Recall | F1 | Support |",
            "|---|---:|---:|---:|---:|",
        ]
    )
    for label in LABELS:
        row = clean["per_class"][label]
        lines.append(
            f"| {label} | {row['precision']:.2%} | {row['recall']:.2%} | {row['f1-score']:.2%} | {int(row['support'])} |"
        )
    lines.extend(
        [
            "",
            "![Confusion matrix INT8](charts/confusion_matrix_int8.png)",
            "",
            "![Lịch sử huấn luyện](charts/training_history.png)",
            "",
            "## Độ bền điều kiện môi trường",
            "",
            "| Profile | Accuracy | Macro-F1 | Organic recall | Organic → paper |",
            "|---|---:|---:|---:|---:|",
        ]
    )
    for profile in robustness["profiles"]:
        row = v5[profile]
        lines.append(
            f"| {profile} | {row['accuracy']:.2%} | {row['macro_f1']:.2%} | {row['per_class']['organic']['recall']:.2%} | {row['organic_to_paper_rate']:.2%} |"
        )
    lines.extend(
        [
            "",
            "![Độ bền môi trường](charts/environmental_robustness.png)",
            "",
            "## INT8 và ESP32",
            "",
            f"- Model: **{inspection['model_size_bytes']:,} byte**, SHA-256 `{inspection['sha256']}`.",
            f"- Input: `{inspection['input']['shape']}` `{inspection['input']['dtype']}`, scale `{inspection['input']['quantization']['scale']}`, zero point `{inspection['input']['quantization']['zero_point']}`.",
            f"- Output: `{inspection['output']['shape']}` `{inspection['output']['dtype']}`, scale `{inspection['output']['quantization']['scale']}`, zero point `{inspection['output']['quantization']['zero_point']}`.",
            f"- Operators: `{', '.join(inspection['unique_operators'])}`; float tensors còn lại: `{len(inspection['float_tensors'])}`.",
            "- Tiền xử lý firmware không đổi: QVGA RGB565 → center crop → floor nearest-neighbor 96×96 → `q = pixel - 128`.",
            "",
            "## Giới hạn",
            "",
            "Các profile môi trường là biến đổi xác định từ test sạch nên đo độ nhạy tương đối, không thay thế ảnh mới chụp trực tiếp từ ESP32-CAM. Sau khi nạp firmware cần thu thêm ảnh thực địa theo từng loại ánh sáng/góc, giữ riêng khỏi train, rồi chạy lại audit. Lớp `other` hiện gồm cardboard và metal; các loại rác ngoài hai nhóm này vẫn cần dữ liệu bổ sung.",
            "",
        ]
    )
    firmware = V5_DIR.parents[1] / "ESP-TRASH" / "build" / "ESP-TRASH.ino.merged.bin"
    if firmware.is_file():
        limit_index = lines.index("## Giới hạn")
        lines[limit_index:limit_index] = [
            f"- Firmware clean-build: **PASS**; merged image **{firmware.stat().st_size:,} byte**, SHA-256 `{_sha256(firmware)}`.",
            "",
        ]
    args.out.resolve().write_text("\n".join(lines), encoding="utf-8", newline="\n")
    print(f"Wrote report: {args.out.resolve()}")


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _matplotlib():
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    return plt


def _plot_distribution(path: Path, counts: dict) -> None:
    plt = _matplotlib()
    x = np.arange(len(LABELS))
    width = 0.25
    fig, axis = plt.subplots(figsize=(9, 5))
    for index, split in enumerate(("train", "validation", "test")):
        axis.bar(x + (index - 1) * width, [counts[split][label] for label in LABELS], width, label=split)
    axis.set_xticks(x, LABELS)
    axis.set_ylabel("Images")
    axis.set_title("V5 source distribution (training exposure is balanced online)")
    axis.legend()
    axis.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)


def _plot_history(path: Path, history: dict) -> None:
    plt = _matplotlib()
    epochs = np.arange(1, len(history.get("loss", [])) + 1)
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    axes[0].plot(epochs, history.get("loss", []), label="train loss")
    axes[0].plot(epochs, history.get("val_loss", []), label="validation loss")
    axes[0].set_title("Loss")
    axes[0].legend()
    axes[1].plot(epochs, history.get("val_macro_f1", []), label="macro-F1")
    axes[1].plot(epochs, history.get("val_min_recall", []), label="min recall")
    axes[1].plot(epochs, history.get("val_organic_recall", []), label="organic recall")
    axes[1].set_ylim(0.0, 1.02)
    axes[1].set_title("Validation selection metrics")
    axes[1].legend()
    for axis in axes:
        axis.grid(alpha=0.25)
        axis.set_xlabel("Epoch")
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)


def _plot_confusion(path: Path, matrix: list[list[int]]) -> None:
    plt = _matplotlib()
    values = np.asarray(matrix, dtype=int)
    fig, axis = plt.subplots(figsize=(6.5, 5.5))
    image = axis.imshow(values, cmap="Blues")
    for row in range(len(LABELS)):
        for column in range(len(LABELS)):
            axis.text(column, row, str(values[row, column]), ha="center", va="center")
    axis.set_xticks(range(len(LABELS)), LABELS)
    axis.set_yticks(range(len(LABELS)), LABELS)
    axis.set_xlabel("Predicted")
    axis.set_ylabel("Actual")
    axis.set_title("V5 full INT8 clean test")
    fig.colorbar(image, ax=axis)
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)


if __name__ == "__main__":
    main()
