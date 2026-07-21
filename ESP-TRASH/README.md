# ESP-TRASH - ESP32-CAM AI Thinker + Arduino Nano

Firmware chạy model TinyCNN V3 full INT8 cục bộ để phân loại `paper`, `plastic`, `organic`.
Nano gửi lệnh chụp, ESP32-CAM trả kết quả qua UART ngay sau inference, sau đó
gửi chính ảnh đã nhận diện và metadata AI về FastAPI qua Wi-Fi.

## Cấu hình mạng

Thông tin nằm trong `network_config.h`:

```cpp
kServerUrl    = "http://172.20.10.4:8000/api/v1/detections"
kDeviceToken  = "aiot-demo-token"
```

Firmware thử credential đã lưu trong NVS trước, sau đó dùng `WIFI_SSID` và
`WIFI_PASSWORD` trong file ignored `secrets.h`. BLE provisioning không được
link vào bản firmware này để dành IRAM cho HTTPS Cloudinary và Firebase.

ESP và máy server phải ở cùng mạng cho phép các client truy cập lẫn nhau.
Một số mobile hotspot bật client isolation; khi đó dù cùng SSID, ESP vẫn không
thể mở TCP đến laptop.

Mất Wi-Fi/server không làm dừng AI: ESP vẫn nhận diện và trả Nano. Firmware thử
kết nối lại ở lần upload tiếp theo; hiện tại không lưu hàng đợi ảnh offline vì
RAM/flash của ESP32-CAM có giới hạn.

## Mở và nạp bằng Arduino IDE

1. Mở `ESP-TRASH.ino` bằng Arduino IDE.
2. Cài **esp32 by Espressif Systems 3.3.10**.
3. Chọn **Tools > Board > esp32 > AI Thinker ESP32-CAM**.
4. Chọn CPU 240 MHz, Flash Frequency 80 MHz, Partition **Huge APP**.
5. Nối GPIO0 với GND, reset và Upload. Nạp xong tháo GPIO0 khỏi GND rồi reset.
6. Mở Serial Monitor 115200 baud để xem IP, inference và HTTP status.

Board phải có PSRAM. Cấp nguồn 5 V ổn định vào chân 5V; không cấp camera từ
chân 3.3V hoặc nguồn yếu của Nano.

## UART với Arduino Nano

| Arduino Nano | ESP32-CAM | Ghi chú |
| --- | --- | --- |
| TX | GPIO13 (RX2) | Qua chia áp 1 kOhm / 2 kOhm |
| RX | GPIO14 (TX2) | Nối trực tiếp |
| GND | GND | Bắt buộc chung mass |

Không dùng microSD vì GPIO13/14 dành cho UART. Cấu hình: 9600 baud, 8N1.

Nano có thể gửi:

```cpp
Serial.println("T 1");         // trigger chụp ảnh và chạy AI
Serial.println("F 20 80 65");  // độ đầy: nhựa, giấy, hữu cơ
```

Mỗi lệnh kết thúc bằng `\n`. Giao thức chỉ dùng chữ, số và dấu cách; không dùng
dấu ngoặc góc, dấu phẩy hoặc dấu hai chấm. Giá trị `F` phải nằm trong `0..100`.

ESP trả:

| Kết quả | Ý nghĩa |
| --- | --- |
| `C 0\n` | Camera/model/ảnh/tiền xử lý/suy luận lỗi |
| `C 1\n` | Nhựa (`plastic`) |
| `C 2\n` | Giấy (`paper`) |
| `C 3\n` | Hữu cơ (`organic`) |

Serial Monitor 115200 baud test được toàn bộ cloud pipeline:

1. Nhập `1` hoặc `T 1` để chụp và phân loại.
2. Sau khi thấy `Test result`, nhập `F 10 10 10` theo thứ tự nhựa, giấy, hữu cơ.
3. Firmware upload JPEG lên Cloudinary, in `secure_url`, cập nhật
   `devices/{deviceId}` và tạo event Firestore có `image_url`.

Firmware chờ lệnh `F` tối đa 60 giây khi test Monitor. Lệnh `WIFI_RESET` vẫn
giữ nguyên.

## Đồng bộ Cloudinary và Firestore

Ảnh QVGA RGB565 dùng cho AI được chuyển thành JPEG quality 80 và upload trực
tiếp tới Cloudinary bằng multipart HTTPS. Chỉ sau khi nhận được `secure_url`,
firmware mới gọi Firestore `documents:commit`. Commit cập nhật
`devices/{deviceId}` và tạo `devices/{deviceId}/events/{eventId}` atomically với
`image_url`, kết quả AI và ba mức đầy.

## Pipeline AI

- Model nguồn: `AI/V3/artifacts/model_int8.tflite`, 62,496 byte, SHA-256
  `5e543adfcd64a5627015e0e770fa8b1638d1febaefea2f105fb383707019826a`.
- Input INT8 `[1, 96, 96, 3]`, RGB, scale `1/255`, zero point `-128`.
- Output INT8 `[1, 3]`, scale `0.05487526208162308`, zero point `-27`:
  `paper`, `plastic`, `organic`.
- QVGA RGB565 -> center crop -> nearest-neighbor 96 x 96 -> quantize trực tiếp.
- TFLite Micro/ESP-NN, dequantize logits và stable-softmax.
- Mapping UART: `C 1` là plastic, `C 2` là paper, `C 3` là organic.
- Tensor arena 256 KiB được cấp một lần trong PSRAM.

Mỗi framebuffer được dùng cho cả input AI và JPEG telemetry, rồi trả lại camera
trước khi chạy TFLite `Invoke()` và trước khi gửi HTTP.
