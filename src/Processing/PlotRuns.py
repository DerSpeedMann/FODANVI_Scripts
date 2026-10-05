"""
PlotRuns.py

Draw the comparison that CompareRuns.py tabulated.

CompareRuns writes every run it finds. That is the record, but it is not
always the picture worth looking at: the three yolo11s weights share an
architecture and differ only in training, so putting them beside the larger
models mixes "what does a bigger model buy" with "what does fine-tuning
buy". Selecting a subset here answers one question at a time.

    --models and --datasets take glob patterns, matched against the model
    and dataset columns of comparison.csv.

Two figures per run:

    bars_<metric>.png      one group per dataset, one bar per model
    models_<metric>.png    one point per model, ordered by parameter size,
                           one line per dataset

Usage:
    python PlotRuns.py                                  everything
    python PlotRuns.py --models "yolo11s*" --prefix finetune
    python PlotRuns.py --models "yolo12x,rtdetr-x,rf-detr-large" --prefix raw

Examples of the two the thesis wants:

    the fine-tuning question, one architecture trained three ways
        --models "yolo11s*" --prefix finetune

    the model question, the pre-trained models on their own
        --models "yolo12x,rtdetr-x,rf-detr-large" --prefix raw
"""

from __future__ import annotations

import argparse
import csv
import fnmatch
from pathlib import Path
from typing import Dict, List, Tuple

METRICS = ("precision", "recall", "map50", "map50_95")
HEADER = {"precision": "P", "recall": "R",
          "map50": "mAP50", "map50_95": "mAP50-95"}


def load_rows(path: Path) -> List[dict]:
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def select(rows: List[dict], models: str, datasets: str) -> List[dict]:
    """Keep rows whose model and dataset match any of the given patterns."""
    def match(value: str, patterns: str) -> bool:
        return any(fnmatch.fnmatch(value, p.strip())
                   for p in patterns.split(",") if p.strip())
    return [r for r in rows
            if match(r["model"], models) and match(r["dataset"], datasets)]


def axes(rows: List[dict]) -> Tuple[List[str], List[str], Dict[str, int]]:
    """Models ordered by parameter size, datasets alphabetical."""
    sized = {r["model"]: int(r["weights_mb"]) for r in rows
             if r["weights_mb"] not in ("--", "")}
    models = sorted({r["model"] for r in rows},
                    key=lambda m: (sized.get(m, 1 << 30), m))
    datasets = sorted({r["dataset"] for r in rows})
    return models, datasets, sized


def plot_bars(rows: List[dict], metric: str, path: Path) -> None:
    """One group per dataset, one bar per model."""
    import matplotlib
    matplotlib.use("Agg")
    from matplotlib import pyplot as plt

    models, datasets, _ = axes(rows)
    by = {(r["model"], r["dataset"]): r[metric] for r in rows}
    width = 0.8 / max(len(models), 1)
    cmap = plt.get_cmap("tab10")

    fig, ax = plt.subplots(figsize=(max(7, 1.4 * len(datasets)), 4.5))
    for i, m in enumerate(models):
        xs, ys = [], []
        for j, d in enumerate(datasets):
            v = by.get((m, d), "")
            if v == "":
                continue        # a pair that was not run leaves a gap
            xs.append(j - 0.4 + width * (i + 0.5))
            ys.append(float(v))
        ax.bar(xs, ys, width=width, label=m, color=cmap(i % 10))

    ax.set_xticks(range(len(datasets)))
    ax.set_xticklabels(datasets, rotation=30, ha="right", fontsize=8)
    ax.set_ylabel(HEADER[metric])
    ax.grid(axis="y", alpha=0.3)
    ax.set_axisbelow(True)
    ax.legend(fontsize=8, ncol=2)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def plot_by_model(rows: List[dict], metric: str, path: Path) -> None:
    """One point per model, ordered by parameter size, a line per dataset.

    The axis is the model, not its size on a continuous scale, because
    several models share a size: the fine-tuned weights are yolo11s
    architecture and weigh exactly what yolo11s weighs. Plotted against
    parameters they land on top of one another, and a line through them
    reads as a size trend when the spread is the effect of training.
    """
    import matplotlib
    matplotlib.use("Agg")
    from matplotlib import pyplot as plt

    models, datasets, sized = axes(rows)
    by = {(r["model"], r["dataset"]): r[metric] for r in rows}
    cmap = plt.get_cmap("tab10")

    fig, ax = plt.subplots(figsize=(max(6, 1.4 * len(models)), 4.8))
    for i, d in enumerate(datasets):
        xs, ys = [], []
        for j, m in enumerate(models):
            v = by.get((m, d), "")
            if v == "":
                continue
            xs.append(j)
            ys.append(float(v))
        if xs:
            ax.plot(xs, ys, "o-", color=cmap(i % 10), lw=1, ms=5,
                    label=d, alpha=0.85)

    ax.set_xticks(range(len(models)))
    ax.set_xticklabels(
        [f"{m}\n{sized[m]} MB" if m in sized else m for m in models],
        fontsize=8)
    ax.set_xlabel("model, ordered by parameter size")
    ax.set_ylabel(HEADER[metric])
    ax.grid(axis="y", alpha=0.3)
    ax.set_axisbelow(True)
    ax.legend(fontsize=8, ncol=2)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def draw(rows: List[dict], metric: str, out: Path, prefix: str = "") -> List[Path]:
    """Both figures for a selection. Returns what was written."""
    out.mkdir(parents=True, exist_ok=True)
    tag = f"{prefix}_" if prefix else ""
    bars = out / f"{tag}bars_{metric}.png"
    models = out / f"{tag}models_{metric}.png"
    plot_bars(rows, metric, bars)
    plot_by_model(rows, metric, models)
    return [bars, models]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--csv", type=Path,
                    default=Path("data/results/comparison.csv"))
    ap.add_argument("--out", type=Path, default=Path("data/results"))
    ap.add_argument("--models", default="*", help="glob(s), comma separated")
    ap.add_argument("--datasets", default="*", help="glob(s), comma separated")
    ap.add_argument("--metric", default="map50_95", choices=METRICS)
    ap.add_argument("--prefix", default="",
                    help="prepended to the file names, to keep a selection "
                         "from overwriting the default figures")
    args = ap.parse_args()

    if not args.csv.exists():
        print(f"{args.csv} does not exist; run CompareRuns.py first")
        return 1

    rows = select(load_rows(args.csv), args.models, args.datasets)
    if not rows:
        print(f"nothing matched models={args.models} datasets={args.datasets}")
        return 1

    models, datasets, _ = axes(rows)
    print(f"{len(rows)} runs: {len(models)} model(s) x {len(datasets)} dataset(s)")
    for p in draw(rows, args.metric, args.out, args.prefix):
        print(f"wrote {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
