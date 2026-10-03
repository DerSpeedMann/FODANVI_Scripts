"""
Build Manifest

Writes a manifest of the capture frames in a folder, so a fetched set can be
checked before anything is run against it.

    BuildManifest.py data/photometry/nikon

Everything it records comes from the frames themselves: the naming fields are
parsed from the file name, the settings are read from the EXIF, and the size
and digest are taken from the bytes. Nothing is carried in from elsewhere, so
the manifest cannot disagree with what it describes and can be regenerated in
a clean checkout.

Everything here is derived, so a rebuild is cheap and never destroys anything.
Which record consumes which frame is recorded in the folder README instead,
beside the command that reads it.

The camera's own file name is deliberately absent. It does not survive the
rename and is not recoverable from the file, so it belongs with the frames in
the capture store rather than in a manifest that claims to be derived.
"""

import argparse
import csv
import hashlib
import struct
from pathlib import Path
from typing import Any, Dict

TIFF_SIZES = {1: 1, 2: 1, 3: 2, 4: 4, 5: 8, 7: 1, 9: 4, 10: 8, 11: 4, 12: 8}
EXIF_TAGS = {0x829A: "exposure_s", 0x829D: "f_number", 0x8827: "iso",
             0x9003: "time", 0x920A: "focal_mm", 0x9207: "metering",
             0x8822: "mode"}
MODES = {0: "", 1: "manual", 2: "program", 3: "aperture priority",
         4: "shutter priority"}
METERING = {0: "", 1: "average", 2: "center-weighted", 3: "spot",
            4: "multi-spot", 5: "matrix", 6: "partial"}
COLUMNS = ["file", "folder", "session", "series", "state", "laptop", "time",
           "exposure_s", "f_number", "iso", "focal_mm", "mode", "metering",
           "bytes", "sha256"]


def read_exif(path: Path) -> Dict[str, Any]:
    """The subset of EXIF the manifest reports, from the raw file itself."""
    d = path.read_bytes()
    end = "<" if d[:2] == b"II" else ">"
    out: Dict[str, Any] = {}

    def directory(off: int, depth: int = 0) -> None:
        if depth > 3 or off <= 0 or off + 2 > len(d):
            return
        count, = struct.unpack(end + "H", d[off:off + 2])
        if count > 500:
            return
        for i in range(count):
            entry = off + 2 + i * 12
            if entry + 12 > len(d):
                return
            tag, typ, n = struct.unpack(end + "HHI", d[entry:entry + 8])
            size = TIFF_SIZES.get(typ, 1) * n
            pointer, = struct.unpack(end + "I", d[entry + 8:entry + 12])
            if tag == 0x8769:                       # the Exif IFD
                directory(pointer, depth + 1)
                continue
            if tag not in EXIF_TAGS:
                continue
            at = entry + 8 if size <= 4 else pointer
            raw = d[at:at + size]
            if typ == 5:
                num, den = struct.unpack(end + "II", raw[:8])
                out[EXIF_TAGS[tag]] = num / den if den else 0
            elif typ == 3:
                out[EXIF_TAGS[tag]] = struct.unpack(end + "H", raw[:2])[0]
            elif typ == 2:
                out[EXIF_TAGS[tag]] = raw.rstrip(b"\x00").decode("ascii", "replace")

    directory(struct.unpack(end + "I", d[4:8])[0])
    return out


def naming(stem: str) -> Dict[str, str]:
    """<session>_<series>_<state>[_lapXX]_<exposure>_<HHMMSS>."""
    parts = stem.split("_")
    return {"session": parts[0] if parts else "",
            "series": parts[1] if len(parts) > 1 else "",
            "state": parts[2] if len(parts) > 2 else "",
            "laptop": next((p for p in parts if p.startswith("lap")), "")}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Write a manifest of the capture frames in a folder.")
    parser.add_argument("folder", type=Path, help="folder holding the capture subfolders")
    parser.add_argument("--pattern", default="*/*.NEF", help="which frames to include")
    parser.add_argument("--out", type=Path, help="manifest path, default MANIFEST.csv in the folder")
    args = parser.parse_args()

    out = args.out or args.folder / "MANIFEST.csv"
    rows = []
    for path in sorted(args.folder.glob(args.pattern)):
        e = read_exif(path)
        rows.append((str(e.get("time", "")), path.name, {
            "file": path.name,
            "folder": path.parent.name,
            **naming(path.stem),
            "time": str(e.get("time", ""))[11:],
            "exposure_s": f"{e['exposure_s']:g}" if "exposure_s" in e else "",
            "f_number": f"{e['f_number']:g}" if "f_number" in e else "",
            "iso": e.get("iso", ""),
            "focal_mm": f"{e['focal_mm']:g}" if "focal_mm" in e else "",
            "mode": MODES.get(e.get("mode"), ""),
            "metering": METERING.get(e.get("metering"), ""),
            "bytes": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }))

    # Capture order, not folder order. One session is split across bg_noise,
    # dark_card and direct_screen_light, so sorting by path interleaves
    # sessions shot hours apart. Frames with no readable time go last.
    rows.sort(key=lambda r: (r[0] == "", r[0], r[1]))
    rows = [r[2] for r in rows]

    if not rows:
        print(f"no frames matched {args.pattern} under {args.folder}")
        return 1

    with open(out, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

    total = sum(r["bytes"] for r in rows)
    print(f"wrote {out}")
    print(f"  {len(rows)} frames, {total / 1048576:.0f} MB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
