from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath
import random
import zipfile

import cv2
import numpy as np


LABELS = {"paper": 0, "plastic": 1}
ID_TO_LABEL = {label_id: name for name, label_id in LABELS.items()}
OTHER_LABEL = 2
THREE_WAY_LABELS = {0: "paper", 1: "plastic", 2: "other"}

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
TRASHNET_ID_TO_CLASS = {
    1: "glass",
    2: "paper",
    3: "cardboard",
    4: "plastic",
    5: "metal",
    6: "trash",
}


@dataclass(frozen=True)
class ImageSample:
    name: str
    label: int
    class_name: str
    split: str
    path: Path | None = None
    zip_path: Path | None = None
    zip_member: str | None = None


@dataclass(frozen=True)
class DatasetSplits:
    train_known: list[ImageSample]
    validation_known: list[ImageSample]
    test_known: list[ImageSample]
    validation_other: list[ImageSample]
    test_other: list[ImageSample]
    source: str

    def manifest(self) -> dict:
        return {
            "source": self.source,
            "train_known": summarize_samples(self.train_known),
            "validation_known": summarize_samples(self.validation_known),
            "test_known": summarize_samples(self.test_known),
            "validation_other": summarize_samples(self.validation_other),
            "test_other": summarize_samples(self.test_other),
        }


def summarize_samples(samples: list[ImageSample]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for sample in samples:
        counts[sample.class_name] = counts.get(sample.class_name, 0) + 1
    counts["total"] = len(samples)
    return counts


def resolve_data_path(data: str | Path) -> Path:
    path = Path(data)
    if path.exists():
        return path

    ai_relative = Path("AI") / path
    if ai_relative.exists():
        return ai_relative

    raise FileNotFoundError(f"Dataset path not found: {data}")


def load_dataset_splits(data: str | Path, seed: int = 42) -> DatasetSplits:
    path = resolve_data_path(data)
    if path.is_dir() and (path / "train").is_dir():
        return _load_explicit_layout(path)

    zip_path, manifest_dir = _resolve_trashnet_zip(path)
    if zip_path is not None:
        split_files = {
            "train": manifest_dir / "one-indexed-files-notrash_train.txt",
            "validation": manifest_dir / "one-indexed-files-notrash_val.txt",
            "test": manifest_dir / "one-indexed-files-notrash_test.txt",
        }
        if all(split_file.is_file() for split_file in split_files.values()):
            return _load_trashnet_manifest(zip_path, split_files)
        return _split_zip_without_manifest(zip_path, seed)

    if path.is_dir():
        return _split_class_directory(path, seed)

    raise ValueError(f"Unsupported dataset layout: {path}")


def load_images(
    samples: list[ImageSample],
    image_size: int,
    *,
    dtype: np.dtype = np.float32,
    verbose: bool = False,
) -> tuple[np.ndarray, np.ndarray, list[str]]:
    images: list[np.ndarray] = []
    labels: list[int] = []
    skipped: list[str] = []

    file_samples = [sample for sample in samples if sample.path is not None]
    for index, sample in enumerate(file_samples, start=1):
        try:
            images.append(preprocess_image(read_image(sample.path), image_size))
            labels.append(sample.label)
        except Exception as exc:  # pragma: no cover - defensive for corrupt data
            skipped.append(f"{sample.name}: {exc}")
        if verbose and (index % 100 == 0 or index == len(file_samples)):
            print(f"Loaded file images {index}/{len(file_samples)}")

    by_zip: dict[Path, list[ImageSample]] = {}
    for sample in samples:
        if sample.zip_path is not None:
            by_zip.setdefault(sample.zip_path, []).append(sample)

    for zip_path, zip_samples in by_zip.items():
        with zipfile.ZipFile(zip_path) as archive:
            for index, sample in enumerate(zip_samples, start=1):
                try:
                    if sample.zip_member is None:
                        raise RuntimeError(f"Invalid ZIP sample: {sample.name}")
                    encoded = archive.read(sample.zip_member)
                    images.append(preprocess_encoded_image(encoded, image_size))
                    labels.append(sample.label)
                except Exception as exc:  # pragma: no cover - defensive
                    skipped.append(f"{sample.name}: {exc}")
                if verbose and (index % 100 == 0 or index == len(zip_samples)):
                    print(f"Loaded ZIP images {index}/{len(zip_samples)}")

    if not images:
        raise RuntimeError("No images could be decoded")

    return (
        np.stack(images).astype(dtype),
        np.asarray(labels, dtype=np.int64),
        skipped,
    )


def read_image(path: str | Path) -> np.ndarray:
    image = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError(f"Cannot decode image: {path}")
    return image


def preprocess_encoded_image(encoded: bytes, image_size: int) -> np.ndarray:
    buffer = np.frombuffer(encoded, dtype=np.uint8)
    image = cv2.imdecode(buffer, cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("Cannot decode image bytes")
    return preprocess_image(image, image_size)


def preprocess_image(image_bgr: np.ndarray, image_size: int) -> np.ndarray:
    if image_bgr.ndim != 3 or image_bgr.shape[2] != 3:
        raise ValueError("Expected a 3-channel BGR image")

    cropped = center_crop_square(image_bgr)
    resized = cv2.resize(cropped, (image_size, image_size), interpolation=cv2.INTER_AREA)
    rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
    return rgb.astype(np.float32) / 255.0


def center_crop_square(image: np.ndarray) -> np.ndarray:
    height, width = image.shape[:2]
    size = min(height, width)
    y0 = (height - size) // 2
    x0 = (width - size) // 2
    return image[y0 : y0 + size, x0 : x0 + size]


def make_tf_dataset(
    x: np.ndarray,
    y: np.ndarray,
    batch_size: int,
    *,
    shuffle: bool,
    augment: bool,
    seed: int,
):
    import tensorflow as tf

    ds = tf.data.Dataset.from_tensor_slices((x, y))
    if shuffle:
        ds = ds.shuffle(len(x), seed=seed, reshuffle_each_iteration=True)

    if augment:
        image_size = int(x.shape[1])

        def augment_sample(image, label):
            padded = tf.image.resize_with_crop_or_pad(
                image, image_size + 10, image_size + 10
            )
            image = tf.image.random_crop(
                padded, size=[image_size, image_size, 3], seed=seed
            )
            image = tf.image.random_flip_left_right(image, seed=seed)
            image = tf.image.random_brightness(image, max_delta=0.18, seed=seed)
            image = tf.image.random_contrast(image, lower=0.82, upper=1.18, seed=seed)
            return tf.clip_by_value(image, 0.0, 1.0), label

        ds = ds.map(augment_sample, num_parallel_calls=tf.data.AUTOTUNE)

    return ds.batch(batch_size).prefetch(tf.data.AUTOTUNE)


def samples_from_class_dirs(
    root: str | Path,
    *,
    split: str,
    include_known: bool = True,
    include_other: bool = True,
) -> list[ImageSample]:
    root_path = resolve_data_path(root)
    samples: list[ImageSample] = []

    class_labels = dict(LABELS)
    if include_other:
        class_labels["other"] = OTHER_LABEL

    for class_name, label in class_labels.items():
        if not include_known and class_name in LABELS:
            continue
        class_dir = root_path / class_name
        if not class_dir.is_dir():
            continue
        for image_path in sorted(class_dir.rglob("*")):
            if image_path.is_file() and image_path.suffix.lower() in IMAGE_EXTENSIONS:
                samples.append(
                    ImageSample(
                        name=str(image_path),
                        label=label,
                        class_name=class_name,
                        split=split,
                        path=image_path,
                    )
                )
    return samples


def _load_explicit_layout(path: Path) -> DatasetSplits:
    train_known = samples_from_class_dirs(
        path / "train", split="train", include_known=True, include_other=False
    )
    validation_known = samples_from_class_dirs(
        path / "validation_known",
        split="validation",
        include_known=True,
        include_other=False,
    )
    test_known = samples_from_class_dirs(
        path / "test", split="test", include_known=True, include_other=False
    )
    validation_other = samples_from_class_dirs(
        path / "validation_other",
        split="validation",
        include_known=False,
        include_other=True,
    )
    test_other = samples_from_class_dirs(
        path / "test", split="test", include_known=False, include_other=True
    )

    if not test_known:
        test_known = validation_known
    if not validation_known:
        validation_known = test_known

    return DatasetSplits(
        train_known=train_known,
        validation_known=validation_known,
        test_known=test_known,
        validation_other=validation_other,
        test_other=test_other,
        source=str(path),
    )


def _resolve_trashnet_zip(path: Path) -> tuple[Path | None, Path]:
    if path.is_file() and zipfile.is_zipfile(path):
        return path, path.parent

    if path.is_dir():
        direct_zip = path / "dataset-resized.zip"
        if direct_zip.is_file():
            return direct_zip, path

        nested_zip = path / "data" / "dataset-resized.zip"
        if nested_zip.is_file():
            return nested_zip, nested_zip.parent

    return None, path


def _load_trashnet_manifest(
    zip_path: Path,
    split_files: dict[str, Path],
) -> DatasetSplits:
    member_index = _build_zip_member_index(zip_path)

    split_samples = {
        "train_known": [],
        "validation_known": [],
        "test_known": [],
        "validation_other": [],
        "test_other": [],
    }

    for split_name, split_file in split_files.items():
        for image_name, class_id in _read_split_file(split_file):
            class_name = TRASHNET_ID_TO_CLASS[class_id]
            zip_member = member_index.get(image_name)
            if zip_member is None:
                raise FileNotFoundError(f"{image_name} not found inside {zip_path}")

            if class_name in LABELS:
                label = LABELS[class_name]
                bucket = f"{split_name}_known"
            else:
                label = OTHER_LABEL
                bucket = "validation_other" if split_name == "validation" else "test_other"
                if split_name == "train":
                    continue

            split_samples[bucket].append(
                ImageSample(
                    name=image_name,
                    label=label,
                    class_name=class_name if class_name in LABELS else "other",
                    split=split_name,
                    zip_path=zip_path,
                    zip_member=zip_member,
                )
            )

    return DatasetSplits(
        train_known=split_samples["train_known"],
        validation_known=split_samples["validation_known"],
        test_known=split_samples["test_known"],
        validation_other=split_samples["validation_other"],
        test_other=split_samples["test_other"],
        source=str(zip_path),
    )


def _split_zip_without_manifest(zip_path: Path, seed: int) -> DatasetSplits:
    by_class = _collect_zip_by_class(zip_path)
    return _make_random_splits(by_class, seed, source=str(zip_path))


def _split_class_directory(path: Path, seed: int) -> DatasetSplits:
    by_class: dict[str, list[ImageSample]] = {class_name: [] for class_name in LABELS}
    by_class["other"] = []

    for class_name, label in {**LABELS, "other": OTHER_LABEL}.items():
        class_dir = path / class_name
        if not class_dir.is_dir():
            continue
        for image_path in sorted(class_dir.rglob("*")):
            if image_path.is_file() and image_path.suffix.lower() in IMAGE_EXTENSIONS:
                by_class[class_name].append(
                    ImageSample(
                        name=str(image_path),
                        label=label,
                        class_name=class_name,
                        split="all",
                        path=image_path,
                    )
                )

    return _make_random_splits(by_class, seed, source=str(path))


def _make_random_splits(
    by_class: dict[str, list[ImageSample]],
    seed: int,
    *,
    source: str,
) -> DatasetSplits:
    rng = random.Random(seed)
    train_known: list[ImageSample] = []
    validation_known: list[ImageSample] = []
    test_known: list[ImageSample] = []
    validation_other: list[ImageSample] = []
    test_other: list[ImageSample] = []

    for class_name in LABELS:
        samples = list(by_class.get(class_name, []))
        rng.shuffle(samples)
        if len(samples) < 10:
            raise RuntimeError(f"Class '{class_name}' needs at least 10 images")
        n_test = max(1, int(round(len(samples) * 0.15)))
        n_val = max(1, int(round(len(samples) * 0.15)))
        test_known.extend(_with_split(samples[:n_test], "test"))
        validation_known.extend(_with_split(samples[n_test : n_test + n_val], "validation"))
        train_known.extend(_with_split(samples[n_test + n_val :], "train"))

    other_samples = list(by_class.get("other", []))
    rng.shuffle(other_samples)
    if other_samples:
        midpoint = max(1, len(other_samples) // 2)
        validation_other = _with_split(other_samples[:midpoint], "validation")
        test_other = _with_split(other_samples[midpoint:], "test")

    rng.shuffle(train_known)
    rng.shuffle(validation_known)
    rng.shuffle(test_known)
    rng.shuffle(validation_other)
    rng.shuffle(test_other)

    return DatasetSplits(
        train_known=train_known,
        validation_known=validation_known,
        test_known=test_known,
        validation_other=validation_other,
        test_other=test_other,
        source=source,
    )


def _with_split(samples: list[ImageSample], split: str) -> list[ImageSample]:
    return [
        ImageSample(
            name=sample.name,
            label=sample.label,
            class_name=sample.class_name,
            split=split,
            path=sample.path,
            zip_path=sample.zip_path,
            zip_member=sample.zip_member,
        )
        for sample in samples
    ]


def _collect_zip_by_class(zip_path: Path) -> dict[str, list[ImageSample]]:
    result: dict[str, list[ImageSample]] = {class_name: [] for class_name in LABELS}
    result["other"] = []
    with zipfile.ZipFile(zip_path) as archive:
        for member in sorted(archive.namelist()):
            member_path = PurePosixPath(member)
            if member_path.suffix.lower() not in IMAGE_EXTENSIONS:
                continue
            class_name = member_path.parent.name.lower()
            if class_name in LABELS:
                label = LABELS[class_name]
                bucket = class_name
            elif class_name in TRASHNET_ID_TO_CLASS.values():
                label = OTHER_LABEL
                bucket = "other"
            else:
                continue
            result[bucket].append(
                ImageSample(
                    name=member_path.name,
                    label=label,
                    class_name=bucket,
                    split="all",
                    zip_path=zip_path,
                    zip_member=member,
                )
            )
    return result


def _build_zip_member_index(zip_path: Path) -> dict[str, str]:
    member_index: dict[str, str] = {}
    with zipfile.ZipFile(zip_path) as archive:
        for member in archive.namelist():
            member_path = PurePosixPath(member)
            if member_path.suffix.lower() in IMAGE_EXTENSIONS:
                member_index[member_path.name] = member
    return member_index


def _read_split_file(path: Path) -> list[tuple[str, int]]:
    rows: list[tuple[str, int]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        image_name, class_id = line.split()
        rows.append((image_name, int(class_id)))
    return rows
