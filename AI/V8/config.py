"""V8 training and deployment contract."""

from pathlib import Path


V8_DIR = Path(__file__).resolve().parent
DATASET_DIR = V8_DIR / "dataset_prepared"
ARTIFACTS_DIR = V8_DIR / "artifacts"

# Keep the deployed class order compatible with V7 and the ESP32 firmware.
CLASS_NAMES = ("paper", "plastic", "organic")
CLASS_TO_INDEX = {name: index for index, name in enumerate(CLASS_NAMES)}
SPLITS = ("train", "validation", "test")
IMAGE_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png"})

MODEL_VERSION = "tinycnn-v8-rotation-light-robust"
IMAGE_SIZE = 96
IMAGE_CHANNELS = 3

# Integer constants are deliberately explicit so the same preprocessing can be
# ported to ESP32 without a floating-point interpretation mismatch.
PREPROCESSING_CONFIG = {
    "operation_order": [
        "decode RGB",
        "center square crop",
        "nearest-neighbor floor resize to 96x96",
        "RGB565 low-bit truncation",
        "bounded gray-world white balance",
        "bounded mean-luminance normalization",
        "normalize float32 to [0,1]",
    ],
    "rgb565_steps": [8, 4, 8],
    "white_balance": {
        "method": "gray-world channel means",
        "gain_q10_limits": [768, 1365],
        "gain_limits": [0.75, 1.3330078125],
    },
    "luminance": {
        "formula": "(77*R + 150*G + 29*B + 128)//256",
        "mean_dead_band": [96, 160],
        "gain_q8_limits": [192, 341],
    },
}

AUGMENTATION_CONFIG = {
    "train_only": True,
    "views_per_source_per_epoch": 16,
    "geometry": {
        "rotation_degrees": [0, 90, 180, 270],
        "interpolation": "none (tf.image.rot90)",
        "flip": False,
        "scale": False,
        "translation": False,
        "shear": False,
        "perspective": False,
        "crop_jitter": False,
    },
    "lighting_before_normalization": {
        "gamma": [0.55, 1.8],
        "exposure_gain": [0.45, 1.8],
        "contrast": [0.7, 1.35],
        "per_channel_illuminant_gain": [0.72, 1.28],
    },
}

