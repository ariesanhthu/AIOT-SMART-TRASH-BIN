# V10 labeled ESP data augmentation report

All generated files are physically saved under `dataset_prepared/train/<label>`.
Validation and test were not augmented or changed.

| Split | paper | plastic | organic | Total |
|---|---:|---:|---:|---:|
| train | 251 | 251 | 238 | 740 |
| validation | 13 | 13 | 13 | 39 |
| test | 13 | 13 | 13 | 39 |

- Source images found: 6.
- Source images used: 5.
- New originals: 5.
- New saved augmentations: 60.
- Saved dimensions: 320x240.
- Exact duplicate files: 0.
- Source-group leakage: 0.

## Saved variants

- `resize_lowres`
- `rotate_left`
- `rotate_right`
- `jpeg_quality_20`
- `gaussian_blur`
- `sensor_noise`
- `color_warm`
- `color_cool`
- `color_desaturated`
- `light_bright`
- `light_dark`
- `edge_dark_blur_noise`

## Skipped leakage risks

- `data/paper/d6c607ff-e54d-4b58-9170-290051e6d6cf.jpg`: source already belongs to held-out split (test).
