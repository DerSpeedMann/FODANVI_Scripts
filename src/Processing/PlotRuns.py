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
    panels_<metric>.png    with "kind": "panels", grouped bars as above but
                           split into panels stacked on one shared axis,
                           "panels" naming each panel's title and datasets;
                           a model styled "--" gets hollow, hatched bars
    nested_<metric>.png    with "kind": "nested", panels whose bars overlap:
                           "slots" lists the models sharing one slot, the
                           first drawn as a wide light bar, the second as a
                           narrow full one inside it, so two stages of one
                           training take the room of one bar
    heatmap_<metric>.png   with "kind": "heatmap", one row per dataset and
                           one column per model, each cell colored and
                           labeled with its figure; "panels" groups the rows,
                           with a rule between groups; a figure that can be
                           negative (a gain or change) gets a diverging scale
                           centered on zero

Models and datasets appear in the order of the patterns that pick them, so a
plot that names them one by one sets the order, and "colors" in a plot entry
gives the bars their colors in that order, which is how a comparison such as
v1 against v2 of one stage gets one hue in two shades. A lines plot also
takes "width" in inches, so a figure meant for a page can be drawn narrow,
and "baseline", a model whose figure is subtracted from every other model's
on the same dataset, so the lines show the gain over it; the baseline must
be among the plot's models and is not drawn itself. A plot with "pairs"
instead of "datasets" draws, per pair of a label, a "dataset" and the dataset
it is taken against ("minus"), each model's difference between the two, with
"change" naming it on the axis.

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


def against(rows: List[dict], baseline: str, metric: str) -> List[dict]:
    """Each model's figure minus the baseline model's on the same dataset.

    The baseline itself is dropped, and a dataset it was not run on drops
    out, since there is nothing to subtract.
    """
    base = {r["dataset"]: float(r[metric]) for r in rows
            if r["model"] == baseline and r[metric] not in ("--", "")}
    return [{**r, metric: f"{float(r[metric]) - base[r['dataset']]:.4f}"}
            for r in rows
            if r["model"] != baseline and r["dataset"] in base
            and r[metric] not in ("--", "")]


def plot_lines(rows: List[dict], metric: str, path: Path,
               order: str = "*", model_order: str = "*",
               colors: Optional[List[str]] = None,
               styles: Optional[List[str]] = None,
               width: Optional[float] = None,
               change: Optional[str] = None) -> None:
    """One line per model across the datasets, in the order listed.

    The datasets are categories, not a scale: the line only makes a model's
    run easy to follow from one set to the next, which is what a comparison
    of several models over the same sets needs.

    width, when given, is the figure's in inches. The dataset names then
    stand steeper, since at a narrow width a shallow slant runs each into
    the next.

    change, when given, says what the figures are a change of, such as
    "gain over yolo11s" (see against) or "change from denoising" (see
    draw_pairs): the axis says so and a line marks zero.
    """
    import matplotlib
    matplotlib.use("Agg")
    from matplotlib import pyplot as plt

    models, datasets, _ = axes(rows, order, model_order)
    by = {(r["model"], r["dataset"]): r[metric] for r in rows}
    cmap = plt.get_cmap("tab10" if len(models) <= 10 else "tab20")

    fig, ax = plt.subplots(
        figsize=(width or max(7, 0.7 * len(datasets) + 2), 4.5))
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
    if width:
        ax.set_xticklabels(datasets, rotation=45, ha="right",
                           rotation_mode="anchor", fontsize=8)
    else:
        ax.set_xticklabels(datasets, rotation=30, ha="right", fontsize=8)
    if change:
        ax.set_ylabel(f"{HEADER[metric]} {change}")
        ax.axhline(0, color="black", lw=0.8)
    else:
        ax.set_ylabel(HEADER[metric])
    ax.grid(alpha=0.3)
    ax.set_axisbelow(True)
    # As many columns as the width holds, about one per two datasets or one
    # per two inches of a set width, so a narrow plot wraps its legend
    # rather than overhanging it.
    cols = int(width // 2) if width else len(datasets) // 2
    ax.legend(fontsize=8, ncol=min(len(models), max(2, cols), 6),
              loc="lower center", bbox_to_anchor=(0.5, 1.0), frameon=False)
    fig.tight_layout()
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def picked(present: List[str], patterns: str) -> List[str]:
    """Those of present that the patterns match, in the patterns' order;
    unlike ordered, what no pattern matches is left out."""
    out: List[str] = []
    for p in [p.strip() for p in patterns.split(",") if p.strip()]:
        out += [v for v in present if fnmatch.fnmatch(v, p) and v not in out]
    return out


def plot_panels(rows: List[dict], metric: str, path: Path,
                panels: Optional[List[dict]] = None,
                order: str = "*", model_order: str = "*",
                colors: Optional[List[str]] = None,
                styles: Optional[List[str]] = None,
                width: Optional[float] = None,
                change: Optional[str] = None,
                slots: Optional[List[List[str]]] = None,
                labels: Optional[Dict[str, str]] = None) -> None:
    """Grouped bars, one group per dataset and one bar per model, split
    into panels stacked one above the other.

    With slots, the bars of a group overlap instead (the "nested" kind):
    each slot is a list of one or two models sharing one position, the
    first drawn as a wide bar in a light shade of its color, the second as
    a narrow bar in the full color inside it. A slot of one model is a
    plain bar. Models in no slot are not drawn. labels, when given, names
    a model in the legend in place of its run name.

    The datasets are categories, so no line joins them; splitting them into
    panels keeps the number of bars per row low enough for a page width.
    Each panel is a dict of a "title" and "datasets", comma separated
    patterns matched against the datasets drawn (or the labels of columns
    and pairs), in the order given; a dataset may stand in more than one
    panel, as a reference does. Without panels, one panel holds them all.

    All panels share the value axis, so bar heights compare across them.
    A model styled "--" (see styles) gets a hollow, hatched bar, the
    counterpart of the hollow marker of the lines plot. change works as in
    plot_lines: the axis says so and a line marks zero.
    """
    import matplotlib
    matplotlib.use("Agg")
    from matplotlib import pyplot as plt

    models, datasets, _ = axes(rows, order, model_order)
    by = {(r["model"], r["dataset"]): float(r[metric]) for r in rows
          if r[metric] not in ("--", "")}
    if not panels:
        panels = [{"title": "", "datasets": ",".join(datasets)}]
    built = [(p.get("title", ""), picked(datasets, p["datasets"]))
             for p in panels]
    for title, ds in built:
        if not ds:
            print(f"  {path.name}: panel '{title}' matched nothing")
    built = [(t, ds) for t, ds in built if ds]
    if not built or not by:
        print(f"  {path.name}: nothing to draw, skipped")
        return
    cmap = plt.get_cmap("tab10" if len(models) <= 10 else "tab20")
    color_of = {m: colors[i % len(colors)] if colors else cmap(i % cmap.N)
                for i, m in enumerate(models)}
    name = (lambda m: labels.get(m, m)) if labels else (lambda m: m)
    if slots:
        slots = [[m for m in s if m in models] for s in slots]
        slots = [s for s in slots if s]
        models = [m for s in slots for m in s]
    bar = 0.8 / max(len(slots) if slots else len(models), 1)

    shown = [by[(m, d)] for _, ds in built for d in ds for m in models
             if (m, d) in by]
    lo, hi = min(0.0, min(shown)), max(0.0, max(shown))
    pad = 0.08 * (hi - lo)

    fig, axs = plt.subplots(len(built), 1, sharey=True, squeeze=False,
                            figsize=(width or 6.5, 3.0 * len(built)))
    def values(m: str, ds: List[str], k: int):
        """x and y of model m's bars at slot (or bar) position k; a pair
        that was not run leaves a gap."""
        xs = [j - 0.4 + bar * (k + 0.5) for j, d in enumerate(ds)
              if (m, d) in by]
        return xs, [by[(m, d)] for d in ds if (m, d) in by]

    for ax, (title, ds) in zip(axs[:, 0], built):
        if slots:
            for k, slot in enumerate(slots):
                for depth, m in enumerate(slot[:2]):
                    xs, ys = values(m, ds, k)
                    color = color_of[m]
                    if depth == 0 and len(slot) > 1:
                        ax.bar(xs, ys, width=bar * 0.95, label=name(m),
                               color=light(color), edgecolor=color, lw=0.8)
                    else:
                        ax.bar(xs, ys, width=bar * (0.45 if depth else 0.95),
                               label=name(m), color=color)
        for i, m in enumerate([] if slots else models):
            xs, ys = values(m, ds, i)
            color = color_of[m]
            hollow = bool(styles) and styles[i % len(styles)] != "-"
            ax.bar(xs, ys, width=bar, label=name(m),
                   color="white" if hollow else color, edgecolor=color,
                   linewidth=1.0 if hollow else 0,
                   hatch="////" if hollow else None)
        ax.set_xticks(range(len(ds)))
        ax.set_xticklabels(ds, rotation=20, ha="right",
                           rotation_mode="anchor", fontsize=8)
        if title:
            ax.set_title(title, fontsize=9, loc="left")
        if change:
            ax.set_ylabel(f"{HEADER[metric]} {change}")
            ax.axhline(0, color="black", lw=0.8)
        else:
            ax.set_ylabel(HEADER[metric])
        ax.set_ylim(lo - pad if lo < 0 else 0, hi + pad)
        ax.grid(axis="y", alpha=0.3)
        ax.set_axisbelow(True)
    fig.tight_layout()
    # Above the panels rather than inside: inside, it covers whichever bars
    # happen to be tallest under it. Centered on the figure, not the axes,
    # so long names overhang neither side; at most four columns, five
    # models as three over two rather than four over one.
    # Nested slots go one per column, wide above narrow, so each column of
    # the legend reads as one slot.
    n = len(models)
    handles, names = axs[0, 0].get_legend_handles_labels()
    if slots:
        pad_to = max(len(s) for s in slots)
        cols, k = [], 0
        for s in slots:
            cols.append(list(range(k, k + len(s))) + [None] * (pad_to - len(s)))
            k += len(s)
        from matplotlib.patches import Patch
        blank = Patch(visible=False)
        order_ = [c[r] for c in cols for r in range(pad_to)]
        handles = [handles[i] if i is not None else blank for i in order_]
        names = [names[i] if i is not None else "" for i in order_]
        ncol = len(slots)
    else:
        ncol = n if n <= 4 else -(-n // 2) if n <= 8 else 4
    fig.legend(handles, names, fontsize=8, ncol=ncol,
               loc="lower center", bbox_to_anchor=(0.5, 1.0),
               frameon=False)
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def light(color, share: float = 0.35) -> Tuple[float, float, float]:
    """color mixed with white, share of it kept: the wide bar of a slot."""
    from matplotlib.colors import to_rgb
    return tuple(1 - share + share * c for c in to_rgb(color))


def plot_heatmap(rows: List[dict], metric: str, path: Path,
                 panels: Optional[List[dict]] = None,
                 order: str = "*", model_order: str = "*",
                 width: Optional[float] = None,
                 change: Optional[str] = None,
                 labels: Optional[Dict[str, str]] = None) -> None:
    """One row per dataset, one column per model, each cell colored and
    labeled with the model's figure on that dataset.

    For a figure set too large for bars, such as a gain over a baseline on
    every dataset: every value stays readable as a number, the color only
    guides the eye. panels, as in plot_panels, sets the rows and their
    order, a rule between one panel's rows and the next; without panels,
    the datasets in the order listed. Where a figure can be negative (with
    change, or when any value is), the scale diverges from zero, blue for a
    gain and red for a loss; otherwise it runs over the range shown.
    labels names a model's column in place of its run name.

    With more models than datasets, the grid turns: one row per model and
    one column per dataset, the rules between panels then vertical, so the
    cells stay wide enough for their figures.
    """
    import matplotlib
    matplotlib.use("Agg")
    from matplotlib import pyplot as plt
    from matplotlib.colors import TwoSlopeNorm
    import numpy as np

    models, datasets, _ = axes(rows, order, model_order)
    by = {(r["model"], r["dataset"]): float(r[metric]) for r in rows
          if r[metric] not in ("--", "")}
    groups = [picked(datasets, p["datasets"]) for p in panels] \
        if panels else [datasets]
    groups = [g for g in groups if g]
    ds = [d for g in groups for d in g]
    if not ds or not by:
        print(f"  {path.name}: nothing to draw, skipped")
        return
    grid = np.array([[by.get((m, d), np.nan) for m in models] for d in ds])

    signed = bool(change) or np.nanmin(grid) < 0
    if signed:
        lim = float(np.nanmax(np.abs(grid)))
        cmap, norm = "RdBu", TwoSlopeNorm(0, -lim, lim)
        dark = lambda v: abs(v) > 0.6 * lim
        fmt = "{:+.3f}"
    else:
        lo, hi = float(np.nanmin(grid)), float(np.nanmax(grid))
        cmap, norm = "viridis", matplotlib.colors.Normalize(lo, hi)
        dark = lambda v: v < (lo + hi) / 2
        fmt = "{:.3f}"

    names = [labels.get(m, m) if labels else m for m in models]
    turned = len(models) > len(ds)
    if turned:
        grid, rows_, cols_ = grid.T, names, ds
        size = (width or 6.5, 0.38 * len(models) + 2.2)
    else:
        rows_, cols_ = ds, names
        size = (width or 5.2, 0.28 * len(ds) + 1.4)

    fig, ax = plt.subplots(figsize=size)
    im = ax.imshow(grid, cmap=cmap, norm=norm, aspect="auto")
    for i in range(len(rows_)):
        for j in range(len(cols_)):
            v = grid[i, j]
            if not np.isnan(v):
                ax.text(j, i, fmt.format(v), ha="center", va="center",
                        fontsize=7.5, color="white" if dark(v) else "black")
    edge = -0.5
    for g in groups[:-1]:
        edge += len(g)
        (ax.axvline if turned else ax.axhline)(edge, color="black", lw=1.2)
    ax.set_yticks(range(len(rows_)))
    ax.set_yticklabels(rows_, fontsize=8)
    ax.set_xticks(range(len(cols_)))
    ax.set_xticklabels(cols_, rotation=25, ha="left", rotation_mode="anchor",
                       fontsize=8)
    ax.xaxis.tick_top()
    ax.tick_params(length=0)
    for s in ax.spines.values():
        s.set_visible(False)
    cb = fig.colorbar(im, ax=ax, fraction=0.05, pad=0.03)
    cb.set_label(f"{HEADER[metric]} {change}" if change else HEADER[metric],
                 fontsize=8)
    cb.ax.tick_params(labelsize=7)
    fig.tight_layout()
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def draw(rows: List[dict], metric: str, out: Path, prefix: str = "",
         sweep: Optional[Path] = Path("sweep.json"),
         group: str = "dataset", order: str = "*", model_order: str = "*",
         colors: Optional[List[str]] = None, kind: str = "bars",
         styles: Optional[List[str]] = None,
         width: Optional[float] = None,
         baseline: Optional[str] = None,
         change: Optional[str] = None,
         panels: Optional[List[dict]] = None,
         slots: Optional[List[List[str]]] = None,
         labels: Optional[Dict[str, str]] = None) -> List[Path]:
    """The figure for a selection, limited to the sweep. Returns what was
    written. With a baseline, each model is drawn as its gain over it;
    change labels rows that already hold a change (see draw_pairs);
    panels splits a "panels" or "nested" plot and groups the rows of a
    "heatmap"; slots pairs the models of a "nested" plot (see
    plot_panels); labels renames models in legend or columns."""
    rows = in_sweep(rows, sweep)
    if baseline:
        rows = against(rows, baseline, metric)
        change = f"gain over {baseline}"
    out.mkdir(parents=True, exist_ok=True)
    tag = f"{prefix}_" if prefix else ""
    path = out / f"{tag}{kind}_{metric}.png"
    if kind == "lines":
        plot_lines(rows, metric, path, order, model_order, colors, styles,
                   width, change)
    elif kind == "panels":
        plot_panels(rows, metric, path, panels, order, model_order, colors,
                    styles, width, change, labels=labels)
    elif kind == "nested":
        if not slots:
            raise ValueError(f"plot '{prefix}' is nested but has no slots")
        plot_panels(rows, metric, path, panels, order, model_order, colors,
                    styles, width, change, slots, labels)
    elif kind == "heatmap":
        plot_heatmap(rows, metric, path, panels, order, model_order, width,
                     change, labels)
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


def draw_columns(rows: List[dict], p: dict, out: Path,
                 sweep: Path) -> List[Path]:
    """A plot whose points are "columns": each a label and dataset patterns,
    the point of a model being its highest figure over the matching sets.

    This is how a model's best preprocessing goes beside its unprocessed
    figure when the best configuration differs from model to model. Which
    set gave each point is printed, so the text can name it.
    """
    written = []
    models = p.get("models", "*")
    for metric in p.get("metrics", ["map50_95"]):
        built = []
        for col in p["columns"]:
            pool = in_sweep(select(rows, models, col["datasets"]), sweep)
            best: Dict[str, dict] = {}
            for r in pool:
                if r["model"] not in best or \
                        float(r[metric]) > float(best[r["model"]][metric]):
                    best[r["model"]] = r
            for m, r in best.items():
                built.append({**r, "dataset": col["label"]})
                print(f"  {p.get('prefix', '')}: {col['label']}, {m}: "
                      f"{r['dataset']} {float(r[metric]):.3f}")
        written += draw(built, metric, out, p.get("prefix", ""), None,
                        "dataset", ",".join(c["label"] for c in p["columns"]),
                        models, p.get("colors"), p.get("kind", "lines"),
                        p.get("styles"), p.get("width"),
                        panels=p.get("panels"), slots=p.get("slots"),
                        labels=p.get("labels"))
    return written


def draw_pairs(rows: List[dict], p: dict, out: Path,
               sweep: Path) -> List[Path]:
    """A plot whose points are "pairs": each a label, a dataset and the
    dataset it is taken against ("minus"), the point of a model being the
    difference of its two figures.

    This is how the change a preprocessing step brings goes beside the
    change it brings on another set, when the sets it starts from differ.
    A model that lacks either run of a pair leaves a gap.
    """
    written = []
    models = p.get("models", "*")
    pool = in_sweep(select(rows, models, "*"), sweep)
    for metric in p.get("metrics", ["map50_95"]):
        by = {(r["model"], r["dataset"]): r for r in pool
              if r[metric] not in ("--", "")}
        built = []
        for pair in p["pairs"]:
            for m in {r["model"] for r in pool}:
                a = by.get((m, pair["dataset"]))
                b = by.get((m, pair["minus"]))
                if a is None or b is None:
                    continue
                diff = float(a[metric]) - float(b[metric])
                built.append({**a, "dataset": pair["label"],
                              metric: f"{diff:.4f}"})
        written += draw(built, metric, out, p.get("prefix", ""), None,
                        "dataset", ",".join(c["label"] for c in p["pairs"]),
                        models, p.get("colors"), p.get("kind", "lines"),
                        p.get("styles"), p.get("width"), None,
                        p.get("change", "change"), p.get("panels"),
                        p.get("slots"), p.get("labels"))
    return written


def draw_configured(rows: List[dict], out: Path,
                    sweep: Path = Path("sweep.json")) -> List[Path]:
    """Every plot sweep.json names. Returns what was written.

    A plot whose selection matches nothing is reported and skipped rather
    than failing the rest, since a model or dataset can leave the sweep
    while a plot still names it.
    """
    written = []
    for p in configured(sweep):
        if "columns" in p:
            written += draw_columns(rows, p, out, sweep)
            continue
        if "pairs" in p:
            written += draw_pairs(rows, p, out, sweep)
            continue
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
                            p.get("kind", "bars"), p.get("styles"),
                            p.get("width"), p.get("baseline"),
                            panels=p.get("panels"), slots=p.get("slots"),
                            labels=p.get("labels"))
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
