"""Classify one image with the float or INT8 three-class model."""

from __future__ import annotations

import argparse
import json

import numpy as np

try:
    from .config import DEFAULT_INT8_MODEL, DEFAULT_METADATA, LABELS, resolve_input_path
    from .dataset import preprocess_file
    from .evaluate_model import load_predictor
    from .metadata import (
        read_json,
        validate_metadata_contract,
        verify_artifact_hash,
    )
    from .metrics import stable_softmax
except ImportError:
    from config import DEFAULT_INT8_MODEL, DEFAULT_METADATA, LABELS, resolve_input_path  # type: ignore
    from dataset import preprocess_file  # type: ignore
    from evaluate_model import load_predictor  # type: ignore
    from metadata import read_json, validate_metadata_contract, verify_artifact_hash  # type: ignore
    from metrics import stable_softmax  # type: ignore


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True)
    parser.add_argument("--model", default=str(DEFAULT_INT8_MODEL))
    parser.add_argument("--metadata", default=str(DEFAULT_METADATA))
    parser.add_argument("--json", action="store_true", dest="as_json")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    image_path = resolve_input_path(args.image)
    model_path = resolve_input_path(args.model)
    metadata_path = resolve_input_path(args.metadata)

    metadata = read_json(metadata_path)
    validate_metadata_contract(metadata)
    artifact_key = "int8_model" if model_path.suffix.lower() == ".tflite" else "float_model"
    verify_artifact_hash(metadata, artifact_key, model_path)

    image = preprocess_file(image_path)
    predictor = load_predictor(model_path)
    logits = np.asarray(predictor.predict_one(image), dtype=np.float32)
    probabilities = stable_softmax(logits[np.newaxis, ...])[0]
    predicted_index = int(np.argmax(logits))
    result = {
        "image": str(image_path),
        "model": str(model_path),
        "model_version": metadata["model_version"],
        "class_index": predicted_index,
        "label": LABELS[predicted_index],
        "confidence": float(probabilities[predicted_index]),
        "logits": {label: float(logits[index]) for index, label in enumerate(LABELS)},
        "probabilities": {
            label: float(probabilities[index]) for index, label in enumerate(LABELS)
        },
    }
    if args.as_json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return

    print(f"Image: {result['image']}")
    print(f"Decision: {result['label'].upper()}")
    print(f"Confidence: {result['confidence']:.4f}")
    for label in LABELS:
        print(f"  {label}: {result['probabilities'][label]:.4f}")


if __name__ == "__main__":
    main()
