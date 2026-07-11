Run: 2026-07-11

Pipeline was updated from the old LogisticRegression baseline to the Tiny CNN
flow described in `docs/01_TRAIN_MODEL.md`.

Dataset split from `AI/trashnet/data`:

- Train known: 750 images (`paper`: 403, `plastic`: 347)
- Validation known: 144 images
- Test known: 182 images
- Validation other: 184 images
- Test other: 249 images

Float model, known test only:

- Accuracy: 87.91%
- Macro F1: 87.53%
- Recall paper: 88.89%
- Recall plastic: 86.49%

INT8 model, known test only:

- Accuracy: 87.36%
- Macro F1: 86.99%
- Recall paper: 87.96%
- Recall plastic: 86.49%
- Model size: 25,096 bytes

Rejection/OTHER result on TrashNet non-paper/plastic test images:

- OTHER false accept rate: 93.98% for INT8
- Calibration result: `feasible=false`

Conclusion: the Tiny CNN and INT8 export satisfy the paper/plastic recall target
on the current TrashNet split, but the OTHER gate is not reliable with TrashNet
non-paper/plastic classes. A real `validation_other/other` and final `test/other`
set from the prototype capture setup is still required before acceptance.
