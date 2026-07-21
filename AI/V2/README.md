# AI V2 - TinyCNN 3 lớp cho ESP32

`AI/V2` là bản mới độc lập; không xóa hoặc ghi đè code/model cũ trong `AI/src`,
`AI/artifacts` và `AI/esp32`.

Thứ tự nhãn cố định:

```text
0 = paper
1 = plastic
2 = organic
```

## Chạy toàn bộ

Từ thư mục `AI`:

```powershell
python -m pip install -r V2/requirements.txt
python -m V2.run_pipeline --force-prepare
```

Pipeline:

1. Loại đúng 5 frame đã xác minh là trống khỏi `AI/DATASET/train/paper`.
2. Sinh 9 biến thể cho mỗi ảnh train gốc và lưu trực tiếp vào
   `AI/DATASET/train/<class>` với hậu tố `__aug_v2_XX.jpg`.
3. Tạo `V2/dataset_augmented` với split chống rò rỉ: biến thể chỉ được train
   khi ảnh nguồn thuộc train; validation và internal holdout chỉ chứa ảnh gốc.
4. Train TinyCNN `96x96x3`, 3 logits.
5. Quantize full INT8, kiểm tra operator/kích thước và sinh C array.
6. Đánh giá holdout, kiểm tra toàn bộ ảnh gốc (gồm tất cả plastic) và tạo báo cáo.

Đầu ra chính:

- `TRAINING_RESULT.md`: kết quả và giới hạn của lần train.
- `artifacts/model_float.keras`: model float.
- `artifacts/model_int8.tflite`: model full INT8 để deploy.
- `artifacts/model_data.h/.cc`: C array.
- `esp32_model/model_data.h/.cc`: bản C array dành riêng cho V2.
- `artifacts/original_predictions.csv`: dự đoán từng ảnh gốc.

Frame không có vật thể rác không được gán là `paper`, dù background là giấy.
Nếu thiết bị cần nhận biết trạng thái không có rác thì phải thu dữ liệu và thêm
lớp thứ tư `empty/background`; V2 hiện giữ đúng yêu cầu 3 lớp.
