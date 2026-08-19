"""Manifest-driven V10 input pipeline with one shared ESP32 preprocessing path."""

from __future__ import annotations

import csv
from dataclasses import dataclass
import hashlib
import math
from pathlib import Path
from typing import Sequence

import tensorflow as tf

from V10.config import (
    CLASS_NAMES,
    CLASS_TO_INDEX,
    DATASET_DIR,
    IMAGE_CHANNELS,
    IMAGE_HEIGHT,
    IMAGE_WIDTH,
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
    kind: str
    source_group: str
    online_augment: bool
    sha256: str


def load_samples(root: str | Path = DATASET_DIR) -> tuple[Sample, ...]:
    data_root = Path(root).expanduser().resolve()
    manifest = data_root / "manifest.csv"
    if not manifest.is_file():
        raise FileNotFoundError(f"V10 manifest does not exist: {manifest}")
    rows = list(csv.DictReader(manifest.open(encoding="utf-8", newline="")))
    samples: list[Sample] = []
    hashes: dict[str, str] = {}
    groups: dict[str, set[str]] = {}
    for row in rows:
        path = data_root / row["relative_path"]
        if not path.is_file():
            raise FileNotFoundError(f"Manifest image is missing: {path}")
        split, label = row["split"], row["label"]
        if split not in SPLITS or label not in CLASS_NAMES:
            raise ValueError(f"Invalid manifest split/label: {row}")
        if int(row["label_id"]) != CLASS_TO_INDEX[label]:
            raise ValueError(f"Invalid label id: {row}")
        digest = _sha256(path)
        if digest != row["sha256"]:
            raise ValueError(f"V10 checksum mismatch: {path}")
        if digest in hashes:
            raise ValueError(f"Exact duplicate: {hashes[digest]} and {path}")
        hashes[digest] = str(path)
        if split != "train" and row["kind"] != "original":
            raise ValueError(f"Augmentation outside train: {path}")
        group = row["source_group"]
        groups.setdefault(group, set()).add(split)
        online_augment = row["online_augment"].lower() == "true"
        if online_augment:
            raise ValueError(
                f"V10 requires saved augmentation files; online augmentation is forbidden: {path}"
            )
        samples.append(Sample(
            path=path.resolve(),
            relative_path=row["relative_path"],
            split=split,
            label=label,
            label_id=CLASS_TO_INDEX[label],
            kind=row["kind"],
            source_group=group,
            online_augment=False,
            sha256=digest,
        ))
    leaking = {group: splits for group, splits in groups.items() if len(splits) > 1}
    if leaking:
        raise ValueError(f"V10 source-group leakage: {leaking}")
    for split in SPLITS:
        counts = [sum(s.split == split and s.label == label for s in samples) for label in CLASS_NAMES]
        if any(count == 0 for count in counts):
            raise ValueError(f"V10 {split} contains an empty class: {counts}")
        # Training may contain unequal numbers of physical source files.  The
        # round-robin class streams below still present every class equally.
        # Held-out metrics remain directly comparable on balanced splits.
        if split != "train" and len(set(counts)) != 1:
            raise ValueError(f"V10 {split} is not class-balanced: {counts}")
    return tuple(samples)


def samples_for_split(samples: Sequence[Sample], split: str) -> tuple[Sample, ...]:
    if split not in SPLITS:
        raise ValueError(f"Unknown split: {split}")
    return tuple(sample for sample in samples if sample.split == split)


def steps_per_epoch(samples: Sequence[Sample], batch_size: int, views_per_source: int) -> int:
    if batch_size < 1 or views_per_source < 1:
        raise ValueError("batch size and views per source must be positive")
    counts = [sum(s.label_id == index for s in samples) for index in range(len(CLASS_NAMES))]
    if any(count == 0 for count in counts):
        raise ValueError(f"Cannot train from empty classes: {counts}")
    return math.ceil(max(counts) * len(CLASS_NAMES) * views_per_source / batch_size)


def make_training_dataset(
    samples: Sequence[Sample], *, batch_size: int, seed: int
) -> tf.data.Dataset:
    streams = []
    for label_id, label in enumerate(CLASS_NAMES):
        selected = [sample for sample in samples if sample.label_id == label_id]
        if not selected:
            raise ValueError(f"Empty training class: {label}")
        paths = [str(sample.path) for sample in selected]
        stream = tf.data.Dataset.from_tensor_slices(paths)
        stream = stream.shuffle(
            len(paths), seed=seed + label_id * 1009, reshuffle_each_iteration=True
        ).repeat()
        stream = stream.map(
            lambda path, y=label_id: (
                preprocess_training_file(path), tf.cast(y, tf.int32)
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
    return dataset.with_options(options).batch(batch_size).prefetch(AUTOTUNE)


def make_evaluation_dataset(samples: Sequence[Sample], *, batch_size: int) -> tf.data.Dataset:
    paths = [str(sample.path) for sample in samples]
    labels = [sample.label_id for sample in samples]
    dataset = tf.data.Dataset.from_tensor_slices((paths, labels)).map(
        lambda path, label: (preprocess_file_tensor(path), label),
        num_parallel_calls=AUTOTUNE,
        deterministic=True,
    )
    return dataset.cache().batch(batch_size).prefetch(AUTOTUNE)


def preprocess_file_tensor(path: tf.Tensor) -> tf.Tensor:
    image = tf.io.decode_image(
        tf.io.read_file(path), channels=IMAGE_CHANNELS, expand_animations=False
    )
    return apply_illumination_contract(center_crop_resize_u8(image))


def preprocess_training_file(path: tf.Tensor) -> tf.Tensor:
    image = tf.io.decode_image(
        tf.io.read_file(path), channels=IMAGE_CHANNELS, expand_animations=False
    )
    return apply_illumination_contract(center_crop_resize_u8(image))


def center_crop_resize_u8(image: tf.Tensor) -> tf.Tensor:
    """Center-crop to 4:3 and floor-resize exactly like ESP-TRASH-V3."""
    image = tf.ensure_shape(tf.cast(image, tf.uint8), [None, None, IMAGE_CHANNELS])
    shape = tf.shape(image)
    source_height, source_width = shape[0], shape[1]
    tf.debugging.assert_positive(source_height, message="Decoded image is empty")
    tf.debugging.assert_positive(source_width, message="Decoded image is empty")

    source_is_wider = source_width * IMAGE_HEIGHT > source_height * IMAGE_WIDTH
    crop_width = tf.where(
        source_is_wider,
        source_height * IMAGE_WIDTH // IMAGE_HEIGHT,
        source_width,
    )
    crop_height = tf.where(
        source_is_wider,
        source_height,
        source_width * IMAGE_HEIGHT // IMAGE_WIDTH,
    )
    crop_width = tf.maximum(crop_width, 1)
    crop_height = tf.maximum(crop_height, 1)
    x0 = (source_width - crop_width) // 2
    y0 = (source_height - crop_height) // 2
    cropped = tf.image.crop_to_bounding_box(
        image, y0, x0, crop_height, crop_width
    )
    y_indices = tf.minimum(
        tf.range(IMAGE_HEIGHT, dtype=tf.int32) * crop_height // IMAGE_HEIGHT,
        crop_height - 1,
    )
    x_indices = tf.minimum(
        tf.range(IMAGE_WIDTH, dtype=tf.int32) * crop_width // IMAGE_WIDTH,
        crop_width - 1,
    )
    resized = tf.gather(tf.gather(cropped, y_indices, axis=0), x_indices, axis=1)
    return tf.ensure_shape(
        resized, [IMAGE_HEIGHT, IMAGE_WIDTH, IMAGE_CHANNELS]
    )


def apply_illumination_contract(image: tf.Tensor) -> tf.Tensor:
    """RGB565 + bounded gray-world WB + bounded mean-luma normalization."""
    if image.dtype.is_floating:
        pixels = tf.cast(
            tf.round(tf.clip_by_value(image, 0.0, 1.0) * 255.0), tf.int32
        )
    else:
        pixels = tf.cast(image, tf.int32)
    steps = tf.constant([8, 4, 8], tf.int32)
    pixels = (pixels // steps) * steps

    channel_sum = tf.reduce_sum(pixels, axis=[0, 1])
    count = IMAGE_HEIGHT * IMAGE_WIDTH
    channel_mean = (channel_sum + count // 2) // count
    target = (tf.reduce_sum(channel_mean) + 1) // 3
    safe_channel_mean = tf.maximum(channel_mean, 1)
    gains_q10 = (target * 1024 + safe_channel_mean // 2) // safe_channel_mean
    gains_q10 = tf.clip_by_value(gains_q10, 768, 1365)
    pixels = tf.clip_by_value((pixels * gains_q10 + 512) // 1024, 0, 255)

    luma = (
        77 * pixels[..., 0] + 150 * pixels[..., 1] + 29 * pixels[..., 2] + 128
    ) // 256
    mean_luma = (tf.reduce_sum(luma) + count // 2) // count
    safe_mean = tf.maximum(mean_luma, 1)
    brighten = tf.minimum(341, (96 * 256 + safe_mean // 2) // safe_mean)
    darken = tf.maximum(192, (160 * 256 + safe_mean // 2) // safe_mean)
    gain_q8 = tf.where(
        mean_luma < 96,
        brighten,
        tf.where(mean_luma > 160, darken, tf.constant(256, tf.int32)),
    )
    pixels = tf.clip_by_value((pixels * gain_q8 + 128) // 256, 0, 255)
    return tf.ensure_shape(
        tf.cast(pixels, tf.float32) / 255.0,
        [IMAGE_HEIGHT, IMAGE_WIDTH, IMAGE_CHANNELS],
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
