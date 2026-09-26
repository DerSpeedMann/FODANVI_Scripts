"""
Scene Lux

Estimates scene illuminance from a raw capture of a reference grey card, using
the reflected-light exposure equation of ISO 2720.

    E = pi * K * N^2 / (rho * S * y_mid) * y_card / t

    N, t, S   aperture, exposure time and ISO, read from the DNG
    rho       reflectance of the card, from its manufacturer spec
    y_card    how bright the card came out, 0..1 after black subtraction
    y_mid     how bright the card comes out when correctly exposed

y_card is by default the median of green photosites within a radius of frame
centre. Median because a card carrying printed marks has bright lines that
pull a mean up by tens of percent while leaving a median untouched; green
because it is the CFA channel closest to the photopic V(lambda) curve that lux
is defined by, and the one white balance leaves near unity. Explicit rectangles
are available via --rois as a cross-check.

y_mid is the camera's own anchor and has to be measured once per camera and
ISO: photograph the card filling the frame under the camera's auto-exposure at
EV 0, then run that frame through this script. Whatever y_card it reports is
y_mid, because a metered-correct mid-grey is by definition what "correctly
exposed" means to that meter. It must be extracted exactly as y_card is -
same channel, same radius - or the two do not cancel. The value in DEFAULTS
was measured this way; see the comment there for the camera it belongs to.

Radius is uncritical while the reference and the measurement are framed alike,
since the lens falloff then divides out of y_card/y_mid. It is NOT uncritical
across different framings: falloff reaches 0.6 stops at the frame edge, so a
card that fills the reference but sits small and off-centre in the measurement
needs flat-field correction first.

SOURCE LIGHT

Cameras are built around daylight. Colour matrices, white-balance presets and
the metering that decides "correct exposure" are all characterised against
daylight illuminants, so under a source with a very different spectrum the
camera is working outside what it was tuned for and its response is only
loosely defined. That makes a result like this representative to a degree that
depends on the illuminant - closest to true under daylight, progressively less
so the further the source departs from it.

It shows up here as y_mid moving with the light. Same camera, same card, same
ISO, measured in daylight vs warm incandescent ceiling light:

    sunlight                  R/G 0.44   y_mid 0.174
    ceiling light             R/G 0.95   y_mid 0.110

0.66 stops apart, purely from the illuminant. So shoot the reference under
light of similar spectral character to the scene. Or capture a range of cool
to warm to get a bracket.

Writes a JSON record of every input, region and result, and an overlay image
marking what was measured - the ROI rectangles, or the circle for a radial
median - both intended as published documentation.
"""

import argparse
import glob
import json
import struct
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Tuple

import numpy as np
import rawpy
from PIL import Image, ImageDraw

K_REFLECTED = 12.5          # ISO 2720, permitted range 10.6-13.4

# Camera calibration, measured once (see docstring of calibrate()).
DEFAULTS = {
    "rho_ref": 0.178,       # Lightdow grey side, manufacturer spec +-2%
    # OnePlus 7 Pro @ ISO 3193, metered mid-grey, measured as the median of
    # green pixels within RADIUS of frame centre. y_mid and y_card must be
    # extracted the same way or they do not cancel.
    "y_mid": 0.17414,
    "radius": 0.50,
}

# Normalised (cx, cy, half_w, half_h). Placed in the gaps between the reticle
# arms and close to centre, where lens falloff is smallest.
DEFAULT_ROIS = {
    "q_ul": (0.422, 0.438, 0.015, 0.020),
    "q_ur": (0.578, 0.438, 0.015, 0.020),
    "q_ll": (0.422, 0.562, 0.015, 0.020),
    "q_lr": (0.578, 0.562, 0.015, 0.020),
}

# A ROI whose 99th percentile sits this far above its median may contain a
# printed line. Advisory only: it is driven by noise as much as by content, so
# on a dim frame every ROI trips it. Validate placement on a well-exposed
# reference, then reuse the same rectangles - never let a tool silently drop
# data from a measurement.
LINE_TOLERANCE = 0.35


# TIFF value types: struct code and bytes per element.
TIFF_TYPES = {1: ("B", 1), 2: ("s", 1), 3: ("H", 2), 4: ("I", 4), 5: ("II", 8),
              7: ("B", 1), 9: ("i", 4), 10: ("ii", 8), 11: ("f", 4), 12: ("d", 8)}


def read_dng_tags(path: Path) -> Dict[str, Any]:
    """
    Minimal TIFF/EXIF reader for the handful of tags the calculation needs.

    Decodes by declared type rather than assuming a width: a value of four
    bytes or fewer is stored inside the tag entry, and the bytes after it are
    undefined padding, so reading a 2-byte SHORT as a 4-byte word only works
    while a writer happens to zero them.
    """
    d = path.read_bytes()
    end = "<" if d[:2] == b"II" else ">"
    start, = struct.unpack(end + "I", d[4:8])

    def directory(at):
        out = {}
        count, = struct.unpack(end + "H", d[at:at + 2])
        for i in range(count):
            p = at + 2 + i * 12
            tag, typ, n = struct.unpack(end + "HHI", d[p:p + 8])
            if typ not in TIFF_TYPES:
                continue
            total = TIFF_TYPES[typ][1] * n
            at_value = p + 8 if total <= 4 else struct.unpack(end + "I", d[p + 8:p + 12])[0]
            out[tag] = (typ, n, at_value)
        return out

    tags = directory(start)
    # The Exif pointer is a LONG, so directory() recorded where its value sits
    # rather than the value itself; it has to be read before use. Nikon NEFs
    # keep the exposure tags behind this pointer, DNGs often inline them.
    if 0x8769 in tags:
        at = tags[0x8769][2]
        tags.update(directory(struct.unpack(end + "I", d[at:at + 4])[0]))

    def value(tag):
        if tag not in tags:
            return None
        typ, n, at = tags[tag]
        code, width = TIFF_TYPES[typ]
        if typ == 2:
            return d[at:at + n].split(bytes(1))[0].decode("ascii", "replace")
        if typ in (5, 10):
            num, den = struct.unpack(end + code, d[at:at + width])
            return num / den if den else 0.0
        return struct.unpack(end + code, d[at:at + width])[0]

    return {
        "exposure_time": value(0x829A),
        "f_number": value(0x829D),
        "iso": value(0x8827),
        "focal_length": value(0x920A),
        "datetime": value(0x0132),
    }


def roi_pixels(shape: Tuple[int, int], roi) -> Tuple[int, int, int, int]:
    h, w = shape
    cx, cy, hw, hh = roi
    return (int((cx - hw) * w), int((cx + hw) * w),
            int((cy - hh) * h), int((cy + hh) * h))


def measure_radial(path: Path, radius: float) -> Dict[str, Any]:
    """
    Median of green pixels within `radius` of frame centre, as a fraction of
    the short side.

    The median rather than the mean because the card carries a printed
    reticle: those lines are far brighter than the card and pull a mean up by
    up to 54%, while a minority of bright pixels leaves a median untouched.
    No threshold and no hand-placed boxes, so the result is reproducible from
    the radius alone.
    """
    with rawpy.imread(str(path)) as r:
        raw = r.raw_image_visible.astype(np.float64)
        colors = r.raw_colors_visible
        blacks = np.array(r.black_level_per_channel, dtype=np.float64)
        white = float(r.white_level)

    # each channel has its own black level; they are not always equal
    black = blacks[colors]
    linear = (raw - black) / (white - black)
    h, w = linear.shape
    yy, xx = np.mgrid[0:h, 0:w]
    rad = np.hypot(yy - h / 2, xx - w / 2) / (min(h, w) / 2)
    sel = ((colors == 1) | (colors == 3)) & (rad < radius)
    v = linear[sel]

    return {
        "black_level": [float(b) for b in blacks],
        "clipped_fraction": float(np.mean(raw[sel] >= white * 0.99)),
        "white_level": white,
        "shape": list(linear.shape),
        "method": "median_green_radial",
        "radius": radius,
        "pixels": int(v.size),
        "y_card": float(np.median(v)),
        "mean_for_reference": float(v.mean()),
        "sd_over_mean": float(v.std() / v.mean()),
    }


def measure(path: Path, rois: Dict[str, tuple]) -> Dict[str, Any]:
    with rawpy.imread(str(path)) as r:
        raw = r.raw_image_visible.astype(np.float64)
        colors = r.raw_colors_visible
        black = float(np.mean(r.black_level_per_channel))
        white = float(r.white_level)

    linear = (raw - black) / (white - black)
    green = (colors == 1) | (colors == 3)

    results = {}
    for name, roi in rois.items():
        x0, x1, y0, y1 = roi_pixels(linear.shape, roi)
        sel = green[y0:y1, x0:x1]
        v = linear[y0:y1, x0:x1][sel]
        median = float(np.median(v))
        lineness = float((np.percentile(v, 99) - median) / median) if median else float("inf")
        results[name] = {
            "rect_px": [x0, y0, x1, y1],
            "pixels": int(v.size),
            "mean": float(v.mean()),
            "sd_over_mean": float(v.std() / v.mean()) if v.mean() else None,
            "lineness": lineness,
            "clean": lineness <= LINE_TOLERANCE,
        }

    means = [v["mean"] for v in results.values()]
    return {
        "black_level": black,
        "white_level": white,
        "shape": list(linear.shape),
        "rois": results,
        "y_card": float(np.mean(means)),
        "y_card_spread": float((max(means) - min(means)) / np.mean(means)),
        "rois_used": list(results),
    }


def illuminance(y_card: float, t: float, f_number: float, iso: float,
                rho_ref: float, y_mid: float) -> Dict[str, float]:
    constant = np.pi * K_REFLECTED * f_number ** 2 / (rho_ref * iso * y_mid)
    return {
        "constant": float(constant),
        "lux": float(constant * y_card / t),
    }


def write_overlay(path: Path, measured: Dict[str, Any], out: Path) -> None:
    """Mark the region the measurement came from, for both modes."""
    with rawpy.imread(str(path)) as r:
        rgb = r.postprocess(use_camera_wb=True, no_auto_bright=False, output_bps=8)
    img = Image.fromarray(rgb)
    scale = 1400 / img.width
    img = img.resize((1400, int(img.height * scale)))
    draw = ImageDraw.Draw(img)
    green = (0, 255, 0)

    if "rois" in measured:
        for name, info in measured["rois"].items():
            x0, y0, x1, y1 = info["rect_px"]
            box = [x0 * scale, y0 * scale, x1 * scale, y1 * scale]
            colour = green if info["clean"] else (255, 0, 0)
            draw.rectangle(box, outline=colour, width=3)
            draw.text((box[0], box[1] - 14), name, fill=colour)
    else:
        h, w = measured["shape"]
        radius = measured["radius"] * min(h, w) / 2 * scale
        cx, cy = w / 2 * scale, h / 2 * scale
        draw.ellipse([cx - radius, cy - radius, cx + radius, cy + radius],
                     outline=green, width=3)
        draw.text((cx - radius, cy - radius - 14),
                  f"median green, r<{measured['radius']}", fill=green)

    img.save(out, quality=90)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Estimate scene illuminance from a raw grey-card capture.")
    parser.add_argument("files", nargs="+", help="DNG captures of the grey card")
    parser.add_argument("--rho", type=float, default=DEFAULTS["rho_ref"],
                        help="reference card reflectance")
    parser.add_argument("--y-mid", type=float, default=DEFAULTS["y_mid"],
                        help="metered mid-grey level for this camera")
    parser.add_argument("--radius", type=float, default=DEFAULTS["radius"],
                        help="radial median region, as a fraction of the short side")
    parser.add_argument("--rois", nargs="?", type=Path, const="default",
                        help="use explicit rectangles instead of the radial median; "
                             "bare flag uses DEFAULT_ROIS, or give a JSON file of "
                             "{name: [cx, cy, half_w, half_h]}")
    parser.add_argument("--record", type=Path, help="write a JSON record here")
    parser.add_argument("--overlay-dir", type=Path,
                        help="write ROI overlay images into this folder")
    args = parser.parse_args()

    rois = None
    if args.rois is not None:
        rois = (DEFAULT_ROIS if str(args.rois) == "default"
                else {k: tuple(v) for k, v in json.loads(args.rois.read_text()).items()})

    # PowerShell and cmd do not expand wildcards, so do it here.
    paths: List[Path] = []
    for name in args.files:
        matched = [Path(m) for m in sorted(glob.glob(name))]
        paths.extend(matched or [Path(name)])

    records = []
    for path in paths:
        tags = read_dng_tags(path)
        measured = measure(path, rois) if rois else measure_radial(path, args.radius)

        record = {"file": path.name, "exif": tags, **measured}
        if measured["y_card"] and tags["exposure_time"] and tags["iso"]:
            record["result"] = illuminance(
                measured["y_card"], tags["exposure_time"], tags["f_number"],
                tags["iso"], args.rho, args.y_mid)
        record["calibration"] = {
            "K": K_REFLECTED, "rho_ref": args.rho, "y_mid": args.y_mid,
            "channel": "green", "standard": "ISO 2720:1974",
        }
        records.append(record)

        print(f"{path.name}")
        print(f"  {tags['exposure_time']} s  ISO {tags['iso']}  f/{tags['f_number']}")
        if rois:
            for roi_name, info in measured["rois"].items():
                flag = "" if info["clean"] else "  check placement"
                print(f"    {roi_name}  {info['rect_px']}  mean={info['mean']:.5f}"
                      f"  lineness={info['lineness']:.2f}{flag}")
            print(f"  y_card = {measured['y_card']:.5f}"
                  f"  (spread {100 * measured['y_card_spread']:.1f}% across {len(measured['rois'])} ROIs)")
        else:
            print(f"  y_card = {measured['y_card']:.5f}  (median of {measured['pixels']:,} "
                  f"green px within r<{measured['radius']})")
        if "result" in record:
            print(f"  E = {record['result']['lux']:.6f} lux")

        if args.overlay_dir:
            args.overlay_dir.mkdir(parents=True, exist_ok=True)
            suffix = "rois" if rois else f"r{args.radius:g}"
            out = args.overlay_dir / f"{path.stem}_{suffix}.jpg"
            write_overlay(path, measured, out)
            print(f"  overlay -> {out}")

    if args.record:
        args.record.parent.mkdir(parents=True, exist_ok=True)
        args.record.write_text(json.dumps({
            "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "region": ({"rois_normalised": {k: list(v) for k, v in rois.items()}}
                       if rois else
                       {"method": "median_green_radial", "radius": args.radius}),
            "captures": records,
        }, indent=2))
        print(f"\nrecord -> {args.record}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
