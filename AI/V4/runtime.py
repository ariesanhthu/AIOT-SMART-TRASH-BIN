"""Configure the shared AI utilities for the isolated V4 label contract."""

from __future__ import annotations

import sys


LABELS: tuple[str, ...] = ("paper", "plastic", "organic", "other")
MODEL_VERSION = "tinycnn-v4-4class"


def configure_shared_contract() -> None:
    """Patch only runtime constants before importing shared ``src`` modules.

    V3 remains reproducible because ``src.config`` keeps its three-class defaults.
    Every V4 entry point calls this function before importing dataset, metadata,
    export, evaluation, or model helpers that capture the shared constants.
    """

    from src import config

    expected_mapping = {label: index for index, label in enumerate(LABELS)}
    if (
        config.LABELS == LABELS
        and config.CLASS_TO_INDEX == expected_mapping
        and config.MODEL_VERSION == MODEL_VERSION
    ):
        return

    stale = sorted(
        name
        for name in sys.modules
        if name in {
            "src.dataset",
            "src.evaluate_model",
            "src.export_int8",
            "src.metadata",
            "src.metrics",
            "src.model",
        }
    )
    if stale:
        raise RuntimeError(
            "V4 contract must be configured before shared AI modules are loaded: "
            + ", ".join(stale)
        )

    config.LABELS = LABELS
    config.CLASS_TO_INDEX = expected_mapping
    config.INDEX_TO_CLASS = {
        index: label for label, index in config.CLASS_TO_INDEX.items()
    }
    config.MODEL_VERSION = MODEL_VERSION
