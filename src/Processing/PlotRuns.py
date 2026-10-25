"""
PlotRuns.py

Draw the comparison that CompareRuns.py tabulated.

CompareRuns writes every run it finds. That is the record, but it is not
always the picture worth looking at: the three yolo11s weights share an
architecture and differ only in training, so putting them beside the larger
models mixes "what does a bigger model buy" with "what does fine-tuning
buy". Selecting a subset here answers one question at a time.

    --models and --datasets take glob patterns, matched against the model
    and dataset columns of comparison.csv; a pattern starting with ! excludes.

The csv holds every run ever made, including conversions and models since
dropped from the study. A figure shows only what sweep.json lists: a run is
drawn when its dataset is among the sweep's datasets and its model among the
sweep's weights. --all draws every run in the csv.

Two figures per run:

    bars_<metric>.png      one group per dataset, one bar per model
    models_<metric>.png    one point per model, ordered by parameter size,
                           one line per dataset

The figures worth keeping are named in the "plots" block of sweep.json,
each with a prefix, model and dataset globs and the metrics to draw, so
the whole set is redrawn by one command rather than retyped. CompareRuns.py
draws the same block after writing the csv.

Usage:
    python PlotRuns.py                                  every plot in sweep.json
    python PlotRuns.py --models "yolo11s*" --prefix test   one selection
"""

from __future__ import annotations

import argparse
import csv
import fnmatch
import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple

METRICS = ("precision", "recall", "map50", "map50_95")
HEADER = {"precision": "P", "recall": "R",
          "map50": "mAP50", "map50_95": "mAP50-95"}


def load_rows(path: Path) -> List[dict]:
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def select(rows: List[dict], models: str, datasets: str) -> List[dict]:
    """Keep rows whose model and dataset match any of the given patterns.

    A pattern starting with ! excludes what it matches, whatever else
    matched, so "real_nvg*,!*_original" is every real set but those.
    """
    def match(value: str, patterns: str) -> bool:
        pats = [p.strip() for p in patterns.split(",") if p.strip()]
        if any(fnmatch.fnmatch(value, p[1:]) for p in pats if p.startswith("!")):
            return False
        return any(fnmatch.fnmatch(value, p) for p in pats if not p.startswith("!"))
    return [r for r in rows
            if match(r["model"], models) and match(r["dataset"], datasets)]


def sweep_selection(path: Path) -> Optional[Tuple[set, set]]:
    """(datasets, models) the sweep covers, models named by weight stem.

    A model in sweep.json is a key with a weight file, and comparison.csv
    names a model by its weight, so the weight's stem is what is compared.
    """
    if not path.exists():
        return None
    cfg = json.loads(path.read_text(encoding="utf-8"))
    datasets = set(cfg.get("datasets", []))
    models = {Path(m["weight"]).stem for m in cfg.get("models", {}).values()}
    return datasets, models


def in_sweep(rows: List[dict], sweep: Optional[Path]) -> List[dict]:
    """Rows the sweep lists; all of them when there is no sweep to go by."""
    selection = sweep_selection(sweep) if sweep else None
    if selection is None:
        return rows
    datasets, models = selection
    return [r for r in rows
            if r["dataset"] in datasets and r["model"] in models]


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


def draw(rows: List[dict], metric: str, out: Path, prefix: str = "",
         sweep: Optional[Path] = Path("sweep.json")) -> List[Path]:
    """Both figures for a selection, limited to the sweep. Returns what was written."""
    rows = in_sweep(rows, sweep)
    out.mkdir(parents=True, exist_ok=True)
    tag = f"{prefix}_" if prefix else ""
    bars = out / f"{tag}bars_{metric}.png"
    models = out / f"{tag}models_{metric}.png"
    plot_bars(rows, metric, bars)
    plot_by_model(rows, metric, models)
    return [bars, models]


def configured(sweep: Path) -> List[dict]:
    """The "plots" block of sweep.json, empty when there is none."""
    if not sweep.exists():
        return []
    return json.loads(sweep.read_text(encoding="utf-8")).get("plots", [])


def draw_configured(rows: List[dict], out: Path,
                    sweep: Path = Path("sweep.json")) -> List[Path]:
    """Every plot sweep.json names. Returns what was written.

    A plot whose selection matches nothing is reported and skipped rather
    than failing the rest, since a model or dataset can leave the sweep
    while a plot still names it.
    """
    written = []
    for p in configured(sweep):
        chosen = select(rows, p.get("models", "*"), p.get("datasets", "*"))
        if not in_sweep(chosen, sweep):
            print(f"  plot '{p.get('prefix', '')}' matched nothing, skipped")
            continue
        for metric in p.get("metrics", ["map50_95"]):
            if metric not in METRICS:
                raise ValueError(f"plot '{p.get('prefix', '')}' asks for "
                                 f"unknown metric '{metric}'")
            written += draw(chosen, metric, out, p.get("prefix", ""), sweep)
    return written


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--csv", type=Path,
                    default=Path("data/results/comparison.csv"))
    ap.add_argument("--out", type=Path, default=Path("data/results"))
    ap.add_argument("--models", help="glob(s), comma separated; without "
                    "--models or --datasets every plot in sweep.json is drawn")
    ap.add_argument("--datasets", help="glob(s), comma separated")
    ap.add_argument("--metric", default="map50_95", choices=METRICS)
    ap.add_argument("--prefix", default="",
                    help="prepended to the file names, to keep a selection "
                         "from overwriting the default figures")
    ap.add_argument("--sweep", type=Path, default=Path("sweep.json"),
                    help="draw only the datasets and models it lists")
    ap.add_argument("--all", action="store_true",
                    help="draw every run in the csv, listed in the sweep or not")
    args = ap.parse_args()
    sweep = None if args.all else args.sweep

    if not args.csv.exists():
        print(f"{args.csv} does not exist; run CompareRuns.py first")
        return 1

    if args.models is None and args.datasets is None:
        if not configured(args.sweep):
            print(f"{args.sweep} names no plots; give --models or --datasets")
            return 1
        for p in draw_configured(load_rows(args.csv), args.out, args.sweep):
            print(f"wrote {p}")
        return 0

    args.models = args.models or "*"
    args.datasets = args.datasets or "*"
    rows = in_sweep(select(load_rows(args.csv), args.models, args.datasets),
                    sweep)
    if not rows:
        print(f"nothing matched models={args.models} datasets={args.datasets}")
        return 1

    models, datasets, _ = axes(rows)
    print(f"{len(rows)} runs: {len(models)} model(s) x {len(datasets)} dataset(s)")
    for p in draw(rows, args.metric, args.out, args.prefix, sweep):
        print(f"wrote {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
