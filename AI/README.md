# AI classifier: paper / plastic / organic

Pipeline hiện tại train trực tiếp ba lớp cố định:

```text
0 = paper
1 = plastic
2 = organic
```

Không còn nhánh `OTHER`, embedding, centroid, threshold hoặc model
LogisticRegression cũ.

## Dataset

Layout chuẩn nằm trong `DATASET/{train,validation,test}/{paper,plastic,organic}`.
`DATASET/manifest.csv` ghi nguồn và SHA-256 của từng ảnh; `stats.json` ghi hash
toàn bộ manifest. Paper/plastic giữ split TrashNet chính thức. Organic được loại
trùng theo nội dung RGB đã decode trước khi lấy mẫu, trong đó mọi ảnh test trùng
với raw train đều bị loại.

Tạo lại dataset từ raw source:

```powershell
cd AI
python -m src.prepare_dataset --force
```

## Train và export toàn bộ

```powershell
cd AI
python -m pip install -r requirements.txt
python -m src.pipeline --epochs 100 --patience 18
```

Pipeline chỉ xóa các tên artefact nằm trong allowlist, sau đó thực hiện:

1. Train TinyCNN v2 bằng `tf.data` streaming.
2. Export full INT8 với representative set cân bằng ba lớp.
3. Kiểm tra dtype, shape, operator, model size, metric và float/INT8 agreement.
4. Sinh `artifacts/model_data.{h,cc}`.
5. Đồng bộ cùng C array sang `esp32/main/model/`.

Tiền xử lý dùng RGB, center-square crop và nearest-neighbor với ánh xạ integer
`src = floor(dst * crop_size / 96)`. C++ ghi trực tiếp kết quả quantize vào input
tensor; không có ảnh float/RGB trung gian trên ESP32.

## Model hiện tại

- Version: `tinycnn-v2-3class`
- Input: `int8 [1,96,96,3]`, scale `1/255`, zero point `-128`
- Output: một tensor logits `int8 [1,3]`
- Tham số: `7.947`
- TFLite: `21.992` byte, full integer
- SHA-256: `c8f97f74baec7c98ec52eaed97dc377c621471a317361787980b8e120fad02f8`
- Test INT8 accuracy: `89,06%`
- Test INT8 macro-F1: `89,17%`
- Recall paper/plastic/organic: `87,96% / 90,54% / 89,19%`
- Agreement float/INT8: `99,22%`

Chi tiết máy đọc được nằm trong `artifacts/model_metadata.json`,
`metrics_int8.json`, `comparison.json` và `quantization.json`.

## ESP32

`esp32/` là project ESP-IDF cho ESP32-CAM Ai-Thinker. Xem `esp32/README.md`.
Host test phần pointer preprocessing:

```powershell
g++ -std=c++17 -O2 -Wall -Wextra -Wpedantic -Werror `
  -I esp32/main `
  esp32/tests/image_preprocessor_host_test.cpp `
  esp32/main/image_preprocessor.cpp esp32/main/status.cpp `
  -o esp32/tests/image_preprocessor_host_test.exe
esp32/tests/image_preprocessor_host_test.exe
```

Project chưa được build/flash trên mạch trong môi trường này vì không có
ESP-IDF toolchain. Metric hiện tại cũng chỉ phản ánh hai dataset nguồn; cần test
thêm ảnh chụp thật từ đúng camera, ánh sáng và cơ cấu của prototype trước khi
nghiệm thu phần cứng.
