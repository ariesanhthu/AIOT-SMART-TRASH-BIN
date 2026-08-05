# Trạng thái LED AI và nguyên tắc hoạt động offline

| Trạng thái | Hành vi |
| --- | --- |
| `LOADING` | Đèn bật/tắt mỗi 1 giây khi ESP đang khởi động, chụp, inference hoặc đồng bộ cloud |
| `READY` | Đèn sáng liên tục khi hệ thống sẵn sàng |
| `ERROR` | Đèn nhấp nháy nhanh liên tục khi UART/AI lỗi hoặc ESP trả kết quả không phân loại được (`C 0`) |
| `OFF` | Hệ thống không có điện |

- ESP32-CAM và Nano vẫn chụp, phân loại và điều khiển ngăn khi không có Wi-Fi.
- ESP luôn trả kết quả AI về Nano trước phần cloud; server lỗi không làm mất kết quả cục bộ.
- Nano gửi dữ liệu mức đầy `F` một lần, không tự gửi lại nếu mất ACK.
- ESP không tự POST lại cùng Firestore event nếu lần gửi one-shot bị lỗi.
- `C 1`, `C 2`, `C 3` lần lượt điều khiển ngăn nhựa, giấy, hữu cơ; sau khi
  transaction kết thúc, LED AI chuyển `READY`.
- `C 0` không mở ngăn và giữ LED AI ở `ERROR` cho tới lượt xử lý mới.
