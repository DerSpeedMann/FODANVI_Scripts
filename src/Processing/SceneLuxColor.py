"""
Scene Lux Color

Finds the screen color that reproduces a scene's spectral signature, so a
SceneLux calibration can be shot under light of the same character as the
scene it calibrates.

    SceneLuxColor.py estimate --signal scene/*.NEF --noise dark/*.NEF \\
        --red r/*.NEF --green g/*.NEF --blue b/*.NEF --record color.json

    SceneLuxColor.py refine --record color.json --verify guess/*.NEF

WHY THIS EXISTS

y_mid, the raw level a metered-correct mid gray reaches, is not a constant of
the camera body. The meter integrates all the light reaching it while the
analysis samples one CFA channel, so the two disagree by however much the
illuminant's spectrum departs from what the meter was characterised against.
Measured on one body across six screen colors, y_mid spanned a factor of 7.
A calibration shot under the wrong color therefore scales the result by
whatever that factor happens to be, silently.

The fix is to shoot the calibration under the scene's own color. This script
derives that color from the scene itself and reports a screen RGB to display.

METHOD

A display has three primaries, so the camera's response to it is spanned by
three vectors. Photograph the card under each primary at full drive and the
per-primary camera responses form the columns of a 3x3 matrix M: drive the
display with linear amounts d and the camera sees M d.

The scene's own signature is its net response, signal minus dark, in the same
three camera channels. Call it c. Solving M d = c gives the drive that makes
the display look to this camera like the scene does. Only the direction of c
matters, since the exposure is free, so d is scaled to put its largest
component at full drive and the display is then as bright as it can be.

WHAT IS AND IS NOT MODELLED

The solve is exact in camera-channel space: three channels, three primaries.
What it cannot capture is metamerism. Two spectra that produce identical
camera responses are identical as far as this camera is concerned and may
still differ to the meter, which is a different sensor with a different
response. Matching in camera space is the best available proxy, not a
guarantee, and it is the reason the refine step exists.

The other approximation is the display transfer function, assumed sRGB. A
real panel departs from it, more so near black. That error lands in the drive
values rather than in M, which is measured at full drive only.

REFINE

Shoot the card under the suggested color and pass those frames to `refine`.
It compares what the camera actually saw against the target, reports the
disagreement per channel ratio, and corrects the drive by the same factor in
the opposite direction:

    d_new = d_guess * (M^-1 c_target) / (M^-1 c_measured)

That is one Newton step on whatever the model got wrong, whether panel gamma,
primary drift or the metamerism above, without needing to know which. Repeat
until the reported disagreement stops falling; two rounds is usually enough,
and the floor is set by how repeatably the camera meters the scene.

SAMPLING

Regions are the SceneLux rectangles, and must be: the derived color is only
meaningful for the measurement it calibrates, and sampling a different part
of the frame answers a different question. On one dataset a central crop and
the SceneLux boxes disagreed by 5% in R/G, which is larger than the match
this script is trying to achieve.

DARK FRAMES

Dark current scales with exposure, so a dark frame only describes frames of
its own exposure time. The script subtracts the darks from the scene frames
and refuses if the two disagree on exposure. Primary and verification frames
are bright and short; nothing is subtracted from them.
"""

import argparse
import glob
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Sequence

import numpy as np
import rawpy

from SceneLux import DEFAULT_ROIS, read_dng_tags, roi_pixels

CHANNELS = ("R", "G", "B")

# Bayer indices in rawpy's raw_colors: 1 and 3 are the two greens, which are
# averaged together because lux is defined against a photopic curve that
# neither green alone represents better than the pair.
BAYER = {"R": (0,), "G": (1, 3), "B": (2,)}

PRIMARY_FLAG = {"R": "red", "G": "green", "B": "blue", "W": "white"}

# What is photographed of the display. R, G and B are the basis. W is
# not a fourth basis vector, since three primaries already span the
# space; it is the one capture able to falsify the model.
REFERENCES = ("R", "G", "B", "W")

# Percent by which the *chromatic* part of white may depart from the sum of
# the primaries before the linear model is called unsafe. The uniform part is
# not bounded, because the solve is scale-free and a uniform error cancels.
ADDITIVITY_TOLERANCE = 3.0


def srgb_encode(x: np.ndarray) -> np.ndarray:
    """Linear 0..1 to sRGB 0..1 (IEC 61966-2-1)."""
    x = np.clip(x, 0.0, 1.0)
    return np.where(x <= 0.0031308, 12.92 * x, 1.055 * x ** (1 / 2.4) - 0.055)


def srgb_decode(v: np.ndarray) -> np.ndarray:
    """sRGB 0..1 to linear 0..1."""
    v = np.clip(v, 0.0, 1.0)
    return np.where(v <= 0.04045, v / 12.92, ((v + 0.055) / 1.055) ** 2.4)


def measure(path: Path, rois: Dict[str, Sequence[float]]) -> Dict[str, Any]:
    """
    Mean linear level per CFA channel, averaged over the ROI rectangles.

    Mean rather than median, unlike SceneLux's y_card: this is a color ratio
    between channels of the same region, and a median taken per channel over
    a region containing printed lines biases each channel differently.
    """
    with rawpy.imread(str(path)) as r:
        raw = r.raw_image_visible.astype(np.float64)
        colors = r.raw_colors_visible
        blacks = np.array(r.black_level_per_channel, dtype=np.float64)
        white = float(r.white_level)

    # Per-channel black in both terms, as SceneLux does. The levels are often
    # equal across channels, but where they are not, a mean in the denominator
    # would scale the channels differently and bias the very ratio this script
    # exists to measure.
    black = blacks[colors]
    linear = (raw - black) / (white - black)

    per_roi = {}
    for name, roi in rois.items():
        x0, x1, y0, y1 = roi_pixels(linear.shape, roi)
        patch, cpatch = linear[y0:y1, x0:x1], colors[y0:y1, x0:x1]
        per_roi[name] = {c: float(patch[np.isin(cpatch, BAYER[c])].mean())
                         for c in CHANNELS}

    level = {c: float(np.mean([v[c] for v in per_roi.values()])) for c in CHANNELS}
    exif = read_dng_tags(path)
    clipped = float(np.mean(raw >= white * 0.99))
    return {
        "file": path.name,
        "exif": exif,
        "clipped_fraction": clipped,
        "rois": per_roi,
        "level": level,
    }


def settings(frames: List[Dict[str, Any]], what: str) -> Dict[str, float]:
    """Exposure, aperture and ISO, once, refusing a set that disagrees."""
    keys = ("exposure_time", "f_number", "iso")
    seen = {k: {f["exif"][k] for f in frames} for k in keys}
    for k, values in seen.items():
        if len(values) != 1:
            raise SystemExit(
                f"{what}: frames disagree on {k} ({sorted(values)}). "
                "Every frame in a set has to share its exposure settings, "
                "since the levels are compared directly.")
    return {k: next(iter(v)) for k, v in seen.items()}


def scale(frame: Dict[str, Any]) -> float:
    """Factor turning a raw level into a response per unit luminance."""
    e = frame["exif"]
    return e["f_number"] ** 2 / (e["exposure_time"] * e["iso"])


def response(frames: List[Dict[str, Any]], what: str,
             dark: List[Dict[str, Any]] = None) -> np.ndarray:
    """
    Camera response per unit scene luminance, as a 3-vector.

    Signal goes as t*S/N^2, so dividing it out makes frames shot at different
    settings comparable. That matters even within one set: the camera meters
    each calibration frame on its own and routinely picks a different shutter
    for two frames of the same target, so each frame is normalised before
    they are averaged.

    Dark is different. It is an additive offset that grows with exposure
    rather than part of the signal, so it has to come off in raw levels,
    before normalising, and only from frames of its own exposure time.
    """
    if not dark:
        return np.mean([[f["level"][c] * scale(f) for c in CHANNELS]
                        for f in frames], axis=0)

    s = settings(frames, what)
    d = settings(dark, what + " dark")
    if d["exposure_time"] != s["exposure_time"]:
        raise SystemExit(
            f"{what}: dark frames are {d['exposure_time']} s but the frames "
            f"are {s['exposure_time']} s. Dark current scales with exposure, "
            "so darks only describe their own exposure time.")
    level = np.array([np.mean([f["level"][c] for f in frames]) for c in CHANNELS])
    level -= np.array([np.mean([f["level"][c] for f in dark]) for c in CHANNELS])
    return level * s["f_number"] ** 2 / (s["exposure_time"] * s["iso"])


def ratios(v: np.ndarray) -> Dict[str, float]:
    """R/G and B/G. Green is the reference channel, as everywhere else here."""
    return {"R/G": float(v[0] / v[1]), "B/G": float(v[2] / v[1])}


def solve(matrix: np.ndarray, target: np.ndarray) -> Dict[str, Any]:
    """
    Linear display drive reproducing `target`, scaled to full brightness.

    Only the direction of target matters, so the solution is normalised to put
    its largest component at full drive. A negative component means the scene
    sits outside the display gamut and cannot be matched; it is clipped and
    reported rather than silently passed on.
    """
    drive = np.linalg.solve(matrix, target)
    out_of_gamut = bool((drive < 0).any())
    drive = np.clip(drive, 0.0, None)
    if not drive.any():
        raise SystemExit("no non-negative drive reproduces this target.")
    drive = drive / drive.max()

    code = np.round(srgb_encode(drive) * 255).astype(int)
    return {
        "drive_linear": [float(x) for x in drive],
        "rgb": [int(x) for x in code],
        "out_of_gamut": out_of_gamut,
        # Both through the model, so their difference isolates what rounding
        # to 8-bit costs. Against a measurement neither is a prediction: the
        # model is exactly what a measurement disagrees with.
        "predicted": ratios(matrix @ srgb_decode(code / 255.0)),
        "predicted_unquantized": ratios(matrix @ drive),
    }


def check_additivity(matrix, white):
    """
    Whether the display is the sum of its primaries, split into the part that
    matters and the part that does not.

    An additive display driven at full white produces what its three
    primaries produce together, so M @ [1,1,1] has to reproduce the measured
    white. Nothing in the solve tests this, which is why white is captured:
    it is the only frame that can show the model is wrong rather than merely
    imprecise.

    The disagreement splits in two, and only one half is a problem. A uniform
    error, every channel off by the same factor, is a brightness difference,
    and the solve is scale-free: it matches the direction of a response and
    lets exposure carry the magnitude, so a uniform factor cancels exactly.
    Televisions limit backlight on bright content, so a full-white frame is
    routinely dimmer than three primaries measured one at a time, by ten
    percent or more. That is expected and harmless here.

    What is not harmless is the part left after the uniform factor is divided
    out, because that is the display failing to mix its primaries the way the
    model assumes. A white subpixel does it, since white then comes from a
    fourth emitter the primaries never excite. So does any per-channel
    clipping. That error does not cancel, and no amount of refining fixes it.
    """
    predicted = matrix @ np.ones(3)
    ratio = white / predicted
    # Geometric mean, because these are multiplicative factors; an arithmetic
    # mean would not divide out cleanly.
    uniform = float(np.exp(np.log(ratio).mean()))
    chromatic = {c: float((ratio[i] / uniform - 1) * 100)
                 for i, c in enumerate(CHANNELS)}
    worst = max(abs(v) for v in chromatic.values())
    return {
        "measured": [float(x) for x in white],
        "predicted": [float(x) for x in predicted],
        "total_percent": {c: float((ratio[i] - 1) * 100)
                          for i, c in enumerate(CHANNELS)},
        "uniform_percent": float((uniform - 1) * 100),
        "chromatic_percent": chromatic,
        "worst_chromatic_percent": worst,
        "additive": bool(worst <= ADDITIVITY_TOLERANCE),
    }


def collect(patterns: Sequence[str], rois, what: str) -> List[Dict[str, Any]]:
    files = sorted({Path(p) for pat in patterns for p in glob.glob(pat)})
    if not files:
        raise SystemExit(f"{what}: no files matched {list(patterns)}")
    return [measure(f, rois) for f in files]


def load_rois(arg) -> Dict[str, Sequence[float]]:
    if arg in (None, "default"):
        return dict(DEFAULT_ROIS)
    return json.loads(Path(arg).read_text())


def table(rows: Sequence[Sequence[Any]], head: Sequence[str]) -> None:
    widths = [max(len(str(r[i])) for r in (head, *rows)) for i in range(len(head))]
    print("  ".join(str(h).ljust(w) for h, w in zip(head, widths)))
    for r in rows:
        print("  ".join(str(c).ljust(w) for c, w in zip(r, widths)))


def report_match(measured: Dict[str, float], target: Dict[str, float]) -> Dict[str, float]:
    """Disagreement per ratio, signed, as a percentage of the target."""
    return {k: float((measured[k] / target[k] - 1) * 100) for k in target}


def cmd_estimate(args) -> int:
    rois = load_rois(args.rois)

    signal = collect(args.signal, rois, "signal")
    noise = collect(args.noise, rois, "noise") if args.noise else None
    prim = {c: collect(getattr(args, PRIMARY_FLAG[c]), rois, c)
            for c in REFERENCES}

    target = response(signal, "signal", noise)
    if (target <= 0).any():
        raise SystemExit(
            "a channel came out at or below its dark level, so the scene has "
            "no measurable signal there. Longer exposure or a brighter scene.")

    matrix = np.column_stack([response(prim[c], c) for c in CHANNELS])
    result = solve(matrix, target)

    print(f"scene, {len(signal)} frames"
          + (f" less {len(noise)} dark frames" if noise else " (no dark frames)"))
    table([[c, f"{target[i]:.6e}"] for i, c in enumerate(CHANNELS)],
          ["channel", "net response"])
    t = ratios(target)
    print(f"  target   R/G {t['R/G']:.3f}   B/G {t['B/G']:.3f}")

    print("\ndisplay primaries, camera response per unit luminance")
    table([[c] + [f"{matrix[i, j]:.4e}" for i in range(3)]
           for j, c in enumerate(CHANNELS)],
          ["primary", "cam R", "cam G", "cam B"])

    add = check_additivity(matrix, response(prim["W"], "W"))
    print("")
    print("additivity, measured white against the sum of the primaries")
    table([[c, f"{add['measured'][i]:.4e}", f"{add['predicted'][i]:.4e}",
            f"{add['total_percent'][c]:+.1f} %",
            f"{add['chromatic_percent'][c]:+.1f} %"]
           for i, c in enumerate(CHANNELS)],
          ["channel", "measured", "predicted", "total", "chromatic"])
    print(f"  uniform component {add['uniform_percent']:+.1f} %, which "
          "cancels: the solve matches the")
    print("  direction of a response, not its magnitude. A television "
          "dimming its backlight")
    print("  on bright content shows up here and is harmless.")
    if add["additive"]:
        print(f"  chromatic component within {ADDITIVITY_TOLERANCE:g} %, so "
              "the primaries mix as the model")
        print("  assumes and the suggestion below stands.")
    else:
        print(f"  WARNING: chromatic component {add['worst_chromatic_percent']:.1f} %, "
              f"beyond the {ADDITIVITY_TOLERANCE:g} % this model tolerates.")
        print("           The display does not mix its primaries additively, "
              "which a white")
        print("           subpixel or per-channel clipping would both cause. "
              "Check the primary")
        print("           frames for clipping, and if it persists this "
              "display cannot be")
        print("           matched this way: the suggestion below is unsound.")

    r, g, b = result["rgb"]
    p = result["predicted"]
    print(f"\nsuggested screen RGB ({r}, {g}, {b})")
    print(f"  predicted  R/G {p['R/G']:.3f}   B/G {p['B/G']:.3f}")
    d = report_match(p, t)
    print(f"  against target  R/G {d['R/G']:+.1f} %   B/G {d['B/G']:+.1f} %"
          "   (model only, not a measurement)")
    if result["out_of_gamut"]:
        print("  WARNING: the scene falls outside the display gamut. The drive "
              "was clipped,\n           so the match above is the closest the "
              "display can reach.")

    record = {
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "rois": {k: list(v) for k, v in rois.items()},
        "target": {"response": [float(x) for x in target], "ratios": t},
        "matrix": [[float(x) for x in row] for row in matrix],
        "additivity": add,
        "suggestion": result,
        "history": [],
        "frames": {"signal": signal, "noise": noise or [],
                   **{PRIMARY_FLAG[c]: prim[c] for c in REFERENCES}},
    }
    if args.record:
        Path(args.record).write_text(json.dumps(record, indent=2))
        print(f"\nwrote {args.record}")
    return 0


def cmd_refine(args) -> int:
    record = json.loads(Path(args.record).read_text())
    rois = {k: tuple(v) for k, v in record["rois"].items()}
    matrix = np.array(record["matrix"])
    target = np.array(record["target"]["response"])
    t = record["target"]["ratios"]

    guess = record["suggestion"]
    if args.shot_at:
        # What the frames were actually displayed under, which is not always
        # what the record last suggested: a value may have been rounded, typed
        # by hand, or carried over from an earlier round. The correction is
        # relative to the drive that produced these frames, so taking the
        # record's word for it would silently correct from the wrong place.
        shot = np.array(args.shot_at, dtype=float)
        drive = srgb_decode(shot / 255.0)
        guess = {"rgb": [int(x) for x in shot]}
    else:
        drive = np.array(guess["drive_linear"])

    verify = collect(args.verify, rois, "verify")
    measured = response(verify, "verify")
    m = ratios(measured)

    print(f"verification, {len(verify)} frames under RGB "
          f"({', '.join(str(x) for x in guess['rgb'])})")
    print(f"  measured R/G {m['R/G']:.3f}   B/G {m['B/G']:.3f}")
    print(f"  target   R/G {t['R/G']:.3f}   B/G {t['B/G']:.3f}")
    d = report_match(m, t)
    print(f"  diff     R/G {d['R/G']:+.1f} %   B/G {d['B/G']:+.1f} %")

    # One Newton step in drive space: the model said this drive would give
    # what we wanted, it gave something else, so correct by the ratio of the
    # drives the model maps those two responses back to.
    want = np.linalg.solve(matrix, target)
    got = np.linalg.solve(matrix, measured)
    if (got <= 0).any() or (want <= 0).any():
        raise SystemExit(
            "the correction is undefined: the model maps one of these "
            "responses to a negative drive, which means the measurement sits "
            "outside the gamut the primaries span. Re-measure the primaries.")

    corrected = solve(matrix, matrix @ (drive * want / got))
    r, g, b = corrected["rgb"]
    print(f"\ncorrected screen RGB ({r}, {g}, {b})")
    print(f"  expect to measure  R/G {t['R/G']:.3f}   B/G {t['B/G']:.3f}")
    print("  the correction is calibrated against this measurement, so the "
          "target is\n  what it aims at; no model prediction is quoted here "
          "because the model is\n  what the measurement just disagreed with.")
    q = report_match(corrected["predicted"], corrected["predicted_unquantized"])
    if max(abs(v) for v in q.values()) >= 0.5:
        print(f"  rounding to 8-bit shifts it by R/G {q['R/G']:+.1f} %"
              f"   B/G {q['B/G']:+.1f} %")

    if max(abs(v) for v in d.values()) <= args.tolerance:
        print(f"\nwithin {args.tolerance:g} %: the previous value is good "
              "enough, no need to reshoot.")
    else:
        print(f"\noutside {args.tolerance:g} %: shoot the card under the "
              "corrected value and run refine again.")

    record.setdefault("history", []).append({
        "rgb": guess["rgb"],
        "measured_ratios": m,
        "diff_percent": d,
        "frames": [f["file"] for f in verify],
    })
    record["suggestion"] = corrected
    if not args.dry_run:
        Path(args.record).write_text(json.dumps(record, indent=2))
        print(f"wrote {args.record}, round {len(record['history'])}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Match a display color to a scene's spectral signature.")
    sub = parser.add_subparsers(dest="command", required=True)

    e = sub.add_parser("estimate", help="derive the screen color from the scene")
    e.add_argument("--signal", nargs="+", required=True,
                   help="raw frames of the scene under its own light")
    e.add_argument("--noise", nargs="+",
                   help="lens-covered frames at the same exposure as --signal")
    for c in REFERENCES:
        e.add_argument(f"--{PRIMARY_FLAG[c]}", nargs="+", required=True,
                       dest=PRIMARY_FLAG[c],
                       help=("frames of the card lit by full white, which "
                             "checks that the display is additive"
                             if c == "W" else
                             "frames of the card lit by the display's "
                             f"{PRIMARY_FLAG[c]} primary at full drive"))
    e.add_argument("--rois", nargs="?", const="default",
                   help="JSON of {name: [cx, cy, half_w, half_h]}; "
                        "omitted or bare uses the SceneLux defaults")
    e.add_argument("--record", help="write a JSON record here, needed by refine")
    e.set_defaults(func=cmd_estimate)

    r = sub.add_parser("refine", help="correct the color from a test capture")
    r.add_argument("--record", required=True, help="record written by estimate")
    r.add_argument("--verify", nargs="+", required=True,
                   help="raw frames of the card under the suggested color")
    r.add_argument("--shot-at", nargs=3, type=int, metavar=("R", "G", "B"),
                   help="what the verify frames were actually displayed "
                        "under, if not the record's current suggestion")
    r.add_argument("--tolerance", type=float, default=3.0,
                   help="percent disagreement treated as close enough")
    r.add_argument("--dry-run", action="store_true",
                   help="report without updating the record")
    r.set_defaults(func=cmd_refine)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
