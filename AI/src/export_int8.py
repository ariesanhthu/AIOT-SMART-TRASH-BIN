from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import tensorflow as tf

try:
    from .dataset_cnn import load_dataset_splits, load_images, samples_from_class_dirs
except ImportError:
    from dataset_cnn import load_dataset_splits, load_images, samples_from_class_dirs


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export a full-integer TFLite model.")
    parser.add_argument("--model", default="artifacts/model_float.keras")
    parser.add_argument("--representative-data", default="trashnet/data")
    parser.add_argument("--image-size", type=int, default=96)
    parser.add_argument("--out", default="artifacts/model_int8.tflite")
    parser.add_argument("--quantization-out", default=None)
    parser.add_argument("--max-representative", type=int, default=200)
    parser.add_argument("--seed", type=int, default=42)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    model = tf.keras.models.load_model(args.model, compile=False)
    representative = load_representative_images(
        args.representative_data,
        args.image_size,
        args.max_representative,
        args.seed,
    )

    converter = tf.lite.TFLiteConverter.from_keras_model(model)
    converter.optimizations = [tf.lite.Optimize.DEFAULT]
    converter.representative_dataset = representative_dataset(representative)
    converter.target_spec.supported_ops = [tf.lite.OpsSet.TFLITE_BUILTINS_INT8]
    converter.inference_input_type = tf.int8
    converter.inference_output_type = tf.int8

    tflite_model = converter.convert()
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(tflite_model)

    quantization_path = (
        Path(args.quantization_out)
        if args.quantization_out
        else out_path.parent / "quantization.json"
    )
    quantization = inspect_quantization(out_path)
    quantization["model_size_bytes"] = out_path.stat().st_size
    quantization_path.write_text(
        json.dumps(quantization, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    print(f"Saved INT8 model: {out_path}")
    print(f"Saved quantization metadata: {quantization_path}")
    print(json.dumps(quantization, indent=2))


def load_representative_images(
    data_path: str,
    image_size: int,
    max_representative: int,
    seed: int,
) -> np.ndarray:
    path = Path(data_path)
    try:
        splits = load_dataset_splits(path, seed=seed)
        samples = splits.train_known
    except Exception:
        samples = samples_from_class_dirs(
            path, split="representative", include_known=True, include_other=False
        )

    if not samples:
        raise RuntimeError("Representative dataset is empty")

    rng = np.random.default_rng(seed)
    if len(samples) > max_representative:
        indices = rng.choice(len(samples), size=max_representative, replace=False)
        samples = [samples[int(index)] for index in indices]

    x_rep, _, _ = load_images(samples, image_size)
    return x_rep.astype(np.float32)


def representative_dataset(images: np.ndarray):
    def generator():
        for image in images:
            yield [image[np.newaxis, ...].astype(np.float32)]

    return generator


def inspect_quantization(model_path: Path) -> dict:
    interpreter = tf.lite.Interpreter(model_path=str(model_path))
    interpreter.allocate_tensors()
    input_detail = interpreter.get_input_details()[0]
    output_details = interpreter.get_output_details()

    outputs = []
    for output in output_details:
        scale, zero_point = output["quantization"]
        outputs.append(
            {
                "name": output["name"],
                "shape": [int(value) for value in output["shape"]],
                "dtype": np.dtype(output["dtype"]).name,
                "scale": float(scale),
                "zero_point": int(zero_point),
            }
        )

    input_scale, input_zero_point = input_detail["quantization"]
    return {
        "input_name": input_detail["name"],
        "input_dtype": np.dtype(input_detail["dtype"]).name,
        "input_scale": float(input_scale),
        "input_zero_point": int(input_zero_point),
        "input_shape": [int(value) for value in input_detail["shape"]],
        "outputs": outputs,
    }


if __name__ == "__main__":
    main()
