# V7 evaluation report

V7 is a three-class closed-set model trained only from raw `AI/V7/data` ESP32-CAM captures.
No TrashNet, external data, stored `__aug_v2_` image, or `other` class is used.

## Contract

- Labels: `0=paper`, `1=plastic`, `2=organic`.
- Input: RGB 96×96.
- Preprocessing: center-square crop → nearest-floor resize → RGB565 → bounded Q8 luma gain.
- Split: chronological capture bursts; augmentation is online on train only.
- Counts: `{"train": {"paper": 13, "plastic": 21, "organic": 14}, "validation": {"paper": 4, "plastic": 4, "organic": 3}, "test": {"paper": 3, "plastic": 5, "organic": 3}}`.

## Test results

| Model | Accuracy | Macro recall | Paper recall | Plastic recall | Organic recall |
|---|---:|---:|---:|---:|---:|
| keras_fp32 | 0.8182 | 0.8667 | 1.0000 | 0.6000 | 1.0000 |
| tflite_fp32 | 0.8182 | 0.8667 | 1.0000 | 0.6000 | 1.0000 |
| tflite_int8 | 0.8182 | 0.8667 | 1.0000 | 0.6000 | 1.0000 |

## Quantization parity

- Keras/INT8 top-1 agreement: `1.0000`.
- INT8 accuracy drop: `0.0000`.

## Limitation

Test is a chronological burst holdout from the same capture date, not a sealed independent recapture session.
Capture a new ESP32 session with the same physical objects for a sealed final test before reporting deployment accuracy.
