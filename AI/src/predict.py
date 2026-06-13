from __future__ import annotations

import argparse
from pathlib import Path
import zipfile

import joblib
import numpy as np

try:
    from .features import extract_features
except ImportError:
    from features import extract_features


def load_source(image: str, zip_member: str | None) -> str | bytes:
    if zip_member is None:
        image_path = Path(image)
        if not image_path.is_file():
            raise FileNotFoundError(f"Image not found: {image_path}")
        return str(image_path)

    zip_path = Path(image)
    if not zip_path.is_file():
        raise FileNotFoundError(f"ZIP not found: {zip_path}")
    with zipfile.ZipFile(zip_path) as archive:
        try:
            return archive.read(zip_member)
        except KeyError as exc:
            raise FileNotFoundError(
                f"ZIP member not found: {zip_member}"
            ) from exc


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Classify one paper/plastic image.")
    parser.add_argument("--model", default="artifacts/light_trashnet_model.joblib")
    parser.add_argument(
        "--image",
        required=True,
        help="Image path, or TrashNet ZIP path when --zip-member is used.",
    )
    parser.add_argument("--zip-member", help="Image member path inside the ZIP.")
    parser.add_argument(
        "--threshold",
        type=float,
        default=None,
        help="Override the confidence threshold stored in the model.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    artifact = joblib.load(args.model)
    model = artifact["model"]
    labels = {int(key): value for key, value in artifact["labels"].items()}
    threshold = (
        args.threshold
        if args.threshold is not None
        else float(artifact.get("confidence_threshold", 0.65))
    )
    if not 0.5 <= threshold <= 1.0:
        raise ValueError("Confidence threshold must be between 0.5 and 1.0")

    source = load_source(args.image, args.zip_member)
    features = extract_features(source).reshape(1, -1)
    probabilities = model.predict_proba(features)[0]
    classes = [int(value) for value in model.classes_]
    best_index = int(np.argmax(probabilities))
    predicted_id = classes[best_index]
    confidence = float(probabilities[best_index])

    source_name = args.zip_member or args.image
    print(f"Image: {source_name}")
    print(f"Prediction: {labels[predicted_id]}")
    print(f"Confidence: {confidence:.4f}")
    print("Probabilities:")
    for index, class_id in enumerate(classes):
        print(f"  {labels[class_id]}: {float(probabilities[index]):.4f}")
    print(f"Decision: {'ACCEPT' if confidence >= threshold else 'REJECT'}")


if __name__ == "__main__":
    main()
