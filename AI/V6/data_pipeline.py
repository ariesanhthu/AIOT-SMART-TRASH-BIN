"""Balanced V6 input pipeline with train-only camera-domain augmentation."""

from __future__ import annotations

import math
from typing import Sequence

import tensorflow as tf

from V6.runtime import LABELS
from src.config import IMAGE_CHANNELS, IMAGE_SIZE
from src.dataset import ImageSample, apply_input_contract_u8


AUTOTUNE = tf.data.AUTOTUNE
ENVIRONMENT_PROFILE_COUNT = 4


def balanced_steps_per_epoch(samples: Sequence[ImageSample], batch_size: int) -> int:
    """Expose every class exactly as often as the largest source class."""

    counts = [
        sum(sample.label_id == label_id for sample in samples)
        for label_id in range(len(LABELS))
    ]
    if any(count == 0 for count in counts):
        raise ValueError(f"Cannot balance empty classes: {counts}")
    return math.ceil(max(counts) * len(LABELS) / batch_size)


def make_balanced_training_dataset(
    samples: Sequence[ImageSample], *, batch_size: int, seed: int
) -> tf.data.Dataset:
    """Create an infinite round-robin class stream with fresh augmentation."""

    if batch_size < 1:
        raise ValueError("batch_size must be positive")
    streams: list[tf.data.Dataset] = []
    for label_id, label in enumerate(LABELS):
        paths = [str(sample.path) for sample in samples if sample.label_id == label_id]
        if not paths:
            raise ValueError(f"Training class is empty: {label}")
        stream = tf.data.Dataset.from_tensor_slices(paths)
        stream = stream.shuffle(
            len(paths),
            seed=seed + 1009 * label_id,
            reshuffle_each_iteration=True,
        ).repeat()
        stream = stream.map(
            lambda path, class_id=label_id: (
                augment_environment(decode_and_preprocess_raw(path)),
                tf.cast(class_id, tf.int32),
            ),
            num_parallel_calls=AUTOTUNE,
            deterministic=False,
        )
        streams.append(stream)

    choices = tf.data.Dataset.from_tensor_slices(
        tf.range(len(LABELS), dtype=tf.int64)
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


def make_balanced_calibration_dataset(
    samples: Sequence[ImageSample], *, batch_size: int, seed: int
) -> tf.data.Dataset:
    """Create a balanced stream with mild camera augmentation for fine-tuning."""

    if batch_size < 1:
        raise ValueError("batch_size must be positive")
    streams: list[tf.data.Dataset] = []
    for label_id, label in enumerate(LABELS):
        paths = [str(sample.path) for sample in samples if sample.label_id == label_id]
        if not paths:
            raise ValueError(f"Training class is empty: {label}")
        stream = tf.data.Dataset.from_tensor_slices(paths)
        stream = stream.shuffle(
            len(paths), seed=seed + 2017 * label_id, reshuffle_each_iteration=True
        ).repeat()
        stream = stream.map(
            lambda path, class_id=label_id: (
                augment_calibration(decode_and_preprocess_raw(path)),
                tf.cast(class_id, tf.int32),
            ),
            num_parallel_calls=AUTOTUNE,
            deterministic=False,
        )
        streams.append(stream)
    choices = tf.data.Dataset.from_tensor_slices(
        tf.range(len(LABELS), dtype=tf.int64)
    ).repeat()
    dataset = tf.data.Dataset.choose_from_datasets(
        streams, choices, stop_on_empty_dataset=False
    )
    options = tf.data.Options()
    options.experimental_deterministic = False
    return dataset.with_options(options).batch(batch_size).prefetch(AUTOTUNE)


def make_environment_validation_dataset(
    samples: Sequence[ImageSample], *, batch_size: int
) -> tf.data.Dataset:
    """Build deterministic overexposed/warm/cool/low-light validation views."""

    if not samples:
        raise ValueError("Cannot build environmental validation without samples")
    paths = [str(sample.path) for sample in samples]
    labels = [sample.label_id for sample in samples]
    combined: tf.data.Dataset | None = None
    for profile_id in range(ENVIRONMENT_PROFILE_COUNT):
        profile = tf.data.Dataset.from_tensor_slices((paths, labels)).map(
            lambda path, label, selected=profile_id: (
                apply_float_input_contract(
                    deterministic_environment_profile(
                        decode_and_preprocess_raw(path), selected
                    )
                ),
                label,
            ),
            num_parallel_calls=AUTOTUNE,
            deterministic=True,
        )
        combined = profile if combined is None else combined.concatenate(profile)
    if combined is None:
        raise RuntimeError("Environmental validation profiles were not created")
    return combined.cache().batch(batch_size).prefetch(AUTOTUNE)


def decode_and_preprocess_raw(path: tf.Tensor) -> tf.Tensor:
    """Apply the firmware crop/resize mapping, before its sensor contract."""

    encoded = tf.io.read_file(path)
    image = tf.io.decode_image(
        encoded, channels=IMAGE_CHANNELS, expand_animations=False
    )
    image.set_shape([None, None, IMAGE_CHANNELS])
    shape = tf.shape(image)
    height, width = shape[0], shape[1]
    square_size = tf.minimum(height, width)
    tf.debugging.assert_positive(square_size, message="Decoded image has zero size")
    offset_y = (height - square_size) // 2
    offset_x = (width - square_size) // 2
    square = tf.image.crop_to_bounding_box(
        image, offset_y, offset_x, square_size, square_size
    )
    indices = tf.math.floordiv(
        tf.range(IMAGE_SIZE, dtype=tf.int32) * square_size, IMAGE_SIZE
    )
    indices = tf.minimum(indices, square_size - 1)
    resized = tf.gather(tf.gather(square, indices, axis=0), indices, axis=1)
    resized.set_shape([IMAGE_SIZE, IMAGE_SIZE, IMAGE_CHANNELS])
    return tf.image.convert_image_dtype(resized, tf.float32)


def augment_environment(image: tf.Tensor) -> tf.Tensor:
    """Apply bounded camera augmentation without changing the V4 data domain."""

    image = tf.ensure_shape(image, [IMAGE_SIZE, IMAGE_SIZE, IMAGE_CHANNELS])
    image = tf.image.random_flip_left_right(image)
    image = _random_viewpoint(image)

    # Most views stay close to V4/new-camera inputs. Extreme light paths are
    # deliberately rare so the small dataset is not overwhelmed by synthetic domains.
    selector = tf.random.uniform([])
    image = tf.case(
        [
            (selector < 0.66, lambda: _mild_exposure(image)),
            (selector < 0.78, lambda: _random_overexposure(image)),
            (selector < 0.90, lambda: _random_low_light(image)),
        ],
        default=lambda: _random_general_exposure(image),
        exclusive=False,
    )
    image = tf.image.random_contrast(image, 0.82, 1.20)
    image = tf.image.random_saturation(image, 0.84, 1.18)
    image = tf.image.random_hue(image, 0.025)
    image = image * tf.random.uniform([1, 1, 3], 0.92, 1.08)
    image = tf.cond(
        tf.random.uniform([]) < 0.20,
        lambda: _random_shadow(image),
        lambda: image,
    )
    image = tf.clip_by_value(image, 0.0, 1.0)
    image = tf.cond(
        tf.random.uniform([]) < 0.10,
        lambda: tf.nn.avg_pool2d(image[None, ...], 3, 1, "SAME")[0],
        lambda: image,
    )
    image = tf.cond(
        tf.random.uniform([]) < 0.12,
        lambda: _random_low_resolution(image),
        lambda: image,
    )
    image = tf.cond(
        tf.random.uniform([]) < 0.22,
        lambda: image
        + tf.random.normal(
            tf.shape(image), stddev=tf.random.uniform([], 0.003, 0.014)
        ),
        lambda: image,
    )
    return apply_float_input_contract(image)


def augment_calibration(image: tf.Tensor) -> tf.Tensor:
    """Adapt robust features to clean camera data without losing light coverage."""

    image = tf.ensure_shape(image, [IMAGE_SIZE, IMAGE_SIZE, IMAGE_CHANNELS])
    image = tf.image.random_flip_left_right(image)
    image = tf.image.resize_with_crop_or_pad(image, IMAGE_SIZE + 8, IMAGE_SIZE + 8)
    image = tf.image.random_crop(
        image, [IMAGE_SIZE, IMAGE_SIZE, IMAGE_CHANNELS]
    )
    selector = tf.random.uniform([])
    image = tf.case(
        [
            (selector < 0.12, lambda: _random_overexposure(image)),
            (selector < 0.22, lambda: _random_low_light(image)),
        ],
        default=lambda: _mild_exposure(image),
        exclusive=False,
    )
    image = tf.image.random_contrast(image, 0.84, 1.18)
    image = tf.image.random_saturation(image, 0.86, 1.16)
    image = image * tf.random.uniform([1, 1, 3], 0.93, 1.07)
    image = tf.cond(
        tf.random.uniform([]) < 0.18,
        lambda: image + tf.random.normal(tf.shape(image), stddev=0.008),
        lambda: image,
    )
    return apply_float_input_contract(image)


def deterministic_environment_profile(image: tf.Tensor, profile_id: int) -> tf.Tensor:
    values = tf.clip_by_value(image, 0.0, 1.0)
    if profile_id == 0:  # clipped overexposure
        return tf.clip_by_value(tf.pow(values, 0.70) * 1.18 + 0.055, 0.0, 1.0)
    if profile_id == 1:  # warm auto-white-balance error
        return tf.clip_by_value(values * [1.18, 1.02, 0.78], 0.0, 1.0)
    if profile_id == 2:  # cool auto-white-balance error
        return tf.clip_by_value(values * [0.80, 0.98, 1.18], 0.0, 1.0)
    if profile_id == 3:  # low light
        return tf.clip_by_value(tf.pow(values, 1.58) * 0.70, 0.0, 1.0)
    raise ValueError(f"Unknown environment profile: {profile_id}")


def apply_float_input_contract(image: tf.Tensor) -> tf.Tensor:
    """Use the exact RGB565 + integer luma path used at inference."""

    pixels = tf.cast(
        tf.round(tf.clip_by_value(image, 0.0, 1.0) * 255.0), tf.uint8
    )
    contracted = apply_input_contract_u8(pixels)
    return tf.ensure_shape(
        tf.cast(contracted, tf.float32) / 255.0,
        [IMAGE_SIZE, IMAGE_SIZE, IMAGE_CHANNELS],
    )


def _random_viewpoint(image: tf.Tensor) -> tf.Tensor:
    angle = tf.random.uniform([], -0.174533, 0.174533)  # +/-10 degrees
    scale = tf.random.uniform([], 0.92, 1.08)
    shear = tf.random.uniform([], -0.035, 0.035)
    translate_x = tf.random.uniform([], -0.05, 0.05) * float(IMAGE_SIZE)
    translate_y = tf.random.uniform([], -0.05, 0.05) * float(IMAGE_SIZE)
    cosine = tf.cos(angle) / scale
    sine = tf.sin(angle) / scale
    a0, a1 = cosine, sine + shear
    b0, b1 = -sine, cosine
    center = (float(IMAGE_SIZE) - 1.0) / 2.0
    a2 = center - a0 * center - a1 * center - translate_x
    b2 = center - b0 * center - b1 * center - translate_y
    transform = tf.reshape(
        tf.stack([a0, a1, a2, b0, b1, b2, 0.0, 0.0]), [1, 8]
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


def _mild_exposure(image: tf.Tensor) -> tf.Tensor:
    image = tf.image.adjust_gamma(
        tf.clip_by_value(image, 0.0, 1.0),
        tf.random.uniform([], 0.88, 1.14),
        tf.random.uniform([], 0.94, 1.06),
    )
    return tf.image.random_brightness(image, 0.055)


def _random_general_exposure(image: tf.Tensor) -> tf.Tensor:
    image = tf.image.adjust_gamma(
        tf.clip_by_value(image, 0.0, 1.0),
        tf.random.uniform([], 0.78, 1.28),
        tf.random.uniform([], 0.90, 1.10),
    )
    return tf.image.random_brightness(image, 0.09)


def _random_overexposure(image: tf.Tensor) -> tf.Tensor:
    image = tf.image.adjust_gamma(
        tf.clip_by_value(image, 0.0, 1.0),
        tf.random.uniform([], 0.72, 0.90),
        tf.random.uniform([], 1.02, 1.13),
    )
    image = image + tf.random.uniform([], 0.015, 0.055)
    return tf.cond(
        tf.random.uniform([]) < 0.28,
        lambda: _add_random_glare(image),
        lambda: tf.clip_by_value(image, 0.0, 1.0),
    )


def _random_low_light(image: tf.Tensor) -> tf.Tensor:
    image = tf.image.adjust_gamma(
        tf.clip_by_value(image, 0.0, 1.0),
        tf.random.uniform([], 1.18, 1.52),
        tf.random.uniform([], 0.72, 0.90),
    )
    return tf.clip_by_value(image, 0.0, 1.0)


def _random_white_balance(image: tf.Tensor) -> tf.Tensor:
    selector = tf.random.uniform([])
    return tf.case(
        [
            (
                selector < 0.24,
                lambda: image
                * tf.reshape(
                    tf.stack(
                        [
                            tf.random.uniform([], 1.08, 1.22),
                            tf.random.uniform([], 0.97, 1.06),
                            tf.random.uniform([], 0.76, 0.92),
                        ]
                    ),
                    [1, 1, 3],
                ),
            ),
            (
                selector < 0.48,
                lambda: image
                * tf.reshape(
                    tf.stack(
                        [
                            tf.random.uniform([], 0.76, 0.92),
                            tf.random.uniform([], 0.95, 1.05),
                            tf.random.uniform([], 1.08, 1.22),
                        ]
                    ),
                    [1, 1, 3],
                ),
            ),
        ],
        default=lambda: image * tf.random.uniform([1, 1, 3], 0.86, 1.14),
        exclusive=False,
    )


def _add_random_glare(image: tf.Tensor) -> tf.Tensor:
    coordinates = tf.linspace(0.0, 1.0, IMAGE_SIZE)
    grid_y, grid_x = tf.meshgrid(coordinates, coordinates, indexing="ij")
    center_x = tf.random.uniform([], 0.12, 0.88)
    center_y = tf.random.uniform([], 0.12, 0.88)
    sigma_x = tf.random.uniform([], 0.16, 0.40)
    sigma_y = tf.random.uniform([], 0.16, 0.40)
    distance = (
        tf.square((grid_x - center_x) / sigma_x)
        + tf.square((grid_y - center_y) / sigma_y)
    )
    mask = tf.exp(-0.5 * distance)[..., None]
    return tf.clip_by_value(image + mask * tf.random.uniform([], 0.06, 0.22), 0.0, 1.0)


def _random_shadow(image: tf.Tensor) -> tf.Tensor:
    start = tf.random.uniform([], 0.48, 0.82)
    ramp = tf.linspace(start, 1.0, IMAGE_SIZE)
    ramp = tf.cond(
        tf.random.uniform([]) < 0.5,
        lambda: tf.reverse(ramp, [0]),
        lambda: ramp,
    )
    horizontal = tf.reshape(ramp, [1, IMAGE_SIZE, 1])
    vertical = tf.reshape(ramp, [IMAGE_SIZE, 1, 1])
    return image * tf.cond(
        tf.random.uniform([]) < 0.5, lambda: horizontal, lambda: vertical
    )


def _random_low_resolution(image: tf.Tensor) -> tf.Tensor:
    side = tf.random.uniform([], 54, 85, dtype=tf.int32)
    small = tf.image.resize(image, [side, side], method="area", antialias=True)
    return tf.image.resize(small, [IMAGE_SIZE, IMAGE_SIZE], method="nearest")
