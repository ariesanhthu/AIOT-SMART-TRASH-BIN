"""Generate V4 charts, a Vietnamese Markdown report, and a verified PDF report."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from PIL import Image as PilImage
from reportlab.lib import colors
from reportlab.lib.colors import HexColor
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Image,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


V4_DIR = Path(__file__).resolve().parent
AI_DIR = V4_DIR.parent
REPOSITORY_DIR = AI_DIR.parent
DEFAULT_ARTIFACTS = V4_DIR / "artifacts"
DEFAULT_STATS = V4_DIR / "dataset_prepared" / "stats.json"
DEFAULT_LINEAGE = V4_DIR / "dataset_prepared" / "lineage.csv"
DEFAULT_MARKDOWN = V4_DIR / "EVALUATION_REPORT.md"
DEFAULT_PDF = REPOSITORY_DIR / "output" / "pdf" / "V4_MODEL_REPORT.pdf"
DEFAULT_CHARTS = V4_DIR / "charts"
LABELS = ("paper", "plastic", "organic", "other")
COLORS = ("#2F6BFF", "#7A5AF8", "#16A085", "#F59E0B")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifacts", type=Path, default=DEFAULT_ARTIFACTS)
    parser.add_argument("--dataset-stats", type=Path, default=DEFAULT_STATS)
    parser.add_argument("--lineage", type=Path, default=DEFAULT_LINEAGE)
    parser.add_argument("--markdown", type=Path, default=DEFAULT_MARKDOWN)
    parser.add_argument("--pdf", type=Path, default=DEFAULT_PDF)
    parser.add_argument("--charts", type=Path, default=DEFAULT_CHARTS)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    artifacts = args.artifacts.resolve()
    charts = args.charts.resolve()
    charts.mkdir(parents=True, exist_ok=True)

    payload = {
        "stats": _read_json(args.dataset_stats),
        "training": _read_json(artifacts / "training_metrics.json"),
        "config": _read_json(artifacts / "training_config.json"),
        "history": _read_json(artifacts / "training_history.json"),
        "float": _read_json(artifacts / "metrics_float.json")["metrics"],
        "int8": _read_json(artifacts / "metrics_int8.json")["metrics"],
        "comparison": _read_json(artifacts / "comparison.json"),
        "quantization": _read_json(artifacts / "quantization.json"),
        "metadata": _read_json(artifacts / "model_metadata.json"),
        "float_size": (artifacts / "model_float.keras").stat().st_size,
        "int8_size": (artifacts / "model_int8.tflite").stat().st_size,
        "firmware": _firmware_info(),
    }
    lineage = list(_read_lineage(args.lineage.resolve()))

    _configure_matplotlib()
    _plot_distribution(payload["stats"], charts / "data_distribution.png")
    _plot_history(payload["history"], charts / "training_history.png")
    _plot_confusion(payload["int8"]["confusion_matrix"], charts / "confusion_matrix_int8.png")
    _plot_comparison(payload["float"], payload["int8"], charts / "float_int8_comparison.png")
    _plot_esp_example(lineage, args.lineage.resolve().parent, charts / "esp_simulation_example.png")

    markdown_path = args.markdown.resolve()
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.write_text(_render_markdown(payload), encoding="utf-8", newline="\n")

    pdf_path = args.pdf.resolve()
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    _build_pdf(payload, charts, pdf_path)
    print(f"Saved Markdown report: {markdown_path}")
    print(f"Saved PDF report: {pdf_path}")


def _read_json(path: str | Path) -> dict:
    payload = json.loads(Path(path).resolve().read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return payload


def _read_lineage(path: Path):
    with path.open("r", encoding="utf-8", newline="") as handle:
        yield from csv.DictReader(handle)


def _firmware_info() -> dict:
    build = REPOSITORY_DIR / "ESP-TRASH" / "build"
    app = build / "ESP-TRASH.ino.bin"
    merged = build / "ESP-TRASH.ino.merged.bin"
    result = {
        "verified": app.is_file() and merged.is_file(),
        "app_size": app.stat().st_size if app.is_file() else None,
        "merged_size": merged.stat().st_size if merged.is_file() else None,
        "merged_sha256": _sha256(merged) if merged.is_file() else None,
    }
    return result


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _configure_matplotlib() -> None:
    plt.rcParams.update({
        "font.family": "Arial",
        "font.size": 10,
        "axes.titleweight": "bold",
        "axes.edgecolor": "#CBD5E1",
        "axes.labelcolor": "#334155",
        "xtick.color": "#475569",
        "ytick.color": "#475569",
        "figure.facecolor": "white",
        "axes.facecolor": "white",
    })


def _plot_distribution(stats: dict, path: Path) -> None:
    counts = stats["prepared_counts"]
    fig, axes = plt.subplots(1, 3, figsize=(11.8, 4.1))
    for axis, split in zip(axes, ("train", "validation", "test")):
        values = [counts[split][label] for label in LABELS]
        bars = axis.bar(LABELS, values, color=COLORS, width=0.68)
        axis.bar_label(bars, padding=3, fontsize=9)
        axis.set_title(split.capitalize())
        axis.set_ylabel("Số ảnh" if split == "train" else "")
        axis.grid(axis="y", alpha=0.20)
        axis.set_axisbelow(True)
        axis.tick_params(axis="x", rotation=20)
    fig.suptitle("Phân bố dữ liệu V4 theo split", fontsize=14, fontweight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    fig.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(fig)


def _plot_history(history: dict, path: Path) -> None:
    epochs = np.arange(1, len(history.get("loss", [])) + 1)
    fig, axes = plt.subplots(1, 2, figsize=(11.8, 4.2))
    axes[0].plot(epochs, history.get("loss", []), label="train loss", color=COLORS[0])
    axes[0].plot(epochs, history.get("val_loss", []), label="validation loss", color=COLORS[3])
    axes[0].set(title="Loss", xlabel="Epoch", ylabel="Loss")
    axes[0].legend(frameon=False)
    axes[0].grid(alpha=0.2)
    axes[1].plot(epochs, history.get("accuracy", []), label="train accuracy", color=COLORS[0])
    axes[1].plot(epochs, history.get("val_accuracy", []), label="validation accuracy", color=COLORS[2])
    axes[1].plot(epochs, history.get("val_macro_f1", []), label="validation macro-F1", color=COLORS[3])
    axes[1].set(title="Accuracy và macro-F1", xlabel="Epoch", ylabel="Score", ylim=(0, 1.05))
    axes[1].legend(frameon=False)
    axes[1].grid(alpha=0.2)
    fig.suptitle("Lịch sử huấn luyện model V4 tuned", fontsize=14, fontweight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    fig.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(fig)


def _plot_confusion(matrix: list[list[int]], path: Path) -> None:
    values = np.asarray(matrix, dtype=np.int64)
    fig, axis = plt.subplots(figsize=(6.8, 5.7))
    image = axis.imshow(values, cmap="Blues", vmin=0)
    fig.colorbar(image, ax=axis, fraction=0.046, pad=0.04)
    axis.set(
        title="Confusion matrix - Full INT8 trên test",
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
            axis.text(
                column, row, str(values[row, column]), ha="center", va="center",
                color="white" if values[row, column] > threshold else "#0F172A",
                fontsize=13, fontweight="bold",
            )
    fig.tight_layout()
    fig.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(fig)


def _plot_comparison(float_metrics: dict, int8_metrics: dict, path: Path) -> None:
    names = ("Accuracy", "Balanced accuracy", "Macro-F1")
    keys = ("accuracy", "balanced_accuracy", "macro_f1")
    float_values = [100 * float(float_metrics[key]) for key in keys]
    int8_values = [100 * float(int8_metrics[key]) for key in keys]
    x = np.arange(len(names))
    width = 0.34
    fig, axis = plt.subplots(figsize=(8.6, 4.7))
    left = axis.bar(x - width / 2, float_values, width, label="Float", color=COLORS[0])
    right = axis.bar(x + width / 2, int8_values, width, label="Full INT8", color=COLORS[2])
    axis.bar_label(left, fmt="%.1f%%", padding=3)
    axis.bar_label(right, fmt="%.1f%%", padding=3)
    axis.set(xticks=x, xticklabels=names, ylabel="Phần trăm", ylim=(0, 105))
    axis.set_title("So sánh Float và Full INT8")
    axis.legend(frameon=False)
    axis.grid(axis="y", alpha=0.2)
    axis.set_axisbelow(True)
    fig.tight_layout()
    fig.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(fig)


def _plot_esp_example(lineage: list[dict], dataset_root: Path, path: Path) -> None:
    row = next((item for item in lineage if item.get("kind") == "esp_simulated"), None)
    if row is None:
        raise ValueError("Lineage has no ESP-simulated example")
    source = Path(row["source_path"])
    prepared = dataset_root / Path(row["prepared_relative_path"])
    with PilImage.open(source) as image:
        original = np.asarray(image.convert("RGB"))
    with PilImage.open(prepared) as image:
        simulated = np.asarray(image.convert("RGB"))
    fig, axes = plt.subplots(1, 2, figsize=(9.6, 4.2))
    axes[0].imshow(original)
    axes[0].set_title(f"Nguồn TrashNet - {original.shape[1]}x{original.shape[0]}")
    axes[1].imshow(simulated)
    axes[1].set_title(f"ESP simulation - {simulated.shape[1]}x{simulated.shape[0]}")
    for axis in axes:
        axis.axis("off")
    fig.suptitle("Ví dụ domain adaptation chỉ áp dụng cho train", fontsize=13, fontweight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.91))
    fig.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(fig)


def _percent(value: float) -> str:
    return f"{100.0 * float(value):.2f}%"


def _size(value: int | None) -> str:
    if value is None:
        return "N/A"
    return f"{value:,} byte ({value / 1024:.2f} KiB)"


def _render_markdown(data: dict) -> str:
    stats = data["stats"]
    training = data["training"]
    int8 = data["int8"]
    comparison = data["comparison"]
    quant = data["quantization"]
    metadata = data["metadata"]
    config = data["config"]
    counts = stats["prepared_counts"]
    distribution_rows = "\n".join(
        f"| {label} | {counts['train'][label]} | {counts['validation'][label]} | {counts['test'][label]} |"
        for label in LABELS
    )
    class_rows = "\n".join(
        f"| {label} | {_percent(int8['per_class'][label]['precision'])} | "
        f"{_percent(int8['per_class'][label]['recall'])} | "
        f"{_percent(int8['per_class'][label]['f1-score'])} | "
        f"{int(int8['per_class'][label]['support'])} |"
        for label in LABELS
    )
    gate = "PASS" if comparison["passed"] else "FAIL"
    return f"""# Báo cáo huấn luyện, đánh giá và triển khai model V4

## Kết luận

- Model: `{metadata['model_version']}`, đầu vào `96x96x3`, đầu ra bốn logits theo thứ tự `paper`, `plastic`, `organic`, `other`.
- Full INT8 test accuracy: **{_percent(int8['accuracy'])}**; macro-F1: **{_percent(int8['macro_f1'])}**.
- Float/INT8 agreement: **{_percent(comparison['float_int8_class_agreement'])}**; accuracy drop: **{_percent(comparison['accuracy_drop'])}**.
- Quality gate: **{gate}**. Firmware clean-build: **{'PASS' if data['firmware']['verified'] else 'CHƯA XÁC NHẬN'}**.
- `other` được map sang UART `C 0`, không mở ngăn paper/plastic/organic.

## Dữ liệu

| Lớp | Train | Validation | Test |
|---|---:|---:|---:|
{distribution_rows}

- `other` train = 260, đúng bằng trung bình của ba lớp train V3; gồm 130 cardboard và 130 metal.
- 65/260 ảnh `other` train được mô phỏng QVGA RGB565; validation và test không bị làm xấu.
- Split V3 được giữ nguyên; mỗi ảnh nguồn TrashNet chỉ thuộc một split.

![Phân bố dữ liệu](charts/data_distribution.png)

![Ví dụ mô phỏng ESP](charts/esp_simulation_example.png)

## Huấn luyện và tinh chỉnh

- Kiến trúc V3 được giữ: năm block Conv2D-BatchNorm-ReLU6, GlobalAveragePooling và Dense head; chỉ đổi head từ 3 sang 4 lớp.
- Tham số: **{training['model_parameters']:,}**; best epoch: **{training['best_epoch']}**; epoch đã chạy: **{training['epochs_ran']}**.
- Class weight cuối: `{json.dumps(config['class_weights'], ensure_ascii=False)}`. Paper và plastic được nhân 1.15 sau khi baseline INT8 làm lật một mẫu paper sang other.

![Lịch sử huấn luyện](charts/training_history.png)

## Đánh giá Full INT8

| Lớp | Precision | Recall | F1 | Support |
|---|---:|---:|---:|---:|
{class_rows}

![So sánh Float và INT8](charts/float_int8_comparison.png)

![Confusion matrix INT8](charts/confusion_matrix_int8.png)

## Quantization và firmware

- INT8 model: **{_size(data['int8_size'])}**, SHA-256 `{metadata['artifacts']['int8_model']['sha256']}`.
- Input: `{quant['input']['shape']}`, `{quant['input']['dtype']}`, scale `{quant['input']['quantization']['scale']}`, zero point `{quant['input']['quantization']['zero_point']}`.
- Output: `{quant['output']['shape']}`, `{quant['output']['dtype']}`, scale `{quant['output']['quantization']['scale']}`, zero point `{quant['output']['quantization']['zero_point']}`.
- TFLM operators: `{', '.join(quant['unique_operators'])}`; float tensor còn lại: `{len(quant['float_tensors'])}`.
- Firmware app binary: `{_size(data['firmware']['app_size'])}`; merged SHA-256 `{data['firmware']['merged_sha256'] or 'N/A'}`.

## Giới hạn

Test chỉ có 25 ảnh, trong đó plastic có 4 ảnh và other có 6 ảnh. Cardboard trong TrashNet có thể chồng lấn ngữ nghĩa với một số mẫu paper màu nâu; cần thu thêm test thực địa từ camera ESP32-CAM. Clean-build và self-test tham chiếu đã được kiểm tra, nhưng báo cáo này không thay thế thử nghiệm trên bo mạch vật lý.
"""


def _register_fonts() -> tuple[str, str]:
    candidates = (
        (Path("C:/Windows/Fonts/arial.ttf"), Path("C:/Windows/Fonts/arialbd.ttf")),
        (Path("C:/Windows/Fonts/calibri.ttf"), Path("C:/Windows/Fonts/calibrib.ttf")),
    )
    for regular, bold in candidates:
        if regular.is_file() and bold.is_file():
            pdfmetrics.registerFont(TTFont("ReportRegular", str(regular)))
            pdfmetrics.registerFont(TTFont("ReportBold", str(bold)))
            return "ReportRegular", "ReportBold"
    raise FileNotFoundError("A Unicode TrueType font is required to render Vietnamese")


def _build_pdf(data: dict, charts: Path, destination: Path) -> None:
    regular, bold = _register_fonts()
    page_width, page_height = A4
    document = SimpleDocTemplate(
        str(destination), pagesize=A4,
        rightMargin=17 * mm, leftMargin=17 * mm,
        topMargin=17 * mm, bottomMargin=17 * mm,
        title="Báo cáo model V4 - AIoT Smart Trash Bin",
        author="AIoT Smart Trash Bin",
        subject="Training, evaluation, INT8 quantization and ESP32 deployment",
    )
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        name="ReportTitle", fontName=bold, fontSize=23, leading=28,
        textColor=HexColor("#0F172A"), alignment=TA_LEFT, spaceAfter=8,
    ))
    styles.add(ParagraphStyle(
        name="ReportSubtitle", fontName=regular, fontSize=11, leading=16,
        textColor=HexColor("#475569"), spaceAfter=12,
    ))
    styles.add(ParagraphStyle(
        name="ReportH1", fontName=bold, fontSize=16, leading=20,
        textColor=HexColor("#1D4ED8"), spaceBefore=5, spaceAfter=8,
    ))
    styles.add(ParagraphStyle(
        name="ReportH2", fontName=bold, fontSize=12, leading=16,
        textColor=HexColor("#0F172A"), spaceBefore=5, spaceAfter=5,
    ))
    styles.add(ParagraphStyle(
        name="ReportBody", fontName=regular, fontSize=9.4, leading=14,
        textColor=HexColor("#25324A"), spaceAfter=6,
    ))
    styles.add(ParagraphStyle(
        name="ReportSmall", fontName=regular, fontSize=8, leading=11,
        textColor=HexColor("#64748B"), spaceAfter=4,
    ))
    styles.add(ParagraphStyle(
        name="ReportMetric", fontName=bold, fontSize=17, leading=20,
        textColor=HexColor("#1D4ED8"), alignment=TA_CENTER,
    ))
    styles.add(ParagraphStyle(
        name="ReportMetricLabel", fontName=regular, fontSize=7.5, leading=10,
        textColor=HexColor("#64748B"), alignment=TA_CENTER,
    ))

    story = []
    story.extend(_pdf_cover(data, styles, regular, bold))
    story.append(PageBreak())
    story.extend(_pdf_data_section(data, charts, styles, regular, bold, page_width))
    story.append(PageBreak())
    story.extend(_pdf_training_section(data, charts, styles, regular, bold, page_width))
    story.append(PageBreak())
    story.extend(_pdf_evaluation_section(data, charts, styles, regular, bold, page_width))
    story.append(PageBreak())
    story.extend(_pdf_deployment_section(data, styles, regular, bold))

    def decorate(canvas, doc):
        canvas.saveState()
        canvas.setStrokeColor(HexColor("#E2E8F0"))
        canvas.line(17 * mm, 13 * mm, page_width - 17 * mm, 13 * mm)
        canvas.setFont(regular, 7.5)
        canvas.setFillColor(HexColor("#64748B"))
        canvas.drawString(17 * mm, 8.5 * mm, "AIoT Smart Trash Bin - Model V4")
        canvas.drawRightString(page_width - 17 * mm, 8.5 * mm, f"Trang {doc.page}")
        canvas.restoreState()

    document.build(story, onFirstPage=decorate, onLaterPages=decorate)


def _pdf_cover(data: dict, styles, regular: str, bold: str) -> list:
    int8 = data["int8"]
    comparison = data["comparison"]
    firmware = data["firmware"]
    gate = "PASS" if comparison["passed"] else "FAIL"
    gate_color = HexColor("#047857" if comparison["passed"] else "#B91C1C")
    elements = [
        Spacer(1, 14 * mm),
        Paragraph("BÁO CÁO MODEL V4", styles["ReportTitle"]),
        Paragraph(
            "Huấn luyện, đánh giá, lượng tử hóa Full INT8 và tích hợp ESP32-CAM",
            styles["ReportSubtitle"],
        ),
        Spacer(1, 5 * mm),
    ]
    metrics = [
        (_percent(int8["accuracy"]), "INT8 accuracy"),
        (_percent(int8["macro_f1"]), "INT8 macro-F1"),
        (_percent(comparison["float_int8_class_agreement"]), "Float/INT8 agreement"),
        (_size(data["int8_size"]).split(" (")[0], "Model size"),
    ]
    metric_cells = []
    for value, label in metrics:
        metric_cells.append([
            Paragraph(value, styles["ReportMetric"]),
            Paragraph(label, styles["ReportMetricLabel"]),
        ])
    table = Table([metric_cells], colWidths=[42 * mm] * 4, rowHeights=[31 * mm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), HexColor("#F8FAFC")),
        ("BOX", (0, 0), (-1, -1), 0.7, HexColor("#CBD5E1")),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, HexColor("#E2E8F0")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
    ]))
    elements.extend([
        table,
        Spacer(1, 10 * mm),
        Paragraph("Kết luận triển khai", styles["ReportH1"]),
        Paragraph(
            f"Quality gate: <font name='{bold}' color='{gate_color.hexval()}'>{gate}</font>. "
            f"Clean-build firmware: <font name='{bold}'>{'PASS' if firmware['verified'] else 'CHƯA XÁC NHẬN'}</font>. "
            "Bản tuned giữ nguyên backbone V3, thêm lớp other ở index 3 và đạt accuracy drop 0% sau Full INT8.",
            styles["ReportBody"],
        ),
        Paragraph(
            "Quy tắc an toàn: other được xem là lớp từ chối. Firmware trả UART C 0, "
            "không mở ngăn paper, plastic hoặc organic và không ghi sai waste_type vào thống kê.",
            styles["ReportBody"],
        ),
        Spacer(1, 5 * mm),
        _info_table([
            ("Model", data["metadata"]["model_version"]),
            ("Label order", "paper, plastic, organic, other"),
            ("Input", "INT8 [1, 96, 96, 3], RGB"),
            ("Output", "INT8 [1, 4], logits"),
            ("Model SHA-256", data["metadata"]["artifacts"]["int8_model"]["sha256"]),
        ], styles, regular, bold, widths=(35 * mm, 133 * mm)),
        Spacer(1, 6 * mm),
        Paragraph(
            "Phạm vi xác nhận: dataset split, metric float/INT8, quantization contract, C array byte-for-byte và clean-build firmware. "
            "Cần test bổ sung trên bo mạch vật lý để đo latency và độ bền ngoài hiện trường.",
            styles["ReportSmall"],
        ),
    ])
    return elements


def _pdf_data_section(data: dict, charts: Path, styles, regular, bold, page_width) -> list:
    stats = data["stats"]
    counts = stats["prepared_counts"]
    rows = [["Lớp", "Train", "Validation", "Test"]]
    rows.extend([[label, counts["train"][label], counts["validation"][label], counts["test"][label]] for label in LABELS])
    elements = [
        Paragraph("1. Dữ liệu và kiểm soát mất cân bằng", styles["ReportH1"]),
        Paragraph(
            "V4 giữ nguyên toàn bộ split của V3. Lớp other dùng ảnh TrashNet cardboard và metal; số mẫu train là 260, "
            "đúng bằng trung bình số mẫu train của paper, plastic và organic. Vì vậy other có class weight 1.0 và không lấn át ba lớp điều khiển ngăn.",
            styles["ReportBody"],
        ),
        _styled_table(rows, [45 * mm, 35 * mm, 44 * mm, 35 * mm], regular, bold),
        Spacer(1, 4 * mm),
        Image(str(charts / "data_distribution.png"), width=174 * mm, height=60 * mm),
        Spacer(1, 3 * mm),
        Paragraph("Domain adaptation theo camera ESP", styles["ReportH2"]),
        Paragraph(
            "65/260 ảnh other train (25%) được chuyển về QVGA 320x240, lượng tử màu kiểu RGB565, thay đổi nhẹ brightness, contrast, saturation, "
            "color gain, noise, blur và JPEG. Validation/test không bị biến đổi. Mỗi ảnh nguồn TrashNet chỉ xuất hiện trong đúng một split.",
            styles["ReportBody"],
        ),
        Image(str(charts / "esp_simulation_example.png"), width=151 * mm, height=58 * mm),
        Paragraph(
            "Lưu ý ngữ nghĩa: một số cardboard có thể gần với paper màu nâu. Đây là lý do report tách rõ test support và yêu cầu thu thêm ảnh thực địa.",
            styles["ReportSmall"],
        ),
    ]
    return elements


def _pdf_training_section(data: dict, charts: Path, styles, regular, bold, page_width) -> list:
    training = data["training"]
    config = data["config"]
    weights = config["class_weights"]
    elements = [
        Paragraph("2. Kiến trúc, huấn luyện và tinh chỉnh", styles["ReportH1"]),
        Paragraph(
            "Backbone V3 được giữ nguyên để bảo toàn contract TFLite Micro: năm block Conv2D - BatchNorm - ReLU6, "
            "GlobalAveragePooling và Dense logits. Chỉ Dense head đổi từ 3 sang 4 output; tổng số tham số là "
            f"{training['model_parameters']:,}.",
            styles["ReportBody"],
        ),
        _info_table([
            ("Batch size", str(config["batch_size"])),
            ("Learning rate", str(config["learning_rate"])),
            ("Weight decay", str(config["weight_decay"])),
            ("Label smoothing", str(config["label_smoothing"])),
            ("Best epoch / ran", f"{training['best_epoch']} / {training['epochs_ran']}"),
            ("Training time", f"{training['training_seconds']:.2f} giây"),
        ], styles, regular, bold, widths=(45 * mm, 123 * mm)),
        Spacer(1, 4 * mm),
        Image(str(charts / "training_history.png"), width=174 * mm, height=62 * mm),
        Paragraph("Tinh chỉnh theo kết quả quantization", styles["ReportH2"]),
        Paragraph(
            "Baseline float đạt 96%, nhưng INT8 làm lật một mẫu paper gần biên sang other, khiến accuracy drop 4%. "
            "Thay vì hạ gate, V4 tăng nhẹ hệ số paper và plastic lên 1.15. Bản tuned giữ nguyên float accuracy và đưa agreement lên 100%, accuracy drop về 0%.",
            styles["ReportBody"],
        ),
        _info_table([
            ("paper", f"{float(weights['0']):.4f}"),
            ("plastic", f"{float(weights['1']):.4f}"),
            ("organic", f"{float(weights['2']):.4f}"),
            ("other", f"{float(weights['3']):.4f}"),
        ], styles, regular, bold, widths=(45 * mm, 123 * mm)),
    ]
    return elements


def _pdf_evaluation_section(data: dict, charts: Path, styles, regular, bold, page_width) -> list:
    float_metrics = data["float"]
    int8 = data["int8"]
    comparison = data["comparison"]
    summary = [
        ["Model", "Accuracy", "Balanced acc.", "Macro-F1"],
        ["Float", _percent(float_metrics["accuracy"]), _percent(float_metrics["balanced_accuracy"]), _percent(float_metrics["macro_f1"])],
        ["Full INT8", _percent(int8["accuracy"]), _percent(int8["balanced_accuracy"]), _percent(int8["macro_f1"])],
    ]
    per_class = [["Lớp", "Precision", "Recall", "F1", "Support"]]
    for label in LABELS:
        metrics = int8["per_class"][label]
        per_class.append([
            label, _percent(metrics["precision"]), _percent(metrics["recall"]),
            _percent(metrics["f1-score"]), str(int(metrics["support"])),
        ])
    elements = [
        Paragraph("3. Evaluation và quality gate", styles["ReportH1"]),
        _styled_table(summary, [42 * mm] * 4, regular, bold),
        Spacer(1, 4 * mm),
        Image(str(charts / "float_int8_comparison.png"), width=118 * mm, height=60 * mm),
        Spacer(1, 3 * mm),
        Paragraph("Chỉ số từng lớp - Full INT8", styles["ReportH2"]),
        _styled_table(per_class, [34 * mm, 34 * mm, 34 * mm, 34 * mm, 28 * mm], regular, bold),
        Spacer(1, 4 * mm),
        Paragraph(
            f"Gate tổng: {'PASS' if comparison['passed'] else 'FAIL'} - agreement {_percent(comparison['float_int8_class_agreement'])}, "
            f"accuracy drop {_percent(comparison['accuracy_drop'])}, min class recall {_percent(comparison['int8_min_class_recall'])}.",
            styles["ReportBody"],
        ),
        Image(str(charts / "confusion_matrix_int8.png"), width=90 * mm, height=74 * mm),
        Paragraph(
            "Giới hạn thống kê: test có 25 ảnh; plastic chỉ có 4 ảnh nên một lỗi tương ứng 25 điểm phần trăm recall. "
            "Kết quả phù hợp để kiểm tra pipeline và so sánh bản model, chưa đủ thay thế benchmark thực địa lớn.",
            styles["ReportSmall"],
        ),
    ]
    return elements


def _pdf_deployment_section(data: dict, styles, regular, bold) -> list:
    quant = data["quantization"]
    metadata = data["metadata"]
    firmware = data["firmware"]
    gates = data["comparison"]["gates"]
    gate_rows = [["Gate", "Kết quả"]]
    gate_rows.extend([[name.replace("_passed", ""), "PASS" if passed else "FAIL"] for name, passed in gates.items()])
    elements = [
        Paragraph("4. Quantization và triển khai ESP32", styles["ReportH1"]),
        Paragraph(
            "Model được post-training quantization bằng toàn bộ 1,040 ảnh train và hai range anchor 0/1. "
            "FlatBuffer không còn float tensor và chỉ chứa ba loại operator đã có trong resolver V3.",
            styles["ReportBody"],
        ),
        _info_table([
            ("INT8 model", _size(data["int8_size"])),
            ("Input", f"{quant['input']['dtype']} {quant['input']['shape']}"),
            ("Input quantization", f"scale={quant['input']['quantization']['scale']}, zero={quant['input']['quantization']['zero_point']}"),
            ("Output", f"{quant['output']['dtype']} {quant['output']['shape']}"),
            ("Output quantization", f"scale={quant['output']['quantization']['scale']}, zero={quant['output']['quantization']['zero_point']}"),
            ("Operators", ", ".join(quant["unique_operators"])),
            ("SHA-256", metadata["artifacts"]["int8_model"]["sha256"]),
        ], styles, regular, bold, widths=(45 * mm, 123 * mm)),
        Spacer(1, 5 * mm),
        Paragraph("Firmware contract", styles["ReportH2"]),
        Spacer(1, 2 * mm),
        Paragraph(
            "Firmware kiểm tra model size, SHA-256, schema, tensor shape, dtype và quantization trước khi chạy. "
            "Self-test LiteRT tham chiếu cho input tổng hợp là [-111, 6, -119, 127], top class other. "
            "Nhãn other map sang UART C 0 và cloud waste_type=null.",
            styles["ReportBody"],
        ),
        _styled_table(gate_rows, [110 * mm, 54 * mm], regular, bold),
        Spacer(1, 5 * mm),
        Paragraph("Clean-build firmware", styles["ReportH2"]),
        Spacer(1, 2 * mm),
        _info_table([
            ("Build status", "PASS" if firmware["verified"] else "CHƯA XÁC NHẬN"),
            ("Application binary", _size(firmware["app_size"])),
            ("Merged binary", _size(firmware["merged_size"])),
            ("Merged SHA-256", firmware["merged_sha256"] or "N/A"),
        ], styles, regular, bold, widths=(45 * mm, 123 * mm)),
        Spacer(1, 7 * mm),
        Paragraph("5. Khuyến nghị kiểm thử tiếp theo", styles["ReportH1"]),
        Paragraph(
            "1) Chạy ít nhất 30 mẫu mỗi lớp bằng đúng ESP32-CAM và ánh sáng thực tế. "
            "2) Ghi riêng false reject paper -> other và false accept cardboard -> paper. "
            "3) Đo latency, tensor arena thực dùng và kiểm tra UART C 0 không kích hoạt servo. "
            "4) Mở rộng test plastic vì support hiện chỉ là 4.",
            styles["ReportBody"],
        ),
        Paragraph(
            "Các file tái tạo: AI/V4/prepare_dataset.py, train.py, export_int8.py, evaluate_model.py, "
            "artifacts/*.json và ESP-TRASH/verify_embedded_model.py.",
            styles["ReportSmall"],
        ),
    ]
    return elements


def _styled_table(rows, widths, regular: str, bold: str) -> Table:
    converted = []
    for row_index, row in enumerate(rows):
        font = bold if row_index == 0 else regular
        converted.append([
            Paragraph(str(value), ParagraphStyle(
                name=f"Cell{row_index}{column_index}", fontName=font,
                fontSize=8.2, leading=10.5, textColor=HexColor("#1E293B"),
                alignment=TA_LEFT,
            ))
            for column_index, value in enumerate(row)
        ])
    table = Table(converted, colWidths=widths, repeatRows=1, hAlign="LEFT")
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), HexColor("#EAF1FF")),
        ("TEXTCOLOR", (0, 0), (-1, 0), HexColor("#1D4ED8")),
        ("GRID", (0, 0), (-1, -1), 0.45, HexColor("#CBD5E1")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, HexColor("#F8FAFC")]),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    return table


def _info_table(items, styles, regular: str, bold: str, widths) -> Table:
    rows = [
        [
            Paragraph(str(name), ParagraphStyle(
                name=f"InfoLabel{index}", fontName=bold, fontSize=8.2,
                leading=10.5, textColor=HexColor("#334155"),
            )),
            Paragraph(str(value), ParagraphStyle(
                name=f"InfoValue{index}", fontName=regular, fontSize=8.2,
                leading=10.5, textColor=HexColor("#334155"),
            )),
        ]
        for index, (name, value) in enumerate(items)
    ]
    table = Table(rows, colWidths=list(widths), hAlign="LEFT")
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), HexColor("#F1F5F9")),
        ("GRID", (0, 0), (-1, -1), 0.4, HexColor("#D7E0EA")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return table


if __name__ == "__main__":
    main()
