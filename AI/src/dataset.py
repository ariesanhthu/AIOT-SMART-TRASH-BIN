from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Iterator
from pathlib import Path, PurePosixPath
import random
import zipfile


LABELS = {"paper": 0, "plastic": 1}
ID_TO_LABEL = {label_id: name for name, label_id in LABELS.items()}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


@dataclass(frozen=True)
class ImageSample:
    name: str
    label: int
    path: Path | None = None
    zip_member: str | None = None


class TrashNetDataset:
    """Read the two required TrashNet classes from a directory or ZIP file."""

    def __init__(self, source: str | Path):
        self.source = Path(source)
        if not self.source.exists():
            raise FileNotFoundError(f"Dataset not found: {self.source}")
        self.is_zip = self.source.is_file() and zipfile.is_zipfile(self.source)
        if self.source.is_file() and not self.is_zip:
            raise ValueError(f"Dataset file is not a ZIP archive: {self.source}")

    def collect(
        self,
        max_per_class: int | None = None,
        seed: int = 42,
    ) -> list[ImageSample]:
        if max_per_class is not None and max_per_class < 10:
            raise ValueError("--max-per-class must be at least 10")

        by_class = self._collect_from_zip() if self.is_zip else self._collect_from_dir()
        rng = random.Random(seed)
        samples: list[ImageSample] = []

        for class_name in LABELS:
            class_samples = sorted(by_class[class_name], key=lambda item: item.name)
            rng.shuffle(class_samples)
            if max_per_class is not None:
                class_samples = class_samples[:max_per_class]
            if len(class_samples) < 10:
                raise RuntimeError(
                    f"Class '{class_name}' needs at least 10 readable candidates; "
                    f"found {len(class_samples)}"
                )
            samples.extend(class_samples)

        rng.shuffle(samples)
        return samples

    def iter_encoded(
        self, samples: list[ImageSample]
    ) -> Iterator[tuple[ImageSample, bytes]]:
        """Yield encoded images while opening a ZIP archive only once."""
        if not self.is_zip:
            for sample in samples:
                if sample.path is None:
                    raise RuntimeError(f"Invalid directory sample: {sample}")
                yield sample, sample.path.read_bytes()
            return

        with zipfile.ZipFile(self.source) as archive:
            for sample in samples:
                if sample.zip_member is None:
                    raise RuntimeError(f"Invalid ZIP sample: {sample}")
                yield sample, archive.read(sample.zip_member)

    def _collect_from_zip(self) -> dict[str, list[ImageSample]]:
        result = {name: [] for name in LABELS}
        with zipfile.ZipFile(self.source) as archive:
            for member in archive.namelist():
                member_path = PurePosixPath(member)
                if member_path.suffix.lower() not in IMAGE_EXTENSIONS:
                    continue
                class_name = member_path.parent.name.lower()
                if class_name in LABELS:
                    result[class_name].append(
                        ImageSample(
                            name=member,
                            label=LABELS[class_name],
                            zip_member=member,
                        )
                    )
        return result

    def _collect_from_dir(self) -> dict[str, list[ImageSample]]:
        result = {name: [] for name in LABELS}
        roots = [self.source, self.source / "dataset-resized"]

        for class_name, label_id in LABELS.items():
            class_dir = next(
                (root / class_name for root in roots if (root / class_name).is_dir()),
                None,
            )
            if class_dir is None:
                raise FileNotFoundError(
                    f"Missing class folder '{class_name}' under {self.source}"
                )
            for image_path in class_dir.rglob("*"):
                if image_path.is_file() and image_path.suffix.lower() in IMAGE_EXTENSIONS:
                    result[class_name].append(
                        ImageSample(
                            name=str(image_path), label=label_id, path=image_path
                        )
                    )
        return result
