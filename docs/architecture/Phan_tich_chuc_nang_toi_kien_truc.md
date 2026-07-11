# BÁO CÁO PHÂN TÍCH TÁC ĐỘNG CỦA YÊU CẦU (FREQ/NFREQ) ĐẾN KIẾN TRÚC DATABASE

**Hệ thống:** Thùng rác thông minh hỗ trợ giáo dục phân loại rác — Nhóm 2

**Phạm vi phụ trách:** Sub-Goal 3 — Dashboard, thông báo, thống kê (UC 2.5.1 – 2.5.4)

**Người thực hiện:** Đặng Nguyễn Thành Hiếu (23127364)

**Mục đích:** Xác định requirement nào thực sự ràng buộc kiến trúc database, tránh thiết kế theo cảm tính.

---


## 1. Mục tiêu 1 & 2 — Tác động gián tiếp (nguồn dữ liệu, không ràng buộc DB trực tiếp)

Các FREQ của Mục tiêu 1 (phát hiện rác, chụp ảnh, AI phân loại — FREQ.1–5) và Mục tiêu 2 (điều khiển servo, đóng/mở nắp, LED cảnh báo, phát hiện đầy — FREQ.1–6) đều xử lý **hoàn toàn cục bộ trên firmware/mạch chính**, không có yêu cầu nào nói tới việc lưu trữ hay truy vấn từ server. Do đó nhóm này **không trực tiếp ràng buộc kiến trúc DB**.

Tuy nhiên có 2 điểm cần ghi nhận vì chúng là **nguồn gốc dữ liệu** sẽ đổ vào DB ở Mục tiêu 3:

| Nguồn | Requirement | Dữ liệu sinh ra | Nơi lưu ở Mục tiêu 3 |
|---|---|---|---|
| Mục tiêu 1 | FREQ.3 (AI phân loại: hữu cơ/giấy/nhựa) | Kết quả phân loại (`waste_type`) | field trong `events` |
| Mục tiêu 2 | FREQ.5 (phát hiện đầy bằng cảm biến siêu âm) | Trạng thái đầy từng ngăn | field trong `devices.compartments` |

→ Kết luận: Mục tiêu 1, 2 quyết định **field nào cần có** trong schema, nhưng không quyết định **kiến trúc/loại DB**.

## 3. Mục tiêu 3 — Tác động trực tiếp đến kiến trúc DB

### 3.1 Nhóm Ghi nhận sự kiện (Event ingestion)

| Requirement | Nội dung | Ràng buộc lên DB |
|---|---|---|
| FREQ.3, FREQ.4 | Ghi mỗi sự kiện phân loại lên server, gồm loại rác, mã thùng, thời gian | Cần collection **insert-only** (không update), tối thiểu 3 field: `waste_type`, `device_id`, `timestamp` |
| NFREQ.8 | Mất mạng: firmware queue tối đa 150 sự kiện/24h trong RAM, khi có mạng lại đồng bộ **theo đúng thứ tự thời gian** | Server phải hỗ trợ **ghi hàng loạt (batch insert)**, và phải dùng **timestamp do firmware gán** thay vì server-side timestamp — nếu không, thứ tự sự kiện bị sai khi đồng bộ trễ |
| FREQ.2 | Lưu thông báo trạng thái cục bộ khi mất mạng, đồng bộ khi có mạng | Cần field đánh dấu sự kiện đồng bộ trễ (vd `synced_late: boolean`) để phục vụ audit/debug |

### 3.2 Nhóm Trạng thái thời gian thực (Real-time state)

| Requirement | Nội dung | Ràng buộc lên DB |
|---|---|---|
| NFREQ.5 | Dashboard cập nhật ≤ 5 giây | Bắt buộc cơ chế **real-time push** (listener), không chấp nhận polling định kỳ chậm |
| FREQ.6 | Hiển thị mức đầy, trạng thái kết nối, thống kê trên dashboard | Cần document **trạng thái hiện tại** riêng biệt, được overwrite liên tục — tách khỏi lịch sử thô |
| FREQ.7 | Hiển thị trạng thái ngoại tuyến kèm dữ liệu cập nhật lần cuối | Bắt buộc field `last_seen_at`; logic "online/offline" phải tự tính ở tầng ứng dụng (DB không tự phát hiện mất kết nối) |

### 3.3 Nhóm Thống kê (Aggregation)

| Requirement | Nội dung | Ràng buộc lên DB |
|---|---|---|
| FREQ.5 | Tổng hợp thống kê theo loại rác, loại thùng, **theo ngày và theo tháng** | Cần quyết định: (a) precompute cả 2 mức ngày/tháng, hoặc (b) chỉ precompute theo ngày rồi tổng hợp tháng lúc truy vấn |
| FREQ.8 | Lọc thống kê theo thùng, loại rác, khoảng thời gian | Cần index hỗ trợ range-query theo thời gian kết hợp lọc theo thiết bị/loại rác |
| NFREQ.6 | Lưu tối thiểu 30 ngày; cục bộ chỉ giữ 24 giờ khi mất mạng | Cần xác định rõ chính sách retention ở tầng server (giữ vĩnh viễn hay tự xoá sau X ngày) |

### 3.4 Nhóm Cảnh báo (Alerts)

| Requirement | Nội dung | Ràng buộc lên DB |
|---|---|---|
| FREQ.1 | Tạo thông báo đầy: mã thiết bị, tên ngăn, % đầy, thời gian; hiển thị dashboard | Cần entity riêng có **vòng đời trạng thái** (active → resolved), tách khỏi log sự kiện thô để truy vấn "cảnh báo đang active" nhanh |

### 3.5 Nhóm Cấu hình & Quản lý thiết bị từ xa

| Requirement | Nội dung | Ràng buộc lên DB |
|---|---|---|
| FREQ.9 | Cấu hình ngưỡng đầy riêng từng ngăn, cập nhật về mạch | Field `threshold` theo từng ngăn; cần cơ chế đẩy thay đổi này xuống firmware |
| FREQ.11 | Bật/tắt chế độ bảo trì từ dashboard | Field `maintenance_mode`; firmware phải nhận được thay đổi gần như ngay lập tức |
| NFREQ.19 | Lệnh cấu hình áp dụng ≤ 7 giây nếu thiết bị online | **Ràng buộc hai chiều**: không chỉ dashboard cần real-time, firmware cũng phải lắng nghe real-time (không thể chỉ poll định kỳ chậm) |
| FREQ.10 | Upload model AI mới từ dashboard; server lưu, đẩy xuống khi online; firmware xác nhận version | Cần cơ chế lưu và theo dõi **version của model** — thiết kế trước đó **chưa có chỗ cho việc này** |

### 3.6 Nhóm Bảo mật & Khả năng mở rộng

| Requirement | Nội dung | Ràng buộc lên DB |
|---|---|---|
| NFREQ.14 | Yêu cầu xác thực cho tính năng quản trị | Cần entity người dùng với phân quyền (role) |
| NFREQ.15 | Không lưu thông tin xác thực trong mã nguồn firmware | Không ảnh hưởng schema, nhưng ảnh hưởng cơ chế cấp quyền ghi cho thiết bị (device-specific credential, không phải admin credential) |
| NFREQ.7 | Hỗ trợ tối thiểu 10 thiết bị đồng thời, không đổi kiến trúc | Bắt buộc `device_id` phải là khoá phân vùng (partition key) xuyên suốt toàn bộ schema ngay từ đầu |


