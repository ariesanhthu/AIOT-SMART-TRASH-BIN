"""Single source of truth for the V10 training/deployment contract."""

from pathlib import Path


V10_DIR = Path(__file__).resolve().parent
REPOSITORY_DIR = V10_DIR.parents[1]
DATASET_DIR = V10_DIR / "dataset_prepared"
ARTIFACTS_DIR = V10_DIR / "artifacts"
ESP_V3_DIR = REPOSITORY_DIR / "ESP-TRASH-V3"

CLASS_NAMES = ("paper", "plastic", "organic")
CLASS_TO_INDEX = {name: index for index, name in enumerate(CLASS_NAMES)}
SPLITS = ("train", "validation", "test")
IMAGE_HEIGHT = 96
IMAGE_WIDTH = 128
IMAGE_CHANNELS = 3
MODEL_VERSION = "tinycnn-v10-wide-128x96-esp-contract"

# This order and these integer bounds match ESP-TRASH-V3/image_preprocessor.cpp.
PREPROCESSING_CONFIG = {
    "operation_order": [
        "decode RGB",
        "center crop to 4:3 without distortion",
        "nearest-neighbor floor resize to 128x96 (width x height)",
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

MODEL_CONFIG = {
    "architecture": "five stride-2 Conv2D-BatchNorm-ReLU6 blocks, global average pooling, softmax",
    "filters": [16, 24, 40, 64, 96],
    "input_shape_hwc": [IMAGE_HEIGHT, IMAGE_WIDTH, IMAGE_CHANNELS],
    "tflite_micro_friendly": True,
}

AUGMENTATION_CONFIG = {
    "train_only": True,
    "manifest_controlled": True,
    "materialized_files_only": True,
    "online_augmentation": False,
    "never_augment_an_augmentation_output": True,
    "geometry": (
        "none online; reviewed saved variants include low-resolution resize "
        "and bounded +/-7 degree rotation"
    ),
    "lighting_before_contract": {
        "gamma": [0.62, 1.60],
        "exposure_gain": [0.58, 1.55],
        "contrast": [0.72, 1.30],
        "per_channel_illuminant_gain": [0.76, 1.24],
    },
    "gaussian_sensor_noise_sigma_normalized": [0.003, 0.025],
    "saved_labeled_esp_edge_cases": [
        "resize_lowres",
        "rotate_left",
        "rotate_right",
        "jpeg_quality_20",
        "gaussian_blur",
        "sensor_noise",
        "color_warm",
        "color_cool",
        "color_desaturated",
        "light_bright",
        "light_dark",
        "edge_dark_blur_noise",
    ],
    "validation_test_augmented": False,
}
