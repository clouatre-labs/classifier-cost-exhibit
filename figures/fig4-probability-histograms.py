"""Figure 4: predicted fail-class probability histograms per model.

Regenerate: uv run --with matplotlib python figures/fig4-probability-histograms.py
Reads only committed results/raw/fold-*.json records.
"""

import json
import pathlib

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

RAW = pathlib.Path(__file__).parent.parent / "results" / "raw"
MODELS = ["random_forest", "knn", "logistic_regression", "decision_tree"]
COLORS = {
    "random_forest": "#D55E00",
    "knn": "#0072B2",
    "logistic_regression": "#009E73",
    "decision_tree": "#CC79A7",
}


def load():
    by_model = {m: {"pass": [], "fail": []} for m in MODELS}
    for path in sorted(RAW.glob("fold-*.json")):
        rec = json.loads(path.read_text())
        for m in rec["models"]:
            for t, p in zip(m["y_true"], m["y_prob"]):
                by_model[m["model"]]["pass" if t == 0 else "fail"].append(p)
    return by_model


def main():
    by_model = load()
    fig, axes = plt.subplots(2, 2, figsize=(9, 6.5), dpi=150, sharex=True, sharey=True)
    for ax, name in zip(axes.flat, MODELS):
        ax.hist(by_model[name]["pass"], bins=40, range=(0, 1), alpha=0.6,
                color=COLORS[name], label="pass units")
        fails = by_model[name]["fail"]
        weights = [len(by_model[name]["pass"]) / max(len(fails), 1)] * len(fails)
        ax.hist(fails, bins=40, range=(0, 1), alpha=0.8, color="black",
                weights=weights, label="fail units (rescaled)")
        ax.axvline(0.5, color="gray", linestyle="--", linewidth=1)
        ax.axvline(1.0 / 15.0, color="black", linestyle=":", linewidth=1)
        ax.set_title(name, fontsize=9)
        ax.legend(fontsize=7)
    for ax in axes[1]:
        ax.set_xlabel("Predicted probability of fail class")
    fig.suptitle("Predicted probabilities: graded outputs enable threshold tuning, degenerate 0/1 outputs do not",
                 fontsize=10)
    fig.tight_layout()
    out = pathlib.Path(__file__).parent / "fig4-probability-histograms.png"
    fig.savefig(out)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
