"""
Analyze NVG

Measures one set of images and reports the quantities GenerateNVG.py is
parameterised by, so the synthetic conversion can be tuned against numbers
rather than by eye.

    AnalyzeNVG.py captures/*.jpg --label real --csv nvg_stats.csv
    AnalyzeNVG.py synthetic/*.jpg --label green --csv nvg_stats.csv --append

One set per run. Run it once over the real captures and once over the
conversion, append both to the same file, and the rows carry a `group`
column to plot or tabulate against each other.

Every pixel of every image counts. Deciding which part of a frame is the
field belongs to GenerateCrops.py, which finds the circular boundary and
trims the radius to drop the vignette; this script measures what it is
given. Feed it uncropped captures and the black surround will drag every
statistic toward zero, so crop first.

WHAT IT MEASURES AND WHY

GenerateNVG builds its output from one grayscale image, tinted by a fixed
triple of channel multipliers. Every pixel therefore carries the same R:G:B
ratio until something clips, which has two consequences. The color of a real
device is fully described by two numbers, R/G and B/G, so they can be read
off a capture and used directly as multipliers. And if a real capture does
not hold a constant ratio across its pixels, the single-tint model cannot
reproduce it, which is worth knowing before tuning the multipliers to a
number that averages over the failure.

The rest of the measurements line up with the other NVGConfig fields:

    channel ratios      -> red_multiplier, green_multiplier, blue_multiplier
    luma mean and sd    -> contrast_beta, contrast_alpha
    percentiles, clip   -> whether alpha and beta push the range off either end
    noise sd            -> noise_intensity
    grain correlation   -> grain_size
    edge/center falloff -> vignette_intensity
    bright fraction     -> bloom_threshold, bloom_intensity

Read the falloff with the crop in mind. GenerateCrops removes the outer
tenth of the radius, so a cropped capture has already lost the steepest part
of its vignette and will report less falloff than the device produces. It is
still the right target to match, as long as the synthetic images it is
compared against were cropped the same way.

RATIOS ON DARK PIXELS

R/G is unstable where G is near zero: the quotient of two small noisy numbers
is noise. The headline ratio is therefore a ratio of means over the frame,
which weights by signal and is stable. The per-pixel spread beside it is
computed only where the green channel clears a floor, and says whether the
constant-ratio assumption holds; it is not an error bar on the headline.
"""

import argparse
import csv
import glob
import os
from pathlib import Path
from typing import Any, Dict, Sequence

import cv2
import numpy as np

# Per-pixel ratios are only formed where green clears this fraction of its
# own mean, below which the quotient is dominated by noise.
RATIO_FLOOR = 0.25

# Above this, the per-pixel ratio is not constant enough for one tint to
# describe the image. A judgement, not a standard: it is set where the
# variation starts to exceed the differences between the device colors the
# conversion is trying to tell apart.
RATIO_CONSTANT_LIMIT = 0.15

# Long edge the spatial statistics are computed over. Noise and grain are
# per-pixel properties, so resizing would change them; this crops instead.
SPATIAL_CROP = 1200

COLUMNS = ["group", "file", "width", "height",
           "mean_r", "mean_g", "mean_b", "rg", "bg", "rg_sd", "bg_sd",
           "lit_fraction", "luma_mean", "luma_sd", "p01", "p50", "p99",
           "clip_low", "clip_high", "bright_235", "noise_sd",
           "noise_dark", "noise_mid", "noise_bright", "grain_px",
           "edge_over_center"]


def ratios(bgr: np.ndarray) -> Dict[str, float]:
    """Channel ratios against green, and how constant they are."""
    b, g, r = (bgr[:, :, i].astype(np.float64).ravel() for i in range(3))
    mg = g.mean()
    out = {
        "mean_r": float(r.mean()), "mean_g": float(mg), "mean_b": float(b.mean()),
        "rg": float(r.mean() / mg) if mg else float("nan"),
        "bg": float(b.mean() / mg) if mg else float("nan"),
    }
    lit = g > mg * RATIO_FLOOR
    out["lit_fraction"] = float(lit.mean())
    if lit.sum() > 100:
        out["rg_sd"] = float((r[lit] / g[lit]).std())
        out["bg_sd"] = float((b[lit] / g[lit]).std())
    else:
        out["rg_sd"] = out["bg_sd"] = float("nan")
    return out


def tones(gray: np.ndarray) -> Dict[str, float]:
    """Level statistics driving contrast_alpha, contrast_beta and bloom."""
    v = gray.astype(np.float64).ravel()
    p01, p50, p99 = np.percentile(v, [1, 50, 99])
    return {
        "luma_mean": float(v.mean()), "luma_sd": float(v.std()),
        "p01": float(p01), "p50": float(p50), "p99": float(p99),
        "clip_low": float(np.mean(v <= 1)),
        "clip_high": float(np.mean(v >= 254)),
        "bright_235": float(np.mean(v >= 235)),
    }


def grain(gray: np.ndarray) -> Dict[str, float]:
    """
    Noise amplitude and the scale it is correlated over.

    The residual against a lightly blurred copy isolates what varies faster
    than the image content. Its spread is taken as a median absolute
    deviation scaled to a standard deviation, because edges put heavy tails
    on that residual and a plain standard deviation would read them as noise.

    Grain size is where the residual stops correlating with itself: a shifted
    copy of pure per-pixel noise decorrelates at one pixel, while grain that
    was blurred to a coarser particle stays correlated about that far.

    The residual is also reported per brightness band, over the thresholds
    GenerateNVG modulates grain with: it suppresses grain below 0.3 and above
    0.8 and runs it at full strength between. A single figure averages those
    bands together and cannot tell grain from image texture, because texture
    does not follow that curve. The shape does: added grain rises from the
    dark band to the mid band, while detail in the picture usually falls.
    Compare the profile, not the magnitude.
    """
    g = gray.astype(np.float32)
    residual = g - cv2.GaussianBlur(g, (0, 0), 1.5)
    if residual.size < 100:
        return {"noise_sd": float("nan"), "grain_px": float("nan"),
                "noise_dark": float("nan"), "noise_mid": float("nan"),
                "noise_bright": float("nan")}

    mad = float(np.median(np.abs(residual - np.median(residual))))

    out_bands = {}
    level = gray.astype(np.float32) / 255.0
    for name, lo, hi in (("dark", 0.0, 0.3), ("mid", 0.3, 0.8), ("bright", 0.8, 1.01)):
        sel = (level >= lo) & (level < hi)
        if sel.sum() < 500:
            out_bands[f"noise_{name}"] = float("nan")
            continue
        v = residual[sel]
        out_bands[f"noise_{name}"] = 1.4826 * float(
            np.median(np.abs(v - np.median(v))))

    centred = residual - residual.mean()
    denom = float((centred ** 2).sum())
    grain_px = float("nan")
    if denom > 0:
        grain_px = 9.0
        for lag in range(1, 9):
            if float((centred * np.roll(centred, lag, axis=1)).sum() / denom) < 0.5:
                grain_px = float(lag)
                break
    return {"noise_sd": 1.4826 * mad, "grain_px": grain_px, **out_bands}


def falloff(gray: np.ndarray) -> Dict[str, float]:
    """
    Edge against center brightness, which is what vignette_intensity sets.

    Radius runs from the frame center and is normalised by the corner, so
    the number means the same whatever the aspect ratio. On a frame cropped
    to the field that is the field's own center; on an uncropped one it is
    not, which is another reason to crop first.
    """
    h, w = gray.shape
    yy, xx = np.mgrid[0:h, 0:w]
    rad = np.hypot(yy - (h - 1) / 2, xx - (w - 1) / 2)
    rad /= rad.max()
    v = gray.astype(np.float64)
    center, edge = v[rad <= 0.2], v[rad >= 0.8]
    if center.size < 50 or edge.size < 50 or center.mean() == 0:
        return {"edge_over_center": float("nan")}
    return {"edge_over_center": float(edge.mean() / center.mean())}


def analyze(path: Path) -> Dict[str, Any]:
    bgr = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if bgr is None:
        raise SystemExit(f"cannot read {path}")
    h, w = bgr.shape[:2]
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)

    row: Dict[str, Any] = {"file": path.name, "width": w, "height": h}
    row.update(ratios(bgr))
    row.update(tones(gray))
    if max(h, w) > SPATIAL_CROP:
        y0, x0 = max(0, h // 2 - SPATIAL_CROP // 2), max(0, w // 2 - SPATIAL_CROP // 2)
        row.update(grain(gray[y0:y0 + SPATIAL_CROP, x0:x0 + SPATIAL_CROP]))
    else:
        row.update(grain(gray))
    row.update(falloff(gray))
    return row


def summarise(rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """Mean of each measure across the set, with its spread across images."""
    out: Dict[str, Any] = {"n": len(rows)}
    for k, v0 in rows[0].items():
        if not isinstance(v0, (int, float)):
            continue
        vals = np.array([r[k] for r in rows], dtype=float)
        vals = vals[~np.isnan(vals)]
        out[k] = float(vals.mean()) if vals.size else float("nan")
        out[k + "_spread"] = float(vals.max() - vals.min()) if vals.size else float("nan")
    return out


def color_split(rg: float, bg: float) -> Dict[str, float]:
    """
    Channel multipliers reproducing this color, scaled so nothing clips.

    GenerateNVG multiplies one gray image by each of these, so the largest
    has to stay at or below 1 or the brightest pixels saturate in that
    channel and the tint shifts where the image is brightest, which is the
    one place a viewer would notice.
    """
    trio = np.array([rg, 1.0, bg], dtype=float) / max(rg, 1.0, bg)
    return {"red_multiplier": round(float(trio[0]), 3),
            "green_multiplier": round(float(trio[1]), 3),
            "blue_multiplier": round(float(trio[2]), 3)}


# Measures worth seeing side by side, with the NVGConfig field each one
# drives. Eight panels rather than one axis because they share no scale: a
# ratio near 0.01 and a level near 200 on the same axis shows one of them.
PANELS = [
    ("rg", "R/G", "red_multiplier"),
    ("bg", "B/G", "blue_multiplier"),
    ("luma_mean", "luma mean", "contrast_beta"),
    ("luma_sd", "luma sd", "contrast_alpha"),
    ("p99", "p99", "headroom"),
    ("noise_mid", "noise sd, mid band", "noise_intensity"),
    ("grain_px", "grain px", "grain_size"),
    ("edge_over_center", "edge / center", "vignette_intensity"),
]


def plot(path: Path, rows: Sequence[Dict[str, Any]]) -> None:
    """
    Every measure, every image, grouped, for checking a set at a glance.

    Plotted from the csv rather than from the run that just finished, so a
    file built up over several appended runs shows all of its groups and the
    figure matches the table beside it.

    Each image is its own point, with the group mean as a bar across them.
    Showing the points rather than the mean alone is the whole purpose: a
    single outlier dragging a group mean, or two groups that disagree by more
    than their spreads, is the thing a quick check needs to catch, and a bar
    chart of means hides exactly that.
    """
    import matplotlib
    matplotlib.use("Agg")           # never displays, and Qt fails when piped
    from matplotlib import pyplot as plt

    groups = list(dict.fromkeys(r["group"] for r in rows))
    colors = plt.cm.tab10.colors

    fig, axes = plt.subplots(2, 4, figsize=(14, 6.5))
    for ax, (key, label, tunes) in zip(axes.ravel(), PANELS):
        for i, g in enumerate(groups):
            v = [float(r[key]) for r in rows
                 if r["group"] == g and r[key] not in ("", None)
                 and float(r[key]) == float(r[key])]
            if not v:
                continue
            jitter = (np.random.default_rng(0).random(len(v)) - 0.5) * 0.28
            ax.plot(np.full(len(v), i) + jitter, v, "o", ms=4, alpha=0.65,
                    color=colors[i % len(colors)], mew=0)
            m = float(np.mean(v))
            ax.plot([i - 0.3, i + 0.3], [m, m], "-", lw=2.2, color="0.15",
                    zorder=3)
            ax.annotate(f"{m:.3g}", (i, m), textcoords="offset points",
                        xytext=(0, 7), ha="center", fontsize=7.5, color="0.15")
        ax.set_xticks(range(len(groups)))
        ax.set_xticklabels(groups, fontsize=7.5, rotation=20, ha="right")
        ax.set_xlim(-0.6, len(groups) - 0.4)
        ax.set_title(f"{label}   ({tunes})", fontsize=9)
        ax.tick_params(axis="y", labelsize=7.5)
        ax.grid(alpha=0.25, axis="y")

    fig.suptitle(f"{path.stem}: {len(rows)} images, "
                 f"{len(groups)} groups, bar is the group mean", fontsize=10)
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=150)
    plt.close(fig)


def table(rows: Sequence[Sequence[Any]], head: Sequence[str]) -> None:
    w = [max(len(str(r[i])) for r in (head, *rows)) for i in range(len(head))]
    print("  ".join(str(h).ljust(n) for h, n in zip(head, w)))
    for r in rows:
        print("  ".join(str(c).ljust(n) for c, n in zip(r, w)))


def main() -> int:
    p = argparse.ArgumentParser(
        description="Measure one set of images for tuning GenerateNVG. "
                    "Crop first with GenerateCrops.py; this measures whole "
                    "frames.")
    p.add_argument("files", nargs="+", help="images in this set")
    p.add_argument("--label", help="name for the set, written to the group "
                                   "column; defaults to the parent folder")
    p.add_argument("--csv", help="write the per-image table here")
    p.add_argument("--append", action="store_true",
                   help="add to an existing --csv instead of replacing it, so "
                        "two sets end up in one file ready to plot")
    p.add_argument("--sample", type=int, metavar="N",
                   help="measure a random N of the matched files instead of "
                        "all of them. Drawn with a fixed seed so the same N "
                        "over the same set gives the same images twice")
    p.add_argument("--seed", type=int, default=0,
                   help="seed for --sample")
    p.add_argument("--no-plot", action="store_true",
                   help="skip the figure written beside --csv")
    p.add_argument("--per-image", action="store_true",
                   help="list every image rather than the first and last few")
    args = p.parse_args()

    files = sorted({Path(q) for pat in args.files for q in glob.glob(pat)})
    if not files:
        raise SystemExit(f"no files matched {args.files}")
    matched = len(files)
    if args.sample and args.sample < matched:
        # Sampled from the sorted list with a fixed seed, so the selection is
        # reproducible and does not depend on the order the filesystem
        # happened to return.
        idx = np.random.default_rng(args.seed).choice(
            matched, args.sample, replace=False)
        files = [files[i] for i in sorted(idx)]
    label = args.label or files[0].parent.name

    rows = []
    for f in files:
        r = analyze(f)
        r["group"] = label
        rows.append(r)
    s = summarise(rows)

    sampled = (f", sampled from {matched} with seed {args.seed}"
               if len(rows) < matched else "")
    print(f"=== {label}, {len(rows)} images{sampled} ===")
    shown = rows if (args.per_image or len(rows) <= 10) else rows[:5] + rows[-5:]
    table([[r["file"][:44], f"{r['width']}x{r['height']}",
            f"{r['rg']:.3f}", f"{r['bg']:.3f}",
            f"{r['luma_mean']:.1f}", f"{r['luma_sd']:.1f}",
            f"{r['noise_sd']:.2f}", f"{r['grain_px']:.0f}",
            f"{r['edge_over_center']:.3f}"] for r in shown],
          ["file", "size", "R/G", "B/G", "luma", "sd", "noise", "grain",
           "edge/ctr"])
    if len(shown) < len(rows):
        print(f"  ... {len(rows) - len(shown)} more, all of them in the csv")

    print(f"\n  R/G {s['rg']:.3f}  spread {s['rg_spread']:.3f}"
          f"     B/G {s['bg']:.3f}  spread {s['bg_spread']:.3f}")
    print(f"  per-pixel ratio sd within an image: R/G {s['rg_sd']:.3f}, "
          f"B/G {s['bg_sd']:.3f}")
    if max(s["rg_sd"], s["bg_sd"]) > RATIO_CONSTANT_LIMIT:
        print(f"    above {RATIO_CONSTANT_LIMIT}, so the ratio is not constant "
              "across the frame and one\n    tint cannot reproduce these "
              "images exactly, whatever it is set to.")

    m = color_split(s["rg"], s["bg"])
    print("\n=== color split for GenerateNVG ===")
    for k in ("red_multiplier", "green_multiplier", "blue_multiplier"):
        print(f"  {k:<17}{m[k]}")
    print("  scaled so the largest is 1.0; multiply all three by one factor to "
          "trade\n  headroom against brightness.")

    print("\n=== the other NVGConfig targets ===")
    table([["luma mean", f"{s['luma_mean']:.1f}", f"{s['luma_mean_spread']:.1f}", "contrast_beta"],
           ["luma sd", f"{s['luma_sd']:.1f}", f"{s['luma_sd_spread']:.1f}", "contrast_alpha"],
           ["p01", f"{s['p01']:.0f}", f"{s['p01_spread']:.0f}", "where beta lands the floor"],
           ["p50", f"{s['p50']:.0f}", f"{s['p50_spread']:.0f}", "midpoint after alpha and beta"],
           ["p99", f"{s['p99']:.0f}", f"{s['p99_spread']:.0f}", "headroom before clipping"],
           ["clipped low", f"{s['clip_low']:.2%}", f"{s['clip_low_spread']:.2%}", "beta too low"],
           ["clipped high", f"{s['clip_high']:.2%}", f"{s['clip_high_spread']:.2%}", "beta too high"],
           ["at or above 235", f"{s['bright_235']:.2%}", f"{s['bright_235_spread']:.2%}", "bloom_threshold population"],
           ["noise sd, all", f"{s['noise_sd']:.2f}", f"{s['noise_sd_spread']:.2f}", "noise_intensity"],
           ["  dark <0.3", f"{s['noise_dark']:.2f}", f"{s['noise_dark_spread']:.2f}", "suppressed by the bell curve"],
           ["  mid 0.3-0.8", f"{s['noise_mid']:.2f}", f"{s['noise_mid_spread']:.2f}", "noise_intensity, full strength"],
           ["  bright >0.8", f"{s['noise_bright']:.2f}", f"{s['noise_bright_spread']:.2f}", "suppressed by the bell curve"],
           ["grain px", f"{s['grain_px']:.1f}", f"{s['grain_px_spread']:.1f}", "grain_size"],
           ["edge / center", f"{s['edge_over_center']:.3f}", f"{s['edge_over_center_spread']:.3f}", "vignette_intensity"]],
          ["measure", "mean", "spread", "tunes"])

    if args.csv:
        exists = os.path.exists(args.csv)
        mode = "a" if (args.append and exists) else "w"
        with open(args.csv, mode, newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=COLUMNS, extrasaction="ignore")
            if mode == "w":
                w.writeheader()
            for r in rows:
                w.writerow({k: (round(v, 6) if isinstance(v, float) else v)
                            for k, v in r.items() if k in COLUMNS})
        verb = "appended to" if mode == "a" else "wrote"
        print(f"\n{verb} {args.csv}, {len(rows)} rows as group '{label}'")
        if args.append and not exists:
            print("  (--append given but the file did not exist, so it was "
                  "created with a header)")

        if not args.no_plot:
            # Read back rather than plotting `rows`, so an appended file shows
            # every group it holds and not just the one this run added.
            with open(args.csv, newline="", encoding="utf-8") as fh:
                allrows = list(csv.DictReader(fh))
            img = Path(args.csv).with_suffix(".png")
            plot(img, allrows)
            print(f"wrote {img}, {len(allrows)} images in "
                  f"{len({r['group'] for r in allrows})} groups")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
