"""
GenerateBoxAnnotations.py

Turn a dataset's YOLO labels into COCO-format box annotations, on the host.

The converted COCO sets carry segmentation polygons, cls x1 y1 x2 y2 ...,
because COCO ships masks and the conversion kept them. Ultralytics derives
the enclosing box itself; rfdetr_val.py has to be given it. This writes that
file, one box per label, polygons reduced to their bounding box.

It is run here rather than letting rfdetr_val.py build it inside the
container because doing so reads an image header and a label file per image
across a Windows bind mount, which is around 400 times slower: under a
minute here against nearly four hours there for a 5000 image split. The
result is the same file, so it is built once and passed as the fourth
argument to rfdetr_val.py, which RunSweep.ps1 does whenever one is present.

It reuses rfdetr_val's own collect_pairs and build_gt, so the image order,
and so the image ids the predictions are keyed by, cannot drift between the
two.

The configs carry `path: /datasets`, the mount target inside the container,
so on the host that is rewritten to the directory the yaml itself sits in.

Usage:
    python GenerateBoxAnnotations.py <data_yaml> [out.json]

    python GenerateBoxAnnotations.py data/datasets/coco_nvg_green_clean.yaml
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from rfdetr_val import build_gt, collect_pairs, load_yolo_yaml


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    yaml_path = Path(sys.argv[1])
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else \
        yaml_path.parent / f"{yaml_path.stem}_gt.json"

    val_dirs, names = load_yolo_yaml(str(yaml_path))
    # /datasets only exists in the container; here the sets are beside the
    # config. Anything already present is left alone.
    host_root = yaml_path.parent.resolve()
    # Drop the drive and the "/datasets" mount name, keeping what follows.
    val_dirs = [d if d.exists()
                else host_root / Path(*Path(d).parts[2:]) for d in val_dirs]
    for d in val_dirs:
        print(f"  host val dir: {d}  (exists={d.exists()})")
    pairs = collect_pairs(val_dirs)
    if not pairs:
        print(f"no images found for {yaml_path}")
        return 1

    gt = build_gt(pairs, names)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w") as fh:
        json.dump(gt, fh)
    print(f"{len(gt['images'])} images, {len(gt['annotations'])} annotations")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
