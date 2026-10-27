"""
CompareRuns.py

Collect the headline metrics of every validation run into one table, for
comparing models against each other and against the conversions.

Every folder under data/runs/ is included. What a run was is read from the run
itself, from the Model and Data lines all three validation scripts print
into logs/console.log, so a run stays readable after the config that
produced it has moved on, and nothing here has to be told what to ignore.
The folder name is the fallback when a log has neither line.

Each run folder already holds tables/per_class_metrics.csv, written by the
validation script. This reads the "all" row out of each and writes:

    comparison.csv          one row per run, long form
    matrix_<metric>.csv     a dataset by model grid of one metric

and, unless --no-plots, every figure the "plots" block of sweep.json names,
drawn by PlotRuns.py. That script takes the same csv and will draw any subset of
it, which is what to reach for when a figure should answer one question
rather than show every run at once.

When sweep.json has a "classes" list, every run is scored on those classes
only: each metric is the mean of their per-class values, which is how the
"all" row is formed in the first place, so a set that contains only those
classes reads the same either way. This is what makes COCO comparable with
the real captures, which hold four classes, where the "all" row of a COCO run
averages eighty. Instances are summed over the classes; images stays the
number of images scored, since every image can produce a false positive.
--all-classes reports the "all" row instead.

A validation run with no tables is named rather than skipped quietly: an
absent row in a thesis table should be visible here first. Prediction runs
live in the same folder and are counted separately, since they have no
ground truth and so nothing to compare.

Usage:
    python CompareRuns.py [--runs data/runs] [--out data/results]
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

METRICS = ("precision", "recall", "map50", "map50_95")
HEADER = {"precision": "P", "recall": "R",
          "map50": "mAP50", "map50_95": "mAP50-95"}


def identify(run: Path) -> Tuple[str, str, str]:
    """What model and dataset a run was, from its own log.

    The weight file names the model and the yaml names the dataset, both as
    the validators recorded them, which beats taking apart a folder name
    where model and dataset each contain underscores. The weight's own file
    name comes back too, so its size can be looked up.
    """
    log = run / "logs" / "console.log"
    model = dataset = weight = ""
    if log.exists():
        text = log.read_text(encoding="utf-8", errors="replace")[:4000]
        m = re.search(r"^Model:\s*(\S+)", text, re.M)
        d = re.search(r"^Data:\s*(\S+)", text, re.M)
        if m:
            weight = Path(m.group(1).replace("\\", "/")).name
            model = Path(weight).stem
        if d:
            dataset = Path(d.group(1).replace("\\", "/")).stem
    if not model or not dataset:
        # No log, or an older one: fall back to the folder's own name.
        stem = run.name[4:] if run.name.startswith("val_") else run.name
        model = model or stem
        dataset = dataset or "?"
    return model, dataset, weight


SIZES = "weight_sizes.csv"


def _tensor_bytes(obj, seen=None) -> int:
    """Bytes of tensor data reachable from obj, each tensor counted once."""
    import torch

    if seen is None:
        seen = set()
    if torch.is_tensor(obj):
        if id(obj) in seen:
            return 0
        seen.add(id(obj))
        return obj.numel() * obj.element_size()
    if isinstance(obj, dict):
        return sum(_tensor_bytes(v, seen) for v in obj.values())
    if isinstance(obj, (list, tuple, set)):
        return sum(_tensor_bytes(v, seen) for v in obj)
    if hasattr(obj, "state_dict"):
        try:
            return _tensor_bytes(obj.state_dict(), seen)
        except Exception:
            return 0
    return 0


# State-dict entries that are buffers rather than parameters. A module can
# be asked which is which; a bare OrderedDict cannot, so these are named.
_BUFFER_SUFFIXES = ("num_batches_tracked", "running_mean", "running_var")


def _param_count(obj) -> Optional[int]:
    """Parameters, which is what a published parameter count means.

    Not the same as the number of tensors in the file. A state dict also
    carries BatchNorm buffers, and counting those would overstate the model.
    Where the checkpoint holds a module the distinction is exact, since
    parameters() excludes buffers by definition; where it holds a plain
    OrderedDict the buffers are dropped by name instead.
    """
    if hasattr(obj, "parameters"):
        try:
            return sum(p.numel() for p in obj.parameters())
        except Exception:
            return None
    if hasattr(obj, "items"):
        try:
            import torch
            return sum(v.numel() for k, v in obj.items()
                       if torch.is_tensor(v) and not k.endswith(_BUFFER_SUFFIXES))
        except Exception:
            return None
    return None


def _weights_info(path: Path) -> Optional[Tuple[int, Optional[int]]]:
    """(bytes of parameter data, parameter count), read in one load.

    A released Ultralytics checkpoint is the model and nothing else, so its
    file size is its weight size. A training checkpoint is not: RF-DETR's is
    1572 MB on disk against 542 MB of parameters, the rest Adam state, and
    the fine-tuned yolo11s weights are 38 MB against 18 MB for the same
    reason. Comparing file sizes across the two compares different things.

    The count is the figure published leaderboards quote, so it is the one
    that can be checked against them, where a size in MB cannot: it moves
    with the dtype the checkpoint happens to be stored in. The two fine-tuned
    yolo11s files both count 9,458,752, the same as the yolo11s they came
    from, which is the check that fine-tuning left the architecture alone.

    Those two keep their model under `ema` with `model` set to None, so the
    keys are tried in order and the first that is actually populated wins.
    """
    try:
        import torch
        ck = torch.load(path, map_location="cpu", weights_only=False)
    except Exception:
        return None
    obj = ck
    if isinstance(ck, dict):
        for key in ("model", "ema", "state_dict"):
            if ck.get(key) is not None:
                obj = ck[key]
                break
    return _tensor_bytes(obj), _param_count(obj)


def load_sizes(models_dir: Path) -> Dict[str, Dict[str, int]]:
    """The recorded sizes, which are versioned and may outlive the weights.

    No weight file is in the repository: the pre-trained ones are downloaded
    and the fine-tuned ones come with the capture archive. Reading a 1.5 GB
    checkpoint to report on it also costs more than the report. So the
    answer is written down, keyed on the file size, which survives a clone
    where a timestamp would not.
    """
    f = models_dir / SIZES
    out: Dict[str, Dict[str, int]] = {}
    if not f.exists():
        return out
    with open(f, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            try:
                rec = {"bytes": int(row["bytes"]),
                       "weights_bytes": int(row["weights_bytes"])}
            except (KeyError, ValueError):
                continue
            # Added after the first records were written, so a row without it
            # is not an error: it is re-measured when the file is at hand.
            try:
                rec["params"] = int(row["params"])
            except (KeyError, ValueError, TypeError):
                pass
            out[row["file"]] = rec
    return out


def save_sizes(models_dir: Path, sizes: Dict[str, Dict[str, int]]) -> None:
    f = models_dir / SIZES
    try:
        with open(f, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["file", "bytes", "weights_bytes", "params"])
            for name in sorted(sizes):
                rec = sizes[name]
                w.writerow([name, rec["bytes"], rec["weights_bytes"],
                            rec.get("params", "")])
    except OSError:
        pass


def weight_sizes(weight: str, models_dir: Path,
                 sizes: Dict[str, Dict[str, int]],
                 unknown: set) -> Tuple[str, str, str]:
    """(file MB, weights MB, parameters), measured if here, recorded if not.

    `sizes` is updated in place when a measurement is taken and `unknown`
    collects any weight that could be neither measured nor looked up, so the
    caller writes the record and reports the gaps once at the end.
    """
    if not weight:
        return "--", "--", "--"

    f = models_dir / weight
    known = sizes.get(weight)

    if f.exists():
        n = f.stat().st_size
        # Re-read when the file changed, and also when the record predates
        # the parameter column, so an old csv fills itself in rather than
        # reporting a dash next to a file that is sitting right there.
        if not known or known["bytes"] != n or "params" not in known:
            info = _weights_info(f)
            if info is not None:
                wb, pc = info
                rec = {"bytes": n, "weights_bytes": wb}
                if pc is not None:
                    rec["params"] = pc
                sizes[weight] = rec
                known = rec
        file_bytes = n
    elif known:
        file_bytes = known["bytes"]
    else:
        # Neither here nor written down, so the row goes out with dashes and
        # the caller is told which file would fix it.
        unknown.add(weight)
        return "--", "--", "--"

    # Rounded to the nearest MB, as in the weight table in the appendix.
    wb = known["weights_bytes"] if known else None
    pc = known.get("params") if known else None
    return (str(round(file_bytes / 1_000_000)),
            "--" if wb is None else str(round(wb / 1_000_000)),
            "--" if pc is None else str(pc))


def is_prediction(run: Path) -> bool:
    """True for a prediction run, which has nothing to compare.

    data/runs/ holds both. A prediction has no ground truth and so no
    metrics, and reporting it as a validation with no tables would read as
    a run that failed. The predict scripts head their log with the word, so
    the run says which it is.
    """
    log = run / "logs" / "console.log"
    if not log.exists():
        return False
    head = log.read_text(encoding="utf-8", errors="replace")[:400]
    return "PREDICTION" in head


def sweep_classes(path: Path) -> List[str]:
    """The "classes" list of sweep.json, empty when there is none."""
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8")).get("classes", [])


def read_overall(run: Path, classes: List[str]) -> Optional[Dict[str, str]]:
    """The 'all' row of a run's per-class table, or its mean over `classes`.

    A class missing from the table has no instances in that dataset and so
    no AP to average; it is left out of the mean rather than counted as zero.
    """
    table = run / "tables" / "per_class_metrics.csv"
    if not table.exists():
        return None
    with open(table, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    overall = next((r for r in rows if r.get("class") == "all"), None)
    if overall is None or not classes:
        return overall
    picked = [r for r in rows if r.get("class") in classes]
    if not picked:
        return None
    out = dict(overall)
    out["instances"] = str(sum(int(r["instances"]) for r in picked))
    for k in METRICS:
        out[k] = str(round(sum(float(r[k]) for r in picked) / len(picked), 4))
    return out


def write_matrix_csv(rows: List[dict], metric: str, path: Path,
                     models: List[str], datasets: List[str]) -> None:
    """One dataset per row, one model per column.

    This way round because the question is nearly always how the models
    compare on a given set of imagery, which is then a single line to read
    across, and because adding a dataset lengthens the table rather than
    widening it.
    """
    by = {(r["model"], r["dataset"]): r[metric] for r in rows}
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["dataset", *models])
        for d in datasets:
            w.writerow([d] + [by.get((m, d), "") for m in models])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--runs", type=Path, default=Path("data/runs"))
    ap.add_argument("--out", type=Path, default=Path("data/results"))
    ap.add_argument("--models", type=Path, default=Path("data/models"),
                    help="where the weight files are, for their sizes")
    ap.add_argument("--metric", default="map50_95", choices=METRICS,
                    help="which metric the matrix and figures report")
    ap.add_argument("--no-plots", action="store_true",
                    help="tables only, leave the figures to PlotRuns.py")
    ap.add_argument("--sweep", type=Path, default=Path("sweep.json"),
                    help="its \"classes\" list restricts every run to those")
    ap.add_argument("--all-classes", action="store_true",
                    help="report the 'all' row, over every class a run has")
    args = ap.parse_args()
    classes = [] if args.all_classes else sweep_classes(args.sweep)
    if classes:
        print(f"scored on {len(classes)} classes: {', '.join(classes)}")

    sizes = load_sizes(args.models)
    unknown: set = set()
    rows, missing = [], []
    predictions = []
    for run in sorted(p for p in args.runs.iterdir() if p.is_dir()):
        # Asked first, not as a fallback when no tables are found. A
        # prediction has no ground truth, so whatever a prediction folder
        # happens to contain it is not a result and must not become a row.
        if is_prediction(run):
            predictions.append(run.name)
            continue
        overall = read_overall(run, classes)
        if overall is None:
            missing.append(run.name)
            continue
        model, dataset, weight = identify(run)
        if dataset != "?" and not run.name.endswith("_" + dataset):
            # Nothing depends on the folder name, but a log that disagrees
            # with it means the run scored another set than its name says.
            print(f"  {run.name}: log says {dataset}")
        file_mb, weights_mb, params = weight_sizes(weight, args.models,
                                                   sizes, unknown)
        rows.append({"model": model, "dataset": dataset,
                     "file_mb": file_mb, "weights_mb": weights_mb,
                     "params": params,
                     "images": overall["images"],
                     "instances": overall["instances"],
                     **{k: overall[k] for k in METRICS}})

    if not rows:
        print("no finished runs found under", args.runs)
        return 1

    save_sizes(args.models, sizes)
    rows.sort(key=lambda r: (r["model"], r["dataset"]))
    models = sorted({r["model"] for r in rows})
    datasets = sorted({r["dataset"] for r in rows})

    args.out.mkdir(parents=True, exist_ok=True)
    csv_path = args.out / "comparison.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["model", "file_mb", "weights_mb",
                                           "params", "dataset", "images",
                                           "instances", *METRICS])
        w.writeheader()
        w.writerows(rows)

    matrix_csv = args.out / f"matrix_{args.metric}.csv"
    write_matrix_csv(rows, args.metric, matrix_csv, models, datasets)

    # The figures sweep.json names, so one run of this redraws all of them.
    # Without a plots block, the default two for everything in one.
    written = []
    if not args.no_plots:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from PlotRuns import configured, draw, draw_configured
        if configured(Path("sweep.json")):
            written = draw_configured(rows, args.out)
        else:
            written = draw(rows, args.metric, args.out)

    full = len(models) * len(datasets)
    print(f"{len(rows)} runs: {len(models)} models x {len(datasets)} datasets"
          f"{'' if len(rows) == full else f', {full - len(rows)} pair(s) not run'}")
    for name in missing:
        print(f"  no tables: {name}")
    if predictions:
        print(f"  {len(predictions)} prediction run(s), nothing to score: "
              + ", ".join(predictions))
    for w in sorted(unknown):
        print(f"  size unknown, reported as --: {w} is not in "
              f"{args.models} and has no row in {SIZES}")
    for f in [csv_path, matrix_csv, *written]:
        if f.exists():
            print(f"wrote {f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
