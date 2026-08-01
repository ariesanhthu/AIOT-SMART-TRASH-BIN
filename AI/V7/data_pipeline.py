"""V7 input pipeline matching the ESP32-CAM preprocessing contract."""

from __future__ import annotations

import csv
from dataclasses import dataclass
import hashlib
import math
from pathlib import Path, PurePosixPath
from typing import Sequence

import numpy as np
import tensorflow as tf

from V7.config import (
    CLASS_NAMES,
    CLASS_TO_INDEX,
    IMAGE_CHANNELS,
    IMAGE_SIZE,
    PREPARED_DATA_DIR,
    SPLITS,
)


AUTOTUNE = tf.data.AUTOTUNE


@dataclass(frozen=True)
class Sample:
    path: Path
    relative_path: str
    split: str
    label: str
    label_id: int
    sha256: str
    burst_id: str


def load_samples(root: str | Path = PREPARED_DATA_DIR) -> tuple[Sample, ...]:
    data_root = Path(root).expanduser().resolve()
    manifest_path = data_root / "manifest.csv"
    if not manifest_path.is_file():
        raise FileNotFoundError(
            f"Prepared V7 manifest not found: {manifest_path}. Run V7.prepare_dataset."
        )
    samples: list[Sample] = []
    seen: set[str] = set()
    with manifest_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {
            "relative_path",
            "split",
            "label",
            "label_id",
            "output_sha256",
            "burst_id",
        }
        missing = required - set(reader.fieldnames or ())
        if missing:
            raise ValueError(f"V7 manifest is missing columns: {sorted(missing)}")
        for line_number, row in enumerate(reader, start=2):
            relative = PurePosixPath(row["relative_path"])
            if relative.is_absolute() or ".." in relative.parts:
                raise ValueError(f"Unsafe manifest path at line {line_number}")
            normalized = relative.as_posix()
            if normalized in seen:
                raise ValueError(f"Duplicate V7 manifest path: {normalized}")
            seen.add(normalized)
            split, label = row["split"], row["label"]
            label_id = int(row["label_id"])
            if split not in SPLITS or label not in CLASS_NAMES:
                raise ValueError(f"Invalid split/label at manifest line {line_number}")
            if label_id != CLASS_TO_INDEX[label]:
                raise ValueError(f"Label index mismatch at manifest line {line_number}")
            if len(relative.parts) != 3 or relative.parts[:2] != (split, label):
                raise ValueError(
                    f"Unexpected prepared path layout at line {line_number}"
                )
            path = data_root.joinpath(*relative.parts).resolve()
            if not path.is_relative_to(data_root) or not path.is_file():
                raise FileNotFoundError(f"Prepared V7 image not found: {path}")
            digest = _sha256(path)
            if digest != row["output_sha256"]:
                raise RuntimeError(f"Prepared V7 image hash mismatch: {path}")
            samples.append(
                Sample(
                    path, normalized, split, label, label_id, digest, row["burst_id"]
                )
            )

    for split in SPLITS:
        for label in CLASS_NAMES:
            if not any(
                sample.split == split and sample.label == label for sample in samples
            ):
                raise RuntimeError(f"Empty V7 split/class: {split}/{label}")
    _assert_no_burst_leakage(samples)
    return tuple(samples)


def samples_for_split(samples: Sequence[Sample], split: str) -> tuple[Sample, ...]:
    if split not in SPLITS:
        raise ValueError(f"Unknown V7 split: {split}")
    return tuple(sample for sample in samples if sample.split == split)


def balanced_steps_per_epoch(samples: Sequence[Sample], batch_size: int) -> int:
    if batch_size < 1:
        raise ValueError("batch_size must be positive")
    counts = [sum(sample.label_id == index for sample in samples) for index in range(3)]
    if any(count == 0 for count in counts):
        raise ValueError(f"Cannot balance empty V7 classes: {counts}")
    return math.ceil(max(counts) * len(CLASS_NAMES) / batch_size)


def make_balanced_training_dataset(
    samples: Sequence[Sample], *, batch_size: int, seed: int
) -> tf.data.Dataset:
    """Round-robin classes; only this stream receives online augmentation."""

    streams: list[tf.data.Dataset] = []
    for label_id, label in enumerate(CLASS_NAMES):
        paths = [str(sample.path) for sample in samples if sample.label_id == label_id]
        if not paths:
            raise ValueError(f"Empty V7 training class: {label}")
        stream = tf.data.Dataset.from_tensor_slices(paths)
        stream = stream.shuffle(
            len(paths), seed=seed + 1009 * label_id, reshuffle_each_iteration=True
        ).repeat()
        stream = stream.map(
            lambda path, selected_label=label_id: (
                preprocess_training_file(path),
                tf.cast(selected_label, tf.int32),
            ),
            num_parallel_calls=AUTOTUNE,
            deterministic=False,
        )
        streams.append(stream)

    choices = tf.data.Dataset.from_tensor_slices(
        tf.range(len(CLASS_NAMES), dtype=tf.int64)
    ).repeat()
    dataset = tf.data.Dataset.choose_from_datasets(
        streams, choices, stop_on_empty_dataset=False
    )
    options = tf.data.Options()
    options.experimental_deterministic = False
    return (
        dataset.with_options(options)
        .batch(batch_size, drop_remainder=False)
        .prefetch(AUTOTUNE)
    )


def make_evaluation_dataset(
    samples: Sequence[Sample], *, batch_size: int
) -> tf.data.Dataset:
    if not samples:
        raise ValueError("Cannot evaluate an empty V7 split")
    paths = [str(sample.path) for sample in samples]
    labels = [sample.label_id for sample in samples]
    dataset = tf.data.Dataset.from_tensor_slices((paths, labels)).map(
        lambda path, label: (preprocess_file_tensor(path), label),
        num_parallel_calls=AUTOTUNE,
        deterministic=True,
    )
    return dataset.cache().batch(batch_size).prefetch(AUTOTUNE)


def preprocess_file(path: str | Path) -> np.ndarray:
    tensor = preprocess_file_tensor(tf.constant(str(Path(path).resolve())))
    return tensor.numpy().astype(np.float32, copy=False)


def preprocess_file_tensor(path: tf.Tensor) -> tf.Tensor:
    encoded = tf.io.read_file(path)
    decoded = tf.io.decode_jpeg(encoded, channels=IMAGE_CHANNELS)
    raw = center_crop_resize_u8(decoded)
    return apply_float_input_contract(raw)


def preprocess_training_file(path: tf.Tensor) -> tf.Tensor:
    encoded = tf.io.read_file(path)
    decoded = tf.io.decode_jpeg(encoded, channels=IMAGE_CHANNELS)
    image = tf.cast(center_crop_resize_u8(decoded), tf.float32) / 255.0
    image = augment_training_image(image)
    return apply_float_input_contract(image)


def center_crop_resize_u8(image: tf.Tensor) -> tf.Tensor:
    """Exact integer index mapping implemented by ImagePreprocessor on ESP32."""

    image = tf.ensure_shape(tf.cast(image, tf.uint8), [None, None, IMAGE_CHANNELS])
    shape = tf.shape(image)
    height, width = shape[0], shape[1]
    square_size = tf.minimum(height, width)
    tf.debugging.assert_positive(square_size, message="Decoded image has zero size")
    crop_y = (height - square_size) // 2
    crop_x = (width - square_size) // 2
    square = tf.image.crop_to_bounding_box(
        image, crop_y, crop_x, square_size, square_size
    )
    indices = tf.math.floordiv(
        tf.range(IMAGE_SIZE, dtype=tf.int32) * square_size, IMAGE_SIZE
    )
    indices = tf.minimum(indices, square_size - 1)
    resized = tf.gather(tf.gather(square, indices, axis=0), indices, axis=1)
    return tf.ensure_shape(resized, [IMAGE_SIZE, IMAGE_SIZE, IMAGE_CHANNELS])


def apply_float_input_contract(image: tf.Tensor) -> tf.Tensor:
    if image.dtype.is_floating:
        pixels = tf.cast(tf.round(tf.clip_by_value(image, 0.0, 1.0) * 255.0), tf.uint8)
    else:
        pixels = tf.cast(image, tf.uint8)
    contracted = apply_firmware_input_contract_u8(pixels)
    return tf.ensure_shape(
        tf.cast(contracted, tf.float32) / 255.0,
        [IMAGE_SIZE, IMAGE_SIZE, IMAGE_CHANNELS],
    )


def apply_firmware_input_contract_u8(image: tf.Tensor) -> tf.Tensor:
    """Match RGB565 expansion and bounded Q8 luminance gain in firmware."""

    pixels = tf.cast(
        tf.ensure_shape(image, [IMAGE_SIZE, IMAGE_SIZE, IMAGE_CHANNELS]), tf.int32
    )
    steps = tf.constant([8, 4, 8], dtype=tf.int32)
    pixels = (pixels // steps) * steps
    luma = (
        77 * pixels[..., 0] + 150 * pixels[..., 1] + 29 * pixels[..., 2] + 128
    ) // 256
    pixel_count = IMAGE_SIZE * IMAGE_SIZE
    mean_luma = (tf.reduce_sum(luma) + pixel_count // 2) // pixel_count
    safe_mean = tf.maximum(mean_luma, 1)
    brighten_gain = tf.minimum(341, (96 * 256 + safe_mean // 2) // safe_mean)
    darken_gain = tf.maximum(192, (160 * 256 + safe_mean // 2) // safe_mean)
    gain_q8 = tf.where(
        mean_luma < 96,
        brighten_gain,
        tf.where(mean_luma > 160, darken_gain, tf.constant(256, tf.int32)),
    )
    result = tf.clip_by_value((pixels * gain_q8 + 128) // 256, 0, 255)
    return tf.ensure_shape(
        tf.cast(result, tf.uint8), [IMAGE_SIZE, IMAGE_SIZE, IMAGE_CHANNELS]
    )


def augment_training_image(image: tf.Tensor) -> tf.Tensor:
    """Bounded camera variation; no class mixing or external backgrounds."""

    image = tf.ensure_shape(image, [IMAGE_SIZE, IMAGE_SIZE, IMAGE_CHANNELS])
    image = tf.image.random_flip_left_right(image)
    image = _random_viewpoint(image)
    image = tf.image.adjust_gamma(
        tf.clip_by_value(image, 0.0, 1.0), tf.random.uniform([], 0.85, 1.15)
    )
    image = tf.image.random_brightness(image, max_delta=0.15)
    image = tf.image.random_contrast(image, lower=0.85, upper=1.15)
    image = tf.cond(
        tf.random.uniform([]) < 0.12,
        lambda: tf.nn.avg_pool2d(image[None, ...], 3, 1, "SAME")[0],
        lambda: image,
    )
    image = tf.cond(
        tf.random.uniform([]) < 0.25,
        lambda: image
        + tf.random.normal(tf.shape(image), stddev=tf.random.uniform([], 0.002, 0.012)),
        lambda: image,
    )
    image = tf.clip_by_value(image, 0.0, 1.0)
    image = tf.cond(
        tf.random.uniform([]) < 0.15,
        lambda: _random_jpeg(image),
        lambda: image,
    )
    return tf.ensure_shape(
        tf.clip_by_value(image, 0.0, 1.0),
        [IMAGE_SIZE, IMAGE_SIZE, IMAGE_CHANNELS],
    )


def _random_viewpoint(image: tf.Tensor) -> tf.Tensor:
    angle = tf.random.uniform([], -0.157080, 0.157080)  # +/-9 degrees
    scale = tf.random.uniform([], 0.90, 1.10)
    translate_x = tf.random.uniform([], -0.08, 0.08) * float(IMAGE_SIZE)
    translate_y = tf.random.uniform([], -0.08, 0.08) * float(IMAGE_SIZE)
    cosine = tf.cos(angle) / scale
    sine = tf.sin(angle) / scale
    center = (float(IMAGE_SIZE) - 1.0) / 2.0
    offset_x = center - cosine * center - sine * center - translate_x
    offset_y = center + sine * center - cosine * center - translate_y
    transform = tf.reshape(
        tf.stack([cosine, sine, offset_x, -sine, cosine, offset_y, 0.0, 0.0]),
        [1, 8],
    )
    result = tf.raw_ops.ImageProjectiveTransformV3(
        images=image[None, ...],
        transforms=transform,
        output_shape=tf.constant([IMAGE_SIZE, IMAGE_SIZE], tf.int32),
        interpolation="BILINEAR",
        fill_mode="REFLECT",
        fill_value=0.0,
    )[0]
    return tf.ensure_shape(result, [IMAGE_SIZE, IMAGE_SIZE, IMAGE_CHANNELS])


def _random_jpeg(image: tf.Tensor) -> tf.Tensor:
    pixels = tf.cast(tf.round(tf.clip_by_value(image, 0.0, 1.0) * 255.0), tf.uint8)
    compressed = tf.image.random_jpeg_quality(pixels, 65, 95)
    return tf.cast(compressed, tf.float32) / 255.0


def _assert_no_burst_leakage(samples: Sequence[Sample]) -> None:
    assignments: dict[str, str] = {}
    for sample in samples:
        previous = assignments.setdefault(sample.burst_id, sample.split)
        if previous != sample.split:
            raise RuntimeError(
                f"Capture burst leaks across splits: {sample.burst_id} ({previous}/{sample.split})"
            )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
