# AI module: Tiny CNN paper/plastic classifier

This module trains and tests the AI portion only. It reads the existing
TrashNet ZIP/split files from `trashnet/data`, trains only the two known
classes (`paper`, `plastic`), calibrates an `OTHER` rejection gate, exports a
full-integer TFLite model, and converts it to C arrays for ESP32 firmware.

## Main scripts

```text
src/
├── dataset_cnn.py
├── model_tiny_cnn.py
├── train_cnn.py
├── calibrate_rejection.py
├── export_int8.py
├── evaluate_model.py
├── convert_to_c_array.py
└── predict.py
```

## Train and export

Run from the `AI` directory:

```powershell
python src/train_cnn.py --data trashnet/data --image-size 96 --out artifacts --seed 42
python src/calibrate_rejection.py --model artifacts/model_float.keras --data trashnet/data --out artifacts
python src/export_int8.py --model artifacts/model_float.keras --representative-data trashnet/data --out artifacts/model_int8.tflite
python src/evaluate_model.py --model artifacts/model_int8.tflite --data trashnet/data --thresholds artifacts/thresholds.json --centroids artifacts/centroids.json
python src/convert_to_c_array.py --model artifacts/model_int8.tflite --header artifacts/model_data.h --source artifacts/model_data.cc
```

`python src/train.py ...` is kept as a compatibility wrapper for
`train_cnn.py`.

## Current result

The 2026-07-11 run produces:

- Float known-test accuracy: 87.91%
- INT8 known-test accuracy: 87.36%
- INT8 model size: 25,096 bytes
- INT8 OTHER false accept on TrashNet non-paper/plastic test images: 93.98%

The paper/plastic classifier is usable on the current split, but the `OTHER`
gate is not accepted yet. Capture a real `validation_other/other` and
`test/other` set from the prototype setup before final acceptance.
