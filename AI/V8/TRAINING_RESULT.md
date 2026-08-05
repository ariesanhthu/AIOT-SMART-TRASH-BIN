# V8 training result

Training date: 2026-08-04 (Asia/Bangkok)  
Dataset: `AI/V8/dataset_prepared`

## Configuration

- Model: TinyCNN, 53,203 parameters, RGB 96x96, three softmax outputs.
- Labels: `paper=0`, `plastic=1`, `organic=2`.
- Training images: 48; validation: 11; test: 11.
- Balanced online augmentation: 1,008 samples/epoch, batch 16.
- Geometry: quarter-turn rotation only; no flip, translation, scale, shear,
  perspective, affine deformation, or crop jitter.
- Lighting augmentation: gamma, exposure, contrast and illuminant colour.
- Preprocessing: RGB565 simulation, bounded gray-world white balance and
  bounded mean-luminance normalization.
- Requested epochs: 80; early stopping: epoch 20; selected checkpoint: epoch 6.
- Device: CPU; TensorFlow 2.20.0.

## Metrics

| Split | Accuracy | Macro recall | Minimum class recall |
|---|---:|---:|---:|
| Validation (11 images) | 100.00% | 100.00% | 100.00% |
| Test (11 images) | 81.82% | 77.78% | 33.33% |

Test confusion matrix (rows=true, columns=predicted; order paper, plastic,
organic):

```text
[[3, 0, 0],
 [0, 5, 0],
 [1, 1, 1]]
```

Paper and plastic recall are 100% on this test split. Organic recall is 33.33%
(one of three correct), so organic needs more independent captures under varied
objects and lighting before deployment. Because validation and test each contain
only 11 images from the same capture period, these metrics have high uncertainty
and must not be presented as general deployment accuracy.

## Artifact

- Model: `artifacts/model_float.keras`
- Size: 722,246 bytes
- SHA-256: `b0e4c8d923ef6da952a7f9fb886056e173e7877f27e03cf37a40d8e6d957a914`
- Full machine-readable details: `artifacts/model_metadata.json`

The ESP32 preprocessing must be updated to the V8 contract, especially the
bounded gray-world step, before this model is exported and deployed.
