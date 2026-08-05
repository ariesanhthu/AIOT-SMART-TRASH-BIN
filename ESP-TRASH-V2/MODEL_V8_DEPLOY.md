# Model V8 deployment

Firmware nhúng trực tiếp model full INT8:

```text
AI/V8/artifacts/model_int8.tflite
```

## Contract

- Model: `tinycnn-v8-rotation-light-robust`.
- Model size: 62,560 bytes.
- SHA-256: `12d9d1c5c16b72c1acd384fcc13004e652b435534c8fbf2a5e6219c980580c6d`.
- Input: INT8 `[1,96,96,3]`, scale `1/255`, zero point `-128`.
- Output: INT8 `[1,3]`, scale `1/256`, zero point `-128`, probabilities.
- Labels: `paper=0`, `plastic=1`, `organic=2`.
- UART routing remains `plastic=1`, `paper=2`, `organic=3`; pipeline errors
  return `C 0`.

## Preprocessing

The firmware matches the V8 integer preprocessing contract:

1. Center-square crop from QVGA RGB565.
2. Nearest-neighbor floor resize to 96x96.
3. RGB565 channel levels: R/B step 8, G step 4.
4. Bounded gray-world white balance with Q10 gains `[768,1365]`.
5. Bounded mean-luminance normalization with Q8 gains `[192,341]` and
   dead-band `[96,160]`.
6. Quantize each channel exactly as `pixel - 128`.

`preprocessing_contract_test.cpp` compares a deterministic RGB pattern with
the TensorFlow V8 reference using an FNV-1a digest.

## Model runtime

The full-INT8 graph uses only `CONV_2D`, `MEAN`, `FULLY_CONNECTED` and
`SOFTMAX`. The deterministic startup input produces LiteRT raw output
`[-128,127,-128]`; plastic wins by 255 raw units. Firmware requires a minimum
margin of 127.

INT8 validation accuracy is 11/11 and test accuracy is 9/11. The test set has
only 11 images; organic recall is 1/3, so additional independent organic
captures are required before claiming deployment-level accuracy.

## Verification

From the repository root:

```powershell
python .\ESP-TRASH-V2\verify_embedded_model.py
g++ -std=c++17 -Wall -Wextra -Werror -I ESP-TRASH-V2 `
  ESP-TRASH-V2\preprocessing_contract_test.cpp `
  ESP-TRASH-V2\image_preprocessor.cpp `
  -o ESP-TRASH-V2\build\preprocessing_contract_test.exe
.\ESP-TRASH-V2\build\preprocessing_contract_test.exe
.\ESP-TRASH-V2\build_firmware.ps1
```
