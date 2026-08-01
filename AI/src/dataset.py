"""Strict, streaming dataset loader shared by training and deployment checks."""

from __future__ import annotations

import csv
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path, PurePosixPath
import random
from typing import Any, Sequence

import numpy as np
import tensorflow as tf

try:
    from .config import (
        CLASS_TO_INDEX,
        IMAGE_CHANNELS,
        IMAGE_EXTENSIONS,
        IMAGE_SIZE,
        LABELS,
        LUMINANCE_NORMALIZATION,
        RGB565_INPUT,
        SPLITS,
        resolve_input_path,
    )
except ImportError:
    from config import (  # type: ignore
        CLASS_TO_INDEX,
        IMAGE_CHANNELS,
        IMAGE_EXTENSIONS,
        IMAGE_SIZE,
        LABELS,
        LUMINANCE_NORMALIZATION,
        RGB565_INPUT,
        SPLITS,
        resolve_input_path,
    )


MANIFEST_COLUMNS = {
    "relative_path",
    "split",
    "label",
    "label_id",
    "source",
    "source_sha256",
    "output_sha256",
    "width",
    "height",
}


@dataclass(frozen=True)
class ImageSample:
    path: Path
    relative_path: str
    split: str
    label: str
    label_id: int
    sha256: str | None = None


@dataclass(frozen=True)
class DatasetIndex:
    root: Path
    samples: tuple[ImageSample, ...]
    dataset_sha256: str
    manifest_path: Path | None

    def for_split(self, split: str) -> tuple[ImageSample, ...]:
        if split not in SPLITS:
            raise ValueError(f"Unknown split '{split}'; expected one of {SPLITS}")
        return tuple(sample for sample in self.samples if sample.split == split)

    def counts(self) -> dict[str, dict[str, int]]:
        result: dict[str, dict[str, int]] = {}
        for split in SPLITS:
            per_class = {
                label: sum(
                    sample.split == split and sample.label == label
                    for sample in self.samples
                )
                for label in LABELS
            }
            per_class["total"] = sum(per_class.values())
            result[split] = per_class
        return result

    def summary(self) -> dict[str, Any]:
        return {
            "root": str(self.root),
            "dataset_sha256": self.dataset_sha256,
            "manifest": str(self.manifest_path) if self.manifest_path else None,
            "counts": self.counts(),
            "total": len(self.samples),
        }


def load_dataset_index(data: str | Path) -> DatasetIndex:
    root = resolve_input_path(data)
    if not root.is_dir():
        raise NotADirectoryError(f"Dataset root is not a directory: {root}")
    _validate_exact_layout(root)

    manifest_path = root / "manifest.csv"
    if manifest_path.is_file():
        samples = _read_manifest(root, manifest_path)
        fingerprint = _validate_manifest_fingerprint(root, manifest_path)
        _validate_manifest_covers_images(root, samples)
        _validate_manifest_image_hashes(samples)
    else:
        samples = _scan_layout(root)
        fingerprint = _fingerprint_scanned_samples(root, samples)
        manifest_path = None

    _validate_counts(samples)
    return DatasetIndex(
        root=root,
        samples=tuple(samples),
        dataset_sha256=fingerprint,
        manifest_path=manifest_path,
    )


def make_dataset(
    samples: Sequence[ImageSample],
    *,
    batch_size: int,
    training: bool,
    seed: int,
    augment: bool | None = None,
) -> tf.data.Dataset:
    if not samples:
        raise ValueError("Cannot build a dataset from zero samples")
    if batch_size < 1:
        raise ValueError("batch_size must be positive")

    if augment is None:
        augment = training
    if augment and not training:
        raise ValueError("Augmentation is only valid for a training dataset")

    paths = [str(sample.path) for sample in samples]
    labels = [sample.label_id for sample in samples]
    dataset = tf.data.Dataset.from_tensor_slices((paths, labels))
    if training:
        dataset = dataset.shuffle(
            buffer_size=min(len(samples), 4096),
            seed=seed,
            reshuffle_each_iteration=True,
        )
    dataset = dataset.map(
        lambda path, label: (_decode_and_preprocess(path), label),
        num_parallel_calls=tf.data.AUTOTUNE,
        deterministic=not training,
    )
    if augment:
        dataset = dataset.map(
            lambda image, label: (_augment(image), label),
            num_parallel_calls=tf.data.AUTOTUNE,
            deterministic=False,
        )

    options = tf.data.Options()
    options.experimental_deterministic = not training
    dataset = dataset.with_options(options)
    return dataset.batch(batch_size, drop_remainder=False).prefetch(tf.data.AUTOTUNE)


def preprocess_file(path: str | Path) -> np.ndarray:
    """Return one firmware-contract RGB float32 image with shape ``96x96x3``."""

    resolved = resolve_input_path(path)
    tensor = _decode_and_preprocess(tf.constant(str(resolved)))
    return tensor.numpy().astype(np.float32, copy=False)


def preprocess_file_raw(path: str | Path) -> np.ndarray:
    """Return center-cropped/resized RGB without the deployment input contract."""

    resolved = resolve_input_path(path)
    encoded = tf.io.read_file(tf.constant(str(resolved)))
    decoded = tf.io.decode_image(
        encoded, channels=IMAGE_CHANNELS, expand_animations=False
    )
    tensor = _preprocess_decoded(decoded, apply_contract=False)
    return tensor.numpy().astype(np.float32, copy=False)


def preprocess_encoded(encoded: bytes) -> np.ndarray:
    tensor = _preprocess_decoded(
        tf.io.decode_image(encoded, channels=IMAGE_CHANNELS, expand_animations=False)
    )
    return tensor.numpy().astype(np.float32, copy=False)


def compute_class_weights(samples: Sequence[ImageSample]) -> dict[int, float]:
    """Return normalized inverse-frequency weights for balanced class recall."""

    counts = np.asarray(
        [sum(sample.label_id == index for sample in samples) for index in range(len(LABELS))],
        dtype=np.float64,
    )
    if np.any(counts == 0):
        raise ValueError(f"Cannot compute class weights with zero counts: {counts.tolist()}")
    inverse = counts.sum() / (len(LABELS) * counts)
    inverse /= np.mean(inverse)
    inverse = np.clip(inverse, 0.75, 1.35)
    return {index: float(weight) for index, weight in enumerate(inverse)}


def stratified_representative_samples(
    index: DatasetIndex,
    *,
    per_class: int,
    seed: int,
) -> tuple[ImageSample, ...]:
    if per_class < 1:
        raise ValueError("per_class must be positive")
    rng = random.Random(seed)
    train = index.for_split("train")
    selected: list[ImageSample] = []
    for label_id, label in enumerate(LABELS):
        candidates = [sample for sample in train if sample.label_id == label_id]
        if not candidates:
            raise ValueError(f"Representative data has no training images for '{label}'")
        rng.shuffle(candidates)
        selected.extend(candidates[: min(per_class, len(candidates))])
    rng.shuffle(selected)
    return tuple(selected)


def _decode_and_preprocess(path: tf.Tensor) -> tf.Tensor:
    encoded = tf.io.read_file(path)
    decoded = tf.io.decode_image(
        encoded, channels=IMAGE_CHANNELS, expand_animations=False
    )
    return _preprocess_decoded(decoded)


def _preprocess_decoded(
    image: tf.Tensor, *, apply_contract: bool = True
) -> tf.Tensor:
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

    # Explicit floor mapping is intentional: the ESP32 implementation can reproduce it
    # exactly with integer pointer arithmetic and no interpolation scratch buffer.
    indices = tf.math.floordiv(
        tf.range(IMAGE_SIZE, dtype=tf.int32) * square_size,
        IMAGE_SIZE,
    )
    indices = tf.minimum(indices, square_size - 1)
    resized = tf.gather(tf.gather(square, indices, axis=0), indices, axis=1)
    resized.set_shape([IMAGE_SIZE, IMAGE_SIZE, IMAGE_CHANNELS])
    if apply_contract:
        resized = apply_input_contract_u8(resized)
    return tf.image.convert_image_dtype(resized, tf.float32)


def apply_input_contract_u8(image: tf.Tensor) -> tf.Tensor:
    """Apply configured sensor quantization and exposure normalization."""

    result = tf.cast(image, tf.uint8)
    if RGB565_INPUT:
        result = simulate_rgb565_u8(result)
    if LUMINANCE_NORMALIZATION:
        result = normalize_luminance_u8(result)
    return tf.ensure_shape(result, [IMAGE_SIZE, IMAGE_SIZE, IMAGE_CHANNELS])


def simulate_rgb565_u8(image: tf.Tensor) -> tf.Tensor:
    """Match ESP32 RGB565 expansion: R/B multiples of 8, G multiples of 4."""

    pixels = tf.cast(image, tf.int32)
    steps = tf.constant([8, 4, 8], dtype=tf.int32)
    quantized = (pixels // steps) * steps
    return tf.ensure_shape(
        tf.cast(quantized, tf.uint8), [IMAGE_SIZE, IMAGE_SIZE, IMAGE_CHANNELS]
    )


def normalize_luminance_u8(image: tf.Tensor) -> tf.Tensor:
    """Apply the configured bounded integer luminance normalization.

    Images whose mean luma is already in [96, 160] are unchanged. Outside that dead-band a
    single RGB gain moves the mean toward the nearest edge, capped to
    [0.75, 1.332] in Q8 fixed point so noise and clipped colors are not
    amplified aggressively.
    """

    pixels = tf.cast(image, tf.int32)
    luma = (
        77 * pixels[..., 0]
        + 150 * pixels[..., 1]
        + 29 * pixels[..., 2]
        + 128
    ) // 256
    pixel_count = tf.size(luma, out_type=tf.int32)
    mean_luma = (tf.reduce_sum(luma) + pixel_count // 2) // pixel_count
    safe_mean = tf.maximum(mean_luma, 1)
    brighten_gain = tf.minimum(
        341, (96 * 256 + safe_mean // 2) // safe_mean
    )
    darken_gain = tf.maximum(
        192, (160 * 256 + safe_mean // 2) // safe_mean
    )
    gain_q8 = tf.where(
        mean_luma < 96,
        brighten_gain,
        tf.where(mean_luma > 160, darken_gain, tf.constant(256, tf.int32)),
    )
    normalized = tf.clip_by_value((pixels * gain_q8 + 128) // 256, 0, 255)
    return tf.ensure_shape(
        tf.cast(normalized, tf.uint8), [IMAGE_SIZE, IMAGE_SIZE, IMAGE_CHANNELS]
    )


def _augment(image: tf.Tensor) -> tf.Tensor:
    padded = tf.image.resize_with_crop_or_pad(image, IMAGE_SIZE + 10, IMAGE_SIZE + 10)
    image = tf.image.random_crop(
        padded,
        size=[IMAGE_SIZE, IMAGE_SIZE, IMAGE_CHANNELS],
    )
    image = tf.image.random_flip_left_right(image)
    image = tf.image.random_brightness(image, max_delta=0.12)
    image = tf.image.random_contrast(image, lower=0.88, upper=1.12)
    return tf.clip_by_value(image, 0.0, 1.0)


def _validate_exact_layout(root: Path) -> None:
    root_children = {child.name: child for child in root.iterdir() if child.is_dir()}
    for split in SPLITS:
        split_dir = root_children.get(split)
        if split_dir is None:
            raise FileNotFoundError(
                f"Missing lowercase split directory '{split}' under {root}"
            )
        class_dirs = {child.name: child for child in split_dir.iterdir() if child.is_dir()}
        for label in LABELS:
            if label not in class_dirs:
                raise FileNotFoundError(
                    f"Missing lowercase class directory '{split}/{label}' under {root}"
                )


def _read_manifest(root: Path, manifest_path: Path) -> list[ImageSample]:
    samples: list[ImageSample] = []
    seen_paths: set[str] = set()
    with manifest_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fields = set(reader.fieldnames or [])
        missing = MANIFEST_COLUMNS - fields
        if missing:
            raise ValueError(f"Dataset manifest is missing columns: {sorted(missing)}")
        for line_number, row in enumerate(reader, start=2):
            relative = PurePosixPath(row["relative_path"].strip())
            if relative.is_absolute() or ".." in relative.parts:
                raise ValueError(f"Unsafe relative_path at manifest line {line_number}")
            split = row["split"].strip()
            label = row["label"].strip()
            try:
                label_id = int(row["label_id"])
            except ValueError as exc:
                raise ValueError(f"Invalid label_id at manifest line {line_number}") from exc
            if split not in SPLITS or label not in LABELS:
                raise ValueError(f"Invalid split/label at manifest line {line_number}")
            if label_id != CLASS_TO_INDEX[label]:
                raise ValueError(f"label_id mismatch at manifest line {line_number}")
            if len(relative.parts) < 3 or relative.parts[:2] != (split, label):
                raise ValueError(
                    f"relative_path must start with '{split}/{label}/' at line {line_number}"
                )
            normalized = relative.as_posix()
            if normalized in seen_paths:
                raise ValueError(f"Duplicate relative_path in manifest: {normalized}")
            seen_paths.add(normalized)
            path = root.joinpath(*relative.parts)
            if not path.is_file():
                raise FileNotFoundError(f"Manifest image not found: {path}")
            if path.suffix.lower() not in IMAGE_EXTENSIONS:
                raise ValueError(f"Unsupported image extension in manifest: {path}")
            output_sha256 = row["output_sha256"].strip().lower()
            if len(output_sha256) != 64 or any(
                character not in "0123456789abcdef" for character in output_sha256
            ):
                raise ValueError(f"Invalid output_sha256 at manifest line {line_number}")
            samples.append(
                ImageSample(
                    path=path,
                    relative_path=normalized,
                    split=split,
                    label=label,
                    label_id=label_id,
                    sha256=output_sha256,
                )
            )
    return samples


def _scan_layout(root: Path) -> list[ImageSample]:
    samples: list[ImageSample] = []
    for split in SPLITS:
        for label in LABELS:
            class_dir = root / split / label
            for path in sorted(class_dir.rglob("*")):
                if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS:
                    samples.append(
                        ImageSample(
                            path=path,
                            relative_path=path.relative_to(root).as_posix(),
                            split=split,
                            label=label,
                            label_id=CLASS_TO_INDEX[label],
                        )
                    )
    return samples


def _validate_manifest_covers_images(
    root: Path, samples: Sequence[ImageSample]
) -> None:
    indexed = {sample.relative_path for sample in samples}
    discovered = {
        path.relative_to(root).as_posix()
        for split in SPLITS
        for label in LABELS
        for path in (root / split / label).rglob("*")
        if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
    }
    missing = sorted(discovered - indexed)
    extra = sorted(indexed - discovered)
    if missing or extra:
        raise ValueError(
            "manifest.csv does not exactly cover dataset images; "
            f"unindexed={missing[:5]}, missing_files={extra[:5]}"
        )


def _validate_manifest_image_hashes(samples: Sequence[ImageSample]) -> None:
    seen: dict[str, str] = {}
    for sample in samples:
        if sample.sha256 is None:
            raise ValueError(f"Manifest sample has no SHA256: {sample.relative_path}")
        digest = hashlib.sha256()
        with sample.path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        actual = digest.hexdigest()
        if actual != sample.sha256:
            raise ValueError(
                f"Image SHA256 mismatch for {sample.relative_path}: "
                f"manifest={sample.sha256}, actual={actual}"
            )
        duplicate = seen.get(actual)
        if duplicate is not None:
            raise ValueError(
                f"Duplicate image content in canonical dataset: "
                f"{duplicate} and {sample.relative_path}"
            )
        seen[actual] = sample.relative_path


def _validate_manifest_fingerprint(root: Path, manifest_path: Path) -> str:
    fingerprint = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    stats_path = root / "stats.json"
    if stats_path.is_file():
        stats = json.loads(stats_path.read_text(encoding="utf-8"))
        expected = stats.get("dataset_sha256")
        if expected and expected != fingerprint:
            raise ValueError(
                "Dataset manifest SHA256 does not match stats.json: "
                f"expected={expected}, actual={fingerprint}"
            )
    return fingerprint


def _fingerprint_scanned_samples(
    root: Path, samples: Sequence[ImageSample]
) -> str:
    digest = hashlib.sha256()
    for sample in samples:
        stat = sample.path.stat()
        digest.update(sample.relative_path.encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(stat.st_size).encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def _validate_counts(samples: Sequence[ImageSample]) -> None:
    for split in SPLITS:
        for label in LABELS:
            count = sum(
                sample.split == split and sample.label == label for sample in samples
            )
            if count == 0:
                raise ValueError(f"Dataset split '{split}/{label}' is empty")
