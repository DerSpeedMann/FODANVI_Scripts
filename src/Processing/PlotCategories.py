"""
PlotCategories.py

Draw the per-category figures of the pre-trained models on COCO and on the
captures, which comparison.csv does not hold: it keeps one figure per run,
the per-category ones live in each run's tables/per_class_metrics.csv.

One line per model and dataset across the four categories, in the colors of
the PlotRuns figures: COCO dashed with hollow markers, the captures solid.
The categories are categories, not a scale; the line only makes a model's
run easy to follow, as in PlotRuns.

Usage:
    python src/Processing/PlotCategories.py
    python src/Processing/PlotCategories.py --metric map50
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


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--runs", type=Path, default=Path("data/runs"))
    ap.add_argument("--out", type=Path, default=Path("data/results"))
    ap.add_argument("--metric", default="map50_95", choices=tuple(HEADER))
    ap.add_argument("--width", type=float, default=6.5)
    args = ap.parse_args()

    import matplotlib
    matplotlib.use("Agg")
    from matplotlib import pyplot as plt

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
