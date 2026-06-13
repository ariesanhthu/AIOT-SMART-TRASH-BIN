# AI module: phân loại giấy và nhựa

Module này chỉ train và test AI bằng Python, không có code ESP. Dataset được đọc trực
tiếp từ `trashnet/data/dataset-resized.zip`, chỉ dùng hai lớp `paper` và `plastic`.

## Cấu trúc

```text
src/
├─ dataset.py       # đọc TrashNet từ ZIP hoặc folder
├─ features.py      # trích xuất 27 đặc trưng nhẹ
├─ train.py         # train, đánh giá và lưu model
└─ predict.py       # phân loại một ảnh

artifacts/          # được tạo sau khi train
├─ light_trashnet_model.joblib
└─ metrics.json
```

Model là `StandardScaler + LogisticRegression`. Ảnh được resize về `64x64`, sau đó
trích xuất mean/std RGB và HSV, histogram xám, đặc trưng hình dạng và mật độ cạnh.
Lớp `plastic` của TrashNet gồm nhiều đồ nhựa, không chỉ chai nhựa, nên đây là model
baseline cho bài toán giấy/nhựa.

## Cài đặt

Từ thư mục gốc project:

```powershell
python -m pip install -r requirements.txt
```

## Train nhanh bằng sample dataset

Lệnh dưới lấy ngẫu nhiên có seed cố định 150 ảnh mỗi lớp:

```powershell
python src/train.py --max-per-class 150
```

Train toàn bộ ảnh `paper` và `plastic`:

```powershell
python src/train.py
```

Có thể đổi dataset và thư mục output:

```powershell
python src/train.py --data path/to/dataset-resized.zip --out artifacts
python src/train.py --data path/to/dataset-resized --out artifacts
```

Kết quả terminal gồm accuracy, precision, recall, F1 và confusion matrix. Chi tiết
được lưu trong `artifacts/metrics.json`.

## Test phân loại

Với một file ảnh bình thường:

```powershell
python src/predict.py --image path/to/test.jpg
```

Test trực tiếp một ảnh trong ZIP TrashNet, không cần giải nén:

```powershell
python src/predict.py `
  --image trashnet/data/dataset-resized.zip `
  --zip-member dataset-resized/plastic/plastic1.jpg
```

Output mẫu:

```text
Prediction: plastic
Confidence: 0.8123
Probabilities:
  paper: 0.1877
  plastic: 0.8123
Decision: ACCEPT
```

Mặc định prediction bị `REJECT` khi confidence nhỏ hơn `0.65`. Có thể test ngưỡng
khác bằng `--threshold`, ví dụ:

```powershell
python src/predict.py --image path/to/test.jpg --threshold 0.70
```

## Lưu ý dataset

TrashNet có 594 ảnh giấy và 482 ảnh nhựa. Dataset được chụp chủ yếu trên nền trắng,
vì vậy accuracy trên test split của TrashNet không đại diện đầy đủ cho ảnh ngoài đời.
Muốn nhận diện riêng chai nhựa, cần bổ sung ảnh chai nhựa thực tế rồi đặt vào cấu trúc:

```text
custom_dataset/
├─ paper/
└─ plastic/
```

Sau đó train bằng `python src/train.py --data custom_dataset`.
