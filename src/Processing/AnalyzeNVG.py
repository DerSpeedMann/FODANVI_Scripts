"""
Analyze NVG

Measures one set of images and reports the quantities GenerateNVGv2.py is
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

GenerateNVGv2 builds its output from one grayscale image, tinted by a fixed
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
import json
import os
from datetime import datetime, timezone
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

# The region every statistic but the falloff is measured over: a disc of this
# fraction of the inscribed-circle radius, centred on the frame.
#
# The vignette is present in the captures and in the conversions both, so
# averaging over a whole frame measures the falloff as much as the thing being
# asked about, and it does so differently on each side: the captures are square
# crops of the circular field while the conversions are 4:3 and 3:2 frames.
# Measured over the whole frame the real green reference reads luma_mean 83.3
# and luma_sd 21.6; over this region it reads 96.6 and 18.0. The mean is 16 per
# cent low because the dark annulus is averaged in, and the spread is 16 per
# cent high because the falloff gradient itself counts as contrast, which then
# propagates into contrast_alpha. For white those errors are 19 and 30 per cent.
#
# 0.5 keeps about a quarter of the pixels, enough that the per-image noise
# figures stay stable, and on the references it cuts the within-region spread
# from 22.1 to about 13. Channel ratios are the one family that barely moves,
# a quotient of two means being scale invariant under a vignette, which is why
# the color conclusions survive this and the tone ones do not.
REGION_FRAC = 0.5

# Brightness bands of the grain profile, and how many images a band needs
# before it is written: one image alone is its scene, not the device.
PROFILE_BANDS = 10
PROFILE_MIN_IMAGES = 2


def region_mask(h: int, w: int, frac: float = REGION_FRAC) -> np.ndarray:
    """Boolean mask of the centred measurement disc.

    Normalised by the inscribed radius rather than the corner, so the region
    is the same fraction of the field whatever the aspect ratio.
    """
    cy, cx = (h - 1) / 2.0, (w - 1) / 2.0
    yy, xx = np.mgrid[0:h, 0:w]
    return np.hypot(yy - cy, xx - cx) <= (min(h, w) / 2.0) * frac

COLUMNS = ["group", "file", "width", "height",
           "mean_r", "mean_g", "mean_b", "rg", "bg", "rg_sd", "bg_sd",
           "lit_fraction", "luma_mean", "luma_sd", "p01", "p50", "p99",
           "clip_low", "clip_high", "bright_235", "noise_sd",
           "noise_dark", "noise_mid", "noise_bright", "grain_px",
           "edge_over_center"]


def ratios(bgr: np.ndarray, mask: np.ndarray) -> Dict[str, float]:
    """Channel ratios against green, and how constant they are.

    Taken inside `mask` (see REGION_FRAC). These move least of anything here
    when the region changes, but the dark annulus of a real capture is noise
    dominated and biases the quotient where the signal is near zero.
    """
    b, g, r = (bgr[:, :, i].astype(np.float64)[mask] for i in range(3))
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


def tones(gray: np.ndarray, mask: np.ndarray) -> Dict[str, float]:
    """Level statistics driving contrast_alpha, contrast_beta and bloom.

    Taken inside `mask`, so the falloff is not read as either darkness or
    contrast. See REGION_FRAC for what measuring the whole frame costs.
    """
    v = gray.astype(np.float64)[mask]
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
    GenerateNVGv2 modulates grain with: it suppresses grain below 0.3 and above
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
                "noise_bright": float("nan"),
                **{f"noise_b{i}": float("nan") for i in range(PROFILE_BANDS)}}

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

    # The same residual in ten bands of 0.1, which build_config writes as the
    # grain profile GenerateNVGv2 applies band by band.
    for i in range(PROFILE_BANDS):
        sel = (level >= i / PROFILE_BANDS) & (level < (i + 1) / PROFILE_BANDS)
        if sel.sum() < 500:
            out_bands[f"noise_b{i}"] = float("nan")
            continue
        v = residual[sel]
        out_bands[f"noise_b{i}"] = 1.4826 * float(
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

    Radius runs from the frame center and is normalised by the inscribed
    radius, so 1.0 is the largest circle the frame contains and the bands
    below are the same fraction of the field whatever the aspect ratio. On a
    frame cropped to the field that is the field's own center; on an
    uncropped one it is not, which is another reason to crop first.

    Normalising by the corner instead, as this did until the region was
    introduced, makes the bands aspect dependent: on a 4:3 conversion
    `rad >= 0.8` reaches into corners that lie outside any circular field,
    while on a square capture it is the outer fifth of the field, so the two
    numbers were never measuring the same annulus. The edge band is capped at
    1.0 for the same reason.

    What this still does not reconcile is that GenerateNVGv2 builds its vignette
    from two 1-D Gaussians scaled to the frame's own width and height, making
    it elliptical on a non-square frame, where the device's is circular. That
    is in the conversion, not in the measurement, so it is not fixed here.
    """
    h, w = gray.shape
    yy, xx = np.mgrid[0:h, 0:w]
    rad = np.hypot(yy - (h - 1) / 2, xx - (w - 1) / 2)
    rad /= min(h, w) / 2.0
    v = gray.astype(np.float64)
    center, edge = v[rad <= 0.2], v[(rad >= 0.8) & (rad <= 1.0)]
    if center.size < 50 or edge.size < 50 or center.mean() == 0:
        return {"edge_over_center": float("nan")}
    return {"edge_over_center": float(edge.mean() / center.mean())}


def analyze(path: Path) -> Dict[str, Any]:
    bgr = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if bgr is None:
        raise SystemExit(f"cannot read {path}")
    h, w = bgr.shape[:2]
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)

    mask = region_mask(h, w)

    row: Dict[str, Any] = {"file": path.name, "width": w, "height": h}
    row.update(ratios(bgr, mask))
    row.update(tones(gray, mask))

    # Grain needs a rectangle: the autocorrelation shifts the residual against
    # itself, which a masked set of pixels cannot do. The square inscribed in
    # the measurement disc is the largest one entirely inside the region, so
    # the brightness bands grain is split by are read off un-vignetted levels.
    # Averaged over a whole frame the vignette pushes genuine mid-tones into
    # the dark band instead, which moved noise_dark by up to 43 per cent.
    side = min(int((min(h, w) / 2.0) * REGION_FRAC * 2 ** 0.5), SPATIAL_CROP)
    if side >= 16:
        y0, x0 = (h - side) // 2, (w - side) // 2
        row.update(grain(gray[y0:y0 + side, x0:x0 + side]))
    else:
        row.update(grain(gray))

    # Deliberately the whole frame: this is the one measurement whose subject
    # is the falloff itself.
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
        out[k + "_n"] = int(vals.size)
    return out


def color_split(rg: float, bg: float) -> Dict[str, float]:
    """
    Channel multipliers reproducing this color, scaled so nothing clips.

    GenerateNVGv2 multiplies one gray image by each of these, so the largest
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


# Brightness the v2 grain curve peaks at. noise_intensity is the grain there,
# so that is the band to read it from. Must match GenerateNVGv2's grain_peak.
GRAIN_PEAK = 0.15

# An equalised histogram is close to uniform over 0..255, whose mean and
# standard deviation are these. GenerateNVGv2 equalises before applying
# contrast, so they are what alpha and beta act on.
EQUALISED_MEAN = 127.5
EQUALISED_SD = 255.0 / (12 ** 0.5)


def solve_vignette(shape, target, lo=1.0, hi=8.0):
    """
    The vignette_intensity whose mask would produce this edge/center ratio.

    GenerateNVGv2 builds the mask as an outer product of two Gaussian kernels
    with sigma = side / vignette_intensity, normalised to peak at one. There
    is no tidy inverse, so this bisects on the same statistic falloff()
    measures, computed on the mask itself. Monotonic in the intensity, so
    bisection is safe.

    It answers "what setting would darken a flat field this much", which is
    an upper bound: a real capture's edges are also darker because of what
    was in front of the lens, and that is counted here as vignette.
    """
    h, w = shape
    yy, xx = np.mgrid[0:h, 0:w]
    rad = np.hypot(yy - (h - 1) / 2, xx - (w - 1) / 2)
    rad /= rad.max()
    inner, outer = rad <= 0.2, rad >= 0.8

    def ratio(v):
        kx = cv2.getGaussianKernel(w, w / v)
        ky = cv2.getGaussianKernel(h, h / v)
        m = ky * kx.T
        m = m / m.max()
        return float(m[outer].mean() / m[inner].mean())

    if target >= ratio(lo):
        return lo
    if target <= ratio(hi):
        return hi
    for _ in range(40):
        mid = (lo + hi) / 2
        if ratio(mid) > target:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def build_config(s: Dict[str, Any], label: str, n: int,
                 color: str) -> Dict[str, Any]:
    """
    Turn the measurements into something GenerateNVGv2.py can load.

    Three of these are read almost directly and are the reason the file is
    worth writing. The channel multipliers are the measured ratios. The
    grain is the residual spread at the band the curve peaks at, since
    GenerateNVGv2 draws its noise with a standard deviation of
    noise_intensity * mask and the mask is one there. Grain size is the lag
    the residual stays correlated over, rounded to an odd kernel.

    Two are derived through an assumption and should be treated as a
    starting point. Contrast inverts alpha and beta against an equalised
    histogram, which is only approximately uniform, and the measured levels
    carry the grain that is applied after contrast. The vignette is solved
    against a flat field, so anything dark at the edges of the real scene
    inflates it.

    Measuring inside REGION_FRAC removes most, not all, of the vignette from
    these two. GenerateNVGv2 multiplies the mask in after convertScaleAbs, and
    across the region that mask still averages around 0.93 at the default
    intensities, so the levels predicted here come out a few per cent dark
    rather than the 38 to 51 per cent they did over a whole frame. Matching
    the target exactly still wants the pair solved against the pipeline; what
    changed is that the starting point is now close enough to be useful.

    Nothing is emitted for bloom. Its threshold and intensity do not follow
    from a histogram without assuming what in the scene should bloom.
    """
    # The grain profile: residual spread per brightness band, for every band
    # at least PROFILE_MIN_IMAGES images reach. GenerateNVGv2 applies it band by
    # band and holds the end values beyond the measured range, so nothing is
    # read off an assumed curve. noise_intensity then scales the profile as a
    # whole and 1.0 applies it as measured. Only with no band measured at all
    # does the single figure at GRAIN_PEAK stand in, as it did before.
    profile = [(round((i + 0.5) / PROFILE_BANDS, 3), round(s[f"noise_b{i}"], 4))
               for i in range(PROFILE_BANDS)
               if s.get(f"noise_b{i}_n", 0) >= PROFILE_MIN_IMAGES]
    if profile:
        noise = 1.0
    else:
        peak_band = "noise_dark" if GRAIN_PEAK < 0.3 else "noise_mid"
        noise = s[peak_band]
    grain = int(round(s["grain_px"]))
    grain += (grain + 1) % 2                      # kernels must be odd

    alpha = s["luma_sd"] / EQUALISED_SD
    beta = s["luma_mean"] - alpha * EQUALISED_MEAN

    vign = solve_vignette((600, 800), s["edge_over_center"])

    m = color_split(s["rg"], s["bg"])
    return {
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": {"group": label, "images": n,
                   "region_frac": REGION_FRAC,
                   "written_by": "AnalyzeNVG.py --config"},
        "color": color,
        "color_settings": {
            "color": color,
            "red_multiplier": m["red_multiplier"],
            "green_multiplier": m["green_multiplier"],
            "blue_multiplier": m["blue_multiplier"],
            "contrast_multiplier": 1.0,
            "brightness_multiplier": 1.0,
        },
        "noise_intensity": round(float(noise), 3),
        "grain_profile": {"brightness": [b for b, _ in profile],
                          "sigma": [v for _, v in profile]} if profile else None,
        "grain_size": grain,
        "contrast_alpha": round(float(alpha), 3),
        "contrast_beta": int(round(beta)),
        "vignette_intensity": round(float(vign), 2),
        "measured": {k: round(float(s[k]), 4) for k in
                     ("rg", "bg", "rg_sd", "bg_sd", "luma_mean", "luma_sd",
                      "p01", "p50", "p99", "noise_sd", "noise_dark",
                      "noise_mid", "grain_px", "edge_over_center")},
    }


def table(rows: Sequence[Sequence[Any]], head: Sequence[str]) -> None:
    w = [max(len(str(r[i])) for r in (head, *rows)) for i in range(len(head))]
    print("  ".join(str(h).ljust(n) for h, n in zip(head, w)))
    for r in rows:
        print("  ".join(str(c).ljust(n) for c, n in zip(r, w)))


def main() -> int:
    p = argparse.ArgumentParser(
        description="Measure one set of images for tuning GenerateNVGv2. "
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
    p.add_argument("--config", metavar="FILE",
                   help="write a json GenerateNVGv2.py can load with its own "
                        "--config, derived from these measurements")
    p.add_argument("--config-color", choices=["green", "white"], default="green",
                   help="which color mode the written config targets")
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
    print("\n=== color split for GenerateNVGv2 ===")
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

    if args.config:
        cfg = build_config(s, label, len(rows), args.config_color)
        Path(args.config).write_text(json.dumps(cfg, indent=2), encoding="utf-8")
        print(f"\nwrote {args.config}")
        print(f"  measured directly: multipliers "
              f"{cfg['color_settings']['red_multiplier']}, "
              f"{cfg['color_settings']['green_multiplier']}, "
              f"{cfg['color_settings']['blue_multiplier']}; "
              f"noise_intensity {cfg['noise_intensity']}; "
              f"grain_size {cfg['grain_size']}")
        print(f"  derived through an assumption, treat as a starting point: "
              f"contrast_alpha {cfg['contrast_alpha']}, "
              f"contrast_beta {cfg['contrast_beta']}, "
              f"vignette_intensity {cfg['vignette_intensity']}")
        print("  nothing written for bloom; it does not follow from a "
              "histogram.")

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
