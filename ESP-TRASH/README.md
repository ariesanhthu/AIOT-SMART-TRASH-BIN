# ESP-TRASH - ESP32-CAM AI Thinker + Arduino Nano

Firmware chạy model TinyCNN V6 full INT8 cục bộ để phân loại `paper`, `plastic`,
`organic` và từ chối `other`.
Nano gửi lệnh chụp, ESP32-CAM trả kết quả qua UART ngay sau inference, sau đó
upload ảnh lên Cloudinary và ghi metadata trực tiếp vào Firebase/Firestore.

## Cấu hình mạng

Firmware thử credential đã lưu trong NVS trước, sau đó dùng `WIFI_SSID` và
`WIFI_PASSWORD` trong file ignored `secrets.h`. Sao chép
`secrets.example.h` thành `secrets.h`, rồi điền Cloudinary và các trường
`FIREBASE_*`. BLE provisioning không được link vào firmware để dành IRAM cho
HTTPS Cloudinary và Firebase.

Mất Wi-Fi không làm dừng AI: ESP vẫn nhận diện và trả Nano. Firmware thử
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
Serial.println("H 1");         // hỏi ESP đã khởi tạo xong và sẵn sàng chưa
Serial.println("T 1");         // trigger chụp ảnh và chạy AI
Serial.println("F 20 80 65");  // sau khi xử lý: độ đầy nhựa, giấy, hữu cơ
```

Mỗi lệnh kết thúc bằng `\n`. Giao thức chỉ dùng chữ, số và dấu cách; không dùng
dấu ngoặc góc, dấu phẩy hoặc dấu hai chấm. Giá trị `F` phải nằm trong `0..100`.

ESP trả:

| Phản hồi | Ý nghĩa |
| --- | --- |
| `R 1\n` | ESP đã khởi tạo xong và đang rảnh |
| `R 0\n` | ESP đang xử lý transaction trước |
| `A T\n` | Đã nhận trigger; bắt đầu chụp và phân loại |
| `C 0\n` | Lỗi pipeline hoặc model dự đoán `other`; Nano không định tuyến vào ngăn |
| `C 1\n` | Nhựa (`plastic`) |
| `C 2\n` | Giấy (`paper`) |
| `C 3\n` | Hữu cơ (`organic`) |
| `A F\n` | Đã nhận đủ ba mức đầy từ Nano |
| `D 1\n` | Cloudinary và Firestore thành công; ESP đã rảnh |
| `D 0\n` | Đồng bộ cloud thất bại nhưng ESP đã rảnh |

Luồng UART đầy đủ:

```text
Nano -- H 1 ----------> ESP
Nano <- R 1 ----------- ESP
Nano -- T 1 ----------> ESP
Nano <- A T ----------- ESP
Nano <- C <0..3> ------ ESP
Nano xử lý servo/cảnh báo và đo lại ba ngăn
Nano -- F <p> <pa> <o> -> ESP
Nano <- A F ----------- ESP
ESP upload Cloudinary rồi commit trực tiếp Firestore
Nano <- D <0|1> ------- ESP
```

Nano chỉ trigger sau `R 1`, gửi lại `T`/`F` tối đa ba lần nếu mất ACK và luôn
gửi `F` kể cả khi nhận `C 0`. ESP bỏ qua trigger lặp khi transaction đang chạy,
do đó gói retry không tạo thêm lần chụp ngoài ý muốn.

Serial Monitor 115200 baud test được toàn bộ cloud pipeline:

1. Nhập `1` hoặc `T 1` để chụp và phân loại.
2. Sau khi thấy `Test result`, nhập `F 10 10 10` theo thứ tự nhựa, giấy, hữu cơ.
3. Firmware upload JPEG lên Cloudinary, in `secure_url`, rồi gửi event
   `CLASSIFY`/`ERROR` (kèm `image_url`) trực tiếp vào Firestore. Nếu ngăn nào
   đó vượt ngưỡng đầy, firmware gửi thêm một event `FULL_ALERT` riêng.

Firmware chờ lệnh `F` tối đa 60 giây khi test Monitor. Lệnh `WIFI_RESET` vẫn
giữ nguyên.

## Đồng bộ trực tiếp Firebase

Ảnh QVGA RGB565 dùng cho AI được chuyển thành JPEG quality 80 và upload trực
tiếp tới Cloudinary bằng multipart HTTPS (nếu upload thất bại, event vẫn được
gửi với `imageUrl: null`). ESP dùng `FIREBASE_PROJECT_ID`, `FIREBASE_API_KEY`,
`FIREBASE_USER_EMAIL`, `FIREBASE_USER_PASSWORD` và `FIREBASE_DEVICE_ID` từ
`secrets.h` để lấy Firebase ID token và commit trực tiếp vào Firestore; không
gọi backend service.

## Pipeline AI

- Model nguồn: `AI/V6/artifacts/model_int8.tflite`, 62,816 byte, SHA-256
  `efcc9b902c03e573d2a5fe7cd46127c8bfeee79dbbd676a179921f54ba2a6981`.
- Input INT8 `[1, 96, 96, 3]`, RGB, scale `1/255`, zero point `-128`.
- Output INT8 `[1, 4]`, scale `0.06401441246271133`, zero point `-15`:
  `paper`, `plastic`, `organic`, `other`.
- QVGA RGB565 -> center crop -> nearest-neighbor 96 x 96 -> cân bằng mean-luma
  có giới hạn -> quantize. Mean luma trong `[96,160]` được giữ nguyên; ngoài
  khoảng này dùng gain Q8 giới hạn `[192,341]`, giống chính xác lúc train.
- TFLite Micro/ESP-NN, dequantize logits và stable-softmax.
- Mapping UART: `C 1` là plastic, `C 2` là paper, `C 3` là organic;
  `other` trả `C 0` để không mở nhầm ngăn.
- Tensor arena 256 KiB được cấp một lần trong PSRAM.

Mỗi framebuffer được dùng cho cả input AI và JPEG telemetry, rồi trả lại camera
trước khi chạy TFLite `Invoke()` và trước khi gửi HTTP.
