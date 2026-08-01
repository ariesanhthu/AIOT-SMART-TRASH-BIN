# LUỒNG KẾT NỐI THÙNG RÁC THÔNG MINH

## 1. Luồng thật với Arduino Nano

Giao tiếp UART2 dùng 9600 baud, mỗi lệnh kết thúc bằng `\n`.

| Chiều | Lệnh | Ý nghĩa |
|---|---|---|
| Nano → ESP32-CAM | `T 1` | Chụp ảnh và chạy AI |
| ESP32-CAM → Nano | `C 0..3` | 0=lỗi, 1=plastic, 2=paper, 3=organic |
| Nano → ESP32-CAM | `F plastic paper organic` | Mức đầy phần trăm của ba ngăn |

Ví dụ:

```text
Nano -> ESP: T 1
ESP  -> Nano: C 2
Nano -> ESP: F 10 10 10
```

ESP giữ JPEG của lần nhận diện trong RAM sau khi trả `C 2`. Chỉ khi nhận được
`F 10 10 10` của cùng chu kỳ, ESP mới bắt đầu đồng bộ cloud.

## 2. Test end-to-end bằng Serial Monitor

Mở Serial Monitor ở 115200 baud và chọn line ending có newline.

1. Nhập `T 1` hoặc `1`.
2. Chờ kết quả AI và dòng yêu cầu nhập mức đầy.
3. Nhập `F 10 10 10`.
4. Theo dõi lần lượt các log Cloudinary và Firestore.

Serial Monitor dùng cùng parser và cùng cloud pipeline với Nano. Khác biệt duy
nhất là kết quả `C x` chỉ được in ra Monitor, không gửi qua UART2.

## 3. Luồng Cloudinary và Firestore

```text
T 1
  -> ESP chụp JPEG + chạy AI
  -> trả/in C x
F plastic paper organic
  -> POST multipart JPEG tới Cloudinary
  -> nhận secure_url
  -> Firebase Authentication lấy ID token
  -> POST documents:commit (device update + event create)
```

ESP gọi trực tiếp Cloudinary và Cloud Firestore qua HTTPS, không qua backend.

Nếu Cloudinary không trả về `secure_url`, firmware vẫn gửi event với
`image_url: null` và in lỗi HTTP để có thể chẩn đoán riêng phần upload ảnh.

### 3.1 Upload ảnh Cloudinary

Endpoint:

```text
POST https://api.cloudinary.com/v1_1/{cloud_name}/image/upload
Content-Type: multipart/form-data
```

Multipart body gồm:

| Field | Nội dung |
|---|---|
| `upload_preset` | Unsigned upload preset |
| `file` | JPEG đã dùng cho lần nhận diện |

Firmware lấy trường `secure_url` từ JSON response và dùng giá trị đó làm
`image_url` trong event Firestore.

### 3.2 Atomic commit lên Firestore

Endpoint:

```text
POST projects/{projectId}/databases/(default)/documents:commit
```

Một commit chứa hai write: cập nhật `devices/{deviceId}` với `updateMask`, và
tạo `devices/{deviceId}/events/{eventId}` với precondition `exists=false`.
Firestore áp dụng cả hai write hoặc không áp dụng write nào, tránh lệch giữa
trạng thái thiết bị và lịch sử event.

Device write chỉ cập nhật các trường telemetry:

```json
{
  "last_seen_at": "2026-07-21T10:20:30Z",
  "firmware_version": "v3.0-arduino",
  "ai_model_version": "waste_v3_int8",
  "class_name": "paper",
  "compartments": {
    "organic": {
      "fill_percent": 10.0,
      "status": "normal"
    },
    "paper": {
      "fill_percent": 10.0,
      "status": "normal"
    },
    "plastic": {
      "fill_percent": 10.0,
      "status": "normal"
    }
  }
}
```

`threshold`, `maintenance_mode`, `name` và `location` không bị ghi đè.

Event write được ghi đúng schema:

```json
{
  "event_type": "CLASSIFY",
  "waste_type": "paper",
  "target_compartment": "paper",
  "ai_confidence": 0.92,
  "fill_percent": {
    "organic": 10.0,
    "paper": 10.0,
    "plastic": 10.0
  },
  "alert_threshold": 80.0,
  "device_timestamp": "2026-07-21T10:20:30Z",
  "received_at": "2026-07-21T10:20:30Z",
  "synced_late": false,
  "firmware_version": "v3.0-arduino",
  "ai_model_version": "waste_v3_int8",
  "alert_status": null,
  "resolved_at": null,
  "resolved_by": null,
  "image_url": "https://res.cloudinary.com/.../image/upload/...jpg"
}
```

Trên wire, firmware bọc từng giá trị bằng kiểu của Firestore REST API như
`stringValue`, `doubleValue`, `timestampValue`, `booleanValue` và
`mapValue`.

## 4. Xác thực và quyền ghi

Firmware đăng nhập bằng `FIREBASE_USER_EMAIL` và
`FIREBASE_USER_PASSWORD` rồi dùng Firebase ID token để ghi Firestore.

ID token cuối cùng phải có custom claim `device_id` trùng
`FIREBASE_DEVICE_ID`. Firestore Rules chỉ cho thiết bị:

- đọc và cập nhật đúng `devices/{deviceId}`;
- cập nhật các trường telemetry được cho phép;
- tạo event mới trong `devices/{deviceId}/events`;
- không sửa hoặc xóa event cũ;
- không sửa `threshold` và `maintenance_mode`.

## 5. Log mong đợi khi test

```text
Test command received from Serial Monitor
Test result: 2
Enter F <plastic> <paper> <organic> to continue cloud sync
Monitor fill levels plastic=10 paper=10 organic=10
Cloudinary upload complete: ... JPEG bytes
Cloudinary secure_url: https://res.cloudinary.com/...
Firebase direct authentication ready
Firestore direct commit: HTTP 200, event=evt_...
```

Mọi status trong khoảng `200..299` được firmware xem là thành công. Khi lỗi,
firmware in tối đa 300 ký tự đầu của Firestore error response để chẩn đoán.
