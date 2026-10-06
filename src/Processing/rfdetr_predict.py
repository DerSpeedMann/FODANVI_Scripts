"""
rfdetr_predict.py

Run RF-DETR over one image, or a folder of them, and say what it found.

The validation scripts need a labelled dataset. This does not: it is for
looking at a single capture and asking whether anything is detected at all,
which is the question when the subject is new and there is no ground truth
to score against.

For YOLO and RT-DETR the equivalent already exists, `yolo detect predict`,
which cannot load RF-DETR because it is not an Ultralytics model.

Writes an annotated copy of each image, a .txt of the detections beside it,
and the console output to <out_dir>/logs/console.log, as the validation
scripts do. Nothing is scored; there is nothing to score against.

Usage, inside the container:
    python rfdetr_predict.py <model> <image|dir> <out_dir> [conf] [names.yaml]

    python rfdetr_predict.py /models/rf-detr-large.pth \\
        /data/rc_car.jpg /ultralytics/runs/detect/predict_rc_car 0.25
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import yaml
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent))

from console_logging import capture_console
# RF-DETR emits COCO's 91-class ids, 1-90 with gaps, while the yaml names
# are the contiguous 0-79. rfdetr_val.py maps between them; the same table
# is used here so a prediction is labelled the same way a validation is.
from rfdetr_val import COCO_91_TO_80, REMAP_COCO_91

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
MODEL_RESOLUTION = 560   # RF-DETR-L's native resolution, as in rfdetr_val.py


def load_names(path: str) -> dict:
    try:
        with open(path) as fh:
            names = yaml.safe_load(fh).get("names", {})
        if isinstance(names, list):
            return {i: n for i, n in enumerate(names)}
        return {int(k): v for k, v in names.items()}
    except Exception:
        return {}


def as_rgb(path: Path):
    """RF-DETR raises on anything that is not three channels."""
    with Image.open(path) as im:
        return im.convert("RGB") if im.mode != "RGB" else im.copy()


def main() -> int:
    if len(sys.argv) < 4:
        print(__doc__)
        return 1
    model_path, source, out_dir = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3])
    conf = float(sys.argv[4]) if len(sys.argv) > 4 else 0.25
    names = load_names(sys.argv[5] if len(sys.argv) > 5
                       else "/datasets/coco.yaml")

    images = ([source] if source.is_file()
              else sorted(p for p in source.rglob("*")
                          if p.suffix.lower() in IMAGE_EXT))
    if not images:
        print(f"no images under {source}")
        return 1
    out_dir.mkdir(parents=True, exist_ok=True)

    cap = capture_console()
    cap.__enter__()
    print("=" * 80)
    print("RF-DETR PREDICTION")
    print("=" * 80)
    print(f"Model:   {model_path}")
    print(f"Source:  {source}")
    print(f"Conf:    {conf}")
    print(f"Images:  {len(images)}")
    print("=" * 80)
    from rfdetr import RFDETRLarge
    model = RFDETRLarge(pretrain_weights=model_path,
                        resolution=MODEL_RESOLUTION)

    for img_path in images:
        im = as_rgb(img_path)
        det = model.predict([im], threshold=conf)
        if isinstance(det, (list, tuple)):
            det = det[0]

        found = []
        if det is not None and len(det):
            xyxy = np.asarray(det.xyxy)
            confs = np.asarray(det.confidence)
            cls = np.asarray(det.class_id)
            order = np.argsort(-confs)
            draw = ImageDraw.Draw(im)
            for i in order:
                cid = int(cls[i])
                if REMAP_COCO_91:
                    cid = COCO_91_TO_80.get(cid, cid)
                label = names.get(cid, f"class {cid}")
                found.append((label, float(confs[i]), xyxy[i].tolist()))
                x0, y0, x1, y1 = xyxy[i]
                draw.rectangle([x0, y0, x1, y1], outline=(255, 0, 0), width=3)
                draw.text((x0 + 3, max(0, y0 - 12)),
                          f"{label} {confs[i]:.2f}", fill=(255, 0, 0))

        stem = img_path.stem
        im.save(out_dir / f"{stem}_pred.jpg", quality=95)
        with open(out_dir / f"{stem}_pred.txt", "w", encoding="utf-8") as fh:
            for label, c, (x0, y0, x1, y1) in found:
                fh.write(f"{label}\t{c:.4f}\t{x0:.1f}\t{y0:.1f}"
                         f"\t{x1:.1f}\t{y1:.1f}\n")

        if found:
            print(f"{img_path.name}: {len(found)} detection(s)")
            for label, c, _ in found[:10]:
                print(f"    {label:<16} {c:.3f}")
        else:
            print(f"{img_path.name}: nothing above {conf}")

    print(f"\nwrote {out_dir}")
    cap.__exit__(None, None, None)
    print(f"Console log saved to {cap.write_log(out_dir)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
