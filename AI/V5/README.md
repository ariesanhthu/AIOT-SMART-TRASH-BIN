# AI V5 - balanced, environment-robust TinyCNN for ESP32-CAM

V5 keeps the V4 deployment contract and label order:

```text
0 = paper
1 = plastic
2 = organic
3 = other (cardboard + metal reject class)
input = RGB 96x96, center-square floor nearest-neighbor, pixel/255
```

## What changed from V4

- Physical classes use the leakage-safe `DATASET-V1-FULL` instead of the small
  V3 set dominated by nine offline copies of each original.
- Cardboard/metal keep the official TrashNet train/validation/test split.
- Training samples classes in exact round-robin order, giving every class 573
  effective examples per epoch without changing validation or test data.
- Train-only augmentation covers rotation/viewpoint, exposure/gamma, shadows,
  white balance, blur/noise, reduced resolution and RGB565 quantization. A
  class-symmetric 35% lighting branch specifically simulates globally clipped
  exposure and local glare; mild fine-tuning retains a 20% version of it.
- Evaluation reports clean metrics and deterministic environmental stress
  profiles separately, including the `organic -> paper` error rate.

## Run

From `AI`:

```powershell
python -m pip install -r V5/requirements.txt
python -m V5.run_pipeline --force-prepare
```

To reuse an already prepared dataset or trained float model:

```powershell
python -m V5.run_pipeline --skip-prepare
python -m V5.run_pipeline --skip-prepare --skip-train
```

The pipeline trains a robust base model, then runs two short balanced camera
calibration stages; `artifacts_tuned2` is the deployment candidate. Generated
datasets/artifacts are ignored because they are reproducible. The
deployment copy is embedded in `ESP-TRASH/model_data.cpp` only after INT8 and
environmental verification pass.
