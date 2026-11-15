# AGENTS.md

## Project overview

Pre-registered evaluation exhibit on the UCI SECOM dataset: tests whether the accuracy-optimal classifier misses more defects than a lower-accuracy alternative under an explicit error-cost matrix, and whether a cost-aligned decision threshold (p* = FP/(FP+FN)) reverses the ranking. Python (stdlib-only validator via uv); one directory per pre-registered experiment under `experiments/`.

## Stack & Commands

Python 3 via [uv](https://docs.astral.sh/uv/); no third-party dependencies.

```
# build:  n/a (analysis repo; figures regenerate via recipe/)
# test:   uv run python validate_schema.py --self-test
# lint:   uv run python validate_schema.py
# format: n/a
```

## Labels and Milestones
- Canonical labels reuse the Conventional Commits type vocabulary: `feat`, `fix`, `docs`, `chore`, `refactor`, `ci`, `testing`, `perf`, plus domain labels (`dependencies`, `security`). Safe-settings syncs the org label set add/update-only, so the GitHub defaults (`bug`, `enhancement`, `documentation`) still exist; prefer the Conventional Commits labels and ignore the defaults (org-wide removal is tracked in clouatre-labs/.github)
- Meta labels are kept: `good first issue`, `help wanted`, `duplicate`, `invalid`, `question`, `wontfix`
- Milestones are theme-based with a due date; close a milestone when its last issue closes; carry-over work moves to the current quarter milestone (e.g. `Q4 2026`)

## Development standards

- GPG sign and DCO sign-off: `git commit -S --signoff` (every commit)
- Treat all repositories as public; no secrets, API keys, credentials, or PII
- Actions pinned to SHA (not tags); actionlint recommended for local workflow validation
- Training data is stale: verify APIs and versions against installed packages or docs

## Testing

- One happy path and one edge case per behavior; no redundant variations
- AAA pattern (Arrange, Act, Assert); keep each test focused and short

## Design references

- [METHODOLOGY.md](METHODOLOGY.md): shared experimental design contract (pre-registration, blind scoring, analysis plan)
- [DATA_DICTIONARY.md](DATA_DICTIONARY.md): schema for `analysis.json` and `scores.json`
- [docs/REPO-STANDARDS.md](docs/REPO-STANDARDS.md): artifact map and post-clone checklist
- [experiments/README.md](experiments/README.md): experiment directory layout

## Do not

- Add dependencies without justification in the PR description
- Implement features not specified in the assigned issue
- Modify files outside the scope of the assigned issue
<!-- Add project-specific constraints here -->
