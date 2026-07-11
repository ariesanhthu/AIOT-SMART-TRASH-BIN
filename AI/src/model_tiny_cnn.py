from __future__ import annotations

import tensorflow as tf


def build_tiny_cnn(image_size: int = 96, num_classes: int = 2) -> tf.keras.Model:
    inputs = tf.keras.Input(shape=(image_size, image_size, 3), name="image")

    x = tf.keras.layers.Conv2D(
        12, 3, strides=2, padding="same", use_bias=False, name="stem_conv"
    )(inputs)
    x = tf.keras.layers.BatchNormalization(name="stem_bn")(x)
    x = tf.keras.layers.ReLU(max_value=6.0, name="stem_relu6")(x)

    x = _depthwise_pointwise_block(x, 24, "block1")
    x = _depthwise_pointwise_block(x, 32, "block2")
    x = _depthwise_pointwise_block(x, 48, "block3")
    x = _depthwise_pointwise_block(x, 64, "block4")

    x = tf.keras.layers.GlobalAveragePooling2D(name="global_average_pooling")(x)
    embedding = tf.keras.layers.Dense(32, name="embedding")(x)
    logits = tf.keras.layers.Dense(num_classes, name="logits")(embedding)

    return tf.keras.Model(inputs=inputs, outputs=logits, name="tiny_trash_cnn")


def build_deploy_model(trained_model: tf.keras.Model) -> tf.keras.Model:
    return tf.keras.Model(
        inputs=trained_model.input,
        outputs=[
            trained_model.get_layer("logits").output,
            trained_model.get_layer("embedding").output,
        ],
        name="tiny_trash_cnn_deploy",
    )


def build_embedding_model(model: tf.keras.Model) -> tf.keras.Model:
    return tf.keras.Model(
        inputs=model.input,
        outputs=model.get_layer("embedding").output,
        name=f"{model.name}_embedding",
    )


def _depthwise_pointwise_block(
    x: tf.Tensor,
    pointwise_filters: int,
    name: str,
) -> tf.Tensor:
    x = tf.keras.layers.DepthwiseConv2D(
        3, strides=2, padding="same", use_bias=False, name=f"{name}_depthwise"
    )(x)
    x = tf.keras.layers.Conv2D(
        pointwise_filters,
        1,
        padding="same",
        use_bias=False,
        name=f"{name}_pointwise",
    )(x)
    x = tf.keras.layers.BatchNormalization(name=f"{name}_bn")(x)
    return tf.keras.layers.ReLU(max_value=6.0, name=f"{name}_relu6")(x)
