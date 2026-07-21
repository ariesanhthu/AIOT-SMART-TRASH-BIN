# FastAPI receiver cho ESP32-CAM

Server nhận ảnh JPEG và kết quả AI từ `ESP-TRASH`, lưu ảnh và metadata thành
file riêng. Swagger UI có tại `http://localhost:8000/docs`.

## Chạy server

```powershell
cd server-tmp
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python main.py
```

Server lắng nghe trên `0.0.0.0:8000` và in URL LAN dành cho ESP khi khởi động.
IP được xác minh trên Wi-Fi `AIoTSTB` ngày 2026-07-18 là `172.20.10.4`:

```text
ESP telemetry URL: http://172.20.10.4:8000/api/v1/detections
```

Nếu DHCP đổi IP, dùng URL mới server vừa in để sửa `kServerUrl` trong
`ESP-TRASH/network_config.h`. Windows Firewall phải cho phép Python nhận kết
nối TCP cổng 8000. ESP và máy phải ở cùng mạng không bật client isolation.

Kiểm tra server trước khi capture:

```powershell
curl.exe http://localhost:8000/health
curl.exe http://172.20.10.4:8000/health
```

Device token mặc định là `aiot-demo-token`, giống firmware. Có thể đổi phía
server trước khi chạy:

```powershell
$env:AIOT_DEVICE_TOKEN = "token-moi"
python main.py
```

Khi đổi token phải sửa cả `kDeviceToken` trong firmware.

## API

- `GET /health`: trạng thái server và số bản ghi.
- `POST /api/v1/detections`: nhận JPEG cùng các header kết quả AI.
- `GET /api/v1/detections?limit=20`: danh sách bản ghi mới nhất.
- `GET /api/v1/detections/{id}`: metadata của một bản ghi.
- `GET /api/v1/detections/{id}/image`: tải/xem ảnh JPEG.

Dữ liệu mặc định được lưu tại:

```text
server-tmp/data/images/{uuid}.jpg
server-tmp/data/metadata/{uuid}.json
```

Giới hạn ảnh mặc định là 1.5 MB. Có thể thay đổi qua
`AIOT_MAX_IMAGE_BYTES`. Thư mục lưu trữ có thể đổi qua `AIOT_DATA_DIR`.

## Test

```powershell
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

Firmware gửi body `image/jpeg` trực tiếp để không phải tạo thêm bản sao base64
hoặc multipart trong RAM của ESP32. Kết quả, confidence, ba xác suất, kích thước
ảnh, thời gian inference, device ID và model SHA-256 nằm trong HTTP headers.
