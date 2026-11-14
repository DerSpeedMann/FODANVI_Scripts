"""
PlotCategories.py

Draw the per-category figures of the pre-trained models on COCO and on the
captures, which comparison.csv does not hold: it keeps one figure per run,
the per-category ones live in each run's tables/per_class_metrics.csv.

By default (--kind panels), one panel per dataset, COCO above the captures,
each with one group per category and one bar per model in the colors of the
PlotRuns figures, both panels on one shared axis: the categories are
categories, not a scale, so no line joins them. Written as
pretrained_categories_panels_<metric>.png.

--kind lines draws the earlier figure instead, one line per model and
dataset across the four categories, COCO dashed with hollow markers, the
captures solid, as pretrained_categories_lines_<metric>.png.

Usage:
    python src/Processing/PlotCategories.py
    python src/Processing/PlotCategories.py --metric map50
    python src/Processing/PlotCategories.py --kind lines
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

CATEGORIES = ("backpack", "bottle", "laptop", "mouse")
# Label as in comparison.csv, run folder stem, color as in sweep.json.
MODELS = (("rf-detr-large", "rfdetrl", "#1f77b4"),
          ("rtdetr-x", "rtdetrx", "#d62728"),
          ("yolo12x", "yolo12x", "#9467bd"))
DATASETS = (("coco", "COCO", "--"), ("real_nvg", "captures", "-"))
HEADER = {"map50": "mAP50", "map50_95": "mAP50-95"}


def per_class(runs: Path, stem: str, dataset: str, metric: str) -> dict:
    path = runs / f"val_{stem}_{dataset}" / "tables" / "per_class_metrics.csv"
    with open(path, newline="", encoding="utf-8") as fh:
        return {r["class"]: float(r[metric]) for r in csv.DictReader(fh)}


def panels(args, plt) -> int:
    """One panel per dataset, a bar per model in each category group."""
    values = {(label, dataset): per_class(args.runs, stem, dataset,
                                          args.metric)
              for label, stem, _ in MODELS for dataset, _, _ in DATASETS}
    for (label, dataset), v in values.items():
        print(f"{label:14} {dataset:9} "
              + " ".join(f"{c} {v[c]:.3f}" for c in CATEGORIES))
    top = max(v[c] for v in values.values() for c in CATEGORIES) * 1.08
    bar = 0.8 / len(MODELS)

    fig, axs = plt.subplots(len(DATASETS), 1, sharey=True,
                            figsize=(args.width, 3.0 * len(DATASETS)))
    for ax, (dataset, name, _) in zip(axs, DATASETS):
        for i, (label, _, color) in enumerate(MODELS):
            xs = [j - 0.4 + bar * (i + 0.5) for j in range(len(CATEGORIES))]
            ys = [values[(label, dataset)][c] for c in CATEGORIES]
            ax.bar(xs, ys, width=bar, color=color, label=label)
        ax.set_xticks(range(len(CATEGORIES)))
        ax.set_xticklabels(CATEGORIES, fontsize=8)
        ax.set_title(name, fontsize=9, loc="left")
        ax.set_ylabel(HEADER[args.metric])
        ax.set_ylim(0, top)
        ax.grid(axis="y", alpha=0.3)
        ax.set_axisbelow(True)
    axs[0].legend(fontsize=8, ncol=len(MODELS), loc="lower center",
                  bbox_to_anchor=(0.5, 1.12), frameon=False)
    fig.tight_layout()
    args.out.mkdir(parents=True, exist_ok=True)
    path = args.out / f"pretrained_categories_panels_{args.metric}.png"
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"wrote {path}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--runs", type=Path, default=Path("data/runs"))
    ap.add_argument("--out", type=Path, default=Path("data/results"))
    ap.add_argument("--metric", default="map50_95", choices=tuple(HEADER))
    ap.add_argument("--width", type=float, default=6.5)
    ap.add_argument("--kind", default="panels", choices=("panels", "lines"))
    args = ap.parse_args()

    import matplotlib
    matplotlib.use("Agg")
    from matplotlib import pyplot as plt

    if args.kind == "panels":
        return panels(args, plt)

    fig, ax = plt.subplots(figsize=(args.width, 4.5))
    xs = range(len(CATEGORIES))
    for label, stem, color in MODELS:
        for dataset, name, style in DATASETS:
            values = per_class(args.runs, stem, dataset, args.metric)
            ys = [values[c] for c in CATEGORIES]
            print(f"{label:14} {name:9} "
                  + " ".join(f"{c} {v:.3f}" for c, v in zip(CATEGORIES, ys)))
            ax.plot(xs, ys, marker="o", ms=5, lw=1.5, ls=style, color=color,
                    mfc=color if style == "-" else "white",
                    label=f"{label}, {name}")

    ax.set_xticks(list(xs))
    ax.set_xticklabels(CATEGORIES)
    ax.set_ylabel(HEADER[args.metric])
    ax.grid(alpha=0.3)
    ax.set_axisbelow(True)
    ax.legend(fontsize=8, ncol=3, loc="lower center",
              bbox_to_anchor=(0.5, 1.0), frameon=False)
    fig.tight_layout()
    args.out.mkdir(parents=True, exist_ok=True)
    path = args.out / f"pretrained_categories_lines_{args.metric}.png"
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
