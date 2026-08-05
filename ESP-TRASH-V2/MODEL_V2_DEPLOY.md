# Model V2 trên ESP32-CAM

> Tài liệu lịch sử. Firmware hiện tại đã chuyển sang V3; xem `MODEL_V3_DEPLOY.md`.

Firmware nhúng trực tiếp model:

```text
AI/V2/artifacts/model_int8.tflite
size    = 31,584 byte
SHA-256 = 8a43d85ca2f2e38779d8e3b942e077687684d1a2175315918ea1c3569d0a7114
```

## Contract inference

- Input: INT8 `[1, 96, 96, 3]`, RGB, scale `1/255`, zero point `-128`.
- Output: INT8 `[1, 3]`, scale `0.042801760137081146`, zero point `-11`.
- Nhãn model: `paper=0`, `plastic=1`, `organic=2`.
- Mã trả về Nano: `plastic=1`, `paper=2`, `organic=3`, lỗi=`0`.
- Operator TFLM đăng ký: `CONV_2D`, `MEAN`, `FULLY_CONNECTED`.

Firmware kiểm tra size, SHA contract, schema TFLite, shape, dtype và quantization
trước khi bật pipeline. Sai contract thì trả trạng thái lỗi thay vì chạy model
không tương thích.

Khi khởi động, firmware còn chạy một input tổng hợp xác định trước. LiteRT trên
máy tính cho raw output `[-128, 127, -12]` với lớp cao nhất là `plastic`.
Firmware yêu cầu cùng lớp cao nhất với margin đủ lớn; nếu kernel TFLM trên mạch
chạy sai thì dừng bằng `model_self_test_failed`, không tiếp tục phân loại ảnh.
Serial cũng in đầy đủ SHA-256 model đang thực sự chạy.

## Preprocessing trên mạch

Camera giữ cấu hình QVGA `320x240 RGB565`:

1. Crop vuông chính giữa thành vùng `240x240`.
2. Resize nearest-neighbor về `96x96` bằng đúng công thức lúc train:
   `source_index = (destination_index * 240) / 96`.
3. Chuyển RGB565 big-endian thành RGB bằng mức màu giống đường chuyển JPEG đã
   tạo ảnh train: `R5 << 3`, `G6 << 2`, `B5 << 3`.
4. Quantize từng kênh trực tiếp thành `int8`: `q = pixel - 128`.
5. Ghi thẳng vào `TfLiteTensor::data.int8`, không có ảnh trung gian.

Offset lấy mẫu X/Y được tính một lần rồi cache. Vòng lặp nóng dùng con trỏ;
không `malloc`, không dùng `String`, không resize bằng float trong mỗi inference.
Framebuffer được trả cho camera trước `Invoke()`.

Tensor arena 256 KiB được cấp đúng một lần từ PSRAM với alignment 16 byte.
Resolver chỉ chứa ba kernel model cần dùng.

## Build

Yêu cầu:

- Arduino IDE 2.x;
- `esp32 by Espressif Systems` phiên bản 3.3.10;
- board `AI Thinker ESP32-CAM` có PSRAM.

Chạy tại PowerShell:

```powershell
.\ESP-TRASH\build_firmware.ps1 -Clean
```

Script tự kiểm tra model nhúng, cài `Chirale_TensorFLowLite 2.0.0` khi thiếu,
và build với CPU 240 MHz, flash 80 MHz, QIO, Huge APP.

File nạp toàn bộ flash:

```text
ESP-TRASH/build/ESP-TRASH.ino.merged.bin
```

Có thể upload từ Arduino IDE như bình thường, hoặc dùng `esptool` ghi merged
binary tại địa chỉ `0x0`. Không ghi flash khi chưa nối GPIO0 xuống GND và cấp
nguồn 5 V ổn định cho ESP32-CAM.
