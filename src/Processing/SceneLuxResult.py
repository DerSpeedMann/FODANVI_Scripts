"""
Scene Lux Result

Turns two SceneLux records into a dark-subtracted illuminance result.

SceneLux measures one frame at a time and knows nothing about pairs of
frames, so the dark subtraction lives here instead: it needs two sets of
captures and a model across them, which is a different job from sampling a
single card.

    SceneLux ... lens-covered frames  --record dark.json
    SceneLux ... lens-clear frames    --record measure.json
    SceneLuxResult --dark dark.json --measure measure.json --csv table.csv

Dark current rises while the sensor works and falls when it idles, so a
single averaged dark only describes the moment it was taken. Covered frames
shot either side of the measurement bracket it, and a straight line through
them in capture time gives each measurement frame the dark level for its own
timestamp. That is why the records carry EXIF timestamps: everything here is
derived from them, with no access to the raw files.
"""

import argparse
import csv
import json
import math
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

EXIF_TIME = "%Y:%m:%d %H:%M:%S"


def seconds(capture: Dict[str, Any]) -> float:
    """Absolute capture time. The full date is parsed rather than the clock
    time alone so a session running past midnight stays monotonic."""
    stamp = datetime.strptime(capture["exif"]["datetime"], EXIF_TIME)
    return stamp.timestamp()


def fit_line(xs: List[float], ys: List[float]):
    n = len(xs)
    if n < 2 or max(xs) == min(xs):
        return 0.0, sum(ys) / n
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    slope = sxy / sxx
    return slope, my - slope * mx


def load(path: Path) -> List[Dict[str, Any]]:
    return json.loads(path.read_text())["captures"]


def write_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {path}")


def plot(path: Path, table: List[Dict[str, Any]]) -> None:
    """The same rows the CSV holds, drawn. Every series is read out of the
    table so the figure cannot drift away from the numbers beside it. The
    drift line is just dark_model_dn, which lies on the fit by construction."""
    import matplotlib
    matplotlib.use("Agg")           # never displays, and Qt fails when piped
    from matplotlib import pyplot as plt

    def series(kind, key):
        rs = [r for r in table if r["kind"] == kind]
        return [r["t_s"] for r in rs], [r[key] for r in rs]

    fig, ax = plt.subplots(figsize=(7, 4))
    t = [r["t_s"] for r in table]
    fit = [r["dark_model_dn"] for r in table]
    se = [r["dark_model_se_dn"] for r in table]
    ax.fill_between(t, [f - e for f, e in zip(fit, se)],
                    [f + e for f, e in zip(fit, se)],
                    color="tab:blue", alpha=0.18, lw=0,
                    label="drift model, +/-1 standard error")
    ax.plot(t, fit, color="tab:blue", lw=1, label="linear drift model")
    ax.plot(*series("dark", "y_card_dn"), "o", color="tab:blue",
            label=f"lens-covered frames (n={sum(r['kind'] == 'dark' for r in table)})")
    mt, mfit = series("measure", "dark_model_dn")
    ax.errorbar(mt, mfit,
                yerr=[r["dark_model_se_dn"] for r in table if r["kind"] == "measure"],
                fmt="x", ms=9, color="tab:red", capsize=4, lw=1,
                label="interpolated for measurement")
    ax.errorbar(*series("measure", "y_card_dn"),
                yerr=[r["dark_model_se_dn"] for r in table if r["kind"] == "measure"],
                fmt="s", color="tab:green", capsize=4, lw=1,
                label="measurement frames")
    ax.set_xlabel("time since first frame (s)")
    ax.set_ylabel(f"{table[0]['channel']}-channel level (DN)")
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=150)
    plt.close(fig)
    print(f"wrote {path}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Dark-subtracted illuminance from two SceneLux records.")
    parser.add_argument("--dark", type=Path, required=True,
                        help="SceneLux record of the lens-covered frames")
    parser.add_argument("--measure", type=Path, required=True,
                        help="SceneLux record of the measurement frames")
    parser.add_argument("--csv", type=Path,
                        help="write the result table here, every frame in one file")
    parser.add_argument("--out", type=Path, help="write a JSON log here")
    parser.add_argument("--label", default="", help="name for this run in the table")
    parser.add_argument("--plot", type=Path, help="write the dark model plot here")
    args = parser.parse_args()

    dark, measure = load(args.dark), load(args.measure)

    # A dark frame only describes the measurement frame's offset when both were
    # shot with the same exposure, gain and aperture; otherwise the subtraction
    # is meaningless rather than merely imprecise.
    keys = {"exposure_time", "iso", "f_number"}
    settings = {tuple(sorted((k, c["exif"][k]) for k in keys)) for c in dark + measure}
    if len(settings) > 1:
        for c in dark + measure:
            print(f"  {c['file']}: " + "  ".join(f"{k}={c['exif'][k]}" for k in sorted(keys)))
        raise SystemExit("dark and measurement frames differ in exposure, ISO or f-number")

    # Subtracting a dark sampled on one channel from a measurement sampled on
    # another would be meaningless, so the records have to agree.
    channels = {c["calibration"]["channel"] for c in dark + measure}
    if len(channels) > 1:
        raise SystemExit(f"records mix sampling channels: {sorted(channels)}")

    t0 = min(seconds(c) for c in dark + measure)

    xs = [seconds(c) - t0 for c in dark]
    ys = [c["y_card"] for c in dark]
    slope, intercept = fit_line(xs, ys)
    full_scale = measure[0]["white_level"] - measure[0]["black_level"]
    cal = measure[0]["calibration"]

    def model(x: float) -> float:
        """Fitted dark level at capture time x. The only place the drift model
        is evaluated, so the plot, the table and the lux cannot disagree."""
        return slope * x + intercept

    def row(kind, c, x, constant=None):
        """One frame. delta is the level above the drift model, which is the
        residual for a covered frame and the signal for a measurement one."""
        level = model(x)
        delta = c["y_card"] - level
        return {"label": args.label, "kind": kind, "file": c["file"], "t_s": x,
                "channel": cal["channel"],
                "exposure_s": c["exif"]["exposure_time"],
                "f_number": c["exif"]["f_number"], "iso": c["exif"]["iso"],
                "y_card": c["y_card"], "dark_model": level, "delta": delta,
                "y_card_dn": c["y_card"] * full_scale,
                "dark_model_dn": level * full_scale,
                "delta_dn": delta * full_scale,
                "dark_model_se": None, "dark_model_se_dn": None,
                "constant": constant, "lux": None, "lux_se": None,
                "lux_lo": None, "lux_hi": None}

    dark_rows = [row("dark", c, x) for c, x in zip(dark, xs)]

    # The residual of a covered frame is its delta, so the fit quality is read
    # back off the rows rather than recomputed from the fit inputs.
    residuals = [r["delta"] for r in dark_rows]
    n = len(residuals)
    rms = (sum(r * r for r in residuals) / (n - 2)) ** 0.5 if n > 2 else float("nan")

    mean_x = sum(xs) / len(xs)
    sxx = sum((x - mean_x) ** 2 for x in xs)

    def se_at(x: float) -> float:
        """Standard error of the fitted dark level at time x. Smallest at the
        centroid of the covered frames and growing away from it, which is why
        the measurement is bracketed rather than followed by darks."""
        if n <= 2 or sxx == 0:
            return float("nan")
        return rms * (1 / n + (x - mean_x) ** 2 / sxx) ** 0.5

    rows, luxes = [], []
    for c in measure:
        e = c["exif"]
        constant = (math.pi * cal["K"] * e["f_number"] ** 2
                    / (cal["rho_ref"] * e["iso"] * cal["y_mid"]))
        r = row("measure", c, seconds(c) - t0, constant=constant)
        r["lux"] = constant * r["delta"] / e["exposure_time"]
        r["lux_se"] = constant * se_at(r["t_s"]) / e["exposure_time"]
        r["lux_lo"] = r["lux"] - r["lux_se"]
        r["lux_hi"] = r["lux"] + r["lux_se"]
        luxes.append(r["lux"])
        rows.append(r)

    for r in dark_rows + rows:
        r["dark_model_se"] = se_at(r["t_s"])
        r["dark_model_se_dn"] = r["dark_model_se"] * full_scale

    mean_lux = sum(luxes) / len(luxes)
    spread = (max(luxes) - min(luxes)) / mean_lux if len(luxes) > 1 else 0.0

    # The same fit is subtracted from every measurement frame, so its error is
    # common to them and does not average away; the frame-to-frame scatter does.
    t_mean = sum(r["t_s"] for r in rows) / len(rows)
    se_model = rows[0]["constant"] * se_at(t_mean) / rows[0]["exposure_s"]
    if len(luxes) > 1:
        var = sum((v - mean_lux) ** 2 for v in luxes) / (len(luxes) - 1)
        se_scatter = (var / len(luxes)) ** 0.5
    else:
        se_scatter = float("nan")
    se_total = (se_model ** 2 + se_scatter ** 2) ** 0.5

    table = sorted(dark_rows + rows, key=lambda r: r["t_s"])

    print(f"dark model   {len(dark)} frames   slope {slope * 60:+.3e}/min   "
          f"intercept {intercept:.6f}   residual rms {rms * full_scale:.3f} DN")
    print(f"{'kind':<8}{'file':<38}{'t_s':>5}{'y_card':>9}{'dark':>8}"
          f"{'+/-':>7}{'delta':>9}{'lux':>12}{'lux low':>11}{'lux high':>11}")
    for r in table:
        def fmt(key, places=3):
            v = r[key]
            return f"{v:.{places}e}" if v is not None else ""
        print(f"{r['kind']:<8}{r['file']:<38}{r['t_s']:>5.0f}"
              f"{r['y_card_dn']:>9.3f}{r['dark_model_dn']:>8.3f}"
              f"{r['dark_model_se_dn']:>7.3f}{r['delta_dn']:>9.3f}"
              f"{fmt('lux'):>12}{fmt('lux_lo'):>11}{fmt('lux_hi'):>11}")
    print("levels in DN, +/- after dark is the fit standard error there;"
          " lux low/high span that frame's own error")
    print(f"\nmean {mean_lux:.3e} lux   spread {100 * spread:.1f}% across "
          f"{len(luxes)} measurement frames")
    print(f"statistical uncertainty  dark model +/-{se_model:.2e} "
          f"({100 * se_model / mean_lux:.1f}%)   frame scatter +/-{se_scatter:.2e} "
          f"({100 * se_scatter / mean_lux:.1f}%)   combined +/-{se_total:.2e} "
          f"({100 * se_total / mean_lux:.1f}%)")
    print(f"range {mean_lux - se_total:.3e} to {mean_lux + se_total:.3e} lux "
          f"= {mean_lux:.3e} +/- {se_total:.2e}")
    print("this covers the dark subtraction only, not rho or y_mid")

    if args.csv:
        write_csv(args.csv, table)

    if args.plot:
        plot(args.plot, table)

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps({
            "label": args.label,
            "sources": {"dark": str(args.dark), "measure": str(args.measure)},
            "calibration": cal,
            "dark_model": {"slope_per_second": slope, "intercept": intercept,
                           "residual_rms": rms, "n_frames": len(dark),
                           "full_scale_dn": full_scale,
                           "residual_rms_dn": rms * full_scale},
            "frames": table,
            "result": {"lux_mean": mean_lux, "lux_spread": spread,
                       "lux_se_dark_model": se_model,
                       "lux_se_frame_scatter": se_scatter,
                       "lux_se_combined": se_total,
                       "lux_lo": mean_lux - se_total,
                       "lux_hi": mean_lux + se_total},
        }, indent=2))
        print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
