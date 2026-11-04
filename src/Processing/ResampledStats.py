"""
ResampledStats.py

Summarize the runs on the resampled sets that BuildResampledSets.py built and
RunResampled.ps1 ran, overall and per category, from each run's
tables/per_class_metrics.csv.

Two tables:

    resampled_variability.csv   how far a single score moves: per category
                                the score on the set the sets were drawn
                                from, its instances there and per set, and
                                the mean, sample standard deviation, 1.96
                                standard deviations, range and how many sets
                                lie within 1.96 standard deviations of the
                                mean; the standard deviation is also given
                                over the first 25, 50 and 75 sets, to show
                                whether a hundred suffice
    resampled_paired.csv        with --variant, how far the difference
                                between the variant and the source moves
                                when both are scored on the same images
                                (sets rebuilt with --reuse): per category the
                                difference on the full sets, and over the
                                resampled sets its mean, standard deviation,
                                1.96 standard deviations, range, how many
                                sets it was positive on and how many lie
                                within 1.96 standard deviations, and the
                                correlation of the two scores

Set r of the variant is paired with set r of the source, which --reuse makes
the same captures in the same multiplicity.

Usage:
    python src/Processing/ResampledStats.py
    python src/Processing/ResampledStats.py --variant real_nvg_dn_h20_w5
"""

from __future__ import annotations

import argparse
import csv
import re
import statistics as st
from pathlib import Path
from typing import Dict, List

CATEGORIES = ("all", "backpack", "bottle", "laptop", "mouse")


def per_class(run: Path, metric: str) -> Dict[str, dict]:
    path = run / "tables" / "per_class_metrics.csv"
    with open(path, newline="", encoding="utf-8") as fh:
        return {r["class"]: r for r in csv.DictReader(fh)}


def resampled(runs: Path, model: str, source: str, tag: str) -> Dict[int, Path]:
    """Run folders of the resampled sets of source, by set number."""
    pat = re.compile(rf"^val_{re.escape(model)}_{re.escape(source)}_"
                     rf"{re.escape(tag)}_r(\d+)$")
    found = {}
    for p in runs.iterdir():
        m = pat.match(p.name)
        if m:
            found[int(m.group(1))] = p
    return dict(sorted(found.items()))


def write(path: Path, rows: List[dict]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {path}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--model", default="yolo12x")
    ap.add_argument("--source", default="real_nvg")
    ap.add_argument("--variant", help="preprocessed variant rebuilt with "
                    "--reuse SOURCE; adds the paired table")
    ap.add_argument("--tag", default="rs_u66p7")
    ap.add_argument("--metric", default="map50_95")
    ap.add_argument("--runs", type=Path, default=Path("data/runs"))
    ap.add_argument("--resampled", type=Path,
                    default=Path("data/runs_resampled"))
    ap.add_argument("--out", type=Path, default=Path("data/results"))
    args = ap.parse_args()
    m = args.metric

    src = resampled(args.resampled, args.model, args.source, args.tag)
    if not src:
        print(f"no resampled runs of {args.model} on {args.source}")
        return 1
    full = per_class(args.runs / f"val_{args.model}_{args.source}", m)
    sets = [per_class(p, m) for p in src.values()]
    print(f"{len(sets)} resampled sets of {args.source}")

    rows = []
    for c in CATEGORIES:
        v = [float(s[c][m]) for s in sets]
        inst = [int(s[c]["instances"]) for s in sets]
        mean, sd = st.mean(v), st.stdev(v)
        rows.append({
            "category": c, "full": full[c][m],
            "instances": full[c]["instances"],
            "instances_min": min(inst), "instances_max": max(inst),
            "mean": f"{mean:.4f}", "sd": f"{sd:.4f}",
            "sd_1p96": f"{1.96 * sd:.4f}",
            "min": f"{min(v):.4f}", "max": f"{max(v):.4f}",
            "within_1p96": sum(abs(x - mean) <= 1.96 * sd for x in v),
            **{f"sd_first{n}": f"{st.stdev(v[:n]):.4f}"
               for n in (25, 50, 75) if n < len(v)},
            "sets": len(v)})
    args.out.mkdir(parents=True, exist_ok=True)
    write(args.out / "resampled_variability.csv", rows)

    if not args.variant:
        return 0
    var = resampled(args.resampled, args.model, args.variant, args.tag)
    common = [r for r in src if r in var]
    if not common:
        print(f"no resampled runs of {args.model} on {args.variant}")
        return 1
    full_v = per_class(args.runs / f"val_{args.model}_{args.variant}", m)
    a_sets = [per_class(src[r], m) for r in common]
    b_sets = [per_class(var[r], m) for r in common]
    print(f"{len(common)} paired sets of {args.variant} and {args.source}")

    rows = []
    for c in CATEGORIES:
        a = [float(s[c][m]) for s in a_sets]
        b = [float(s[c][m]) for s in b_sets]
        d = [y - x for x, y in zip(a, b)]
        mean, sd = st.mean(d), st.stdev(d)
        rows.append({
            "category": c,
            "full": f"{float(full_v[c][m]) - float(full[c][m]):.4f}",
            "mean": f"{mean:.4f}", "sd": f"{sd:.4f}",
            "sd_1p96": f"{1.96 * sd:.4f}",
            "min": f"{min(d):.4f}", "max": f"{max(d):.4f}",
            "positive": sum(x > 0 for x in d),
            "within_1p96": sum(abs(x - mean) <= 1.96 * sd for x in d),
            "correlation": f"{st.correlation(a, b):.3f}",
            "sets": len(d)})
    write(args.out / f"resampled_paired_{args.variant}.csv", rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
