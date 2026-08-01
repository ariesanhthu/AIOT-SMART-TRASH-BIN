# API Guide — AIoT Smart Trash Bin
## 1. Kiến trúc tổng quan

```text
Dashboard (React)
  --Firebase ID Token-->
  Backend (Spring Boot)
  --Firebase Admin SDK-->
  Firestore

ESP32 / Firmware
  --X-Provision-Secret-->            POST /api/devices/{deviceId}/auth-token
  <--Device JWT--
  --Device JWT (Bearer)-->           POST /api/devices/{deviceId}/events
  --(open, không cần token)-->       GET  /api/devices/{deviceId}/config
  Backend
  --Firebase Admin SDK-->
  Firestore
```

Điểm khác biệt lớn nhất so với thiết kế cũ:

| | Cũ (ESP32 -> Firestore thẳng) | Mới (ESP32 -> Backend -> Firestore) |
|---|---|---|
| Ghi event | ESP32 tự ghi vào `devices/{id}/events` | ESP32 `POST /api/devices/{id}/events`, Backend ghi Firestore |
| Cập nhật trạng thái/fill_percent | ESP32 tự ghi `devices/{id}` | Backend cập nhật khi xử lý event (tuỳ service impl) |
| Side effect (daily_stats, status=full) | Cloud Functions `onCreate` | `DailyStatsAggregationJob` (Spring `@Scheduled`, poll `events` collectionGroup, checkpoint theo `received_at`) |
| Đọc config | ESP32 đọc Firestore trực tiếp | ESP32 `GET /api/devices/{id}/config` (open, không auth) |
| Auth cho ESP32 | Firebase custom token -> ID token, dùng để ghi Firestore | Device token riêng (JWT do Backend cấp), dùng để gọi REST API — **không phải Firebase ID token** |
| Security Rules Firestore | Phải giới hạn theo `device_id` claim | Không còn cần thiết cho ESP32 (ESP32 không chạm Firestore); chỉ Backend (Admin SDK) chạm Firestore |

Hai tầng auth song song ở Backend:
- **FirebaseAuthFilter**: xác thực Dashboard bằng Firebase ID Token, set attribute `email` vào request.
- **DeviceTokenFilter**: xác thực ESP32 bằng Device JWT (do chính Backend cấp qua `/auth-token`), riêng biệt với Firebase.

---

## 2. Luồng ESP32

### 2.1 Xin Device Token — `POST /api/devices/{deviceId}/auth-token`

Dùng khi thiết bị mới provisioning hoặc token hết hạn.

```http
POST /api/devices/bin-a1/auth-token
X-Provision-Secret: <PROVISION_SECRET của device này>
```

Không cần body.

Response (ví dụ):

```json
{
  "deviceId": "bin-a1",
  "token": "<device JWT>",
  "expiresIn": 3600
}
```

Lưu ý:
- Secret so sánh với `device.provisioning.secret` lưu ở Firestore/DB.
- Token trả về là JWT riêng của hệ thống (không phải Firebase ID token) — dùng cho các request tiếp theo.
- Vì endpoint dùng shared secret qua header, nên có rate-limit/log lại các lần gọi để phát hiện brute-force.

### 2.2 Ingest Event — `POST /api/devices/{deviceId}/events`

```http
POST /api/devices/bin-a1/events
Authorization: Bearer <device JWT>
Content-Type: application/json
```

Body (CLASSIFY):

```json
{
  "eventType": "CLASSIFY",
  "wasteType": "paper",
  "targetCompartment": "paper",
  "aiConfidence": 0.92,
  "fillPercent": { "organic": 42, "paper": 71, "plastic": 30 },
  "alertThreshold": 0.8,
  "deviceTimestamp": "2026-07-19T08:30:00Z",
  "firmwareVersion": "1.0.0",
  "aiModelVersion": "trashnet-tflite-v1.2"
}
```

Body (FULL_ALERT):

```json
{
  "eventType": "FULL_ALERT",
  "targetCompartment": "plastic",
  "fillPercent": { "organic": 42, "paper": 71, "plastic": 91 },
  "alertThreshold": 0.85,
  "deviceTimestamp": "2026-07-19T08:30:00Z",
  "firmwareVersion": "1.0.0",
  "aiModelVersion": "trashnet-tflite-v1.2"
}
```

Response: `201 Created` + `EventResponse` (event vừa tạo, kèm `id`, `receivedAt` server-side).

Backend xử lý (đề xuất, tuỳ implementation thực tế của `EventService`):
- Auth bằng `DeviceTokenFilter` -> lấy `deviceId` từ token, đối chiếu với path `deviceId`.
- Ghi vào Firestore `devices/{deviceId}/events/{eventId}` bằng Admin SDK.
- Cập nhật `devices/{deviceId}.compartments.*.fill_percent` / `status` nếu event ảnh hưởng trạng thái hiện tại.
- Daily stats KHÔNG cập nhật ngay tại đây — việc này do `DailyStatsAggregationJob` polling định kỳ đảm nhiệm (không còn Cloud Functions).

### 2.3 Đọc Config — `GET /api/devices/{deviceId}/config`

```http
GET /api/devices/bin-a1/config
```

- **Open**, không cần token (nhất quán với `FirebaseAuthFilter`/`DeviceTokenFilter` policy loại trừ path này).
- Response:

```json
{
  "thresholds": { "organic": 80, "paper": 80, "plastic": 85 },
  "maintenanceMode": false
}
```

Cơ chế polling đề xuất: đọc piggyback sau mỗi lần POST event, hoặc heartbeat 30–60s nếu lâu không có event. Không đảm bảo áp dụng config trong ≤7s nếu không có thêm cơ chế push (MQTT/SSE) — vẫn là đánh đổi như thiết kế cũ.

---

## 3. Luồng Dashboard

Tất cả gọi kèm:

```http
Authorization: Bearer <Firebase ID Token>
Content-Type: application/json
```

### 3.1 `GET /api/devices`
Danh sách tất cả thiết bị + trạng thái hiện tại (compartments, fillPercent, status).

### 3.2 `GET /api/devices/{deviceId}`
Chi tiết 1 thiết bị.

### 3.3 `PATCH /api/devices/{deviceId}/config`
Cập nhật threshold / maintenance mode. Có thể gửi partial body.

```json
{ "thresholds": { "plastic": 85 } }
```

Backend lấy `email` từ request attribute (set bởi `FirebaseAuthFilter`) để ghi `last_config_updated_by`. Response: `204 No Content`.

### 3.4 `GET /api/devices/{deviceId}/events?eventType=&limit=`
Lịch sử event, filter theo `eventType` (`CLASSIFY | FULL_ALERT | ERROR | MAINTENANCE`), mặc định `limit=50`.
- `eventType=CLASSIFY` → bảng lịch sử phân loại (Bin Detail).
- `eventType=FULL_ALERT` → trang Alerts + cảnh báo gần đây ở Dashboard.

### 3.5 `PATCH /api/devices/{deviceId}/events/{eventId}/resolve`
Resolve một `FULL_ALERT`. Cần Firebase ID Token. Backend ghi lại ai resolve (`email` từ request attribute). Response: `204 No Content`.
> Mới nối thật — trước đây trang Alerts chỉ resolve ở local state frontend.

### 3.6 `GET /api/daily-stats?deviceId=&from=&to=&date=`
Thống kê phân loại theo ngày cho 1 thiết bị. Nếu truyền `date`, override cả `from`/`to` bằng giá trị đó (query 1 ngày).

### 3.7 `GET /api/daily-stats/summary?days=`
Tổng hợp thống kê `days` ngày gần nhất (mặc định 1).

### 3.8 `GET /api/daily-stats/ranking?days=`
Xếp hạng thiết bị theo `days` ngày gần nhất (mặc định 7).

---

## 4. Bảng endpoint tổng hợp

| Method | Path | Auth | Caller |
|---|---|---|---|
| POST | `/api/devices/{deviceId}/auth-token` | `X-Provision-Secret` | ESP32 |
| POST | `/api/devices/{deviceId}/events` | Device JWT (Bearer) | ESP32 |
| GET | `/api/devices/{deviceId}/config` | Không (open) | ESP32 |
| GET | `/api/devices` | Firebase ID Token | Dashboard |
| GET | `/api/devices/{deviceId}` | Firebase ID Token | Dashboard |
| PATCH | `/api/devices/{deviceId}/config` | Firebase ID Token | Dashboard |
| GET | `/api/devices/{deviceId}/events` | Không (open) | Dashboard |
| PATCH | `/api/devices/{deviceId}/events/{eventId}/resolve` | Firebase ID Token | Dashboard |
| GET | `/api/daily-stats` | — | Dashboard |
| GET | `/api/daily-stats/summary` | — | Dashboard |
| GET | `/api/daily-stats/ranking` | — | Dashboard |

---

Lưu ý: backend đã có api endpoint GET /config, nhưng chưa dùng. ❌ ESP32 chưa đọc config động từ backend — threshold vẫn hardcode, endpoint GET /config có ở backend nhưng chưa được gọi từ firmware. Đây là phần còn thiếu để hoàn thiện luồng "đổi threshold từ dashboard, ESP32 tự áp dụng."

```
network_config::kFullThresholdPercent // = 80, hardcode trong file .h, biên dịch cứng vào firmware
```