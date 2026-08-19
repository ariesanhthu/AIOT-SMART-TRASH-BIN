# Model V10 deployment

`ESP-TRASH-V4` embeds the full-INT8 model from
`AI/V10/artifacts/model_int8.tflite`.

## Contract

- Model: `tinycnn-v10-wide-128x96-esp-contract` (92,115 Keras parameters).
- Size: 102,880 bytes.
- SHA-256: `ec212a03b00d38e2cfe1933309f49de4cfab67746a9d1c4116736abf82b01b13`.
- Input: INT8 `[1,96,128,3]`, scale `1/255`, zero point `-128`.
- Output: INT8 `[1,3]`, scale `1/256`, zero point `-128`.
- Labels: `paper=0`, `plastic=1`, `organic=2`.
- Operators: `CONV_2D`, `MEAN`, `FULLY_CONNECTED`, `SOFTMAX`.
- Startup self-test raw output: `[-128,-128,127]`; expected `organic`.

## Preprocessing

ESP edge inference uses this deterministic preprocessing contract:

1. Decode RGB / read the QVGA RGB565 camera framebuffer.
2. Nearest-neighbor integer-floor resize of the complete frame to 128x96;
   no square crop or aspect-ratio crop is performed.
3. RGB565 channel truncation (R/B step 8, G step 4).
4. Bounded gray-world white balance, Q10 gains `[768,1365]`.
5. Bounded mean-luminance normalization, Q8 gains `[192,341]`, dead-band
   `[96,160]`.
6. Quantize exactly as `pixel - 128`.

After inference, firmware applies an application-level confidence threshold of
`0.60`. A lower confidence returns `C 0` (not recognized); this threshold is
not stored in or applied by the TFLite model.

The Python/C++ preprocessing contract test uses a non-4:3 synthetic source and
matches FNV-1a digest `0x08dea6c58ccf666a`.

## Accuracy

| Dataset | Float | Full INT8 | Note |
|---|---:|---:|---|
| Validation (39) | 92.31% | 94.87% | 1 top-1 float/INT8 disagreement |
| Test (39) | 94.87% | 94.87% | 0 top-1 disagreements |
| `server-tmp` (259) | 98.84% | 98.84% | 222 are exact train files; not independent |

## Build and memory check

Clean build for `esp32:esp32:esp32cam` with Huge APP succeeds:

- Program storage: 1,496,702 / 3,145,728 bytes (47%); 1,649,026 bytes free.
- Static internal RAM: 77,716 / 327,680 bytes (23%); 249,964 bytes free.
- Tensor arena: 262,144 bytes allocated once in external PSRAM.
- One QVGA RGB565 framebuffer: 153,600 bytes in external PSRAM.
- App SHA-256: `2b8802a9ff3ff77cdac64b381c3c06a7b3a088e5fa6d5506dc83224096eeff63`.
- Merged image SHA-256: `9bd2e4fd33f6a42df85a50f07d750fcb5fb369e4579ba897b622ca175fb4980b`.
- The exact model byte sequence occurs once in the app binary at offset 93,232.

There is no compile/link flash or static-RAM overflow. `AllocateTensors()` and
the model self-test run at boot; confirm the printed `Model arena used` and
PSRAM largest-free-block values once on the physical board, because a desktop
build cannot reproduce the ESP-NN scratch-buffer allocation exactly.

## Verification

From the repository root:

```powershell
python .\ESP-TRASH-V4\verify_embedded_model.py
python -m V10.verify_preprocessing  # run from AI/
.\ESP-TRASH-V4\build_firmware.ps1 -Clean
```
