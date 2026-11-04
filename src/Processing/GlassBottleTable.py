"""
GlassBottleTable.py

What every model predicts on the glass bottle in the four captures of the
glass bottle check, two with the bottle in its sleeve and two without, at
the same two positions (in front of and beside the backpack).

The per-category figures do not separate this bottle from the metal one, so
the four images are read from each run's saved predictions.json on the
unprocessed captures (real_nvg) instead: for the labeled bottle box, the
highest-scoring bottle prediction and the highest-scoring prediction of
another category whose box overlaps it at an IoU of at least --iou, at any
confidence, since the validator keeps predictions down to 0.001. Ultralytics
predictions are mapped onto the _gt.json as MovingCarTable.py does;
rfdetr_val writes them against the same _gt.json already.

Writes data/results/glass_bottle_matches.csv, one row per model, image and
kind (bottle or another category), and prints the same table.

Usage:
    python GlassBottleTable.py
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from CompareRuns import identify
from MovingCarTable import _stem, iou, load_preds

DATASET = "real_nvg"
# (capture, position, sleeve); the stems in the set carry a crop suffix
IMAGES = [
    ("capture_20251225_220740_674", "front", "sleeve"),
    ("capture_20251225_220828_343", "front", "no sleeve"),
    ("capture_20251225_220928_237", "beside", "sleeve"),
    ("capture_20251225_220850_606", "beside", "no sleeve"),
]
# yolo11x ran on the captures only as the setup check, not in the sweep
SKIP = {"yolo11x"}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run-dir", type=Path, default=Path("data/runs"))
    ap.add_argument("--datasets", type=Path, default=Path("data/datasets"))
    ap.add_argument("--iou", type=float, default=0.5)
    ap.add_argument("--out", type=Path,
                    default=Path("data/results/glass_bottle_matches.csv"))
    args = ap.parse_args()

    gt_path = args.datasets / f"{DATASET}_gt.json"
    if not gt_path.exists():
        raise SystemExit(f"{gt_path} does not exist; run the sweep first")
    gt = json.loads(gt_path.read_text(encoding="utf-8"))
    names = {c["id"]: c["name"] for c in gt["categories"]}
    ids = {_stem(i["file_name"]): i["id"] for i in gt["images"]}
    targets = []
    for capture, position, sleeve in IMAGES:
        stem = next(s for s in ids if s.startswith(capture))
        box = next(a["bbox"] for a in gt["annotations"]
                   if a["image_id"] == ids[stem] and names[a["category_id"]] == "bottle")
        targets.append((capture, position, sleeve, ids[stem], box))

    rows = []
    for run in sorted(args.run_dir.glob(f"val_*_{DATASET}")):
        pred = run / "predictions.json"
        if not pred.exists():
            print(f"{run.name}: no predictions.json, skipped")
            continue
        model, _, _ = identify(run)
        if model in SKIP:
            continue
        preds = load_preds(pred, ids, names)
        for capture, position, sleeve, iid, box in targets:
            on_box = [(p[1], iou(p[2], box), p[0]) for p in preds[iid]
                      if iou(p[2], box) >= args.iou]
            for kind in ("bottle", "other"):
                hits = [h for h in on_box if (h[2] == "bottle") == (kind == "bottle")]
                score, overlap, category = max(hits) if hits else (None, None, "")
                rows.append({
                    "model": model, "image": capture, "position": position,
                    "sleeve": sleeve, "kind": kind,
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
    print(f"\nwritten to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
