# ĐỀ XUẤT THIẾT KẾ DATABASE — HỆ THỐNG THÙNG RÁC THÔNG MINH AIoT

**Sub-Goal 3:** Dashboard, thông báo, thống kê, cấu hình & quản lý thiết bị từ xa  
**Người thực hiện:** Đặng Nguyễn Thành Hiếu (23127364)  
**Cơ sở:** Tài liệu đặc tả yêu cầu phiên bản 2.2 và Report 1 — Phân tích tác động của FREQ/NFREQ đến kiến trúc DB

---

## 1. Nguyên tắc thiết kế

Thiết kế database cho prototype này ưu tiên nguyên tắc **YAGNI (You Aren't Gonna Need It)**: chỉ đưa vào schema những dữ liệu đang được requirement bắt buộc hoặc có tác động trực tiếp đến dashboard trong giai đoạn hiện tại. Các phần có thể phát sinh sau như lịch sử cập nhật model, vòng đời cảnh báo phức tạp, thống kê tháng precompute sẽ được ghi nhận như extension point, chưa đưa vào core schema để tránh tăng độ phức tạp sớm.

Các yêu cầu chính từ đặc tả mới nhất:

- Dashboard cập nhật trạng thái thùng vừa ghi nhận rác trong **≤ 5 giây** (**NFREQ.5**).
- Hiển thị cảnh báo khi mức đầy đạt/vượt ngưỡng cấu hình, mặc định **0.8** (**FREQ.1**, **FREQ.9**).
- Ghi nhận sự kiện phân loại thành công gồm loại rác, mã thùng và thời gian (**FREQ.3**, **FREQ.4**).
- Tổng hợp thống kê theo loại rác, loại thùng, theo ngày và theo tháng (**FREQ.5**), nhưng yêu cầu lưu trữ tối thiểu chỉ là **30 ngày** (**NFREQ.6**).
- Hỗ trợ tối thiểu **10 thiết bị** trong cùng backend (**NFREQ.7**).
- Khi mất mạng, firmware có thể lưu tối đa 150 sự kiện hoặc 24 giờ rồi đồng bộ lại theo thứ tự thời gian (**NFREQ.8**).
- Quản trị viên cần xác thực cho tính năng quản trị (**NFREQ.14**).
- Cập nhật model AI từ xa là **nên có/tùy chọn**, không phải phần bắt buộc của core database (**FREQ.10**, **NFREQ.17**). Trong phạm vi hiện tại, nhóm thống nhất cách cập nhật model là train xong rồi nạp thủ công vào thiết bị/firmware.

## 2. Lựa chọn công nghệ: Firestore (Firebase)

Đề xuất dùng **Cloud Firestore** vì phù hợp với quy mô và thời gian triển khai của nhóm:

- Dễ tích hợp với backend REST API: backend dùng Firebase Admin SDK để đọc/ghi Firestore, còn Dashboard và ESP32 không truy cập Firestore trực tiếp.
- Đáp ứng dashboard cập nhật trong ≤ 5 giây bằng polling REST API mỗi 3-5 giây ở prototype; có thể nâng cấp SSE/WebSocket sau nếu cần realtime mượt hơn.
- Phù hợp với prototype ít thiết bị, tối thiểu 10 thiết bị theo NFREQ.7.
- Dễ tích hợp Firebase Authentication cho dashboard quản trị; backend xác minh Firebase ID Token trước khi cho phép thao tác quản trị.
- Giảm chi phí vận hành so với tự triển khai PostgreSQL + job scheduler.

**Đánh đổi chấp nhận:** Firestore không mạnh về JOIN và aggregate phức tạp. Vì vậy schema tách rõ 2 loại dữ liệu: trạng thái hiện tại để dashboard đọc nhanh, và event lịch sử để thống kê/truy vết.

## 2.1 Ranh giới giao tiếp backend

Thiết kế này không chọn hướng client ghi trực tiếp vào Firestore. Firestore là database nội bộ phía sau backend.

```text
Dashboard
  └─ REST API + Firebase ID Token
       └─ Backend
            ├─ Firestore
            └─ Firebase Auth

ESP32/Firmware
  └─ REST API + device token/API key
       └─ Backend
            └─ Firestore
```
![Sơ đồ kiến trúc giao tiếp backend](./ESP32-CAM%20Firmware%20Event-2026-07-09-142228.png)
Vai trò từng lớp:

- Dashboard chỉ gọi REST API, không giữ quyền ghi Firestore.
- ESP32 chỉ gửi telemetry/event và lấy cấu hình qua REST API, không dùng credential quản trị.
- Backend validate dữ liệu, xác thực quyền, chuẩn hóa timestamp, ghi event, cập nhật trạng thái hiện tại và thống kê.
- Firestore chỉ lưu dữ liệu; Firebase Auth chỉ xác thực người dùng dashboard.

## 3. Core schema đề xuất

```text
devices/{deviceId}
  ├─ name: string
  ├─ location: string
  ├─ last_seen_at: timestamp
  ├─ maintenance_mode: boolean
  ├─ firmware_version: string
  ├─ ai_model_version: string
  └─ compartments: {
        organic: {
          threshold: number,          // mặc định 0.8
          fill_percent: number,
          status: "normal" | "full"
        },
        paper: {
          threshold: number,
          fill_percent: number,
          status: "normal" | "full"
        },
        plastic: {
          threshold: number,
          fill_percent: number,
          status: "normal" | "full"
        }
      }

devices/{deviceId}/events/{eventId}
  ├─ event_type: "CLASSIFY" | "FULL_ALERT" | "ERROR" | "MAINTENANCE"
  ├─ waste_type: "organic" | "paper" | "plastic" | null
  ├─ target_compartment: "organic" | "paper" | "plastic" | null
  ├─ ai_confidence: number | null
  ├─ fill_percent: {
  │     organic: number,
  │     paper: number,
  │     plastic: number
  │   }
  ├─ alert_threshold: number
  ├─ device_timestamp: timestamp
  ├─ received_at: timestamp
  ├─ synced_late: boolean
  ├─ firmware_version: string
  └─ ai_model_version: string

daily_stats/{deviceId}_{yyyy-mm-dd}
  ├─ device_id: string
  ├─ date: string
  ├─ organic_count: number
  ├─ paper_count: number
  ├─ plastic_count: number
  └─ total_count: number

users/{uid}
  ├─ email: string
  └─ role: "admin" | "viewer"
```

## 4. Vì sao schema này đủ cho phiên bản hiện tại

### 4.1 `devices` — trạng thái hiện tại của thùng

`devices/{deviceId}` là document trạng thái hiện tại do backend cập nhật. Dashboard không đọc trực tiếp Firestore; dashboard gọi REST API như `GET /api/devices` hoặc `GET /api/devices/{id}` để backend trả về trạng thái mới nhất. Mỗi lần firmware gửi telemetry mới qua API, backend cập nhật mức đầy từng ngăn, `last_seen_at`, phiên bản firmware/model và trạng thái bảo trì.

Không lưu `connection_status` cố định trong DB vì trạng thái online/offline có thể suy ra từ `last_seen_at`. Cách này tránh trường hợp dữ liệu bị lệch, ví dụ `connection_status = "online"` nhưng thiết bị đã lâu không gửi heartbeat.

### 4.2 `events` — lịch sử sự kiện thô

`devices/{deviceId}/events` là log insert-only cho các sự kiện `CLASSIFY`, `FULL_ALERT`, `ERROR`, `MAINTENANCE`. Cấu trúc này bám sát bảng dữ liệu tối thiểu trong đặc tả: device ID, timestamp, event type, waste category, confidence, target compartment, fill level, alert threshold, firmware version và AI model version.

`device_timestamp` là thời gian do firmware gán tại lúc sự kiện xảy ra. `received_at` là thời gian server nhận được. Khi mất mạng và đồng bộ lại, `synced_late = true` giúp phân biệt dữ liệu đến trễ mà vẫn giữ đúng thứ tự thời gian gốc theo NFREQ.8.

### 4.3 `daily_stats` — thống kê đủ dùng, chưa precompute tháng

Đặc tả yêu cầu thống kê theo ngày và theo tháng, nhưng dữ liệu lưu tối thiểu chỉ 30 ngày và quy mô tối thiểu là 10 thiết bị. Vì vậy core schema chỉ precompute `daily_stats`.

Thống kê tháng có thể được tính bằng cách cộng các document ngày trong khoảng thời gian được chọn. Với prototype, đọc khoảng 30 document/ngày cho mỗi thiết bị là chấp nhận được và đơn giản hơn so với duy trì thêm `monthly_stats`.

Chỉ thêm `monthly_stats` khi có bằng chứng rằng dashboard bị chậm, số thiết bị tăng nhiều, hoặc chi phí read thực sự trở thành vấn đề.

### 4.4 `users` — phân quyền dashboard

`users/{uid}` chỉ lưu metadata phân quyền như `role`. Thông tin đăng nhập thật do Firebase Authentication quản lý, đáp ứng NFREQ.14 và tránh tự lưu credential trong database.

## 5. Những phần cố ý chưa đưa vào core schema

Các điểm dưới đây không được xem là thiếu sót ngoài ý muốn, mà là phần nhóm chủ động giới hạn khỏi core schema để phù hợp phạm vi prototype:

| Phần chưa đưa vào core | Requirement liên quan | Lý do chấp nhận ở prototype | Khi nào nên thêm / rủi ro dài hạn |
|---|---|---|---|
| `model_versions` và luồng upload model từ dashboard | FREQ.10, NFREQ.17 | FREQ.10 là tính năng "nên có"; NFREQ.17 chỉ bắt buộc hỗ trợ cập nhật model tối thiểu bằng cách nạp thủ công. Nhóm hiện train model xong rồi nạp trực tiếp vào thiết bị/firmware, DB chỉ lưu `ai_model_version` để truy vết. | Thêm khi triển khai cập nhật từ xa thật, rollback, changelog model, xác nhận trạng thái triển khai model qua dashboard, hoặc quản lý nhiều phiên bản model cho nhiều thiết bị. |
| `commands` collection cho lệnh chờ | FREQ.9, FREQ.11, NFREQ.19 | Với demo, backend có thể ghi trực tiếp `threshold` và `maintenance_mode` vào `devices`; firmware lấy cấu hình mới khi online. | Thêm khi cần queue lệnh offline, retry, trạng thái `pending/applied/failed`; nếu không sẽ khó chứng minh lệnh đã được áp dụng trong ≤ 7 giây ở môi trường thật. |
| `alerts` collection riêng | FREQ.1 | Cảnh báo đầy hiện tại có thể hiển thị từ `devices.compartments.{type}.status = "full"` và event `FULL_ALERT`, chưa cần lifecycle `active/resolved`. | Thêm khi cần danh sách cảnh báo đang xử lý, lịch sử xử lý, người xác nhận, SLA dọn rác hoặc lifecycle active/resolved/acknowledged. |
| `monthly_stats` precompute | FREQ.5 | Thống kê tháng có thể cộng từ `daily_stats`; quy mô tối thiểu 30 ngày và 10 thiết bị vẫn chấp nhận được. | Thêm khi dashboard thống kê tháng chậm, số thiết bị tăng, thời gian lưu trữ dài hơn, hoặc chi phí read trở thành vấn đề. |
| Cơ chế TTL/cron dọn dữ liệu | NFREQ.6 | Schema đã có `device_timestamp` và `received_at`, đủ để thêm TTL/scheduled cleanup sau mà không đổi cấu trúc chính. | Thêm khi vận hành dài ngày để tránh tăng chi phí lưu trữ và truy vấn. |
| Lưu ảnh phân loại | NFREQ.16 | NFREQ.16 yêu cầu xóa ảnh tạm trong 2 giây theo mặc định, nên core schema không lưu ảnh. | Chỉ thêm khi có chính sách quyền riêng tư rõ ràng và mục tiêu debug/dataset cụ thể. |

## 6. Luồng ghi dữ liệu chính

### 6.1 Khi phân loại thành công

1. Firmware phân loại rác và điều khiển ngăn tương ứng.
2. Sau khi đóng nắp, firmware đọc cảm biến siêu âm và tính `fill_percent`.
3. Firmware gửi event `CLASSIFY` lên backend REST API gồm `waste_type`, `ai_confidence`, `target_compartment`, `device_timestamp`, `firmware_version`, `ai_model_version`.
4. Backend ghi document mới vào `devices/{deviceId}/events`.
5. Backend cập nhật `devices/{deviceId}` để dashboard lấy trạng thái mới qua API.
6. Backend increment `daily_stats/{deviceId}_{yyyy-mm-dd}`.

### 6.2 Khi ngăn vượt ngưỡng đầy

1. Firmware phát hiện `fill_percent >= threshold`.
2. Firmware gửi event `FULL_ALERT` lên backend REST API gồm ngăn đầy, phần trăm đầy và thời điểm phát hiện.
3. Backend ghi event và cập nhật `devices.compartments.{type}.status = "full"`.
4. Dashboard gọi API định kỳ hoặc nhận push sau này để hiển thị cảnh báo.

### 6.3 Khi mất mạng rồi đồng bộ lại

1. Firmware giữ queue cục bộ tối đa 150 sự kiện hoặc 24 giờ theo NFREQ.8.
2. Khi có mạng lại, firmware gửi batch lên backend REST API theo thứ tự `device_timestamp`.
3. Backend ghi từng event với `synced_late = true`.
4. Thống kê ngày dựa trên `device_timestamp`, không dựa trên `received_at`.

## 7. Retention dữ liệu

NFREQ.6 yêu cầu lưu tối thiểu 30 ngày. Với prototype, đề xuất:

- Giữ `events` tối thiểu 30 ngày.
- Không bắt buộc tự động xóa ngay trong giai đoạn đầu nếu dung lượng vẫn nhỏ.
- Nếu cần tuân thủ đúng câu "xóa dữ liệu cũ hơn" trong phần giải pháp của đặc tả, có thể thêm TTL hoặc scheduled Cloud Function sau, nhưng không làm phức tạp schema.

Điểm quan trọng là schema đã có `device_timestamp` và `received_at`, nên việc dọn dữ liệu theo tuổi bản ghi có thể thêm sau mà không đổi cấu trúc chính.

## 8. Index/query cần chuẩn bị

Các truy vấn chính:

- Dashboard trạng thái: gọi backend API, backend đọc `devices`.
- Lịch sử thiết bị: `devices/{deviceId}/events` order by `device_timestamp desc`.
- Lọc thống kê theo ngày: đọc `daily_stats` theo `device_id` và `date`.
- Lọc event theo loại rác trong một thiết bị: query subcollection `events` theo `waste_type` và `device_timestamp`.

Index đề xuất:

```text
devices/{deviceId}/events:
  - device_timestamp desc
  - event_type asc, device_timestamp desc
  - waste_type asc, device_timestamp desc

daily_stats:
  - device_id asc, date asc
```

## 9. Đối chiếu requirement theo mức đáp ứng

Bảng này không dùng một nhãn "đáp ứng" chung cho mọi requirement, vì có requirement được schema xử lý trực tiếp, có requirement chỉ được schema hỗ trợ một phần, và có requirement không thuộc trách nhiệm của database.

| Mức | Ý nghĩa |
|---|---|
| Đầy đủ | Core schema đã có cấu trúc dữ liệu cần thiết cho requirement ở phạm vi database. |
| Một phần | Schema chỉ lưu dữ liệu liên quan hoặc bằng chứng vận hành; tính năng đầy đủ cần thêm logic/collection ngoài core. |
| N/A | Không thuộc phạm vi database; thuộc firmware, authentication, API contract hoặc tầng ứng dụng. |

| Requirement | Mức đáp ứng | Collection/document liên quan | Ghi chú |
|---|---|---|---|
| FREQ.1 | Đầy đủ | `devices`, `devices/{id}/events` | Cảnh báo đầy được thể hiện bằng `devices.compartments.{type}.status = "full"` và event `FULL_ALERT`. Chưa có lifecycle xử lý cảnh báo riêng. |
| FREQ.2 | Một phần | `devices/{id}/events` | DB có chỗ nhận dữ liệu đồng bộ trễ bằng `synced_late`; việc lưu cục bộ khi mất mạng là trách nhiệm firmware. |
| FREQ.3 | Đầy đủ | `devices/{id}/events`, `daily_stats` | Ghi nhận sự kiện phân loại thành công và cập nhật thống kê ngày. |
| FREQ.4 | Đầy đủ | `devices/{id}/events` | Event có `waste_type`, `device_timestamp`; mã thùng nằm ở path `devices/{deviceId}`. |
| FREQ.5 | Một phần | `daily_stats`, `devices/{id}/events` | Đáp ứng thống kê ngày. Thống kê tháng được tính từ `daily_stats`, chưa precompute `monthly_stats`. |
| FREQ.6 | Đầy đủ | `devices`, `daily_stats` | Backend đọc trạng thái hiện tại từ `devices` và thống kê từ `daily_stats`, sau đó trả cho dashboard qua REST API. |
| FREQ.7 | Đầy đủ | `devices` | Trạng thái offline được suy ra từ `last_seen_at`, không lưu `connection_status` riêng. |
| FREQ.8 | Đầy đủ | `daily_stats`, `devices/{id}/events` | Có `device_id/date` cho thống kê và `waste_type/device_timestamp` cho lọc event. |
| FREQ.9 | Đầy đủ | `devices` | Ngưỡng đầy nằm trong `devices.compartments.{type}.threshold`. |
| FREQ.10 | Một phần / defer | `devices`, `devices/{id}/events` | Core chỉ lưu `ai_model_version` để truy vết. Nhóm chưa cam kết hoàn thiện upload model từ dashboard; trong phạm vi hiện tại, model được train xong rồi nạp thủ công vào thiết bị/firmware. Nếu triển khai cập nhật từ xa thật, cần thêm `model_versions` hoặc `commands`. |
| FREQ.11 | Một phần | `devices` | Có `maintenance_mode` để backend lưu cấu hình từ dashboard. Nếu cần queue lệnh offline và trạng thái `pending/applied/failed`, phải thêm `commands`. |
| NFREQ.5 | Một phần | `devices` | DB có document trạng thái mới nhất để backend trả nhanh cho dashboard. Việc đạt ≤ 5 giây phụ thuộc REST polling 3-5 giây hoặc SSE/WebSocket ở tầng backend. |
| NFREQ.6 | Đầy đủ | `devices/{id}/events`, `daily_stats` | Có timestamp để giữ/tự dọn dữ liệu tối thiểu 30 ngày. TTL/cron là triển khai vận hành, không cần đổi schema. |
| NFREQ.7 | Đầy đủ | Toàn bộ schema | `deviceId` là partition key trong `devices`, subcollection `events`, và key của `daily_stats`. |
| NFREQ.8 | Một phần | `devices/{id}/events` | DB hỗ trợ batch ghi lại theo `device_timestamp` và đánh dấu `synced_late`; queue 150 event/24h thuộc firmware. |
| NFREQ.10 | N/A với DB | `devices/{id}/events` chỉ ghi bằng chứng | Kiểm tra servo/cảm biến khi có điện lại là trách nhiệm firmware. DB chỉ nhận event `ERROR` nếu firmware phát hiện lỗi. |
| NFREQ.11 | N/A với DB | `devices/{id}/events` chỉ ghi bằng chứng | Phát hiện lỗi servo/cảm biến trong 5 giây thuộc thiết bị/firmware. DB chỉ lưu log/cảnh báo sau khi lỗi được báo cáo. |
| NFREQ.12 | Một phần | `devices/{id}/events` | Event có `ai_model_version`, `ai_confidence`, `waste_type` để team kỹ thuật đánh giá định kỳ; quy trình đánh giá không thuộc DB. |
| NFREQ.13 | Một phần | `devices`, `devices/{id}/events` | Có ghi version đang chạy và version tại thời điểm phát sinh event. Chưa có quản lý vòng đời version, rollback, changelog hoặc `model_versions`. |
| NFREQ.14 | Đầy đủ | `users` | `users.role` lưu metadata phân quyền; xác thực thật do Firebase Authentication xử lý. |
| NFREQ.15 | N/A với DB | Không áp dụng | Không lưu credential trong firmware là quyết định kiến trúc auth/firmware, không phải schema. Report chỉ liên quan gián tiếp qua việc dùng Firebase Auth và phân quyền. |
| NFREQ.17 | Một phần / defer | `devices`, `devices/{id}/events` | Schema có chỗ ghi `ai_model_version`; cập nhật model tối thiểu bằng nạp thủ công không cần DB. Đây là hướng nhóm chọn cho prototype; cập nhật từ xa qua dashboard là tùy chọn và đã defer khỏi core schema. |
| NFREQ.18 | N/A với DB | Không áp dụng | Tài liệu interface cho dashboard/API thuộc API contract, không phải thiết kế collection. |
| NFREQ.19 | Một phần | `devices` | `threshold` và `maintenance_mode` nằm trong `devices`; việc firmware áp dụng trong ≤ 7 giây phụ thuộc endpoint lấy cấu hình, chu kỳ polling của ESP32 và logic firmware. |

## 10. Kết luận

Thiết kế đề xuất giữ core database ở mức nhỏ: **trạng thái hiện tại (`devices`) + lịch sử sự kiện (`events`) + thống kê ngày (`daily_stats`) + phân quyền (`users`)**. Cấu trúc này đáp ứng các yêu cầu bắt buộc của đặc tả phiên bản 2.2, đồng thời để ngỏ đường nâng cấp khi hệ thống thực sự cần lịch sử cảnh báo, thống kê tháng precompute, queue lệnh hoặc quản lý phiên bản model đầy đủ.

Ưu điểm chính của hướng này là ít dữ liệu trùng lặp, ít logic đồng bộ chéo, dễ demo, dễ kiểm thử và không tự khóa nhóm vào một schema quá nặng khi requirement vẫn còn ở mức prototype.
