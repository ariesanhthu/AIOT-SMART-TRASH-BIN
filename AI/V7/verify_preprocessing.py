"""Prove TensorFlow preprocessing matches an independent firmware-style reference."""

from __future__ import annotations

import argparse
import json

import numpy as np
import tensorflow as tf

from V7.config import IMAGE_SIZE, PREPARED_DATA_DIR
from V7.data_pipeline import load_samples, preprocess_file


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", default=str(PREPARED_DATA_DIR))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    samples = load_samples(args.data)
    maximum_delta = 0
    for sample in samples:
        decoded = tf.io.decode_jpeg(
            tf.io.read_file(str(sample.path)), channels=3
        ).numpy()
        reference = firmware_reference(decoded)
        actual = np.rint(preprocess_file(sample.path) * 255.0).astype(np.uint8)
        delta = int(
            np.max(np.abs(reference.astype(np.int16) - actual.astype(np.int16)))
        )
        maximum_delta = max(maximum_delta, delta)
        if delta != 0:
            raise RuntimeError(f"V7 preprocessing mismatch ({delta}) for {sample.path}")
    print(
        json.dumps(
            {
                "samples": len(samples),
                "maximum_u8_delta": maximum_delta,
                "status": "exact",
            },
            indent=2,
        )
    )


def firmware_reference(decoded: np.ndarray) -> np.ndarray:
    height, width, channels = decoded.shape
    if channels != 3:
        raise ValueError("Reference expects RGB")
    crop_size = min(height, width)
    crop_x = (width - crop_size) // 2
    crop_y = (height - crop_size) // 2
    square = decoded[crop_y : crop_y + crop_size, crop_x : crop_x + crop_size]
    indices = np.arange(IMAGE_SIZE, dtype=np.int64) * crop_size // IMAGE_SIZE
    resized = square[indices[:, None], indices[None, :]].astype(np.int32)
    resized = (
        resized
        // np.asarray([8, 4, 8], dtype=np.int32)
        * np.asarray([8, 4, 8], dtype=np.int32)
    )
    luma = (
        77 * resized[..., 0] + 150 * resized[..., 1] + 29 * resized[..., 2] + 128
    ) // 256
    mean = int(
        (int(luma.sum()) + IMAGE_SIZE * IMAGE_SIZE // 2) // (IMAGE_SIZE * IMAGE_SIZE)
    )
    if mean < 96:
        gain = min(341, (96 * 256 + max(mean, 1) // 2) // max(mean, 1))
    elif mean > 160:
        gain = max(192, (160 * 256 + mean // 2) // mean)
    else:
        gain = 256
    return np.clip((resized * gain + 128) // 256, 0, 255).astype(np.uint8)


if __name__ == "__main__":
    main()
