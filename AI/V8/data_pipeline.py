"""Balanced V8 input pipeline with rotation-only geometric augmentation."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math
from pathlib import Path
from typing import Sequence

import tensorflow as tf

from V8.config import (
    CLASS_NAMES,
    CLASS_TO_INDEX,
    DATASET_DIR,
    IMAGE_CHANNELS,
    IMAGE_EXTENSIONS,
    IMAGE_SIZE,
    SPLITS,
)


AUTOTUNE = tf.data.AUTOTUNE


@dataclass(frozen=True)
class Sample:
    path: Path
    split: str
    label: str
    label_id: int
    sha256: str


def load_samples(root: str | Path = DATASET_DIR) -> tuple[Sample, ...]:
    """Scan the supplied prepared split and reject leakage/invalid layout."""

    data_root = Path(root).expanduser().resolve()
    if not data_root.is_dir():
        raise FileNotFoundError(f"V8 dataset does not exist: {data_root}")
    samples: list[Sample] = []
    hashes: dict[str, Sample] = {}
    for split in SPLITS:
        split_dir = data_root / split
        found_classes = {p.name for p in split_dir.iterdir() if p.is_dir()}
        if found_classes != set(CLASS_NAMES):
            raise ValueError(
                f"{split_dir} classes must be {sorted(CLASS_NAMES)}, got "
                f"{sorted(found_classes)}"
            )
        for label in CLASS_NAMES:
            paths = sorted(
                p for p in (split_dir / label).iterdir()
                if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS
            )
            if not paths:
                raise ValueError(f"Empty V8 split/class: {split}/{label}")
            for path in paths:
                digest = _sha256(path)
                sample = Sample(path.resolve(), split, label, CLASS_TO_INDEX[label], digest)
                if digest in hashes:
                    previous = hashes[digest]
                    raise ValueError(
                        "Exact image duplicate detected (possible split leakage): "
                        f"{previous.path} and {sample.path}"
                    )
                hashes[digest] = sample
                samples.append(sample)
    return tuple(samples)


def samples_for_split(samples: Sequence[Sample], split: str) -> tuple[Sample, ...]:
    if split not in SPLITS:
        raise ValueError(f"Unknown split: {split}")
    return tuple(sample for sample in samples if sample.split == split)


def steps_per_epoch(
    samples: Sequence[Sample], batch_size: int, views_per_source: int
) -> int:
    """Balance to the largest class, then draw many fresh online views."""

    if batch_size < 1 or views_per_source < 1:
        raise ValueError("batch_size and views_per_source must be positive")
    counts = [sum(s.label_id == i for s in samples) for i in range(len(CLASS_NAMES))]
    if any(count == 0 for count in counts):
        raise ValueError(f"Cannot balance empty classes: {counts}")
    return math.ceil(max(counts) * len(CLASS_NAMES) * views_per_source / batch_size)


def make_training_dataset(
    samples: Sequence[Sample], *, batch_size: int, seed: int
) -> tf.data.Dataset:
    streams: list[tf.data.Dataset] = []
    for label_id, label in enumerate(CLASS_NAMES):
        paths = [str(s.path) for s in samples if s.label_id == label_id]
        if not paths:
            raise ValueError(f"Empty training class: {label}")
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


def make_evaluation_dataset(
    samples: Sequence[Sample], *, batch_size: int
) -> tf.data.Dataset:
    paths = [str(s.path) for s in samples]
    labels = [s.label_id for s in samples]
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
    image = tf.cast(center_crop_resize_u8(image), tf.float32) / 255.0
    image = augment_rotation_and_lighting(image)
    return apply_illumination_contract(image)


def center_crop_resize_u8(image: tf.Tensor) -> tf.Tensor:
    """Center-square crop and exact nearest-floor resize used on ESP32."""

    image = tf.ensure_shape(tf.cast(image, tf.uint8), [None, None, IMAGE_CHANNELS])
    shape = tf.shape(image)
    side = tf.minimum(shape[0], shape[1])
    tf.debugging.assert_positive(side, message="Decoded image is empty")
    y0 = (shape[0] - side) // 2
    x0 = (shape[1] - side) // 2
    square = tf.image.crop_to_bounding_box(image, y0, x0, side, side)
    indices = tf.minimum(
        tf.range(IMAGE_SIZE, dtype=tf.int32) * side // IMAGE_SIZE, side - 1
    )
    resized = tf.gather(tf.gather(square, indices, axis=0), indices, axis=1)
    return tf.ensure_shape(resized, [IMAGE_SIZE, IMAGE_SIZE, IMAGE_CHANNELS])


def augment_rotation_and_lighting(image: tf.Tensor) -> tf.Tensor:
    """No affine warping: only lossless quarter-turns plus photometric changes."""

    image = tf.ensure_shape(image, [IMAGE_SIZE, IMAGE_SIZE, IMAGE_CHANNELS])
    image = tf.image.rot90(image, tf.random.uniform([], 0, 4, dtype=tf.int32))

    # Simulate dim/bright exposure, non-linear sensor response, contrast and
    # warm/cool/mixed illuminants. The deployment preprocessing below removes
    # most of this variation; remaining variation is learned by the CNN.
    image = tf.image.adjust_gamma(image, tf.random.uniform([], 0.55, 1.80))
    image *= tf.random.uniform([], 0.45, 1.80)
    image = tf.image.adjust_contrast(image, tf.random.uniform([], 0.70, 1.35))
    channel_gain = tf.random.uniform([1, 1, 3], 0.72, 1.28)
    image *= channel_gain
    return tf.ensure_shape(
        tf.clip_by_value(image, 0.0, 1.0),
        [IMAGE_SIZE, IMAGE_SIZE, IMAGE_CHANNELS],
    )


def apply_illumination_contract(image: tf.Tensor) -> tf.Tensor:
    """RGB565 + bounded gray-world WB + bounded global luma normalization."""

    if image.dtype.is_floating:
        pixels = tf.cast(
            tf.round(tf.clip_by_value(image, 0.0, 1.0) * 255.0), tf.int32
        )
    else:
        pixels = tf.cast(image, tf.int32)
    pixels = (pixels // tf.constant([8, 4, 8], tf.int32)) * tf.constant(
        [8, 4, 8], tf.int32
    )

    # Bounded gray-world correction in Q10. Bounds avoid amplifying noise in a
    # nearly absent channel and preserve useful object colour information.
    channel_sum = tf.reduce_sum(pixels, axis=[0, 1])
    count = IMAGE_SIZE * IMAGE_SIZE
    channel_mean = (channel_sum + count // 2) // count
    target = (tf.reduce_sum(channel_mean) + 1) // 3
    gains_q10 = (target * 1024 + tf.maximum(channel_mean, 1) // 2) // tf.maximum(
        channel_mean, 1
    )
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
        [IMAGE_SIZE, IMAGE_SIZE, IMAGE_CHANNELS],
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

