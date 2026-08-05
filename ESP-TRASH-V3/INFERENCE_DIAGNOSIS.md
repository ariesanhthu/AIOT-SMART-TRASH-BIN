# Chẩn đoán hiện tượng luôn dự đoán organic

Ngày kiểm tra: 2026-07-18.

## Kết luận

Chưa có bằng chứng model V2 bị collapse sang `organic`.

- Model INT8 nhúng có đúng `31,584` byte và SHA-256
  `8a43d85ca2f2e38779d8e3b942e077687684d1a2175315918ea1c3569d0a7114`.
- Trên 77 ảnh gốc trong `AI/DATASET`, pipeline Python đạt `98.70%` và phân bố
  dự đoán là `paper=26`, `plastic=24`, `organic=27`.
- Mô phỏng preprocessing RGB565 đã sửa đạt `97.40%`, phân bố dự đoán là
  `paper=26`, `plastic=23`, `organic=28`. Nó không collapse về một lớp.
- Tất cả metadata hiện có trong `server-tmp/data/metadata` mang model SHA cũ
  `c8f97f74baec7c98ec52eaed97dc377c621471a317361787980b8e120fad02f8`;
  chưa có bản ghi nào chứng minh V2 đang chạy trên mạch.

Vì vậy khả năng cần kiểm tra đầu tiên là binary cũ/chưa nạp đúng. Nếu model
self-test của bản firmware mới pass mà ảnh thật vẫn thành `organic`, nguyên
nhân còn lại nằm ở domain ảnh camera thực tế (ánh sáng, màu, framing hoặc vật
khác ảnh train). Cần giữ đúng JPEG của lần dự đoán sai để đối chiếu Python và
ESP trên cùng một ảnh.

## Sai lệch preprocessing đã sửa

Bản trước mở rộng RGB565 bằng cách lặp bit thấp lên đủ dải 0–255. Ảnh train JPEG
lại được tạo từ các mức `R5 << 3`, `G6 << 2`, `B5 << 3`. Sai lệch nhỏ này làm
độ chính xác mô phỏng giảm từ `97.40%` xuống `92.21%`, chủ yếu đổi `paper` thành
`plastic`; nó không giải thích hiện tượng mọi ảnh thành `organic`.

Kết quả đầy đủ:

```text
AI/V2/artifacts/esp_preprocessing_diagnosis/summary.json
AI/V2/artifacts/esp_preprocessing_diagnosis/predictions.csv
```

## Xác minh sau khi nạp

Nạp `ESP-TRASH-V2/build/ESP-TRASH-V2.ino.merged.bin` tại địa chỉ `0x0`, sau đó mở
Serial Monitor. Khi khởi động thành công phải thấy:

```text
Model self-test passed: 31584 bytes, SHA-256=8a43d85ca2f2e38779d8e3b942e077687684d1a2175315918ea1c3569d0a7114
```

Nếu thấy `model_self_test_failed`, output kernel TFLM trên mạch không khớp
reference và pipeline sẽ dừng. Nếu self-test pass, chụp ít nhất 5 vật độc lập
mỗi lớp và giữ các JPEG upload cùng xác suất để đánh giá confusion matrix thật;
không kết luận từ một mẫu plastic duy nhất.
