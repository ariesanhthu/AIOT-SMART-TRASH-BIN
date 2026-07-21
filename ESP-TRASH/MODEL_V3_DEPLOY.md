# Model V3 trên ESP32-CAM

Firmware nhúng trực tiếp model:

```text
AI/V3/artifacts/model_int8.tflite
size    = 62,496 byte
SHA-256 = 5e543adfcd64a5627015e0e770fa8b1638d1febaefea2f105fb383707019826a
```

## Contract inference

- Input: INT8 `[1, 96, 96, 3]`, RGB, scale `1/255`, zero point `-128`.
- Output: INT8 `[1, 3]`, scale `0.05487526208162308`, zero point `-27`.
- Nhãn model: `paper=0`, `plastic=1`, `organic=2`.
- Mã trả về Nano: `plastic=1`, `paper=2`, `organic=3`, lỗi=`0`.
- Operator TFLM đăng ký: `CONV_2D`, `MEAN`, `FULLY_CONNECTED`.

Firmware kiểm tra size, SHA-256, schema TFLite, shape, dtype và quantization trước
khi bật pipeline. Self-test tổng hợp cho output tham chiếu LiteRT
`[-128, 82, 45]`, lớp cao nhất là `plastic`; firmware yêu cầu plastic thắng hai
lớp còn lại ít nhất 24 mức INT8 để chịu được sai khác làm tròn giữa các kernel.

## Preprocessing

Pipeline không đổi so với V2: QVGA RGB565 được crop vuông chính giữa, resize
nearest-neighbor về `96x96`, chuyển RGB và quantize trực tiếp bằng `q = pixel - 128`.
Thứ tự kênh và công thức resize trùng với pipeline huấn luyện.

Tensor arena 256 KiB được cấp một lần từ PSRAM. V3 có năm convolution thay vì bốn,
nhưng vẫn dùng cùng ba loại operator TFLM nên không cần mở rộng resolver.

## Build

```powershell
.\ESP-TRASH\build_firmware.ps1 -Clean
```

Script chạy `verify_embedded_model.py` trước khi compile và sẽ dừng nếu C array,
contract hoặc metadata không khớp V3.
