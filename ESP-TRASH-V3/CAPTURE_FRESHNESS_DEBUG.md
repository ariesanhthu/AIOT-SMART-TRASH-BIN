# Debug hiện tượng lặp lại nhãn trước

## Kết luận khi đọc code

Model/TFLite không giữ nhãn của lượt trước:

- `RecognitionTelemetry` và `ClassificationResult` được tạo mới mỗi transaction.
- Preprocessor ghi đè đủ `96 × 96 × 3` byte input trước mỗi `Invoke()`.
- Postprocess đọc lại cả ba xác suất từ output hiện tại; không có smoothing,
  majority vote hoặc cache class cũ.

Điểm có khả năng gây cảm giác “đoán lại ảnh trước” nằm ở camera. Cấu hình cũ dùng
một framebuffer, `CAMERA_GRAB_WHEN_EMPTY`, và mỗi trigger chỉ gọi `Capture()` một
lần. Chính header của esp32-camera ghi rằng những frame đầu ở chế độ này có thể
cũ. `WarmUpCamera()` trước đây chỉ chạy lúc boot, không flush trước từng trigger.

Không có JPEG/log inference mạch cũ được lưu trong workspace, nên không thể chứng
minh hồi tố rằng các lần test trước thật sự dùng cùng byte ảnh. Bản debug mới tạo
đủ dấu vết để kết luận ở lần test kế tiếp.

## Pipeline mới

Sau khi ESP nhận `T 1`:

1. Gửi `A T` ngay.
2. Chờ đúng 2000 ms.
3. Khóa camera để web stream không chen vào.
4. Lấy và trả một frame đang nằm trong queue.
5. Chờ camera hoàn tất frame tiếp theo và giữ frame này.
6. Hash ảnh RGB565, preprocess, hash tensor input, inference và encode JPEG từ
   cùng một frame.

Thời điểm chụp thực tế là `2000 ms + thời gian flush/chụp frame kế tiếp`. Serial
in giá trị đo thật ở trường `trigger_to_frame`; không giả định FPS camera.

## Log cần quan sát

Mỗi lượt có hai dòng dạng:

```text
Capture #2: trigger accepted; settle=2000 ms, queued frames to discard=1
Capture #2: trigger_to_frame=...ms frame_ts=...us frame_age=...us raw_hash=........ input_hash=........ same_raw=no same_input=no
```

- `trigger_to_frame` phải lớn hơn hoặc bằng khoảng 2000 ms.
- `frame_age` phải nhỏ, tương ứng frame vừa hoàn tất chứ không phải frame giữ từ
  transaction trước.
- `raw_hash` kiểm tra toàn bộ framebuffer RGB565.
- `input_hash` kiểm tra đúng tensor mà model nhận sau preprocessing.
- `same_raw=YES` hoặc `same_input=YES` sẽ sinh thêm dòng `WARNING`.

Nếu lượt sau vẫn ra cùng nhãn nhưng hai hash khác và JPEG đúng là vật mới, vấn đề
không còn là reuse ảnh; khi đó cần đối chiếu xác suất ba class, framing/ánh sáng
và chạy model Python trên chính JPEG đó.

## Kịch bản test trên mạch

1. Nạp binary mới và mở Serial Monitor 115200 baud.
2. Đóng trang `/stream` để log thử nghiệm dễ đọc, dù mutex đã bảo vệ inference.
3. Cho giấy vào, lưu hai dòng `Capture` và dòng xác suất.
4. Chờ transaction kết thúc, lấy vật ra để cảm biến trigger rearm hoàn toàn.
5. Lặp lại lần lượt với plastic và organic, rồi đổi thứ tự class.
6. So sánh sequence, timestamp, hai hash và JPEG Cloudinary của từng lượt.

Lưu ý: code Nano hiện tại dùng cảm biến siêu âm HC-SR04 tại D9/D8 để tạo trigger,
không phải cảm biến âm thanh. LED `READY` chỉ cho biết transaction trước đã xong;
việc ảnh mới được đảm bảo bởi delay + flush nằm ở ESP sau khi nhận `T 1`.

