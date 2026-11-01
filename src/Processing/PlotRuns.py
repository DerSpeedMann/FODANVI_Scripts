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

One figure per selection and metric:

    bars_<metric>.png      one group per dataset, one bar per model; with
                           "group": "model" in a plot entry, one group per
                           model, one bar per dataset
    lines_<metric>.png     with "kind": "lines" instead, one line per model
                           across the datasets in the order listed, with
                           "styles" giving each line its dash pattern

Models and datasets appear in the order of the patterns that pick them, so a
plot that names them one by one sets the order, and "colors" in a plot entry
gives the bars their colors in that order, which is how a comparison such as
v1 against v2 of one stage gets one hue in two shades.

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


def ordered(present: List[str], patterns: str) -> List[str]:
    """present in the order of the patterns that pick them, in the order
    given among those one pattern picks, the rest after."""
    out: List[str] = []
    for p in [p.strip() for p in patterns.split(",")
              if p.strip() and not p.strip().startswith("!")]:
        out += [v for v in present if fnmatch.fnmatch(v, p) and v not in out]
    return out + [v for v in present if v not in out]


def axes(rows: List[dict], datasets: str = "*", models: str = "*"
         ) -> Tuple[List[str], List[str], Dict[str, int]]:
    """Models and datasets in the order of the patterns that pick them.

    A plot that names them one by one so gets them in that order, which keeps
    a set beside the ones it is compared with rather than wherever its name
    sorts. Among the models one pattern picks, the smaller comes first.
    """
    sized = {r["model"]: int(r["weights_mb"]) for r in rows
             if r["weights_mb"] not in ("--", "")}
    by_size = sorted({r["model"] for r in rows},
                     key=lambda m: (sized.get(m, 1 << 30), m))
    return (ordered(by_size, models),
            ordered(sorted({r["dataset"] for r in rows}), datasets), sized)


def plot_bars(rows: List[dict], metric: str, path: Path,
              group: str = "dataset", order: str = "*",
              model_order: str = "*",
              colors: Optional[List[str]] = None) -> None:
    """One group per dataset, one bar per model, or the other way round
    with group="model". colors, when given, are the bars' in order."""
    import matplotlib
    matplotlib.use("Agg")
    from matplotlib import pyplot as plt

    models, datasets, sized = axes(rows, order, model_order)
    by = {(r["model"], r["dataset"]): r[metric] for r in rows}
    if group == "model":
        groups, bars = models, datasets
        value = lambda g, b: by.get((g, b), "")
        ticks = [f"{m}\n{sized[m]} MB" if m in sized else m for m in models]
    else:
        groups, bars = datasets, models
        value = lambda g, b: by.get((b, g), "")
        ticks = datasets
    width = 0.8 / max(len(bars), 1)
    cmap = plt.get_cmap("tab10" if len(bars) <= 10 else "tab20")

    fig, ax = plt.subplots(figsize=(max(7, 0.25 * len(groups) * len(bars) + 2), 4.5))
    for i, b in enumerate(bars):
        xs, ys = [], []
        for j, g in enumerate(groups):
            v = value(g, b)
            if v == "":
                continue        # a pair that was not run leaves a gap
            xs.append(j - 0.4 + width * (i + 0.5))
            ys.append(float(v))
        color = colors[i % len(colors)] if colors else cmap(i % cmap.N)
        ax.bar(xs, ys, width=width, label=b, color=color)

    ax.set_xticks(range(len(groups)))
    if group == "model":
        ax.set_xticklabels(ticks, fontsize=8)
    else:
        ax.set_xticklabels(ticks, rotation=30, ha="right", fontsize=8)
    ax.set_ylabel(HEADER[metric])
    ax.grid(axis="y", alpha=0.3)
    ax.set_axisbelow(True)
    # Above the axes rather than inside: inside, it covers whichever bars
    # happen to be tallest under it.
    ax.legend(fontsize=8, ncol=min(len(bars), 6), loc="lower center",
              bbox_to_anchor=(0.5, 1.0), frameon=False)
    fig.tight_layout()
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def plot_lines(rows: List[dict], metric: str, path: Path,
               order: str = "*", model_order: str = "*",
               colors: Optional[List[str]] = None,
               styles: Optional[List[str]] = None) -> None:
    """One line per model across the datasets, in the order listed.

    The datasets are categories, not a scale: the line only makes a model's
    run easy to follow from one set to the next, which is what a comparison
    of several models over the same sets needs.
    """
    import matplotlib
    matplotlib.use("Agg")
    from matplotlib import pyplot as plt

    models, datasets, _ = axes(rows, order, model_order)
    by = {(r["model"], r["dataset"]): r[metric] for r in rows}
    cmap = plt.get_cmap("tab10" if len(models) <= 10 else "tab20")

    fig, ax = plt.subplots(figsize=(max(7, 0.7 * len(datasets) + 2), 4.5))
    for i, m in enumerate(models):
        xs, ys = [], []
        for j, d in enumerate(datasets):
            v = by.get((m, d), "")
            if v == "":
                continue        # a pair that was not run leaves a gap
            xs.append(j)
            ys.append(float(v))
        color = colors[i % len(colors)] if colors else cmap(i % cmap.N)
        style = styles[i % len(styles)] if styles else "-"
        # A dashed line also gets hollow markers, so the two still tell
        # apart where the lines run on top of each other.
        ax.plot(xs, ys, marker="o", ms=5, lw=1.5, ls=style, color=color,
                mfc=color if style == "-" else "white", label=m)

    ax.set_xticks(range(len(datasets)))
    ax.set_xticklabels(datasets, rotation=30, ha="right", fontsize=8)
    ax.set_ylabel(HEADER[metric])
    ax.grid(alpha=0.3)
    ax.set_axisbelow(True)
    # As many columns as the width holds, about one per two datasets, so a
    # narrow plot wraps its legend rather than overhanging it.
    ax.legend(fontsize=8, ncol=min(len(models), max(2, len(datasets) // 2), 6),
              loc="lower center", bbox_to_anchor=(0.5, 1.0), frameon=False)
    fig.tight_layout()
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def draw(rows: List[dict], metric: str, out: Path, prefix: str = "",
         sweep: Optional[Path] = Path("sweep.json"),
         group: str = "dataset", order: str = "*", model_order: str = "*",
         colors: Optional[List[str]] = None, kind: str = "bars",
         styles: Optional[List[str]] = None) -> List[Path]:
    """The figure for a selection, limited to the sweep. Returns what was written."""
    rows = in_sweep(rows, sweep)
    out.mkdir(parents=True, exist_ok=True)
    tag = f"{prefix}_" if prefix else ""
    path = out / f"{tag}{kind}_{metric}.png"
    if kind == "lines":
        plot_lines(rows, metric, path, order, model_order, colors, styles)
    elif kind == "bars":
        plot_bars(rows, metric, path, group, order, model_order, colors)
    else:
        raise ValueError(f"plot '{prefix}' asks for unknown kind '{kind}'")
    return [path]


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
            written += draw(chosen, metric, out, p.get("prefix", ""), sweep,
                            p.get("group", "dataset"), p.get("datasets", "*"),
                            p.get("models", "*"), p.get("colors"),
                            p.get("kind", "bars"), p.get("styles"))
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
    for p in draw(rows, args.metric, args.out, args.prefix, sweep,
                  "dataset", args.datasets, args.models):
        print(f"wrote {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
