# V6 evaluation report

Evaluation date: 2026-08-01. Dataset fingerprint:
`8c360510e048314dbf7c1bf5dfe10cbe8089e6310640a9cd998a37603532e5d0`.

## Dataset

- Sole base: all 1,099 images and original splits from
  `AI/V4/dataset_prepared`.
- Added data: 30 `esp32-cam-*` images from V6 train, ten each for paper,
  plastic and organic.
- No other V6 images or external dataset were admitted.
- Stored train counts: paper 450, plastic 170, organic 190, other 260.
- Effective per-epoch counts: 450 images for every class through exact
  round-robin sampling and fresh bounded augmentation; no stored duplicate was
  created.
- V4 validation/test remain unchanged. All new same-session camera captures
  remain train-only to avoid burst leakage.

## Training and INT8 result

- Exactly 25 epochs were run; checkpoint selection chose epoch 23 using V4
  validation plus deterministic environmental validation.
- Architecture remains the V4 TinyCNN: 53,452 parameters and the same five
  Conv2D, Mean and FullyConnected operator inventory.
- Full-INT8 size: 62,816 bytes.
- SHA-256:
  `efcc9b902c03e573d2a5fe7cd46127c8bfeee79dbbd676a179921f54ba2a6981`.
- Float/INT8 label agreement: 100%; accuracy drop: 0%.

| Test metric | Result |
| --- | ---: |
| Samples | 25 |
| Accuracy | 0.9600 |
| Macro-F1 | 0.9534 |
| Paper recall | 1.0000 |
| Plastic recall | 0.7500 |
| Organic recall | 1.0000 |
| Other recall | 1.0000 |
| Organic predicted as paper | 0/4 |

As a non-independent training sanity check, the INT8 model classifies 28/30
new ESP32 captures correctly: plastic 10/10, organic 10/10, paper 8/10. One
paper capture is predicted plastic and one organic. This does not replace a
camera test set because all 30 images participated in training.

Confusion matrix, rows actual and columns predicted in
`paper, plastic, organic, other` order:

```text
[[11,0,0,0],
 [ 1,3,0,0],
 [ 0,0,4,0],
 [ 0,0,0,6]]
```

Mean macro-F1 across eight synthetic environment profiles is 0.6569, versus
0.5497 for the V4 baseline. The
model is strong on low light, overexposure and rotations, but strong warm/cool
casts and the combined-hard profile remain weak. This is consistent with the
requested narrow V4-plus-camera training domain.

The clean test has only 25 V4 images, and the 30 new camera captures are part
of train. Consequently the 96% result is not sufficient evidence of physical
camera generalization. A future evaluation should use a separate camera
session that is never included in training.
