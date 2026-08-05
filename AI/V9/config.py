"""Single source of truth for the V9 training/deployment contract."""

from pathlib import Path


V9_DIR = Path(__file__).resolve().parent
REPOSITORY_DIR = V9_DIR.parents[1]
DATASET_DIR = V9_DIR / "dataset_prepared"
ARTIFACTS_DIR = V9_DIR / "artifacts"
ESP_V3_DIR = REPOSITORY_DIR / "ESP-TRASH-V3"

CLASS_NAMES = ("paper", "plastic", "organic")
CLASS_TO_INDEX = {name: index for index, name in enumerate(CLASS_NAMES)}
SPLITS = ("train", "validation", "test")
IMAGE_SIZE = 96
IMAGE_CHANNELS = 3
MODEL_VERSION = "tinycnn-v9-balanced-esp-contract"

# This order and these integer bounds match ESP-TRASH-V2/image_preprocessor.cpp.
PREPROCESSING_CONFIG = {
    "operation_order": [
        "decode RGB",
        "center square crop",
        "nearest-neighbor floor resize to 96x96",
        "RGB565 low-bit truncation",
        "bounded gray-world white balance",
        "bounded mean-luminance normalization",
        "rescale float32 to [0,1]",
    ],
    "applies_to": ["train", "validation", "test", "quantization_representative"],
    "rgb565_steps": [8, 4, 8],
    "white_balance": {
        "method": "gray-world channel means",
        "gain_q10_limits": [768, 1365],
    },
    "luminance": {
        "formula": "(77*R + 150*G + 29*B + 128)//256",
        "mean_dead_band": [96, 160],
        "gain_q8_limits": [192, 341],
    },
}

AUGMENTATION_CONFIG = {
    "train_only": True,
    "manifest_controlled": True,
    "materialized_files_only": True,
    "online_augmentation": False,
    "never_augment_an_augmentation_output": True,
    "geometry": "none online; retain reviewed legacy variants only",
    "lighting_before_contract": {
        "gamma": [0.62, 1.60],
        "exposure_gain": [0.58, 1.55],
        "contrast": [0.72, 1.30],
        "per_channel_illuminant_gain": [0.76, 1.24],
    },
    "gaussian_sensor_noise_sigma_normalized": [0.003, 0.025],
    "validation_test_augmented": False,
}
