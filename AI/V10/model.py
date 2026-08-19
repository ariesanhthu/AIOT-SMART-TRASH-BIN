"""ESP32-sized V10 classifier using only TFLite Micro friendly operators."""

import tensorflow as tf

from V10.config import (
    CLASS_NAMES,
    IMAGE_CHANNELS,
    IMAGE_HEIGHT,
    IMAGE_WIDTH,
    MODEL_CONFIG,
)


def build_model(dropout: float = 0.22) -> tf.keras.Model:
    inputs = tf.keras.Input(
        (IMAGE_HEIGHT, IMAGE_WIDTH, IMAGE_CHANNELS),
        dtype=tf.float32,
        name="image",
    )
    x = inputs
    for block_index, filters in enumerate(MODEL_CONFIG["filters"], start=1):
        name = f"block{block_index}"
        x = tf.keras.layers.Conv2D(
            filters, 3, strides=2, padding="same", use_bias=False,
            name=f"{name}_conv",
        )(x)
        x = tf.keras.layers.BatchNormalization(
            momentum=0.90, epsilon=1e-3, name=f"{name}_bn"
        )(x)
        x = tf.keras.layers.ReLU(max_value=6.0, name=f"{name}_relu6")(x)
    x = tf.keras.layers.GlobalAveragePooling2D(name="global_average_pooling")(x)
    x = tf.keras.layers.Dropout(dropout, name="classifier_dropout")(x)
    outputs = tf.keras.layers.Dense(
        len(CLASS_NAMES), activation="softmax", name="waste_class"
    )(x)
    return tf.keras.Model(inputs, outputs, name="tinycnn_v10_wide_128x96_esp_contract")
