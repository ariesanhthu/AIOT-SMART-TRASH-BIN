# V10 INT8 inference trên server-tmp

## Kết quả

- INT8 accuracy: **98.46%** (255/259).
- Balanced/macro recall: **98.90%**.
- Macro-F1: **0.984**.
- Float accuracy: **98.46%**.
- Float/INT8 đổi top-1: **0** ảnh.
- Ảnh confidence >= 0.8: **250**, accuracy **99.60%**.

| true \ predicted | paper | plastic | organic |
|---|---:|---:|---:|
| paper | 133 | 2 | 1 |
| plastic | 1 | 90 | 0 |
| organic | 0 | 0 | 32 |

## Kiểm tra leakage/exposure

- `heldout_validation`: 18
- `heldout_test`: 18
- `exact_train_file`: 222
- `unseen`: 1

Accuracy trên subset hoàn toàn unseen: 0.00% trên 1 ảnh.

**Giới hạn diễn giải:** `dataset_augmented_v9` được tạo từ chính các ảnh
`server-tmp`. Vì vậy kết quả tổng ở trên xác nhận model và preprocessing mới xử lý
đúng tập dữ liệu đã đưa vào pipeline, nhưng không phải phép đo tổng quát hóa độc lập.
Hãy giữ một phiên chụp mới, chưa dùng làm source/augmentation, cho acceptance test cuối.
