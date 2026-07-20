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

- ESP32 ghi thẳng vào Firestore (không qua backend trung gian ở chiều thiết bị), dùng Firebase Auth device credential (custom token hoặc anonymous auth theo `device_id`) kết hợp Firestore Security Rules để giới hạn phạm vi ghi/đọc.
- Dashboard vẫn đi qua backend riêng: backend dùng Firebase Admin SDK để đọc/ghi Firestore thay cho dashboard, xác minh Firebase ID Token trước khi cho phép thao tác quản trị (đổi ngưỡng, bật/tắt bảo trì, đọc thống kê).
- Đáp ứng dashboard cập nhật trong ≤ 5 giây bằng polling REST API mỗi 3-5 giây ở prototype; có thể nâng cấp SSE/WebSocket sau nếu cần realtime mượt hơn.
- Phù hợp với prototype ít thiết bị, tối thiểu 10 thiết bị theo NFREQ.7.
- Giảm chi phí vận hành so với tự triển khai PostgreSQL + job scheduler; đồng thời giảm code backend phía ingestion vì không cần viết REST endpoint nhận event từ ESP32.

**Đánh đổi chấp nhận:** Firestore không mạnh về JOIN và aggregate phức tạp. Vì vậy schema tách rõ 2 loại dữ liệu: trạng thái hiện tại để dashboard đọc nhanh, và event lịch sử để thống kê/truy vết. Ngoài ra, việc ESP32 ghi trực tiếp có nghĩa nhóm đánh đổi lớp validate/chuẩn hóa dữ liệu từ code backend sang Firestore Security Rules + Cloud Functions — xem mục 2.1 và 2.2.

## 2.1 Ranh giới giao tiếp — ESP32 ghi trực tiếp, Dashboard qua backend

**Quyết định đã đổi so với bản trước:** trước đây tài liệu này chọn "không cho client ghi trực tiếp vào Firestore". Nhóm hiện chốt lại theo hướng khác cho hai chiều giao tiếp riêng biệt, lý do: ESP32 không cần polling liên tục để chờ backend phản hồi, và giảm bớt một lớp REST server phải viết/maintain cho việc chỉ nhận telemetry.

```text
Dashboard
  └─ REST API + Firebase ID Token
       └─ Backend
            ├─ Firestore (đọc trạng thái, thống kê; ghi threshold/maintenance_mode)
            └─ Firebase Auth

ESP32/Firmware
  └─ Firestore SDK/REST + Firebase Auth device credential (per-device, không phải admin key)
       └─ Firestore
            ├─ ghi trực tiếp: devices/{deviceId} (trạng thái), devices/{deviceId}/events (sự kiện)
            └─ đọc trực tiếp: devices/{deviceId} (threshold, maintenance_mode — xem mục 2.2 cách đọc)

Cloud Functions (Firestore Trigger)
  └─ onCreate devices/{deviceId}/events → increment daily_stats, cập nhật compartments.status, tạo FULL_ALERT
```
![Sơ đồ kiến trúc giao tiếp backend](./ESP32-CAM%20Firmware%20Event-2026-07-09-142228.png)
Vai trò từng lớp:

- Dashboard chỉ gọi REST API, không giữ quyền ghi Firestore trực tiếp.
- ESP32 ghi/đọc Firestore trực tiếp bằng credential riêng của từng thiết bị, không dùng credential quản trị (đáp ứng NFREQ.15: không lưu API key admin trong firmware).
- Vì không còn backend chặn ở chiều ghi của ESP32, các việc trước đây backend làm (validate dữ liệu, chuẩn hóa timestamp, cập nhật thống kê) phải chuyển sang **Firestore Security Rules** (validate cấu trúc/giá trị hợp lệ khi ghi) và **Cloud Functions** (side-effect sau khi ghi thành công) — không được bỏ qua, nếu không NFREQ.8 (đồng bộ đúng thứ tự) và FREQ.5 (tổng hợp thống kê) sẽ không ai đảm nhiệm.
- Firebase Auth xác thực cả người dùng dashboard (ID Token) lẫn thiết bị (custom token/anonymous, gắn `device_id` vào claims để Security Rules kiểm tra thiết bị chỉ ghi được đúng path của nó).

## 2.2 Đọc cấu hình từ thiết bị — pull theo chu kỳ, không polling liên tục

Vì ESP32 giờ đọc thẳng Firestore thay vì nhận lệnh đẩy từ backend, UC 2.5.4 (cấu hình từ xa) đổi từ mô hình "server đẩy lệnh" sang "thiết bị tự kéo cấu hình mới nhất", theo 2 cơ chế kết hợp — không cần vòng lặp polling tần suất cao:

1. **Piggyback theo hoạt động sẵn có:** mỗi lần ESP32 vốn đã ghi `devices/{deviceId}/events` (sau khi phân loại, sau khi đo mức đầy), nó đọc kèm `devices/{deviceId}.compartments.{type}.threshold` và `maintenance_mode` trong cùng phiên kết nối — không tốn thêm handshake mạng.
2. **Heartbeat chu kỳ dài (khuyến nghị 30–60 giây):** phòng trường hợp lâu không có ai bỏ rác, thiết bị vẫn đọc lại `devices/{deviceId}` theo chu kỳ này để không bị "đứng" cấu hình cũ quá lâu.

Hệ quả cần ghi vào spec: NFREQ.19 ("áp dụng ≤ 7 giây") không còn được đảm bảo bằng cơ chế pull này; xem mục 9 để biết cách điều chỉnh mức đáp ứng. Khi thật sự cần real-time dưới ngưỡng giây, hướng nâng cấp không cần đổi schema là thêm MQTT (đã có trong lớp giao tiếp của đặc tả gốc) — Cloud Function publish lên topic `devices/{deviceId}/config` khi `devices/{deviceId}` thay đổi, ESP32 subscribe sẵn (kết nối persistent, không phải polling).

## 3. Core schema đề xuất

```text
devices/{deviceId}
  ├─ name: string
  ├─ location: string
  ├─ last_seen_at: timestamp
  ├─ maintenance_mode: boolean
  ├─ firmware_version: string
  ├─ ai_model_version: string
  ├─ class_name: string 
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

`devices/{deviceId}` là document trạng thái hiện tại, giờ được **ESP32 tự cập nhật trực tiếp** (mức đầy từng ngăn, `last_seen_at`, phiên bản firmware/model) mỗi khi có telemetry mới, còn `threshold`/`maintenance_mode` do **dashboard qua backend** ghi vào cùng document này. Dashboard không đọc/ghi trực tiếp Firestore; dashboard gọi REST API như `GET /api/devices` hoặc `GET /api/devices/{id}` để backend trả về trạng thái mới nhất, và `PATCH /api/devices/{id}/config` để backend ghi threshold/maintenance_mode xuống Firestore.

Vì cùng một document giờ có 2 nguồn ghi (ESP32 ghi phần trạng thái đo được, backend ghi phần cấu hình do người quản lý đặt), Firestore Security Rules cần tách quyền theo field: ESP32 chỉ được phép ghi các field trạng thái (`fill_percent`, `status`, `last_seen_at`, version), không được ghi `threshold`/`maintenance_mode`; ngược lại backend (qua Admin SDK, bỏ qua rules) là nơi duy nhất ghi `threshold`/`maintenance_mode`.

Không lưu `connection_status` cố định trong DB vì trạng thái online/offline có thể suy ra từ `last_seen_at`. Cách này tránh trường hợp dữ liệu bị lệch, ví dụ `connection_status = "online"` nhưng thiết bị đã lâu không gửi heartbeat.

### 4.2 `events` — lịch sử sự kiện thô

`devices/{deviceId}/events` là log insert-only cho các sự kiện `CLASSIFY`, `FULL_ALERT`, `ERROR`, `MAINTENANCE`. Cấu trúc này bám sát bảng dữ liệu tối thiểu trong đặc tả: device ID, timestamp, event type, waste category, confidence, target compartment, fill level, alert threshold, firmware version và AI model version.

`device_timestamp` là thời gian do firmware gán tại lúc sự kiện xảy ra. `received_at` giờ là thời gian Firestore ghi nhận document (dùng `serverTimestamp()` thay vì backend gán, vì không còn backend chặn giữa). Khi mất mạng và đồng bộ lại, firmware tự đặt `synced_late = true` giúp phân biệt dữ liệu đến trễ mà vẫn giữ đúng thứ tự thời gian gốc theo NFREQ.8 — do không còn backend validate, Security Rules nên ràng buộc tối thiểu: `device_timestamp` phải có mặt và thuộc kiểu timestamp hợp lệ khi ghi.

Vì ESP32 ghi thẳng, không ai đứng giữa để tăng `daily_stats` hay chuyển `compartments.status` sang `"full"` như trước. Việc này chuyển sang **Cloud Function trigger `onCreate`** trên `devices/{deviceId}/events`: mỗi document event mới tạo ra sẽ kích hoạt function tương ứng để cộng dồn `daily_stats` (theo `waste_type`) và cập nhật `devices/{deviceId}.compartments.{type}.status` khi `event_type == "FULL_ALERT"`.

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
3. Firmware ghi trực tiếp document mới vào `devices/{deviceId}/events` (Firestore SDK/REST, dùng device credential) gồm `waste_type`, `ai_confidence`, `target_compartment`, `device_timestamp`, `firmware_version`, `ai_model_version`.
4. Trong cùng phiên, firmware cập nhật `devices/{deviceId}` (phần trạng thái đo được: `fill_percent`, `last_seen_at`) và **đọc kèm** `threshold`/`maintenance_mode` hiện tại từ chính document đó (piggyback theo mục 2.2) để dùng cho lần hoạt động kế tiếp.
5. Cloud Function `onCreate` trên `events` tự động increment `daily_stats/{deviceId}_{yyyy-mm-dd}`.

### 6.2 Khi ngăn vượt ngưỡng đầy

1. Firmware phát hiện `fill_percent >= threshold` (threshold đọc được từ lần piggyback/heartbeat gần nhất).
2. Firmware ghi trực tiếp event `FULL_ALERT` vào `devices/{deviceId}/events` gồm ngăn đầy, phần trăm đầy và thời điểm phát hiện.
3. Cloud Function `onCreate` đọc event `FULL_ALERT` và cập nhật `devices.compartments.{type}.status = "full"`.
4. Dashboard gọi backend API định kỳ (3–5 giây) hoặc nhận push sau này để hiển thị cảnh báo.

### 6.3 Khi mất mạng rồi đồng bộ lại

1. Firmware giữ queue cục bộ tối đa 150 sự kiện hoặc 24 giờ theo NFREQ.8.
2. Khi có mạng lại, firmware ghi batch trực tiếp lên Firestore theo thứ tự `device_timestamp`, đánh dấu `synced_late = true` cho các event này.
3. Cloud Function xử lý từng event mới như bình thường (không phân biệt event đến đúng giờ hay trễ khi tính `daily_stats`).
4. Thống kê ngày dựa trên `device_timestamp`, không dựa trên `received_at`.

### 6.4 Khi quản lý đổi ngưỡng đầy hoặc bật/tắt bảo trì

1. Quản lý thao tác trên dashboard, gọi backend API (`PATCH /api/devices/{id}/config`) kèm Firebase ID Token.
2. Backend xác thực quyền, dùng Admin SDK ghi `threshold`/`maintenance_mode` vào `devices/{deviceId}`.
3. Thiết bị **không** nhận được đẩy ngay; cấu hình mới chỉ được ESP32 đọc thấy ở lần piggyback/heartbeat kế tiếp (xem mục 2.2) — đây là điểm khác với thiết kế cũ và cần phản ánh trong spec ở NFREQ.19.

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
| FREQ.9 | Đầy đủ (lưu trữ) / Một phần (áp dụng xuống thiết bị) | `devices` | Ngưỡng đầy nằm trong `devices.compartments.{type}.threshold`, backend ghi được ngay khi quản lý cấu hình. Việc thiết bị *nhận* được giá trị mới phụ thuộc cơ chế pull ở mục 2.2, không phải push tức thời. |
| FREQ.10 | Một phần / defer | `devices`, `devices/{id}/events` | Core chỉ lưu `ai_model_version` để truy vết. Nhóm chưa cam kết hoàn thiện upload model từ dashboard; trong phạm vi hiện tại, model được train xong rồi nạp thủ công vào thiết bị/firmware. Nếu triển khai cập nhật từ xa thật, cần thêm `model_versions` hoặc `commands`. |
| FREQ.11 | Một phần | `devices` | Có `maintenance_mode` để backend lưu cấu hình từ dashboard. Thiết bị đọc giá trị này qua pull (mục 2.2), không phải nhận đẩy. Nếu cần queue lệnh offline, xác nhận đã áp dụng, và trạng thái `pending/applied/failed`, phải thêm `commands` — xem mục 5. |
| NFREQ.5 | Một phần | `devices` | DB có document trạng thái mới nhất để backend trả nhanh cho dashboard. Việc đạt ≤ 5 giây phụ thuộc REST polling 3-5 giây hoặc SSE/WebSocket ở tầng backend. |
| NFREQ.6 | Đầy đủ | `devices/{id}/events`, `daily_stats` | Có timestamp để giữ/tự dọn dữ liệu tối thiểu 30 ngày. TTL/cron là triển khai vận hành, không cần đổi schema. |
| NFREQ.7 | Đầy đủ | Toàn bộ schema | `deviceId` là partition key trong `devices`, subcollection `events`, và key của `daily_stats`. |
| NFREQ.8 | Một phần | `devices/{id}/events` | DB hỗ trợ batch ghi lại theo `device_timestamp` và đánh dấu `synced_late`; queue 150 event/24h thuộc firmware. |
| NFREQ.10 | N/A với DB | `devices/{id}/events` chỉ ghi bằng chứng | Kiểm tra servo/cảm biến khi có điện lại là trách nhiệm firmware. DB chỉ nhận event `ERROR` nếu firmware phát hiện lỗi. |
| NFREQ.11 | N/A với DB | `devices/{id}/events` chỉ ghi bằng chứng | Phát hiện lỗi servo/cảm biến trong 5 giây thuộc thiết bị/firmware. DB chỉ lưu log/cảnh báo sau khi lỗi được báo cáo. |
| NFREQ.12 | Một phần | `devices/{id}/events` | Event có `ai_model_version`, `ai_confidence`, `waste_type` để team kỹ thuật đánh giá định kỳ; quy trình đánh giá không thuộc DB. |
| NFREQ.13 | Một phần | `devices`, `devices/{id}/events` | Có ghi version đang chạy và version tại thời điểm phát sinh event. Chưa có quản lý vòng đời version, rollback, changelog hoặc `model_versions`. |
| NFREQ.14 | Đầy đủ | `users` | `users.role` lưu metadata phân quyền; xác thực thật do Firebase Authentication xử lý. |
| NFREQ.15 | Một phần | `devices`, Firestore Security Rules | Từ khi ESP32 ghi trực tiếp Firestore, đây không còn N/A hoàn toàn: firmware phải dùng Firebase Auth device credential (custom token/anonymous, gắn `device_id`) chứ không phải admin API key, và Security Rules phải giới hạn thiết bị chỉ ghi/đọc đúng path của nó (mục 2.1, 4.1). Nếu không làm rule này, một thiết bị bị lộ credential có thể ghi đè dữ liệu thiết bị khác. |
| NFREQ.17 | Một phần / defer | `devices`, `devices/{id}/events` | Schema có chỗ ghi `ai_model_version`; cập nhật model tối thiểu bằng nạp thủ công không cần DB. Đây là hướng nhóm chọn cho prototype; cập nhật từ xa qua dashboard là tùy chọn và đã defer khỏi core schema. |
| NFREQ.18 | N/A với DB | Không áp dụng | Tài liệu interface cho dashboard/API thuộc API contract, không phải thiết kế collection. |
| NFREQ.19 | Một phần, đã nới mục tiêu | `devices` | `threshold` và `maintenance_mode` nằm trong `devices`, nhưng với cơ chế pull (piggyback + heartbeat 30–60s ở mục 2.2), thời gian áp dụng không còn đảm bảo ≤ 7 giây trong mọi trường hợp — chỉ đảm bảo nếu thiết bị đang hoạt động (có sự kiện thường xuyên) hoặc trong vòng 1 chu kỳ heartbeat. Cần sửa lại con số/diễn đạt của NFREQ.19 trong spec chính, hoặc bổ sung MQTT push (mục 2.2) nếu muốn giữ nguyên ≤ 7 giây. |

## 10. Kết luận

Thiết kế đề xuất giữ core database ở mức nhỏ: **trạng thái hiện tại (`devices`) + lịch sử sự kiện (`events`) + thống kê ngày (`daily_stats`) + phân quyền (`users`)**. Cấu trúc này đáp ứng các yêu cầu bắt buộc của đặc tả phiên bản 2.2, đồng thời để ngỏ đường nâng cấp khi hệ thống thực sự cần lịch sử cảnh báo, thống kê tháng precompute, queue lệnh hoặc quản lý phiên bản model đầy đủ.

Ưu điểm chính của hướng này là ít dữ liệu trùng lặp, ít logic đồng bộ chéo, dễ demo, dễ kiểm thử và không tự khóa nhóm vào một schema quá nặng khi requirement vẫn còn ở mức prototype.

**Cập nhật kiến trúc (phiên bản này):** nhóm đổi chiều ghi của ESP32 từ "qua backend" sang "ghi/đọc trực tiếp Firestore", còn Dashboard vẫn qua backend riêng (mục 2.1). Đánh đổi chính là: (1) validate dữ liệu và side-effect (tăng thống kê, cập nhật trạng thái đầy) chuyển từ code backend sang Firestore Security Rules + Cloud Functions; (2) cấu hình từ dashboard xuống thiết bị (FREQ.9, FREQ.11) không còn là push tức thời mà là pull theo chu kỳ (mục 2.2), kéo theo việc phải nới lại NFREQ.19 trong spec chính; (3) bắt buộc dùng Firebase Auth device credential + Security Rules theo `device_id` để không vi phạm NFREQ.15. Hướng nâng cấp lên push thật sự (MQTT) không yêu cầu đổi lại core schema.