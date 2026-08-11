# ESP-TRASH-V3 - ESP32-CAM AI Thinker + Arduino Nano

Firmware chạy model TinyCNN V9 full INT8 cục bộ để phân loại `paper`, `plastic`
và `organic` với preprocessing giảm nhạy theo độ sáng và màu nguồn sáng.
Nano gửi lệnh chụp, ESP32-CAM trả kết quả qua UART ngay sau inference, sau đó
POST trực tiếp JPEG, kết quả AI và ba mức đầy vào Python server chạy trên máy.
Ảnh được lưu local và frontend tải lại từ chính server này; không dùng
Cloudinary, Spring backend hay Firebase trong đường chạy hiện tại.

## Cấu hình mạng

Firmware dùng `WIFI_SSID` và `WIFI_PASSWORD` trong file ignored `secrets.h`.
ESP và máy chạy Python server phải cùng Wi-Fi `AIoTSTB`. Cấu hình hiện tại:

```text
ESP32-CAM:       172.20.10.2
Python server:   172.20.10.4:8000
POST detection:  http://172.20.10.4:8000/api/v1/detections
```

Nếu DHCP đổi IP máy, sửa `kLocalServerHost` và `kServerUrl` trong
`network_config.h`, build rồi flash lại ESP.

Mất Wi-Fi không làm dừng AI: ESP khởi động UART/camera/model mà không chờ mạng,
vẫn nhận diện và trả Nano. Kết nối lại Wi-Fi chạy nền mỗi 15 giây. Nếu mạng đang
mất khi nhận `F`, ESP bỏ qua upload ngay; không lưu hàng đợi ảnh offline vì
RAM/flash của ESP32-CAM có giới hạn.

Ở lần boot đầu, sau khi camera/model sẵn sàng, ESP chỉ chờ Wi-Fi tối đa 5 giây.
Nếu Wi-Fi đã kết nối thì đi tiếp ngay, không probe/chờ Python server lúc boot.
Kết nối server chỉ được thử khi có một ảnh hoàn chỉnh cần upload. ESP không tự phát
`R 1`; sau khi boot xong nó chỉ trả trạng thái khi Nano gửi probe `H 1`, tránh
để một gói ready cũ chen vào transaction.
Nếu server chưa sẵn sàng, AI local tiếp tục hoạt động và firmware thử gửi lại ở
transaction kế tiếp.

## Mở và nạp bằng Arduino IDE

1. Mở `ESP-TRASH-V3.ino` bằng Arduino IDE.
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
| `A T\n` | Đã nhận trigger; chờ vật ổn định 2 giây rồi chụp frame mới |
| `C 0\n` | Lỗi pipeline/model; Nano không định tuyến vào ngăn |
| `C 1\n` | Nhựa (`plastic`) |
| `C 2\n` | Giấy (`paper`) |
| `C 3\n` | Hữu cơ (`organic`) |
| `A F\n` | Đã nhận đủ ba mức đầy từ Nano |
| `D 1\n` | Python server đã nhận và lưu ảnh; ESP đã rảnh |
| `D 0\n` | Gửi server local thất bại nhưng ESP đã rảnh |

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
ESP POST JPEG + metadata tới Python server local
Nano <- D <0|1> ------- ESP
```

Nano chỉ trigger sau `R 1`, có thể gửi lại `T` nếu mất ACK nhưng chỉ gửi `F`
đúng một lần để không vô tình tạo lại ảnh/event. Nano luôn gửi `F` kể cả khi
nhận `C 0`. ESP bỏ qua trigger lặp khi transaction đang chạy, do đó gói retry
không tạo thêm lần chụp ngoài ý muốn. JPEG POST theo chính sách one-shot; Nano
nhận `D 0` khi server không trả HTTP 2xx.

## LED AI trên Arduino Nano

| Trạng thái | Hiển thị |
| --- | --- |
| `LOADING` | Bật/tắt luân phiên mỗi 1 giây khi khởi động, chụp, inference hoặc gửi server |
| `READY` | Sáng liên tục khi hệ thống sẵn sàng |
| `ERROR` | Nhấp nháy nhanh liên tục (150 ms) khi UART/AI lỗi hoặc nhận `C 0` |
| `OFF` | Tắt khi hệ thống không có điện |

Server lỗi hoặc không có Wi-Fi không làm mất kết quả phân loại cục bộ. Với
`C 1..3`, Nano vẫn điều khiển LED/ngăn tương ứng và chuyển về `READY` sau khi
transaction kết thúc. Với `C 0`, LED AI giữ `ERROR` cho tới lượt xử lý mới.

Serial Monitor 115200 baud test được toàn bộ local pipeline:

1. Nhập `1` hoặc `T 1` để chụp và phân loại.
2. Sau khi thấy `Test result`, nhập `F 10 10 10` theo thứ tự nhựa, giấy, hữu cơ.
3. Firmware POST JPEG và metadata tới Python server. Server lưu file ảnh,
   tạo event `CLASSIFY` và tự sinh `FULL_ALERT` khi mức đầy vượt ngưỡng.

Firmware chờ lệnh `F` tối đa 60 giây khi test Monitor. Lệnh `WIFI_RESET` vẫn
giữ nguyên.

## Đồng bộ qua Python server local

Ảnh QVGA RGB565 dùng cho AI được chuyển thành JPEG quality 80 rồi POST trực tiếp
tới `server-tmp` dưới dạng body `image/jpeg`. Kết quả, confidence, xác suất,
firmware/model version và ba mức đầy nằm trong HTTP headers. Server lưu JPEG ở
`server-tmp/data/images` và metadata ở `server-tmp/data/metadata`; frontend đọc
ảnh qua `/api/v1/detections/{id}/image` với `Cache-Control: no-store`.

## Pipeline AI

- Model nguồn: `AI/V9/artifacts/model_int8.tflite`, 62,560 byte, SHA-256
  `851054bd0256a3173aa69a2dee733f059d14651271e684be06bc750cf8564253`.
- Input INT8 `[1, 96, 96, 3]`, RGB, scale `1/255`, zero point `-128`.
- Output INT8 `[1, 3]`, scale `1/256`, zero point `-128`:
  `paper`, `plastic`, `organic`.
- QVGA RGB565 -> center crop -> nearest-neighbor floor 96 x 96 -> gray-world
  white balance Q10 giới hạn `[768,1365]` -> mean-luma Q8 giới hạn
  `[192,341]` -> quantize. Đây là đúng thứ tự preprocessing V9 lúc train,
  validation, test và representative calibration.
- TFLite Micro/ESP-NN chạy `CONV_2D`, `MEAN`, `FULLY_CONNECTED`, `SOFTMAX`.
- Mapping UART: `C 1` là plastic, `C 2` là paper, `C 3` là organic; lỗi pipeline
  trả `C 0`.
- Tensor arena 256 KiB được cấp một lần trong PSRAM.
- Test giữ kín 21 ảnh: float `19/21` (90,48%), INT8 `19/21` (90,48%), không
  có ảnh nào đổi nhãn sau quantize. Tập test
  vẫn chỉ thuộc phiên chụp 2026-08-01 nên chưa thay thế kiểm thử phiên chụp mới.

### Chống dùng lại frame cũ

Camera dùng một framebuffer và `CAMERA_GRAB_WHEN_EMPTY`, nên frame đầu tiên trong
queue có thể được chụp trước trigger. Với mỗi `T 1`, firmware hiện thực hiện:

1. ACK `A T` ngay cho Nano.
2. Chờ `2000 ms` để vật đi vào vùng camera và ổn định.
3. Ghi mốc thời gian, giữ camera mutex và bỏ một frame đang chờ.
4. Chỉ nhận frame có timestamp sau mốc đó; frame cũ tiếp tục bị trả về driver.
5. Dùng đúng frame mới đó cho cả preprocessing AI và JPEG telemetry.

Serial Monitor in sequence, thời gian từ trigger tới frame, timestamp/tuổi frame,
hash ảnh RGB565, hash tensor input và cờ `same_raw`/`same_input`. Xem quy trình
test trong `CAPTURE_FRESHNESS_DEBUG.md`.

Mỗi framebuffer được dùng cho cả input AI và JPEG telemetry, rồi trả lại camera
trước khi chạy TFLite `Invoke()` và trước khi gửi HTTP.
