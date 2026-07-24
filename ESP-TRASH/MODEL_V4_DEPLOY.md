# Model V4 tren ESP32-CAM

Firmware nhung truc tiep model full INT8:

```text
AI/V4/artifacts/model_int8.tflite
size    = 62,600 byte
SHA-256 = 64df4971dc9b208b2400b8bbc1a608a55164e3342d22ac178b4dc2bb9d0a06f2
```

## Contract inference

- Input: INT8 `[1, 96, 96, 3]`, RGB, scale `1/255`, zero point `-128`.
- Output: INT8 `[1, 4]`, scale `0.05950229614973068`, zero point `-27`.
- Label order: `paper=0`, `plastic=1`, `organic=2`, `other=3`.
- Ma tra ve Nano: `plastic=1`, `paper=2`, `organic=3`; `other` va loi tra `0`.
- Operator TFLM: `CONV_2D`, `MEAN`, `FULLY_CONNECTED`.

`other` la lop tu choi. Firmware van log ten lop va bon xac suat, nhung khong gui
lenh mo bat ky ngan nao. Su kien cloud cua ket qua nay co `waste_type=null` va
`target_compartment=null`, tranh lam sai thong ke cua ba ngan vat ly.

Firmware kiem tra size, SHA-256, schema TFLite, shape, dtype va quantization
truoc khi bat pipeline. Self-test tong hop co output LiteRT tham chieu
`[-111, 6, -119, 127]`, voi `other` la lop cao nhat.

## Preprocessing

QVGA RGB565 duoc center-crop, resize nearest-neighbor ve `96x96`, chuyen RGB va
quantize truc tiep bang `q = pixel - 128`. Contract nay khong doi so voi V3.

## Xac minh va build

```powershell
python .\ESP-TRASH\verify_embedded_model.py
.\ESP-TRASH\build_firmware.ps1 -Clean
```

Script build dung ngay neu C array, metadata hoac `model_contract.h` khong khop
model V4.
