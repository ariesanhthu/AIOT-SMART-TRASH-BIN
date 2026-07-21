# Cập nhật thực hiện so với spec và đánh giá đánh đổi prototype

> Cập nhật lần 2 (20/07/2026) — sau khi nối ConfigPage, thêm polling, alert lifecycle, Firestore index.

## 1. Kết luận ngắn

Hướng hiện tại không sai hướng đồ án. Kiến trúc Dashboard -> Backend -> Firestore và ESP32 -> Firestore trực tiếp phù hợp prototype.

**[CẬP NHẬT 0.1]** So với lần audit trước, bản hiện tại đã tiến thêm một bước quan trọng: **polling <= 5 giây, thêm các endpoint mới như `PATCH .../resolve`** đều đã hoàn thành và test xác nhận hoạt động đúng. Phần còn thiếu chỉ còn ở mức "cần leader quyết định hướng" (đơn vị threshold, tên field) chứ không còn là nợ kỹ thuật (technical debt) nữa.

**[CẬP NHẬT 0.2]** Bảng điểm thưởng `REWARDS` đã cập nhật thành `useRanking` hook, đọc thật từ backend endpoint `/api/daily-stats/ranking?days=7`, realdata cho Dashboard doughnut và 2 kpi quá `/api/daily-stats/summary` — **Xong**. Phần còn mock/chưa nối thật: `ConfigPage` vẫn còn mock `AI_CONFIDENCE_DEFAULTS`, `MODEL_VERSION_LIST`, `MQTT_DEFAULTS` từ `mockData.ts` — vì chưa có OTA model và chưa có MQTT broker thật. Nhóm cần chót có sử dụng tính năng này hay không.

## 2. Đối chiếu theo nhóm yêu cầu (cập nhật)

| Nhóm yêu cầu | Spec mong muốn | Hiện trạng code | Đánh giá |
|---|---|---|---|
| Dashboard xem trạng thái thùng | Hiện mức đầy từng ngăn, trạng thái online/offline, last update | `GET /api/devices` đã có; frontend mapping ra `Bin`; online suy ra từ `lastSeenAt` | Đạt |
| Cập nhật dashboard <= 5 giây | Dashboard nhận dữ liệu mới trong <= 5 giây | **[XONG]** Đã thêm polling 3-5 giây cho `useBins`, `useDailyStats`, `useFullAlerts` | **Đạt** |
| Ghi event phân loại | Lưu loại rác, thùng, thời gian, confidence, compartment | ESP32 schema + backend read event + Cloud Function đã có | Đạt về schema/backend; cần firmware gửi đúng payload |
| Thống kê theo ngày | Tổng hợp organic/paper/plastic theo ngày | Cloud Function increment `daily_stats`; **[XONG]** đã thêm composite index | **Đạt** |
| Thống kê theo tháng | Có thống kê theo tháng | Chưa có `monthly_stats` | Chấp nhận được cho prototype 30 ngày |
| Cảnh báo đầy | Hiện `FULL_ALERT` khi vượt ngưỡng | Event `FULL_ALERT`, FE đọc alert; Function set status full | Đạt |
| Xử lý cảnh báo | Theo dõi cảnh báo đã xử lý/chưa xử lý | **[XONG]** Endpoint `PATCH .../resolve` lưu `alert_status`, `resolved_at`, `resolved_by` xuống Firestore thật, đã test xác nhận giữ trạng thái sau refresh | **Đạt** |
| Cấu hình ngưỡng đầy | Admin đổi threshold từng ngăn từ dashboard | **[XONG]** `ConfigPage` đã gọi `PATCH /config` thật | **Đạt** |
| Bảo trì từ xa | Bật/tắt `maintenance_mode` | Backend support field; **[CẦN KIỂM TRA]** UI đã nối cùng lúc với ConfigPage, cần xác nhận riêng | Có khả năng đã đạt, cần test lại |
| Cập nhật model AI từ xa | Optional/nên có | Chỉ lưu `ai_model_version`; UI model là mock | Chấp nhận prototype |
| Bảo mật dashboard | Admin/user xác thực trước khi gọi API | FE lấy Firebase ID Token; backend có filter auth; **[FIX]** đã sửa filter chặn nhầm CORS preflight | Đúng hướng, đã ổn định |
| Bảo mật ESP32 | Không nhúng Admin key vào firmware | Backend cấp custom token, Security Rules giới hạn `device_id` | Đúng hướng prototype |
| Mất mạng và sync lại | Queue local, sync theo timestamp | DB hỗ trợ, firmware chưa đánh giá | DB hỗ trợ, firmware cần implement |
| Lưu dữ liệu tối thiểu 30 ngày | Giữ event/stat tối thiểu 30 ngày | Schema có timestamp/date; chưa có TTL/cleanup | Chấp nhận prototype |

## 3. Những gì mới hoàn thành trong lần cập nhật này

- **ConfigPage** gọi API thật (`PATCH /api/devices/{id}/config`), không còn mock `THRESHOLDS`.
- **Polling 3-5 giây** cho `useBins`, `useDailyStats`, `useFullAlerts` — đạt yêu cầu dashboard cập nhật <= 5 giây.
- **Alert lifecycle thật**: endpoint `PATCH /api/devices/{id}/events/{eventId}/resolve`, backend cập nhật `alert_status`/`resolved_at`/`resolved_by`, đã test xác nhận lưu Firestore thật (không còn chỉ local state).
- **Firestore composite index** đã tạo cho cả `events (event_type, device_timestamp)` và `daily_stats (device_id, date)` — cả hai đều từng gây lỗi 500 khi query thật, giờ đã hoạt động ổn định.
- Sửa 2 bug kỹ thuật phát sinh trong quá trình tích hợp (không nằm trong spec nhưng đáng ghi lại cho team):
  - Lombok `@Data` không copy annotation `@PropertyName` sang getter/setter tự sinh → phải viết tay getter/setter cho `Device`, `Compartment`, `EventData`, `DailyStat`.
  - `firebase-admin:9.4.3` không tương thích với protobuf/gRPC version mà Spring Boot 4 BOM kéo về → nâng lên `9.10.0` để fix lỗi verify JWT signature.
- **SummaryStatsToday** thêm endpoint mới `GET /api/daily-stats/summary?date={yyyy-mm-dd}` cho Dashboard KPI và bảng điểm thưởng để lấy dữ liệu thật từừng ngày — xác nhận đã nối thật trong lần cập nhật này doughnut và 2 kpi đã show data.
- **RankingByDailyStats** thêm `className` vào `DeviceResponse`, `GET /api/daily-stats/ranking?days={7|30}` để FE hiển thị tên lớp thùng (Class A/B/C) — xác nhận được tính năng ranking xếp hạng các thùng - lớp học tương ứng.
- **DailyStats** Backend có cài đặt endpoint `GET /api/daily-stats` để FE có thể lấy thống kê theo ngày cụ thể. FE chưa có UI hiển thị thống kê theo ngày cụ thể dù đã nối thật với endpoint `GET /api/daily-stats?deviceId={id}&from={yyyy-mm-dd}&to={yyyy-mm-dd}`. Chỉ hiển thị 7 ngày gần nhất. (Chọn ngày range sẽ thêm sau.)
- **Threshold unit**: DB ghi mặc định `0.8` (dạng ratio 0-1), UI hiện đang xử lý theo `%` 80-100. Chốt hướng backend 0-1, frontend convert khi hiển thị.

## 4. Những gì vẫn cố ý defer (không đổi so với lần trước)

| Phần bỏ qua/defer | Lý do prototype | Khi nào cần làm |
|---|---|---|
| `monthly_stats` precompute | Có thể cộng từ daily stats | Khi query tháng chậm hoặc số device tăng |
| Upload/deploy model AI từ dashboard | Optional theo spec | Khi cần OTA model |
| Push config realtime <= 7 giây | Pull đơn giản hơn MQTT | Khi muốn giữ đúng NFREQ.19 |
| TTL/cron xóa data cũ | Dữ liệu demo nhỏ | Khi chạy lâu ngày |
| Reward/student points backend | Ngoài core dashboard | Khi spec demo cần gamification thật |

## 5. Việc còn lại — cần leader quyết định trước khi code tiếp

### 5.1 alert_threshold field gây nhầm lẫn (chưa đổi so với lần trước)
- Nhóm chốt AI model có trả về phân loại `rejected` hay không, nên chưa có field riêng `ai_threshold` hay `classification_status` trong event. Hiện tại vẫn dùng chung field `alert_threshold` cho cả "ngưỡng đầy thùng" và "ngưỡng AI confidence", gây nhầm lẫn. Cụ thể là có thể có filter để lọc ra các event bị "AI rejected".
### 5.2 Trang StatisticsPage
- Chưa có UI hiển thị thống kê theo ngày cụ thể dù đã nối thật với endpoint `GET /api/daily-stats?deviceId={id}&from={yyyy-mm-dd}&to={yyyy-mm-dd}`. Chỉ hiển thị thống kê theo ngày mặc định (7 ngày gần nhất) trong lần cập nhật này. Cần leader quyết định có cần thêm UI chọn from/to date range hay không.
### 5.3 Trang ConfigPage
- Vẫn còn mock `AI_CONFIDENCE_DEFAULTS`, `MODEL_VERSION_LIST`, `MQTT_DEFAULTS` từ `mockData.ts` — vì chưa có OTA model và chưa có MQTT broker thật. Nhóm cần chốt có sử dụng tính năng này hay không.
### 5.4 Trạng thái online/offline của thiết bị
- Hiện tại dashboard chỉ dựa vào `last_seen_at` để suy ra ít hơn 5 phút gì đó, chưa có field `online_status` riêng. Nếu muốn có trạng thái realtime, cần thêm Cloud Function cập nhật `online_status` khi ESP32 gửi event hoặc ping. Cần leader quyết định có cần thêm field `online_status` hay không.
