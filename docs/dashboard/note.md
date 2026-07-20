# Note dashboard, API và DB

> Cập nhật lần 2 (20/07/2026) — sau khi nối thật ConfigPage, polling, alert lifecycle, và tạo Firestore composite index.

## Phạm vi mình đang check

Phần dashboard hiện tại thuộc Sub-Goal 3: xem trạng thái thùng, cảnh báo đầy, thống kê phân loại, cấu hình ngưỡng và quản lý thiết bị từ xa. Kiến trúc đã chốt theo hướng:

- Dashboard React không đọc/ghi Firestore trực tiếp.
- Dashboard gọi Spring Boot REST API và gửi Firebase ID Token của user.
- Backend dùng Firebase Admin SDK để đọc/ghi Firestore.
- ESP32 ghi/đọc Firestore trực tiếp bằng credential riêng của thiết bị.
- Cloud Functions xử lý side effect sau khi ESP32 tạo event.

## Các collection/doc chính trong Firestore

```text
devices/{deviceId}
devices/{deviceId}/events/{eventId}
daily_stats/{deviceId}_{yyyy-mm-dd}
users/{uid}
```

(Cấu trúc field giữ nguyên như bản audit đầu — xem lại phần này ở note.md gốc nếu cần, không đổi.)

## API dashboard đang gọi

```text
GET   /api/devices
GET   /api/devices/{deviceId}
PATCH /api/devices/{deviceId}/config
GET   /api/devices/{deviceId}/events?eventType=CLASSIFY&limit=20
GET   /api/devices/{deviceId}/events?eventType=FULL_ALERT&limit=50
PATCH /api/devices/{deviceId}/events/{eventId}/resolve
GET   /api/daily-stats?deviceId={id}&from={yyyy-mm-dd}&to={yyyy-mm-dd}
```
(Bổ sung endpoint `resolve` — mới nối thật trong lần cập nhật này.)

## Phần đã merge đúng (cập nhật)

- DTO frontend mirror đúng DTO backend theo camelCase.
- Backend đọc Firestore field snake_case bằng `@PropertyName`, trả JSON camelCase cho frontend.
- `DashboardPage`, `BinDetailPage`, `StatisticsPage`, `AlertsPage` đọc dữ liệu thật từ backend qua service/hook.
- Cloud Function tăng `daily_stats` khi có event `CLASSIFY`.
- Cloud Function cập nhật `compartments.{type}.status = "full"` khi có event `FULL_ALERT`.
- Security Rules chặn dashboard/client đọc ghi trực tiếp `daily_stats` và `users`.
- **[MỚI] `ConfigPage` đã nối API thật** — gọi `PATCH /api/devices/{id}/config`, không còn dùng `THRESHOLDS` mock.
- **[MỚI] Polling 3-5 giây đã thêm** cho `useBins`, `useDailyStats`, `useFullAlerts` — đạt yêu cầu cập nhật dashboard ≤ 5 giây.
- **[MỚI] Alert lifecycle đã nối thật** — nút "Xử lý" gọi `PATCH .../resolve`, backend cập nhật `alert_status`, `resolved_at`, `resolved_by` trong Firestore; đã test xác nhận trạng thái giữ nguyên sau khi refresh.
- **[MỚI] Firestore composite index đã tạo** cho `events` (`event_type` + `device_timestamp`) và `daily_stats` (`device_id` + `date`).
- Dashboard KPI `Tổng lượt bỏ rác`, `Rác tái chế`, doughnut `Phân loại rác hôm nay` — **Xong**, xác nhận đã nối thật trong lần cập nhật này doughnut và 2 kpi đã show data.

## Phần còn mock/chưa nối thật
- Bảng điểm thưởng `REWARDS` vẫn là mock, chưa có backend/schema trong prototype hiện tại.

## Điểm cần chú ý khi merge với team (cập nhật)

1. Thêm polling 3-5 giây — **Đã xong.**
2. Nối `ConfigPage` với API thật — **Đã xong.**
3. Thêm Firestore composite index cho `daily_stats` — **Đã xong**, đồng thời phát hiện và tạo thêm luôn index cho `events` (chưa được nhắc trong audit đầu, nhưng cũng bị lỗi tương tự).
4. **[CHƯA GIẢI QUYẾT]** Thống nhất đơn vị `threshold`: DB ghi mặc định `0.8` (dạng ratio 0-1), UI hiện đang xử lý theo `%` 80-100. Cần chốt với leader một đơn vị duy nhất — hiện tại code frontend có xử lý mapping ratio↔percent ở tầng UI, cần leader xác nhận đây có phải hướng đúng không.
5. **[CHƯA GIẢI QUYẾT]** Tên field `alert_threshold` trong event đang gây nhầm lẫn giữa "ngưỡng đầy thùng" và "ngưỡng AI confidence". Cần leader quyết định có tách field riêng hay không.
6. **[MỚI] Lưu ý kỹ thuật cho backend team:** nâng cấp `firebase-admin` từ `9.4.3` lên `9.10.0` — bản cũ không tương thích với version protobuf/gRPC mà Spring Boot 4 BOM kéo về, gây lỗi verify chữ ký JWT (`Failed to verify the signature of Firebase ID token`) dù token/credential hoàn toàn hợp lệ. Đây là lỗi rất khó debug vì không liên quan gì tới logic code, ai gặp lại nên biết trước.
7. **[MỚI] Lưu ý cho model Firestore:** khi dùng Lombok `@Data` kèm `@PropertyName` (Firestore SDK), annotation processing có thể fail âm thầm tuỳ môi trường máy — nếu thấy warning `PojoBeanMapper: No setter/field for X found`, kiểm tra ngay xem Lombok có đang thực sự sinh getter/setter hay không trước khi nghi ngờ code logic.