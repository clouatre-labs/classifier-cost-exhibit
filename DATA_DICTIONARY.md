# Data Dictionary

This document defines the schema and field meanings for experiment data files in this repository. `validate_schema.py` enforces the required fields below; run `uv run python validate_schema.py` before every PR that touches `experiments/`, `results/`, or `seal.json`.

## Layout

Each experiment directory `experiments/<slug>/` contains:

- `analysis.json`: run metadata, message counts, and evaluation scores (schema below)
- `scores.json`: per-criterion rubric scores with justifications
- `protocol.md`, `runner-prompt.md`, `scorer-prompt.md`: pre-registration artifacts
- `sessions/`: raw session logs or database exports

## analysis.json

### Top-level schema

| Field | Type | Nullable | Description |
|-------|------|----------|-------------|
| `experiment` | string | no | Experiment slug, matches the directory name |
| `schema_version` | string | no | Version of this schema the record conforms to |
| `title` | string | no | Human-readable experiment title |
| `issue` | string \| null | yes | Target issue or task reference |
| `date` | string | no | Experiment date (YYYY-MM-DD) |
| `model` | string | no | Model identifier under test |
| `n_per_group` | integer | no | Number of runs per group |
| `control_condition` | string | no | Description of the control condition |
| `treatment_condition` | string | no | Description of the treatment condition |
| `rubric_version` | string | no | Rubric identifier used for scoring |
| `orchestrator_session` | string \| null | yes | Orchestrator session reference, if any |
| `repo_head` | string | no | Repository commit at run time |
| `experiment_start` | string | no | ISO 8601 timestamp with UTC offset of first run |
| `experiment_end` | string | no | ISO 8601 timestamp with UTC offset of last run |
| `analyzed_at` | string | no | ISO 8601 timestamp with UTC offset of analysis |
| `runs` | object | no | Map of run ID to run record |
| `scores` | object | no | Scoring summary keyed by run ID |
| `statistical_test` | string | no | Pre-registered statistical test name |
| `conclusion` | string | no | Result summary |
| `pre_acknowledged_limitations` | array | no | Limitations stated before analysis |

### Run record schema

| Field | Type | Nullable | Description |
|-------|------|----------|-------------|
| `group` | string | no | `control` or `treatment` |
| `session_id` | string | no | Session identifier from the run harness |
| `messages` | integer | no | Message count in the session |
| `input_tokens` | integer | no | Accumulated input tokens |
| `output_tokens` | integer | no | Accumulated output tokens |
| `total_tokens` | integer | no | Sum of input and output tokens |
| `wall_clock_seconds` | number | no | Elapsed wall-clock seconds |
| `bytes` | integer \| null | yes | Session byte size, if recorded |
| `note` | string \| null | yes | Optional note (e.g. failure reason) |

## scores.json

Free-form per-criterion scoring keyed by run ID; each entry SHOULD include the score value, per-criterion results, and scorer justifications.

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
