"""TinyCNN v2: a single-output, three-class model designed for TFLite Micro."""

from __future__ import annotations

import tensorflow as tf

try:
    from .config import IMAGE_CHANNELS, IMAGE_SIZE, LABELS
except ImportError:
    from config import IMAGE_CHANNELS, IMAGE_SIZE, LABELS  # type: ignore


def build_tiny_cnn_v2() -> tf.keras.Model:
    inputs = tf.keras.Input(
        shape=(IMAGE_SIZE, IMAGE_SIZE, IMAGE_CHANNELS),
        dtype=tf.float32,
        name="image",
    )
    x = tf.keras.layers.Conv2D(
        12,
        kernel_size=3,
        strides=2,
        padding="same",
        use_bias=False,
        name="stem_conv",
    )(inputs)
    x = tf.keras.layers.BatchNormalization(name="stem_bn")(x)
    x = tf.keras.layers.ReLU(max_value=6.0, name="stem_relu6")(x)

    for filters, name in ((24, "block1"), (32, "block2"), (48, "block3"), (64, "block4")):
        x = _depthwise_pointwise_block(x, filters, name)

    x = tf.keras.layers.GlobalAveragePooling2D(name="global_average_pooling")(x)
    logits = tf.keras.layers.Dense(len(LABELS), name="logits")(x)
    model = tf.keras.Model(inputs=inputs, outputs=logits, name="tinycnn_v2_3class")
    validate_model_contract(model)
    return model


def validate_model_contract(model: tf.keras.Model) -> None:
    expected_input = (None, IMAGE_SIZE, IMAGE_SIZE, IMAGE_CHANNELS)
    expected_output = (None, len(LABELS))
    if tuple(model.input_shape) != expected_input:
        raise ValueError(
            f"Model input shape must be {expected_input}, got {model.input_shape}"
        )
    if isinstance(model.output_shape, list) or tuple(model.output_shape) != expected_output:
        raise ValueError(
            "Model must expose exactly one three-logit output; "
            f"got {model.output_shape}"
        )


def _depthwise_pointwise_block(
    tensor: tf.Tensor, pointwise_filters: int, name: str
) -> tf.Tensor:
    tensor = tf.keras.layers.DepthwiseConv2D(
        kernel_size=3,
        strides=2,
        padding="same",
        use_bias=False,
        name=f"{name}_depthwise",
    )(tensor)
    tensor = tf.keras.layers.Conv2D(
        pointwise_filters,
        kernel_size=1,
        padding="same",
        use_bias=False,
        name=f"{name}_pointwise",
    )(tensor)
    tensor = tf.keras.layers.BatchNormalization(name=f"{name}_bn")(tensor)
    return tf.keras.layers.ReLU(max_value=6.0, name=f"{name}_relu6")(tensor)
