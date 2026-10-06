"""
ConvertRaw.py

Render camera raw files to JPEG, so the detectors can read them.

The detection scripts take jpg and png. The Nikon captures are NEF, which
has to be demosaiced and tone mapped first, and how that is done changes
what a detector sees. Two renderings are offered and the choice is not
cosmetic:

    faithful (default)  camera white balance, no automatic brightening.
                        A dark frame stays dark, so the detector is shown
                        what the sensor recorded.

    --auto-bright       lets the converter scale the image up until it
                        uses the full range. A night frame comes out
                        looking like a normal photograph. Useful to see
                        whether the subject is there at all, but the
                        detector is then reading an image nobody captured.

Report which one the numbers came from. On imagery this dark the
difference is not subtle.

The mean level of each output is printed, 0 to 255, as a check that the
rendering did what was expected.

Usage:
    python ConvertRaw.py <file|dir> [out_dir] [--auto-bright] [--quality 95]

    python ConvertRaw.py data/images
    python ConvertRaw.py data/images data/images_bright --auto-bright
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import rawpy
from PIL import Image

RAW_EXT = {".nef", ".dng", ".cr2", ".arw", ".raf", ".rw2"}


def render(path: Path, auto_bright: bool) -> np.ndarray:
    with rawpy.imread(str(path)) as raw:
        return raw.postprocess(
            use_camera_wb=True,
            no_auto_bright=not auto_bright,
            output_bps=8,
        )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("source", type=Path)
    ap.add_argument("out", type=Path, nargs="?",
                    help="default: beside the source files")
    ap.add_argument("--auto-bright", action="store_true",
                    help="scale each frame up to use the full range")
    ap.add_argument("--quality", type=int, default=95)
    args = ap.parse_args()

    src = args.source
    files = ([src] if src.is_file()
             else sorted(p for p in src.rglob("*")
                         if p.suffix.lower() in RAW_EXT))
    if not files:
        print(f"no raw files under {src}")
        return 1

    out = args.out or (src if src.is_dir() else src.parent)
    out.mkdir(parents=True, exist_ok=True)
    mode = "auto-brightened" if args.auto_bright else "faithful"
    print(f"{len(files)} file(s), {mode}, into {out}\n")

    for f in files:
        rgb = render(f, args.auto_bright)
        dst = out / f"{f.stem}.jpg"
        Image.fromarray(rgb).save(dst, quality=args.quality)
        print(f"  {f.name} -> {dst.name}   mean {rgb.mean():5.1f}/255  "
              f"{rgb.shape[1]}x{rgb.shape[0]}")

    print(f"\nwrote {len(files)} jpg into {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
