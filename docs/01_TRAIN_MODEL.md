# Thành phần 1 — Train và xuất model

## 1. Phạm vi

Phần này chịu trách nhiệm:

- Chuẩn bị dữ liệu `paper` và `plastic`.
- Train Tiny CNN hai lớp.
- Tạo bộ lọc từ chối để sinh kết quả `OTHER`.
- Lượng tử hóa model sang INT8.
- Xuất toàn bộ artifact cho firmware ESP32.
- Đánh giá model float và model INT8 trên máy tính.

Phần này **không** chịu trách nhiệm:

- Điều khiển servo.
- Chụp ảnh trực tiếp trong firmware.
- Đánh giá nghiệm thu cuối cùng trên ESP32.

---

## 2. Dữ liệu

### 2.1 Dữ liệu được phép dùng để train

```text
data/
├── train/
│   ├── paper/
│   └── plastic/
└── validation_known/
    ├── paper/
    └── plastic/
```

Nguồn ban đầu:

- Toàn bộ lớp `paper` của TrashNet.
- Toàn bộ lớp `plastic` của TrashNet.
- Ảnh giấy và nhựa tự chụp bằng chính camera hoặc buồng chụp của prototype.

Không giới hạn ở 150 ảnh mỗi lớp như baseline hiện tại.

### 2.2 Dữ liệu chỉ dùng để hiệu chỉnh `OTHER`

```text
data/
└── validation_other/
    └── other/
```

Ví dụ:

- Thức ăn thừa.
- Vỏ trái cây.
- Lá cây.
- Lon kim loại.
- Vật thể không phải rác.
- Ảnh trống hoặc tay người lọt vào vùng chụp.

Các ảnh này:

- Không đi qua loss.
- Không dùng để cập nhật trọng số CNN.
- Chỉ dùng để chọn threshold từ chối.

### 2.3 Chống rò rỉ dữ liệu

Khi nhóm tự chụp nhiều ảnh của cùng một vật:

- Toàn bộ ảnh của vật đó phải nằm trong cùng một split.
- Không để một góc chụp ở train và góc khác của cùng vật ở test.
- Nên chia theo `object_id` hoặc `capture_session`, không chia ngẫu nhiên từng frame.

---

## 3. Cấu trúc source cần tạo

```text
src/
├── dataset_cnn.py
├── model_tiny_cnn.py
├── train_cnn.py
├── calibrate_rejection.py
├── export_int8.py
├── evaluate_model.py
└── convert_to_c_array.py
```

### Trách nhiệm từng file

| File | Trách nhiệm |
|---|---|
| `dataset_cnn.py` | Đọc ảnh, chia split, augmentation, normalize |
| `model_tiny_cnn.py` | Khai báo Tiny CNN và embedding |
| `train_cnn.py` | Train, early stopping, lưu checkpoint |
| `calibrate_rejection.py` | Chọn confidence, margin và khoảng cách centroid |
| `export_int8.py` | Full integer quantization |
| `evaluate_model.py` | Đánh giá model float và INT8 |
| `convert_to_c_array.py` | Chuyển `.tflite` thành `.cc/.h` |

---

## 4. Kiến trúc model đề xuất

### 4.1 Input

```text
96 x 96 x 3 RGB
```

Chỉ giảm xuống `80 x 80 x 3` nếu kiểm tra thực tế cho thấy ESP32 thiếu RAM hoặc inference quá chậm.

### 4.2 Tiny CNN

```text
Input 96x96x3
Conv2D 3x3, 12 filters, stride 2
BatchNorm
ReLU6

DepthwiseConv2D 3x3, stride 2
Pointwise Conv2D, 24 filters
BatchNorm
ReLU6

DepthwiseConv2D 3x3, stride 2
Pointwise Conv2D, 32 filters
BatchNorm
ReLU6

DepthwiseConv2D 3x3, stride 2
Pointwise Conv2D, 48 filters
BatchNorm
ReLU6

DepthwiseConv2D 3x3, stride 2
Pointwise Conv2D, 64 filters
BatchNorm
ReLU6

GlobalAveragePooling
Dense 32, name="embedding"
Dense 2, name="logits"
```

Yêu cầu:

- Không dùng Lambda layer.
- Không dùng operator tùy chỉnh.
- Không dùng attention hoặc layer quá nặng.
- Ưu tiên operator được TensorFlow Lite Micro hỗ trợ.
- Theo dõi số tham số, kích thước `.tflite` và tensor arena thực tế.

---

## 5. Tiền xử lý và augmentation

### 5.1 Tiền xử lý bắt buộc

```text
1. Crop ROI trung tâm giống vùng chụp của ESP32.
2. Resize về 96x96.
3. Chuyển đúng thứ tự kênh RGB.
4. Áp dụng cùng công thức quantization/normalization với firmware.
```

Không dùng pipeline trên máy tính khác với pipeline trên ESP32.

### 5.2 Augmentation

Khuyến nghị:

- Xoay: `-15°` đến `+15°`.
- Dịch: tối đa `10%`.
- Zoom: `0.85` đến `1.15`.
- Brightness: khoảng `±20%`.
- Contrast: khoảng `±20%`.
- Blur nhẹ.
- JPEG artifacts nhẹ.
- Shadow nhẹ.
- Cutout nhỏ.

Không đổi hue quá mạnh vì màu sắc và độ trong có thể là tín hiệu phân biệt nhựa.

---

## 6. Train

### 6.1 Cấu hình ban đầu

```yaml
image_size: 96
batch_size: 16
epochs_max: 100
optimizer: AdamW
learning_rate: 0.001
weight_decay: 0.0001
label_smoothing: 0.05
early_stopping_patience: 15
seed: 42
```

### 6.2 Loss

```text
SparseCategoricalCrossentropy hoặc CategoricalCrossentropy
```

Chỉ có hai target:

```text
0 = paper
1 = plastic
```

### 6.3 Model selection

Chọn checkpoint theo:

1. Macro F1 validation cao nhất.
2. Recall hai lớp không bị lệch quá lớn.
3. Kích thước model và độ trễ phù hợp.
4. Kết quả sau quantization không giảm quá mức.

Không chọn model chỉ dựa trên train accuracy.

---

## 7. Tạo cổng `OTHER`

### 7.1 Tín hiệu quyết định

Với mỗi ảnh:

```text
p_paper
p_plastic
confidence = max(p_paper, p_plastic)
margin = abs(p_paper - p_plastic)
embedding_distance = khoảng cách tới centroid của lớp được dự đoán
```

### 7.2 Luật quyết định

```text
Nếu confidence < confidence_min:
    OTHER
Ngược lại nếu margin < margin_min:
    OTHER
Ngược lại nếu use_embedding_distance và distance > distance_max của lớp:
    OTHER
Ngược lại:
    PAPER hoặc PLASTIC
```

### 7.3 Centroid

Tính trên embedding của các mẫu train đúng:

```text
centroid_paper   = mean(embedding của paper)
centroid_plastic = mean(embedding của plastic)
```

Ngưỡng khoảng cách phải được chọn bằng:

- `validation_known`.
- `validation_other`.

Không chọn ngưỡng bằng tập test cuối.

### 7.4 Mục tiêu khi hiệu chỉnh

Ưu tiên giảm trường hợp:

```text
OTHER -> PAPER/PLASTIC
```

vì lỗi này làm hệ thống mở sai cổng tái chế.

---

## 8. Quantization INT8

### 8.1 Yêu cầu

- Full integer quantization.
- Input INT8 hoặc UINT8.
- Output INT8 hoặc UINT8.
- Representative dataset phải lấy từ ảnh thật sau đúng pipeline tiền xử lý.
- Không chấp nhận model chỉ quantize weight nhưng activation vẫn float.

### 8.2 Kiểm tra sau chuyển đổi

Bắt buộc so sánh:

| Chỉ số | Model float | Model INT8 |
|---|---:|---:|
| Accuracy |  |  |
| Macro F1 |  |  |
| Recall paper |  |  |
| Recall plastic |  |  |
| Other false accept rate |  |  |
| Kích thước model |  |  |

Nếu INT8 giảm quá nhiều:

- Kiểm tra representative dataset.
- Kiểm tra preprocessing.
- Dùng quantization-aware training.
- Giảm augmentation gây lệch.
- Không tăng model ngay trước khi xác định nguyên nhân.

---

## 9. Artifact bắt buộc

```text
artifacts/
├── model_float.keras
├── model_int8.tflite
├── model_data.cc
├── model_data.h
├── labels.json
├── thresholds.json
├── centroids.json
├── quantization.json
├── metrics_float.json
├── metrics_int8.json
├── confusion_matrix_int8.csv
└── training_config.json
```

### Nội dung `quantization.json`

```json
{
  "input_dtype": "int8",
  "input_scale": 0.0,
  "input_zero_point": 0,
  "output_dtype": "int8",
  "output_scale": 0.0,
  "output_zero_point": 0,
  "input_shape": [1, 96, 96, 3]
}
```

---

## 10. Lệnh dự kiến

Các script dưới đây cần được tạo; đây là giao diện CLI thống nhất đề xuất.

```bash
python src/train_cnn.py \
  --data data \
  --image-size 96 \
  --out artifacts \
  --seed 42
```

```bash
python src/calibrate_rejection.py \
  --model artifacts/model_float.keras \
  --known data/validation_known \
  --other data/validation_other \
  --out artifacts
```

```bash
python src/export_int8.py \
  --model artifacts/model_float.keras \
  --representative-data data/train \
  --out artifacts/model_int8.tflite
```

```bash
python src/evaluate_model.py \
  --model artifacts/model_int8.tflite \
  --data data/test \
  --thresholds artifacts/thresholds.json \
  --centroids artifacts/centroids.json
```

```bash
python src/convert_to_c_array.py \
  --model artifacts/model_int8.tflite \
  --header artifacts/model_data.h \
  --source artifacts/model_data.cc
```

---

## 11. Tiêu chí hoàn thành phần train

- [ ] Chỉ `paper` và `plastic` được dùng để cập nhật trọng số.
- [ ] Dùng toàn bộ dữ liệu có sẵn thay vì giới hạn 150 ảnh mỗi lớp.
- [ ] Có ảnh thực tế từ camera/prototype trong train hoặc validation.
- [ ] Có validation `OTHER` riêng.
- [ ] Có kết quả model float và INT8.
- [ ] Model INT8 có input/output và quantization metadata rõ ràng.
- [ ] Có `model_data.cc` và `model_data.h`.
- [ ] Có threshold và centroid đã hiệu chỉnh.
- [ ] Không dùng tập test để chọn threshold.
- [ ] Artifact có version và seed để tái lập kết quả.
