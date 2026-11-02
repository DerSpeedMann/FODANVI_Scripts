"""
BuildDay2NightDatasets.py

Build every day-to-night conversion of COCO this project uses, from one
command, so a fresh clone with COCO in place can regenerate all of them.

    v1, GenerateNVG.py, hand-tuned values hardcoded in the script
        coco_nvg_green_noisy    grain, blur, bloom and vignette on
        coco_nvg_green_clean    those four off
        coco_nvg_white_noisy
        coco_nvg_white_clean

    v2, GenerateNVGv2.py, configs AnalyzeNVG.py measured off real captures
        coco_nvg2_green_noisy           green from nvg_config_selected_green.json
        coco_nvg2_green_clean           (the five green references)
        coco_nvg2_white_noisy           white from nvg_config_selected_white.json
        coco_nvg2_white_clean           (the five white references)
        coco_nvg_captures_green_noisy   green from nvg_config_setup_green.json
        coco_nvg_captures_green_clean   (the 66 evaluation captures)
        coco_nvg2_green_grain           as the clean sets, with the grain on
        coco_nvg2_white_grain           (validation only, for the denoising)

Named like the v1 sets: _noisy carries grain, blur, bloom and vignette,
_clean has all four off.

The nvg2 sets are the fine-tuning data of the v2 chain, both phosphors measured
on the handpicked references, so that no statistic of the 66 evaluation
captures reaches the training data; coco_nvg2_clean.yaml and
coco_nvg2_noisy.yaml pair green with white for the two stages. The captures
set is matched to the camera path the models are scored on and is for
validation only; its train split is never needed. See
data/day2night/README.md for how the configs were measured.

Each clean variant disables grain, blur, bloom and vignette and nothing else,
so it differs from its sibling only in those four. Histogram equalisation stays
on in both: it is part of the tone mapping, not one of the effects. Each grain
variant disables blur, bloom and vignette only, so it differs from its clean
sibling in the grain alone; denoising it and setting it beside the clean set
measures the denoising on the grain without the other three in the way. The v1
flags are those recorded in MA_Paper/supplementary/code/Readme.md.

GenerateNVG.py is frozen. Regenerating the v1 sets with it gives
complete sets, not necessarily the original ones: the green noisy val2017 on
disk was written by an earlier revision of that script and carries more blue
than the frozen one produces.

Each set also gets its yaml, written beside the source's: a copy of coco.yaml
with train and val pointed at the new folders and the header comment replaced
by one naming the generator and config. The groupings that combine two v1
conversions for fine-tuning are not sets of their own and stay versioned.

BuildDatasets.ps1 is not used here because it iterates images/train and
images/val, while COCO carries train2017 and val2017; pointed at COCO it finds
neither split and writes an empty dataset.

Resumable. A split whose output already holds as many images as its source is
left alone, so an interrupted run continues where it stopped. Pass --force to
rebuild one anyway. The validation split is all the sweep scores; train2017
is only needed to fine-tune, and takes most of the time.

    python BuildDay2NightDatasets.py                       all twelve, both splits
    python BuildDay2NightDatasets.py --splits val2017      all twelve, val only
    python BuildDay2NightDatasets.py --only "coco_nvg2_*"  the v2 training four
    python BuildDay2NightDatasets.py --only "coco_nvg_captures_*" --splits val2017
    python BuildDay2NightDatasets.py --only "coco_nvg2_*_grain" --splits val2017
    python BuildDay2NightDatasets.py --dry-run
"""

from __future__ import annotations

import argparse
import fnmatch
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

V1 = "GenerateNVG.py"
V2 = "GenerateNVGv2.py"

# Disabling the four effects. Both generators guard each on > 0, so zero
# skips the block rather than dividing by it.
CLEAN = ["--noise-intensity", "0", "--blur-amount", "0",
         "--bloom-intensity", "0", "--vignette-intensity", "0"]
# The same with the grain left on.
GRAIN = CLEAN[2:]

# name -> (generator, color, config or None, suffix the generator appends,
#          extra arguments)
VARIANTS = {
    "coco_nvg_green_noisy":  (V1, "green", None, "_nvg_green", []),
    "coco_nvg_green_clean":  (V1, "green", None, "_nvg_green", CLEAN),
    "coco_nvg_white_noisy":  (V1, "white", None, "_nvg_white", []),
    "coco_nvg_white_clean":  (V1, "white", None, "_nvg_white", CLEAN),
    "coco_nvg2_green_noisy": (V2, "green", "nvg_config_selected_green.json",
                              "_nvg2_green", []),
    "coco_nvg2_green_clean": (V2, "green", "nvg_config_selected_green.json",
                              "_nvg2_green", CLEAN),
    "coco_nvg2_white_noisy": (V2, "white", "nvg_config_selected_white.json",
                              "_nvg2_white", []),
    "coco_nvg2_white_clean": (V2, "white", "nvg_config_selected_white.json",
                              "_nvg2_white", CLEAN),
    "coco_nvg_captures_green_noisy": (V2, "green", "nvg_config_setup_green.json",
                                      "_nvg2_green", []),
    "coco_nvg_captures_green_clean": (V2, "green", "nvg_config_setup_green.json",
                                      "_nvg2_green", CLEAN),
    "coco_nvg2_green_grain": (V2, "green", "nvg_config_selected_green.json",
                              "_nvg2_green", GRAIN),
    "coco_nvg2_white_grain": (V2, "white", "nvg_config_selected_white.json",
                              "_nvg2_white", GRAIN),
}

V1_HEADER = """# One conversion on its own, so a model can be scored against it
# alone. The paired configs beside this one combine two.
"""

V2_HEADER = """# {source} converted with GenerateNVGv2.py and the config AnalyzeNVG.py
# measured off real captures ({config}).{note}
# Built by BuildDay2NightDatasets.py. Images and labels both carry the
# {suffix} suffix, as the earlier converted COCO sets do.
"""

CLEAN_NOTE = "\n# Grain, blur, bloom and vignette are disabled in this one."
GRAIN_NOTE = "\n# Blur, bloom and vignette are disabled in this one, the grain is on."
NOTES = {id(CLEAN): CLEAN_NOTE, id(GRAIN): GRAIN_NOTE}
LABELS = {id(CLEAN): "clean", id(GRAIN): "grain only"}


def count(folder: Path) -> int:
    return sum(1 for p in folder.iterdir() if p.is_file()) if folder.is_dir() else 0


def run(cmd: list[str]) -> None:
    proc = subprocess.run([sys.executable, "-I", *cmd])
    if proc.returncode != 0:
        raise SystemExit(f"failed: {' '.join(str(c) for c in cmd)}")


def write_yaml(name: str) -> None:
    """
    The source's yaml, adapted to this set.

    Its leading comment is replaced, and every train or val entry that names
    the source folder is pointed at this one; everything else, the class names
    included, is carried over as it stands. Read as bytes and stripped of every
    CR before CRLF is restored, since coco.yaml ends its lines in CR CR LF and
    read_text would turn that into a blank line after each one.
    """
    script, color, config, suffix, extra = VARIANTS[name]
    src = (DATASETS / f"{SOURCE}.yaml").read_bytes().decode("utf-8")
    lines = src.replace("\r", "").split("\n")
    while lines and lines[0].startswith("#"):
        lines.pop(0)
    body = "\n".join(lines).replace(f"  - {SOURCE}/images/",
                                    f"  - {name}/images/")
    if f"  - {name}/images/" not in body:
        raise SystemExit(f"{SOURCE}.yaml names no {SOURCE}/images/ folder "
                         "to point at the new set")

    if script == V1:
        header = V1_HEADER
    else:
        header = V2_HEADER.format(source=SOURCE, config=config,
                                       suffix=suffix,
                                       note=NOTES.get(id(extra), ""))
    out = (header + body).replace("\n", "\r\n")      # CRLF, no BOM
    (DATASETS / f"{name}.yaml").write_bytes(out.encode("utf-8"))
    print(f"  wrote {name}.yaml")


def build(name: str, splits: list[str], force: bool, dry: bool) -> None:
    script, color, config, suffix, extra = VARIANTS[name]
    dst = DATASETS / name
    args = ["--color", color]
    if config:
        args = ["--config", str(CONFIGS / config), *args]

    print(f"\n=== {name}  ({script}, {color}"
          f"{', ' + config if config else ''}, "
          f"{LABELS.get(id(extra), 'full')}) ===")
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

        # The generators skip an input whose output file is already there, so
        # a forced rebuild has to clear the split or it would report a full set
        # in a second without having rewritten any of it.
        if force and out_img.is_dir():
            print(f"  {split}: clearing {have} existing images")
            shutil.rmtree(out_img)
            have = 0

        print(f"  {split}: converting {want} images -> {out_img}")
        out_img.mkdir(parents=True, exist_ok=True)
        t0 = time.time()
        run([str(PROC / script), str(src_img), str(out_img), *args, *extra])
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
        print(f"  would write {name}.yaml")
    else:
        write_yaml(name)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--only", nargs="+", default=["*"], metavar="PATTERN",
                   help="dataset names or wildcards, e.g. coco_nvg2_*")
    p.add_argument("--splits", nargs="+", default=["val2017", "train2017"],
                   metavar="SPLIT")
    p.add_argument("--force", action="store_true",
                   help="rebuild a split that already looks complete")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    names = [n for n in VARIANTS
             if any(fnmatch.fnmatch(n, pat) for pat in args.only)]
    if not names:
        raise SystemExit(f"no dataset matched {args.only}; "
                         f"known: {', '.join(VARIANTS)}")
    for name in names:
        build(name, args.splits, args.force, args.dry_run)
    print("\ndone")


main()
