"""
Scene Lux Grain

Grain of a night vision device against its gain setting, per frame, from raw
captures of its eyepiece over the regions SceneLux measured the card in, set
against the noise the camera adds on its own.

    SceneLuxGrain.py --rois rois\\rois_nvg.json \\
        --series g1_max trough_nvg\\s05_01_*.NEF \\
        --series g2 trough_nvg\\s05_02_*.NEF ... \\
        --pairs direct_screen_light\\s18_03_*.NEF direct_screen_light\\s18_04_*.NEF \\
        --dark direct_screen_light\\s18_01_*.NEF --csv grain_table.csv \\
        --summary grain_series.csv

Each frame is reduced to one of its two green photosite planes, black
subtracted and scaled to the white level, so that neighbouring values come
from the same CFA channel and no demosaicing mixes them. Inside each region
the noise is measured as AnalyzeNVG measures it on the evaluation captures:
the residual against a Gaussian-blurred copy (sigma 1.5), its spread as a
median absolute deviation scaled to a standard deviation. The blur runs over a
margin around the region so that its edges do not enter the residual.

Beside the spread, the correlation of the residual with itself shifted by one
value along a row, which on a single green plane is two photosites. Noise
independent per photosite reads slightly negative there, since the blurred copy
it is taken against shares part of every value; a positive value means the
residual is correlated over more than one value, as a coarser grain is.

CAMERA NOISE

The camera adds two kinds of noise of its own. Read and dark noise are
measured in the same frame, in four corner regions outside the intensified
field, which see no light but share exposure, ISO and temperature with the
card regions. Photon shot noise is not in the corners, since it follows the
light: its variance is the signal in DN times the DN per photoelectron. That
conversion is estimated by photon transfer from pairs of frames of an evenly
lit target at the same ISO, passed with --pairs two files per pair: the
variance of the difference of a pair, halved, less the variance of a dark
pair (--dark), against the mean level. Regions at the centre of the target
are left out of the fit, see OFFCENTRE.

The camera's expected residual at a level is the shot and the corner variance
passed through the same residual filter, whose effect on independent noise is
measured on simulated white noise rather than derived. What is left of the
measured residual after removing it in quadrature is the part the camera does
not explain. The camera share is the same comparison as a ratio, the camera
variance over the measured variance, capped at one, where the camera alone
could produce all of the residual.

Frames are reported one by one, in the order given, and the four regions are
averaged per frame. The pairs, too, are taken in the order given, so no file
name has to sort in capture order. With --summary the frames are also averaged per series,
the frames shot at one setting in one go. Which frames those are is a fact
about how they were shot, as in SceneLuxGain, so the script does not read it
from the files: each --series names a label and its frames. Grouping by
series rather than by setting keeps a setting returned to later as a row of
its own.
"""

import argparse
import csv
import json
from pathlib import Path
from typing import List, Sequence

import cv2
import numpy as np
import rawpy

SIGMA = 1.5
MARGIN = 8

# Corners of the frame, outside the intensified field, as (centre x, centre y,
# half width, half height) normalised like the card regions.
CORNERS = {
    "c_ul": (0.05, 0.08, 0.015, 0.02),
    "c_ur": (0.95, 0.08, 0.015, 0.02),
    "c_ll": (0.05, 0.92, 0.015, 0.02),
    "c_lr": (0.95, 0.92, 0.015, 0.02),
}

# Photon-transfer regions, half size 100 values of the green plane. The centre
# of the screen target is left out: there the pairs read well above the
# off-centre regions at a similar level, which pure shot noise would not do,
# so something besides shot noise varies between the two frames there.
OFFCENTRE = ((0.3, 0.3), (0.7, 0.7))
PTC_HALF = 100


def green_plane(path: Path):
    """First green photosite plane, black subtracted, as a fraction of white,
    and the white level above black in DN."""
    with rawpy.imread(str(path)) as r:
        raw = r.raw_image_visible.astype(np.float64)
        colors = r.raw_colors_visible
        black = float(np.mean(r.black_level_per_channel))
        white = float(r.white_level)
    for dy in (0, 1):
        for dx in (0, 1):
            if colors[dy, dx] == 1:
                return (raw[dy::2, dx::2] - black) / (white - black), white - black
    raise ValueError(f"{path.name}: no green photosite in the CFA pattern")


def residual_of(block: np.ndarray) -> np.ndarray:
    block = block.astype(np.float32)
    return block - cv2.GaussianBlur(block, (0, 0), SIGMA)


def region(plane: np.ndarray, rect) -> dict:
    """Mean, residual spread and lag-one correlation inside one region."""
    cx, cy, hw, hh = rect
    h, w = plane.shape
    x0, x1 = int((cx - hw) * w), int((cx + hw) * w)
    y0, y1 = int((cy - hh) * h), int((cy + hh) * h)
    big = plane[y0 - MARGIN:y1 + MARGIN, x0 - MARGIN:x1 + MARGIN]
    residual = residual_of(big)[MARGIN:-MARGIN, MARGIN:-MARGIN]
    mad = float(np.median(np.abs(residual - np.median(residual))))
    centred = residual - residual.mean()
    lag1 = float((centred * np.roll(centred, 1, axis=1)).sum() / (centred ** 2).sum())
    return {"mean": float(plane[y0:y1, x0:x1].mean()),
            "noise_sd": 1.4826 * mad, "lag1": lag1}


def averaged(plane: np.ndarray, rects) -> dict:
    per = [region(plane, rect) for rect in rects]
    return {k: float(np.mean([p[k] for p in per])) for k in per[0]}


def filter_factor() -> float:
    """Residual spread over input spread, for noise independent per value."""
    noise = np.random.default_rng(0).standard_normal((512, 512))
    return float(residual_of(noise)[MARGIN:-MARGIN, MARGIN:-MARGIN].std())


def pair_stats(a: Path, b: Path) -> List[tuple]:
    """(mean DN, half the variance of the difference in DN^2) per region."""
    pa, span = green_plane(a)
    pb, _ = green_plane(b)
    h, w = pa.shape
    out = []
    for cy, cx in OFFCENTRE:
        y0, x0 = int(cy * h) - PTC_HALF, int(cx * w) - PTC_HALF
        sa = pa[y0:y0 + 2 * PTC_HALF, x0:x0 + 2 * PTC_HALF] * span
        sb = pb[y0:y0 + 2 * PTC_HALF, x0:x0 + 2 * PTC_HALF] * span
        out.append(((sa.mean() + sb.mean()) / 2, np.var(sa - sb) / 2))
    return out


def conversion(pairs: Sequence[Path], dark: Sequence[Path]) -> float:
    """DN per photoelectron, as the slope of variance over level above dark."""
    if len(pairs) % 2 or len(dark) != 2:
        raise SystemExit("--pairs takes two files per pair, --dark exactly two")
    dark_stats = pair_stats(*dark)
    points = []
    for i in range(0, len(pairs), 2):
        for (m, v), (dm, dv) in zip(pair_stats(pairs[i], pairs[i + 1]), dark_stats):
            points.append((m - dm, v - dv))
            print(f"  {pairs[i].name:34s} level {m - dm:7.1f} DN  "
                  f"shot var {v - dv:8.1f} DN^2  ratio {(v - dv) / (m - dm):.2f}")
    x = np.array([p[0] for p in points])
    y = np.array([p[1] for p in points])
    return float((x * y).sum() / (x * x).sum())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[1])
    parser.add_argument("frames", type=Path, nargs="*", help="raw captures")
    parser.add_argument("--series", nargs="+", action="append", default=[],
                        metavar=("LABEL", "FRAME"),
                        help="a label and the raw captures of one series; "
                             "repeat per series")
    parser.add_argument("--rois", type=Path, required=True,
                        help="normalised regions, as SceneLux reads them")
    parser.add_argument("--pairs", type=Path, nargs="+", required=True,
                        help="photon-transfer frames, two per pair, in order")
    parser.add_argument("--dark", type=Path, nargs=2, required=True,
                        help="a dark pair at the same settings")
    parser.add_argument("--csv", type=Path, help="write the per-frame table here")
    parser.add_argument("--summary", type=Path,
                        help="write the table averaged per series here")
    args = parser.parse_args()
    if any(len(s) < 2 for s in args.series):
        raise SystemExit("--series takes a label and at least one frame")
    series = {s[0]: [Path(p) for p in s[1:]] for s in args.series}
    frames = list(dict.fromkeys(
        args.frames + [p for paths in series.values() for p in paths]))
    if not frames:
        raise SystemExit("no frames given")
    if args.summary and not series:
        raise SystemExit("--summary needs the frames grouped with --series")

    k = conversion(args.pairs, args.dark)
    f = filter_factor()
    print(f"conversion {k:.2f} DN per photoelectron, residual filter factor {f:.3f}")

    rois = json.loads(args.rois.read_text())
    rows = {}
    for path in frames:
        plane, span = green_plane(path)
        card = averaged(plane, rois.values())
        floor = averaged(plane, CORNERS.values())
        level_dn = card["mean"] * span
        electrons = level_dn / k
        shot = f * np.sqrt(k * level_dn) / span
        camera = float(np.hypot(shot, floor["noise_sd"]))
        left = float(np.sqrt(max(card["noise_sd"] ** 2 - camera ** 2, 0.0)))
        row = {"file": path.name, "level": card["mean"], "electrons": electrons,
               "noise_sd": card["noise_sd"], "corner_sd": floor["noise_sd"],
               "camera_sd": camera, "unexplained_sd": left,
               "noise_rel": card["noise_sd"] / card["mean"],
               "camera_rel": camera / card["mean"],
               "camera_share": min(camera ** 2 / card["noise_sd"] ** 2, 1.0),
               "lag1": card["lag1"]}
        rows[path] = row
        print(f"{path.name:34s} level {row['level']:.5f}  e- {electrons:6.1f}  "
              f"sd {row['noise_sd'] * 1e3:.3f}  corner {row['corner_sd'] * 1e3:.3f}  "
              f"camera {camera * 1e3:.3f}  left {left * 1e3:.3f}  "
              f"lag1 {row['lag1']:+.3f}")

    if args.csv:
        write_csv(args.csv, list(rows.values()))
    if args.summary:
        write_csv(args.summary, per_series(rows, series))
    return 0


def per_series(rows: dict, series: dict) -> List[dict]:
    """Rows averaged over the frames of each series, in the order given."""
    out = []
    for label, paths in series.items():
        group = [rows[p] for p in paths]
        mean = {k: float(np.mean([r[k] for r in group]))
                for k in group[0] if k != "file"}
        out.append({"series": label, "frames": len(group), **mean})
    return out


def write_csv(path: Path, rows: List[dict]) -> None:
    with path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    raise SystemExit(main())
