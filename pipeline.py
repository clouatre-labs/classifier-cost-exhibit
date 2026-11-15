"""
Run the sealed SECOM pipeline and write raw per-fold records.

All protocol parameters are read from seal.json; nothing is chosen at run
time except the output directory and fold scope, which the caller pins on
the command line (the pilot uses the same splitter class and random_state
with n_repeats=1 and the first two folds; the sealed run uses the seal's
n_repeats=3 with all folds).

Usage:
    uv run python pipeline.py --seal seal.json --data-dir data \
        --out-dir results/raw [--pilot]

Requires scikit-learn and numpy (not needed for schema validation in CI).
"""

import argparse
import datetime
import hashlib
import json
import pathlib
import sys
import time

import numpy as np
from sklearn.metrics import accuracy_score, precision_score, recall_score
from sklearn.model_selection import RepeatedStratifiedKFold
from sklearn.neighbors import KNeighborsClassifier
from sklearn.tree import DecisionTreeClassifier
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression

SCHEMA_VERSION = "1.0.0"
EXPERIMENT = "secom-cost-threshold"


def load_seal(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_dataset(data_dir, seal):
    """Load SECOM features and labels, verify against the seal, remap labels."""
    x_path = pathlib.Path(data_dir) / "secom.data"
    y_path = pathlib.Path(data_dir) / "secom_labels.data"
    for path, key in ((x_path, "secom.data"), (y_path, "secom_labels.data")):
        digest = sha256_of(path)
        expected = seal["dataset"]["files"][key]["sha256"]
        if digest != expected:
            raise SystemExit(f"checksum mismatch for {path}: {digest} != {expected}")
    X = np.loadtxt(x_path)
    with open(y_path, encoding="utf-8") as fh:
        lines = [line for line in fh.read().strip().split("\n") if line]
    y_raw = np.array([int(line.split()[0]) for line in lines])
    if X.shape != tuple(seal["dataset"]["files"]["secom.data"]["shape"]):
        raise SystemExit(f"feature matrix shape mismatch: {X.shape}")
    if len(y_raw) != seal["dataset"]["files"]["secom_labels.data"]["rows"]:
        raise SystemExit(f"label row count mismatch: {len(y_raw)}")
    y = (y_raw == 1).astype(int)  # -1 (pass) -> 0, 1 (fail) -> 1
    n_pass = int((y == 0).sum())
    n_fail = int((y == 1).sum())
    expected = seal["dataset"]["class_counts"]
    if n_pass != expected["pass_0"] or n_fail != expected["fail_1"]:
        raise SystemExit(f"class counts mismatch: {n_pass} pass, {n_fail} fail")
    return X, y


class Preprocessor:
    """Median imputation -> variance drop -> correlation drop -> standardize.

    All statistics are fit on the training fold only; transform is applied
    to the test fold. Keeps the pipeline leakage-safe by construction.
    """

    def __init__(self, std_threshold, corr_abs_threshold):
        self.std_threshold = std_threshold
        self.corr_abs_threshold = corr_abs_threshold

    def fit(self, X):
        self.median_ = np.nanmedian(X, axis=0)
        Xi = np.where(np.isnan(X), self.median_, X)
        std = Xi.std(axis=0)
        keep_var = np.where(std >= self.std_threshold)[0]  # NaN std drops here
        self.n_after_variance_ = len(keep_var)
        Xv = Xi[:, keep_var]
        corr = np.corrcoef(Xv, rowvar=False)
        if not np.isfinite(corr).all():
            raise SystemExit("correlation matrix contains non-finite values")
        drop = set()
        for i in range(corr.shape[0]):
            for j in range(i + 1, corr.shape[0]):
                if abs(corr[i, j]) > self.corr_abs_threshold:
                    drop.add(j)  # keep the lower-indexed column
        kept_positions = [k for k in range(len(keep_var)) if k not in drop]
        self.columns_ = keep_var[np.array(kept_positions)]
        self.n_after_correlation_ = len(kept_positions)
        Xk = Xv[:, kept_positions]
        self.mean_ = Xk.mean(axis=0)
        self.scale_ = Xk.std(axis=0)
        return self

    def transform(self, X):
        Xi = np.where(np.isnan(X), self.median_, X)
        Xk = Xi[:, self.columns_]
        return (Xk - self.mean_) / self.scale_


def make_estimator(spec):
    name = spec["estimator"]
    params = dict(spec["params"])
    if spec.get("random_state") is not None:
        params["random_state"] = spec["random_state"]
    estimators = {
        "KNeighborsClassifier": KNeighborsClassifier,
        "DecisionTreeClassifier": DecisionTreeClassifier,
        "RandomForestClassifier": RandomForestClassifier,
        "LogisticRegression": LogisticRegression,
    }
    if name not in estimators:
        raise SystemExit(f"estimator not in seal: {name}")
    return estimators[name](**params)


def evaluate_fold(X, y, train_idx, test_idx, seal):
    pre = Preprocessor(
        seal["numeric_guards"]["variance_drop_std_below"],
        seal["numeric_guards"]["correlation_abs_drop_above"],
    )
    pre.fit(X[train_idx])
    Xtr = pre.transform(X[train_idx])
    Xte = pre.transform(X[test_idx])
    ytr, yte = y[train_idx], y[test_idx]
    n_raw = X.shape[1]
    n_var = int(pre.n_after_variance_)
    n_corr = int(pre.n_after_correlation_)
    records = []
    for model_name, spec in seal["models"].items():
        est = make_estimator(spec)
        started = time.perf_counter()
        est.fit(Xtr, ytr)
        y_pred = est.predict(Xte)
        y_prob = est.predict_proba(Xte)[:, 1]
        elapsed = time.perf_counter() - started
        fn = int(((yte == 1) & (y_pred == 0)).sum())
        fp = int(((yte == 0) & (y_pred == 1)).sum())
        records.append({
            "model": model_name,
            "wall_clock_seconds": round(elapsed, 6),
            "metrics": {
                "accuracy": float(accuracy_score(yte, y_pred)),
                "recall_fail": float(recall_score(yte, y_pred, pos_label=1, zero_division=0)),
                "precision_fail": float(precision_score(yte, y_pred, pos_label=1, zero_division=0)),
                "fn": fn,
                "fp": fp,
            },
            "features": {
                "raw": n_raw,
                "after_variance": n_var,
                "after_correlation": n_corr,
            },
            "y_true": [int(v) for v in yte],
            "y_prob": [float(v) for v in y_prob],
        })
    return records


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seal", default="seal.json")
    ap.add_argument("--data-dir", default="data")
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--pilot", action="store_true",
                    help="run n_repeats=1, first 2 folds only (pilot scope)")
    args = ap.parse_args()

    seal = load_seal(args.seal)
    X, y = load_dataset(args.data_dir, seal)
    spl = seal["splitter"]
    n_repeats = 1 if args.pilot else spl["n_repeats"]
    folds_limit = 2 if args.pilot else None

    rskf = RepeatedStratifiedKFold(
        n_splits=spl["n_splits"], n_repeats=n_repeats, random_state=spl["random_state"]
    )
    out_dir = pathlib.Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    zero_division = seal["numeric_guards"]["zero_division"]  # pinned; asserted below
    if zero_division != 0:
        raise SystemExit("seal must pin zero_division=0")

    total_started = time.perf_counter()
    for fold_index, (train_idx, test_idx) in enumerate(rskf.split(X, y)):
        if folds_limit is not None and fold_index >= folds_limit:
            break
        records = evaluate_fold(X, y, train_idx, test_idx, seal)
        repeat = fold_index // spl["n_splits"]
        split = fold_index % spl["n_splits"]
        record = {
            "schema_version": SCHEMA_VERSION,
            "run_kind": "pilot" if args.pilot else "sealed",
            "experiment": EXPERIMENT,
            "date": datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%d"),
            "splitter": {
                "class": "RepeatedStratifiedKFold",
                "n_splits": spl["n_splits"],
                "n_repeats": n_repeats,
                "random_state": spl["random_state"],
            },
            "fold": {"repeat": repeat, "split": split, "index": fold_index},
            "models": records,
        }
        path = out_dir / f"fold-{fold_index:02d}.json"
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(record, fh, allow_nan=False, indent=2)
            fh.write("\n")
        print(f"wrote {path}")

    elapsed = time.perf_counter() - total_started
    print(f"runtime_seconds={elapsed:.1f}")


if __name__ == "__main__":
    main()
