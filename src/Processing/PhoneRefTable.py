"""
PhoneRefTable.py

AP50 per category, model and exposure time on the smartphone captures of the
static scene (phone_ref).

The set holds one image per exposure time, named phone_ref_<NN>s_<hash>, and
a sweep run scores both together. This scores each exposure on its own, for
every labeled category, from the run's saved predictions.json, by the
pycocotools path every model shares (CrossCheckScoring.py), so the
Ultralytics and the RF-DETR runs are scored the same way. No model is run.

Ultralytics predictions are keyed by file name with category_id as class + 1
and are mapped onto the _gt.json as CrossCheckScoring does; rfdetr_val
writes them against the same _gt.json already.

Writes data/results/phone_ref_ap50.csv, one row per model and category with
a column per exposure time, and prints the same table.

With one image per exposure time and one object per category, AP50 can only
be 0 or 1/(k+1), k the false detections of the category ranked above the
true one, and it does not show how confident the detection was. So beside it,
data/results/phone_ref_conf.csv gives for every object the detection
pycocotools matches to it at IoU 0.5: its confidence, its IoU and k, or
empty fields where nothing matched. With a single object in the image and
category that is the highest-scoring prediction of the category at IoU 0.5
or more, which is what the matching picks.

Usage:
    python PhoneRefTable.py
"""

from __future__ import annotations

import argparse
import contextlib
import csv
import io
import json
import re
import sys
from pathlib import Path
from typing import Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pycocotools.coco import COCO
from pycocotools.cocoeval import COCOeval

from CompareRuns import identify
from rfdetr_val import per_class_ap_from_pycoco

DATASET = "phone_ref"
EXPOSURE = re.compile(r"phone_ref_(\d+)s_")


def _base(v) -> str:
    return str(v).replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]


def load_preds(pred_path: Path, ids: Dict[str, int]) -> List[dict]:
    preds = json.loads(pred_path.read_text(encoding="utf-8"))
    if preds and "file_name" in preds[0]:
        return [{"image_id": ids[_base(p["file_name"])],
                 "category_id": p["category_id"] - 1,
                 "bbox": p["bbox"], "score": p["score"]} for p in preds]
    return preds


def ap50(gt_path: Path, preds: List[dict], img_ids: List[int],
         cat_ids: List[int]) -> Dict[int, float]:
    with contextlib.redirect_stdout(io.StringIO()):
        coco_gt = COCO(str(gt_path))
        ev = COCOeval(coco_gt, coco_gt.loadRes(preds), "bbox")
        ev.params.imgIds = img_ids
        ev.params.catIds = cat_ids
        ev.evaluate()
        ev.accumulate()
        ev.summarize()
    return {c: v["mAP50"] for c, v in per_class_ap_from_pycoco(ev).items()}


def iou(a: List[float], b: List[float]) -> float:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    ix = max(0.0, min(ax + aw, bx + bw) - max(ax, bx))
    iy = max(0.0, min(ay + ah, by + bh) - max(ay, by))
    inter = ix * iy
    return inter / (aw * ah + bw * bh - inter)


def matched(ann: dict, preds: List[dict]) -> Dict[str, object]:
    """The prediction matched to one labeled object at IoU 0.5, if any."""
    same = sorted((p for p in preds if p["image_id"] == ann["image_id"]
                   and p["category_id"] == ann["category_id"]),
                  key=lambda p: -p["score"])
    for above, p in enumerate(same):
        overlap = iou(p["bbox"], ann["bbox"])
        if overlap >= 0.5:
            return {"confidence": round(p["score"], 3),
                    "iou": round(overlap, 2), "ranked_above": above}
    return {"confidence": "", "iou": "", "ranked_above": ""}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run-dir", type=Path, default=Path("data/runs"))
    ap.add_argument("--datasets", type=Path, default=Path("data/datasets"))
    ap.add_argument("--out", type=Path,
                    default=Path("data/results/phone_ref_ap50.csv"))
    args = ap.parse_args()

    gt_path = args.datasets / f"{DATASET}_gt.json"
    if not gt_path.exists():
        raise SystemExit(f"{gt_path} does not exist; run the sweep first")
    gt = json.loads(gt_path.read_text(encoding="utf-8"))
    ids = {_base(i["file_name"]): i["id"] for i in gt["images"]}
    names = {c["id"]: c["name"] for c in gt["categories"]}
    cat_ids = sorted({a["category_id"] for a in gt["annotations"]},
                     key=lambda c: names[c])

    groups: Dict[str, List[int]] = {}
    for name, i in ids.items():
        m = EXPOSURE.match(name)
        if not m:
            raise SystemExit(f"{name}: no exposure time in the file name")
        groups.setdefault(f"{int(m.group(1))} s", []).append(i)
    order = sorted(groups, key=lambda g: int(g.split()[0]))

    exposure_of = {i: g for g, members in groups.items() for i in members}
    rows = []
    conf_rows = []
    for run in sorted(args.run_dir.glob(f"val_*_{DATASET}")):
        pred = run / "predictions.json"
        if not pred.exists():
            print(f"{run.name}: no predictions.json, skipped")
            continue
        model, _, _ = identify(run)
        preds = load_preds(pred, ids)
        per = {g: ap50(gt_path, preds, groups[g], cat_ids) for g in order}
        for c in cat_ids:
            row = {"model": model, "category": names[c]}
            row.update({g: round(per[g][c], 3) for g in order})
            rows.append(row)
        for ann in sorted(gt["annotations"], key=lambda a: (
                names[a["category_id"]], int(exposure_of[a["image_id"]].split()[0]))):
            conf_rows.append({"model": model, "category": names[ann["category_id"]],
                              "exposure": exposure_of[ann["image_id"]],
                              **matched(ann, preds)})
    if not rows:
        raise SystemExit(f"no val_*_{DATASET} run in {args.run_dir}")

    cols = ["model", "category"] + order
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)

    widths = [max(len(c), *(len(str(r[c])) for r in rows)) for c in cols]
    print("  ".join(c.ljust(n) for c, n in zip(cols, widths)))
    for r in rows:
        print("  ".join(str(r[c]).ljust(n) for c, n in zip(cols, widths)))
    print(f"\nwritten to {args.out}")

    conf_out = args.out.with_name(f"{DATASET}_conf.csv")
    with open(conf_out, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(conf_rows[0]))
        w.writeheader()
        w.writerows(conf_rows)
    print(f"matched confidence per object written to {conf_out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
