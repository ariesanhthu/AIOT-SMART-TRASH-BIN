# Thành phần 3 — Test, kiểm tra và nghiệm thu

> **Đã thay thế một phần:** metric/rejection v1 bên dưới chỉ mang tính lịch sử.
> Kết quả ba lớp hiện hành nằm trong `AI/artifacts/metrics_int8.json` và
> `AI/artifacts/comparison.json`.

## 1. Mục tiêu

Phần test phải trả lời được:

1. Model có phân biệt giấy và nhựa tốt hơn baseline hiện tại không?
2. Model có từ chối đúng vật không phải giấy/nhựa không?
3. Model INT8 có giữ chất lượng sau quantization không?
4. Kết quả trên ESP32 có khớp kết quả trên máy tính không?
5. Toàn bộ hệ thống có mở đúng cổng trong tối đa 5 giây không?
6. Hệ thống có ổn định khi chạy lặp lại, mất mạng và điều khiển servo không?

---

## 2. Các tầng kiểm thử

```text
Tầng 1: Unit test tiền xử lý
Tầng 2: Test model float trên máy tính
Tầng 3: Test model INT8 trên máy tính
Tầng 4: So khớp Python và ESP32
Tầng 5: Test ba cổng trên prototype
Tầng 6: Test độ bền và tình huống lỗi
```

Không bỏ qua tầng giữa và chỉ demo vài ảnh thành công.

---

## 3. Bộ dữ liệu test

### 3.1 Cấu trúc

```text
data/
└── test/
    ├── paper/
    ├── plastic/
    └── other/
```

### 3.2 Số lượng

Mức tối thiểu để kiểm tra nội bộ:

| Nhóm | Số vật thể riêng biệt tối thiểu |
|---|---:|
| Paper | 30 |
| Plastic | 30 |
| Other | 30 |

Mức khuyến nghị để báo cáo:

| Nhóm | Số vật thể riêng biệt khuyến nghị |
|---|---:|
| Paper | 50 |
| Plastic | 50 |
| Other | 50-100 |

Mỗi vật có thể chụp nhiều điều kiện, nhưng khi báo cáo phải tách rõ:

```text
Số vật thể riêng biệt
Số ảnh/frame
```

Không dùng nhiều frame gần giống nhau để làm số lượng test có vẻ lớn hơn.

### 3.3 Điều kiện bắt buộc

- Chụp bằng camera của prototype hoặc camera có pipeline tương đương.
- Vật thể chưa xuất hiện trong train.
- Có ánh sáng trong nhà đúng bối cảnh triển khai.
- Có nhiều góc đặt và khoảng cách trong giới hạn vùng chờ.
- Tập `OTHER` có hữu cơ và vật lạ thực tế.
- Không dùng test để chọn threshold.

---

## 4. Tách validation và test

### Validation

Dùng để:

- Chọn `confidence_min`.
- Chọn `margin_min`.
- Chọn distance threshold.
- Chọn số frame.
- Chọn ROI.
- Chọn checkpoint.

### Test cuối

Chỉ chạy sau khi đã khóa:

- Model.
- Threshold.
- ROI.
- Firmware.
- Version artifact.

Sau khi xem test cuối, không được chỉnh threshold rồi báo lại cùng bộ test như một kết quả độc lập.

---

## 5. Unit test preprocessing

### 5.1 Golden test vector

Tạo 5-10 ảnh chuẩn.

Python xuất:

```text
golden/
├── image_01.jpg
├── image_01_preprocessed.bin
├── image_01_expected_input.json
└── ...
```

ESP32 chạy cùng ảnh hoặc buffer và ghi input tensor ra log/checksum.

Kiểm tra:

- Crop đúng tọa độ.
- Resize đúng.
- RGB không bị đảo thành BGR.
- Quantized pixel khớp.
- Sai số nằm trong giới hạn cho phép.

Nếu preprocessing không khớp, không tiếp tục đánh giá model.

---

## 6. Đánh giá model trên máy tính

### 6.1 Chỉ số bắt buộc

Cho ba kết quả vận hành:

```text
PAPER
PLASTIC
OTHER
```

Báo cáo:

- Accuracy.
- Macro precision.
- Macro recall.
- Macro F1.
- Precision/recall/F1 từng lớp.
- Confusion matrix.
- False accept rate của `OTHER`.
- Reject rate của giấy/nhựa.
- ROC hoặc bảng trade-off threshold nếu cần.

### 6.2 Confusion matrix

```text
                 Dự đoán
Thực tế       PAPER  PLASTIC  OTHER
PAPER
PLASTIC
OTHER
```

Hai lỗi cần theo dõi riêng:

```text
OTHER -> PAPER/PLASTIC
PAPER/PLASTIC -> OTHER
```

### 6.3 So sánh bắt buộc

| Phiên bản | Accuracy | Macro F1 | Recall paper | Recall plastic | Other false accept |
|---|---:|---:|---:|---:|---:|
| Baseline Logistic Regression |  |  |  |  | Không hỗ trợ đúng |
| Tiny CNN float |  |  |  |  |  |
| Tiny CNN INT8 |  |  |  |  |  |
| ESP32 thực tế |  |  |  |  |  |

---

## 7. Test quantization

Dùng cùng một tập ảnh và so sánh output float/INT8:

```text
abs(p_float - p_int8)
pred_float == pred_int8
decision_float == decision_int8
```

Ghi lại:

- Tỷ lệ đổi nhãn sau quantization.
- Tỷ lệ đổi từ ACCEPT sang OTHER.
- Tỷ lệ đổi từ OTHER sang ACCEPT.
- Mẫu sai lệch lớn nhất.

Không chỉ kiểm tra model `.tflite` có chạy được.

---

## 8. Test Python và ESP32 khớp nhau

Chọn tối thiểu:

- 10 ảnh giấy.
- 10 ảnh nhựa.
- 10 ảnh other.

Với mỗi ảnh, so sánh:

| Trường | Python INT8 | ESP32 |
|---|---:|---:|
| p_paper |  |  |
| p_plastic |  |  |
| confidence |  |  |
| margin |  |  |
| distance |  |  |
| result |  |  |

Tiêu chí:

- Kết quả cuối phải giống nhau.
- Xác suất có thể sai số nhỏ do preprocessing/rounding.
- Nếu khác nhãn, phải dừng nghiệm thu và tìm nguyên nhân.

---

## 9. Test end-to-end ba cổng

### 9.1 Một test case chuẩn

```text
ID: E2E-PAPER-001
Vật: Tờ giấy A4 đã vò nhẹ
Điều kiện: Ánh sáng trong nhà, đặt giữa ROI
Kỳ vọng AI: PAPER
Kỳ vọng servo: SERVO_PAPER
Kỳ vọng thời gian: <= 5 giây
Kỳ vọng telemetry: result=PAPER, error_code=null
```

### 9.2 Bảng test case tối thiểu

| Nhóm | Tình huống |
|---|---|
| Paper | giấy trắng, giấy in, giấy vò, giấy màu, hộp giấy mỏng trong phạm vi đã định |
| Plastic | chai trong, chai màu, ly nhựa, bao bì nhựa, nhựa bị bóp |
| Other | vỏ chuối, lá, thức ăn, lon, vật trống, tay lọt ROI |
| Camera | thiếu sáng, cháy sáng, ảnh mờ, vật ngoài ROI |
| Servo | ngăn đầy, servo kẹt, nguồn yếu |
| Network | mất Wi-Fi, reconnect |
| Flow | đưa vật liên tiếp, giữ vật quá lâu, nhiều vật cùng lúc |

Phải xác định rõ `cardboard/hộp giấy` thuộc giấy hay `OTHER` trong phạm vi sản phẩm trước khi test.

---

## 10. Test thời gian

Đo riêng:

```text
T_capture
T_preprocess
T_inference
T_decision
T_servo_command
T_total
```

Định nghĩa:

```text
T_total = từ lúc cảm biến kích hoạt đến lúc phát lệnh mở cổng
```

Báo cáo:

- Trung bình.
- Median.
- P95.
- Lớn nhất.
- Số mẫu vượt 5 giây.

Không chỉ báo cáo thời gian `Invoke()`.

---

## 11. Test bộ nhớ

Ghi lại:

- Model size trong flash.
- Firmware binary size.
- Tensor arena.
- Free internal heap trước/sau khởi tạo.
- Free PSRAM trước/sau camera.
- Heap thấp nhất trong một chu kỳ.
- Số lần reset hoặc allocation fail.

Test trong cấu hình đầy đủ:

```text
camera + AI + servo + sensor + Wi-Fi/telemetry
```

Không dùng chương trình AI rút gọn để kết luận hệ thống hoàn chỉnh đủ RAM.

---

## 12. Test độ bền

### 12.1 Chu kỳ liên tục

Mức tối thiểu:

```text
100 chu kỳ phân loại và đóng/mở
```

Khuyến nghị:

```text
300-500 chu kỳ
```

Theo dõi:

- Reset.
- Memory leak.
- Camera timeout.
- Servo kẹt.
- Kết quả drift theo nhiệt.
- Thời gian tăng dần.
- Wi-Fi làm gián đoạn inference.

### 12.2 Khởi động lại

- Mất điện đột ngột.
- Khởi động lại 20 lần.
- Mất Wi-Fi khi boot.
- Camera init thất bại một lần.
- Servo ở vị trí không chuẩn.

Hệ thống phải trở về trạng thái an toàn, không tự mở sai cổng.

---

## 13. Ngưỡng nghiệm thu

### AI

- [ ] Accuracy ba đầu ra `>= 85%`.
- [ ] Recall paper `>= 85%`.
- [ ] Recall plastic `>= 85%`.
- [ ] Other false accept rate `<= 10%`.
- [ ] Có confusion matrix và số mẫu rõ ràng.
- [ ] Tập test không trùng train.

### Thiết bị

- [ ] Tổng thời gian phản hồi `<= 5 giây`.
- [ ] Model chạy cục bộ không cần Internet.
- [ ] Không cần SD/SSD.
- [ ] Không reset trong ít nhất 100 chu kỳ.
- [ ] Không mở cổng khi model/camera lỗi.
- [ ] Mỗi kết quả mở đúng một servo.
- [ ] Ngăn đầy không được mở.
- [ ] Telemetry ghi đúng model version và kết quả.

### Tài liệu

- [ ] Có version model và firmware.
- [ ] Có dataset manifest.
- [ ] Có file threshold/centroid.
- [ ] Có metrics JSON/CSV.
- [ ] Có video demo chứa cả mẫu đúng và mẫu bị từ chối.
- [ ] Có danh sách lỗi còn tồn tại, không chỉ ghi kết quả tốt.

---

## 14. Mẫu file kết quả

### `test_results.csv`

```csv
sample_id,object_id,true_label,predicted_label,p_paper,p_plastic,confidence,margin,distance,capture_ms,preprocess_ms,inference_ms,total_ms,servo,error_code
```

### `acceptance_summary.json`

```json
{
  "model_version": "tinycnn-v1-int8",
  "firmware_version": "esp32-v1",
  "test_objects": {
    "paper": 0,
    "plastic": 0,
    "other": 0
  },
  "accuracy": 0.0,
  "macro_f1": 0.0,
  "paper_recall": 0.0,
  "plastic_recall": 0.0,
  "other_false_accept_rate": 0.0,
  "latency_ms": {
    "mean": 0.0,
    "p95": 0.0,
    "max": 0.0
  },
  "stability_cycles": 0,
  "reset_count": 0,
  "passed": false
}
```

---

## 15. Quy tắc báo cáo

Không ghi “đạt 85%” khi:

- Chỉ test trên dữ liệu TrashNet nền trắng.
- Chỉ test model float.
- Chỉ test hai lớp rồi xem `OTHER` như mặc định đúng.
- Tập test có ảnh gần trùng train.
- Số mẫu quá nhỏ nhưng không công bố.
- Đã chỉnh threshold sau khi xem test.
- Chỉ chọn các mẫu demo dễ nhận diện.

Kết luận nghiệm thu phải dựa trên model INT8 chạy trong firmware hoàn chỉnh.
