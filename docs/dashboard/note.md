# Note dashboard, API và DB

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
GET   /api/daily-stats?deviceId={id}&from={yyyy-mm-dd}&to={yyyy-mm-dd}
```

## Phần đã merge đúng

- DTO frontend đang mirror đúng DTO backend theo camelCase.
- Backend đọc Firestore field snake_case bằng `@PropertyName`, sau đó trả JSON camelCase cho frontend.
- `DashboardPage`, `BinDetailPage`, `StatisticsPage`, `AlertsPage` đã có đường đọc dữ liệu thật từ backend thông qua service/hook.
- Cloud Function đã tăng `daily_stats` khi có event `CLASSIFY`.
- Cloud Function đã cập nhật `compartments.{type}.status = "full"` khi có event `FULL_ALERT`.
- Security Rules đã chặn dashboard/client đọc ghi trực tiếp vào `daily_stats` và `users`, chỉ cho device dùng `device_id` đọc/ghi path của nó.

## Phần còn mock/chưa nối thật

- `ConfigPage` vẫn dùng `THRESHOLDS` trong `mockData` và chỉ show toast khi lưu. Service `updateDeviceConfig` đã có nhưng UI chưa gọi.
- Dashboard KPI `Tổng lượt bỏ rác`, `Rác tái chế`, doughnut `Phân loại rác hôm nay` còn placeholder/static.
- Bảng điểm thưởng `REWARDS` vẫn là mock, chưa có backend/schema trong prototype hiện tại.
- Alerts có nút "Xử lý" nhưng chỉ đổi local state, chưa có API/collection alert lifecycle.
- Các hook dashboard/alerts/stats fetch một lần, chưa polling 3-5 giây nên chưa chứng minh được yêu cầu cập nhật dashboard <= 5 giây.

## Điểm cần chú ý khi merge với team

1. Nếu cần demo realtime, thêm polling 3-5 giây cho `useBins`, `useFullAlerts`, và có thể cho `useDailyStats`.
2. Nếu muốn cấu hình ngưỡng chạy thật, nối `ConfigPage` với `fetchAllBins/fetchBinThresholds/updateDeviceConfig`, bỏ `THRESHOLDS` mock.
3. Thêm Firestore composite index cho `daily_stats`: `device_id ASC`, `date ASC`.
4. Thống nhất đơn vị `threshold`: DB design ghi mặc định `0.8`, UI đang hiển/lưu theo `%` 80-100. Cần chốt một đơn vị. Code frontend hiện đang xử lý threshold như phần trăm.
5. Nếu event `alert_threshold` dùng để so sánh AI confidence thì tên field đang gây nhầm lẫn, vì `alert_threshold` trong spec DB nghiêng về ngưỡng đầy thùng. Nên có field riêng cho AI rejection threshold nếu cần hiển thị "từ chối" chính xác.
