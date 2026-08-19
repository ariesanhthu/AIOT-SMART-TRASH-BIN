# Dataset augmented V9

Dataset này được tạo sau khi review trực quan toàn bộ ảnh nguồn. Split không cắt ngẫu nhiên theo tên file. Ảnh validation/test chỉ là ảnh gốc; mọi augmentation cùng lineage chỉ nằm trong train.

## Phân bố

| Split | paper | plastic | organic | Tổng |
|---|---:|---:|---:|---:|
| train | 150 | 150 | 150 | 450 |
| validation | 6 | 6 | 6 | 18 |
| test | 6 | 6 | 6 | 18 |

## Loại file

| Split | Gốc | Augment có sẵn | Augment mới |
|---|---:|---:|---:|
| train | 177 | 45 | 228 |
| validation | 18 | 0 | 0 |
| test | 18 | 0 | 0 |

## Coverage ảnh gốc theo nhóm vật thể

### paper

| Nhóm | train | validation | test |
|---|---:|---:|---:|
| paper_cardboard_or_box | 56 | 3 | 3 |
| paper_crumpled_or_sheet | 67 | 3 | 3 |

### plastic

| Nhóm | train | validation | test |
|---|---:|---:|---:|
| plastic_bottle | 29 | 4 | 4 |
| plastic_film_or_bag | 5 | 2 | 2 |

### organic

| Nhóm | train | validation | test |
|---|---:|---:|---:|
| chili | 2 | 0 | 0 |
| cucumber | 10 | 3 | 3 |
| lime | 7 | 3 | 3 |
| small_fruit | 1 | 0 | 0 |

## Augmentation

Ảnh mới được lưu vật lý ở `train/` với 7 recipe luân phiên: màu/ánh sáng kiểu V9, xoay + zoom/resize, low-light + blur, warm/bright, cool cast, sensor noise và soft-focus + scale. Kích thước đầu ra giữ 320×240.

## Audit

- Exact duplicate output: 0.
- Source-group leakage: 0.
- Augmentation trong validation/test: 0.
- Mỗi class trong train có đúng 150 ảnh; validation/test có 6 ảnh gốc/class.
- Các nhóm phổ biến xuất hiện ở cả ba split: lime/cucumber, bottle/film, cardboard/crumpled-paper.
- Loại 1 ảnh `paper/ae41156a-aa81-46b1-97d7-fb8f22cfdad6.jpg` vì review cho thấy nhiều khả năng là chai nhựa trong suốt bị gán nhãn paper.

## Giới hạn

Ớt chỉ có 2 ảnh gốc và nhóm quả nhỏ chỉ có 1 ảnh gốc, nên không thể phủ độc lập train/validation/test. Các ảnh hiếm này được giữ ở train; cần chụp thêm ảnh gốc trước khi đánh giá riêng các nhóm đó. Validation/test hiện cũng còn nhỏ (6 ảnh/class).

`manifest.csv` lưu lineage, nhóm vật thể, tên/path gốc, recipe, kích thước và SHA-256 của từng file. `stats.json` lưu toàn bộ phân bố và kết quả audit.
