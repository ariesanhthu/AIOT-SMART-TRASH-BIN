"""Shared, deployment-facing configuration for the three-class classifier."""

from __future__ import annotations

from pathlib import Path


AI_DIR = Path(__file__).resolve().parents[1]
REPOSITORY_DIR = AI_DIR.parent

LABELS: tuple[str, ...] = ("paper", "plastic", "organic")
CLASS_TO_INDEX = {label: index for index, label in enumerate(LABELS)}
INDEX_TO_CLASS = {index: label for label, index in CLASS_TO_INDEX.items()}

SPLITS: tuple[str, ...] = ("train", "validation", "test")
IMAGE_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png"})

IMAGE_SIZE = 96
IMAGE_CHANNELS = 3
INPUT_SHAPE = (IMAGE_SIZE, IMAGE_SIZE, IMAGE_CHANNELS)
MODEL_VERSION = "tinycnn-v2-3class"
METADATA_SCHEMA_VERSION = 1
LUMINANCE_NORMALIZATION = False
RGB565_INPUT = False

DEFAULT_DATA_DIR = AI_DIR / "DATASET"
DEFAULT_ARTIFACT_DIR = AI_DIR / "artifacts"
DEFAULT_FLOAT_MODEL = DEFAULT_ARTIFACT_DIR / "model_float.keras"
DEFAULT_INT8_MODEL = DEFAULT_ARTIFACT_DIR / "model_int8.tflite"
DEFAULT_METADATA = DEFAULT_ARTIFACT_DIR / "model_metadata.json"
DEFAULT_FIRMWARE_MODEL_DIR = AI_DIR / "esp32" / "main" / "model"

# These are deliberately conservative for a small ESP32/TFLite Micro model.
MAX_TFLITE_SIZE_BYTES = 256 * 1024
MAX_INT8_ACCURACY_DROP = 0.03
MIN_FLOAT_INT8_AGREEMENT = 0.95
MIN_INT8_MACRO_F1 = 0.80
MIN_INT8_CLASS_RECALL = 0.80

PREPROCESSING_SPEC = {
    "color_space": "RGB",
    "crop": "center_square",
    "resize": "nearest_neighbor_floor",
    "resize_mapping": "source_index=(destination_index*source_size)//96",
    "normalization": "pixel/255.0",
    "input_range": [0.0, 1.0],
}


def resolve_input_path(value: str | Path) -> Path:
    """Resolve a CLI input consistently from either the repository or AI folder."""

    raw = Path(value).expanduser()
    if raw.is_absolute():
        path = raw.resolve()
        if path.exists():
            return path
        raise FileNotFoundError(f"Input path does not exist: {path}")

    candidates = [Path.cwd() / raw]
    if raw.parts and raw.parts[0].lower() == "ai":
        candidates.append(REPOSITORY_DIR / raw)
    candidates.append(AI_DIR / raw)

    checked: list[str] = []
    for candidate in candidates:
        resolved = candidate.resolve()
        if str(resolved) in checked:
            continue
        checked.append(str(resolved))
        if resolved.exists():
            return resolved
    raise FileNotFoundError(
        f"Input path does not exist: {value}. Checked: {', '.join(checked)}"
    )


def resolve_output_path(value: str | Path) -> Path:
    """Resolve a CLI output; simple relative paths are anchored under ``AI``."""

    raw = Path(value).expanduser()
    if raw.is_absolute():
        return raw.resolve()
    if raw.parts and raw.parts[0].lower() == "ai":
        return (REPOSITORY_DIR / raw).resolve()
    if Path.cwd().resolve() == AI_DIR.resolve():
        return (Path.cwd() / raw).resolve()
    return (AI_DIR / raw).resolve()
