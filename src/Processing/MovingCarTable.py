"""
MovingCarTable.py

What every model detects on the frames of the moving car (moving_car), per
session and device as groups.csv records them.

The set has one labeled object per labeled frame, the car, and the frames in
which no remnant of it could be made out as background images. mAP over such
a set says little, so each frame is classified from the run's saved
predictions.json instead, counting a prediction at a confidence of at least
--conf whose box overlaps the labeled one at an IoU of at least --iou:

    car          a car prediction on the car's box
    other        no car, but a prediction of another category on it
    missed       neither
    background   a background frame with any prediction above --conf

The best car score on the box at any confidence is kept as well, since the
validator keeps predictions down to 0.001. Ultralytics predictions are mapped
onto the _gt.json as CrossCheckScoring.py does; rfdetr_val writes them
against the same _gt.json already.

Writes data/results/moving_car_detections.csv, one row per model and group,
and prints the same table, followed by the categories predicted on the car.

Beside it, data/results/moving_car_matches.csv gives the predictions on the
car's box at an IoU of at least --iou, one row per model, group and kind,
car or another category: the labeled frames in which one reached --conf, and
the highest-scoring one over all labeled frames at any confidence, with its
IoU and category. Each frame contributes its highest-scoring prediction of
the kind.

Usage:
    python MovingCarTable.py
"""

from __future__ import annotations

import argparse
import collections
import csv
import json
import sys
from pathlib import Path
from typing import Dict, List, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
from CompareRuns import identify

DATASET = "moving_car"


def _stem(v) -> str:
    return Path(str(v).replace("\\", "/")).stem


def iou(a: List[float], b: List[float]) -> float:
    iw = max(0.0, min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0]))
    ih = max(0.0, min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1]))
    inter = iw * ih
    return inter / (a[2] * a[3] + b[2] * b[3] - inter) if inter else 0.0


def load_preds(path: Path, ids: Dict[str, int],
               names: Dict[int, str]) -> Dict[int, List[Tuple[str, float, list]]]:
    out: Dict[int, List[Tuple[str, float, list]]] = collections.defaultdict(list)
    for p in json.loads(path.read_text(encoding="utf-8")):
        if "file_name" in p:
            iid, cat = ids[_stem(p["file_name"])], p["category_id"] - 1
        else:
            iid, cat = p["image_id"], p["category_id"]
        out[iid].append((names[cat], p["score"], p["bbox"]))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run-dir", type=Path, default=Path("data/runs"))
    ap.add_argument("--datasets", type=Path, default=Path("data/datasets"))
    ap.add_argument("--conf", type=float, default=0.25)
    ap.add_argument("--iou", type=float, default=0.5)
    ap.add_argument("--out", type=Path,
                    default=Path("data/results/moving_car_detections.csv"))
    args = ap.parse_args()

    gt_path = args.datasets / f"{DATASET}_gt.json"
    if not gt_path.exists():
        raise SystemExit(f"{gt_path} does not exist; run the sweep first")
    gt = json.loads(gt_path.read_text(encoding="utf-8"))
    names = {c["id"]: c["name"] for c in gt["categories"]}
    img = {i["id"]: _stem(i["file_name"]) for i in gt["images"]}
    ids = {v: k for k, v in img.items()}
    boxes: Dict[int, List[list]] = collections.defaultdict(list)
    for a in gt["annotations"]:
        boxes[a["image_id"]].append(a["bbox"])
    with open(args.datasets / DATASET / "groups.csv", newline="",
              encoding="utf-8") as fh:
        group = {r["file"]: r.get("group") or f"{r['session']}/{r['device']}"
                 for r in csv.DictReader(fh)}
    order = sorted(set(group.values()))

    rows, seen, match_rows = [], [], []
    for run in sorted(args.run_dir.glob(f"val_*_{DATASET}")):
        pred = run / "predictions.json"
        if not pred.exists():
            print(f"{run.name}: no predictions.json, skipped")
            continue
        model, _, _ = identify(run)
        preds = load_preds(pred, ids, names)
        stat = {g: collections.Counter() for g in order}
        best = collections.defaultdict(float)
        # (group, kind) -> frames reaching --conf, and the best (score, iou, name)
        reached = collections.Counter()
        top_match: Dict[Tuple[str, str], Tuple[float, float, str]] = {}
        for iid, name in img.items():
            g = group[name]
            s = stat[g]
            for b in boxes[iid]:
                on_box = [(p[1], iou(p[2], b), p[0]) for p in preds[iid]
                          if iou(p[2], b) >= args.iou]
                for kind in ("car", "other"):
                    hits = [h for h in on_box if (h[2] == "car") == (kind == "car")]
                    if not hits:
                        continue
                    h = max(hits)
                    reached[(g, kind)] += h[0] >= args.conf
                    if h > top_match.get((g, kind), (-1.0, 0.0, "")):
                        top_match[(g, kind)] = h
            above = [p for p in preds[iid] if p[1] >= args.conf]
            if not boxes[iid]:
                s["background"] += 1
                s["background_with_detection"] += bool(above)
                continue
            s["labeled"] += 1
            on = [p for b in boxes[iid] for p in above if iou(p[2], b) >= args.iou]
            for b in boxes[iid]:
                for p in preds[iid]:
                    if p[0] == "car" and iou(p[2], b) >= args.iou:
                        best[g] = max(best[g], p[1])
            if any(p[0] == "car" for p in on):
                s["car"] += 1
            elif on:
                s["other"] += 1
                top = max(on, key=lambda p: p[1])
                seen.append(f"{model:26} {g:20} {name[:34]:34} {top[0]} {top[1]:.2f}")
            else:
                s["missed"] += 1
        for g in order:
            s = stat[g]
            rows.append({"model": model, "group": g, "labeled": s["labeled"],
                         "car": s["car"], "other": s["other"],
                         "missed": s["missed"], "background": s["background"],
                         "background_with_detection": s["background_with_detection"],
                         "best_car_score": round(best[g], 3)})
            for kind in ("car", "other"):
                if not s["labeled"]:
                    continue
                score, overlap, category = top_match.get((g, kind), (None, None, ""))
                match_rows.append({
                    "model": model, "group": g, "kind": kind,
                    "labeled": s["labeled"], "reached_conf": reached[(g, kind)],
                    "best_score": "" if score is None else round(score, 3),
                    "best_iou": "" if overlap is None else round(overlap, 2),
                    "best_category": category})
    if not rows:
        raise SystemExit(f"no val_*_{DATASET} run in {args.run_dir}")

    cols = list(rows[0])
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)

    widths = [max(len(c), *(len(str(r[c])) for r in rows)) for c in cols]
    print("  ".join(c.ljust(n) for c, n in zip(cols, widths)))
    for r in rows:
        print("  ".join(str(r[c]).ljust(n) for c, n in zip(cols, widths)))
    print(f"\nother categories on the car (conf >= {args.conf}, IoU >= {args.iou}):")
    for line in seen:
        print("  " + line)
    print(f"\nwritten to {args.out}")

    match_out = args.out.with_name(f"{DATASET}_matches.csv")
    with open(match_out, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(match_rows[0]))
        w.writeheader()
        w.writerows(match_rows)
    print(f"predictions on the car's box written to {match_out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
