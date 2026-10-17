"""
GenerateColorShift.py

Apply a per-channel colour formula to every image in a folder.

Each output channel is an arithmetic expression over the input channels
r, g, b (float32, 0-255 range). Results are clipped to [0, 255] and
saved as uint8.  numpy is available as `np` inside the expressions.

--formula R G B is required.

Useful formulas:
  blue tint (luma-best) : "0" "g*0.5" "g"
  red tint (luma-best)  : "g" "g*0.5" "0"
  green-blue swap       : "r" "b" "g"
  old blue method       : "r" "g*0.3" "b+g*0.7"
  identity              : "r" "g" "b"
  luma grayscale        : "Y" "Y" "Y"   (Y = 0.299r+0.587g+0.114b)

Usage:
    python GenerateColorShift.py input/ output/ --formula "0" "g*0.5" "g" --suffix _blue_light
    python GenerateColorShift.py input/ output/ --formula "r" "b" "g" --suffix _blue_swap
"""
import argparse
import os
from PIL import Image, ImageOps
from pathlib import Path
from typing import List
import numpy as np

DEFAULT_SUFFIX: str = "_shifted"


def has_suffix(filename: str, suffix: str) -> bool:
    return suffix in Path(filename).stem


def apply_formula(
    img_array: np.ndarray,
    r_expr: str,
    g_expr: str,
    b_expr: str,
) -> np.ndarray:
    """
    Apply per-channel arithmetic formulas to produce a new image.

    r_expr / g_expr / b_expr are Python expressions evaluated with:
      r, g, b  -- input channels as float32 arrays, values 0-255
      np       -- numpy (for np.clip, np.sqrt, np.where, etc.)
      Y        -- ITU-R BT.601 luma: 0.299*r + 0.587*g + 0.114*b

    Results are clipped to [0, 255] and cast to uint8. Alpha is passed
    through unchanged.

    Examples
    --------
    ("0",   "g*0.5",   "g")          luma-best blue (default)
    ("r",   "g*0.3",   "b+g*0.7")   old blue method
    ("r",   "b",       "g")          channel swap
    ("r",   "g",       "b")          identity
    ("Y",   "Y",       "Y")          grayscale via luma
    """
    arr = img_array.copy()
    if arr.ndim == 2:                               # grayscale -> RGB
        arr = np.stack([arr, arr, arr], axis=-1)

    has_alpha = arr.ndim == 3 and arr.shape[2] == 4
    if has_alpha:
        r = arr[:, :, 0].astype(np.float32)
        g = arr[:, :, 1].astype(np.float32)
        b = arr[:, :, 2].astype(np.float32)
        a = arr[:, :, 3]
    else:
        r = arr[:, :, 0].astype(np.float32)
        g = arr[:, :, 1].astype(np.float32)
        b = arr[:, :, 2].astype(np.float32)

    Y = 0.299 * r + 0.587 * g + 0.114 * b          # BT.601 luma
    ns = {"r": r, "g": g, "b": b, "Y": Y, "np": np}

    def _eval(expr: str) -> np.ndarray:
        # eval may return a scalar (e.g. "0"); broadcast to channel shape.
        out = eval(expr, ns)  # noqa: S307
        return np.clip(np.broadcast_to(out, r.shape), 0, 255).astype(np.uint8)

    new_r = _eval(r_expr)
    new_g = _eval(g_expr)
    new_b = _eval(b_expr)

    if has_alpha:
        return np.stack([new_r, new_g, new_b, a], axis=-1)
    return np.stack([new_r, new_g, new_b], axis=-1)


def color_shift_images(
    input_folder: str,
    output_folder: str | None,
    formula: tuple[str, str, str],
    suffix: str = DEFAULT_SUFFIX,
) -> None:
    """Apply formula to all images in input_folder, writing to output_folder."""
    in_path  = Path(input_folder)
    out_path = Path(output_folder) if output_folder else in_path
    out_path.mkdir(parents=True, exist_ok=True)

    image_ext: set[str] = {".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".webp"}
    files: List[Path] = [f for f in in_path.iterdir()
                         if f.is_file() and f.suffix.lower() in image_ext]

    r_expr, g_expr, b_expr = formula
    print(f"Found {len(files)} images")
    print(f"Formula : R'={r_expr!r}  G'={g_expr!r}  B'={b_expr!r}")
    print(f"Suffix  : {suffix}")
    print()

    ok = skipped = failed = 0
    for f in files:
        if has_suffix(f.name, suffix):
            skipped += 1
            continue

        out_name = f"{f.stem}{suffix}{f.suffix}"
        out_file = out_path / out_name
        if out_file.exists():
            skipped += 1
            continue

        try:
            img  = ImageOps.exif_transpose(Image.open(f))
            arr  = np.array(img)
            out  = apply_formula(arr, r_expr, g_expr, b_expr)
            img2 = Image.fromarray(out)
            kw   = ({"quality": 95, "subsampling": 0}
                    if f.suffix.lower() in {".jpg", ".jpeg"} else {})
            img2.save(out_file, **kw)
            print(f"ok: {f.name} -> {out_name}")
            ok += 1
        except Exception as e:
            print(f"fail: {f.name}: {e}")
            failed += 1

    print(f"\n{'='*60}")
    print(f"=== Summary ===")
    print(f"{'='*60}")
    print(f"Processed : {ok}")
    print(f"Skipped   : {skipped}")
    print(f"Failed    : {failed}")
    print(f"Total     : {ok + skipped + failed}")
    print(f"Output    : {out_path.absolute()}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("input_folder",  nargs="?", default=os.getcwd())
    ap.add_argument("output_folder", nargs="?", default=None)
    ap.add_argument(
        "--formula", nargs=3, metavar=("R", "G", "B"), required=True,
        help=(
            "Three Python expressions for the output R, G, B channels. "
            "Variables r, g, b are input channels (float32, 0-255). "
            "np and Y (BT.601 luma) are also available."
        ),
    )
    ap.add_argument(
        "--suffix", default=DEFAULT_SUFFIX,
        help="Suffix appended to output filenames (default: %(default)s)",
    )
    args = ap.parse_args()

    if not os.path.exists(args.input_folder):
        print(f"Error: input folder {args.input_folder!r} does not exist")
        raise SystemExit(1)

    print(f"Input  : {args.input_folder}")
    print(f"Output : {args.output_folder or args.input_folder + ' (same)'}")
    print()

    color_shift_images(
        args.input_folder,
        args.output_folder,
        formula=tuple(args.formula),
        suffix=args.suffix,
    )
