"""Configure shared AI helpers for the isolated V6 deployment contract."""

from __future__ import annotations

import sys


LABELS: tuple[str, ...] = ("paper", "plastic", "organic", "other")
MODEL_VERSION = "tinycnn-v6-luma-balanced"


def configure_shared_contract() -> None:
    """Patch shared constants before importing contract-aware modules.

    V4 and older pipelines retain their defaults.  V6 owns only the process in
    which one of its entry points is running.
    """

    from src import config

    expected_mapping = {label: index for index, label in enumerate(LABELS)}
    if (
        config.LABELS == LABELS
        and config.CLASS_TO_INDEX == expected_mapping
        and config.MODEL_VERSION == MODEL_VERSION
        and config.LUMINANCE_NORMALIZATION
        and config.RGB565_INPUT
    ):
        return

    captured = {
        "src.dataset",
        "src.evaluate_model",
        "src.export_int8",
        "src.metadata",
        "src.metrics",
        "src.model",
    }
    stale = sorted(name for name in sys.modules if name in captured)
    if stale:
        raise RuntimeError(
            "V6 contract must be configured before shared AI modules: "
            + ", ".join(stale)
        )

    config.LABELS = LABELS
    config.CLASS_TO_INDEX = expected_mapping
    config.INDEX_TO_CLASS = {index: label for label, index in expected_mapping.items()}
    config.MODEL_VERSION = MODEL_VERSION
    config.LUMINANCE_NORMALIZATION = True
    config.RGB565_INPUT = True
    config.PREPROCESSING_SPEC = {
        **config.PREPROCESSING_SPEC,
        "sensor_input": "ESP32 RGB565 expansion",
        "luminance_normalization": (
            "integer mean luma dead-band [96,160], bounded Q8 RGB gain [192,341]"
        ),
        "operation_order": (
            "center crop -> nearest-neighbor floor resize -> RGB565 -> luma gain"
        ),
    }

