# Python server local cho Smart Trash Bin

Server này thay đường chạy Spring Boot/Firebase/Cloudinary khi demo local:

```text
ESP32-CAM --JPEG + kết quả AI + mức đầy--> Python server --> frontend
```

Ảnh và metadata được lưu trực tiếp trên máy:

```text
server-tmp/data/images/{uuid}.jpg
server-tmp/data/metadata/{uuid}.json
server-tmp/data/dashboard_state.json
```

## Mạng đang dùng

ESP và máy tính cùng kết nối Wi-Fi `AIoTSTB`:

- Máy chạy server: `172.20.10.4`
- ESP32-CAM: `172.20.10.2`
- API nhận ảnh: `http://172.20.10.4:8000/api/v1/detections`
- Frontend: `http://172.20.10.4:5173`

Nếu DHCP đổi IP của máy, sửa `kLocalServerHost` và `kServerUrl` trong
`ESP-TRASH-V3/network_config.h`, rồi build/flash lại ESP.

## Chạy server

```powershell
cd server-tmp
python -m pip install -r requirements.txt
python main.py
```

Server lắng nghe trên `0.0.0.0:8000`. Kiểm tra từ máy và qua IP LAN:

```powershell
curl.exe http://localhost:8000/health
curl.exe http://172.20.10.4:8000/health
```

Device token mặc định là `aiot-demo-token`, trùng với firmware. Có thể đổi
server qua biến môi trường `AIOT_DEVICE_TOKEN`, nhưng khi đổi phải cập nhật
`kDeviceToken` trong firmware.

## API tương thích frontend

- `GET /api/devices`
- `GET /api/devices/{deviceId}`
- `GET/PATCH /api/devices/{deviceId}/config`
- `GET /api/devices/{deviceId}/events`
- `PATCH /api/devices/{deviceId}/events/{eventId}/resolve`
- `GET /api/daily-stats`
- `GET /api/daily-stats/summary`
- `GET /api/daily-stats/ranking`

API ảnh trực tiếp từ ESP:

- `POST /api/v1/detections`: body JPEG; metadata nằm trong HTTP headers.
- `GET /api/v1/detections?limit=20`: danh sách nhận diện mới nhất.
- `GET /api/v1/detections/{id}/image`: web tải ảnh local, có `no-store` để
  không giữ nhầm ảnh cũ trong cache.

Server tự tạo event `CLASSIFY`, cảnh báo `FULL_ALERT`, thống kê ngày và xếp
hạng từ các detection đã lưu. Ngưỡng và trạng thái cảnh báo đã xử lý được lưu
trong `dashboard_state.json`, nên restart server không làm mất cấu hình.

## Frontend

`frontend/.env` đã trỏ `BACKEND_URL=http://localhost:8000`. Vite proxy `/api`
sang Python server, vì vậy URL ảnh `/api/v1/detections/{id}/image` hoạt động
cả khi mở frontend bằng `localhost` lẫn IP LAN.

```powershell
cd frontend
npm install
npm run dev -- --host 0.0.0.0
```

## Test

```powershell
python -m pip install -r requirements-dev.txt
python -m pytest -q
python -m ruff check main.py tests
```
