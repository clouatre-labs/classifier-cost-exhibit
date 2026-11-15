# Methodology

Experimental design and analysis plan for experiments in this repository. Replace each `TODO` section per experiment; keep this top-level document as the shared methodological contract.

## Research Question

Does the accuracy-optimal classifier on the UCI SECOM dataset miss more defects than a lower-accuracy alternative under an explicit error-cost matrix, and does a cost-aligned decision threshold (p* = FP/(FP+FN)) reverse the ranking? Framed so that a null result (the accuracy-best model also cost-best at both thresholds) is as informative as the inversion.

## Pre-Registration

The protocol is committed in `seal.json` BEFORE any sealed `fit()` call: pinned dataset SHA256 digests, splitter (`RepeatStratifiedKFold`, 10x3, seed 0), preprocessing pipeline, models and hyperparameters, numeric guards, cost ratios (14:1 baseline, 10:1 sensitivity), and the statistical test (two-sided exact binomial sign test, alpha 0.05). The commit containing the seal must precede the first sealed fold record; edits after data collection begins require a dated addendum.

- Endpoints are named in the seal before any model output is examined.
- The pilot dry run (2 folds, plumbing only) passes before the seal and is excluded from the primary analysis.
- Statistical tests are fixed in `seal.json` before data collection.

## Experimental Design

TODO: Describe per experiment:

- Task and target (issue, dataset, or benchmark used).
- Groups: control and treatment conditions, with exact prompt text or deltas.
- Sample size per group and stopping rule.
- Agent or model configuration (model, temperature, provider, extensions).

## Blind Scoring

Scorers receive only the output artifacts and the rubric. No group labels, run metadata, or sibling outputs are visible during scoring. Report any inter-rater reliability checks and their agreement statistics.

## Analysis Plan

Raw per-fold records (full `y_true`/`y_prob` arrays) land in `results/raw/fold-00..29.json`; the sealed analysis lands in `results/raw/analysis.json` (schemas in [DATA_DICTIONARY.md](DATA_DICTIONARY.md), enforced by `validate_schema.py`). Every reported number re-derives from the committed records via the committed [analysis.py](analysis.py). Figures are generated from the scripts in `figures/` into `figures/`.

## Threats to Validity

TODO: Enumerate, at minimum:

- Ceiling or floor effects in the rubric.
- Rubric-scorer co-design bias.
- Run-to-run variance and seed/provider nondeterminism.
- Contamination of the task in model training data.
