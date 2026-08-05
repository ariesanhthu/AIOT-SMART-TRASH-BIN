# Kết quả train và quantize V9

Model `tinycnn-v9-balanced-esp-contract` được train bằng đúng 225 JPEG đã lưu,
75 ảnh/class, không có augmentation ngẫu nhiên trong RAM. Checkpoint được chọn
theo validation; test chỉ dùng để báo cáo cuối.

| Tập | Float Keras | Full INT8 | Chênh lệch accuracy | Ảnh đổi nhãn |
|---|---:|---:|---:|---:|
| Validation (21) | 20/21 = 95,24% | 20/21 = 95,24% | 0 | 0 |
| Test (21) | 19/21 = 90,48% | 19/21 = 90,48% | 0 | 0 |

Recall test theo thứ tự `paper`, `plastic`, `organic` là
`100%`, `85,71%`, `85,71%` cho cả float và INT8. Confusion matrix test (hàng là
nhãn thật, cột là dự đoán):

```text
[[7, 0, 0],
 [0, 6, 1],
 [1, 0, 6]]
```

Sai số xác suất tuyệt đối lớn nhất giữa float và INT8 trên test là `0.05136`,
trung bình `0.00829`. File INT8 full-integer có kích thước 62.560 byte, không có
tensor float, SHA-256:
`851054bd0256a3173aa69a2dee733f059d14651271e684be06bc750cf8564253`.

Dữ liệu từng ảnh và xác suất của cả hai model nằm trong
`artifacts/evaluation_predictions.csv`; tổng hợp machine-readable nằm trong
`artifacts/evaluation_comparison.json`.
