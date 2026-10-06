"""
YOLO Prediction Script with console logging.

Runs Ultralytics YOLO prediction over images that have no labels, and saves
the console output to <run_dir>/logs/console.log alongside the annotated
images and per-image .txt that Ultralytics writes.

`yolo detect predict` does the same detection but keeps no cleaned log, so a
prediction run leaves nothing in the result folder explaining what produced
it. Every validation run here records that; predictions should too.

Nothing is scored. This is for asking whether a subject is detected at all,
where there is no ground truth to score against.

Usage:
    python yolo_predict.py [model_path] [source] [name] [conf]

Examples:
    python yolo_predict.py /models/yolo12x.pt /data predict_yolo12x_rc_car
    python yolo_predict.py /models/yolo12x.pt /data/rc_car.jpg p_rc 0.05
"""

import sys
from collections import Counter

from ultralytics import YOLO

from console_logging import capture_console

model_path = sys.argv[1] if len(sys.argv) > 1 else "/models/yolo12x.pt"
source = sys.argv[2] if len(sys.argv) > 2 else "/data"
name = sys.argv[3] if len(sys.argv) > 3 else "predict"
conf = float(sys.argv[4]) if len(sys.argv) > 4 else 0.25

with capture_console() as cap:
    print("=" * 80)
    print("YOLO PREDICTION")
    print("=" * 80)
    print(f"Model:   {model_path}")
    print(f"Source:  {source}")
    print(f"Name:    {name}")
    print(f"Conf:    {conf}")
    print("=" * 80)

    model = YOLO(model_path)
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
