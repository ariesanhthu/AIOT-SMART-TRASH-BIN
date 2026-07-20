# Cập nhật thực hiện so với spec và đánh giá đánh đổi prototype

Tài liệu này tổng hợp nhanh việc frontend/backend hiện đã merge đúng tới đâu so với tài liệu đặc tả và các tài liệu kiến trúc DB. Phạm vi đánh giá tập trung vào dashboard, thông báo, thống kê, cấu hình thiết bị và luồng ghi dữ liệu xuống DB.

## 1. Kết luận ngắn

Hướng hiện tại không sai hướng đồ án. Kiến trúc Dashboard -> Backend -> Firestore và ESP32 -> Firestore trực tiếp phù hợp prototype, giảm công viết ingestion API và vẫn bám được yêu cầu cốt lõi: lưu event, hiển trạng thái thùng, thống kê theo ngày, cảnh báo đầy, cấu hình ngưỡng.

Tuy nhiên, nếu nói là "đã đạt đầy đủ spec" thì chưa đúng. Bản hiện tại nên được ghi là prototype có core data flow, nhưng còn thiếu realtime/polling <= 5 giây, UI cấu hình chưa nối API thật, alert lifecycle chưa có backend, và một số màn hình dashboard vẫn còn mock.

## 2. Đối chiếu theo nhóm yêu cầu

| Nhóm yêu cầu | Spec mong muốn | Hiện trạng code | Đánh giá |
|---|---|---|---|
| Dashboard xem trạng thái thùng | Hiện mức đầy từng ngăn, trạng thái online/offline, last update | `GET /api/devices` đã có; frontend mapping ra `Bin`; online suy ra từ `lastSeenAt` | Đạt phần dữ liệu cốt lõi |
| Cập nhật dashboard <= 5 giây | Dashboard nhận dữ liệu mới trong <= 5 giây | Hook frontend fetch 1 lần, chưa polling/listener | Chưa đạt, cần thêm polling 3-5 giây hoặc realtime listener |
| Ghi event phân loại | Lưu loại rác, thùng, thời gian, confidence, compartment | ESP32 schema + backend read event + Cloud Function đã có | Đạt về schema/backend; cần firmware gửi đúng payload |
| Thống kê theo ngày | Tổng hợp organic/paper/plastic theo ngày | Cloud Function increment `daily_stats`; backend/FE đọc daily stats | Đạt core; thiếu index `daily_stats` trong config |
| Thống kê theo tháng | Có thống kê theo tháng | Chưa có `monthly_stats`; có thể cộng từ `daily_stats` | Chấp nhận được cho prototype 30 ngày |
| Cảnh báo đầy | Hiện `FULL_ALERT` khi vượt ngưỡng | Event `FULL_ALERT`, FE đọc alert; Function set status full | Đạt phần hiển thị; chưa có lifecycle active/resolved backend |
| Xử lý cảnh báo | Theo dõi cảnh báo đã xử lý/chưa xử lý | FE chỉ mark local state | Chưa đạt nếu spec yêu cầu lưu trạng thái xử lý thật |
| Cấu hình ngưỡng đầy | Admin đổi threshold từng ngăn từ dashboard | Backend `PATCH /config` và FE service đã có; `ConfigPage` chưa gọi API | Backend đạt, UI chưa merge thật |
| Bảo trì từ xa | Bật/tắt `maintenance_mode` | Backend support field; UI chưa nối thật | Một phần |
| Cập nhật model AI từ xa | Optional/nên có, quản lý version model | Chỉ lưu `ai_model_version`; UI model là mock | Chấp nhận prototype nếu team chốt nạp model thủ công |
| Bảo mật dashboard | Admin/user xác thực trước khi gọi API | FE lấy Firebase ID Token; backend có filter auth | Đúng hướng |
| Bảo mật ESP32 | Không nhúng Admin key vào firmware | Backend cấp custom token, Security Rules giới hạn `device_id` | Đúng hướng prototype |
| Mất mạng và sync lại | Queue local 150 event/24h, sync theo timestamp | DB có `device_timestamp`, `synced_late`; firmware chưa được đánh giá trong phạm vi này | DB hỗ trợ, firmware cần implement |
| Lưu dữ liệu tối thiểu 30 ngày | Giữ event/stat tối thiểu 30 ngày | Schema có timestamp/date; chưa có TTL/cleanup | Chấp nhận prototype, cần policy vận hành sau |

## 3. Những gì đã làm được

- Backend Spring Boot có API đọc thiết bị, đọc event, đọc daily stats, update config và cấp custom token cho ESP32.
- Frontend đã có `apiClient` tự động gắn Firebase ID Token của user vào request.
- Frontend type DTO (`DeviceResponseDto`, `EventResponseDto`, `DailyStatDto`) khớp với backend response camelCase.
- Mapper frontend đã chuyển device response thành model `Bin` để hiển dashboard/bin detail.
- `StatisticsPage` đã đọc daily stats thật theo `deviceId`, `from`, `to`.
- `BinDetailPage` đã đọc lịch sử `CLASSIFY` thật.
- `AlertsPage` và dashboard alert summary đã đọc `FULL_ALERT` thật.
- Firestore Rules đã thể hiện rõ ranh giới: device chỉ ghi path của mình, không sửa threshold/maintenance mode.
- Cloud Function đã thay backend làm side effect: increment daily stats và cập nhật status full.

## 4. Những gì bỏ qua/cố ý defer vì prototype

| Phần bỏ qua/defer | Lý do prototype | Có sai hướng không? | Khi nào cần làm |
|---|---|---|---|
| `monthly_stats` precompute | Quy mô 30 ngày/ít thiết bị, có thể cộng từ daily stats | Không sai | Khi query tháng chậm hoặc số device tăng |
| Alert entity riêng với active/resolved/acknowledged | Demo có thể hiện FULL_ALERT từ event log | Không sai nếu nói rõ "xử lý local" | Khi cần lưu trạng thái xử lý thật |
| Upload/deploy model AI từ dashboard | Spec xem là optional/nên có; prototype có thể nạp model thủ công | Không sai nếu team chốt phạm vi | Khi cần OTA model, rollback, changelog |
| Push config realtime <= 7 giây | Pull heartbeat/piggyback đơn giản hơn MQTT | Có đánh đổi với NFREQ.19 | Khi muốn giữ đúng <= 7 giây trong mọi tình huống |
| TTL/cron xóa data cũ | Dữ liệu demo nhỏ, chưa tốn chi phí | Không sai | Khi chạy lâu ngày hoặc cần policy retention nghiêm |
| Reward/student points backend | Ngoài core dashboard thùng rác hiện tại | Không sai nếu ghi là mock | Khi spec demo cần gamification thật |

## 5. Những điểm có rủi ro nếu không sửa

### 5.1 Thiếu index cho `daily_stats`

Backend query:

```text
where device_id == ?
where date >= ?
where date <= ?
orderBy date asc
```

Design doc có đề xuất index `daily_stats(device_id asc, date asc)` nhưng `firestore.indexes.json` hiện chỉ có index cho `events`. Khi chạy thật, Firestore có thể báo lỗi cần composite index.

Khuyến nghị: thêm index này trước khi demo Statistics.

### 5.2 ConfigPage chưa lưu xuống backend

Backend và frontend service đã sẵn sàng:

```text
PATCH /api/devices/{deviceId}/config
```

Nhưng UI `ConfigPage` hiện còn dùng mock `THRESHOLDS` và `showToast`. Nếu leader hỏi "dashboard có đổi ngưỡng thật chưa" thì câu trả lời hiện tại là chưa, mới có contract/service.

### 5.3 Chưa đảm bảo dashboard cập nhật <= 5 giây

`useBins`, `useFullAlerts`, `useDailyStats` fetch khi mount/thay đổi dependency, chưa polling. Để bám spec, bản prototype nên thêm polling 3-5 giây cho:

- danh sách device/mức đầy
- `FULL_ALERT`
- daily stats nếu màn hình thống kê đang mở

### 5.4 Đơn vị threshold chưa thống nhất

Tài liệu DB có nói threshold mặc định `0.8`, UI lại hiển threshold theo `%` như `80`, `85`, `90`. Code so sánh mức đầy đang dùng `%`.

Cần chốt:

- Hoặc Firestore lưu threshold theo `%` 0-100.
- Hoặc Firestore lưu ratio 0-1 và frontend convert khi hiển thị/lưu.

Để demo ít lỗi, nên chốt `%` 0-100 vì UI và `fillPercent` đang theo phần trăm.

### 5.5 Suy đoán "từ chối" AI qua `alertThreshold` có thể sai nghĩa

Frontend đang tính kết quả phân loại:

```text
aiConfidence >= alertThreshold ? success : rejected
```

Trong design DB, `alert_threshold` nghiêng về ngưỡng cảnh báo đầy thùng, không phải AI confidence threshold. Nếu cần hiển thị "từ chối" chính xác, nên thêm field rõ hơn, ví dụ:

```text
ai_threshold
classification_status: accepted | rejected
```

## 6. Đánh giá đánh đổi có đáng không

Đánh đổi hiện tại là đáng giá cho prototype:

- ESP32 ghi Firestore trực tiếp giúp giảm backend ingestion API, nhanh có demo, phù hợp quy mô 10 thiết bị.
- Dashboard vẫn qua backend giúp giữ authentication/admin logic gọn và không lo expose quyền Firestore cho web client.
- Chỉ precompute daily stats là hợp lý vì spec tối thiểu 30 ngày, chưa cần monthly stats riêng.
- Chưa làm alert lifecycle/model OTA/reward backend là chấp nhận được nếu team trình bày rõ đây là extension, không phải core của prototype.

Đánh đổi cần cảnh giác:

- Không polling/realtime thì không đạt chỉ tiêu <= 5 giây của dashboard.
- Config pull 30-60 giây không đạt NFREQ.19 <= 7 giây nếu spec giữ nguyên.
- Config UI còn mock sẽ dễ bị hiểu nhầm là đã có remote config, trong khi backend mới sẵn sàng.

## 7. Đề xuất việc nên làm tiếp trước merge/demo

1. Thêm polling 3-5 giây cho device status và `FULL_ALERT`.
2. Nối `ConfigPage` vào API `GET /api/devices`, `GET /api/devices/{id}`, `PATCH /api/devices/{id}/config`.
3. Thêm Firestore index cho `daily_stats(device_id asc, date asc)`.
4. Chốt đơn vị threshold là `%` hoặc ratio và sửa tài liệu/code cho đồng nhất.
5. Nếu không kịp làm alert lifecycle, giữ local resolve nhưng ghi rõ trong slide/demo là prototype UI state.
