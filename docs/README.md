# Kế hoạch AI cho thùng rác 3 cổng

## 1. Mục tiêu hệ thống

Hệ thống có ba đầu ra vật lý:

| Kết quả cuối | Hành động |
|---|---|
| `PAPER` | Mở cổng giấy |
| `PLASTIC` | Mở cổng nhựa |
| `OTHER` | Mở cổng còn lại |

Mô hình **chỉ được train bằng hai lớp `paper` và `plastic`**.

`OTHER` không phải lớp train thứ ba. Kết quả này được tạo bởi bộ lọc từ chối khi ảnh không đủ giống giấy hoặc nhựa.

Mục tiêu nghiệm thu:

- Độ chính xác tổng thể trên bộ kiểm thử thực tế: `>= 85%`.
- Recall của `PAPER` và `PLASTIC`: mỗi lớp `>= 85%`.
- Tỷ lệ vật thuộc `OTHER` bị mở nhầm cổng giấy/nhựa: `<= 10%`.
- Thời gian từ lúc kích hoạt camera đến khi có lệnh mở cổng: `<= 5 giây`.
- Chạy cục bộ trên ESP32-CAM.
- Không cần thẻ SD hoặc SSD để lưu mô hình.
- Khi mất Internet, AI và cơ chế mở cổng cơ bản vẫn hoạt động.

## 2. Các tài liệu thành phần

1. [01_TRAIN_MODEL.md](01_TRAIN_MODEL.md)  
   Chuẩn bị dữ liệu, train Tiny CNN, lượng tử hóa INT8 và xuất artifact.

2. [02_ESP32_INFERENCE.md](02_ESP32_INFERENCE.md)  
   Nhúng model vào firmware, chụp ảnh, tiền xử lý, suy luận và điều khiển ba cổng.

3. [03_TEST_VALIDATION.md](03_TEST_VALIDATION.md)  
   Thiết kế bộ test, hiệu chỉnh ngưỡng, kiểm tra chất lượng model và nghiệm thu trên thiết bị.

## 3. Luồng tổng thể

```text
Dữ liệu paper/plastic
        |
        v
Train Tiny CNN hai lớp
        |
        v
Hiệu chỉnh bộ lọc OTHER bằng tập validation riêng
        |
        v
Quantization INT8
        |
        v
model_int8.tflite
        |
        v
Chuyển thành model_data.cc/.h và compile vào flash ESP32
        |
        v
Camera -> preprocess -> inference -> reject/accept
        |
        +--> PAPER   -> servo giấy
        +--> PLASTIC -> servo nhựa
        +--> OTHER   -> servo còn lại
```

## 4. Hợp đồng dữ liệu giữa ba phần

### Đầu ra bắt buộc của phần train

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
└── metrics.json
```

### `labels.json`

```json
{
  "0": "paper",
  "1": "plastic"
}
```

### `thresholds.json`

```json
{
  "confidence_min": 0.75,
  "margin_min": 0.35,
  "paper_distance_max": 0.0,
  "plastic_distance_max": 0.0,
  "use_embedding_distance": true
}
```

Các giá trị trên chỉ là cấu trúc mẫu. Giá trị thật phải được chọn bằng tập validation, không được tự đặt rồi dùng trực tiếp để báo cáo test.

### Kết quả suy luận chuẩn

```c
typedef enum {
    RESULT_PAPER = 0,
    RESULT_PLASTIC = 1,
    RESULT_OTHER = 2,
    RESULT_ERROR = 3
} classification_result_t;
```

## 5. Nguyên tắc bắt buộc

- Không dùng ảnh `glass`, `metal`, `cardboard` hoặc `trash` của TrashNet để cập nhật trọng số model.
- Có thể dùng ảnh hữu cơ/vật lạ do nhóm tự chụp để hiệu chỉnh ngưỡng và kiểm thử `OTHER`.
- Tập test không được trùng vật thể, phiên chụp hoặc ảnh gần giống tập train.
- Tiền xử lý trên máy tính và ESP32 phải giống nhau.
- Chỉ chốt model sau khi bản INT8 đạt yêu cầu; không dùng kết quả model float để thay thế kết quả deploy.
- Không điều chỉnh threshold dựa trên tập test cuối.
