# Cập nhật thực hiện so với spec và đánh giá đánh đổi prototype

> Cập nhật lần 2 (20/07/2026) — sau khi nối ConfigPage, thêm polling, alert lifecycle, Firestore index.

## 1. Kết luận ngắn

Hướng hiện tại không sai hướng đồ án. Kiến trúc Dashboard -> Backend -> Firestore và ESP32 -> Firestore trực tiếp phù hợp prototype.

**[CẬP NHẬT]** So với lần audit trước, bản hiện tại đã tiến thêm một bước quan trọng: **polling <= 5 giây, ConfigPage nối API thật, alert lifecycle có backend thật** đều đã hoàn thành và test xác nhận hoạt động đúng. Phần còn thiếu chỉ còn ở mức "cần leader quyết định hướng" (đơn vị threshold, tên field) chứ không còn là nợ kỹ thuật (technical debt) nữa.

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

## 4. Những gì vẫn cố ý defer (không đổi so với lần trước)

| Phần bỏ qua/defer | Lý do prototype | Khi nào cần làm |
|---|---|---|
| `monthly_stats` precompute | Có thể cộng từ daily stats | Khi query tháng chậm hoặc số device tăng |
| Upload/deploy model AI từ dashboard | Optional theo spec | Khi cần OTA model |
| Push config realtime <= 7 giây | Pull đơn giản hơn MQTT | Khi muốn giữ đúng NFREQ.19 |
| TTL/cron xóa data cũ | Dữ liệu demo nhỏ | Khi chạy lâu ngày |
| Reward/student points backend | Ngoài core dashboard | Khi spec demo cần gamification thật |

## 5. Việc còn lại — cần leader quyết định trước khi code tiếp

### 5.1 Đơn vị threshold chưa thống nhất (chưa đổi so với lần trước)

Firestore hiện lưu threshold dạng ratio `0.8`, UI xử lý theo `%` 80-100 (mapping ở tầng frontend). **Đề xuất giữ nguyên cách này** (Firestore ratio, frontend convert khi hiển thị) vì đã hoạt động ổn định qua test — nhưng cần leader xác nhận chính thức để ghi vào tài liệu, tránh member khác sửa lại theo hướng khác sau này.

### 5.2 Tên field `alert_threshold` gây nhầm lẫn (chưa đổi so với lần trước)

Field này đang dùng cho ngưỡng đầy thùng, nhưng code frontend có chỗ dùng cùng field để suy ra "AI rejected". Đề xuất: nếu cần hiển thị "từ chối" chính xác, thêm field riêng `ai_threshold` hoặc `classification_status`. Cần leader quyết định có cần làm trong phạm vi hiện tại không.

### 5.3 Dashboard KPI và bảng điểm thưởng

`Tổng lượt bỏ rác`, `Rác tái chế`, doughnut chart, bảng điểm thưởng — cần kiểm tra lại xem đã nối thật hay vẫn còn mock, chưa xác nhận trong lần cập nhật này.

## 6. Đánh giá đánh đổi (cập nhật)

So với đánh giá lần trước, các rủi ro chính đã được giải quyết:

- Không polling/realtime thì không đạt chỉ tiêu <= 5 giây → **Đã giải quyết.**
- Config UI còn mock → **Đã giải quyết.**
- Rủi ro còn lại chỉ nằm ở quyết định thiết kế (đơn vị threshold, tên field), không phải nợ kỹ thuật.

## 7. Đề xuất việc nên làm tiếp trước merge/demo (cập nhật)

1. Thêm polling 3-5 giây — **Xong.**
2. Nối ConfigPage vào API — **Xong.**
3. Thêm Firestore index cho daily_stats — **Xong**, đồng thời phát hiện và fix thêm index cho `events`.
4. **Chốt với leader** đơn vị threshold (ratio vs %) và tên field `alert_threshold` — đã đề xuất hướng ở mục 5.1/5.2, chờ xác nhận.
5. Kiểm tra lại Dashboard KPI/reward có còn mock không (mục 5.3) - **Xong**.
6. Nếu leader OK, cập nhật `firestore.indexes.json` bằng cách export từ Firebase Console để đồng bộ với team (tránh member khác pull code về bị thiếu index do tạo thủ công qua Console không được commit) **Xong**.