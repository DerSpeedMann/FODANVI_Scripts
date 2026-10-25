"""
CrossCheckScoring.py

Check that the two scoring paths in this project give the same numbers.

The YOLO and RT-DETR runs are scored by Ultralytics' own metrics, the
RF-DETR runs by pycocotools in rfdetr_val.py. Putting them in one table
assumes the two agree. This tests that on a run Ultralytics has already
scored: its saved predictions.json is scored again through rfdetr_val.py's
path, the same COCOeval call over the same _gt.json and the same
per_class_pr_at_max_f1, both imported from rfdetr_val rather than copied, so
the check cannot drift from what the RF-DETR runs actually used. No model
is run.

Ultralytics writes category_id as class + 1 for a dataset it does not take
for COCO itself, and the _gt.json files are 0-based, so one is subtracted.
Images are matched by file name. A run that did not save predictions.json
cannot be checked; the YOLO validators save it, the RT-DETR one does not.

Compared, per class and as the mean over the classes in sweep.json's
"classes" list, which is how CompareRuns.py reports a run:

    map50_95, map50   both from COCOeval's precision array, area all,
                      maxDets 100; Ultralytics keeps up to 300 per image
    precision, recall Ultralytics takes one confidence for all classes, where
                      mean F1 over classes peaks; rfdetr_val takes each
                      class's own F1 peak, at IoU 0.5

Writes data/results/scoring_crosscheck.csv, one row per run, class and
metric, with both values and their difference.

Usage:
    python CrossCheckScoring.py                         yolo12x on coco and real_nvg
    python CrossCheckScoring.py val_yolo11s_real_nvg val_yolo12x_coco_nvg2_green
"""

from __future__ import annotations

import argparse
import contextlib
import csv
import io
import json
import sys
from pathlib import Path
from typing import Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pycocotools.coco import COCO
from pycocotools.cocoeval import COCOeval

from CompareRuns import identify, sweep_classes
from rfdetr_val import per_class_ap_from_pycoco, per_class_pr_at_max_f1

METRICS = ("precision", "recall", "map50", "map50_95")


def _base(v) -> str:
    return str(v).replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]


def pycoco_scores(gt_path: Path, pred_path: Path) -> Dict[str, Dict[str, float]]:
    """Per-class metrics of an Ultralytics predictions.json, as rfdetr_val scores."""
    gt = json.loads(gt_path.read_text(encoding="utf-8"))
    ids = {_base(i["file_name"]): i["id"] for i in gt["images"]}
    names = {c["id"]: c["name"] for c in gt["categories"]}
    preds = [{"image_id": ids[_base(p["file_name"])],
              "category_id": p["category_id"] - 1,
              "bbox": p["bbox"], "score": p["score"]}
             for p in json.loads(pred_path.read_text(encoding="utf-8"))]

    # As rfdetr_val.main does it, with the summary table kept off the console.
    with contextlib.redirect_stdout(io.StringIO()):
        coco_gt = COCO(str(gt_path))
        ev = COCOeval(coco_gt, coco_gt.loadRes(preds), "bbox")
        ev.params.catIds = sorted({a["category_id"] for a in gt["annotations"]})
        ev.evaluate()
        ev.accumulate()
        ev.summarize()
    ap = per_class_ap_from_pycoco(ev)
    pr = per_class_pr_at_max_f1(gt, preds, iou_thresh=0.5)
    return {names[c]: {"precision": pr[c]["P"], "recall": pr[c]["R"],
                       "map50": ap[c]["mAP50"], "map50_95": ap[c]["mAP"]}
            for c in ap}


def ultralytics_scores(run: Path) -> Dict[str, Dict[str, float]]:
    with open(run / "tables" / "per_class_metrics.csv", newline="",
              encoding="utf-8") as fh:
        return {r["class"]: {k: float(r[k]) for k in METRICS}
                for r in csv.DictReader(fh)}


def compare(run: Path, datasets: Path, classes: List[str]) -> List[dict]:
    _, dataset, _ = identify(run)
    pred = run / "predictions.json"
    gt = datasets / f"{dataset}_gt.json"
    for f in (pred, gt):
        if not f.exists():
            raise SystemExit(f"{run.name}: {f} does not exist")
    ours = pycoco_scores(gt, pred)
    theirs = ultralytics_scores(run)
    picked = [c for c in (classes or sorted(ours)) if c in ours]

    rows = []
    for c in picked + ["mean"]:
        for k in METRICS:
            if c == "mean":
                u = sum(theirs[x][k] for x in picked) / len(picked)
                p = sum(ours[x][k] for x in picked) / len(picked)
            else:
                u, p = theirs[c][k], ours[c][k]
            rows.append({"run": run.name, "dataset": dataset, "class": c,
                         "metric": k, "ultralytics": round(u, 4),
                         "pycocotools": round(p, 4), "delta": round(p - u, 4)})
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("runs", nargs="*",
                    default=["val_yolo12x_coco", "val_yolo12x_real_nvg"],
                    help="run folders under --run-dir")
    ap.add_argument("--run-dir", type=Path, default=Path("data/runs"))
    ap.add_argument("--datasets", type=Path, default=Path("data/datasets"))
    ap.add_argument("--sweep", type=Path, default=Path("sweep.json"))
    ap.add_argument("--out", type=Path,
                    default=Path("data/results/scoring_crosscheck.csv"))
    args = ap.parse_args()

    classes = sweep_classes(args.sweep)
    rows = []
    for name in args.runs:
        rows += compare(args.run_dir / name, args.datasets, classes)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    for r in rows:
        if r["class"] == "mean":
            print(f"{r['run']:28} {r['metric']:10} ultralytics {r['ultralytics']:.4f}"
                  f"  pycocotools {r['pycocotools']:.4f}  delta {r['delta']:+.4f}")
    worst = max((r for r in rows if r["metric"].startswith("map")),
                key=lambda r: abs(r["delta"]))
    print(f"largest mAP difference: {worst['delta']:+.4f} "
          f"({worst['run']}, {worst['class']}, {worst['metric']})")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
