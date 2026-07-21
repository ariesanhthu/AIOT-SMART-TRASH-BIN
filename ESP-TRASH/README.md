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

Wi-Fi được lưu bằng BLE provisioning, không hard-code SSID/password trong
firmware. IP `172.20.10.4` là IP máy chạy server được xác minh trên mạng
`AIoTSTB` ngày 2026-07-18. `server-tmp` sẽ in URL LAN đúng khi khởi động. Nếu
DHCP đổi IP, cập nhật `kServerUrl` rồi nạp lại firmware. Token phải giống biến
`AIOT_DEVICE_TOKEN` phía server.

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
Serial.write(1);       // byte 0x01
// hoặc
Serial.println("1");  // ký tự ASCII '1'
```

ESP trả:

| Kết quả | Ý nghĩa |
| --- | --- |
| `0\n` | Camera/model/ảnh/tiền xử lý/suy luận lỗi |
| `1\n` | Nhựa (`plastic`) |
| `2\n` | Giấy (`paper`) |
| `3\n` | Hữu cơ (`organic`) |

## Dữ liệu gửi FastAPI

Ảnh QVGA RGB565 dùng cho AI được chuyển thành JPEG quality 80. Firmware POST
body `image/jpeg` trực tiếp để không tạo bản sao base64/multipart trong RAM.
Các HTTP header gồm:

- result code và device ID;
- confidence và xác suất paper/plastic/organic;
- thời gian inference;
- chiều rộng/cao ảnh;
- SHA-256 model và device token.

Nano nhận kết quả trước khi HTTP upload bắt đầu. Server trả lỗi hay timeout chỉ
được ghi trên UART0, không thay đổi kết quả đã gửi Nano.

## Pipeline AI

- Model nguồn: `AI/V3/artifacts/model_int8.tflite`, 62,496 byte, SHA-256
  `5e543adfcd64a5627015e0e770fa8b1638d1febaefea2f105fb383707019826a`.
- Input INT8 `[1, 96, 96, 3]`, RGB, scale `1/255`, zero point `-128`.
- Output INT8 `[1, 3]`, scale `0.05487526208162308`, zero point `-27`:
  `paper`, `plastic`, `organic`.
- QVGA RGB565 -> center crop -> nearest-neighbor 96 x 96 -> quantize trực tiếp.
- TFLite Micro/ESP-NN, dequantize logits và stable-softmax.
- Mapping UART: `plastic=1`, `paper=2`, `organic=3`.
- Tensor arena 256 KiB được cấp một lần trong PSRAM.

Mỗi framebuffer được dùng cho cả input AI và JPEG telemetry, rồi trả lại camera
trước khi chạy TFLite `Invoke()` và trước khi gửi HTTP.
