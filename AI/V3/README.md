# AI V3 - TinyCNN phân loại rác cho ESP32

V3 dùng dữ liệu tại `AI/DATASET`, tham khảo hợp đồng tiền xử lý và triển khai của V2:

```text
0 = paper
1 = plastic
2 = organic
input = RGB 96x96
```

V3 không sửa dữ liệu nguồn. Pipeline tạo split riêng trong `AI/V3/dataset_prepared`; ảnh gốc và toàn bộ biến thể augment của nó luôn đi cùng nhau để tránh rò rỉ vào test.

## Chạy toàn bộ

Từ thư mục `AI`:

```powershell
python -m pip install -r V3/requirements.txt
python -m V3.run_pipeline --force-prepare
```

Đầu ra chính:

- `EVALUATION_REPORT.md`: báo cáo huấn luyện, eval và test.
- `charts/data_distribution.png`: phân bố dữ liệu.
- `charts/confusion_matrix_int8.png`: confusion matrix trên test holdout.
- `charts/training_history.png`: learning curves.
- `artifacts/model_float.keras`: model float.
- `artifacts/model_int8.tflite`: model full INT8 để triển khai.
- `artifacts/model_data.h/.cc` và `esp32_model/model_data.h/.cc`: C array cho firmware.
- `artifacts/*.json`, `confusion_matrix_int8.csv`: kết quả máy đọc được.

