# AIoT Smart Trash Bin

Hệ thống thùng rác thông minh sử dụng ESP32-CAM và mô hình TinyCNN INT8 để
nhận diện rác ngay trên thiết bị, Arduino Nano để điều khiển cơ cấu phân loại,
cảm biến siêu âm để đo mức đầy, cùng dashboard web để giám sát và cấu hình từ
xa.

## Chức năng chính

- Nhận diện bốn kết quả: không nhận diện được, nhựa, giấy và hữu cơ.
- Chạy suy luận cục bộ trên ESP32-CAM; chức năng phân loại vẫn hoạt động khi
  mất Internet.
- Điều khiển ba servo, bốn LED và bốn cảm biến siêu âm bằng Arduino Nano.
- Upload ảnh nhận diện lên Cloudinary và ghi sự kiện, mức đầy lên Firestore.
- Dashboard quản lý thiết bị, cảnh báo đầy, lịch sử phân loại, thống kê, cấu
  hình ngưỡng và camera trực tiếp.
- Backend REST dùng Spring Boot, Firebase Authentication và Firestore Admin
  SDK.

## Kiến trúc tổng quát

```text
Vật thể
  |
  v
Cảm biến kích hoạt -> Arduino Nano -- T 1 --> ESP32-CAM
                                              |
                                              +-> Camera + TinyCNN INT8
                                              |
Arduino Nano <-- C <0..3> --------------------+
  |
  +-> Servo phân loại + LED
  +-> Đo mức đầy ba ngăn -- F <p> <pa> <o> --> ESP32-CAM
                                                   |
                                                   +-> Cloudinary / Firestore

Dashboard React <-> Spring Boot REST API <-> Firebase Auth / Firestore
```

## Quy ước kết quả UART

ESP32-CAM trả về cho Arduino Nano theo định dạng `C <mã>`:

| Mã | Kết quả | Hành động |
| --- | --- | --- |
| `0` | Không nhận diện được / lỗi | Không mở ngăn |
| `1` | Nhựa (`plastic`) | Mở ngăn nhựa |
| `2` | Giấy (`paper`) | Mở ngăn giấy |
| `3` | Hữu cơ (`organic`) | Mở ngăn hữu cơ |

Giao tiếp Nano - ESP32-CAM dùng UART 9600 baud, 8N1. Chi tiết lệnh, phản hồi,
sơ đồ chân và cơ chế retry nằm trong [ESP-TRASH/README.md](ESP-TRASH/README.md).

## Cấu trúc thư mục

```text
AI/                              Pipeline dữ liệu, train, đánh giá và export model
ESP-TRASH/                       Firmware Arduino cho ESP32-CAM AI Thinker
arduino_esp_main_controller/     Firmware điều khiển chính cho Arduino Nano
arduino_ultrasonic_test/         Chương trình kiểm thử cảm biến siêu âm
backend/                         REST API Spring Boot + Firebase Admin SDK
frontend/                        Dashboard React 19 + TypeScript + Vite
docs/                            Đặc tả, kiến trúc, flowchart và báo cáo AI
postman/                         Bộ request kiểm thử API
server-tmp/                      Server FastAPI cục bộ để test nhận ảnh JPEG
firestore.rules                  Firestore Security Rules
firestore.indexes.json           Firestore indexes
```

## Chạy dashboard và backend

### Yêu cầu

- Java 21
- Node.js và npm
- Một Firebase project có Authentication và Firestore

### 1. Backend

Đặt Firebase service account tại
`backend/secrets/serviceAccountKey.json`, hoặc khai báo
`FIREBASE_CREDENTIALS_PATH`/`FIREBASE_CREDENTIALS_JSON`. Không commit khóa
service account.

```powershell
cd backend
$env:DEVICE_PROVISIONING_SECRET = "your-provisioning-secret"
$env:DEVICE_JWT_SECRET = "replace-with-a-secret-at-least-32-characters"
.\gradlew.bat bootRun
```

Backend mặc định chạy tại `http://localhost:8080`. Xem thêm
[backend/README.md](backend/README.md) và
[docs/docs_backend/API_GUIDE.md](docs/docs_backend/API_GUIDE.md).

### 2. Frontend

```powershell
cd frontend
Copy-Item .env.example .env.local
npm install
npm run dev
```

Điền cấu hình Firebase trong `.env.local` và thêm URL backend:

```dotenv
VITE_API_BASE_URL=http://localhost:8080
```

Các biến `ESP32_CAMERA_URL` và `ESP32_STREAM_URL` trong `.env.local` được Vite
dùng làm proxy khi phát triển. Truy cập URL mà Vite in ra, thường là
`http://localhost:5173`.

Lệnh kiểm tra frontend:

```powershell
npm run lint
npm run build
```

## Nạp firmware

### ESP32-CAM

1. Sao chép `ESP-TRASH/secrets.example.h` thành `ESP-TRASH/secrets.h`.
2. Điền Wi-Fi, Cloudinary và Firebase trong `secrets.h`.
3. Mở `ESP-TRASH/ESP-TRASH.ino` bằng Arduino IDE.
4. Chọn board `AI Thinker ESP32-CAM`, bật PSRAM và partition `Huge APP`.
5. Nối GPIO0 với GND khi upload; tháo GPIO0 rồi reset sau khi nạp xong.

### Arduino Nano

Mở `arduino_esp_main_controller/arduino_esp_main_controller.ino`, kiểm tra sơ
đồ chân ở đầu file rồi upload cho Nano. Có thể bỏ comment `#define TEST_MODE`
để kiểm tra servo, LED và cảm biến qua Serial Monitor mà không cần ESP32-CAM.

Lưu ý phần cứng: hai board phải chung GND; đường Nano TX sang ESP32 RX cần chia
áp; ESP32-CAM và servo cần nguồn 5 V ổn định, không nên lấy từ nguồn 3.3 V yếu.

## AI model

Firmware trong `ESP-TRASH/` hiện dùng model TinyCNN V6 full INT8 với đầu ra
`paper`, `plastic`, `organic`, `other`; lớp `other` được ánh xạ thành mã UART
`C 0`. Model nhận ảnh RGB `96 x 96` và chạy bằng TensorFlow Lite Micro/ESP-NN.

Pipeline ba lớp ổn định và các thử nghiệm model mới hơn được tách riêng trong
`AI/`. Đọc [AI/README.md](AI/README.md), [AI/V7/README.md](AI/V7/README.md) và
tài liệu triển khai tương ứng trước khi thay model trong firmware; byte array,
thứ tự nhãn và hợp đồng tiền xử lý phải luôn được cập nhật cùng nhau.

## Kiểm thử

Backend:

```powershell
cd backend
.\gradlew.bat test
```

Frontend:

```powershell
cd frontend
npm run lint
npm run build
```

FastAPI receiver dùng để kiểm thử ESP32-CAM độc lập:

```powershell
cd server-tmp
python -m pip install -r requirements-dev.txt
python -m pytest -q
python main.py
```

Swagger UI của receiver nằm tại `http://localhost:8000/docs`. Đây là công cụ
test cục bộ, không phải backend chính của dashboard.

## Tài liệu liên quan

- [Đặc tả yêu cầu](docs/TÀI_LIỆU_ĐẶC_TẢ%20_YÊU_CẦU.md)
- [Tài liệu kiến trúc](docs/architecture/Phan_tich_chuc_nang_toi_kien_truc.md)
- [Luồng kết nối phần cứng](Flow_Connect/flow_connect.md)
- [Flowchart các use case](docs/FLOWCHART/README.md)
- [Hướng dẫn API backend](docs/docs_backend/API_GUIDE.md)
- [Hướng dẫn firmware ESP32-CAM](ESP-TRASH/README.md)

## Bảo mật

Không commit `secrets.h`, Firebase service account, mật khẩu người dùng thiết
bị, provisioning secret hoặc JWT signing secret. Firebase Web API key có thể
được dùng ở frontend, nhưng service account key phải chỉ tồn tại ở backend.
