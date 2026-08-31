"""
YOLO Validation Script with console logging.

Runs Ultralytics YOLO validation and saves the console output to
<run_dir>/logs/console.log for documentation, in addition to the usual
Ultralytics outputs (predictions.json via save_json, plots, per-class table).

Usage:
    python yolo_val.py [model_path] [data_yaml] [name]

Examples:
    python yolo_val.py
    python yolo_val.py /models/yolo11x.pt /datasets/coco_nvg_green.yaml val_yolo11x_green
"""

import sys

from ultralytics import YOLO

from console_logging import capture_console
from console_table_to_csv import write_tables_from_log

model_path = sys.argv[1] if len(sys.argv) > 1 else "/models/yolo11x.pt"
data_yaml = sys.argv[2] if len(sys.argv) > 2 else "coco.yaml"
name = sys.argv[3] if len(sys.argv) > 3 else "val"

with capture_console() as cap:
    print("=" * 80)
    print("YOLO VALIDATION")
    print("=" * 80)
    print(f"Model:   {model_path}")
    print(f"Data:    {data_yaml}")
    print(f"Name:    {name}")
    print("=" * 80)

    print(f"Loading model from {model_path}...")
    model = YOLO(model_path)

    print(f"Running validation on {data_yaml}...")
    results = model.val(data=data_yaml, name=name, save_json=True)

    print()
    print("=" * 80)
    print("VALIDATION RESULTS")
    print("=" * 80)
    print(f"mAP50-95: {results.box.map:.4f}")
    print(f"mAP50:    {results.box.map50:.4f}")
    print(f"mAP75:    {results.box.map75:.4f}")
    print("=" * 80)

log_path = cap.write_log(results.save_dir)
print(f"Console log saved to {log_path}")
tables = write_tables_from_log(results.save_dir)
if tables:
    print(f"Tables saved to {tables[0].parent}")
