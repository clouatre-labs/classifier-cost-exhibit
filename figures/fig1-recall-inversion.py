"""Figure 1: per-fold fail-class recall, accuracy-best vs challenger.

Regenerate: uv run --with matplotlib python figures/fig1-recall-inversion.py
Reads only committed results/raw/fold-*.json records.
"""

import json
import pathlib

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

RAW = pathlib.Path(__file__).parent.parent / "results" / "raw"
BEST, CHALLENGER = "random_forest", "knn"
MODELS = ["random_forest", "knn", "logistic_regression", "decision_tree"]


def load():
    folds = {}
    for path in sorted(RAW.glob("fold-*.json")):
        rec = json.loads(path.read_text())
        folds[rec["fold"]["index"]] = {m["model"]: m for m in rec["models"]}
    return folds


def main():
    folds = load()
    n = len(folds)
    recall_best = [folds[i][BEST]["metrics"]["recall_fail"] for i in range(n)]
    recall_chal = [folds[i][CHALLENGER]["metrics"]["recall_fail"] for i in range(n)]
    acc_best = [folds[i][BEST]["metrics"]["accuracy"] for i in range(n)]
    acc_chal = [folds[i][CHALLENGER]["metrics"]["accuracy"] for i in range(n)]

    fig, ax = plt.subplots(figsize=(8, 4.5), dpi=150)
    xs = range(n)
    ax.scatter(xs, recall_chal, marker="o", s=28, label=f"{CHALLENGER} recall (challenger)",
               color="#1f77b4", alpha=0.85)
    ax.scatter(xs, recall_best, marker="s", s=28, label=f"{BEST} recall (accuracy-best, 0 in all 30 folds)",
               color="#d62728", alpha=0.85)
    ax.plot(xs, acc_chal, linestyle=":", linewidth=1, color="#1f77b4", alpha=0.5,
            label=f"{CHALLENGER} accuracy")
    ax.plot(xs, acc_best, linestyle="--", linewidth=1, color="#d62728", alpha=0.5,
            label=f"{BEST} accuracy")
    ax.set_xlabel("Fold (3 repeats x 10 splits)")
    ax.set_ylabel("Metric value")
    ax.set_title("Fail-class recall: accuracy-best (random forest) vs challenger (k-NN)")
    ax.set_ylim(-0.03, 1.03)
    ax.annotate("random forest detects zero defects in every fold;\n"
                "k-NN detects defects in 10 of 30 folds",
                xy=(0.02, 0.32), xycoords="axes fraction", fontsize=8.5,
                bbox=dict(boxstyle="round,pad=0.35", fc="#fff3f3", ec="#d62728", alpha=0.9))
    ax.legend(fontsize=8, loc="center right")
    fig.tight_layout()
    out = pathlib.Path(__file__).parent / "fig1-recall-inversion.png"
    fig.savefig(out)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
