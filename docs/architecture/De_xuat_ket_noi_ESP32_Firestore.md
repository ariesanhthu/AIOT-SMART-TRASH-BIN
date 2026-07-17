# ĐỀ XUẤT KẾT NỐI ESP32 ↔ FIRESTORE

**Bối cảnh:** `De_xuat_thiet_ke_DB.md` mục 2.1 đã chốt ESP32 ghi/đọc Firestore trực tiếp bằng credential riêng của thiết bị, không dùng Admin SDK key. Tài liệu đó mô tả *cái gì* cần có (custom token gắn `device_id`, Security Rules giới hạn theo path); tài liệu này mô tả *cách* firmware thực sự lấy được credential đó và gọi Firestore, vì đây là phần trước nay chưa được viết ra ở đâu cả.

## 1. Hai loại key — không được nhầm lẫn

| | Admin SDK key (`serviceAccountKey.json`) | Firebase Web API key |
|---|---|---|
| Ai giữ | Chỉ backend (`backend/secrets/serviceAccountKey.json`, gitignored) | Firmware ESP32 |
| Quyền | Bỏ qua Security Rules, toàn quyền đọc/ghi | Không có quyền gì tự thân — chỉ định danh project để gọi Identity Toolkit/Firestore REST; mọi quyền thực tế do Security Rules + token quyết định |
| Có được phép nhúng vào firmware không | **Không bao giờ** — vi phạm NFREQ.15 | Có — đây là thiết kế của Firebase, key này công khai theo mặc định (tương tự App ID trên mobile app) |

Lấy Web API key tại Firebase Console → Project settings → General → "Web API Key" của project `smart-trash-bin-828c1` (xem `.firebaserc`). Không cần tạo Web App riêng trong console để lấy key này.

## 2. Luồng lấy và dùng credential

```text
[Lúc flash / provisioning]
  Nạp vào firmware: WIFI creds, FIREBASE_WEB_API_KEY, FIREBASE_PROJECT_ID,
  BACKEND_BASE_URL, DEVICE_ID, PROVISION_SECRET (xem mục 4)

[Lúc boot / mỗi khi custom token gần hết hạn]
  1. POST {BACKEND_BASE_URL}/api/devices/{deviceId}/auth-token
     Header: X-Provision-Secret: {PROVISION_SECRET}
     -> { "deviceId": "...", "customToken": "<jwt>" }
     (endpoint này KHÔNG cần Firebase ID Token — xem DeviceAuthController,
     bị FirebaseAuthFilter bỏ qua có chủ đích, tự bảo vệ bằng provisioning
     secret vì thiết bị chưa có ID Token lúc gọi lần đầu)

  2. POST https://identitytoolkit.googleapis.com/v1/accounts:signInWithCustomToken?key={FIREBASE_WEB_API_KEY}
     Body: { "token": "<customToken>", "returnSecureToken": true }
     -> { "idToken": "<jwt>", "refreshToken": "...", "expiresIn": "3600" }

[Mỗi lần ghi/đọc Firestore]
  3. Gọi Firestore REST API với header:
     Authorization: Bearer {idToken}
     vd. PATCH https://firestore.googleapis.com/v1/projects/{FIREBASE_PROJECT_ID}/databases/(default)/documents/devices/{deviceId}?updateMask.fieldPaths=fill_percent&updateMask.fieldPaths=last_seen_at
     vd. POST   .../documents/devices/{deviceId}/events (tạo event mới)

     idToken hết hạn sau 1h. Trước khi hết hạn, dùng refreshToken gọi
     https://securetoken.googleapis.com/v1/token?key={FIREBASE_WEB_API_KEY}
     để lấy idToken mới mà không cần gọi lại bước 1.
     Nếu refresh cũng lỗi (vd. mất điện lâu ngày), quay lại bước 1.
```

`device_id` trong custom token claim khớp với `isDevice(deviceId)` trong `firestore.rules` — Security Rules dựa vào `request.auth.token.device_id`, không dựa vào UID, nên firmware phải dùng đúng path `devices/{deviceId}` với `deviceId` bằng UID đã dùng khi tạo custom token (`DeviceAuthService.issueDeviceToken` dùng chính `deviceId` làm UID).

## 3. Kết nối mạng — TLS

ESP32 gọi HTTPS tới `identitytoolkit.googleapis.com`, `securetoken.googleapis.com`, `firestore.googleapis.com` — cả ba đều dùng chứng chỉ do Google Trust Services ký. Firmware cần nhúng root CA tương ứng (vd. `GTS Root R1`, dạng PEM) vào firmware để `esp_tls`/`esp_http_client` xác minh chứng chỉ server; không tắt xác minh TLS (`skip_cert_common_name_check` hoặc tương đương) trên thiết bị thật.

WiFi provisioning (SSID/password) không thuộc phạm vi tài liệu này — dùng cơ chế provisioning ESP-IDF sẵn có (SoftAP/BLE) hoặc nạp cứng lúc build cho giai đoạn demo; không dùng WiFi credential làm giải pháp bảo mật cho Firestore access, vì đó là hai lớp bảo mật khác nhau.

## 4. Biến cấu hình cần nạp cho mỗi thiết bị

| Biến | Nguồn | Ghi chú |
|---|---|---|
| `WIFI_SSID` / `WIFI_PASSWORD` | Theo môi trường triển khai | Ngoài phạm vi tài liệu này |
| `DEVICE_ID` | Do backend/quản trị viên cấp khi đăng ký thiết bị mới trong `devices` collection | Phải khớp document ID trong Firestore |
| `FIREBASE_PROJECT_ID` | `.firebaserc` (`smart-trash-bin-828c1`) | Dùng trong URL Firestore REST |
| `FIREBASE_WEB_API_KEY` | Firebase Console → Project settings | An toàn khi nhúng vào firmware (mục 1) |
| `BACKEND_BASE_URL` | URL deploy của Spring Boot backend | vd. `https://api.example.com` |
| `PROVISION_SECRET` | Giá trị bí mật do đội vận hành đặt, khớp `DEVICE_PROVISIONING_SECRET` phía backend (`application.properties`) | **Không** commit giá trị thật vào repo; đây là bí mật duy nhất thật sự nhạy cảm ở phía firmware — nếu lộ, kẻ tấn công có thể tự cấp custom token cho bất kỳ `deviceId` nào |

## 5. Việc còn thiếu / hướng nâng cấp

- `PROVISION_SECRET` hiện là secret dùng chung cho mọi thiết bị — đủ cho quy mô prototype (NFREQ.7: tối thiểu 10 thiết bị). Nếu số lượng thiết bị tăng hoặc cần thu hồi quyền của một thiết bị cụ thể mà không ảnh hưởng thiết bị khác, cần đổi sang secret/khóa riêng theo từng `deviceId` hoặc cơ chế đăng ký thiết bị có phê duyệt.
- Custom token/`idToken` hiện lưu trong RAM của firmware, không cần lưu Flash — nếu thiết bị mất điện, thực hiện lại bước 1–2 lúc boot.
- Xem `functions/index.js` để biết phần side-effect chạy sau khi ESP32 ghi `events` (tăng `daily_stats`, cập nhật `compartments.status`) — phần này không thuộc trách nhiệm firmware.
