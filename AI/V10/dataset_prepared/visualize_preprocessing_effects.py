"""Visual and quantitative audit of V9 center-crop and 96x96 resizing."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sys
from typing import Any

import cv2
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, balanced_accuracy_score, confusion_matrix
from skimage.metrics import structural_similarity


V9_DIR = Path(__file__).resolve().parent
REPO_DIR = V9_DIR.parents[1]
if str(V9_DIR.parent) not in sys.path:
    sys.path.insert(0, str(V9_DIR.parent))

from V9.analyze_server_tmp_int8 import (  # noqa: E402
    CLASS_NAMES,
    collect_server_items,
    infer_int8,
    load_rgb,
    preprocess_esp_v3,
)


SELECTED_FILES = (
    "b22bb84d-1cf7-46ad-b4d0-22cdf10d932d.jpg",
    "7e6a3c04-9698-4b46-9900-ae538812c20f.jpg",
    "plastic_019__aug_v2_04.jpg",
    "029cbe89-92f1-4d66-a857-5dbc8be06200.jpg",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=REPO_DIR / "server-tmp")
    parser.add_argument(
        "--model", type=Path, default=V9_DIR / "artifacts" / "model_int8.tflite"
    )
    parser.add_argument(
        "--out", type=Path,
        default=V9_DIR / "artifacts" / "server_tmp_int8_analysis" / "preprocessing_visualization",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output = args.out.expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    items = collect_server_items(args.input.expanduser().resolve())
    raw_images = [load_rgb(item["path"]) for item in items]
    truth = np.asarray([int(item["true_id"]) for item in items])

    variant_images: dict[str, np.ndarray] = {}
    for name in VARIANTS:
        variant_images[name] = np.stack([
            preprocess_variant(raw, name) for raw in raw_images
        ])

    variants: dict[str, dict[str, Any]] = {}
    current_predictions: np.ndarray | None = None
    for name, images in variant_images.items():
        probabilities, _ = infer_int8(args.model.expanduser().resolve(), images)
        predicted = probabilities.argmax(axis=1)
        if name == "center_crop_nearest_floor":
            current_predictions = predicted
        variants[name] = {
            "accuracy": float(accuracy_score(truth, predicted)),
            "balanced_accuracy": float(balanced_accuracy_score(truth, predicted)),
            "confusion_matrix": confusion_matrix(
                truth, predicted, labels=np.arange(len(CLASS_NAMES))
            ).tolist(),
            "predicted": predicted,
        }
    if current_predictions is None:
        raise RuntimeError("Current pipeline variant is missing")
    for result in variants.values():
        predicted = result.pop("predicted")
        result["top1_changed_vs_current"] = int(np.sum(predicted != current_predictions))

    quality_rows = []
    for item, raw in zip(items, raw_images, strict=True):
        quality_rows.append({
            "filename": item["filename"],
            "true_label": item["true_label"],
            **resize_quality(raw),
        })
    quality = pd.DataFrame(quality_rows)
    quality.to_csv(output / "resize_quality.csv", index=False, encoding="utf-8-sig")
    summary = {
        "geometry": {
            "original": [320, 240],
            "center_crop": [240, 240],
            "model_input": [96, 96],
            "full_frame_area_retained_by_crop": 0.75,
            "crop_pixel_count_retained_at_96": 0.16,
            "full_frame_pixel_count_retained_at_96": 0.12,
            "linear_downscale_per_axis_from_crop": 0.4,
        },
        "resize_quality_median": {
            column: float(quality[column].median())
            for column in (
                "nearest_psnr_db", "nearest_ssim", "nearest_edge_recall",
                "area_psnr_db", "area_ssim", "area_edge_recall",
            )
        },
        "pipeline_variants_diagnostic_only": variants,
        "warning": (
            "Alternative variants were not used during training. Their accuracy is a sensitivity "
            "diagnostic, not a fair architecture comparison. Retraining is required."
        ),
    }
    (output / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    plot_examples(items, raw_images, output / "crop_resize_examples.jpg")
    export_visual_assets(items, raw_images, output / "visual_assets")
    plot_quality(quality, output / "resize_quality.png")
    plot_variants(variants, output / "pipeline_variant_sensitivity.png")
    write_report(output / "CROP_RESIZE_ANALYSIS.md", summary)
    print(json.dumps(summary, indent=2, ensure_ascii=False))


VARIANTS = (
    "center_crop_nearest_floor",
    "left_crop_nearest_floor",
    "right_crop_nearest_floor",
    "center_crop_area",
    "full_frame_stretch",
    "full_frame_letterbox",
)


def preprocess_variant(raw: np.ndarray, variant: str) -> np.ndarray:
    height, width = raw.shape[:2]
    side = min(height, width)
    y0 = (height - side) // 2
    if variant == "left_crop_nearest_floor":
        x0 = 0
    elif variant == "right_crop_nearest_floor":
        x0 = width - side
    else:
        x0 = (width - side) // 2

    if variant == "center_crop_nearest_floor":
        output, _ = preprocess_esp_v3(raw)
        return output
    if variant in {"left_crop_nearest_floor", "right_crop_nearest_floor"}:
        square = raw[y0:y0 + side, x0:x0 + side]
        resized = nearest_floor(square, 96)
    elif variant == "center_crop_area":
        square = raw[y0:y0 + side, x0:x0 + side]
        resized = cv2.resize(square, (96, 96), interpolation=cv2.INTER_AREA)
    elif variant == "full_frame_stretch":
        resized = cv2.resize(raw, (96, 96), interpolation=cv2.INTER_NEAREST)
    elif variant == "full_frame_letterbox":
        scaled = cv2.resize(raw, (96, 72), interpolation=cv2.INTER_AREA)
        fill = np.median(raw.reshape(-1, 3), axis=0).astype(np.uint8)
        resized = np.empty((96, 96, 3), dtype=np.uint8)
        resized[:] = fill
        resized[12:84] = scaled
    else:
        raise ValueError(variant)
    return illumination_contract(resized)


def nearest_floor(image: np.ndarray, size: int) -> np.ndarray:
    side = image.shape[0]
    indices = np.minimum(np.arange(size, dtype=np.int64) * side // size, side - 1)
    return image[indices[:, None], indices[None, :], :]


def illumination_contract(image: np.ndarray) -> np.ndarray:
    pixels = image.astype(np.int64)
    steps = np.asarray([8, 4, 8], dtype=np.int64)
    pixels = (pixels // steps) * steps
    count = pixels.shape[0] * pixels.shape[1]
    means = (pixels.sum(axis=(0, 1)) + count // 2) // count
    target = (int(means.sum()) + 1) // 3
    safe = np.maximum(means, 1)
    gains = np.clip((target * 1024 + safe // 2) // safe, 768, 1365)
    pixels = np.clip((pixels * gains + 512) // 1024, 0, 255)
    luma = (
        77 * pixels[..., 0] + 150 * pixels[..., 1]
        + 29 * pixels[..., 2] + 128
    ) // 256
    mean_luma = int((int(luma.sum()) + count // 2) // count)
    safe_mean = max(mean_luma, 1)
    if mean_luma < 96:
        gain = min(341, (96 * 256 + safe_mean // 2) // safe_mean)
    elif mean_luma > 160:
        gain = max(192, (160 * 256 + safe_mean // 2) // safe_mean)
    else:
        gain = 256
    return np.clip((pixels * gain + 128) // 256, 0, 255).astype(np.uint8)


def resize_quality(raw: np.ndarray) -> dict[str, float]:
    height, width = raw.shape[:2]
    side = min(height, width)
    square = raw[
        (height - side) // 2:(height + side) // 2,
        (width - side) // 2:(width + side) // 2,
    ]
    steps = np.asarray([8, 4, 8], dtype=np.uint8)
    reference = ((square // steps) * steps).astype(np.uint8)
    nearest = nearest_floor(reference, 96)
    area = cv2.resize(reference, (96, 96), interpolation=cv2.INTER_AREA)
    nearest_rebuilt = cv2.resize(nearest, (side, side), interpolation=cv2.INTER_LINEAR)
    area_rebuilt = cv2.resize(area, (side, side), interpolation=cv2.INTER_LINEAR)
    return {
        **quality_metrics(reference, nearest_rebuilt, "nearest"),
        **quality_metrics(reference, area_rebuilt, "area"),
    }


def quality_metrics(reference: np.ndarray, rebuilt: np.ndarray, prefix: str) -> dict[str, float]:
    mse = float(np.mean((reference.astype(np.float32) - rebuilt.astype(np.float32)) ** 2))
    psnr = 99.0 if mse == 0.0 else 10.0 * math.log10(255.0**2 / mse)
    ssim = float(structural_similarity(reference, rebuilt, channel_axis=2, data_range=255))
    reference_edges = cv2.Canny(cv2.cvtColor(reference, cv2.COLOR_RGB2GRAY), 70, 140) > 0
    rebuilt_edges = cv2.Canny(cv2.cvtColor(rebuilt, cv2.COLOR_RGB2GRAY), 70, 140) > 0
    tolerance = cv2.dilate(rebuilt_edges.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0
    edge_recall = float(np.sum(reference_edges & tolerance) / max(np.sum(reference_edges), 1))
    return {
        f"{prefix}_psnr_db": psnr,
        f"{prefix}_ssim": ssim,
        f"{prefix}_edge_recall": edge_recall,
    }


def plot_examples(items: list[dict], raw_images: list[np.ndarray], path: Path) -> None:
    lookup = {item["filename"]: (item, raw) for item, raw in zip(items, raw_images, strict=True)}
    selected = [lookup[name] for name in SELECTED_FILES]
    fig, axes = plt.subplots(len(selected), 5, figsize=(15, 11))
    headings = (
        "Original 320×240 + crop box", "Center crop 240×240",
        "Actual model input 96×96", "96×96 enlarged to 240", "Hypothetical AREA 96×96",
    )
    for column, heading in enumerate(headings):
        axes[0, column].set_title(heading, fontsize=10)
    for row, (item, raw) in enumerate(selected):
        height, width = raw.shape[:2]
        side = min(height, width)
        x0, y0 = (width - side) // 2, (height - side) // 2
        annotated = raw.copy()
        cv2.rectangle(annotated, (x0, y0), (x0 + side - 1, y0 + side - 1), (255, 0, 0), 3)
        crop = raw[y0:y0 + side, x0:x0 + side]
        actual, _ = preprocess_esp_v3(raw)
        enlarged = cv2.resize(actual, (240, 240), interpolation=cv2.INTER_NEAREST)
        area = illumination_contract(cv2.resize(crop, (96, 96), interpolation=cv2.INTER_AREA))
        displays = (annotated, crop, actual, enlarged, area)
        for column, image in enumerate(displays):
            axes[row, column].imshow(image)
            axes[row, column].axis("off")
        axes[row, 0].set_ylabel(
            f"{item['true_label']}\n{item['filename'][:10]}…",
            rotation=0, ha="right", va="center", fontsize=9,
        )
    fig.suptitle("What V9 actually sees: crop and 96×96 detail loss", fontsize=14)
    fig.tight_layout()
    fig.savefig(path, dpi=180, pil_kwargs={"quality": 93})
    plt.close(fig)


def export_visual_assets(
    items: list[dict], raw_images: list[np.ndarray], output: Path
) -> None:
    output.mkdir(parents=True, exist_ok=True)
    lookup = {item["filename"]: raw for item, raw in zip(items, raw_images, strict=True)}
    for index, filename in enumerate(SELECTED_FILES):
        raw = lookup[filename]
        height, width = raw.shape[:2]
        side = min(height, width)
        x0, y0 = (width - side) // 2, (height - side) // 2
        crop = raw[y0:y0 + side, x0:x0 + side]
        nearest, _ = preprocess_esp_v3(raw)
        area = illumination_contract(
            cv2.resize(crop, (96, 96), interpolation=cv2.INTER_AREA)
        )
        for name, image in (
            ("original", raw), ("crop", crop), ("nearest", nearest), ("area", area)
        ):
            target = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)
            if not cv2.imwrite(
                str(output / f"sample-{index}-{name}.jpg"),
                target,
                [cv2.IMWRITE_JPEG_QUALITY, 82],
            ):
                raise RuntimeError(f"Cannot write visual asset: sample-{index}-{name}.jpg")


def plot_quality(frame: pd.DataFrame, path: Path) -> None:
    fig, axes = plt.subplots(1, 3, figsize=(12, 4.2))
    for ax, metric, ylabel in (
        (axes[0], "psnr_db", "PSNR (dB), higher is better"),
        (axes[1], "ssim", "SSIM, higher is better"),
        (axes[2], "edge_recall", "Edge recall, higher is better"),
    ):
        values = [frame[f"nearest_{metric}"], frame[f"area_{metric}"]]
        ax.boxplot(values, tick_labels=["Nearest-floor", "AREA"], showfliers=False)
        ax.set_ylabel(ylabel)
        ax.grid(axis="y", alpha=0.25)
    fig.suptitle("240×240 → 96×96 reconstruction quality across 259 images")
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def plot_variants(variants: dict[str, dict[str, Any]], path: Path) -> None:
    labels = list(variants)
    accuracy = [variants[label]["accuracy"] for label in labels]
    changed = [variants[label]["top1_changed_vs_current"] for label in labels]
    short = [
        "center NN", "left NN", "right NN", "center AREA", "stretch full", "letterbox full"
    ]
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5))
    axes[0].bar(short, accuracy)
    axes[0].axhline(accuracy[0], color="black", linewidth=1)
    axes[0].set_ylim(0, 1)
    axes[0].set_ylabel("Accuracy (diagnostic only)")
    axes[1].bar(short, changed)
    axes[1].set_ylabel("Top-1 changed vs current (images)")
    for ax in axes:
        ax.tick_params(axis="x", rotation=25)
        ax.grid(axis="y", alpha=0.25)
    fig.suptitle("Sensitivity to crop position and resize policy — without retraining")
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def write_report(path: Path, summary: dict[str, Any]) -> None:
    quality = summary["resize_quality_median"]
    variants = summary["pipeline_variants_diagnostic_only"]
    report = f"""# Kiểm tra trực quan crop và resize V9

## Model thực sự nhìn thấy gì

QVGA 320×240 có 76.800 pixel. Center-crop giữ 240×240 = 57.600 pixel và bỏ hai dải
40×240 ở trái/phải. Sau đó resize còn 96×96 = 9.216 pixel: chỉ còn 16% số pixel của crop,
hay 12% số pixel frame ban đầu. Mỗi chiều bị thu 2,5 lần.

![Crop and resize examples](crop_resize_examples.jpg)

Các ví dụ sai confidence cao vẫn giữ vật thể chính khá rõ trong vùng vuông, nên crop không phải
nguyên nhân trực tiếp của đa số lỗi đã quan sát. Tuy nhiên ảnh có vật ở sát mép trái/phải cho thấy
center-crop có thể cắt một phần vật; đây là rủi ro framing, không phải lỗi công thức crop.

## Mất chất lượng do 240 → 96

Trung vị nearest-floor: PSNR **{quality['nearest_psnr_db']:.2f} dB**, SSIM
**{quality['nearest_ssim']:.3f}**, edge recall **{quality['nearest_edge_recall']:.3f}**.
AREA resize giả định: PSNR **{quality['area_psnr_db']:.2f} dB**, SSIM
**{quality['area_ssim']:.3f}**, edge recall **{quality['area_edge_recall']:.3f}**.

![Resize quality](resize_quality.png)

Nearest-floor bỏ mẫu trực tiếp nên aliasing mạnh hơn AREA. Nhưng firmware và train hiện cùng dùng
nearest-floor; chỉ đổi firmware sang AREA mà không retrain sẽ tạo preprocessing mismatch. AREA có
PSNR/SSIM tốt hơn vì trung bình hóa block, nhưng edge recall thấp hơn vì chính phép trung bình này
làm mờ các cạnh mảnh; không có resize nào giữ lại được chi tiết đã mất ở 96×96.

## Crop có đang “sai” không?

Không sai về implementation: mapping Python và firmware giống nhau, giữ đúng tỉ lệ hình và không
kéo méo vật. Đổi vị trí crop làm top-1 thay đổi ở
{variants['left_crop_nearest_floor']['top1_changed_vs_current']} ảnh khi crop trái và
{variants['right_crop_nearest_floor']['top1_changed_vs_current']} ảnh khi crop phải. Điều này cho
thấy model nhạy với framing. Các accuracy dưới đây chỉ là sensitivity test vì model chưa được train
với pipeline thay thế:

- Current center NN: {variants['center_crop_nearest_floor']['accuracy']:.2%}
- Left crop NN: {variants['left_crop_nearest_floor']['accuracy']:.2%}
- Right crop NN: {variants['right_crop_nearest_floor']['accuracy']:.2%}
- Center AREA: {variants['center_crop_area']['accuracy']:.2%}
- Full-frame stretch: {variants['full_frame_stretch']['accuracy']:.2%}
- Full-frame letterbox: {variants['full_frame_letterbox']['accuracy']:.2%}

![Pipeline sensitivity](pipeline_variant_sensitivity.png)

## Có nên train ảnh nguyên 320×240 không?

**Giữ ảnh nguyên làm dữ liệu nguồn: có. Đưa nguyên 320×240 trực tiếp vào train trong khi ESP infer
96×96: không.** Train và deploy phải có cùng input contract. Nếu model ESP vẫn nhận 96×96, mỗi
epoch phải tạo đúng ảnh 96×96 mà thiết bị sẽ nhìn thấy.

Hướng nên thử theo thứ tự:

1. Giữ file gốc 320×240 và nhãn/source-group; train bằng random crop/translation nhưng validation
   và test luôn dùng pipeline firmware cố định.
2. Thu vật thể ở nhiều vị trí, hoặc điều khiển cơ khí để vật luôn nằm giữa khung.
3. Thử full-frame letterbox 96×96 hoặc input 128×96 giữ tỉ lệ; **retrain từ đầu** rồi so trên test
   deployment cố định. Trong hai phương án, **128×96 là A/B ưu tiên**: 320×240 → 128×96 vẫn
   giảm đều 2,5 lần mỗi chiều như crop 240×240 → 96×96, nên giữ nguyên mật độ chi tiết và toàn
   bộ khung hình; đổi lại input/activation tăng khoảng 33% so với 96×96.
4. Thử AREA/bilinear antialias trong cả train lẫn firmware. Nếu ESP không đủ tài nguyên, dùng
   nearest-floor nhưng thêm augmentation dịch chuyển và scale.
5. Chỉ tăng lên 128/160 nếu đo được lợi ích trên hard cases; chi phí activation/compute tăng gần
   theo bình phương kích thước. Vấn đề coverage vật thể hiện lớn hơn vấn đề độ phân giải.
"""
    path.write_text(report, encoding="utf-8")


if __name__ == "__main__":
    main()
