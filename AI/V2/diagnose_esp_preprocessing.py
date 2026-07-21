"""Compare Python preprocessing with ESP RGB565 variants on camera originals."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import numpy as np
from PIL import Image

from src.config import CLASS_TO_INDEX, IMAGE_SIZE, LABELS
from src.dataset import preprocess_file
from src.evaluate_model import TFLitePredictor
from src.metadata import write_json_atomic, write_text_atomic
from src.metrics import classification_metrics


V2_DIR = Path(__file__).resolve().parent
AI_DIR = V2_DIR.parent
DEFAULT_DATASET = AI_DIR / "DATASET"
DEFAULT_PREPARED = V2_DIR / "dataset_augmented"
DEFAULT_MODEL = V2_DIR / "artifacts" / "model_int8.tflite"
DEFAULT_OUT = V2_DIR / "artifacts" / "esp_preprocessing_diagnosis"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--prepared", type=Path, default=DEFAULT_PREPARED)
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    dataset = args.dataset.resolve()
    out_dir = args.out.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    originals = _original_rows(args.prepared.resolve() / "lineage.csv")
    predictor = TFLitePredictor(args.model.resolve())
    variant_names = (
        "python_rgb",
        "old_firmware_rgb565_bit_replication",
        "current_firmware_rgb565_shift_levels",
        "wrong_rgb565_byte_order",
        "wrong_red_blue_order",
    )
    logits = {name: [] for name in variant_names}
    truth: list[int] = []
    prediction_rows: list[dict[str, object]] = []

    for item in originals:
        relative_path = item["source_relative_path"]
        path = dataset.joinpath(*relative_path.split("/"))
        with Image.open(path) as image:
            rgb = np.asarray(image.convert("RGB"), dtype=np.uint8)
        inputs = {
            "python_rgb": preprocess_file(path),
            **_rgb565_variants(rgb),
        }
        truth_id = CLASS_TO_INDEX[item["label"]]
        truth.append(truth_id)
        row: dict[str, object] = {
            "source_relative_path": relative_path,
            "prepared_split": item["prepared_split"],
            "label": item["label"],
        }
        for name in variant_names:
            scores = predictor.predict_one(inputs[name])
            logits[name].append(scores)
            row[name] = LABELS[int(np.argmax(scores))]
        prediction_rows.append(row)

    truth_array = np.asarray(truth, dtype=np.int64)
    stacked = {name: np.vstack(values) for name, values in logits.items()}
    reference = np.argmax(stacked["python_rgb"], axis=1)
    summary = {
        "dataset": str(dataset),
        "model": str(args.model.resolve()),
        "samples": len(originals),
        "variants": {
            name: {
                "metrics": classification_metrics(truth_array, scores),
                "prediction_counts": {
                    label: int(np.sum(np.argmax(scores, axis=1) == index))
                    for index, label in enumerate(LABELS)
                },
                "agreement_with_python_rgb": float(
                    np.mean(np.argmax(scores, axis=1) == reference)
                ),
            }
            for name, scores in stacked.items()
        },
    }
    write_json_atomic(out_dir / "summary.json", summary)
    write_text_atomic(out_dir / "predictions.csv", _to_csv(prediction_rows))
    print(json.dumps(summary, indent=2, ensure_ascii=False))


def _original_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = [
            dict(row)
            for row in csv.DictReader(handle)
            if row.get("kind") == "original"
        ]
    if not rows:
        raise ValueError(f"No original images in {path}")
    return sorted(rows, key=lambda row: row["source_relative_path"])


def _rgb565_variants(rgb: np.ndarray) -> dict[str, np.ndarray]:
    red5 = np.right_shift(rgb[..., 0], 3).astype(np.uint16)
    green6 = np.right_shift(rgb[..., 1], 2).astype(np.uint16)
    blue5 = np.right_shift(rgb[..., 2], 3).astype(np.uint16)
    packed = (red5 << 11) | (green6 << 5) | blue5
    high = np.right_shift(packed, 8).astype(np.uint16)
    low = np.bitwise_and(packed, 0xFF)
    byte_swapped = (low << 8) | high

    full_range = _unpack_rgb565(packed, replicate_low_bits=True)
    shifted_levels = _unpack_rgb565(packed, replicate_low_bits=False)
    wrong_byte_order = _unpack_rgb565(byte_swapped, replicate_low_bits=True)
    wrong_red_blue = full_range[..., ::-1]
    return {
        "old_firmware_rgb565_bit_replication": _center_floor_resize(full_range),
        "current_firmware_rgb565_shift_levels": _center_floor_resize(
            shifted_levels
        ),
        "wrong_rgb565_byte_order": _center_floor_resize(wrong_byte_order),
        "wrong_red_blue_order": _center_floor_resize(wrong_red_blue),
    }


def _unpack_rgb565(packed: np.ndarray, *, replicate_low_bits: bool) -> np.ndarray:
    red = np.bitwise_and(np.right_shift(packed, 11), 0x1F)
    green = np.bitwise_and(np.right_shift(packed, 5), 0x3F)
    blue = np.bitwise_and(packed, 0x1F)
    if replicate_low_bits:
        red = (red << 3) | (red >> 2)
        green = (green << 2) | (green >> 4)
        blue = (blue << 3) | (blue >> 2)
    else:
        red <<= 3
        green <<= 2
        blue <<= 3
    return np.stack((red, green, blue), axis=-1).astype(np.uint8)


def _center_floor_resize(rgb: np.ndarray) -> np.ndarray:
    height, width, channels = rgb.shape
    if channels != 3:
        raise ValueError(f"Expected RGB input, got {rgb.shape}")
    square_size = min(height, width)
    offset_y = (height - square_size) // 2
    offset_x = (width - square_size) // 2
    indices = np.arange(IMAGE_SIZE, dtype=np.int64) * square_size // IMAGE_SIZE
    resized = rgb[
        offset_y + indices[:, np.newaxis],
        offset_x + indices[np.newaxis, :],
    ]
    return resized.astype(np.float32) / 255.0


def _to_csv(rows: list[dict[str, object]]) -> str:
    from io import StringIO

    output = StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()


if __name__ == "__main__":
    main()
