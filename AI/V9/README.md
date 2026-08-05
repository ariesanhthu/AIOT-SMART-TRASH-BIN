# AI V9

Pipeline V9 dùng dataset cân bằng, augmentation được lưu thành file và một
preprocessing deterministic dùng chung cho train, validation, test, calibration
INT8 và firmware ESP-TRASH-V3.

## Dataset hiện tại

- 267 file JPEG, 89 file cho mỗi class.
- Train: 225 file, đúng 75 file/class.
- Validation: 21 file, đúng 7 ảnh gốc/class.
- Test: 21 file, đúng 7 ảnh gốc/class.
- 86 augmentation cũ và 91 augmentation V9 mới; tất cả chỉ nằm trong train.
- Không có augmentation ngẫu nhiên trong RAM. Mỗi ảnh dùng để train đều tồn tại
  trên đĩa và có một dòng trong `dataset_prepared/manifest.csv`.
- Không thêm loại ảnh/class mới, không còn exact duplicate và không có
  `source_group` đi qua nhiều split.

Tên file tuân theo mẫu:

```text
{class}_{split}_{original|existing_aug|v9_aug}_{NNN}.jpg
```

Chi tiết việc kiểm tra và phân bố nằm trong
`dataset_prepared/DISTRIBUTION_REPORT.md`.

## Preprocessing chung

Mọi split và firmware đều chạy cùng thứ tự: center-square crop, resize
nearest-neighbor xuống 96x96, mô phỏng RGB565, cân bằng trắng gray-world có giới
hạn, chuẩn hóa luminance có giới hạn, rồi rescale `[0,1]`/quantize INT8. Resize và
rescale là preprocessing bắt buộc, không phải biến thể ngẫu nhiên, nên chúng
được áp dụng cả train, validation, test và inference.

## Chạy kiểm tra và tái huấn luyện

Chạy từ thư mục `AI`:

```powershell
python -m V9.audit_dataset
python -m V9.verify_preprocessing
python -m V9.train --epochs 80 --views-per-source 1 --patience 14
python -m V9.export_int8
python -m V9.evaluate
python -m V9.embed_model
```

`views-per-source=1` là chủ ý: train đọc đúng 225 file đã materialize, không tạo
ảnh augment ẩn. Kết quả cuối nằm trong `artifacts/`; xem `TRAINING_RESULT.md`.

