"""Run V7 preparation, training, export, evaluation, and firmware packaging."""

from __future__ import annotations

import argparse
import json

from V7.config import ARTIFACTS_DIR, PREPARED_DATA_DIR, SOURCE_DATA_DIR
from V7.convert_to_c_array import convert_model
from V7.evaluate import evaluate_all
from V7.export_models import export_models
from V7.prepare_dataset import prepare_dataset
from V7.train import train_model


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force-prepare", action="store_true")
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--epochs", type=int, default=40)
    parser.add_argument("--patience", type=int, default=10)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--learning-rate", type=float, default=1e-3)
    parser.add_argument("--dropout", type=float, default=0.0)
    parser.add_argument("--seed", type=int, default=7)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.force_prepare or not PREPARED_DATA_DIR.exists():
        prepared = prepare_dataset(
            SOURCE_DATA_DIR, PREPARED_DATA_DIR, force=args.force_prepare
        )
    else:
        prepared = json.loads(
            (PREPARED_DATA_DIR / "stats.json").read_text(encoding="utf-8")
        )
    if args.prepare_only:
        print(json.dumps({"prepared": prepared}, indent=2, ensure_ascii=False))
        return
    trained = train_model(
        data=PREPARED_DATA_DIR,
        output=ARTIFACTS_DIR,
        batch_size=args.batch_size,
        epochs=args.epochs,
        patience=args.patience,
        learning_rate=args.learning_rate,
        dropout=args.dropout,
        seed=args.seed,
    )
    exported = export_models(
        model_path=ARTIFACTS_DIR / "model_float.keras",
        data=PREPARED_DATA_DIR,
        output=ARTIFACTS_DIR,
        seed=args.seed,
    )
    evaluated = evaluate_all(
        PREPARED_DATA_DIR, ARTIFACTS_DIR, batch_size=args.batch_size
    )
    firmware = convert_model(ARTIFACTS_DIR / "model_int8.tflite")
    print(
        json.dumps(
            {
                "prepared": prepared,
                "trained": trained,
                "exported": exported,
                "evaluated": evaluated,
                "firmware": firmware,
            },
            indent=2,
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
