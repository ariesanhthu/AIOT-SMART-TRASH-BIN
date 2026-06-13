from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np


FEATURE_NAMES = [
    "r_mean", "g_mean", "b_mean",
    "r_std", "g_std", "b_std",
    "h_mean", "s_mean", "v_mean",
    "h_std", "s_std", "v_std",
    "gray_hist_0", "gray_hist_1", "gray_hist_2", "gray_hist_3",
    "gray_hist_4", "gray_hist_5", "gray_hist_6", "gray_hist_7",
    "area_ratio", "bbox_width_ratio", "bbox_height_ratio",
    "aspect_ratio", "extent", "circularity", "edge_density",
]


def read_image(source: str | Path | bytes) -> np.ndarray:
    """Read an image from a path or encoded image bytes."""
    if isinstance(source, bytes):
        encoded = np.frombuffer(source, dtype=np.uint8)
        image = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
        source_name = "image bytes"
    else:
        source_name = str(source)
        image = cv2.imread(source_name, cv2.IMREAD_COLOR)

    if image is None:
        raise ValueError(f"Cannot decode {source_name}")
    return image


def _center_crop_square(image: np.ndarray) -> np.ndarray:
    height, width = image.shape[:2]
    size = min(height, width)
    y0 = (height - size) // 2
    x0 = (width - size) // 2
    return image[y0:y0 + size, x0:x0 + size]


def _largest_object_mask(
    gray: np.ndarray,
) -> tuple[np.ndarray, tuple[int, int, int, int] | None]:
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    _, threshold = cv2.threshold(
        blur, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
    )

    total_area = gray.shape[0] * gray.shape[1]
    best_area = 0.0
    best_mask = np.zeros_like(gray, dtype=np.uint8)
    best_bbox = None

    for candidate in (threshold, 255 - threshold):
        contours, _ = cv2.findContours(
            candidate, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )
        for contour in contours:
            area = cv2.contourArea(contour)
            if not total_area * 0.02 <= area <= total_area * 0.95:
                continue
            if area <= best_area:
                continue

            best_area = area
            best_bbox = cv2.boundingRect(contour)
            best_mask.fill(0)
            cv2.drawContours(best_mask, [contour], -1, 255, thickness=-1)

    return best_mask, best_bbox


def extract_features(
    source: str | Path | bytes | np.ndarray,
    image_size: int = 64,
) -> np.ndarray:
    """Convert one image into a compact, fixed-size feature vector."""
    image = source if isinstance(source, np.ndarray) else read_image(source)
    if image.ndim != 3 or image.shape[2] != 3:
        raise ValueError("Expected a 3-channel BGR image")

    image = _center_crop_square(image)
    image = cv2.resize(image, (image_size, image_size), interpolation=cv2.INTER_AREA)

    rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    rgb_values = rgb.astype(np.float32) / 255.0
    hsv_values = hsv.astype(np.float32)
    hsv_values[:, :, 0] /= 179.0
    hsv_values[:, :, 1:] /= 255.0

    rgb_pixels = rgb_values.reshape(-1, 3)
    hsv_pixels = hsv_values.reshape(-1, 3)
    gray_hist = cv2.calcHist([gray], [0], None, [8], [0, 256]).ravel()
    gray_hist /= gray_hist.sum() + 1e-6

    mask, bbox = _largest_object_mask(gray)
    total_pixels = float(image_size * image_size)
    area_ratio = float(np.count_nonzero(mask)) / total_pixels
    edges = cv2.Canny(gray, 60, 120)
    edge_density = float(np.count_nonzero(edges)) / total_pixels

    shape_features = np.zeros(5, dtype=np.float32)
    if bbox is not None:
        _, _, width, height = bbox
        contours, _ = cv2.findContours(
            mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )
        contour = max(contours, key=cv2.contourArea)
        contour_area = cv2.contourArea(contour)
        perimeter = cv2.arcLength(contour, True)
        shape_features = np.array(
            [
                width / image_size,
                height / image_size,
                width / max(height, 1),
                contour_area / max(width * height, 1),
                4.0 * np.pi * contour_area / max(perimeter * perimeter, 1e-6),
            ],
            dtype=np.float32,
        )

    features = np.concatenate(
        [
            rgb_pixels.mean(axis=0),
            rgb_pixels.std(axis=0),
            hsv_pixels.mean(axis=0),
            hsv_pixels.std(axis=0),
            gray_hist,
            np.array([area_ratio], dtype=np.float32),
            shape_features,
            np.array([edge_density], dtype=np.float32),
        ]
    ).astype(np.float32)

    if features.size != len(FEATURE_NAMES):
        raise RuntimeError(
            f"Feature length mismatch: {features.size} != {len(FEATURE_NAMES)}"
        )
    return features
