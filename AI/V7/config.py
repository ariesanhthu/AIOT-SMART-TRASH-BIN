"""Single source of truth for the V7 data and deployment contract."""

from __future__ import annotations

from pathlib import Path


V7_DIR = Path(__file__).resolve().parent
AI_DIR = V7_DIR.parent
REPOSITORY_DIR = AI_DIR.parent

CLASS_NAMES: tuple[str, ...] = ("paper", "plastic", "organic")
CLASS_TO_INDEX = {name: index for index, name in enumerate(CLASS_NAMES)}
SPLITS: tuple[str, ...] = ("train", "validation", "test")

MODEL_VERSION = "tinycnn-v7-esp32-closed-set"
IMAGE_SIZE = 96
IMAGE_CHANNELS = 3
INPUT_SHAPE = (IMAGE_SIZE, IMAGE_SIZE, IMAGE_CHANNELS)

SOURCE_DATA_DIR = V7_DIR / "data"
PREPARED_DATA_DIR = V7_DIR / "dataset_prepared"
ARTIFACTS_DIR = V7_DIR / "artifacts"
ESP32_MODEL_DIR = V7_DIR / "esp32_model"

RAW_CAPTURE_PREFIX = "esp32-cam-"
RAW_CAPTURE_GLOB = f"{RAW_CAPTURE_PREFIX}*.jpg"
STORED_AUGMENTATION_TOKEN = "__aug_v2_"
IMAGE_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png"})
BURST_GAP_SECONDS = 3.0
SPLIT_TARGETS = {"train": 0.70, "validation": 0.15, "test": 0.15}

# These tokens are checked against every admitted source path. V7 deliberately
# has no fallback to an earlier prepared dataset or to TrashNet.
FORBIDDEN_SOURCE_TOKENS = (
    "trashnet",
    "/v4/",
    "/v5/",
    "/v6/",
    "dataset_prepared",
)

PREPROCESSING_CONFIG = {
    "schema_version": 1,
    "input_shape": [IMAGE_SIZE, IMAGE_SIZE, IMAGE_CHANNELS],
    "color_space": "RGB",
    "source_camera": "ESP32-CAM OV2640 QVGA RGB565",
    "operation_order": [
        "decode RGB",
        "center square crop",
        "nearest-neighbor floor resize",
        "RGB565 low-bit truncation",
        "bounded integer mean-luminance normalization",
        "normalize to float32 [0,1] or quantize to int8",
    ],
    "crop": "center_square",
    "resize": "nearest_neighbor_floor",
    "resize_mapping": ("source_index=(destination_index*center_crop_size)//96"),
    "rgb565_expansion": "R/B=(value//8)*8; G=(value//4)*4",
    "luminance_normalization": {
        "luma_formula": "(77*R + 150*G + 29*B + 128)//256",
        "mean_dead_band": [96, 160],
        "gain_q8_limits": [192, 341],
        "gain_application": "clip((channel*gain_q8+128)//256,0,255)",
    },
    "float_input": {"dtype": "float32", "range": [0.0, 1.0]},
    "int8_input": {"scale": 1.0 / 255.0, "zero_point": -128},
    "firmware_files": [
        "ESP-TRASH/camera_adapter.cpp",
        "ESP-TRASH/image_preprocessor.cpp",
    ],
}
