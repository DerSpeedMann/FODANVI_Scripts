"""
RT-DETR Prediction Script with the ratio_pad fix.

Runs Ultralytics RT-DETR prediction over images that have no labels, and
saves the console output to <run_dir>/logs/console.log alongside the
annotated images and per-image .txt that Ultralytics writes.

It carries the same scale_boxes patch as rtdetr_val.py: RT-DETR hands
float ratio_pad values to a function that assumes otherwise.

`yolo detect predict` does the same detection but keeps no cleaned log, so a
prediction run leaves nothing in the result folder explaining what produced
it. Every validation run here records that; predictions should too.

Nothing is scored. This is for asking whether a subject is detected at all,
where there is no ground truth to score against.

Usage:
    python rtdetr_predict.py [model_path] [source] [name] [conf]

Examples:
    python rtdetr_predict.py /models/rtdetr-x.pt /data predict_rtdetrx_rc_car
    python rtdetr_predict.py /models/rtdetr-x.pt /data/rc_car.jpg p_rc 0.05
"""

import sys
from collections import Counter

from ultralytics import RTDETR
from ultralytics.utils import ops

from console_logging import capture_console

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

model_path = sys.argv[1] if len(sys.argv) > 1 else "/models/rtdetr-x.pt"
source = sys.argv[2] if len(sys.argv) > 2 else "/data"
name = sys.argv[3] if len(sys.argv) > 3 else "predict"
conf = float(sys.argv[4]) if len(sys.argv) > 4 else 0.25

with capture_console() as cap:
    print("=" * 80)
    print("RT-DETR PREDICTION")
    print("=" * 80)
    print(f"Model:   {model_path}")
    print(f"Source:  {source}")
    print(f"Name:    {name}")
    print(f"Conf:    {conf}")
    print("=" * 80)

    model = RTDETR(model_path)
    results = model.predict(source=source, name=name, conf=conf,
                            save=True, save_txt=True, save_conf=True)

    print()
    print("=" * 80)
    print("DETECTIONS")
    print("=" * 80)
    total = Counter()
    for r in results:
        counts = Counter(r.names[int(c)] for c in r.boxes.cls.tolist())
        total.update(counts)
        shown = ", ".join(f"{n} x{c}" for n, c in counts.most_common()) \
            or f"nothing above {conf}"
        print(f"{r.path.split('/')[-1]}: {shown}")
    print("-" * 80)
    print("total: " + (", ".join(f"{n} x{c}" for n, c in total.most_common())
                       or "no detections"))
    print("=" * 80)

save_dir = results[0].save_dir if results else None
if save_dir:
    log_path = cap.write_log(save_dir)
    print(f"Console log saved to {log_path}")
