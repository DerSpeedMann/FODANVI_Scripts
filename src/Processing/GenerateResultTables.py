"""
GenerateResultTables.py

Recompute per-class detection metrics from a saved predictions file and the
COCO-format ground truth, and write them as simple CSV files.

The Ultralytics / COCO ``predictions.json`` contains detections only
(``image_id``, ``category_id``, ``bbox``, ``score``); the per-class metrics
shown in the training console are NOT stored there. This script recomputes
them by evaluating the predictions against the ground-truth annotations, so
the numbers are reproducible from the archived predictions without re-running
inference. Class names and supercategories are read from the ground truth.

Reported metrics are COCO-standard and deterministic:
    ap50_95  mean average precision over IoU 0.50:0.95
    ap50     average precision at IoU 0.50
    ar100    average recall at maxDets=100

Two CSV files are written to the output directory:
    per_class_metrics.csv      one row per class (includes a supercategory column)
    supercategory_metrics.csv  the same metrics averaged per COCO supercategory

Requires ``faster-coco-eval`` (preferred) or ``pycocotools``.

Usage:
    python GenerateResultTables.py \
        --pred runs/detect/val/predictions.json \
        --gt   /datasets/coco/annotations/instances_val2017.json \
        --out  result_tables
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Tuple

import numpy as np

try:
    from faster_coco_eval import COCO, COCOeval_faster as COCOeval
except ImportError:  # fall back to the reference implementation
    from pycocotools.coco import COCO
    from pycocotools.cocoeval import COCOeval


def evaluate(gt_path: str, pred_path: str) -> Tuple[COCO, COCOeval]:
    """Run COCO bbox evaluation of predictions against ground truth."""
    coco_gt: COCO = COCO(gt_path)
    coco_dt = coco_gt.loadRes(pred_path)
    ev = COCOeval(coco_gt, coco_dt, iouType="bbox")
    ev.evaluate()
    ev.accumulate()
    ev.summarize()  # prints the standard 12-line COCO summary
    return coco_gt, ev


def per_class_metrics(coco_gt: COCO, ev: COCOeval) -> List[Dict[str, object]]:
    """Extract per-class ap50_95, ap50 and ar100 from the accumulated arrays.

    precision has shape [T, R, K, A, M] and recall [T, K, A, M], where
    T = IoU thresholds, R = recall thresholds, K = categories,
    A = area ranges (0 = all), M = maxDets (2 = 100).
    """
    precision: np.ndarray = ev.eval["precision"]
    recall: np.ndarray = ev.eval["recall"]
    cat_ids: List[int] = list(ev.params.catIds)

    def _mean(values: np.ndarray) -> float:
        valid = values[values > -1]
        return round(float(valid.mean()), 4) if valid.size else float("nan")

    rows: List[Dict[str, object]] = []
    for i, cid in enumerate(cat_ids):
        cat = coco_gt.loadCats(cid)[0]
        rows.append({
            "id": cid,
            "class": cat["name"],
            "supercategory": cat.get("supercategory", "n/a"),
            "instances": len(coco_gt.getAnnIds(catIds=[cid])),
            "ap50": _mean(precision[0, :, i, 0, 2]),
            "ap50_95": _mean(precision[:, :, i, 0, 2]),
            "ar100": _mean(recall[:, i, 0, 2]),
        })
    return rows


def aggregate_supercategories(rows: List[Dict[str, object]]) -> List[Dict[str, object]]:
    """Average per-class metrics within each COCO supercategory (unweighted,
    matching how COCO defines mAP as the mean over classes)."""
    groups: Dict[str, List[Dict[str, object]]] = defaultdict(list)
    for row in rows:
        groups[str(row["supercategory"])].append(row)

    def _nanmean(key: str, items: List[Dict[str, object]]) -> float:
        vals = np.array([it[key] for it in items], dtype=float)
        vals = vals[~np.isnan(vals)]
        return round(float(vals.mean()), 4) if vals.size else float("nan")

    summary: List[Dict[str, object]] = []
    for name, items in sorted(groups.items()):
        summary.append({
            "supercategory": name,
            "n_classes": len(items),
            "instances": sum(int(it["instances"]) for it in items),
            "ap50": _nanmean("ap50", items),
            "ap50_95": _nanmean("ap50_95", items),
            "ar100": _nanmean("ar100", items),
        })
    return summary


def write_csv(rows: List[Dict[str, object]], path: Path) -> None:
    """Write rows to CSV; NaN metrics are written as empty cells."""
    clean = [{k: ("" if isinstance(v, float) and np.isnan(v) else v)
              for k, v in row.items()} for row in rows]
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(clean)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--pred", required=True, help="predictions.json (COCO detection format)")
    parser.add_argument("--gt", required=True, help="ground-truth annotations (e.g. instances_val2017.json)")
    parser.add_argument("--out", default="result_tables", help="output directory")
    args = parser.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    coco_gt, ev = evaluate(args.gt, args.pred)
    rows = per_class_metrics(coco_gt, ev)
    summary = aggregate_supercategories(rows)

    write_csv(rows, out_dir / "per_class_metrics.csv")
    write_csv(summary, out_dir / "supercategory_metrics.csv")

    print(f"\nWrote:\n  {out_dir/'per_class_metrics.csv'}"
          f"\n  {out_dir/'supercategory_metrics.csv'}")


if __name__ == "__main__":
    main()
