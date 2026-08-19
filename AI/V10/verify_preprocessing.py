"""Check that TensorFlow V10 preprocessing matches the V2 firmware digest."""

from __future__ import annotations

import numpy as np
import tensorflow as tf

from V10.config import IMAGE_HEIGHT, IMAGE_WIDTH
from V10.data_pipeline import apply_illumination_contract, center_crop_resize_u8


EXPECTED_FNV1A = 0x08DEA6C58CCF666A


def main() -> None:
    # Use a non-4:3 source so this digest also validates center-crop offsets.
    y, x = np.mgrid[0:123, 0:211]
    image = np.stack(
        (
            (3 * x + 5 * y + 17) & 255,
            (7 * x + 2 * y + 41) & 255,
            (11 * x + 13 * y + 73) & 255,
        ),
        axis=-1,
    ).astype(np.uint8)
    output = apply_illumination_contract(
        center_crop_resize_u8(tf.constant(image))
    ).numpy()
    pixels = np.rint(output * 255.0).astype(np.uint8).reshape(-1)
    digest = 1469598103934665603
    for value in pixels:
        digest ^= int(value)
        digest = (digest * 1099511628211) & 0xFFFFFFFFFFFFFFFF
    if output.shape != (IMAGE_HEIGHT, IMAGE_WIDTH, 3):
        raise RuntimeError(f"Unexpected V10 preprocessing shape: {output.shape}")
    if EXPECTED_FNV1A and digest != EXPECTED_FNV1A:
        raise RuntimeError(
            f"V10 preprocessing mismatch: 0x{digest:016x} != 0x{EXPECTED_FNV1A:016x}"
        )
    print(f"V10 TensorFlow preprocessing contract: PASS (0x{digest:016x})")


if __name__ == "__main__":
    main()
