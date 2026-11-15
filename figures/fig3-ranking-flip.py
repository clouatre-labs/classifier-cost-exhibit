"""Figure 3: model ranking by accuracy vs by expected cost, side by side.

Regenerate: uv run --with matplotlib python figures/fig3-ranking-flip.py
Reads only committed results/raw/fold-*.json records and analysis.json.
"""

import json
import pathlib

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = pathlib.Path(__file__).parent.parent
RAW = ROOT / "results" / "raw"
FN_COST, FP_COST = 14.0, 1.0
DEFAULT_THRESHOLD = 0.5
COLORS = {
    "random_forest": "#d62728",
    "knn": "#1f77b4",
    "logistic_regression": "#2ca02c",
    "decision_tree": "#9467bd",
}


def load():
    ys, ps, accs = {}, {}, {}
    for path in sorted(RAW.glob("fold-*.json")):
        rec = json.loads(path.read_text())
        for m in rec["models"]:
            name = m["model"]
            ys.setdefault(name, []).extend(m["y_true"])
            ps.setdefault(name, []).extend(m["y_prob"])
            accs.setdefault(name, []).append(m["metrics"]["accuracy"])
    return ys, ps, accs


def main():
    ys, ps, accs = load()
    mean_acc = {n: sum(v) / len(v) for n, v in accs.items()}
    mean_cost = {
        n: FN_COST * sum(1 for a, b in zip(ys[n], ps[n]) if a == 1 and b < DEFAULT_THRESHOLD)
        + FP_COST * sum(1 for a, b in zip(ys[n], ps[n]) if a == 0 and b >= DEFAULT_THRESHOLD)
        for n in ys
    }
    acc_rank = sorted(mean_acc, key=mean_acc.get, reverse=True)
    cost_rank = sorted(mean_cost, key=mean_cost.get)

    fig, axes = plt.subplots(1, 2, figsize=(10.5, 3.8), dpi=150)
    for ax, ranking, values, title, fmt in (
        (axes[0], acc_rank, mean_acc, "By mean accuracy (higher is better)", "{:.4f}"),
        (axes[1], cost_rank, mean_cost, "By expected cost at the 0.5 threshold, 14:1 (lower is better)", "{:.0f}"),
    ):
        names = list(reversed(ranking))  # rank 1 at top
        vals = [values[n] for n in names]
        ax.barh(names, vals, color=[COLORS[n] for n in names])
        for i, v in enumerate(vals):
            ax.text(v, i, " " + fmt.format(v), va="center", fontsize=8)
        ax.set_title(title, fontsize=9)
        ax.set_xticks([])
    fig.suptitle("The accuracy-best model (random forest) is cost-worst at the default threshold",
                 fontsize=10)
    fig.tight_layout()
    out = pathlib.Path(__file__).parent / "fig3-ranking-flip.png"
    fig.savefig(out)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
