# Data Dictionary

This document defines the schema and field meanings for experiment data files in this repository. `validate_schema.py` enforces the required fields below; run `uv run python validate_schema.py` before every PR that touches `experiments/`, `results/`, or `seal.json`.

## Layout

This repository runs one pre-registered experiment (`secom-cost-threshold`) at the repo root; `experiments/example-fixture/` is the CI schema-validation fixture only.

- `seal.json`: pre-registered protocol (schema below)
- `results/raw/fold-00..29.json`: sealed per-fold records (schema below)
- `results/pilot/fold-00..01.json`: pilot records, excluded from the primary analysis
- `results/raw/analysis.json`: sealed analysis output of `analysis.py`
- `results/findings.md`: sealed findings

## Derived analysis (`results/raw/analysis.json`)

Written by `analysis.py` from the raw fold records; not validated by `validate_schema.py` (the raw records and seal are).

| Field | Type | Description |
|-------|------|-------------|
| `schema_version` | string | Schema version, `1.0.0` |
| `experiment` | string | Experiment slug, `secom-cost-threshold` |
| `n_folds` | integer | Number of sealed folds (30) |
| `p_star` | number | Cost-aligned threshold, FP/(FP+FN) |
| `mean_accuracy` | object | Mean accuracy per model |
| `mean_recall_fail` / `mean_precision_fail` | object | Mean fail-class recall/precision per model |
| `accuracy_ranking` / `cost_ranking_at_p_star_baseline` | array | Model orderings by accuracy and cost at p* |
| `accuracy_best` / `challenger` | string | Slug of the accuracy-best and second-ranked models |
| `primary` | object | Sign-test block: test name, `n_nonzero`, `k_challenger_better`, `p_value`, `alpha`, `significant`, mean recalls, descriptive inversions |
| `cost` | object | Expected cost per model at the 0.5 and p* thresholds, 14:1 and 10:1 ratios |
| `ranking_flip_vs_accuracy` | object | Accuracy rank versus cost-at-0.5 rank per model |

## seal.json (experiment `secom-cost-threshold`)

Pre-registered protocol committed before any sealed `fit()` call. `validate_schema.py` enforces the pinned splitter (`n_splits=10`, `n_repeats=3`, `random_state=0`), the exact model set (`knn`, `decision_tree`, `random_forest`, `logistic_regression`), null `random_state` for k-NN (the estimator does not accept it), and `zero_division=0`.

| Field | Type | Description |
|-------|------|-------------|
| `schema_version` | string | Schema version, `1.0.0` |
| `experiment` | string | Experiment slug |
| `sealed_before_run` | boolean | Must be `true` |
| `dataset` | object | Name, UCI id, download URL, class counts, per-file SHA256 digests and shapes |
| `splitter` | object | Pinned splitter class and parameters |
| `models` | object | Estimator name, hyperparameters, `random_state` per model |
| `preprocessing` | array | Ordered preprocessing steps (median imputation, variance drop, correlation drop, scaling) |
| `numeric_guards` | object | Variance drop threshold (`std < 1e-12`), correlation threshold (`\|r\| > 0.95`), `zero_division=0`, strict serialization |
| `primary_endpoint` | object | Comparison, test (two-sided exact binomial sign test), alpha, tie rule |
| `cost_analysis` | object | Cost formula, 14:1 baseline and 10:1 sensitivity FN:FP ratios, `p_star` expression, thresholds compared |
| `record_contents` | object | Scalar metrics and arrays stored per record |

## Per-fold records (`results/pilot/*.json`, `results/raw/*.json`)

One JSON file per fold, serialized with `json.dump(..., allow_nan=False)`; four model entries per file. Pilot records use `run_kind: "pilot"` and are excluded from the primary analysis.

### Top-level schema

| Field | Type | Description |
|-------|------|-------------|
| `schema_version` | string | Schema version, `1.0.0` |
| `run_kind` | string | `pilot` or `sealed` |
| `experiment` | string | Experiment slug, `secom-cost-threshold` |
| `date` | string | Run date (YYYY-MM-DD) |
| `splitter` | object | `class`, `n_splits`, `n_repeats`, `random_state` of the splitter used |
| `fold` | object | `repeat`, `split`, and global `index` of the fold |
| `models` | array | One model record per estimator (four per fold) |

### Model record schema

| Field | Type | Description |
|-------|------|-------------|
| `model` | string | One of `knn`, `decision_tree`, `random_forest`, `logistic_regression` |
| `wall_clock_seconds` | number | Fit + predict wall-clock time for the fold |
| `metrics.accuracy` | number | Fold accuracy |
| `metrics.recall_fail` | number | Recall on the fail class (positive label 1), `zero_division=0` |
| `metrics.precision_fail` | number | Precision on the fail class, `zero_division=0` |
| `metrics.fn` | integer | False negatives on the fail class |
| `metrics.fp` | integer | False positives on the fail class |
| `features.raw` | integer | Feature columns before filtering (590) |
| `features.after_variance` | integer | Columns surviving the variance filter (train fold only) |
| `features.after_correlation` | integer | Columns surviving the correlation filter (train fold only) |
| `y_true` | array of 0/1 | Full test-fold true labels |
| `y_prob` | array of float | Full test-fold predicted probability of the fail class, at full float precision; same length as `y_true` |

`y_true`/`y_prob` let the cost-vs-threshold sweep and probability histograms re-derive from committed records without re-running anything.
