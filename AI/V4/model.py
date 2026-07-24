"""Compact four-class CNN compatible with the ESP32/TFLite Micro contract."""

from __future__ import annotations

from V4.runtime import LABELS, configure_shared_contract

configure_shared_contract()

import tensorflow as tf

from src.config import IMAGE_CHANNELS, IMAGE_SIZE


def build_tiny_cnn_v4() -> tf.keras.Model:
    """Reuse the proven V3 feature extractor and add the V4 reject class."""

    inputs = tf.keras.Input(
        shape=(IMAGE_SIZE, IMAGE_SIZE, IMAGE_CHANNELS),
        dtype=tf.float32,
        name="image",
    )
    x = inputs
    for filters, name in (
        (16, "block1"),
        (24, "block2"),
        (32, "block3"),
        (48, "block4"),
        (64, "block5"),
    ):
        x = tf.keras.layers.Conv2D(
            filters,
            kernel_size=3,
            strides=2,
            padding="same",
            use_bias=True,
            name=f"{name}_conv",
        )(x)
        x = tf.keras.layers.BatchNormalization(
            momentum=0.90,
            epsilon=1e-3,
            name=f"{name}_bn",
        )(x)
        x = tf.keras.layers.ReLU(max_value=6.0, name=f"{name}_relu6")(x)

    x = tf.keras.layers.GlobalAveragePooling2D(name="global_average_pooling")(x)
    x = tf.keras.layers.Dropout(0.30, name="classifier_dropout")(x)
    logits = tf.keras.layers.Dense(len(LABELS), name="logits")(x)
    model = tf.keras.Model(inputs, logits, name="tinycnn_v4_4class")
    validate_model_contract(model)
    return model


def validate_model_contract(model: tf.keras.Model) -> None:
    expected_input = (None, IMAGE_SIZE, IMAGE_SIZE, IMAGE_CHANNELS)
    expected_output = (None, len(LABELS))
    if tuple(model.input_shape) != expected_input:
        raise ValueError(f"Expected input {expected_input}, got {model.input_shape}")
    if isinstance(model.output_shape, list) or tuple(model.output_shape) != expected_output:
        raise ValueError(f"Expected one output {expected_output}, got {model.output_shape}")

