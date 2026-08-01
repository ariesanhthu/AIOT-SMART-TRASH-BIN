"""V6 model: the proven V4 TinyCNN graph with a robust input pipeline."""

from __future__ import annotations

from V6.runtime import LABELS, configure_shared_contract

configure_shared_contract()

import tensorflow as tf  # noqa: E402

from src.config import IMAGE_CHANNELS, IMAGE_SIZE  # noqa: E402


def build_tiny_cnn_v6() -> tf.keras.Model:
    """Keep the V4 operator inventory and parameter budget unchanged."""

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
    model = tf.keras.Model(inputs, logits, name="tinycnn_v6_luma_balanced")
    validate_model_contract(model)
    return model


def validate_model_contract(model: tf.keras.Model) -> None:
    expected_input = (None, IMAGE_SIZE, IMAGE_SIZE, IMAGE_CHANNELS)
    expected_output = (None, len(LABELS))
    if tuple(model.input_shape) != expected_input:
        raise ValueError(f"Expected input {expected_input}, got {model.input_shape}")
    if isinstance(model.output_shape, list) or tuple(model.output_shape) != expected_output:
        raise ValueError(f"Expected one output {expected_output}, got {model.output_shape}")

