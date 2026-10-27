"""
RT-DETR Validation Script with ratio_pad Fix

This script patches the ultralytics scale_boxes function to handle RT-DETR's
float ratio_pad values correctly, preventing validation errors.

Usage:
    python rtdetr_val.py [model_path] [data_yaml] [name]

Examples:
    # Use defaults (rtdetr-l.pt, coco.yaml)
    python rtdetr_val.py

    # Specify model and dataset
    python rtdetr_val.py /models/rtdetr-l.pt /datasets/coco_nvg_green.yaml

    # Specify model, dataset, and run name
    python rtdetr_val.py /models/rtdetr-l.pt /datasets/coco_nvg_green.yaml val_rtdetr_nvg_green
"""

import sys
from ultralytics import RTDETR
import ultralytics.utils.ops as ops

from console_logging import capture_console
from console_table_to_csv import write_tables_from_log

# Save original function
_original_scale_boxes = ops.scale_boxes

def patched_scale_boxes(img1_shape, boxes, img0_shape, ratio_pad=None, padding=True, xywh=False):
    """
    Patched version of scale_boxes that handles RT-DETR's float ratio_pad.

    RT-DETR sometimes passes ratio_pad as a float instead of the expected
    nested list format [[gain_w, gain_h], [pad_w, pad_h]]. This patch
    converts the float to the proper format.
    """
    if ratio_pad is not None:
        if isinstance(ratio_pad, (int, float)):
            # Convert single float to [[gain, gain], [0, 0]]
            ratio_pad = [[ratio_pad, ratio_pad], [0, 0]]
        elif isinstance(ratio_pad, (list, tuple)) and len(ratio_pad) == 2:
            if isinstance(ratio_pad[0], (int, float)):
                # Convert [gain, pad] to [[gain, gain], [pad, pad]]
                ratio_pad = [[ratio_pad[0], ratio_pad[0]], [ratio_pad[1], ratio_pad[1]]]

    return _original_scale_boxes(img1_shape, boxes, img0_shape, ratio_pad, padding, xywh)

# Apply patch globally
ops.scale_boxes = patched_scale_boxes

# Parse command-line arguments with defaults
model_path = sys.argv[1] if len(sys.argv) > 1 else '/models/rtdetr-l.pt'
data_yaml = sys.argv[2] if len(sys.argv) > 2 else 'coco.yaml'
name = sys.argv[3] if len(sys.argv) > 3 else 'val'

# Run validation
with capture_console() as cap:
    print("="*80)
    print("RT-DETR VALIDATION (with ratio_pad fix)")
    print("="*80)
    print(f"Model:   {model_path}")
    print(f"Data:    {data_yaml}")
    print(f"Name:    {name}")
    print("="*80)
    print()

    print(f"Loading model from {model_path}...")
    model = RTDETR(model_path)

    print(f"Running validation on {data_yaml}...")
    results = model.val(data=data_yaml, name=name, save_json=True)

    print()
    print("="*80)
    print("VALIDATION RESULTS")
    print("="*80)
    print(f"mAP50-95: {results.box.map:.4f}")
    print(f"mAP50:    {results.box.map50:.4f}")
    print(f"mAP75:    {results.box.map75:.4f}")
    print("="*80)

log_path = cap.write_log(results.save_dir)
print(f"Console log saved to {log_path}")
tables = write_tables_from_log(results.save_dir)
if tables:
    print(f"Tables saved to {tables[0].parent}")
