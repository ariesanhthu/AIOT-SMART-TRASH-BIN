# Kết quả train TinyCNN V2

## Kết luận nhanh

- Dataset đúng là `AI/DATASET`. Đã loại **5 frame trống** khỏi `train/paper`; frame chỉ có background giấy không được xem là rác giấy trong bài toán phân loại 3 loại rác.
- Augment được ghi **trực tiếp** vào `AI/DATASET/train`: sinh 549 ảnh mới từ 61 ảnh train gốc, mỗi ảnh có 9 biến thể.
- Sau làm sạch có 77 ảnh gốc; toàn bộ `AI/DATASET` hiện có 626 ảnh gồm ảnh gốc và ảnh augment.
- TinyCNN đầu vào `96x96x3`, đầu ra 3 lớp theo thứ tự `paper`, `plastic`, `organic`; **24,379 tham số**.
- Model deploy full INT8 có kích thước **31,584 byte (30.84 KiB)**, nhỏ hơn giới hạn 256 KiB.
- Bản INT8 trên holdout độc lập: accuracy **91.67%**, macro-F1 **91.53%**. Tuy nhiên quality gate là **FAIL** do `agreement, class_recall`.

## Làm sạch và augment dataset

Năm frame bị loại:

```text
train/paper/paper_001.jpg
train/paper/paper_002.jpg
train/paper/paper_004.jpg
train/paper/paper_014.jpg
train/paper/paper_020.jpg
```

Lý do: không nhìn thấy vật thể rác. Nếu giữ chúng ở lớp `paper`, mô hình dễ học sai rằng “không có rác/background” đồng nghĩa với giấy. Muốn nhận biết frame trống đúng cách thì nên bổ sung lớp `empty/background` riêng; mô hình hiện tại chỉ có đúng 3 lớp theo yêu cầu.

| Lớp | Train gốc | Ảnh augment trực tiếp | Validation gốc | Prepared train | Holdout gốc |
|---|---:|---:|---:|---:|---:|
| paper | 19 | 171 | 6 | 150 | 4 |
| plastic | 20 | 180 | 5 | 160 | 4 |
| organic | 22 | 198 | 5 | 180 | 4 |

`AI/DATASET/validation` không được augment. Khi tạo dataset train chuẩn hóa ở `AI/V2/dataset_augmented`, ảnh augment luôn đi cùng ảnh nguồn vào train; augment của 12 ảnh holdout bị loại khỏi train. Vì vậy không có rò rỉ ảnh nguồn giữa train và holdout.

## Kết quả train

- Epoch tốt nhất / epoch đã chạy: **23 / 48**.
- Thời gian train: **59.79 giây**.
- Validation dùng để chọn checkpoint, gồm toàn bộ 16 ảnh gốc trong `AI/DATASET/validation`: accuracy **100.00%**, paper `6/6`, plastic `5/5`, organic `5/5`.
- Validation không phải test độc lập vì đã tham gia chọn checkpoint.

## Đánh giá holdout độc lập

Holdout gồm 12 ảnh gốc lấy từ `AI/DATASET/train` trước khi học; model không thấy các ảnh này và cũng không thấy biến thể augment của chúng.

| Model | Accuracy | Balanced accuracy | Macro-F1 |
|---|---:|---:|---:|
| Float Keras | 75.00% | 75.00% | 70.91% |
| Full INT8 TFLite | 91.67% | 91.67% | 91.53% |

- Recall INT8: paper: 100.00% / plastic: 75.00% / organic: 100.00%.
- Float → INT8: accuracy tăng 16.67%; độ đồng thuận nhãn **83.33%**.
- Quality gate yêu cầu agreement ≥ 95%, macro-F1 ≥ 80%, recall từng lớp ≥ 80%, accuracy không giảm quá 3%, model ≤ 256 KiB: **FAIL**.
- Bản INT8 chỉ sai 1 ảnh plastic thành paper, nhưng plastic recall `3/4 = 75%`, chưa đạt ngưỡng 80%.

Confusion matrix INT8 (hàng là nhãn thật, cột là dự đoán; `paper, plastic, organic`):

```text
[4, 0, 0]
[1, 3, 0]
[0, 0, 4]
```

## Kiểm tra toàn bộ plastic, không chỉ một mẫu

| Phạm vi ảnh plastic gốc | Float | INT8 deploy | Ý nghĩa |
|---|---:|---:|---|
| Train đã thấy | 12/16 | 16/16 | Không phải kiểm tra độc lập |
| Holdout độc lập | 1/4 | 3/4 | Chỉ số tổng quát hóa đáng tin hơn |
| Validation chọn checkpoint | 5/5 | 5/5 | Đã dùng để chọn model |
| Tất cả 25 ảnh plastic gốc | 18/25 | 24/25 | Bao gồm cả ảnh đã thấy |

Audit INT8 trên toàn bộ 77 ảnh gốc đạt 98.70%; riêng plastic đạt **24/25**. Con số này không được dùng thay cho holdout vì có chứa ảnh train. File `artifacts/original_predictions.csv` ghi dự đoán từng ảnh để kiểm tra thủ công.

## Artefact deploy ESP32

- `artifacts/model_float.keras`: 159,495 byte (155.76 KiB).
- `artifacts/model_int8.tflite`: **31,584 byte (30.84 KiB)**, full integer = `true`.
- INT8 input: `int8` `[1, 96, 96, 3]`, scale `0.003921568859368563`, zero point `-128`.
- Operator: `CONV_2D, FULLY_CONNECTED, MEAN`; không có operator không hỗ trợ.
- SHA-256 TFLite: `8a43d85ca2f2e38779d8e3b942e077687684d1a2175315918ea1c3569d0a7114`.
- `artifacts/model_data.h/.cc` và `esp32_model/model_data.h/.cc`: C array để nhúng firmware; không ghi đè `AI/esp32`.

## Hạn chế

Dataset gốc còn nhỏ và nhiều ảnh chụp liên tiếp cùng bối cảnh. Dù INT8 đạt 3/4 plastic ở holdout và 24/25 khi audit toàn bộ, chưa nên coi model là đạt nghiệm thu ngoài thực tế. Nên bổ sung plastic đa dạng hơn (chai, ly, túi trong/đục, vật bị vò, nhiều góc và ánh sáng) rồi đánh giá trên một test set hoàn toàn mới, không dùng để chọn checkpoint.
