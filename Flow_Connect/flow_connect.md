<h1><span style="color:#B30000">KIẾN TRÚC HỆ THỐNG THÙNG RÁC THÔNG MINH</span></h1>

---

<h2><span style="color:#0047AB">1. THIẾT BỊ: ARDUINO</span></h2>

**Gửi đến ESP32-CAM — Kích hoạt nhận diện AI**
- Mục đích: Báo có vật thể xuất hiện tại vùng chờ để bắt đầu chụp ảnh và phân loại.
- Dữ liệu gửi (UART): `T 1` — (Trigger)

**Gửi đến ESP32-CAM — Báo cáo dung tích thực tế của 3 ngăn riêng biệt**
- Mục đích: Gửi dữ liệu đo thời gian thực của cả 3 ngăn (Nhựa, Giấy, Hữu cơ) để ESP32-CAM đóng gói chính xác vào cấu trúc bản đồ (Map) trên Firestore.
- Dữ liệu gửi (UART): `F 20 80 65 ` — (Theo thứ tự cố định: Nhựa = 20%, Giấy = 80%, Hữu cơ = 65%)

- - -

**Nhận từ ESP32-CAM — Kết quả phân loại mở servo hoặc lệnh hủy do đầy**
- Mục đích: Lấy kết quả AI để điều khiển Servo mở đúng ngăn hoặc hủy lệnh nếu ngăn đó báo đầy.
- Dữ liệu nhận (UART):

| Mã lệnh | Ý nghĩa | Hành động |
|:---:|:---|:---|
| `C 1` | AI phân loại là Nhựa | Mở ngăn Nhựa |
| `C 2` | AI phân loại là Giấy | Mở ngăn Giấy |
| `C 3` | AI phân loại là Hữu cơ | Mở ngăn Hữu cơ |
| `C 0` / `<số khác trên>` | Lỗi thiết bị / Thùng đầy từ chối nhận | Bật led đỏ |

---

<h2><span style="color:#0047AB">2. THIẾT BỊ: ESP32-CAM</span></h2>

**Đồng bộ thời gian khởi động — Mạng NTP (esp_sntp)**
- Hành động: Đồng bộ thời gian thực từ máy chủ NTP tại thời điểm khởi động trước khi cho phép vòng lặp main loop chấp nhận các tín hiệu Trigger từ Arduino.
- Ý nghĩa: Đảm bảo trường device_timestamp đạt chuẩn xác thực của bộ lọc firestore.rules và phục vụ chính xác thuật toán gom cụm dữ liệu theo ngày tại Functions Backend.

- - -

**Nhận từ Arduino — Lệnh Trigger / Dữ liệu khoảng cách cảm biến**
- Dữ liệu nhận (UART): `T 1` hoặc `F nhua giay huu_co`

**Gửi đến Arduino — Trả kết quả phân loại tức thời**
- Dữ liệu gửi (UART): `C X` (X nhận các giá trị từ 0 đến 4)

- - -

**Gửi đến Cloud Firestore REST API — Ghi nhận nhật ký sự kiện (Event Logging kèm ID trong JSON)**
- Mục đích: Lưu trữ lịch sử phân loại CLASSIFY hoặc FULL_ALERT. Trường device_id được giữ lại trong JSON payload để phục vụ các câu lệnh truy vấn gom cụm (Collection Group Query).
- Đường dẫn REST: `POST .../projects/{project_id}/databases/(default)/documents/devices/{deviceId}/events`
- Định dạng dữ liệu gửi (Firestore REST API bắt buộc):
```json
{
  "fields": {
    "device_id": { "stringValue": "STBIN_HCMUS_001" },
    "event": { "stringValue": "CLASSIFY" },
    "waste_type": { "stringValue": "nhua" },
    "ai_confidence": { "doubleValue": 0.92 },
    "device_timestamp": { "timestampValue": "2026-07-19T15:20:00Z" },
    "firmware_version": { "stringValue": "v2.4-esp-idf" }
  }
}
```

**Gửi đến Cloud Firestore REST API — Cập nhật trạng thái vi mô từng ngăn (Telemetry Update)**
- Mục đích: Cập nhật chi tiết độ đầy của từng ngăn riêng biệt phục vụ giao diện Dashboard giám sát.
- Phương thức HTTP: `PATCH` (sử dụng tham số `updateMask.fieldPaths` để cập nhật sâu vào Map Object).
- Định dạng dữ liệu gửi (Firestore REST API sử dụng kiểu mapValue cho cấu trúc đa ngăn):
```json
{
  "fields": {
    "device_id": { "stringValue": "STBIN_HCMUS_001" },
    "status": { "stringValue": "online" },
    "last_seen_at": { "timestampValue": "2026-07-19T15:20:00Z" },
    "compartments": {
      "mapValue": {
        "fields": {
          "nhua": { "integerValue": 20 },
          "giay": { "integerValue": 80 },
          "huu_co": { "integerValue": 65 }
        }
      }
    }
  }
}
```

- - -

**Nhận từ Cloud Firestore REST API — Đọc cấu hình điều khiển vi mô từ xa**
- Mục đích: Lấy dữ liệu cấu hình riêng của thùng này về ngưỡng đầy (threshold) và chế độ bảo trì.
- Phương thức HTTP: `GET` trên tài liệu gốc của thiết bị: `.../devices/{deviceId}`

---

<h2><span style="color:#0047AB">3. HỆ THỐNG: CLOUD FIRESTORE REALTIME BACKEND</span></h2>

**Quy trình xác thực phần cứng riêng biệt — Custom Token Exchange Flow**
- Hành động: Thiết bị sử dụng DEVICE_ID kết hợp mã X-Provision-Secret để Backend cấp phát idToken ngắn hạn riêng biệt cho từng thùng, không dùng chung token.

- - -

**Nhận từ các thiết bị — Dữ liệu Telemetry & Logs từ hàng trăm Node**
- Mục đích: Phân định dữ liệu rõ ràng theo ID thiết bị dựa trên cấu trúc đường dẫn.
- Đường dẫn cấu trúc tài liệu lưu trữ (Firestore Collections):

| Đường dẫn | Nội dung |
|:---|:---|
| `/devices/{deviceId}` | Quản lý trạng thái, telemetry đa ngăn và cấu hình của từng thùng |
| `/devices/{deviceId}/events` | Bộ sưu tập sự kiện riêng biệt của từng thùng, phục vụ truy vấn báo cáo hiệu suất theo khu vực |

---