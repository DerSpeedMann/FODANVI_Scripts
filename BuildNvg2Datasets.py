"""
BuildNvg2Datasets.py

Build the four corrected day-to-night conversions of COCO with the current
generator, GenerateNVG.py, driven by the configs AnalyzeNVG.py measured off
real captures (data/day2night/, see its README):

    green   nvg_config_setup_green.json      the 66 evaluation captures
    white   nvg_config_selected_white.json   the five white references

Green is built from the setup measurement because that is the camera path the
models are scored on; white has only the references.

The sets the earlier runs used were produced by GenerateNVGLegacy.py from the
hardcoded COLOR_MODES, tuned by eye against the reference photographs.

    coco_nvg2_green         grain, blur, bloom and vignette as configured
    coco_nvg2_green_clean   the same color and tone, those effects disabled
    coco_nvg2_white         as configured
    coco_nvg2_white_clean   effects disabled

The clean pair disables grain, blur, bloom and vignette and nothing else, so
it differs from its sibling only in those four, exactly as the clean and noisy
variants of the legacy sets did. Histogram equalisation stays on in both: it
is part of the tone mapping, not one of the effects.

Grain comes from the grain_profile each config carries, the residual noise
AnalyzeNVG.py measured per brightness band, which GenerateNVG.py applies band
by band. Contrast and brightness are taken from the config as written.

BuildDatasets.ps1 is not used here because it iterates images/train and
images/val, while COCO carries train2017 and val2017; pointed at COCO it finds
neither split and writes an empty dataset.

Resumable. A split whose output already holds as many images as its source is
left alone, so an interrupted run continues where it stopped. Pass --force to
rebuild one anyway.

    python BuildNvg2Datasets.py                     build all four
    python BuildNvg2Datasets.py --only coco_nvg2_white
    python BuildNvg2Datasets.py --splits val2017    skip the long split
    python BuildNvg2Datasets.py --dry-run
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATASETS = ROOT / "data/datasets"
PROC = ROOT / "src/Processing"
CONFIGS = ROOT / "data/day2night"
SOURCE = "coco"

# Which measurement each color is built from (see data/day2night/README.md).
CONFIG_FOR = {
    "green": "nvg_config_setup_green.json",
    "white": "nvg_config_selected_white.json",
}

# Disabling the four effects. The generator guards each on > 0, so zero skips
# the block rather than dividing by it.
CLEAN = ["--noise-intensity", "0", "--blur-amount", "0",
         "--bloom-intensity", "0", "--vignette-intensity", "0"]

# name -> (color, suffix the generator appends, extra arguments)
VARIANTS = {
    "coco_nvg2_green":       ("green", "_nvg2_green", []),
    "coco_nvg2_green_clean": ("green", "_nvg2_green", CLEAN),
    "coco_nvg2_white":       ("white", "_nvg2_white", []),
    "coco_nvg2_white_clean": ("white", "_nvg2_white", CLEAN),
}

HEADER = """# {source} converted with GenerateNVG.py and the config AnalyzeNVG.py
# measured off real captures ({config}).{note}
# Built by BuildNvg2Datasets.py. Images and labels both carry the
# {suffix} suffix, as the earlier converted COCO sets do.
path: /datasets
train:
  - {name}/images/train2017

val:
  - {name}/images/val2017

"""

CLEAN_NOTE = "\n# Grain, blur, bloom and vignette are disabled in this one."


def count(folder: Path) -> int:
    return sum(1 for p in folder.iterdir() if p.is_file()) if folder.is_dir() else 0


def run(cmd: list[str]) -> None:
    proc = subprocess.run([sys.executable, "-I", *cmd])
    if proc.returncode != 0:
        raise SystemExit(f"failed: {' '.join(str(c) for c in cmd)}")


def names_block() -> str:
    raw = (DATASETS / f"{SOURCE}.yaml").read_text(encoding="utf-8")
    at = raw.find("\nnames:")
    if at < 0:
        raise SystemExit(f"{SOURCE}.yaml has no names: block")
    return raw[at + 1:]


def build(name: str, splits: list[str], force: bool, dry: bool) -> None:
    color, suffix, extra = VARIANTS[name]
    config = CONFIGS / CONFIG_FOR[color]
    dst = DATASETS / name

    print(f"\n=== {name}  ({color}, {config.name}, "
          f"{'clean' if extra else 'full'}) ===")
    for split in splits:
        src_img = DATASETS / SOURCE / "images" / split
        if not src_img.is_dir():
            print(f"  {split}: no source, skipped")
            continue
        want = count(src_img)
        out_img = dst / "images" / split
        have = count(out_img)
        if have >= want and not force:
            print(f"  {split}: {have}/{want} already there, skipped")
            continue
        if dry:
            print(f"  {split}: would convert {want} images "
                  f"({'resume from ' + str(have) if have else 'from scratch'})")
            continue

        # GenerateNVG skips an input whose output file is already there, so a
        # forced rebuild has to clear the split or it would report a full set
        # in a second without having rewritten any of it.
        if force and out_img.is_dir():
            print(f"  {split}: clearing {have} existing images")
            shutil.rmtree(out_img)
            have = 0

        print(f"  {split}: converting {want} images -> {out_img}")
        out_img.mkdir(parents=True, exist_ok=True)
        t0 = time.time()
        run([str(PROC / "GenerateNVG.py"), str(src_img), str(out_img),
             "--config", str(config), "--color", color, *extra])
        got = count(out_img)
        print(f"  {split}: {got} images in {time.time() - t0:.0f}s")

        src_lbl = DATASETS / SOURCE / "labels" / split
        if src_lbl.is_dir():
            out_lbl = dst / "labels" / split
            out_lbl.mkdir(parents=True, exist_ok=True)
            run([str(PROC / "CopyFilesWithSuffix.py"), str(src_lbl),
                 str(out_lbl), suffix])
            print(f"  {split}: {count(out_lbl)} labels")

    if dry:
        return

    yaml = DATASETS / f"{name}.yaml"
    text = HEADER.format(source=SOURCE, config=config.name, suffix=suffix,
                         name=name, note=CLEAN_NOTE if extra else "")
    # CRLF and no BOM, matching every other yaml in data/datasets.
    body = (text + names_block()).replace("\r\n", "\n").replace("\n", "\r\n")
    yaml.write_bytes(body.encode("utf-8"))
    print(f"  wrote {yaml.name}")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--only", nargs="+", default=list(VARIANTS),
                   choices=list(VARIANTS), metavar="NAME")
    p.add_argument("--splits", nargs="+", default=["val2017", "train2017"],
                   metavar="SPLIT")
    p.add_argument("--force", action="store_true",
                   help="rebuild a split that already looks complete")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    for name in args.only:
        build(name, args.splits, args.force, args.dry_run)
    print("\ndone")


main()
