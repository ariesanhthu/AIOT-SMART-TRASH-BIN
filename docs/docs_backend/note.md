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

`devices/{deviceId}` lưu trạng thái hiện tại:

- `name`
- `location`
- `last_seen_at`
- `maintenance_mode`
- `firmware_version`
- `ai_model_version`
- `class_name`
- `compartments.organic/paper/plastic.threshold`
- `compartments.organic/paper/plastic.fill_percent`
- `compartments.organic/paper/plastic.status`

`events` lưu lịch sử sự kiện:

- `event_type`: `CLASSIFY`, `FULL_ALERT`, `ERROR`, `MAINTENANCE`
- `waste_type`
- `target_compartment`
- `ai_confidence`
- `fill_percent`
- `alert_threshold`
- `device_timestamp`
- `received_at`
- `synced_late`
- `firmware_version`
- `ai_model_version`

`daily_stats` lưu thống kê ngày:

- `device_id`
- `date`
- `organic_count`
- `paper_count`
- `plastic_count`
- `total_count`

## API dashboard đang gọi

```text
GET   /api/devices
GET   /api/devices/{deviceId}
PATCH /api/devices/{deviceId}/config
GET   /api/devices/{deviceId}/events?eventType=CLASSIFY&limit=20
GET   /api/devices/{deviceId}/events?eventType=FULL_ALERT&limit=50
PATCH /api/devices/{deviceId}/events/{eventId}/resolve
GET   /api/daily-stats?deviceId={id}&from={yyyy-mm-dd}&to={yyyy-mm-dd}
GET   /api/daily-stats/summary?date={yyyy-mm-dd}
GET   /api/daily-stats/ranking?days={7|30}
```
(Bổ sung endpoint `resolve` — mới nối thật trong lần cập nhật này.)

## Phần đã merge đúng (cập nhật)

- DTO frontend mirror đúng DTO backend theo camelCase.
- Backend đọc Firestore field snake_case bằng `@PropertyName`, trả JSON camelCase cho frontend.
- `DashboardPage`, `BinDetailPage`, `StatisticsPage`, `AlertsPage` đọc dữ liệu thật từ backend qua service/hook.
- Cloud Function tăng `daily_stats` khi có event `CLASSIFY`.
- Cloud Function cập nhật `compartments.{type}.status = "full"` khi có event `FULL_ALERT`.
- Security Rules chặn dashboard/client đọc ghi trực tiếp `daily_stats` và `users`.
- **`ConfigPage` đã nối API thật** — gọi `PATCH /api/devices/{id}/config`, không còn dùng `THRESHOLDS` mock.
- **Polling 3-5 giây đã thêm** cho `useBins`, `useDailyStats`, `useFullAlerts` — đạt yêu cầu cập nhật dashboard ≤ 5 giây.
- **Alert lifecycle đã nối thật** — nút "Xử lý" gọi `PATCH .../resolve`, backend cập nhật `alert_status`, `resolved_at`, `resolved_by` trong Firestore; đã test xác nhận trạng thái giữ nguyên sau khi refresh.
- **Firestore composite index đã tạo** cho `events` (`event_type` + `device_timestamp`) và `daily_stats` (`device_id` + `date`).
- **[MỚI] SummaryStatsToday** thêm endpoint mới `GET /api/daily-stats/summary?date={yyyy-mm-dd}` cho Dashboard KPI và bảng điểm thưởng để lấy dữ liệu thật từừng ngày — xác nhận đã nối thật trong lần cập nhật này doughnut và 2 kpi đã show data.
- **[MỚI] Bảng điểm thưởng `REWARDS`** đã cập nhật thành `useRanking` hook, đọc thật từ backend endpoint `/api/daily-stats/ranking?days=7` — **Xong**

## Phần còn mock/chưa nối thật
- `ConfigPage` vẫn còn mock `AI_CONFIDENCE_DEFAULTS`, `MODEL_VERSION_LIST`, `MQTT_DEFAULTS` từ `mockData.ts` — vì chưa có OTA model và chưa có MQTT broker thật. Nhóm cần chót có sử dụng tính năng này hay không.
- Nhóm chưa chốt được model AI có trả về phân loại `rejected` hay không, nên chưa có field riêng `ai_threshold` hay `classification_status` trong event. Hiện tại vẫn dùng chung field `alert_threshold` cho cả "ngưỡng đầy thùng" và "ngưỡng AI confidence", gây nhầm lẫn.
- Về trạng thái `online/offline` của thiết bị, hiện tại dashboard chỉ dựa vào `last_seen_at` để suy ra ít hơn 5 phút gì đó, chưa có field `online_status` riêng. Nếu muốn có trạng thái realtime, cần thêm Cloud Function cập nhật `online_status` khi ESP32 gửi event hoặc ping.
- Trang DailyStatsPage chưa có UI hiển thị thống kê theo ngày cụ thể dù đã nối thật với endpoint `GET /api/daily-stats?deviceId={id}&from={yyyy-mm-dd}&to={yyyy-mm-dd}`. Chỉ hiển thị thống kê theo ngày mặc định (7 ngày gần nhất) trong lần cập nhật này.

## Điểm cần chú ý khi merge với team (cập nhật)

1. Thêm polling 3-5 giây — **Đã xong.**
2. Nối `ConfigPage` với API thật — **Đã xong.**
3. Thêm Firestore composite index cho `daily_stats` — **Đã xong**, đồng thời phát hiện và tạo thêm luôn index cho `events` (chưa được nhắc trong audit đầu, nhưng cũng bị lỗi tương tự).
4. **Xong** Thống nhất đơn vị `threshold`: DB ghi mặc định `0.8` (dạng ratio 0-1), UI hiện đang xử lý theo `%` 80-100. Cần chốt với leader một đơn vị duy nhất — hiện tại code frontend có xử lý mapping ratio↔percent ở tầng UI, cần leader xác nhận đây có phải hướng đúng không. Và đã chốt hướng backend 0-1, frontend convert khi hiển thị.
5. **[CHƯA GIẢI QUYẾT]** Tên field `alert_threshold` trong event đang gây nhầm lẫn giữa "ngưỡng đầy thùng" và "ngưỡng AI confidence". Cần leader quyết định có tách field riêng hay không.
6. **[MỚI] Lưu ý kỹ thuật cho backend team:** nâng cấp `firebase-admin` từ `9.4.3` lên `9.10.0` — bản cũ không tương thích với version protobuf/gRPC mà Spring Boot 4 BOM kéo về, gây lỗi verify chữ ký JWT (`Failed to verify the signature of Firebase ID token`) dù token/credential hoàn toàn hợp lệ. Đây là lỗi rất khó debug vì không liên quan gì tới logic code, ai gặp lại nên biết trước.
7. **[MỚI] Lưu ý cho model Firestore:** khi dùng Lombok `@Data` kèm `@PropertyName` (Firestore SDK), annotation processing có thể fail âm thầm tuỳ môi trường máy — nếu thấy warning `PojoBeanMapper: No setter/field for X found`, kiểm tra ngay xem Lombok có đang thực sự sinh getter/setter hay không trước khi nghi ngờ code logic.