"""Balanced V5 input pipeline with train-only environmental augmentation."""

from __future__ import annotations

import math
from typing import Sequence

import tensorflow as tf

from V5.runtime import LABELS
from src.config import IMAGE_CHANNELS, IMAGE_SIZE
from src.dataset import ImageSample, apply_input_contract_u8


AUTOTUNE = tf.data.AUTOTUNE


def balanced_steps_per_epoch(samples: Sequence[ImageSample], batch_size: int) -> int:
    """Return steps for one exact, class-balanced pass at the largest count."""

    counts = [sum(sample.label_id == index for sample in samples) for index in range(len(LABELS))]
    if any(count == 0 for count in counts):
        raise ValueError(f"Cannot balance zero-sized classes: {counts}")
    return math.ceil(max(counts) * len(LABELS) / batch_size)


def make_balanced_training_dataset(
    samples: Sequence[ImageSample], *, batch_size: int, seed: int
) -> tf.data.Dataset:
    """Build an infinite round-robin stream with identical class exposure.

    Oversampling is done only in memory. Every base image receives fresh
    geometry, lighting and sensor perturbations whenever it is sampled.
    """

    if batch_size < 1:
        raise ValueError("batch_size must be positive")
    class_streams: list[tf.data.Dataset] = []
    for label_id, label in enumerate(LABELS):
        paths = [str(sample.path) for sample in samples if sample.label_id == label_id]
        if not paths:
            raise ValueError(f"Training class is empty: {label}")
        stream = tf.data.Dataset.from_tensor_slices(paths)
        stream = stream.shuffle(
            len(paths), seed=seed + 1009 * label_id, reshuffle_each_iteration=True
        ).repeat()
        stream = stream.map(
            lambda path, class_id=label_id: (
                augment_environment(decode_and_preprocess(path)),
                tf.cast(class_id, tf.int32),
            ),
            num_parallel_calls=AUTOTUNE,
            deterministic=False,
        )
        class_streams.append(stream)

    choices = tf.data.Dataset.from_tensor_slices(
        tf.range(len(LABELS), dtype=tf.int64)
    ).repeat()
    dataset = tf.data.Dataset.choose_from_datasets(
        class_streams, choices, stop_on_empty_dataset=False
    )
    options = tf.data.Options()
    options.experimental_deterministic = False
    dataset = dataset.with_options(options)
    return dataset.batch(batch_size, drop_remainder=False).prefetch(AUTOTUNE)


def make_balanced_calibration_dataset(
    samples: Sequence[ImageSample], *, batch_size: int, seed: int
) -> tf.data.Dataset:
    """Build an exact-balanced stream with milder fine-tuning augmentation."""

    if batch_size < 1:
        raise ValueError("batch_size must be positive")
    class_streams: list[tf.data.Dataset] = []
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
                augment_calibration(decode_and_preprocess(path)),
                tf.cast(class_id, tf.int32),
            ),
            num_parallel_calls=AUTOTUNE,
            deterministic=False,
        )
        class_streams.append(stream)
    choices = tf.data.Dataset.from_tensor_slices(
        tf.range(len(LABELS), dtype=tf.int64)
    ).repeat()
    dataset = tf.data.Dataset.choose_from_datasets(
        class_streams, choices, stop_on_empty_dataset=False
    )
    options = tf.data.Options()
    options.experimental_deterministic = False
    return dataset.with_options(options).batch(batch_size).prefetch(AUTOTUNE)


def make_environment_validation_dataset(
    samples: Sequence[ImageSample], *, batch_size: int
) -> tf.data.Dataset:
    """Build deterministic low/bright/warm/cool validation profiles."""

    if not samples:
        raise ValueError("Cannot build environmental validation from zero samples")
    paths = [str(sample.path) for sample in samples]
    labels = [sample.label_id for sample in samples]
    combined: tf.data.Dataset | None = None
    for profile_id in range(4):
        profile = tf.data.Dataset.from_tensor_slices((paths, labels)).map(
            lambda path, label, selected=profile_id: (
                _apply_float_input_contract(
                    _deterministic_environment_profile(
                        decode_and_preprocess(path), selected
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
    return (
        combined.cache()
        .batch(batch_size, drop_remainder=False)
        .prefetch(AUTOTUNE)
    )


def decode_and_preprocess(path: tf.Tensor) -> tf.Tensor:
    """Center-crop and floor-resize before train-only camera perturbations."""

    encoded = tf.io.read_file(path)
    image = tf.io.decode_image(encoded, channels=IMAGE_CHANNELS, expand_animations=False)
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
    """Randomize viewpoint, exposure, white balance and ESP32 sensor effects."""

    image = tf.ensure_shape(image, [IMAGE_SIZE, IMAGE_SIZE, IMAGE_CHANNELS])
    image = tf.image.random_flip_left_right(image)
    image = _random_viewpoint(image)

    # Give clipped ESP32-CAM frames a dedicated, sufficiently frequent branch.
    # The branch is sampled identically for every class by the balanced stream.
    image = tf.cond(
        tf.random.uniform([]) < 0.35,
        lambda: _random_overexposure(
            image,
            gamma_range=(0.58, 0.82),
            gain_range=(1.08, 1.24),
            offset_range=(0.035, 0.095),
            glare_probability=0.55,
        ),
        lambda: _random_general_exposure(image),
    )
    image = tf.image.random_contrast(image, lower=0.65, upper=1.40)
    image = tf.image.random_saturation(image, lower=0.65, upper=1.35)
    image = tf.image.random_hue(image, max_delta=0.06)

    # Explicit warm/cool branches cover the observed ESP32 auto-WB failures.
    image = _random_robust_white_balance(image)
    image = tf.cond(
        tf.random.uniform([]) < 0.45,
        lambda: _random_shadow(image),
        lambda: image,
    )
    image = tf.clip_by_value(image, 0.0, 1.0)

    # Blur and resolution loss approximate focus variation and a QVGA source.
    image = tf.cond(
        tf.random.uniform([]) < 0.25,
        lambda: tf.nn.avg_pool2d(image[None, ...], 3, 1, "SAME")[0],
        lambda: image,
    )
    image = tf.cond(
        tf.random.uniform([]) < 0.30,
        lambda: _random_low_resolution(image),
        lambda: image,
    )
    image = tf.cond(
        tf.random.uniform([]) < 0.55,
        lambda: image
        + tf.random.normal(
            tf.shape(image), stddev=tf.random.uniform([], 0.004, 0.035)
        ),
        lambda: image,
    )
    return _apply_float_input_contract(image)


def augment_calibration(image: tf.Tensor) -> tf.Tensor:
    """Mildly adapt robust features back to the clean camera distribution."""

    image = tf.ensure_shape(image, [IMAGE_SIZE, IMAGE_SIZE, IMAGE_CHANNELS])
    image = tf.image.random_flip_left_right(image)
    image = tf.image.resize_with_crop_or_pad(image, IMAGE_SIZE + 8, IMAGE_SIZE + 8)
    image = tf.image.random_crop(image, [IMAGE_SIZE, IMAGE_SIZE, IMAGE_CHANNELS])
    # Preserve overexposure robustness during clean-camera fine-tuning instead
    # of allowing the mild stage to immediately specialize back to clean light.
    image = tf.cond(
        tf.random.uniform([]) < 0.20,
        lambda: _random_overexposure(
            image,
            gamma_range=(0.70, 0.90),
            gain_range=(1.02, 1.14),
            offset_range=(0.015, 0.055),
            glare_probability=0.25,
        ),
        lambda: _random_calibration_exposure(image),
    )
    image = tf.image.random_contrast(image, 0.82, 1.20)
    image = tf.image.random_saturation(image, 0.82, 1.18)
    image = _random_calibration_white_balance(image)
    image = tf.cond(
        tf.random.uniform([]) < 0.25,
        lambda: image + tf.random.normal(tf.shape(image), stddev=0.010),
        lambda: image,
    )
    return _apply_float_input_contract(image)


def _random_viewpoint(image: tf.Tensor) -> tf.Tensor:
    angle = tf.random.uniform([], -0.436332, 0.436332)  # +/- 25 degrees
    scale = tf.random.uniform([], 0.84, 1.18)
    shear = tf.random.uniform([], -0.12, 0.12)
    translate_x = tf.random.uniform([], -0.10, 0.10) * float(IMAGE_SIZE)
    translate_y = tf.random.uniform([], -0.10, 0.10) * float(IMAGE_SIZE)
    cosine = tf.cos(angle) / scale
    sine = tf.sin(angle) / scale
    a0 = cosine
    a1 = sine + shear
    b0 = -sine
    b1 = cosine
    center = (float(IMAGE_SIZE) - 1.0) / 2.0
    a2 = center - a0 * center - a1 * center - translate_x
    b2 = center - b0 * center - b1 * center - translate_y
    transform = tf.reshape(
        tf.stack([a0, a1, a2, b0, b1, b2, 0.0, 0.0]), [1, 8]
    )
    transformed = tf.raw_ops.ImageProjectiveTransformV3(
        images=image[None, ...],
        transforms=transform,
        output_shape=tf.constant([IMAGE_SIZE, IMAGE_SIZE], dtype=tf.int32),
        interpolation="BILINEAR",
        fill_mode="REFLECT",
        fill_value=0.0,
    )[0]
    return tf.ensure_shape(transformed, [IMAGE_SIZE, IMAGE_SIZE, IMAGE_CHANNELS])


def _random_general_exposure(image: tf.Tensor) -> tf.Tensor:
    """Sample the original broad dark-to-bright V5 exposure distribution."""

    image = tf.image.adjust_gamma(
        tf.clip_by_value(image, 0.0, 1.0),
        tf.random.uniform([], 0.60, 1.60),
        tf.random.uniform([], 0.82, 1.18),
    )
    return tf.image.random_brightness(image, max_delta=0.18)


def _deterministic_environment_profile(
    image: tf.Tensor, profile_id: int
) -> tf.Tensor:
    """Apply one validation-only profile before the firmware input contract."""

    values = tf.clip_by_value(image, 0.0, 1.0)
    if profile_id == 0:  # overexposed
        return tf.clip_by_value(tf.pow(values, 0.72) * 1.16 + 0.055, 0.0, 1.0)
    if profile_id == 1:  # warm cast
        return tf.clip_by_value(values * [1.18, 1.02, 0.78], 0.0, 1.0)
    if profile_id == 2:  # cool cast
        return tf.clip_by_value(values * [0.80, 0.98, 1.18], 0.0, 1.0)
    if profile_id == 3:  # low light
        return tf.clip_by_value(tf.pow(values, 1.55) * 0.72, 0.0, 1.0)
    raise ValueError(f"Unknown deterministic profile id: {profile_id}")


def _random_calibration_exposure(image: tf.Tensor) -> tf.Tensor:
    """Sample the original mild exposure distribution used for fine-tuning."""

    image = tf.image.adjust_gamma(
        tf.clip_by_value(image, 0.0, 1.0),
        tf.random.uniform([], 0.78, 1.28),
        tf.random.uniform([], 0.92, 1.08),
    )
    return tf.image.random_brightness(image, max_delta=0.09)


def _random_robust_white_balance(image: tf.Tensor) -> tf.Tensor:
    selector = tf.random.uniform([])
    return tf.case(
        [
            (
                selector < 0.25,
                lambda: image
                * tf.reshape(
                    tf.stack(
                        [
                            tf.random.uniform([], 1.08, 1.24),
                            tf.random.uniform([], 0.96, 1.07),
                            tf.random.uniform([], 0.72, 0.92),
                        ]
                    ),
                    [1, 1, 3],
                ),
            ),
            (
                selector < 0.50,
                lambda: image
                * tf.reshape(
                    tf.stack(
                        [
                            tf.random.uniform([], 0.72, 0.92),
                            tf.random.uniform([], 0.94, 1.06),
                            tf.random.uniform([], 1.08, 1.24),
                        ]
                    ),
                    [1, 1, 3],
                ),
            ),
        ],
        default=lambda: image * tf.random.uniform([1, 1, 3], 0.82, 1.18),
        exclusive=False,
    )


def _random_calibration_white_balance(image: tf.Tensor) -> tf.Tensor:
    selector = tf.random.uniform([])
    return tf.case(
        [
            (
                selector < 0.15,
                lambda: image
                * tf.constant([[[1.16, 1.02, 0.80]]], dtype=tf.float32),
            ),
            (
                selector < 0.30,
                lambda: image
                * tf.constant([[[0.82, 0.98, 1.16]]], dtype=tf.float32),
            ),
        ],
        default=lambda: image * tf.random.uniform([1, 1, 3], 0.94, 1.06),
        exclusive=False,
    )


def _random_overexposure(
    image: tf.Tensor,
    *,
    gamma_range: tuple[float, float],
    gain_range: tuple[float, float],
    offset_range: tuple[float, float],
    glare_probability: float,
) -> tf.Tensor:
    """Simulate global clipping and optional local glare from an ESP32-CAM."""

    image = tf.image.adjust_gamma(
        tf.clip_by_value(image, 0.0, 1.0),
        tf.random.uniform([], *gamma_range),
        tf.random.uniform([], *gain_range),
    )
    image = image + tf.random.uniform([], *offset_range)
    image = tf.cond(
        tf.random.uniform([]) < glare_probability,
        lambda: _add_random_glare(image),
        lambda: image,
    )
    return tf.clip_by_value(image, 0.0, 1.0)


def _add_random_glare(image: tf.Tensor) -> tf.Tensor:
    """Add a soft highlight that clips part of the object or background."""

    coordinates = tf.linspace(0.0, 1.0, IMAGE_SIZE)
    grid_y, grid_x = tf.meshgrid(coordinates, coordinates, indexing="ij")
    center_x = tf.random.uniform([], 0.12, 0.88)
    center_y = tf.random.uniform([], 0.12, 0.88)
    sigma_x = tf.random.uniform([], 0.16, 0.42)
    sigma_y = tf.random.uniform([], 0.16, 0.42)
    distance = (
        tf.square((grid_x - center_x) / sigma_x)
        + tf.square((grid_y - center_y) / sigma_y)
    )
    mask = tf.exp(-0.5 * distance)[..., None]
    strength = tf.random.uniform([], 0.06, 0.24)
    return image + mask * strength


def _random_shadow(image: tf.Tensor) -> tf.Tensor:
    start = tf.random.uniform([], 0.48, 0.82)
    ramp = tf.linspace(start, 1.0, IMAGE_SIZE)
    ramp = tf.cond(tf.random.uniform([]) < 0.5, lambda: tf.reverse(ramp, [0]), lambda: ramp)
    mask_x = tf.reshape(ramp, [1, IMAGE_SIZE, 1])
    mask_y = tf.reshape(ramp, [IMAGE_SIZE, 1, 1])
    mask = tf.cond(tf.random.uniform([]) < 0.5, lambda: mask_x, lambda: mask_y)
    return image * mask


def _random_low_resolution(image: tf.Tensor) -> tf.Tensor:
    side = tf.random.uniform([], 54, 85, dtype=tf.int32)
    small = tf.image.resize(image, [side, side], method="area", antialias=True)
    return tf.image.resize(small, [IMAGE_SIZE, IMAGE_SIZE], method="nearest")


def _apply_float_input_contract(image: tf.Tensor) -> tf.Tensor:
    """Quantize augmented camera data exactly as the ESP32 input path does."""

    pixels = tf.cast(
        tf.round(tf.clip_by_value(image, 0.0, 1.0) * 255.0), tf.uint8
    )
    contracted = apply_input_contract_u8(pixels)
    return tf.ensure_shape(
        tf.cast(contracted, tf.float32) / 255.0,
        [IMAGE_SIZE, IMAGE_SIZE, IMAGE_CHANNELS],
    )
