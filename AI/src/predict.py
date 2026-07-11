from __future__ import annotations

import argparse
from pathlib import Path
import zipfile

import numpy as np

try:
    from .dataset_cnn import ID_TO_LABEL, THREE_WAY_LABELS
    from .dataset_cnn import preprocess_encoded_image, preprocess_image, read_image
    from .evaluate_model import (
        load_centroids,
        load_json,
        load_predictor,
        reject_predictions,
        softmax,
    )
except ImportError:
    from dataset_cnn import ID_TO_LABEL, THREE_WAY_LABELS
    from dataset_cnn import preprocess_encoded_image, preprocess_image, read_image
    from evaluate_model import (
        load_centroids,
        load_json,
        load_predictor,
        reject_predictions,
        softmax,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Classify one trash image.")
    parser.add_argument("--model", default="artifacts/model_int8.tflite")
    parser.add_argument("--image", required=True)
    parser.add_argument("--zip-member")
    parser.add_argument("--thresholds", default="artifacts/thresholds.json")
    parser.add_argument("--centroids", default="artifacts/centroids.json")
    parser.add_argument("--image-size", type=int, default=96)
    parser.add_argument(
        "--threshold",
        type=float,
        default=None,
        help="Override confidence_min from thresholds.json.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    image = load_image(args.image, args.zip_member, args.image_size)
    x = image[np.newaxis, ...].astype(np.float32)

    predictor = load_predictor(args.model)
    logits, embeddings = predictor.predict(x)
    probabilities = softmax(logits)[0]
    raw_label_id = int(np.argmax(probabilities))

    thresholds = load_json(args.thresholds) if Path(args.thresholds).is_file() else None
    if thresholds is not None and args.threshold is not None:
        thresholds["confidence_min"] = args.threshold
    centroids = load_centroids(args.centroids) if Path(args.centroids).is_file() else None
    result_id = int(reject_predictions(logits, embeddings, thresholds, centroids)[0])

    print(f"Image: {args.zip_member or args.image}")
    print(f"Raw prediction: {ID_TO_LABEL[raw_label_id]}")
    print(f"Decision: {THREE_WAY_LABELS[result_id].upper()}")
    print(f"Confidence: {float(np.max(probabilities)):.4f}")
    print(f"Margin: {float(abs(probabilities[0] - probabilities[1])):.4f}")
    print("Probabilities:")
    for label_id, label in ID_TO_LABEL.items():
        print(f"  {label}: {float(probabilities[label_id]):.4f}")


def load_image(image: str, zip_member: str | None, image_size: int) -> np.ndarray:
    if zip_member is None:
        image_path = Path(image)
        if not image_path.is_file():
            raise FileNotFoundError(f"Image not found: {image_path}")
        return preprocess_image(read_image(image_path), image_size)

    zip_path = Path(image)
    if not zip_path.is_file():
        raise FileNotFoundError(f"ZIP not found: {zip_path}")
    with zipfile.ZipFile(zip_path) as archive:
        return preprocess_encoded_image(archive.read(zip_member), image_size)


if __name__ == "__main__":
    main()
