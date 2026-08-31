"""
console_table_to_csv.py

Parse the per-class table Ultralytics prints during validation (as captured in
a run's logs/console.log) into CSV files. Works for any dataset, including the
NVG sets that have no COCO-format ground truth, because it reads the numbers
Ultralytics already computed rather than re-evaluating.

Classes are also aggregated into their COCO supercategories for a compact
overview of which object types are detected well.

Outputs (in --out):
    per_class_metrics.csv      class, supercategory, images, instances, precision, recall, map50, map50_95
    supercategory_metrics.csv  the same metrics averaged per supercategory

Pure standard library, no dependencies.

Usage:
    python console_table_to_csv.py --log results/val_yolo11x_clean/logs/console.log --out results/val_yolo11x_clean/tables
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path
from collections import defaultdict
from statistics import mean

# COCO class -> supercategory
SUPERCATEGORY = {
    "person": "person",
    "bicycle": "vehicle", "car": "vehicle", "motorcycle": "vehicle", "airplane": "vehicle",
    "bus": "vehicle", "train": "vehicle", "truck": "vehicle", "boat": "vehicle",
    "traffic light": "outdoor", "fire hydrant": "outdoor", "stop sign": "outdoor",
    "parking meter": "outdoor", "bench": "outdoor",
    "bird": "animal", "cat": "animal", "dog": "animal", "horse": "animal", "sheep": "animal",
    "cow": "animal", "elephant": "animal", "bear": "animal", "zebra": "animal", "giraffe": "animal",
    "backpack": "accessory", "umbrella": "accessory", "handbag": "accessory", "tie": "accessory",
    "suitcase": "accessory",
    "frisbee": "sports", "skis": "sports", "snowboard": "sports", "sports ball": "sports",
    "kite": "sports", "baseball bat": "sports", "baseball glove": "sports", "skateboard": "sports",
    "surfboard": "sports", "tennis racket": "sports",
    "bottle": "kitchen", "wine glass": "kitchen", "cup": "kitchen", "fork": "kitchen",
    "knife": "kitchen", "spoon": "kitchen", "bowl": "kitchen",
    "banana": "food", "apple": "food", "sandwich": "food", "orange": "food", "broccoli": "food",
    "carrot": "food", "hot dog": "food", "pizza": "food", "donut": "food", "cake": "food",
    "chair": "furniture", "couch": "furniture", "potted plant": "furniture", "bed": "furniture",
    "dining table": "furniture", "toilet": "furniture",
    "tv": "electronic", "laptop": "electronic", "mouse": "electronic", "remote": "electronic",
    "keyboard": "electronic", "cell phone": "electronic",
    "microwave": "appliance", "oven": "appliance", "toaster": "appliance", "sink": "appliance",
    "refrigerator": "appliance",
    "book": "indoor", "clock": "indoor", "vase": "indoor", "scissors": "indoor",
    "teddy bear": "indoor", "hair drier": "indoor", "toothbrush": "indoor",
}


def _is_number(token: str) -> bool:
    try:
        float(token)
        return True
    except ValueError:
        return False


def parse_table(text: str) -> list[dict]:
    """Extract per-class rows from the Ultralytics validation table.

    Each data row is: <class name> <images> <instances> <P> <R> <mAP50> <mAP50-95>,
    where the class name may contain spaces (e.g. 'wine glass'), so the six
    trailing numeric columns are split off from the right.
    """
    rows: list[dict] = []
    in_table = False
    for raw in text.splitlines():
        line = raw.strip()
        if not in_table:
            if "Class" in line and "Instances" in line and "mAP50-95" in line:
                in_table = True
            continue
        if not line or line.startswith("Speed:"):
            break  # end of the table
        tokens = line.split()
        if len(tokens) < 7 or not all(_is_number(t) for t in tokens[-6:]):
            continue
        name = " ".join(tokens[:-6])
        images, instances, p, r, map50, map5095 = tokens[-6:]
        rows.append({
            "class": name,
            "supercategory": "(overall)" if name == "all" else SUPERCATEGORY.get(name, "n/a"),
            "images": int(float(images)),
            "instances": int(float(instances)),
            "precision": float(p),
            "recall": float(r),
            "map50": float(map50),
            "map50_95": float(map5095),
        })
    return rows


def aggregate(rows: list[dict]) -> list[dict]:
    groups: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        if row["class"] == "all":
            continue
        groups[row["supercategory"]].append(row)
    summary = []
    for name, items in sorted(groups.items()):
        summary.append({
            "supercategory": name,
            "n_classes": len(items),
            "instances": sum(it["instances"] for it in items),
            "precision": round(mean(it["precision"] for it in items), 4),
            "recall": round(mean(it["recall"] for it in items), 4),
            "map50": round(mean(it["map50"] for it in items), 4),
            "map50_95": round(mean(it["map50_95"] for it in items), 4),
        })
    return summary


def write_csv(rows: list[dict], path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def write_tables_from_log(run_dir) -> list[Path]:
    """Read <run_dir>/logs/console.log and write CSV tables into <run_dir>/tables.

    Returns the written paths, or [] if the log has no per-class table. Intended
    to be called by the validation scripts right after they save their log.
    """
    run_dir = Path(run_dir)
    log_path = run_dir / "logs" / "console.log"
    if not log_path.exists():
        return []
    rows = parse_table(log_path.read_text(encoding="utf-8", errors="replace"))
    if not rows:
        return []
    out_dir = run_dir / "tables"
    out_dir.mkdir(parents=True, exist_ok=True)
    per_class = out_dir / "per_class_metrics.csv"
    supercat = out_dir / "supercategory_metrics.csv"
    write_csv(rows, per_class)
    write_csv(aggregate(rows), supercat)
    return [per_class, supercat]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--log", required=True, help="path to a run's logs/console.log")
    parser.add_argument("--out", default="tables", help="output directory")
    args = parser.parse_args()

    text = Path(args.log).read_text(encoding="utf-8", errors="replace")
    rows = parse_table(text)
    if not rows:
        raise SystemExit("No per-class table found in the log.")

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    write_csv(rows, out_dir / "per_class_metrics.csv")
    write_csv(aggregate(rows), out_dir / "supercategory_metrics.csv")
    print(f"Parsed {len([r for r in rows if r['class'] != 'all'])} classes.")
    print(f"Wrote:\n  {out_dir/'per_class_metrics.csv'}\n  {out_dir/'supercategory_metrics.csv'}")


if __name__ == "__main__":
    main()
