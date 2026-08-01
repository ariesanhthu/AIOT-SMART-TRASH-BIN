"""V4-style TinyCNN with the V7 three-class closed-set head."""

from __future__ import annotations

import tensorflow as tf

from V7.config import CLASS_NAMES, IMAGE_CHANNELS, IMAGE_SIZE


def build_tiny_cnn_v7(dropout: float = 0.0) -> tf.keras.Model:
    if not 0.0 <= dropout < 1.0:
        raise ValueError("dropout must be in [0,1)")
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
            momentum=0.90, epsilon=1e-3, name=f"{name}_bn"
        )(x)
        x = tf.keras.layers.ReLU(max_value=6.0, name=f"{name}_relu6")(x)
    x = tf.keras.layers.GlobalAveragePooling2D(name="global_average_pooling")(x)
    if dropout:
        x = tf.keras.layers.Dropout(dropout, name="classifier_dropout")(x)
    probabilities = tf.keras.layers.Dense(
        len(CLASS_NAMES), activation="softmax", name="waste_class"
    )(x)
    model = tf.keras.Model(inputs, probabilities, name="tinycnn_v7_3class")
    validate_model_contract(model)
    return model


def validate_model_contract(model: tf.keras.Model) -> None:
    expected_input = (None, IMAGE_SIZE, IMAGE_SIZE, IMAGE_CHANNELS)
    expected_output = (None, len(CLASS_NAMES))
    if tuple(model.input_shape) != expected_input:
        raise ValueError(f"Expected V7 input {expected_input}, got {model.input_shape}")
    if (
        isinstance(model.output_shape, list)
        or tuple(model.output_shape) != expected_output
    ):
        raise ValueError(
            f"Expected V7 output {expected_output}, got {model.output_shape}"
        )
