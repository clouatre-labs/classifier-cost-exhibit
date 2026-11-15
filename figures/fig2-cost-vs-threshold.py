"""Figure 2: expected cost vs decision threshold per model at the 14:1 ratio.

Regenerate: uv run --with matplotlib python figures/fig2-cost-vs-threshold.py
Reads only committed results/raw/fold-*.json records.
"""

import json
import pathlib

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

RAW = pathlib.Path(__file__).parent.parent / "results" / "raw"
P_STAR = 1.0 / (1.0 + 14.0)
FN_COST, FP_COST = 14.0, 1.0
COLORS = {
    "random_forest": "#D55E00",
    "knn": "#0072B2",
    "logistic_regression": "#009E73",
    "decision_tree": "#CC79A7",
}


def load():
    ys, ps = {}, {}
    for path in sorted(RAW.glob("fold-*.json")):
        rec = json.loads(path.read_text())
        for m in rec["models"]:
            ys.setdefault(m["model"], []).extend(m["y_true"])
            ps.setdefault(m["model"], []).extend(m["y_prob"])
    return ys, ps


def cost(y, p, t):
    fn = sum(1 for a, b in zip(y, p) if a == 1 and b < t)
    fp = sum(1 for a, b in zip(y, p) if a == 0 and b >= t)
    return FN_COST * fn + FP_COST * fp


def main():
    ys, ps = load()
    fig, ax = plt.subplots(figsize=(8, 4.5), dpi=150)
    thresholds = [i / 200 for i in range(1, 200)]
    for name in sorted(ys):
        ax.plot(thresholds, [cost(ys[name], ps[name], t) for t in thresholds],
                label=name, color=COLORS[name], linewidth=1.6)
    ax.axvline(0.5, color="gray", linestyle="--", linewidth=1, label="default 0.5")
    ax.axvline(P_STAR, color="black", linestyle=":", linewidth=1.2,
               label=r"p* = 1/15 ≈ 0.067")
    ax.set_xlabel("Decision threshold (fail-class probability cutoff)")
    ax.set_ylabel("Total expected cost (FN:FP = 14:1)")
    ax.set_title("Expected cost vs decision threshold per model at the 14:1 FN:FP ratio")
    ax.legend(fontsize=8)
    fig.tight_layout()
    out = pathlib.Path(__file__).parent / "fig2-cost-vs-threshold.png"
    fig.savefig(out)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
