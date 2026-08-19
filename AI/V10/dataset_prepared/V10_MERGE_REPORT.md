# V10 dataset merge report

`dataset_prepared` now contains both source datasets without deleting
`dataset_augmented_v9`.

| Split | paper | plastic | organic | Total |
|---|---:|---:|---:|---:|
| train | 225 | 225 | 225 | 675 |
| validation | 13 | 13 | 13 | 39 |
| test | 13 | 13 | 13 | 39 |

- Total: 753 images.
- Exact duplicate files: 0.
- Source-group leakage: 0.
- Incoming source rows: 486.
- Physical source-path corrections resolved by filename and SHA-256: 9.
