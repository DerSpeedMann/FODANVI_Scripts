"""
BuildNvg2Datasets.py

Build the four corrected day-to-night conversions of COCO with the current
generator, GenerateNVG.py, driven by the channel multipliers AnalyzeNVG.py
measured off the real captures (data/day2night/nvg_config_selected_*.json).

The sets the earlier runs used were produced by GenerateNVGLegacy.py from the
hardcoded COLOR_MODES, whose green blue multiplier is 0.005 against the 0.119
the captures measure, so the green conversion carried almost no blue at all.
These sets replace that: measured against the same reference captures the new
green lands within 7 per cent on B/G and the new white within 2 per cent on
both ratios.

    coco_nvg2_green         noise, grain and vignette as measured
    coco_nvg2_green_clean   the same color and tone, those effects disabled
    coco_nvg2_white         as measured
    coco_nvg2_white_clean   effects disabled

The clean pair disables noise, blur, bloom and vignette and nothing else, so
it differs from its sibling only in those four, exactly as the clean and noisy
variants of the legacy sets did. Histogram equalisation stays on in both: it
is part of the tone mapping, not one of the effects.

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

# Disabling the four effects. The generator guards each on > 0, so zero skips
# the block rather than dividing by it.
CLEAN = ["--noise-intensity", "0", "--blur-amount", "0",
         "--bloom-intensity", "0", "--vignette-intensity", "0"]

# Contrast measured back off the pipeline rather than taken from the config.
#
# AnalyzeNVG derives contrast_alpha and contrast_beta by inverting an
# assumed-uniform equalised histogram, and its own build_config docstring
# calls that a starting point: the inversion cannot see the vignette, which
# GenerateNVG applies by multiplying AFTER convertScaleAbs, so every level it
# predicts is darker by whatever the vignette mask averages. Built from the
# config as written, the green set came out 51 per cent below the target luma
# mean and the white set 38 per cent below.
#
# These pairs were solved against the real captures' own luma_mean and
# luma_sd by probing the pipeline at three (alpha, beta) points over 150 val
# images and stepping to the target; each is a measured pair, not an
# extrapolation, and lands within 1.3 per cent on both.
#
# STALE. They were solved when AnalyzeNVG measured whole frames, so the target
# they match is the vignette-contaminated one: luma_mean 83.3 for green and
# 126.4 for white. AnalyzeNVG now measures inside REGION_FRAC and those targets
# are 96.6 and 150.3, with luma_sd falling from 21.6 to 18.0 and 37.4 to 26.3
# (see data/day2night/README.md). Checked against the corrected targets the
# sets these pairs built are about 7 per cent bright and 19 per cent over on
# spread for white, less for green.
#
# So the four datasets under data/datasets/coco_nvg2_* match the old
# definition, as do the sixteen runs scored on them. Re-solve these against
# the regenerated configs before rebuilding, and note the vignette and the
# blur both move the answer.
TONE = {
    "coco_nvg2_green":       ("0.5425", "100"),   # mean -0.3%, sd -0.1%
    "coco_nvg2_green_clean": ("0.4863", "76"),    # mean +0.4%, sd +0.1%
    "coco_nvg2_white":       ("0.8702", "108"),   # mean -0.0%, sd -1.0%
    "coco_nvg2_white_clean": ("0.6190", "76"),    # mean +0.6%, sd +1.3%
}

# name -> (color, suffix the generator appends, extra arguments)
VARIANTS = {
    "coco_nvg2_green":       ("green", "_nvg2_green", []),
    "coco_nvg2_green_clean": ("green", "_nvg2_green", CLEAN),
    "coco_nvg2_white":       ("white", "_nvg2_white", []),
    "coco_nvg2_white_clean": ("white", "_nvg2_white", CLEAN),
}

HEADER = """# {source} converted with GenerateNVG.py and the multipliers
# AnalyzeNVG.py measured off the real captures ({config}).{note}
# Contrast is the pair solved against the captures' own luma mean and sd,
# not the one in the config: see the TONE note in BuildNvg2Datasets.py.
# Built by BuildNvg2Datasets.py. Images and labels both carry the
# {suffix} suffix, as the earlier converted COCO sets do.
path: /datasets
train:
  - {name}/images/train2017

val:
  - {name}/images/val2017

"""

CLEAN_NOTE = "\n# Noise, blur, bloom and vignette are disabled in this one."


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
    config = CONFIGS / f"nvg_config_selected_{color}.json"
    dst = DATASETS / name

    print(f"\n=== {name}  ({color}, {'clean' if extra else 'measured'}) ===")
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
        alpha, beta = TONE[name]
        run([str(PROC / "GenerateNVG.py"), str(src_img), str(out_img),
             "--config", str(config), "--color", color,
             "--contrast-alpha", alpha, "--contrast-beta", beta, *extra])
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
