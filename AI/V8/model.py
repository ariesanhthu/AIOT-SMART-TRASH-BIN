"""ESP32-sized V8 classifier."""

import tensorflow as tf

from V8.config import CLASS_NAMES, IMAGE_CHANNELS, IMAGE_SIZE


def build_model(dropout: float = 0.15) -> tf.keras.Model:
    inputs = tf.keras.Input(
        (IMAGE_SIZE, IMAGE_SIZE, IMAGE_CHANNELS), dtype=tf.float32, name="image"
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
    return tf.keras.Model(inputs, outputs, name="tinycnn_v8_rotation_light_robust")

