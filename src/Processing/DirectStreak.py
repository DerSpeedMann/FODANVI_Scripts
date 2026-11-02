"""
DirectStreak.py

Show where the moving car is in the direct digital frames of the moving
scene, in which it cannot be made out against the noise.

Every frame can be cropped to a range of columns (--crop_x) and of rows
(--crop_y), at full resolution, so that the figure shows the path rather than
the whole frame; a range left out keeps the full height or width. The crop is
written unchanged. One frame without the car serves as the background. For
every frame with the car, its change against the background is written too:
both crops are converted to gray, reduced by an integer factor so that every
output pixel averages a block of input pixels, and blurred with a Gaussian in
floating point, and their difference is scaled around mid-gray, so that the
car shows as a dark smear where the frame is darker than the background.

The blur is set per axis, in reduced pixels. Equal values keep the shape of
the smear; a stronger blur along the path suppresses more noise but stretches
noise and smear alike in that direction.

Usage:
    python DirectStreak.py <out_dir> --background <frame> --frames <frame> ...
        [--crop_x LEFT RIGHT] [--crop_y TOP BOTTOM]
        [--reduce 4] [--sigma_x 6] [--sigma_y 6] [--gain 12]

    $d = 'data/datasets/moving_car/source/26_10_02/d500'
    python DirectStreak.py data/results/direct_streak `
        --background $d/DSC_6197.jpg --frames $d/DSC_6198.jpg $d/DSC_6199.jpg `
        --crop_y 1328 2408
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional, Tuple

import numpy as np
from PIL import Image

Range = Optional[Tuple[int, int]]


def crop(path: Path, rows: Range, cols: Range, out_dir: Path) -> Image.Image:
    im = Image.open(path)
    left, right = cols or (0, im.width)
    top, bottom = rows or (0, im.height)
    cut = im.crop((left, top, right, bottom))
    cut.save(out_dir / f"{path.stem}_crop.jpg", quality=95)
    return cut


def blur(a: np.ndarray, sigma: float, axis: int) -> np.ndarray:
    """Gaussian along one axis, in floating point, edges reflected."""
    if sigma <= 0:
        return a
    r = int(np.ceil(3 * sigma))
    k = np.exp(-0.5 * (np.arange(-r, r + 1) / sigma) ** 2)
    k /= k.sum()
    pad = [(0, 0), (0, 0)]
    pad[axis] = (r, r)
    p = np.pad(a, pad, mode="reflect")
    return np.apply_along_axis(lambda v: np.convolve(v, k, mode="valid"), axis, p)


def reduced(cut: Image.Image, reduce: int, sigma: Tuple[float, float]) -> np.ndarray:
    g = cut.convert("L")
    w, h = g.width // reduce, g.height // reduce
    a = np.asarray(g.crop((0, 0, w * reduce, h * reduce)), dtype=np.float64)
    a = a.reshape(h, reduce, w, reduce).mean(axis=(1, 3))
    return blur(blur(a, sigma[0], axis=1), sigma[1], axis=0)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("out_dir", type=Path)
    ap.add_argument("--background", type=Path, required=True,
                    help="a frame without the car")
    ap.add_argument("--frames", type=Path, nargs="+", required=True,
                    help="frames with the car")
    ap.add_argument("--crop_x", type=int, nargs=2, metavar=("LEFT", "RIGHT"),
                    help="crop to these columns, in input pixels; default full width")
    ap.add_argument("--crop_y", type=int, nargs=2, metavar=("TOP", "BOTTOM"),
                    help="crop to these rows, in input pixels; default full height")
    ap.add_argument("--reduce", type=int, default=4)
    ap.add_argument("--sigma_x", type=float, default=6.0,
                    help="Gaussian blur along the rows, in reduced pixels")
    ap.add_argument("--sigma_y", type=float, default=6.0,
                    help="Gaussian blur along the columns, in reduced pixels")
    ap.add_argument("--gain", type=float, default=12.0)
    args = ap.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    rows = tuple(args.crop_y) if args.crop_y else None
    cols = tuple(args.crop_x) if args.crop_x else None
    sigma = (args.sigma_x, args.sigma_y)
    ref = reduced(crop(args.background, rows, cols, args.out_dir),
                  args.reduce, sigma)
    for f in args.frames:
        diff = reduced(crop(f, rows, cols, args.out_dir),
                       args.reduce, sigma) - ref
        Image.fromarray(np.clip(128 + diff * args.gain, 0, 255).astype(np.uint8)).save(
            args.out_dir / f"{f.stem}_change.png")
        print(f"{f.stem}: change {float(diff.min()):.1f} to {float(diff.max()):.1f}")
    print(f"written to {args.out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
