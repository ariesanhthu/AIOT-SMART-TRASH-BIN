# Báo cáo phân tích V10 trên ảnh từ ESP32-CAM

Ngày tạo: 2026-08-14T04:50:01.269363+00:00

## Kết luận chính

V10 INT8 đạt **256/259 = 98.84%** trên ba
thư mục có ground truth `paper/plastic/organic`, macro-recall **99.14%**
và macro-F1 **0.991**. Theo nhãn thư mục có 3 lỗi, nhưng review trực
quan cho thấy một lỗi là ảnh chai nhựa rất có khả năng bị đặt nhầm trong `paper`.
Hai hard case còn lại là carton nâu bị đoán organic và nhựa trong có nhãn giấy lớn
bị đoán paper.

**Không tính accuracy cho `server-tmp/data/images`.** 285 ảnh
ở đó không có GT theo protocol của dự án. Báo cáo chỉ thống kê prediction, confidence,
drift và mức đồng thuận V9/V10; các dòng CSV đều ghi `correctness=NOT_EVALUATED`.

Ngoài ra, đây là chạy V10 **offline trên JPEG telemetry do ESP chụp**. Metadata của cả
285 ảnh vẫn là `tinycnn-v9-balanced-esp-contract`;
chưa phải bằng chứng V10 đã infer raw RGB565 trực tiếp trên board.

## 1. Protocol và kiểm kê dữ liệu

| Nhóm | Số ảnh | Có GT? | Cách dùng |
|---|---:|---|---|
| `server-tmp/paper` | 136 | Có | Accuracy/confusion/error analysis |
| `server-tmp/plastic` | 91 | Có | Accuracy/confusion/error analysis |
| `server-tmp/organic` | 32 | Có | Accuracy/confusion/error analysis |
| `server-tmp/data/images` | 285 | **Không** | Prediction/confidence/agreement only |

- Exact overlap giữa GT và no-GT: **209** ảnh.
- Chỉ có trong các thư mục GT: **50** ảnh.
- Chỉ có trong `data/images`: **76** ảnh.
- Exact duplicate nội bộ GT/no-GT: 0/
  0.

209 ảnh overlap vẫn được đánh giá từ bản nằm trong thư mục GT; bản `data/images`
không tự nhận GT. Quy tắc này tránh lỗi phương pháp từng coi prediction trên data là
đúng/sai dù chưa có nhãn.

## 2. Kết quả V10 trên ảnh có GT

| Model/chế độ | N | Accuracy | Macro recall | Min class recall |
|---|---:|---:|---:|---:|
| V9 INT8 local, crop 96x96 | 259 | 46.33% | 60.72% | 29.41% |
| V9 firmware metadata subset | 209 | 48.80% | 66.39% | 30.88% |
| V10 offline trên cùng subset | 209 | 98.56% | 98.70% | 97.56% |
| **V10 INT8 toàn bộ GT** | **259** | **98.84%** | **99.14%** | **98.53%** |

Hàng firmware V9 và V10 subset dùng cùng 209 ảnh có metadata, nhưng
không hoàn toàn cùng representation: firmware V9 infer framebuffer RGB565, V10 local
infer JPEG đã nén rồi mô phỏng RGB565 truncation.

| true \ predicted | paper | plastic | organic |
|---|---:|---:|---:|
| paper | 134 | 2 | 0 |
| plastic | 1 | 90 | 0 |
| organic | 0 | 0 | 32 |

![Confusion matrix](confusion_matrix_v10.png)

![Model comparison](model_comparison.png)

## 3. Ba trường hợp khác nhãn GT

![GT error montage](gt_error_montage.jpg)

### `paper/83d1d81b-af4e-4edd-873c-899e3ff3a910.jpg`

- Folder GT: `paper`; V10: `plastic`; paper=0.098, plastic=0.898, organic=0.008.
- Exposure: `heldout_validation`; nearest train: `train/plastic/augv9_plastic_train_original_005.jpg` (plastic, cosine 0.0408).
- Phân tích: Cần review thủ công thêm.
### `paper/ae41156a-aa81-46b1-97d7-fb8f22cfdad6.jpg`

- Folder GT: `paper`; V10: `plastic`; paper=0.270, plastic=0.727, organic=0.004.
- Exposure: `unseen`; nearest train: `train/plastic/augv9_plastic_train_original_005.jpg` (plastic, cosine 0.0551).
- Phân tích: Ảnh cho thấy chai/bao bì nhựa trong suốt. File đã bị audit loại khỏi dataset vì nghi gán nhãn paper sai; dự đoán plastic 98.44% phù hợp review trực quan.
### `plastic/2d923f14-4cc7-4855-b05d-712c80001af2.jpg`

- Folder GT: `plastic`; V10: `paper`; paper=0.848, plastic=0.109, organic=0.043.
- Exposure: `heldout_test`; nearest train: `train/paper/augv9_paper_train_original_092.jpg` (paper, cosine 0.1159).
- Phân tích: Cần review thủ công thêm.


Nếu sửa riêng ảnh nghi gán nhãn sai từ paper sang plastic, V10 sẽ đạt 257/259 =
99.23%. Con số này chỉ là sensitivity analysis, **không thay thế metric chính thức**
cho đến khi người phụ trách dữ liệu xác nhận nhãn.

## 4. Leakage và độ tin cậy của phép đo

GT exposure theo manifest V10:

- `exact_train_file`: **222**
- `heldout_validation`: **18**
- `heldout_test`: **18**
- `unseen`: **1**

222/259 ảnh GT là exact train file. Chỉ có một ảnh `unseen`, và đó chính là ảnh nghi
gán nhãn paper sai. Vì vậy 98.84% chủ yếu xác nhận model đã fit dữ liệu đã đưa vào
pipeline và preprocessing chạy nhất quán; nó **không đo generalization deployment**.

Train có 740 file: originals mỗi lớp
{'paper': 133, 'plastic': 62, 'organic': 30}, còn lại là augmentation đã lưu.
Số source-group train theo lớp là {'paper': 138, 'plastic': 69, 'organic': 31}.
Source-group hiện tách theo capture/file lineage, chưa bảo đảm tách theo vật thể vật lý
hoặc phiên chụp độc lập.

![Training distribution](training_distribution.png)

## 5. Confidence, calibration và reject threshold

- Mean confidence ảnh đúng: 0.990.
- Mean confidence ảnh khác GT: 0.824.
- NLL: 0.0330; Brier:
  0.0184; ECE 10-bin: 0.0150.
- Threshold 0.8 nhận 256/259 ảnh
  (98.84%) với accuracy 99.22%.

ECE và selective accuracy cũng bị lạc quan do train overlap. Không được chọn threshold
production từ tập này; cần calibration set độc lập. Ảnh nghi nhãn sai còn cho thấy
"high-confidence error" có thể là lỗi annotation chứ không phải lỗi model.

![Confidence analysis](confidence_analysis.png)

![Selective accuracy](selective_accuracy.png)

## 6. Phân tích 285 ảnh no-GT trong `data/images`

### Prediction distribution — không phải accuracy

| Nguồn prediction | paper | plastic | organic |
|---|---:|---:|---:|
| Firmware V9 metadata | 74 | 123 | 88 |
| Offline V10 | 168 | 66 | 51 |

V9 và V10 đồng ý top-1 trên **138/285 =
48.42%**. Không thể nói model nào đúng trên các ảnh
không có nhãn. Chuyển dịch lớn nhất là V9 plastic -> V10 paper (83) và
V9 organic -> V10 paper (35), phù hợp việc V10 đã được train lại bằng
nhiều ảnh carton/giấy trong chính miền ESP.

![No-GT prediction distribution](no_gt_prediction_distribution.png)

![V9 to V10 transition](no_gt_v9_v10_transition.png)

Confidence V10 trên no-GT: mean 0.950, median
0.996, minimum 0.406;
10 ảnh <0.6, 28 ảnh <0.8 và
245 ảnh >=0.9. Confidence cao không chứng minh đúng khi
không có GT.

10 prediction no-GT confidence thấp nhất:

| File | V10 prediction | V10 confidence | V9 prediction |
|---|---|---:|---|
| `c20f0c47-a206-428d-961b-134da2209a40.jpg` | organic | 0.406 | organic |
| `ef79d1dc-5abc-4f95-985c-83ad2f478fef.jpg` | plastic | 0.445 | paper |
| `a2689a4d-962d-42b5-9670-55d0ba320460.jpg` | paper | 0.496 | plastic |
| `b5ae2be5-a612-46c6-8863-e476ab2ed08f.jpg` | paper | 0.496 | plastic |
| `4c666949-5100-4daa-b2a9-1dc741c1a1ca.jpg` | organic | 0.508 | paper |
| `20e643a9-367f-496d-8c05-098954b6ceb0.jpg` | plastic | 0.527 | plastic |
| `1f6f04d8-d139-4a20-be44-b7c0857f8013.jpg` | plastic | 0.539 | plastic |
| `198617d1-c835-4496-b99b-ec2f68ad41e2.jpg` | organic | 0.543 | organic |
| `955d12ce-9ceb-4d28-8824-4d22efeeb5c6.jpg` | organic | 0.574 | organic |
| `fd19dcec-4d51-4732-8c57-0a45d5ec2905.jpg` | plastic | 0.586 | plastic |

![No-GT low confidence](no_gt_low_confidence_montage.jpg)

10 bất đồng V9/V10 có confidence V10 cao nhất:

| File | V9 | V10 | V10 confidence |
|---|---|---|---:|
| `075b4c96-0e45-4fc1-85e8-b45f01322bc8.jpg` | paper | organic | 0.996 |
| `08957b4d-b996-4f82-a385-44b1c59b5c64.jpg` | organic | paper | 0.996 |
| `09be46bc-6941-4ba6-b61f-c53fb58d7be6.jpg` | plastic | paper | 0.996 |
| `0dc78700-cae4-49d7-af86-780d18f797df.jpg` | plastic | paper | 0.996 |
| `0f733a16-8745-4c19-9904-f0b5c31b91fa.jpg` | organic | paper | 0.996 |
| `118e97e6-00c8-43bd-865b-921efa320cda.jpg` | paper | organic | 0.996 |
| `12a0b7d0-7292-4b7d-bca0-ebefa53d7067.jpg` | plastic | paper | 0.996 |
| `1333e479-d829-4b34-9126-81d276a58278.jpg` | organic | paper | 0.996 |
| `14645458-07eb-40f1-a49a-da76033c4dcb.jpg` | plastic | paper | 0.996 |
| `146b8896-93fd-40bf-8163-c9112058ded4.jpg` | organic | paper | 0.996 |

![No-GT disagreements](no_gt_v9_v10_disagreement_montage.jpg)

Review montage cho thấy nhiều frame no-GT là **thùng trống, tay người, vật chỉ lọt
một phần khung hoặc vật trắng/trong suốt rất ít texture**. Vì classifier chỉ có ba
lớp bắt buộc, nó vẫn phải trả `paper/plastic/organic` ngay cả khi không có vật hợp lệ.
Đáng chú ý, montage bất đồng có cả frame chủ yếu là bàn tay nhưng V10 vẫn trả `paper`
với confidence gần 1.0. Đây không được tính là prediction sai do chưa có GT, nhưng là
bằng chứng rõ rằng confidence hiện tại **không phải object-presence score** và model
thiếu lớp/gate `empty-background-invalid`.

Quan sát định tính cũng cho thấy nhiều chuyển dịch V9 -> V10 confidence cao là carton
hoặc giấy vò được V10 đưa về paper, còn một số chai trong được đưa về plastic. Pattern
này hợp lý về mặt thị giác nhưng vẫn cần gán nhãn để xác nhận. Trong 285 ảnh no-GT có
172 exact train file, 18 validation, 18 test và 77 unseen theo manifest; vì vậy ngay cả
phân bố confidence no-GT cũng chịu ảnh hưởng mạnh của dữ liệu đã thấy.

## 7. Embedding, coverage và giới hạn mô hình

Embedding dùng vector 96D sau global-average-pooling và 225
train-original reference. Có 26 ảnh GT ngoài
ngưỡng nearest-neighbor 95% của lớp thật, và 61
ảnh no-GT ngoài ngưỡng lớp dự đoán. Đây chỉ là diagnostic: exact train overlap tạo rất
nhiều khoảng cách bằng 0 và làm threshold thiên lệch.

![Embedding PCA](embedding_pca.png)

V10 vẫn là whole-image classifier, không detect/segment vật thể. Nó có thể học nền,
màu, silhouette và nhãn in. Coverage organic hiện thiên về cucumber/lime/chili/small
fruit; chưa chứng minh tốt trên thức ăn thừa, vỏ bẩn, rau lá, đồ chín hoặc vật liệu hỗn
hợp. Nhựa trong có nhãn giấy và carton nâu là hai failure mode đã quan sát trực tiếp.

## 8. Kết luận kỹ thuật và hành động ưu tiên

1. **Giữ một phiên ESP mới hoàn toàn độc lập**: không đưa ảnh, frame gần kề hoặc
   augmentation lineage vào train; split theo vật thể vật lý + ngày chụp.
2. **Xác nhận lại nhãn** `paper/ae41156a-...jpg`. Nếu là chai nhựa, sửa GT và ghi
   audit trail; không âm thầm đổi để tăng metric.
3. **Gán nhãn 76 ảnh chỉ có trong `data/images`** trước khi dùng chúng để so accuracy.
   `no_gt_predictions.csv` là queue review, không phải bảng lỗi.
4. Bổ sung hard cases: carton nâu/ướt/bẩn; nhựa trong có label; bao bì composite;
   vật nhỏ/lệch mép; nền và ánh sáng mới; organic ngoài rau quả xanh.
5. Thêm trạng thái `unknown/retry`, nhưng chỉ calibrate threshold trên validation độc
   lập. Các ảnh <0.6 và bất đồng V9/V10 là ưu tiên review/active learning tốt.
6. Thêm **object-presence gate hoặc lớp `empty/background/invalid`** và hard negative
   gồm thùng trống, tay người, ảnh che camera, vật ngoài khung. Threshold softmax của
   classifier ba lớp không giải quyết được trường hợp không có vật.
7. Flash V10 lên board và thu phiên mới có metadata hash
   `7568c7641a4e2bb40828dd89321e0b3c82108e27d2e8e15cdce8cc36bd33f1b3`. Đối chiếu raw-RGB565 firmware với offline JPEG
   để đo riêng sai khác codec/preprocessing.
8. Báo cáo production nên dùng macro recall, per-class recall, confusion, calibration
   và session-level bootstrap; không chỉ dùng accuracy file-level.

## 9. Artifact

- `gt_predictions.csv`: toàn bộ ảnh có GT và prediction V9/V10.
- `gt_misclassified.csv`: ba trường hợp khác folder label.
- `no_gt_predictions.csv`: prediction no-GT, mọi dòng ghi `NOT_EVALUATED`.
- `no_gt_low_confidence.csv`: queue review theo confidence.
- `no_gt_v9_v10_disagreements.csv`: queue review theo model disagreement.
- `summary.json`: toàn bộ số liệu máy đọc được.
- Các PNG/JPG: confusion, transition, confidence, threshold, PCA và montage.

## 10. Giới hạn diễn giải

- Folder name được coi là GT theo yêu cầu, nhưng báo cáo không tự xác minh mọi nhãn.
- V10 chạy local trên JPEG nén, không phải framebuffer RGB565 gốc.
- No-GT tuyệt đối không có accuracy/error rate trong báo cáo.
- PCA là chiếu 2D để quan sát, không phải bằng chứng phân lớp.
- Kết quả GT bị train exposure rất lớn; không dùng 98.84% làm deployment claim.
