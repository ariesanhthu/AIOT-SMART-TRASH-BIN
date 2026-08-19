# V10 training, quantization and deployment report

## Dataset and model

- Combined dataset: 753 files, with 675 train and 39 each for validation/test.
- Each class has 225 train, 13 validation and 13 test images.
- Merge audit: zero exact duplicates and zero source-group leakage.
- Input: 128x96 (width x height), center-crop 4:3 without distortion.
- Architecture: five Conv2D-BatchNorm-ReLU6 blocks with filters
  `16,24,40,64,96`, global average pooling and 3-way softmax.
- Parameters: 92,115; best epoch: 12.

## Accuracy and quantization

| Metric | Float validation | INT8 validation | Float test | INT8 test |
|---|---:|---:|---:|---:|
| Accuracy | 92.31% | 94.87% | 94.87% | 94.87% |
| Macro recall | 92.31% | 94.87% | 94.87% | 94.87% |
| Minimum class recall | 84.62% | 92.31% | 92.31% | 92.31% |

The TFLite model is full integer: INT8 input/output, no float tensors, and only
`CONV_2D`, `MEAN`, `FULLY_CONNECTED`, `SOFTMAX`. It is 102,880 bytes with
SHA-256 `ec212a03b00d38e2cfe1933309f49de4cfab67746a9d1c4116736abf82b01b13`.
Test has zero float/INT8 top-1 disagreements.

## `server-tmp` inference

- Overall INT8: 256/259 = 98.84%; macro recall 99.14%; macro-F1 0.988.
- Confusion: paper `[134,1,1]`, plastic `[1,90,0]`, organic `[0,0,32]`.
- Float and INT8 agree on all 259 top-1 predictions.
- 252 images have confidence >= 0.8; accuracy on them is 99.60%.
- Exposure audit: 222 exact train files, 18 validation, 18 test and 1 unseen.
- The only unseen file is the previously excluded
  `paper/ae41156a-aa81-46b1-97d7-fb8f22cfdad6.jpg`; both models predict
  plastic at 98.44%, consistent with the earlier manual review that it is
  probably a plastic bottle mislabeled as paper.

This 98.84% figure is not an independent generalization estimate because the
augmented dataset was built from `server-tmp`. Use a new capture session that
has never been used as an original or augmentation source for final acceptance.

## ESP32 build and capacity

- Clean firmware build: PASS.
- Program storage: 1,496,702 / 3,145,728 bytes (47%).
- Static internal RAM: 77,716 / 327,680 bytes (23%).
- Tensor arena: 256 KiB external PSRAM; one QVGA RGB565 framebuffer: 150 KiB.
- Python/C++ preprocessing digest: PASS (`0x08dea6c58ccf666a`).
- Embedded model hash, tensor shapes, label order and quantization: PASS.

No compile/link overflow is present. The physical board must still boot once
to make `AllocateTensors()` report exact ESP-NN arena usage and complete the
runtime self-test.
