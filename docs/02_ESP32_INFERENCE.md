# Thành phần 2 — Suy luận và điều khiển trên ESP32

> **Đã thay thế:** hợp đồng hai logits + rejection trong tài liệu này không còn
> hợp lệ. Firmware hiện dùng một output INT8 `[1,3]`; xem `AI/esp32/README.md`.

## 1. Phạm vi

Phần này chịu trách nhiệm:

- Nhúng model INT8 vào firmware.
- Khởi tạo camera.
- Chụp và kiểm tra chất lượng ảnh.
- Crop, resize và quantize ảnh đúng như lúc train.
- Chạy suy luận cục bộ.
- Chuyển hai output model thành ba kết quả `PAPER`, `PLASTIC`, `OTHER`.
- Điều khiển đúng servo.
- Ghi log độ trễ, confidence và trạng thái lỗi.

Phần này không được tự thay đổi:

- Thứ tự label.
- Image size.
- Công thức preprocessing.
- Quantization scale/zero point.
- Threshold và centroid khi chưa có phiên bản artifact mới.

---

## 2. Nền tảng triển khai

Khuyến nghị chính:

```text
ESP-IDF + esp-tflite-micro
```

Chỉ chọn Arduino/PlatformIO khi toàn bộ firmware hiện tại đang dùng Arduino và nhóm đã kiểm chứng thư viện TFLite Micro tương thích.

Không triển khai đồng thời hai framework.

### Không cần SD/SSD

Model được:

```text
model_int8.tflite
    -> model_data.cc / model_data.h
    -> compile cùng firmware
    -> lưu trong flash
```

PSRAM, nếu board có, được dùng làm RAM làm việc cho camera và tensor arena. PSRAM không phải SD/SSD.

---

## 3. Cấu trúc firmware đề xuất

```text
firmware/
├── CMakeLists.txt
├── main/
│   ├── app_main.cpp
│   ├── camera_module.cpp
│   ├── camera_module.h
│   ├── image_preprocess.cpp
│   ├── image_preprocess.h
│   ├── ai_inference.cpp
│   ├── ai_inference.h
│   ├── decision_filter.cpp
│   ├── decision_filter.h
│   ├── servo_controller.cpp
│   ├── servo_controller.h
│   ├── telemetry.cpp
│   ├── telemetry.h
│   ├── model_data.cc
│   ├── model_data.h
│   └── model_config.h
└── sdkconfig
```

### Phân tách trách nhiệm

| Module | Trách nhiệm |
|---|---|
| `camera_module` | Khởi tạo OV2640, chụp frame |
| `image_preprocess` | Crop ROI, resize, RGB, quantize |
| `ai_inference` | Tạo interpreter, tensor arena, invoke |
| `decision_filter` | Confidence, margin, distance, trả kết quả 3 cổng |
| `servo_controller` | Mở/đóng đúng servo, khóa chống mở đồng thời |
| `telemetry` | Log thời gian, nhãn, confidence, lỗi |
| `model_config.h` | Label, threshold, centroid, quantization metadata |

---

## 4. Model contract

### 4.1 Input

Firmware phải xác minh lúc boot:

```text
shape = [1, 96, 96, 3]
dtype = int8 hoặc uint8 đúng theo quantization.json
```

Nếu shape hoặc dtype không khớp:

```text
RESULT_ERROR
Không mở cổng
Báo LED lỗi
```

### 4.2 Output

Tối thiểu:

```text
2 logits/probabilities:
index 0 = paper
index 1 = plastic
```

Nếu model xuất embedding:

```text
embedding 32 chiều
```

Firmware không được đảo label theo suy đoán.

---

## 5. Luồng xử lý chính

```text
1. Cảm biến phát hiện vật.
2. Kiểm tra hệ thống đang IDLE.
3. Bật đèn chiếu sáng cố định.
4. Chờ camera ổn định.
5. Chụp 1-3 frame.
6. Loại frame quá tối, quá sáng hoặc quá mờ.
7. Crop ROI.
8. Resize về input model.
9. Chuyển pixel sang input INT8/UINT8.
10. Chạy interpreter.Invoke().
11. Dequantize output nếu cần.
12. Tính confidence, margin và khoảng cách centroid.
13. Quyết định PAPER/PLASTIC/OTHER.
14. Kiểm tra ngăn mục tiêu có đầy không.
15. Mở đúng một servo.
16. Đóng servo sau thời gian quy định.
17. Ghi telemetry.
18. Trở về IDLE.
```

---

## 6. Tiền xử lý

### 6.1 ROI

Vùng chụp phải cố định trong cấu hình:

```c
typedef struct {
    int x;
    int y;
    int width;
    int height;
} roi_t;
```

Không resize toàn bộ frame nếu phần lớn ảnh là nền.

### 6.2 Resize

Phải dùng cùng quy tắc với Python:

- Bilinear hoặc nearest neighbor phải được thống nhất.
- Đúng thứ tự RGB.
- Không vô tình dùng BGR.
- Không tự động stretch khác tỉ lệ nếu pipeline train dùng center crop.

### 6.3 Quantize pixel

Với input INT8:

```text
q = round(real_value / input_scale) + input_zero_point
q = clamp(q, -128, 127)
```

`real_value` phải đúng miền giá trị mà model dùng khi convert.

Không hard-code `/255.0` nếu model INT8 không yêu cầu cách đó.

---

## 7. Khởi tạo TensorFlow Lite Micro

### 7.1 Operator resolver

Chỉ đăng ký operator model thật sự dùng, ví dụ:

```text
CONV_2D
DEPTHWISE_CONV_2D
FULLY_CONNECTED
MEAN hoặc AVERAGE_POOL_2D
RESHAPE
SOFTMAX
RELU
QUANTIZE/DEQUANTIZE nếu model yêu cầu
```

Không dùng `AllOpsResolver` nếu làm tăng binary hoặc RAM không cần thiết.

### 7.2 Tensor arena

Quy trình:

1. Bắt đầu với kích thước có dự phòng.
2. Log số byte dùng thực tế.
3. Giảm dần sau khi model chạy ổn định.
4. Kiểm tra cả khi camera và Wi-Fi cùng hoạt động.
5. Không chỉ test inference trong chương trình tối giản.

Nếu có PSRAM:

- Framebuffer và vùng lớn có thể đặt ở PSRAM.
- Kiểm tra độ trễ thực tế vì PSRAM chậm hơn SRAM.

---

## 8. Bộ lọc ba cổng

### 8.1 Cấu hình

```c
typedef struct {
    float confidence_min;
    float margin_min;
    float paper_distance_max;
    float plastic_distance_max;
    bool use_embedding_distance;
} rejection_config_t;
```

### 8.2 Luật quyết định

```c
if (inference_error) {
    return RESULT_ERROR;
}

if (confidence < confidence_min) {
    return RESULT_OTHER;
}

if (margin < margin_min) {
    return RESULT_OTHER;
}

if (use_embedding_distance &&
    distance > distance_max_for_predicted_class) {
    return RESULT_OTHER;
}

return predicted_class == 0
    ? RESULT_PAPER
    : RESULT_PLASTIC;
```

### 8.3 Lỗi an toàn

Các trường hợp sau không được mở cổng giấy hoặc nhựa:

- Camera lỗi.
- Model invoke lỗi.
- Input/output không đúng shape.
- Ảnh trống.
- Không đủ sáng hoặc cháy sáng nghiêm trọng.
- Servo mục tiêu báo đầy.
- Confidence không hợp lệ.
- Phát hiện nhiều vật thể nhưng prototype chỉ hỗ trợ một vật.

Tùy thiết kế sản phẩm:

- Có thể đưa lỗi nhận diện sang cổng `OTHER`.
- Hoặc không mở cổng và yêu cầu người dùng thử lại.

Hai trường hợp phải được phân biệt trong telemetry:

```text
OTHER_VALID
RETRY_OR_ERROR
```

---

## 9. Điều khiển servo

### 9.1 Ánh xạ

```text
RESULT_PAPER   -> SERVO_PAPER
RESULT_PLASTIC -> SERVO_PLASTIC
RESULT_OTHER   -> SERVO_OTHER
RESULT_ERROR   -> không mở
```

### 9.2 Quy tắc an toàn

- Chỉ một servo được mở tại một thời điểm.
- Không giữ servo chịu tải lâu.
- Có trạng thái `OPENING`, `OPEN`, `CLOSING`, `IDLE`.
- Có timeout khi servo bị kẹt.
- Nguồn servo tách hoặc đủ dòng; nối chung GND với ESP32.
- Không chạy inference mới trong khi cơ cấu đang mở.
- Không mở ngăn đã đầy.

---

## 10. Chụp nhiều frame

Chỉ bật khi độ trễ vẫn dưới 5 giây.

Phương án:

```text
Frame 1 -> output 1
Frame 2 -> output 2
Frame 3 -> output 3
Final output = trung bình xác suất và embedding
```

Hoặc:

```text
Chỉ chụp lại frame thứ hai khi frame đầu có confidence gần threshold.
```

Phương án thứ hai tiết kiệm thời gian hơn.

---

## 11. Telemetry và log

Mỗi lần phân loại nên ghi:

```json
{
  "timestamp_ms": 0,
  "model_version": "tinycnn-v1-int8",
  "capture_ms": 0,
  "preprocess_ms": 0,
  "inference_ms": 0,
  "decision_ms": 0,
  "total_ms": 0,
  "paper_probability": 0.0,
  "plastic_probability": 0.0,
  "confidence": 0.0,
  "margin": 0.0,
  "distance": 0.0,
  "result": "PAPER",
  "servo": "SERVO_PAPER",
  "error_code": null
}
```

Không cần lưu ảnh trong vận hành bình thường.

Khi debug, chỉ lưu ảnh khi có chế độ kiểm thử rõ ràng và tuân thủ quy định quyền riêng tư.

---

## 12. Tối ưu bộ nhớ và thời gian

Thứ tự tối ưu:

1. Xác minh model INT8 thật sự.
2. Giảm số operator.
3. Tối ưu ROI.
4. Giảm số framebuffer.
5. Chỉ giữ một ảnh đầu vào cần thiết.
6. Giảm input từ `96x96` xuống `80x80` nếu đã đo và cần thiết.
7. Tạm hoãn Wi-Fi trong thời gian inference nếu gây thiếu RAM.
8. Chỉ giảm số layer sau khi có số liệu profiling.

Không giảm model theo cảm tính trước khi đo.

---

## 13. Kiểm tra khi boot

Firmware phải in hoặc gửi log:

```text
Model version
Model size
Input shape
Input dtype
Input scale/zero point
Output shape
Output dtype
Tensor arena allocated bytes
PSRAM detected
Free heap before/after model init
Camera init status
Servo init status
```

Nếu bất kỳ phần bắt buộc nào thất bại, hệ thống vào chế độ lỗi an toàn.

---

## 14. Tiêu chí hoàn thành phần ESP32

- [ ] Model được compile trong firmware, không đọc từ SD/SSD.
- [ ] ESP32 boot và khởi tạo model ổn định.
- [ ] Camera chụp được ảnh đúng ROI.
- [ ] Preprocessing khớp Python bằng test vector.
- [ ] Kết quả INT8 trên ESP32 khớp gần với interpreter trên máy tính.
- [ ] Có đủ ba kết quả `PAPER`, `PLASTIC`, `OTHER`.
- [ ] Không mở servo khi inference lỗi.
- [ ] Chỉ một servo mở tại một thời điểm.
- [ ] Tổng thời gian xử lý `<= 5 giây`.
- [ ] Hệ thống chạy được khi mất Internet.
- [ ] Không reset khi camera, AI và servo hoạt động liên tiếp.
- [ ] Có log model version, latency, confidence và error code.
