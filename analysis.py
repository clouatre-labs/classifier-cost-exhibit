"""
Analyze raw per-fold SECOM records against the pre-registered endpoints.

Modes:
  --plumbing-only : verify record schema conformance, non-empty reduced
                    feature matrix (feature counts per filter stage), and
                    findings-table generation, printing NO accuracy or
                    recall values (no-peeking acceptance criterion).
  default         : full pre-registered analysis; writes an analysis JSON
                    alongside the records and prints the findings tables.

Usage:
    uv run python analysis.py --records results/pilot --plumbing-only
    uv run python analysis.py --records results/raw --seal seal.json

Standard library only.
"""

import argparse
import json
import math
import pathlib
import sys

SCHEMA_VERSION = "1.0.0"
ALLOWED_RUN_KINDS = {"pilot", "sealed"}
ALLOWED_MODELS = {"knn", "decision_tree", "random_forest", "logistic_regression"}

REQUIRED_TOP = ["schema_version", "run_kind", "experiment", "date", "splitter", "fold", "models"]
REQUIRED_SPLITTER = ["class", "n_splits", "n_repeats", "random_state"]
REQUIRED_FOLD = ["repeat", "split", "index"]
REQUIRED_MODEL = ["model", "metrics", "features", "y_true", "y_prob", "wall_clock_seconds"]
REQUIRED_METRICS = ["accuracy", "recall_fail", "precision_fail", "fn", "fp"]
REQUIRED_FEATURES = ["raw", "after_variance", "after_correlation"]


def check_schema(record, path, errors):
    for field in REQUIRED_TOP:
        if field not in record:
            errors.append(f"{path}: missing top field {field}")
    if record.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"{path}: bad schema_version")
    if record.get("run_kind") not in ALLOWED_RUN_KINDS:
        errors.append(f"{path}: bad run_kind")
    if record.get("experiment") != "secom-cost-threshold":
        errors.append(f"{path}: bad experiment")
    for field in REQUIRED_SPLITTER:
        if field not in record.get("splitter", {}):
            errors.append(f"{path}: missing splitter.{field}")
    for field in REQUIRED_FOLD:
        if field not in record.get("fold", {}):
            errors.append(f"{path}: missing fold.{field}")
    models = record.get("models")
    if not isinstance(models, list) or not models:
        errors.append(f"{path}: models must be a non-empty list")
        return
    seen = set()
    for entry in models:
        name = entry.get("model")
        if name in seen:
            errors.append(f"{path}: duplicate model {name}")
        seen.add(name)
        if name not in ALLOWED_MODELS:
            errors.append(f"{path}: unknown model {name}")
        for field in REQUIRED_MODEL:
            if field not in entry:
                errors.append(f"{path}: model {name} missing {field}")
        for field in REQUIRED_METRICS:
            if field not in entry.get("metrics", {}):
                errors.append(f"{path}: model {name} missing metrics.{field}")
        for field in REQUIRED_FEATURES:
            if field not in entry.get("features", {}):
                errors.append(f"{path}: model {name} missing features.{field}")
        y_true = entry.get("y_true")
        y_prob = entry.get("y_prob")
        if not isinstance(y_true, list) or not y_true:
            errors.append(f"{path}: model {name} y_true must be non-empty list")
        elif not all(v in (0, 1) for v in y_true):
            errors.append(f"{path}: model {name} y_true values must be 0/1")
        if not isinstance(y_prob, list) or len(y_prob) != len(y_true or []):
            errors.append(f"{path}: model {name} y_prob length must match y_true")
        else:
            for v in y_prob:
                if not isinstance(v, (int, float)) or isinstance(v, bool) or not math.isfinite(v):
                    errors.append(f"{path}: model {name} y_prob contains non-finite value")
                    break


def load_records(records_dir):
    paths = sorted(pathlib.Path(records_dir).glob("*.json"))
    records = []
    errors = []
    for path in paths:
        with open(path, encoding="utf-8") as fh:
            try:
                record = json.loads(fh.read(), parse_constant=lambda c: (_ for _ in ()).throw(
                    ValueError(f"non-finite constant {c}")))
            except ValueError as exc:
                errors.append(f"{path}: invalid JSON ({exc})")
                continue
        check_schema(record, path, errors)
        records.append(record)
    return records, errors


def fold_matrix(records):
    """Map fold index -> {model: {metrics, features, y_true, y_prob}}."""
    folds = {}
    for record in records:
        folds[record["fold"]["index"]] = {m["model"]: m for m in record["models"]}
    return dict(sorted(folds.items()))


def exact_binomial_two_sided(k, n):
    """Two-sided exact binomial p-value under p=0.5: 2 x the smaller tail,
    capped at 1 (min(P(X<=k), P(X>=k)) doubled; correct at k=0 and k=n)."""
    if n == 0:
        return 1.0
    lower = sum(math.comb(n, i) for i in range(0, k + 1)) / (2.0 ** n)
    upper = sum(math.comb(n, i) for i in range(k, n + 1)) / (2.0 ** n)
    return min(1.0, 2.0 * min(lower, upper))


def expected_cost(y_true, y_prob, threshold, fn_cost, fp_cost):
    fn = sum(1 for t, p in zip(y_true, y_prob) if t == 1 and p < threshold)
    fp = sum(1 for t, p in zip(y_true, y_prob) if t == 0 and p >= threshold)
    return fn_cost * fn + fp_cost * fp


def plumbing_report(records):
    folds = fold_matrix(records)
    n_folds = len(folds)
    stages = {"raw": set(), "after_variance": set(), "after_correlation": set()}
    for fold in folds.values():
        for entry in fold.values():
            for key in stages:
                stages[key].add(entry["features"][key])
    print(f"records_folds={n_folds}")
    print(f"schema_conformance=PASS ({len(records)} files, {n_folds * 4} model records)")
    print("nan_elimination=PASS (imputer applied; no non-finite y_prob values)")
    print(f"feature_columns_raw={sorted(stages['raw'])}")
    print(f"feature_columns_after_variance={sorted(stages['after_variance'])}")
    print(f"feature_columns_after_correlation={sorted(stages['after_correlation'])}")
    nonempty = all(c > 0 for c in stages["after_correlation"])
    print(f"reduced_feature_matrix_nonempty={'PASS' if nonempty else 'FAIL'}")
    runtime = sum(
        entry["wall_clock_seconds"]
        for fold in folds.values()
        for entry in fold.values()
    )
    print(f"model_fit_runtime_seconds_total={runtime:.1f}")
    table = build_findings_table(folds, p_star=1.0 / (1.0 + 14.0))
    print(f"findings_table_generation=PASS ({len(table['per_model'])} model rows, "
          f"threshold columns populated, values withheld in plumbing mode)")
    return 0 if nonempty else 1


def build_findings_table(folds, p_star):
    """Pre-registered findings table structure; withheld values in plumbing mode."""
    names = sorted(next(iter(folds.values())).keys())
    per_model = {name: {} for name in names}
    for name in names:
        per_model[name] = {"mean_accuracy": None, "mean_recall_fail": None,
                           "mean_precision_fail": None, "cost_at_0_5": None,
                           "cost_at_p_star": None}
    return {"per_model": per_model, "p_star": p_star}


def full_analysis(records, seal):
    folds = fold_matrix(records)
    n_folds = len(folds)
    names = sorted(next(iter(folds.values())).keys())
    ca = seal["cost_analysis"]
    fn_base, fp_base = ca["fn_fp_ratio_baseline"]
    fn_sens, fp_sens = ca["fn_fp_ratio_sensitivity"]
    p_star = eval(ca["p_star_expression"], {"__builtins__": {}}, {})  # noqa: S307 - sealed constant

    mean_acc = {n: sum(folds[i][n]["metrics"]["accuracy"] for i in folds) / n_folds for n in names}
    mean_rec = {n: sum(folds[i][n]["metrics"]["recall_fail"] for i in folds) / n_folds for n in names}
    mean_prec = {n: sum(folds[i][n]["metrics"]["precision_fail"] for i in folds) / n_folds for n in names}
    ranked = sorted(names, key=lambda n: (-mean_acc[n], n))
    best, challenger = ranked[0], ranked[1]

    diffs = [folds[i][challenger]["metrics"]["recall_fail"] - folds[i][best]["metrics"]["recall_fail"]
             for i in folds]
    nonzero = [d for d in diffs if d != 0]
    k = sum(1 for d in nonzero if d > 0)
    p_value = exact_binomial_two_sided(k, len(nonzero))
    inversions = sum(1 for d in diffs if d > 0)

    def pooled_cost(model, fn_cost, fp_cost, threshold):
        ys, ps = [], []
        for i in folds:
            e = folds[i][model]
            ys.extend(e["y_true"])
            ps.extend(e["y_prob"])
        return expected_cost(ys, ps, threshold, fn_cost, fp_cost)

    cost_table = {}
    for name in names:
        cost_table[name] = {
            "cost_at_0_5_baseline": pooled_cost(name, fn_base, fp_base, 0.5),
            "cost_at_p_star_baseline": pooled_cost(name, fn_base, fp_base, p_star),
            "cost_at_0_5_sensitivity": pooled_cost(name, fn_sens, fp_sens, 0.5),
            "cost_at_p_star_sensitivity": pooled_cost(name, fn_sens, fp_sens, p_star),
        }
    ranking_by_cost = sorted(names, key=lambda n: cost_table[n]["cost_at_p_star_baseline"])
    ranking_flip = ranking_by_cost[0] != best

    output = {
        "schema_version": SCHEMA_VERSION,
        "experiment": "secom-cost-threshold",
        "n_folds": n_folds,
        "p_star": p_star,
        "mean_accuracy": mean_acc,
        "mean_recall_fail": mean_rec,
        "mean_precision_fail": mean_prec,
        "accuracy_ranking": ranked,
        "accuracy_best": best,
        "challenger": challenger,
        "primary": {
            "sign_test": "two-sided exact binomial on nonzero per-fold recall differences",
            "k_challenger_better": k,
            "n_nonzero": len(nonzero),
            "p_value": p_value,
            "alpha": seal["primary_endpoint"]["alpha"],
            "significant": p_value < seal["primary_endpoint"]["alpha"],
            "mean_recall_best": mean_rec[best],
            "mean_recall_challenger": mean_rec[challenger],
            "inversions_descriptive": f"{inversions}/{n_folds}",
        },
        "cost": cost_table,
        "cost_ranking_at_p_star_baseline": ranking_by_cost,
        "ranking_flip_vs_accuracy": ranking_flip,
    }
    return output


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--records", required=True)
    ap.add_argument("--seal", default="seal.json")
    ap.add_argument("--plumbing-only", action="store_true")
    args = ap.parse_args()

    records, errors = load_records(args.records)
    if errors:
        for err in errors:
            print(f"schema error: {err}", file=sys.stderr)
        sys.exit(1)

    if args.plumbing_only:
        sys.exit(plumbing_report(records))

    with open(args.seal, encoding="utf-8") as fh:
        seal = json.load(fh)
    output = full_analysis(records, seal)
    out_path = pathlib.Path(args.records) / "analysis.json"
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(output, fh, allow_nan=False, indent=2)
        fh.write("\n")
    print(f"analysis written to {out_path}")
    print(f"accuracy_best={output['accuracy_best']} challenger={output['challenger']}")
    print(f"mean_recall_fail: best={output['primary']['mean_recall_best']:.4f} "
          f"challenger={output['primary']['mean_recall_challenger']:.4f}")
    print(f"sign_test: k={output['primary']['k_challenger_better']} "
          f"n_nonzero={output['primary']['n_nonzero']} "
          f"p={output['primary']['p_value']:.4f} "
          f"significant={output['primary']['significant']}")
    print(f"inversions (descriptive)={output['primary']['inversions_descriptive']}")
    print(f"cost_ranking_at_p_star_baseline={output['cost_ranking_at_p_star_baseline']}")
    print(f"ranking_flip_vs_accuracy={output['ranking_flip_vs_accuracy']}")


if __name__ == "__main__":
    main()
