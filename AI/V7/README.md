# AI V7 — ESP32-CAM three-class closed-set classifier

V7 keeps the V4 TinyCNN feature extractor and changes the head to exactly three
softmax outputs:

```text
0 = paper
1 = plastic
2 = organic
input = RGB 96x96
```

## Dataset policy

Only `data/<class>/esp32-cam-*.jpg` is admitted. The preparation step aborts on
an extra class or a non-canonical dataset root. It never reads TrashNet, V4, V5,
V6, `dataset_prepared` from another version, or an external dataset. Stored
`__aug_v2_` and legacy named files are audited but excluded.

Captures within three seconds form one burst. Bursts are split chronologically,
so adjacent frames never cross train/validation/test. Online bounded
augmentation and balanced sampling are applied only to train.

The current 70 raw captures all have the same UTC date. Therefore the generated
test set is a chronological burst holdout, not a sealed independent session.
Capture a later ESP32 session with the same physical objects before reporting
final deployment accuracy.

## Preprocessing contract

The TensorFlow pipeline matches `ESP-TRASH/image_preprocessor.cpp`:

```text
QVGA RGB -> center crop 240x240 -> nearest-floor resize 96x96
         -> RGB565 low-bit truncation -> bounded integer luma gain
         -> float [0,1] / INT8
```

No CLAHE, Canny, Sobel, background replacement, MixUp, CutMix, or external
image is used.

## Run

From `AI`:

```powershell
python -m pip install -r V7/requirements.txt
python -m V7.run_pipeline --force-prepare
python -m V7.verify_preprocessing
```

Preparation alone:

```powershell
python -m V7.run_pipeline --force-prepare --prepare-only
```

Main outputs include `dataset_manifest.csv`, `source_audit.csv`,
`class_names.json`, `preprocessing_config.json`, `EVALUATION_REPORT.md`, models
and metrics under `artifacts/`, and isolated firmware files under
`esp32_model/`. Firmware packaging does not overwrite `ESP-TRASH`; deployment
must use the generated V7 contract together with the V7 byte array.
