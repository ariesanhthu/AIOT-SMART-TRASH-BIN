# AI V4 - four-class TinyCNN for ESP32-CAM

V4 preserves the V3 split and preprocessing contract, then adds:

```text
0 = paper
1 = plastic
2 = organic
3 = other (cardboard + metal)
input = RGB 96x96
```

The `other` training count is 260, equal to the arithmetic mean of the three
V3 training class counts. It is sourced evenly from TrashNet cardboard and
metal. Exactly 25% of `other` train images are transformed to approximate the
QVGA RGB565 ESP32-CAM domain; validation and test images remain unmodified.

From `AI`:

```powershell
python -m pip install -r V4/requirements.txt
python -m V4.run_pipeline --force-prepare
```

The pipeline writes models and machine-readable metrics under `artifacts`, C
arrays under `esp32_model`, charts under `charts`, a Markdown report at
`EVALUATION_REPORT.md`, and the rendered PDF at `../output/pdf/V4_MODEL_REPORT.pdf`.

