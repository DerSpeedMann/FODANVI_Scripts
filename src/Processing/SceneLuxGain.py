"""
Scene Lux Gain

Luminance gain of a night vision device, per frame, from a SceneLux record of
its eyepiece and the scene luminance measured without it.

    SceneLuxGain.py nvg_s5_record.json --scene-luminance 2.847e-05 \\
        --csv gain_table.csv --plot gain_model.png

An intensifier screen emits rather than reflects, so the quantity to compare
is luminance rather than illuminance. SceneLux reports E, the illuminance that
would fall on a card of reflectance rho to produce the level it measured, and
L = E*rho/pi recovers the luminance. Expanded, that is

    L = K * N^2 / (S * y_mid) * y_card / t

in which rho has cancelled, so the assumed card reflectance does not affect
the result. The ratio against the scene luminance is the gain.

Frames are reported one by one, in capture order, and nothing is grouped or
averaged. Which frames share a setting is a fact about how they were shot and
is not in the record, so the script would only be guessing at it. Grouping
belongs wherever that fact is known.
"""

import argparse
import csv
import json
import math
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

EXIF_TIME = "%Y:%m:%d %H:%M:%S"


def luminance(capture: Dict[str, Any]) -> float:
    """Screen luminance in cd/m2, from the record alone."""
    cal, e = capture["calibration"], capture["exif"]
    return (cal["K"] * e["f_number"] ** 2
            / (e["iso"] * cal["y_mid"])
            * capture["y_card"] / e["exposure_time"])


def rows_for(record: Path, scene_l: float) -> List[Dict[str, Any]]:
    caps = json.loads(record.read_text())["captures"]
    stamps = [datetime.strptime(c["exif"]["datetime"], EXIF_TIME).timestamp()
              for c in caps]
    first = min(stamps)
    rows = []
    for c, t in zip(caps, stamps):
        e = c["exif"]
        lum = luminance(c)
        rows.append({
            "file": Path(c["file"].replace(chr(92), "/")).name,
            "time": e.get("datetime", "")[11:],
            "t_s": t - first,
            "exposure_s": e["exposure_time"],
            "f_number": e["f_number"],
            "iso": e["iso"],
            "y_card": c["y_card"],
            "y_card_spread": c.get("y_card_spread", ""),
            "screen_cd_m2": lum,
            "scene_cd_m2": scene_l,
            "gain": lum / scene_l,
        })
    return rows


def nice_ticks(lo: float, hi: float) -> List[float]:
    """Round tick values spanning lo to hi, on a 1-2-5 sequence per decade."""
    out, decade = [], 10.0 ** math.floor(math.log10(lo))
    while decade <= hi:
        for step in (1, 2, 5):
            v = step * decade
            if lo / 1.3 <= v <= hi * 1.3:
                out.append(v)
        decade *= 10
    return out


def plot(path: Path, rows: List[Dict[str, Any]], scene_l: float) -> None:
    """Gain per frame in capture order, for checking a run at a glance.

    Log scale, because a gain control covers more than an order of magnitude
    and a linear axis would flatten everything below the top setting onto the
    baseline. Ticks are placed on a 1-2-5 sequence rather than left to the
    default, which labels only the decades and crowds 900 against 1000.
    """
    import matplotlib
    matplotlib.use("Agg")           # never displays, and Qt fails when piped
    from matplotlib import pyplot as plt
    from matplotlib.ticker import FixedLocator, NullLocator, ScalarFormatter

    t = [r["t_s"] for r in rows]
    g = [r["gain"] for r in rows]

    fig, ax = plt.subplots(figsize=(7, 4))
    ax.plot(t, g, "-", lw=0.6, color="0.7", zorder=0)
    ax.plot(t, g, "o", ms=7, color="tab:blue")
    ax.set_yscale("log")
    ax.yaxis.set_major_locator(FixedLocator(nice_ticks(min(g), max(g))))
    ax.yaxis.set_minor_locator(NullLocator())
    ax.yaxis.set_major_formatter(ScalarFormatter())
    ax.set_xlabel("time since first frame (s)")
    ax.set_ylabel(f"gain, screen / scene luminance\n(scene {scene_l:.3e} cd/m$^2$)")
    ax.grid(alpha=0.3, which="both")
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=150)
    plt.close(fig)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Per-frame luminance gain from a SceneLux record.")
    parser.add_argument("record", type=Path,
                        help="SceneLux record of the frames through the device")
    parser.add_argument("--scene-luminance", type=float, required=True,
                        help="luminance of the same scene without the device, cd/m2")
    parser.add_argument("--csv", type=Path, help="write the per-frame table here")
    parser.add_argument("--plot", type=Path, help="write the gain plot here")
    args = parser.parse_args()

    rows = rows_for(args.record, args.scene_luminance)

    print(f"scene luminance {args.scene_luminance:.3e} cd/m2, "
          f"{len(rows)} frames from {args.record.name}")
    print(f"{'file':<38}{'t_s':>6}{'exp_s':>8}{'f':>6}{'iso':>6}"
          f"{'y_card':>10}{'spread':>9}{'screen':>10}{'gain':>8}")
    for r in rows:
        spread = f"{100 * r['y_card_spread']:.1f}%" if r["y_card_spread"] != "" else ""
        print(f"{r['file']:<38}{r['t_s']:>6.0f}{r['exposure_s']:>8.4g}"
              f"{r['f_number']:>6.1f}{r['iso']:>6}{r['y_card']:>10.5f}"
              f"{spread:>9}{r['screen_cd_m2']:>10.4f}{r['gain']:>8.0f}")

    g = [r["gain"] for r in rows]
    print(f"\n{'range':<38}{'':>6}{'':>8}{'':>6}{'':>6}{'':>10}{'':>9}"
          f"{min(r['screen_cd_m2'] for r in rows):>10.4f}{min(g):>8.0f}")
    print(f"{'':<38}{'':>6}{'':>8}{'':>6}{'':>6}{'':>10}{'to':>9}"
          f"{max(r['screen_cd_m2'] for r in rows):>10.4f}{max(g):>8.0f}")
    print(f"a factor of {max(g) / min(g):.1f}")

    if args.csv:
        args.csv.parent.mkdir(parents=True, exist_ok=True)
        with open(args.csv, "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
        print(f"wrote {args.csv}")

    if args.plot:
        plot(args.plot, rows, args.scene_luminance)
        print(f"wrote {args.plot}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
