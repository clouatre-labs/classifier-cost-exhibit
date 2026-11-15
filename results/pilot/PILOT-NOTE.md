# Pilot note (`secom-cost-threshold`)

Plumbing-only dry run of the sealed methodology on the first two folds of
`RepeatedStratifiedKFold(n_splits=10, n_repeats=1, random_state=0)`, run with
the exact pipeline of the sealed protocol and recorded under `results/pilot/`
(`run_kind: "pilot"`; excluded from the primary analysis and the findings
document). No accuracy or recall values were inspected before the seal.

## Plumbing results

| Check | Result |
| --- | --- |
| Schema conformance (`validate_schema.py`, strict JSON, `allow_nan=False`) | PASS: 2 files, 8 model records |
| NaN elimination (median imputation; no non-finite `y_prob`) | PASS |
| Feature columns, raw | 590 |
| Feature columns after variance drop (`std < 1e-12`) | 474 |
| Feature columns after correlation drop (`\|r\| > 0.95`) | 284-286 per fold |
| Reduced feature matrix non-empty | PASS |
| Findings-table generation | PASS (structure verified, values withheld) |
| Model fit + predict runtime, total across 4 models x 2 folds | ~2.0 s |

All four models (k-NN, decision tree, random forest, logistic regression) fit
and predicted on the real SECOM data, including on the 1e-35-variance float
columns and 41,951 NaN cells that motivated the numeric guards. The pilot is
green: the methodology promotes to the sealed 30-fold run unchanged.
