# Báo cáo dataset V9

## Augmentation có được lưu không?

Có. Model cuối được retrain chỉ bằng file vật lý trong `train/`. Không còn
augmentation online/in-memory:

| Class | Ảnh gốc train | Augment cũ | Augment V9 mới | Tổng train |
|---|---:|---:|---:|---:|
| paper | 10 | 30 | 35 | 75 |
| plastic | 28 | 20 | 27 | 75 |
| organic | 10 | 36 | 29 | 75 |
| **Tổng** | **48** | **86** | **91** | **225** |

91 ảnh V9 mới là các thay đổi ánh sáng/gamma/contrast/màu nguồn sáng và Gaussian
sensor noise, được lưu với hậu tố `v9_aug`. Nguồn của chúng luôn là ảnh gốc trong
train; không ảnh augment nào được dùng làm nguồn để augment tiếp.

86 ảnh augment có sẵn được giữ lại sau khi truy lineage. Chúng không chỉ là ảnh
xoay: pipeline cũ còn có flip, scale, translate, thay đổi ánh sáng, blur và noise.
Vì vậy các ảnh này không bị augment lần nữa.

## Cân bằng và chia tập

| Split | paper | plastic | organic | Tổng | Loại file |
|---|---:|---:|---:|---:|---|
| Train | 75 | 75 | 75 | 225 | gốc + augment đã lưu |
| Validation | 7 | 7 | 7 | 21 | chỉ ảnh gốc |
| Test | 7 | 7 | 7 | 21 | chỉ ảnh gốc |

Trước khi thêm 91 augmentation V9, phần dữ liệu đã review là 144/21/21 file,
tương ứng 81,82%/11,93%/11,93%. Sau khi materialize augmentation chỉ cho train,
tỷ lệ file vật lý thành 84,27%/7,87%/7,87%; val/test không bị co hoặc chuyển sang
train.

Việc chọn split không dùng cách cắt ngang theo thời gian/tên file. Toàn bộ 188
file đầu vào và 91 ảnh V9 mới đã được xem; holdout được chọn theo số lượng vật
thể, kích thước, vị trí và pose sao cho có trường hợp tương ứng trong train.
12 bản sao byte-identical được bỏ, còn nguyên 176 nội dung ảnh duy nhất ban đầu.

Các kiểm tra tự động hiện tại:

- exact duplicate: 0;
- exact-hash leakage: 0;
- source-group leakage: 0;
- augmentation trong validation/test: 0;
- ảnh train tạo online: 0;
- class không cân bằng: 0;
- tên file sai chuẩn: 0;
- V9 augmentation có nguồn không phải ảnh gốc train: 0.

`manifest.csv` lưu tên/path gốc, kind, source group, visual group, hash nguồn,
hash file và kích thước cho từng ảnh. SHA-256 của manifest:
`4bc0c2f1eda9079862701fad64e18590950061fdd5787e43d870aff8a9ebb668`.

Cả 48/48 ảnh gốc trong train hiện có ít nhất một biến thể đã lưu (biến thể cũ
hoặc V9); số ảnh gốc train chưa có biến thể là 0.

Giới hạn còn lại: ảnh ESP32 hiện có vẫn thuộc cùng phiên chụp 2026-08-01. Cần
một phiên chụp độc lập sau này để đo generalization ngoài phiên chụp hiện tại.
