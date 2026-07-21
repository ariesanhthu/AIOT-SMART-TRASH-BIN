# Luồng kết nối, input/output và giao tiếp hệ thống

Tài liệu này note lại các cách kết nối hiện có/cần có giữa Frontend, Backend, Firestore, Cloud Functions và ESP32 cho phần Dashboard - thông báo - thống kê - cấu hình thiết bị. Mục tiêu là để team merge code và nối contract đúng nhau.

## 1. Tổng quan kiến trúc đang dùng

```text
Dashboard React
  -> gọi REST API kèm Firebase ID Token
  -> Spring Boot Backend
  -> Firebase Admin SDK đọc/ghi Firestore

ESP32/Firmware
  -> xin custom token từ Backend bằng provisioning secret
  -> đổi custom token lấy Firebase ID Token
  -> đọc/ghi Firestore trực tiếp bằng Firestore REST/SDK

Cloud Functions
  -> lắng nghe event mới trong devices/{deviceId}/events
  -> cập nhật daily_stats và trạng thái full của compartment
```

Backend dùng Admin SDK nên bypass Firestore Security Rules. Dashboard không đọc/ghi Firestore trực tiếp. ESP32 là client duy nhất được truy cập Firestore trực tiếp và bị giới hạn theo `device_id` trong Security Rules.

## 2. Dashboard -> Backend REST API

Tất cả request từ Dashboard đi qua `VITE_API_BASE_URL` trong frontend và có header:

```http
Authorization: Bearer <Firebase ID Token>
Content-Type: application/json
```

Ngoại lệ: endpoint cấp token cho ESP32 không dùng Firebase ID Token của user, mà dùng `X-Provision-Secret`.

### 2.1 GET /api/devices

Mục đích: Dashboard lấy danh sách thùng và trạng thái hiện tại.

Frontend gọi:

```ts
fetchAllBins() -> GET /api/devices
```

Backend đọc:

```text
Firestore collection: devices
```

Response:

```json
[
  {
    "deviceId": "bin-a1",
    "name": "Bin A1",
    "location": "Tang 1",
    "lastSeenAt": "2026-07-19T08:30:00Z",
    "maintenanceMode": false,
    "firmwareVersion": "1.0.0",
    "aiModelVersion": "trashnet-tflite-v1.2",
    "compartments": {
      "organic": { "threshold": 80, "fillPercent": 42, "status": "normal" },
      "paper": { "threshold": 80, "fillPercent": 70, "status": "normal" },
      "plastic": { "threshold": 85, "fillPercent": 91, "status": "full" }
    }
  }
]
```

Frontend mapping:

- `deviceId` -> `Bin.id`
- `name` -> `Bin.name`
- `location` -> `Bin.location`
- `lastSeenAt` -> tính `online` tạm thời nếu cập nhật trong 5 phút gần nhất
- `compartments.*.fillPercent` -> phần trăm đầy của từng ngăn
- `compartments.*.threshold` -> ngưỡng báo đầy của từng ngăn

Trang đang dùng: Dashboard, Bin Detail, Statistics, Alerts.

### 2.2 GET /api/devices/{deviceId}

Mục đích: lấy chi tiết 1 thiết bị, đặc biệt dùng để đọc threshold khi cần cấu hình.

Input:

```text
Path param:
- deviceId: string
```

Response: giống 1 item trong `GET /api/devices`.

Trang/service liên quan:

```ts
fetchBinThresholds(deviceId)
```

Trang `ConfigPage` hiện chưa gọi service này, vẫn dùng mock `THRESHOLDS`.

### 2.3 PATCH /api/devices/{deviceId}/config

Mục đích: Dashboard cập nhật cấu hình thiết bị từ xa.

Input:

```text
Path param:
- deviceId: string

Body:
{
  "thresholds": {
    "organic": 80,
    "paper": 85,
    "plastic": 90
  },
  "maintenanceMode": false
}
```

Có thể gửi một phần:

```json
{
  "thresholds": { "plastic": 85 }
}
```

Backend ghi Firestore:

```text
devices/{deviceId}.compartments.{type}.threshold
devices/{deviceId}.maintenance_mode
devices/{deviceId}.last_config_updated_by
devices/{deviceId}.last_config_updated_at
```

Response:

```http
204 No Content
```

Trang/service liên quan:

```ts
updateDeviceConfig(deviceId, body)
```

Tình trạng merge: service frontend đã có, backend endpoint đã có, nhưng `ConfigPage` chưa nối vào API thật.

### 2.4 GET /api/devices/{deviceId}/events

Mục đích: lấy lịch sử event của 1 thiết bị.

Input:

```text
Path param:
- deviceId: string

Query params:
- eventType?: CLASSIFY | FULL_ALERT | ERROR | MAINTENANCE
- limit?: number, mặc định 50
```

Ví dụ:

```http
GET /api/devices/bin-a1/events?eventType=CLASSIFY&limit=20
GET /api/devices/bin-a1/events?eventType=FULL_ALERT&limit=50
```

Backend query:

```text
devices/{deviceId}/events
  orderBy device_timestamp desc
  where event_type == eventType nếu có
  limit N
```

Response:

```json
[
  {
    "id": "event-001",
    "eventType": "CLASSIFY",
    "wasteType": "paper",
    "targetCompartment": "paper",
    "aiConfidence": 0.92,
    "fillPercent": {
      "organic": 42,
      "paper": 71,
      "plastic": 30
    },
    "alertThreshold": 0.8,
    "deviceTimestamp": "2026-07-19T08:30:00Z",
    "receivedAt": "2026-07-19T08:30:03Z",
    "syncedLate": false,
    "firmwareVersion": "1.0.0",
    "aiModelVersion": "trashnet-tflite-v1.2"
  }
]
```

Frontend đang dùng:

- `CLASSIFY` -> bảng lịch sử phân loại ở Bin Detail.
- `FULL_ALERT` -> trang Alerts và hộp cảnh báo gần đây ở Dashboard.

Lưu ý prototype: trang Alerts chỉ đánh dấu `resolved` ở local state frontend, backend chưa có entity/lifecycle alert thật.

### 2.5 GET /api/daily-stats

Mục đích: lấy thống kê phân loại theo ngày cho 1 thiết bị.

Input:

```text
Query params:
- deviceId: string
- from: yyyy-MM-dd
- to: yyyy-MM-dd
```

Ví dụ:

```http
GET /api/daily-stats?deviceId=bin-a1&from=2026-07-13&to=2026-07-19
```

Backend query:

```text
daily_stats
  where device_id == deviceId
  where date >= from
  where date <= to
  orderBy date asc
```
```json
[
  {
    "deviceId": "bin-a1",
    "date": "2026-07-19",
    "organicCount": 5,
    "paperCount": 8,
    "plasticCount": 3,
    "totalCount": 16
  }
]
```

Frontend đang dùng: `StatisticsPage` lấy 7 ngày gần nhất của 1 thiết bị đang chọn.

Lưu ý cần bổ sung: `firestore.indexes.json` hiện chưa có composite index `daily_stats(device_id asc, date asc)`, trong khi design doc đã đề xuất index này.

## 3. ESP32 -> Backend -> Firebase Auth

### 3.1 POST /api/devices/{deviceId}/auth-token

Mục đích: ESP32 xin Firebase custom token để đăng nhập vào Firebase bằng danh tính thiết bị.

Input:

```http
POST /api/devices/{deviceId}/auth-token
X-Provision-Secret: <PROVISION_SECRET>
```

Body: không cần.

Backend xử lý:

- So sánh `X-Provision-Secret` với `device.provisioning.secret`.
- Tạo Firebase custom token với UID = `deviceId`.
- Gắn custom claim: `{ "device_id": deviceId }`.

Response:

```json
{
  "deviceId": "bin-a1",
  "customToken": "<firebase-custom-token>"
}
```

### 3.2 ESP32 đổi custom token lấy idToken

ESP32 gọi Firebase Identity Toolkit:

```http
POST https://identitytoolkit.googleapis.com/v1/accounts:signInWithCustomToken?key=<FIREBASE_WEB_API_KEY>
Content-Type: application/json
```

Body:

```json
{
  "token": "<firebase-custom-token>",
  "returnSecureToken": true
}
```

Response Firebase:

```json
{
  "idToken": "<firebase-id-token>",
  "refreshToken": "<refresh-token>",
  "expiresIn": "3600"
}
```

Sau đó ESP32 dùng:

```http
Authorization: Bearer <firebase-id-token>
```

để đọc/ghi Firestore trực tiếp.

## 4. ESP32 -> Firestore trực tiếp

### 4.1 Cập nhật trạng thái hiện tại

Mục đích: cập nhật mức đầy, last seen, version firmware/model.

Firestore path:

```text
devices/{deviceId}
```

Dữ liệu thiết bị được phép update:

```json
{
  "last_seen_at": "<server/device timestamp>",
  "firmware_version": "1.0.0",
  "ai_model_version": "trashnet-tflite-v1.2",
  "compartments": {
    "organic": { "fill_percent": 42, "status": "normal", "threshold": 80 },
    "paper": { "fill_percent": 71, "status": "normal", "threshold": 80 },
    "plastic": { "fill_percent": 91, "status": "full", "threshold": 85 }
  }
}
```

Security Rules yêu cầu:

- `request.auth.token.device_id == deviceId`
- Device không được sửa `threshold`.
- Device không được sửa `maintenance_mode`.
- Device không được tạo/xóa document device.

Lưu ý: vì Firestore Rules đang so sánh `threshold` trước/sau, firmware khi update `compartments` cần giữ lại field `threshold` hiện có, tránh update để mất field.

### 4.2 Tạo event phân loại

Firestore path:

```text
devices/{deviceId}/events/{eventId}
```

Input event:

```json
{
  "event_type": "CLASSIFY",
  "waste_type": "paper",
  "target_compartment": "paper",
  "ai_confidence": 0.92,
  "fill_percent": {
    "organic": 42,
    "paper": 71,
    "plastic": 30
  },
  "alert_threshold": 0.8,
  "device_timestamp": "<timestamp do firmware gán>",
  "received_at": "<serverTimestamp>",
  "synced_late": false,
  "firmware_version": "1.0.0",
  "ai_model_version": "trashnet-tflite-v1.2"
}
```

Output trực tiếp: Firestore tạo document mới. Cloud Function sẽ xử lý side effect.

### 4.3 Tạo event cảnh báo đầy

Input event:

```json
{
  "event_type": "FULL_ALERT",
  "waste_type": null,
  "target_compartment": "plastic",
  "ai_confidence": null,
  "fill_percent": {
    "organic": 42,
    "paper": 71,
    "plastic": 91
  },
  "alert_threshold": 0.85,
  "device_timestamp": "<timestamp do firmware gán>",
  "received_at": "<serverTimestamp>",
  "synced_late": false,
  "firmware_version": "1.0.0",
  "ai_model_version": "trashnet-tflite-v1.2"
}
```

Cloud Function sau đó cập nhật:

```text
devices/{deviceId}.compartments.plastic.status = "full"
```

### 4.4 Đọc cấu hình từ xa

Firestore path:

```text
devices/{deviceId}
```

ESP32 đọc các field:

```json
{
  "maintenance_mode": false,
  "compartments": {
    "organic": { "threshold": 80 },
    "paper": { "threshold": 80 },
    "plastic": { "threshold": 85 }
  }
}
```

Cơ chế theo design hiện tại:

- Đọc piggyback sau mỗi lần ghi event/trạng thái.
- Đọc heartbeat mỗi 30-60 giây nếu lâu không có event.

Đánh đổi: không đảm bảo cấu hình áp dụng trong <= 7 giây ở mọi trường hợp nếu không thêm MQTT/SSE/push.

## 5. Cloud Functions side effects

Trigger:

```text
onCreate devices/{deviceId}/events/{eventId}
```

Nếu `event_type == "CLASSIFY"` và `waste_type` hợp lệ:

```text
daily_stats/{deviceId}_{yyyy-mm-dd}
  device_id = deviceId
  date = yyyy-mm-dd lấy từ device_timestamp
  {waste_type}_count += 1
  total_count += 1
```

Nếu `event_type == "FULL_ALERT"` và `target_compartment` hợp lệ:

```text
devices/{deviceId}.compartments.{target_compartment}.status = "full"
```

Lưu ý: function hiện chưa set giá trị mặc định `organic_count`, `paper_count`, `plastic_count` về 0. Backend đã fallback `null -> 0` khi trả DTO, nên dashboard vẫn đọc được.

## 6. Trạng thái merge hiện tại

| Hạng mục | Trạng thái | Ghi chú |
|---|---|---|
| Frontend đọc danh sách device | Đã nối backend | `useBins` -> `GET /api/devices` |
| Frontend đọc lịch sử CLASSIFY | Đã nối backend | `useClassifyHistory` -> event API |
| Frontend đọc FULL_ALERT | Đã nối backend | `useFullAlerts` -> event API, resolve local |
| Frontend đọc daily stats | Đã nối backend | `StatisticsPage` -> `GET /api/daily-stats` |
| Frontend cập nhật threshold/config | Chưa nối vào UI | Service đã có, `ConfigPage` vẫn mock/toast |
| Dashboard realtime <= 5 giây | Chưa đảm bảo | Hook fetch 1 lần, chưa polling/listener |
| ESP32 auth token | Đã có backend endpoint | Cần firmware gọi đúng flow custom token |
| ESP32 ghi Firestore trực tiếp | Đã có rules/function hỗ trợ | Cần firmware dùng đúng schema |
| `daily_stats` index | Thiếu trong config hiện tại | Cần thêm composite index `device_id ASC, date ASC` |
```