"""
BuildResampledSets.py

Build resampled copies of a validation set, for judging how far a score on a
set as small as the 66 captures moves when the images are drawn differently.

Each set holds as many images as the source. A share of them, --unique-pct,
is drawn without replacement from the source; the rest are drawn with
replacement from those, so a set of 66 at 66.7 % holds 44 different captures,
22 of them twice or more. A duplicate is copied under its own name, with its
label, so the validator scores it as one more image.

Every set gets its own folder and its own yaml under --out, named
<source>_rs_u<pct>_r<NNN>, and manifest.json lists the files each set was
drawn from, so a set can be rebuilt or traced back. The yaml points at the
container path the sweep mounts the datasets at, /datasets, so the sets are
run as they are by RunResampled.ps1. They are kept out of the dataset folder
proper so RunSweep.ps1 neither reports nor sweeps them.

Usage:
    python BuildResampledSets.py --runs 100
    python BuildResampledSets.py --source real_nvg_white --unique-pct 66.7 --runs 50 --seed 7
"""

from __future__ import annotations

import argparse
import json
import random
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATASETS = ROOT / "data/datasets"


def names_block(yaml_path: Path) -> str:
    """The names: block of the source yaml, copied as it is, so the sets keep
    the class ids the models were trained with."""
    text = yaml_path.read_text(encoding="utf-8")
    i = text.find("\nnames:")
    if i < 0:
        raise SystemExit(f"{yaml_path} has no names: block")
    return text[i + 1:]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", default="real_nvg",
                    help="dataset under data/datasets to resample (val split)")
    ap.add_argument("--unique-pct", type=float, default=66.7,
                    help="share of each set drawn without replacement, in %%")
    ap.add_argument("--runs", type=int, required=True,
                    help="number of sets to build")
    ap.add_argument("--seed", type=int, default=0,
                    help="set r is drawn with seed + r, so a set can be rebuilt")
    ap.add_argument("--out", type=Path, default=DATASETS / "resampled")
    ap.add_argument("--force", action="store_true",
                    help="rebuild sets whose folder already exists")
    args = ap.parse_args()

    src = DATASETS / args.source
    images = sorted((src / "images" / "val").glob("*.jpg"))
    if not images:
        raise SystemExit(f"no images in {src / 'images' / 'val'}")
    labels = src / "labels" / "val"
    missing = [p.name for p in images if not (labels / (p.stem + ".txt")).exists()]
    if missing:
        raise SystemExit(f"{len(missing)} image(s) without a label, e.g. {missing[0]}")
    if not 0 < args.unique_pct <= 100:
        raise SystemExit("--unique-pct must be above 0 and at most 100")
    # The yaml names the set by its container path, so it has to sit under
    # the folder the container mounts.
    args.out = args.out.resolve()
    if DATASETS.resolve() not in args.out.parents:
        raise SystemExit(f"--out must be inside {DATASETS}, which the container "
                         f"mounts at /datasets")

    size = len(images)
    unique = round(size * args.unique_pct / 100)
    if unique < 1:
        raise SystemExit(f"{args.unique_pct} % of {size} leaves no image")
    pct_tag = f"{args.unique_pct:g}".replace(".", "p")
    names = names_block(DATASETS / f"{args.source}.yaml")
    args.out.mkdir(parents=True, exist_ok=True)

    manifest_path = args.out / "manifest.json"
    manifest = (json.loads(manifest_path.read_text(encoding="utf-8"))
                if manifest_path.exists() else {})

    print(f"{args.source}: {size} images, {unique} unique and "
          f"{size - unique} duplicate per set, {args.runs} set(s)")
    built = skipped = 0
    for r in range(1, args.runs + 1):
        name = f"{args.source}_rs_u{pct_tag}_r{r:03d}"
        dst = args.out / name
        if dst.exists() and not args.force:
            skipped += 1
            continue
        if dst.exists():
            shutil.rmtree(dst)

        rng = random.Random(args.seed + r)
        picked = rng.sample(images, unique)
        drawn = picked + [rng.choice(picked) for _ in range(size - unique)]

        out_img = dst / "images" / "val"
        out_lab = dst / "labels" / "val"
        out_img.mkdir(parents=True)
        out_lab.mkdir(parents=True)
        seen: dict[str, int] = {}
        for p in drawn:
            n = seen.get(p.stem, 0)
            seen[p.stem] = n + 1
            stem = p.stem if n == 0 else f"{p.stem}__dup{n}"
            shutil.copyfile(p, out_img / f"{stem}{p.suffix}")
            shutil.copyfile(labels / f"{p.stem}.txt", out_lab / f"{stem}.txt")

        (args.out / f"{name}.yaml").write_text(
            f"# {size} images resampled from {args.source} by "
            f"BuildResampledSets.py:\n"
            f"# {unique} drawn without replacement, {size - unique} duplicated "
            f"from those, seed {args.seed + r}.\n"
            f"path: /datasets/{args.out.relative_to(DATASETS.resolve()).as_posix()}/{name}\n"
            f"train: images/val\nval: images/val\ntest:\n\n{names}",
            encoding="utf-8")
        manifest[name] = {"source": args.source, "seed": args.seed + r,
                          "unique": unique, "size": size,
                          "files": [p.name for p in drawn]}
        built += 1

    manifest_path.write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    print(f"built {built}, skipped {skipped} (exist) in {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
