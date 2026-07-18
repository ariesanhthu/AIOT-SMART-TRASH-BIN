# ESP32-CAM INT8 deployment scaffold

This directory is an ESP-IDF scaffold for the Ai-Thinker ESP32-CAM (original
`esp32` target) and its OV2640 camera. It contains only the camera-to-model
inference path. Servo, ultrasonic sensor, Wi-Fi, and telemetry integration are
intentionally outside this scaffold.

The firmware contract is a real three-class classifier:

```text
input  : int8 [1, 96, 96, 3], RGB, real pixel range [0, 1]
output : int8 [1, 3], ordered paper, plastic, organic
```

`organic` is a trained class. It must not be implemented as the old rejection
or `OTHER` branch.

The embedded model currently has 7,947 parameters, is 21,992 bytes, and has
SHA-256 `c8f97f74baec7c98ec52eaed97dc377c621471a317361787980b8e120fad02f8`.

## Status and safety

- `main/model/model_data.cc` is generated from the verified three-class INT8
  model by `python -m src.pipeline`; it is not a placeholder.
- The image preprocessing core was compiled and run on the host with GCC 13.
- The full ESP-IDF target has **not** been built, flashed, or measured on a
  physical board in the current environment because `idf.py` is unavailable.
- No actuator command is emitted. Any later actuator layer must interpret all
  initialization/capture/inference failures as "all gates closed".

## Layout

```text
AI/esp32/
|-- CMakeLists.txt
|-- sdkconfig.defaults        PSRAM and external-BSS settings
|-- partitions.csv           3 MiB factory application partition
|-- main/
|   |-- app_main.cpp          serialized capture -> preprocess -> invoke loop
|   |-- camera_adapter.*      Ai-Thinker pins and move-only framebuffer lease
|   |-- image_preprocessor.*  host-testable pointer-only hot loop
|   |-- tflm_classifier.*     TFLM/ESP-NN adapter and exact tensor checks
|   |-- model_contract.h      labels, shape, quantization, arena size
|   |-- status.*              allocation-free status reporting
|   `-- model/
|       |-- model_data.h
|       `-- model_data.cc
`-- tests/
    `-- image_preprocessor_host_test.cpp
```

Only `camera_adapter.cpp` knows the `esp32-camera` framebuffer API, and only
`tflm_classifier.cpp` knows TFLite Micro APIs. This keeps version-sensitive
code localized. Managed dependencies are pinned to compatible minor releases:

- `espressif/esp-tflite-micro ~1.3.7`
- `espressif/esp32-camera ~2.1.7`
- ESP-IDF `>=5.1`

The Espressif TFLM component includes ESP-NN optimized kernels. Convolution,
depthwise convolution, and fully-connected matrix work should stay inside
TFLM/ESP-NN; replacing those kernels with application C++ pointer loops would
discard SIMD/assembly optimization and make correctness harder to prove.

## Refresh the embedded model

The Python pipeline writes the verified pair (never the old two-class
artifacts) directly into:

```text
AI/esp32/main/model/model_data.cc
AI/esp32/main/model/model_data.h
```

The generated symbols must remain:

```cpp
extern const unsigned char g_model[];
extern const int g_model_len;
```

After changing the architecture, synchronize `model_contract.h` with the final
export:

1. Require one input tensor, exactly `int8 [1, 96, 96, 3]`.
2. Require one output tensor, exactly `int8 [1, 3]`.
3. Copy input scale and zero point from `quantization.json`.
4. Keep label order exactly `paper`, `plastic`, `organic`.
5. If the graph exports logits, keep `kOutputSemantic = kLogits`; if it exports
   softmax probabilities, change it to `kProbabilities`.
6. Inventory final operators and update the resolver in
   `tflm_classifier.cpp`. The current generated TinyCNN registers exactly
   `CONV_2D`, `DEPTHWISE_CONV_2D`, `MEAN`, and `FULLY_CONNECTED`.

The firmware validates schema, shapes, dtypes, input quantization, output
quantization, and arena allocation at boot. A stale two-class model cannot pass
these checks.

## Preprocessing contract

`ImagePreprocessor` performs, without heap allocation:

1. Validate source length and stride with division-first overflow checks.
2. Center-crop the source to a square.
3. Resize with deterministic nearest-neighbor mapping:
   `src = floor(dst * crop_size / dst_size)`.
4. Decode interleaved RGB888 or RGB565 (both byte orders supported).
5. Quantize RGB values directly into `TfLiteTensor::data.int8` through a
   256-entry lookup table prepared once at boot.

The training/evaluation preprocessing must use the same center crop, RGB order,
and nearest-neighbor rule. The old Python `cv2.INTER_AREA` pipeline is not
bit-equivalent and must not be used as the reference for this firmware.

The QVGA RGB565 camera buffer is read through `const uint8_t*` row/pixel
pointers. Horizontal source offsets are precomputed once per frame, and the hot
loop writes sequentially through an `int8_t*`. No full RGB888 copy is created.

## Memory ownership

- The model C array is `alignas(16)` read-only data in flash.
- The 256 KiB tensor arena is `alignas(16)`, statically reserved in external
  PSRAM, and never allocated/freed per inference.
- The camera uses one PSRAM framebuffer (`fb_count = 1`).
- `CameraFrameLease` is move-only and always calls `esp_camera_fb_return()` on
  destruction, including every early-return path.
- The frame is returned immediately after the input tensor has been filled,
  before `Invoke()` starts.
- Capture, preprocessing, and invocation are serialized. Neither the camera
  buffer nor `MicroInterpreter` is thread-safe in this design.

After the final model boots, read `arena_used_bytes()` from the log and reduce
`kTensorArenaBytes` only after repeated camera + inference + Wi-Fi stress tests.
Also monitor the largest free internal and PSRAM blocks, not just total bytes.

The original ESP32 camera driver warns that uncompressed RGB capture competes
with Wi-Fi for PSRAM bandwidth. This scaffold uses QVGA, one framebuffer, and a
serialized path. If real-device tests show corrupt frames while Wi-Fi is active,
keep `ImagePreprocessor` unchanged and replace only `CameraAdapter` with a JPEG
capture/decoder adapter backed by one fixed-size buffer; do not allocate a new
decode buffer for every frame.

## Host preprocessing test

From the repository root in PowerShell:

```powershell
g++ -std=c++17 -O2 -Wall -Wextra -Wpedantic -Werror `
  -I AI/esp32/main `
  AI/esp32/tests/image_preprocessor_host_test.cpp `
  AI/esp32/main/image_preprocessor.cpp `
  AI/esp32/main/status.cpp `
  -o AI/esp32/tests/image_preprocessor_host_test.exe

AI/esp32/tests/image_preprocessor_host_test.exe
```

The test covers center cropping, nearest-neighbor boundary mapping, RGB888,
big/little-endian RGB565, quantization, short source/destination rejection, and
sentinel bytes proving that the destination boundary is not overwritten.

## ESP-IDF build (requires the toolchain)

```powershell
cd AI/esp32
idf.py set-target esp32
idf.py build
idf.py -p COM_PORT flash monitor
```

Do not select `esp32s3`: the specified Ai-Thinker board uses the original ESP32.
PSRAM must be detected at runtime or initialization fails. Use a stable 5 V
supply; do not power servos from the ESP32-CAM regulator. The camera consumes
most convenient GPIOs, so the existing system recommendation of a second
Arduino/ESP32 for servos and level sensors remains appropriate.
