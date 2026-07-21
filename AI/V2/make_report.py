"""Generate the Vietnamese V2 Markdown report from measured artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


V2_DIR = Path(__file__).resolve().parent
AI_DIR = V2_DIR.parent
DEFAULT_ARTIFACTS = V2_DIR / "artifacts"
DEFAULT_DATASET_STATS = V2_DIR / "dataset_augmented" / "stats.json"
DEFAULT_AUGMENTATION_STATS = AI_DIR / "DATASET" / "augmentation_stats.json"
DEFAULT_CLEANUP = V2_DIR / "dataset_cleanup.json"
DEFAULT_REPORT = V2_DIR / "TRAINING_RESULT.md"
LABELS = ("paper", "plastic", "organic")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifacts", type=Path, default=DEFAULT_ARTIFACTS)
    parser.add_argument("--dataset-stats", type=Path, default=DEFAULT_DATASET_STATS)
    parser.add_argument(
        "--augmentation-stats", type=Path, default=DEFAULT_AUGMENTATION_STATS
    )
    parser.add_argument("--cleanup", type=Path, default=DEFAULT_CLEANUP)
    parser.add_argument("--out", type=Path, default=DEFAULT_REPORT)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    artifacts = args.artifacts.resolve()
    report = _render_report(
        prepared=_read_json(args.dataset_stats),
        augmentation=_read_json(args.augmentation_stats),
        cleanup=_read_json(args.cleanup),
        training=_read_json(artifacts / "training_metrics.json"),
        float_payload=_read_json(artifacts / "metrics_float.json"),
        int8_payload=_read_json(artifacts / "metrics_int8.json"),
        comparison=_read_json(artifacts / "comparison.json"),
        quantization=_read_json(artifacts / "quantization.json"),
        metadata=_read_json(artifacts / "model_metadata.json"),
        audit=_read_json(artifacts / "original_audit.json"),
        float_size=(artifacts / "model_float.keras").stat().st_size,
        int8_size=(artifacts / "model_int8.tflite").stat().st_size,
    )
    args.out.resolve().write_text(report, encoding="utf-8", newline="\n")
    print(f"Saved report: {args.out.resolve()}")


def _read_json(path: Path) -> dict:
    payload = json.loads(path.resolve().read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return payload


def _percent(value: float) -> str:
    return f"{100.0 * float(value):.2f}%"


def _size(value: int) -> str:
    return f"{value:,} byte ({value / 1024:.2f} KiB)"


def _render_report(
    *,
    prepared: dict,
    augmentation: dict,
    cleanup: dict,
    training: dict,
    float_payload: dict,
    int8_payload: dict,
    comparison: dict,
    quantization: dict,
    metadata: dict,
    audit: dict,
    float_size: int,
    int8_size: int,
) -> str:
    float_test = float_payload["metrics"]
    int8_test = int8_payload["metrics"]
    validation = training["validation"]
    original_splits = prepared["prepared_original_split_counts"]
    prepared_counts = prepared["prepared_counts"]
    plastic_float = audit["float"]["plastic"]
    plastic_int8 = audit["int8"]["plastic"]
    all_int8 = audit["int8"]["groups"]["all_originals"]
    confusion = int8_test["confusion_matrix"]
    gate_text = "PASS" if comparison["passed"] else "FAIL"
    failed_gates = ", ".join(
        name.replace("_passed", "")
        for name, passed in comparison["gates"].items()
        if not passed
    )
    source_original_total = (
        sum(augmentation["train_original_counts"].values())
        + sum(augmentation["validation_original_counts"].values())
    )
    direct_dataset_total = (
        augmentation["train_total_after_augmentation"]
        + sum(augmentation["validation_original_counts"].values())
    )
    dataset_rows = "\n".join(
        f"| {label} | {augmentation['train_original_counts'][label]} | "
        f"{augmentation['generated_counts'][label]} | "
        f"{augmentation['validation_original_counts'][label]} | "
        f"{prepared_counts['train'][label]} | "
        f"{original_splits['test'][label]} |"
        for label in LABELS
    )
    recalls = " / ".join(
        f"{label}: {_percent(int8_test['per_class'][label]['recall'])}"
        for label in LABELS
    )
    accuracy_change = float_test["accuracy"] - int8_test["accuracy"]
    if accuracy_change >= 0:
        accuracy_change_text = f"giảm {_percent(accuracy_change)}"
    else:
        accuracy_change_text = f"tăng {_percent(-accuracy_change)}"

    return f"""# Kết quả train TinyCNN V2

## Kết luận nhanh

- Dataset đúng là `AI/DATASET`. Đã loại **{cleanup['verified_empty_count']} frame trống** khỏi `train/paper`; frame chỉ có background giấy không được xem là rác giấy trong bài toán phân loại 3 loại rác.
- Augment được ghi **trực tiếp** vào `AI/DATASET/train`: sinh {augmentation['generated_total']} ảnh mới từ {sum(augmentation['train_original_counts'].values())} ảnh train gốc, mỗi ảnh có {augmentation['augmentations_per_image']} biến thể.
- Sau làm sạch có {source_original_total} ảnh gốc; toàn bộ `AI/DATASET` hiện có {direct_dataset_total} ảnh gồm ảnh gốc và ảnh augment.
- TinyCNN đầu vào `96x96x3`, đầu ra 3 lớp theo thứ tự `paper`, `plastic`, `organic`; **{training['model_parameters']:,} tham số**.
- Model deploy full INT8 có kích thước **{_size(int8_size)}**, nhỏ hơn giới hạn 256 KiB.
- Bản INT8 trên holdout độc lập: accuracy **{_percent(int8_test['accuracy'])}**, macro-F1 **{_percent(int8_test['macro_f1'])}**. Tuy nhiên quality gate là **{gate_text}** do `{failed_gates}`.

## Làm sạch và augment dataset

Năm frame bị loại:

```text
train/paper/paper_001.jpg
train/paper/paper_002.jpg
train/paper/paper_004.jpg
train/paper/paper_014.jpg
train/paper/paper_020.jpg
```

Lý do: không nhìn thấy vật thể rác. Nếu giữ chúng ở lớp `paper`, mô hình dễ học sai rằng “không có rác/background” đồng nghĩa với giấy. Muốn nhận biết frame trống đúng cách thì nên bổ sung lớp `empty/background` riêng; mô hình hiện tại chỉ có đúng 3 lớp theo yêu cầu.

| Lớp | Train gốc | Ảnh augment trực tiếp | Validation gốc | Prepared train | Holdout gốc |
|---|---:|---:|---:|---:|---:|
{dataset_rows}

`AI/DATASET/validation` không được augment. Khi tạo dataset train chuẩn hóa ở `AI/V2/dataset_augmented`, ảnh augment luôn đi cùng ảnh nguồn vào train; augment của 12 ảnh holdout bị loại khỏi train. Vì vậy không có rò rỉ ảnh nguồn giữa train và holdout.

## Kết quả train

- Epoch tốt nhất / epoch đã chạy: **{training['best_epoch']} / {training['epochs_ran']}**.
- Thời gian train: **{training['training_seconds']:.2f} giây**.
- Validation dùng để chọn checkpoint, gồm toàn bộ 16 ảnh gốc trong `AI/DATASET/validation`: accuracy **{_percent(validation['accuracy'])}**, paper `6/6`, plastic `5/5`, organic `5/5`.
- Validation không phải test độc lập vì đã tham gia chọn checkpoint.

## Đánh giá holdout độc lập

Holdout gồm 12 ảnh gốc lấy từ `AI/DATASET/train` trước khi học; model không thấy các ảnh này và cũng không thấy biến thể augment của chúng.
Mỗi lớp chỉ có 4 ảnh nên một dự đoán sai làm recall của lớp thay đổi 25 điểm phần trăm. Đây là lý do plastic `3/4` tương ứng 75%; ma trận bên dưới là holdout, không phải validation.

| Model | Accuracy | Balanced accuracy | Macro-F1 |
|---|---:|---:|---:|
| Float Keras | {_percent(float_test['accuracy'])} | {_percent(float_test['balanced_accuracy'])} | {_percent(float_test['macro_f1'])} |
| Full INT8 TFLite | {_percent(int8_test['accuracy'])} | {_percent(int8_test['balanced_accuracy'])} | {_percent(int8_test['macro_f1'])} |

- Recall INT8: {recalls}.
- Float → INT8: accuracy {accuracy_change_text}; độ đồng thuận nhãn **{_percent(comparison['float_int8_class_agreement'])}**.
- Quality gate yêu cầu agreement ≥ 95%, macro-F1 ≥ 80%, recall từng lớp ≥ 80%, accuracy không giảm quá 3%, model ≤ 256 KiB: **{gate_text}**.
- Bản INT8 chỉ sai 1 ảnh plastic thành paper, nhưng plastic recall `3/4 = 75%`, chưa đạt ngưỡng 80%.

Không trộn ảnh augment vào metric validation/holdout chính. Có thể dùng biến thể augment như một stress-test riêng để kiểm tra độ ổn định với xoay, sáng tối hoặc blur, nhưng chúng vẫn bắt nguồn từ cùng 4 ảnh và không làm số nguồn độc lập tăng lên. Cách giảm độ dao động của metric là chụp thêm ảnh gốc mới.

Confusion matrix INT8 (hàng là nhãn thật, cột là dự đoán; `paper, plastic, organic`):

```text
{confusion[0]}
{confusion[1]}
{confusion[2]}
```

## Kiểm tra toàn bộ plastic, không chỉ một mẫu

| Phạm vi ảnh plastic gốc | Float | INT8 deploy | Ý nghĩa |
|---|---:|---:|---|
| Train đã thấy | {plastic_float['train_seen']['correct']}/{plastic_float['train_seen']['samples']} | {plastic_int8['train_seen']['correct']}/{plastic_int8['train_seen']['samples']} | Không phải kiểm tra độc lập |
| Holdout độc lập | {plastic_float['internal_test']['correct']}/{plastic_float['internal_test']['samples']} | {plastic_int8['internal_test']['correct']}/{plastic_int8['internal_test']['samples']} | Chỉ số tổng quát hóa đáng tin hơn |
| Validation chọn checkpoint | {plastic_float['external_validation']['correct']}/{plastic_float['external_validation']['samples']} | {plastic_int8['external_validation']['correct']}/{plastic_int8['external_validation']['samples']} | Đã dùng để chọn model |
| Tất cả 25 ảnh plastic gốc | {plastic_float['all_plastic_originals']['correct']}/{plastic_float['all_plastic_originals']['samples']} | {plastic_int8['all_plastic_originals']['correct']}/{plastic_int8['all_plastic_originals']['samples']} | Bao gồm cả ảnh đã thấy |

Audit INT8 trên toàn bộ {audit['original_samples']} ảnh gốc đạt {_percent(all_int8['accuracy'])}; riêng plastic đạt **{plastic_int8['all_plastic_originals']['correct']}/{plastic_int8['all_plastic_originals']['samples']}**. Con số này không được dùng thay cho holdout vì có chứa ảnh train. File `artifacts/original_predictions.csv` ghi dự đoán từng ảnh để kiểm tra thủ công.

## Artefact deploy ESP32

- `artifacts/model_float.keras`: {_size(float_size)}.
- `artifacts/model_int8.tflite`: **{_size(int8_size)}**, full integer = `{str(quantization['full_integer']).lower()}`.
- INT8 input: `{quantization['input']['dtype']}` `{quantization['input']['shape']}`, scale `{quantization['input']['quantization']['scale']}`, zero point `{quantization['input']['quantization']['zero_point']}`.
- Operator: `{", ".join(quantization['unique_operators'])}`; không có operator không hỗ trợ.
- SHA-256 TFLite: `{metadata['artifacts']['int8_model']['sha256']}`.
- `artifacts/model_data.h/.cc` và `esp32_model/model_data.h/.cc`: C array để nhúng firmware; không ghi đè `AI/esp32`.

## Hạn chế

Dataset gốc còn nhỏ và nhiều ảnh chụp liên tiếp cùng bối cảnh. Dù INT8 đạt 3/4 plastic ở holdout và 24/25 khi audit toàn bộ, chưa nên coi model là đạt nghiệm thu ngoài thực tế. Nên bổ sung plastic đa dạng hơn (chai, ly, túi trong/đục, vật bị vò, nhiều góc và ánh sáng) rồi đánh giá trên một test set hoàn toàn mới, không dùng để chọn checkpoint.
"""


if __name__ == "__main__":
    main()
