# Results

Raw per-fold records for the `secom-cost-threshold` experiment.

- `pilot/`: dry-run records from the first two folds of
  `RepeatedStratifiedKFold(n_splits=10, n_repeats=1, random_state=0)`,
  run before the seal was committed. Plumbing checks only; excluded from
  the primary analysis and the findings document.
- `raw/`: sealed run records from the pinned
  `RepeatedStratifiedKFold(n_splits=10, n_repeats=3, random_state=0)`
  (30 fold-evaluations), committed only after a green pilot and the seal.

Records validate against the schema in `DATA_DICTIONARY.md`; run
`uv run python validate_schema.py`.

## Dataset

UCI SECOM (id 179). The raw dataset is NOT committed; re-fetch and verify:

```bash
curl -LO https://archive.ics.uci.edu/static/public/179/secom.zip
unzip secom.zip   # secom.data, secom_labels.data
shasum -a 256 secom.data secom_labels.data
```

Expected SHA256 digests (also pinned in `seal.json`):

- `secom.data`: `20f0e7ee434f7dcbae0eea9ffff009a2b57f42d6b0dc9a5bd4f00782c0a3374c`
- `secom_labels.data`: `126884cf453705c9e61a903fe906f0665a3b45ce3639e621edc5c93c89627e03`

Place the two files in a `data/` directory at the repository root
(gitignored) before running `pipeline.py`.
