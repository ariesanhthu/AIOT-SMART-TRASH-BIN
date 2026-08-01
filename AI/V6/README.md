# AI V6 - V4-compatible, balanced and lighting-robust

V6 keeps the deployed V4 TinyCNN graph and label order:

```text
0 = paper
1 = plastic
2 = organic
3 = other
input = RGB 96x96
```

The only base dataset is `AI/V4/dataset_prepared`, produced by the V4
`prepare_dataset.py`. V6 preserves its train/validation/test splits exactly and
adds only files named `esp32-cam-*` from
`AI/V6/dataset_prepared/train/<label>`. Other files in the mixed V6 source
folders are deliberately ignored. File names do not determine the label; the
parent class folder does. Each same-session ESP32 burst stays in train.

Before both training and ESP32 inference, V6 applies the same integer contract:

```text
center square -> floor nearest 96x96 -> RGB565 -> bounded mean-luma gain
```

Mean luma in `[96,160]` is unchanged. Outside the dead-band a shared RGB gain
moves it toward the nearest boundary, capped to Q8 `[192,341]`. This avoids
amplifying black-frame noise or crushing already clipped highlights. Training
uses bounded camera augmentation: horizontal flip, at most 10-degree rotation,
mild crop/scale/exposure/colour changes, and rare shadow, blur, resolution and
noise changes. Exact round-robin sampling removes paper frequency bias; a small
organic-vs-paper margin term targets the observed failure without changing the
embedded graph.

Run from `AI`:

```powershell
python -m V6.run_pipeline --force-prepare --embed
```

Neither V4 nor V6 source data is deleted or rewritten. The verified combined
view is written to `dataset_indexed` and the final 25-epoch model to
`artifacts`. The extra fine-tune stage is disabled unless `--fine-tune` is
explicitly supplied. Deployment is refused unless clean INT8 and aggregate
environmental gates pass.

## Current verified result

The current indexed dataset contains 1,099 V4 images and 30 new ESP32-CAM
images. No other dataset is included:

| Split | paper | plastic | organic | other | Total |
| --- | ---: | ---: | ---: | ---: | ---: |
| train | 450 | 170 | 190 | 260 | 1,070 |
| validation | 15 | 5 | 5 | 9 | 34 |
| test | 11 | 4 | 4 | 6 | 25 |

The final full-INT8 model is 62,816 bytes. On the untouched V4 test split it has
96% accuracy, macro-F1 0.9534, and 100% label agreement with the float model.
Recall is paper 100%, plastic 75%, organic 100%, other 100%. Organic predicted
as paper is 0/4. Mean macro-F1 over eight synthetic lighting/angle stress
profiles is 0.6569 versus 0.5497 for the V4 baseline.

The V4 test set contains only 25 images, so these numbers have wide uncertainty.
The 30 new camera images are training samples and are not independent test
evidence. Strong warm/cool colour casts remain the weakest condition; collect a
separate physical-camera test set before treating the model as production
calibrated.
