# Model V5 trên ESP32-CAM

Firmware nhúng trực tiếp model full INT8 đã qua fine-tune cân bằng:

```text
AI/V5/artifacts_tuned2/model_int8.tflite
size    = 62,776 byte
SHA-256 = 08c17480e04782a655ad9d9241b367dc63d677f42e439601f25a9b7d4888877e
```

## Contract inference

- Input: INT8 `[1, 96, 96, 3]`, RGB, scale `1/255`, zero point `-128`.
- Output: INT8 `[1, 4]`, scale `0.041392892599105835`, zero point `14`.
- Label order: `paper=0`, `plastic=1`, `organic=2`, `other=3`.
- Mã trả về Nano: `plastic=1`, `paper=2`, `organic=3`; `other` và lỗi trả `0`.
- TFLM operators: `CONV_2D`, `MEAN`, `FULLY_CONNECTED`.

Tiền xử lý firmware không đổi: QVGA RGB565 được center-crop, resize floor
nearest-neighbor về `96x96`, chuyển RGB và quantize trực tiếp bằng
`q = pixel - 128`.

Startup self-test dùng input xác định `channel=(index*159+91)&255`. LiteRT cho
raw output `[124, -16, -52, 1]`, top `paper`, margin `123`; firmware yêu cầu
margin tối thiểu `64` để chấp nhận sai khác làm tròn nhỏ giữa kernel.

## Kết quả trước deploy

- Clean test độc lập: 394 ảnh; accuracy `80.46%`, macro-F1 `80.90%`.
- Recall INT8: paper `79.63%`, plastic `79.73%`, organic `91.89%`, other `75.36%`.
- `organic -> paper`: `5/74 = 6.76%`.
- Float/INT8 agreement: `97.46%`; toàn bộ clean deployment gate PASS.
- 8 stress profile môi trường: mean macro-F1 `59.81%`, organic recall trung
  bình `84.46%`, organic-to-paper trung bình `6.59%`.
- V4 trên cùng clean test: accuracy `37.06%`, macro-F1 `19.57%`, organic recall
  `1.35%`; đây là benchmark công bằng hơn test 25 ảnh cũ của V4.
- Clean firmware build PASS: app binary `1,415,968` byte; merged image
  `4,194,304` byte, SHA-256
  `6a250d59701db629123dc27721ae47cb998a8add114a46a6887924239462d49a`.

Stress profile là biến đổi từ test sạch, không thay thế ảnh mới chụp trực tiếp
từ ESP32-CAM. Hai profile lệch white-balance mạnh vẫn là điểm yếu; cần thu ảnh
thực địa rồi đánh giá lại trước nghiệm thu cuối.

## Xác minh và build

```powershell
python .\ESP-TRASH\verify_embedded_model.py
.\ESP-TRASH\build_firmware.ps1 -Clean
```

Script dừng nếu C array, metadata, size, SHA-256, shape hoặc quantization không
khớp model V5.
