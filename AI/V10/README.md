# AI V10

V10 replaces the square 96x96 input with a 128x96 4:3 input, widens the
ESP-friendly CNN, combines the prepared and augmented datasets, trains from
scratch and exports a full-INT8 model for `ESP-TRASH-V3`.

## Reproduce

Run from `AI/`:

```powershell
python -m V10.merge_datasets
python -m V10.augment_data
python -m V10.verify_preprocessing
python -m V10.train --epochs 80 --patience 14 --batch-size 16 --seed 10
python -m V10.export_int8
python -m V10.evaluate
python -m V10.infer_server_tmp
python -m V10.analyze_esp_data
python -m V10.embed_model
```

Then run from the repository root:

```powershell
python .\ESP-TRASH-V3\verify_embedded_model.py
.\ESP-TRASH-V3\build_firmware.ps1 -Clean
```

See `artifacts/DEPLOYMENT_REPORT.md` for deployment measurements and
`artifacts/esp_data_analysis/REPORT.md` for the full ESP image analysis. The
analysis treats `server-tmp/data/images` as no-GT and never assigns it an
accuracy/error rate.
