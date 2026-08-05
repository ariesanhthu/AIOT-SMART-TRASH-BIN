# Camera streaming trên website

Firmware giữ nguyên camera ở `QVGA/RGB565` cho pipeline AI và cung cấp thêm ba
endpoint:

| Endpoint | Chức năng |
| --- | --- |
| `http://esp-trash.local/health` | Kiểm tra HTTP server |
| `http://esp-trash.local/capture` | Chụp một ảnh JPEG, cổng 80 |
| `http://esp-trash.local:81/stream` | Luồng MJPEG, cổng 81 |

Sau khi ESP32 kết nối Wi-Fi, Serial Monitor 115200 baud sẽ in cả hostname và IP.
Nếu máy không phân giải được `esp-trash.local`, dùng IP được in trên Serial
Monitor.

## Cấu hình frontend khi chạy Vite

Mặc định Vite proxy tới `esp-trash.local`. Khi cần dùng IP, tạo
`frontend/.env.local` từ `frontend/.env.example` rồi sửa:

```dotenv
ESP32_CAMERA_URL=http://<IP-ESP32>
ESP32_STREAM_URL=http://<IP-ESP32>:81
```

Sau khi đổi file môi trường, khởi động lại `npm run dev`. Không đặt IP máy chạy
backend vào hai biến trên; đây phải là IP của chính ESP32-CAM.

Với frontend đã build và được phục vụ bởi một server khác, có thể cấu hình hai
biến `VITE_ESP32_CAMERA_URL` và `VITE_ESP32_STREAM_URL` trước khi chạy
`npm run build`. Firmware đã trả header CORS cho capture và stream. Trình duyệt
sẽ chặn kết nối nếu website chạy HTTPS nhưng ESP32 chỉ chạy HTTP; trong trường
hợp đó cần reverse proxy hai endpoint qua server HTTPS.

## Đồng thời với AI/Nano

Camera chỉ có một framebuffer. `CameraAdapter` dùng mutex gắn với
`CameraFrameLease`, nên lệnh từ Nano, capture website và MJPEG không thể sử dụng
framebuffer cùng lúc. Stream nhả framebuffer trước khi gửi JPEG qua mạng và bị
giới hạn khoảng 8 FPS để pipeline nhận diện vẫn có thời gian lấy camera.

Riêng inference dùng `CaptureFresh`: sau 2 giây settle, mutex được giữ liên tục
trong lúc bỏ frame đang chờ và chụp frame kế tiếp. Vì vậy web stream không thể
chen vào giữa thao tác flush và frame dùng cho model.
