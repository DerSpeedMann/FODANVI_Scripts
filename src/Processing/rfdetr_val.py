"""
RF-DETR Validation - YOLO-style mAP

Loads Roboflow's RF-DETR, runs inference on a YOLO-format validation set,
converts predictions + YOLO labels into COCO JSON, and computes mAP via
pycocotools so results are directly comparable to Ultralytics' model.val()
output (mAP50, mAP50-95, mAP75).

Usage:
    python rfdetr_val.py <model_path> <data_yaml> [name]

Example:
    python rfdetr_val.py /models/rf-detr-large.pth /datasets/coco_nvg_clean.yaml val_rfdetr

Notes:
    - Requires `rfdetr==1.2.0` and `pycocotools` (rfdetr is NOT in the
      ultralytics docker image; install at runtime, see docker_run command in
      the Readme).
    - The rfdetr pin is essential. 1.2.0 is the release current when the
      models were selected, and its RFDETRLarge is the original RF-DETR-L
      (rf-detr-large.pth, 560 px) that the leaderboard ranked at the time.
      From rfdetr 1.4.0 on, RFDETRLarge loads a different, newer model and
      the original is renamed RFDETRLargeDeprecated, so an unpinned install
      silently evaluates the wrong model under the same name.
    - transformers must be pinned too (4.53.3, current when rfdetr 1.2.0
      was released): rfdetr 1.2.0 does not cap it, and transformers 5.x
      removed find_pruneable_heads_and_indices, so the import fails with
      an ImportError on an unpinned install.
    - Assumes the RF-DETR model emits the same class IDs as the YAML's `names:`.
      If the model was fine-tuned on a remapped subset, predictions won't align
      with GT and mAP will be wrong.
"""

import json
import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np
import torch
import yaml
from PIL import Image
from pycocotools.coco import COCO
from pycocotools.cocoeval import COCOeval
from tqdm import tqdm

from console_logging import capture_console
from console_table_to_csv import write_tables_from_log

# RF-DETR-L, the detection checkpoint `rf-detr-large.pth`. With rfdetr pinned
# to 1.2.0 this class is the original Large model; see the pin note above.
from rfdetr import RFDETRLarge as RFDETRClass

CONF_THRESHOLD = 0.001  # Ultralytics uses 0.001 for val to maximize recall
MODEL_RESOLUTION = 560  # Must match the checkpoint's training resolution;
                        # 560 is RF-DETR-L's native resolution, the
                        # RFDETRLarge default in rfdetr 1.2.0.
BATCH_SIZE = 1          # RF-DETR's predict() doesn't actually GPU-batch a list of
                        # inputs — passing batch=8 ran ~4x slower than batch=1.
OPTIMIZE_FOR_INFERENCE = False  # On the segmentation checkpoint used earlier (768 px)
                                # this *hurt* throughput (1.6 it/s vs ~5 it/s eager):
                                # the TorchScript tracer can't handle the model's
                                # dynamic control flow and the resulting graph has slow
                                # fallback paths. Untested on RF-DETR-L.
REMAP_COCO_91 = True    # Many RF-DETR checkpoints emit COCO 91-class IDs (1-90
                        # with gaps at 12, 26, 29, 30, 45, 66, 68, 69, 71, 83).
                        # Set False if your YAML's `names:` already uses that
                        # space; True if it uses contiguous 0-79.

# COCO 91-class (1-indexed, with gaps) → COCO 80-class (contiguous 0-indexed)
COCO_91_TO_80 = {
    1: 0, 2: 1, 3: 2, 4: 3, 5: 4, 6: 5, 7: 6, 8: 7, 9: 8, 10: 9,
    11: 10, 13: 11, 14: 12, 15: 13, 16: 14, 17: 15, 18: 16, 19: 17,
    20: 18, 21: 19, 22: 20, 23: 21, 24: 22, 25: 23, 27: 24, 28: 25,
    31: 26, 32: 27, 33: 28, 34: 29, 35: 30, 36: 31, 37: 32, 38: 33,
    39: 34, 40: 35, 41: 36, 42: 37, 43: 38, 44: 39, 46: 40, 47: 41,
    48: 42, 49: 43, 50: 44, 51: 45, 52: 46, 53: 47, 54: 48, 55: 49,
    56: 50, 57: 51, 58: 52, 59: 53, 60: 54, 61: 55, 62: 56, 63: 57,
    64: 58, 65: 59, 67: 60, 70: 61, 72: 62, 73: 63, 74: 64, 75: 65,
    76: 66, 77: 67, 78: 68, 79: 69, 80: 70, 81: 71, 82: 72, 84: 73,
    85: 74, 86: 75, 87: 76, 88: 77, 89: 78, 90: 79,
}


def load_yolo_yaml(yaml_path):
    yaml_path = Path(yaml_path)
    with open(yaml_path) as f:
        cfg = yaml.safe_load(f)
    raw_path = cfg.get("path", ".")
    base = Path(raw_path)
    if not base.is_absolute():
        # Ultralytics convention: resolve `path:` relative to the YAML file's dir.
        base = (yaml_path.parent / base).resolve()
    val = cfg["val"]
    if isinstance(val, str):
        val = [val]
    val_dirs = [base / d for d in val]
    names = cfg["names"]
    if isinstance(names, list):
        names = {i: n for i, n in enumerate(names)}
    print(f"YAML path:    {base}  (exists={base.exists()})")
    for d in val_dirs:
        print(f"  val dir:    {d}  (exists={d.exists()})")
    return val_dirs, names


def collect_pairs(val_dirs):
    exts = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
    pairs = []
    for img_dir in val_dirs:
        if not img_dir.exists():
            print(f"  SKIP missing dir: {img_dir}")
            continue
        label_dir = Path(str(img_dir).replace("images", "labels", 1))
        n_before = len(pairs)
        for img in img_dir.rglob("*"):
            if img.suffix.lower() in exts:
                pairs.append((img, label_dir / (img.stem + ".txt")))
        print(f"  {img_dir}: {len(pairs) - n_before} images, "
              f"label dir={label_dir} (exists={label_dir.exists()})")
    return pairs


def yolo_to_xywh(cx, cy, w, h, iw, ih):
    return [(cx - w / 2) * iw, (cy - h / 2) * ih, w * iw, h * ih]


def build_gt(pairs, names):
    images, annotations = [], []
    ann_id = 1
    for img_id, (img_path, lbl_path) in enumerate(tqdm(pairs, desc="Reading GT"), start=1):
        with Image.open(img_path) as im:
            iw, ih = im.size
        images.append({"id": img_id, "file_name": str(img_path), "width": iw, "height": ih})
        if not lbl_path.exists():
            continue
        with open(lbl_path) as f:
            for line in f:
                parts = line.strip().split()
                if len(parts) < 5:
                    continue
                cls = int(parts[0])
                cx, cy, w, h = map(float, parts[1:5])
                bbox = yolo_to_xywh(cx, cy, w, h, iw, ih)
                annotations.append({
                    "id": ann_id,
                    "image_id": img_id,
                    "category_id": cls,
                    "bbox": bbox,
                    "area": bbox[2] * bbox[3],
                    "iscrowd": 0,
                })
                ann_id += 1
    categories = [{"id": k, "name": v} for k, v in names.items()]
    return {"images": images, "annotations": annotations, "categories": categories}


def install_forward_timer(model):
    """Wrap the underlying nn.Module's forward() with a CUDA-synced timer.
    Returns a list whose [0] element accumulates pure forward-pass seconds.
    Returns None if we can't find the underlying module (timing won't be available).

    Searches the wrapper's attributes (and one level of nesting) for the first
    torch.nn.Module. RF-DETR's wrapper class names vary across versions."""
    visited = set()

    def find_nn_module(obj, depth=0):
        if depth > 2 or id(obj) in visited:
            return None, None
        visited.add(id(obj))
        for attr in dir(obj):
            if attr.startswith("_"):
                continue
            try:
                val = getattr(obj, attr)
            except Exception:
                continue
            if isinstance(val, torch.nn.Module):
                return val, f"{type(obj).__name__}.{attr}"
            # Recurse one level into plain Python containers/objects.
            if depth == 0 and hasattr(val, "__dict__") and not callable(val):
                found, path = find_nn_module(val, depth + 1)
                if found is not None:
                    return found, f"{attr}.{path}"
        return None, None

    nn_module, location = find_nn_module(model)
    if nn_module is None:
        return None
    print(f"Forward-pass timer hooked on: {location} ({type(nn_module).__name__})")

    cuda = torch.cuda.is_available()
    accumulator = [0.0]
    orig_forward = nn_module.forward

    def timed_forward(*args, **kwargs):
        if cuda:
            torch.cuda.synchronize()
        t0 = time.perf_counter()
        out = orig_forward(*args, **kwargs)
        if cuda:
            torch.cuda.synchronize()
        accumulator[0] += time.perf_counter() - t0
        return out

    nn_module.forward = timed_forward
    return accumulator


def run_inference(model, pairs, valid_class_ids, forward_seconds=None):
    preds = []
    dropped = 0
    dropped_ids = set()
    n = len(pairs)
    predict_seconds = 0.0  # Sum of model.predict() wall time across all batches.
    with tqdm(total=n, desc="Inferring") as pbar:
        for start in range(0, n, BATCH_SIZE):
            chunk = pairs[start : start + BATCH_SIZE]
            paths = [str(p[0]) for p in chunk]
            actual = len(paths)
            # Optimized model requires fixed batch size; pad the last batch
            # and discard the padded results.
            if actual < BATCH_SIZE:
                paths = paths + [paths[-1]] * (BATCH_SIZE - actual)
            t0 = time.perf_counter()
            results = model.predict(paths, threshold=CONF_THRESHOLD)
            predict_seconds += time.perf_counter() - t0
            if not isinstance(results, (list, tuple)):
                results = [results]
            for offset, det in enumerate(results[:actual]):
                img_id = start + offset + 1
                if det is None or len(det) == 0:
                    continue
                xyxy = np.asarray(det.xyxy)
                confs = np.asarray(det.confidence)
                clsids = np.asarray(det.class_id)
                for (x1, y1, x2, y2), conf, cls in zip(xyxy, confs, clsids):
                    cls = int(cls)
                    if REMAP_COCO_91:
                        mapped = COCO_91_TO_80.get(cls)
                        if mapped is None:
                            dropped += 1
                            dropped_ids.add(cls)
                            continue
                        cls = mapped
                    if cls not in valid_class_ids:
                        dropped += 1
                        dropped_ids.add(cls)
                        continue
                    preds.append({
                        "image_id": img_id,
                        "category_id": cls,
                        "bbox": [float(x1), float(y1), float(x2 - x1), float(y2 - y1)],
                        "score": float(conf),
                    })
            pbar.update(len(chunk))
    if dropped:
        print(f"WARNING: dropped {dropped} predictions with class_ids outside the YAML "
              f"taxonomy. Unique offending IDs: {sorted(dropped_ids)}")
        print("  → Likely the checkpoint uses COCO's 91-class ID space (with gaps); "
              "remap predictions to contiguous 0-79 to recover those detections.")
    return preds, predict_seconds


def iou_xywh(box1, box2):
    x1, y1, w1, h1 = box1
    x2, y2, w2, h2 = box2
    xa, ya = max(x1, x2), max(y1, y2)
    xb, yb = min(x1 + w1, x2 + w2), min(y1 + h1, y2 + h2)
    inter = max(0, xb - xa) * max(0, yb - ya)
    union = w1 * h1 + w2 * h2 - inter
    return inter / union if union > 0 else 0.0


def per_class_pr_at_max_f1(gt_dict, predictions, iou_thresh=0.5):
    """For each class with GT, compute P/R at max-F1 confidence threshold +
    image/instance counts. Returns {class_id: dict(images, instances, P, R)}."""
    gt_by_cls_img = defaultdict(lambda: defaultdict(list))
    for ann in gt_dict["annotations"]:
        gt_by_cls_img[ann["category_id"]][ann["image_id"]].append(ann["bbox"])

    pred_by_cls = defaultdict(list)
    for p in predictions:
        pred_by_cls[p["category_id"]].append(p)

    out = {}
    for cls, by_img in gt_by_cls_img.items():
        n_images = len(by_img)
        n_inst = sum(len(v) for v in by_img.values())
        preds = sorted(pred_by_cls.get(cls, []), key=lambda p: -p["score"])
        if not preds:
            out[cls] = {"images": n_images, "instances": n_inst, "P": 0.0, "R": 0.0}
            continue

        matched = defaultdict(set)
        tps, fps = [], []
        for p in preds:
            gts = by_img.get(p["image_id"], [])
            best_iou, best_j = 0.0, -1
            for j, gt_box in enumerate(gts):
                if j in matched[p["image_id"]]:
                    continue
                iou = iou_xywh(p["bbox"], gt_box)
                if iou > best_iou:
                    best_iou, best_j = iou, j
            if best_iou >= iou_thresh:
                matched[p["image_id"]].add(best_j)
                tps.append(1); fps.append(0)
            else:
                tps.append(0); fps.append(1)

        cum_tp = np.cumsum(tps)
        cum_fp = np.cumsum(fps)
        precisions = cum_tp / np.maximum(cum_tp + cum_fp, 1)
        recalls = cum_tp / max(n_inst, 1)
        f1 = 2 * precisions * recalls / np.maximum(precisions + recalls, 1e-12)
        idx = int(np.argmax(f1))
        out[cls] = {
            "images": n_images,
            "instances": n_inst,
            "P": float(precisions[idx]),
            "R": float(recalls[idx]),
        }
    return out


def per_class_ap_from_pycoco(ev):
    """Pull per-category mAP50 and mAP50-95 out of a COCOeval object after
    summarize(). Returns {category_id: dict(mAP50, mAP)}."""
    prec = ev.eval["precision"]  # [T(=10), R(=101), K, A(=4), M(=3)]
    cat_ids = list(ev.params.catIds)
    out = {}
    for k, cid in enumerate(cat_ids):
        p_k = prec[:, :, k, 0, 2]  # area=all, maxDets=100
        valid = p_k > -1
        ap50 = float(p_k[0][valid[0]].mean()) if valid[0].any() else 0.0
        ap = float(p_k[valid].mean()) if valid.any() else 0.0
        out[cid] = {"mAP50": ap50, "mAP": ap}
    return out


def print_ultralytics_table(per_class_pr, per_class_ap, names, total_images):
    """Print Ultralytics-style table: class | images | instances | P | R | mAP50 | mAP50-95."""
    classes = sorted(per_class_pr.keys())
    if not classes:
        print("No classes with GT — table empty.")
        return

    header = f"{'Class':>22}{'Images':>11}{'Instances':>11}{'P':>11}{'R':>11}{'mAP50':>11}{'mAP50-95':>11}"
    print(header)

    total_inst = sum(m["instances"] for m in per_class_pr.values())
    mean_p = float(np.mean([per_class_pr[c]["P"] for c in classes]))
    mean_r = float(np.mean([per_class_pr[c]["R"] for c in classes]))
    mean_ap50 = float(np.mean([per_class_ap.get(c, {}).get("mAP50", 0.0) for c in classes]))
    mean_ap = float(np.mean([per_class_ap.get(c, {}).get("mAP", 0.0) for c in classes]))
    print(f"{'all':>22}{total_images:>11d}{total_inst:>11d}"
          f"{mean_p:>11.4f}{mean_r:>11.4f}{mean_ap50:>11.4f}{mean_ap:>11.4f}")

    for cid in classes:
        pr = per_class_pr[cid]
        ap = per_class_ap.get(cid, {"mAP50": 0.0, "mAP": 0.0})
        print(f"{names.get(cid, str(cid)):>22}{pr['images']:>11d}{pr['instances']:>11d}"
              f"{pr['P']:>11.4f}{pr['R']:>11.4f}{ap['mAP50']:>11.4f}{ap['mAP']:>11.4f}")


def next_run_dir(base_dir, name):
    """Match Ultralytics: if `name` is taken, append -2, -3, ..."""
    base_dir = Path(base_dir)
    if not (base_dir / name).exists():
        return base_dir / name
    n = 2
    while (base_dir / f"{name}-{n}").exists():
        n += 1
    return base_dir / f"{name}-{n}"


def main():
    model_path = sys.argv[1] if len(sys.argv) > 1 else "/models/rf-detr-large.pth"
    data_yaml = sys.argv[2] if len(sys.argv) > 2 else "/datasets/coco_nvg_clean.yaml"
    name = sys.argv[3] if len(sys.argv) > 3 else "val_rfdetr"

    out_dir = next_run_dir("/ultralytics/runs/detect", name)
    out_dir.mkdir(parents=True)
    global _run_dir
    _run_dir = out_dir

    print("=" * 80)
    print("RF-DETR VALIDATION (YOLO-style mAP via pycocotools)")
    print("=" * 80)
    print(f"Model:   {model_path}")
    print(f"Data:    {data_yaml}")
    print(f"Out:     {out_dir}")
    print("=" * 80)

    val_dirs, names = load_yolo_yaml(data_yaml)
    pairs = collect_pairs(val_dirs)
    print(f"Found {len(pairs)} validation images across {len(val_dirs)} dir(s)")

    print(f"Loading RF-DETR from {model_path}...")
    model = RFDETRClass(pretrain_weights=model_path, resolution=MODEL_RESOLUTION)
    if OPTIMIZE_FOR_INFERENCE:
        try:
            model.optimize_for_inference(batch_size=BATCH_SIZE)
            print(f"Model optimized for inference (batch_size={BATCH_SIZE}).")
        except Exception as e:
            print(f"optimize_for_inference() not available or failed: {e}")

    forward_seconds = install_forward_timer(model)
    if forward_seconds is None:
        print("Forward-pass timer not installed (no nn.Module attribute found).")

    gt_dict = build_gt(pairs, names)
    gt_path = out_dir / "gt.json"
    with open(gt_path, "w") as f:
        json.dump(gt_dict, f)

    preds, predict_seconds = run_inference(
        model, pairs, valid_class_ids=set(names.keys()), forward_seconds=forward_seconds
    )
    pred_path = out_dir / "predictions.json"
    with open(pred_path, "w") as f:
        json.dump(preds, f)

    if not preds:
        print("No predictions produced — aborting eval.")
        sys.exit(1)

    coco_gt = COCO(str(gt_path))
    coco_dt = coco_gt.loadRes(str(pred_path))
    ev = COCOeval(coco_gt, coco_dt, "bbox")
    # Only evaluate classes actually present in GT (matches Ultralytics behavior).
    gt_classes = sorted({a["category_id"] for a in gt_dict["annotations"]})
    ev.params.catIds = gt_classes
    ev.evaluate()
    ev.accumulate()
    ev.summarize()

    per_class_pr = per_class_pr_at_max_f1(gt_dict, preds, iou_thresh=0.5)
    per_class_ap = per_class_ap_from_pycoco(ev)

    print()
    print("=" * 80)
    print("PER-CLASS RESULTS")
    print("=" * 80)
    print_ultralytics_table(per_class_pr, per_class_ap, names, total_images=len(pairs))

    n = len(pairs)
    ms_total = (predict_seconds / max(n, 1)) * 1000
    if forward_seconds is not None:
        ms_forward = (forward_seconds[0] / max(n, 1)) * 1000
        ms_other = ms_total - ms_forward
        print(f"Speed: {ms_other:.1f}ms preprocess+postprocess, {ms_forward:.1f}ms inference, "
              f"{ms_total:.1f}ms total per image")
    else:
        print(f"Speed: {ms_total:.1f}ms total per image "
              f"(forward-pass timer unavailable)")
    print(f"Results saved to {out_dir}")

    print("=" * 80)
    print(f"Overall mAP50-95: {ev.stats[0]:.4f}")
    print(f"Overall mAP50:    {ev.stats[1]:.4f}")
    print(f"Overall mAP75:    {ev.stats[2]:.4f}")
    print("=" * 80)


_run_dir = None

if __name__ == "__main__":
    cap = capture_console()
    with cap:
        try:
            main()
        finally:
            if _run_dir is not None:
                log_path = cap.write_log(_run_dir)
                print(f"Console log saved to {log_path}")
                tables = write_tables_from_log(_run_dir)
                if tables:
                    print(f"Tables saved to {tables[0].parent}")
