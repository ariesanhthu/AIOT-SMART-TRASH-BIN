# Smart Trash Bin Backend

Backend Spring Boot kết nối Firestore bằng Firebase Admin SDK, cung cấp API cho dashboard và cấp Device JWT cho ESP32.

## 1. Yêu cầu

- JDK 21 (`java -version` phải hiển thị phiên bản 21).
- Có quyền truy cập Firebase project `smart-trash-bin-828c1`.
- Không cần cài Gradle riêng vì dự án đã có Gradle Wrapper.

Nếu dùng Windows, có thể cài JDK bằng PowerShell:

```powershell
winget install --id Microsoft.OpenJDK.21 --exact
```

Sau khi cài, đóng rồi mở lại terminal và kiểm tra:

```powershell
java -version
```

## 2. Firebase service account

1. Mở Firebase Console → **Project settings** → **Service accounts**.
2. Chọn **Generate new private key**.
3. Lưu file với đường dẫn:

```text
backend/secrets/serviceAccountKey.json
```

Thư mục `secrets/` đã được `.gitignore`. Không commit, gửi cho firmware hoặc đưa service-account JSON lên kho mã nguồn.

Nếu muốn đặt file ở vị trí khác, khai báo `FIREBASE_CREDENTIALS_PATH` bằng đường dẫn tuyệt đối. Khi triển khai cloud, có thể truyền toàn bộ nội dung JSON qua `FIREBASE_CREDENTIALS_JSON` thay cho file.

## 3. Biến môi trường

Backend sử dụng các biến sau:

| Biến | Bắt buộc | Mặc định | Ý nghĩa |
| --- | --- | --- | --- |
| `DEVICE_PROVISIONING_SECRET` | Có | Rỗng | Secret ESP32 gửi trong header `X-Provision-Secret` để lấy Device JWT. |
| `DEVICE_JWT_SECRET` | Có | Giá trị chỉ dành cho phát triển | Khóa ký Device JWT, phải dài tối thiểu 32 ký tự. |
| `FIREBASE_CREDENTIALS_PATH` | Không | `secrets/serviceAccountKey.json` | Đường dẫn tới Firebase service-account JSON. |
| `FIREBASE_CREDENTIALS_JSON` | Không | Rỗng | Nội dung service-account JSON; được ưu tiên hơn biến đường dẫn. |
| `DEVICE_JWT_EXPIRY_SECONDS` | Không | `86400` | Thời hạn Device JWT, tính bằng giây. |
| `PORT` | Không | `8080` | Cổng HTTP của backend. |

Hai secret phải giống giá trị được cấu hình ở phía ESP32 khi thiết bị gọi API. Không ghi secret thật trực tiếp vào `application.properties`.

### PowerShell (Windows)

Chạy từ thư mục `backend`:

```powershell
$env:DEVICE_PROVISIONING_SECRET = "thay-bang-secret-cua-thiet-bi"
$env:DEVICE_JWT_SECRET = "thay-bang-khoa-ngau-nhien-it-nhat-32-ky-tu"
$env:FIREBASE_CREDENTIALS_PATH = (Resolve-Path ".\secrets\serviceAccountKey.json").Path
.\gradlew.bat bootRun
```

Các biến trên chỉ tồn tại trong terminal hiện tại. Có thể tạo khóa ngẫu nhiên bằng:

```powershell
[Convert]::ToHexString([Security.Cryptography.RandomNumberGenerator]::GetBytes(32))
```

### macOS/Linux

Chạy từ thư mục `backend`:

```bash
export DEVICE_PROVISIONING_SECRET='thay-bang-secret-cua-thiet-bi'
export DEVICE_JWT_SECRET='thay-bang-khoa-ngau-nhien-it-nhat-32-ky-tu'
export FIREBASE_CREDENTIALS_PATH="$PWD/secrets/serviceAccountKey.json"
chmod +x gradlew
./gradlew bootRun
```

## 4. Khởi động và kiểm tra

Khi log có dòng tương tự `Tomcat started on port 8080`, backend đã sẵn sàng tại:

```text
http://localhost:8080
```

Mở terminal thứ hai để kiểm tra API đọc công khai:

```powershell
Invoke-RestMethod http://localhost:8080/api/devices
```

Hoặc dùng curl:

```bash
curl http://localhost:8080/api/devices
```

Kiểm tra endpoint cấp token cho thiết bị:

```powershell
$headers = @{ "X-Provision-Secret" = $env:DEVICE_PROVISIONING_SECRET }
Invoke-RestMethod -Method Post `
  -Uri "http://localhost:8080/api/devices/STBIN_HCMUS_001/auth-token" `
  -Headers $headers
```

Thay `STBIN_HCMUS_001` bằng `deviceId` thực tế. Dừng backend bằng `Ctrl+C`.

## 5. Xác thực API

- Các request `GET /api/**` hiện được phép đọc không cần token.
- `POST /api/devices/{deviceId}/auth-token` dùng `X-Provision-Secret`.
- `POST /api/devices/{deviceId}/events` dùng `Authorization: Bearer <Device JWT>`.
- Các request ghi quản trị (`PATCH`, `POST`, `DELETE` khác) dùng `Authorization: Bearer <Firebase ID Token>`.

Một số endpoint chính:

```text
GET   /api/devices
GET   /api/devices/{deviceId}
GET   /api/devices/{deviceId}/config
PATCH /api/devices/{deviceId}/config
POST  /api/devices/{deviceId}/auth-token
GET   /api/devices/{deviceId}/events
POST  /api/devices/{deviceId}/events
PATCH /api/devices/{deviceId}/events/{eventId}/resolve
GET   /api/daily-stats?deviceId={deviceId}
GET   /api/daily-stats/summary?days=1
GET   /api/daily-stats/ranking?days=7
```

## 6. Build và test

Windows:

```powershell
.\gradlew.bat clean test
.\gradlew.bat clean bootJar
java -jar .\build\libs\backend-0.0.1-SNAPSHOT.jar
```

macOS/Linux:

```bash
./gradlew clean test
./gradlew clean bootJar
java -jar build/libs/backend-0.0.1-SNAPSHOT.jar
```

## 7. Chạy bằng Docker

Build image:

```bash
docker build -t smart-trash-bin-backend .
```

Chạy container và mount service-account ở chế độ chỉ đọc:

```bash
docker run --rm -p 8080:8080 \
  -e DEVICE_PROVISIONING_SECRET='thay-bang-secret-cua-thiet-bi' \
  -e DEVICE_JWT_SECRET='thay-bang-khoa-ngau-nhien-it-nhat-32-ky-tu' \
  -e FIREBASE_CREDENTIALS_PATH='/run/secrets/serviceAccountKey.json' \
  -v "$PWD/secrets/serviceAccountKey.json:/run/secrets/serviceAccountKey.json:ro" \
  smart-trash-bin-backend
```

## 8. Lỗi thường gặp

- `java is not recognized` hoặc `JAVA_HOME is not set`: cài JDK 21, mở terminal mới và chạy lại `java -version`.
- `FileNotFoundException: secrets/serviceAccountKey.json`: chạy lệnh từ thư mục `backend`, hoặc đặt `FIREBASE_CREDENTIALS_PATH` thành đường dẫn tuyệt đối.
- API cấp token trả lỗi provisioning: kiểm tra `DEVICE_PROVISIONING_SECRET` của backend và ESP32 có giống nhau không.
- Lỗi khóa JWT: `DEVICE_JWT_SECRET` phải dài ít nhất 32 ký tự và giữ ổn định; đổi khóa sẽ làm token cũ mất hiệu lực.
- Cổng 8080 đang được dùng: đặt `$env:PORT = "8081"` trên PowerShell hoặc `export PORT=8081` trên macOS/Linux.
- Firestore báo thiếu quyền: kiểm tra service account thuộc đúng Firebase project và Firestore đã được bật.

Luồng credential phía thiết bị được mô tả tại [Đề xuất kết nối ESP32–Firestore](../docs/architecture/De_xuat_ket_noi_ESP32_Firestore.md).
