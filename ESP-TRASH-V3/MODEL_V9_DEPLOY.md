# Model V9 deployment

`ESP-TRASH-V3` nhúng trực tiếp full-INT8 model tại
`AI/V9/artifacts/model_int8.tflite`.

## Contract

- Model: `tinycnn-v9-balanced-esp-contract`.
- Size: 62,560 bytes.
- SHA-256: `851054bd0256a3173aa69a2dee733f059d14651271e684be06bc750cf8564253`.
- Input: INT8 `[1,96,96,3]`, scale `1/255`, zero point `-128`.
- Output: INT8 `[1,3]`, scale `1/256`, zero point `-128`.
- Labels: `paper=0`, `plastic=1`, `organic=2`.
- Operators: `CONV_2D`, `MEAN`, `FULLY_CONNECTED`, `SOFTMAX`.
- Startup self-test raw output: `[-128,-128,127]`; expected `organic`.

## Preprocessing

Training, validation, test, quantization calibration and firmware use the same
deterministic contract:

1. Decode RGB / read RGB565 camera framebuffer.
2. Center-square crop.
3. Nearest-neighbor floor resize to 96x96.
4. RGB565 channel truncation (R/B step 8, G step 4).
5. Bounded gray-world white balance, Q10 gains `[768,1365]`.
6. Bounded mean-luminance normalization, Q8 gains `[192,341]` with dead-band
   `[96,160]`.
7. Quantize exactly as `pixel - 128`.

## Test result

The same held-out 21 images were evaluated before and after quantization:

| Model | Accuracy | Paper recall | Plastic recall | Organic recall |
|---|---:|---:|---:|---:|
| Float Keras | 90.48% (19/21) | 100% | 85.71% | 85.71% |
| Full INT8 | 90.48% (19/21) | 100% | 85.71% | 85.71% |

There were zero label disagreements between float and INT8 on all 21 test
images. The maximum absolute probability difference was `0.05136`.

The test images are leakage-free but were captured in the same 2026-08-01
session as the training pool. A later independent capture session is still
required before claiming deployment-level generalization.

## Verification

From the repository root:

```powershell
python .\ESP-TRASH-V3\verify_embedded_model.py
g++ -std=c++17 -Wall -Wextra -Werror -I ESP-TRASH-V3 `
  ESP-TRASH-V3\preprocessing_contract_test.cpp `
  ESP-TRASH-V3\image_preprocessor.cpp `
  -o ESP-TRASH-V3\preprocessing_contract_test.exe
.\ESP-TRASH-V3\preprocessing_contract_test.exe
.\ESP-TRASH-V3\build_firmware.ps1
```
