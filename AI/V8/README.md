# AI V8 — rotation-only, illumination-robust classifier

V8 trains the three-class ESP32-CAM classifier from the already split dataset
at `AI/V8/dataset_prepared`.

Class/output contract is unchanged from V7:

```text
0 = paper
1 = plastic
2 = organic
input = RGB 96x96
```

## Augmentation policy

- Geometry: only 0°, 90°, 180° or 270° rotation via `tf.image.rot90`.
- No flip, translation, scale, shear, perspective or crop jitter.
- Train-only lighting simulation: gamma, exposure, contrast, and per-channel
  illuminant gains (warm/cool/mixed light).
- 16 fresh online views per balanced source image per epoch by default. No
  augmented files are written, and validation/test are never augmented.

Quarter-turn rotation was chosen because it does not interpolate or deform the
square image. Arbitrary-angle rotation would require resampling and corner
filling, which can introduce artifacts.

## Illumination preprocessing

After the ESP32-compatible center crop and nearest-floor resize, V8 applies
RGB565 truncation, bounded gray-world white balance, then bounded mean-luma
normalization. This reduces sensitivity to both exposure level and light color.
The integer constants are recorded in `config.py` and in model metadata.

Important: deployment preprocessing must implement this V8 contract. A V8
model must not be paired with the older V7 preprocessing, which lacks the
gray-world step.

## Train

From the `AI` directory:

```powershell
python -m pip install -r V8/requirements.txt
python -m V8.train
```

Quick smoke run:

```powershell
python -m V8.train --epochs 2 --views-per-source 2 --out V8/artifacts_smoke
```

The default run draws 1,008 balanced augmented samples per epoch (63 steps at
batch size 16) from the 48 training images. Best-checkpoint selection uses only
validation macro recall/accuracy. The test split is evaluated exactly once
after model selection.

The supplied validation (11 images) and test (11 images) sets are very small,
so their percentages have high uncertainty. Collect an independent later
ESP32-CAM session before treating test accuracy as deployment accuracy.
