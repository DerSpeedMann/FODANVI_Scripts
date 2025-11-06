from ultralytics import RTDETR
import ultralytics.utils.ops as ops

# Save original function
_original_scale_boxes = ops.scale_boxes

def patched_scale_boxes(img1_shape, boxes, img0_shape, ratio_pad=None, padding=True, xywh=False):
    # Fix: Handle float ratio_pad from RT-DETR
    if ratio_pad is not None:
        if isinstance(ratio_pad, (int, float)):
            ratio_pad = [[ratio_pad, ratio_pad], [0, 0]]
        elif isinstance(ratio_pad, (list, tuple)) and len(ratio_pad) == 2:
            if isinstance(ratio_pad[0], (int, float)):
                ratio_pad = [[ratio_pad[0], ratio_pad[0]], [ratio_pad[1], ratio_pad[1]]]
    
    return _original_scale_boxes(img1_shape, boxes, img0_shape, ratio_pad, padding, xywh)

# Apply patch
ops.scale_boxes = patched_scale_boxes

# Run validation
print('Running RT-DETR validation with patch...')
model = RTDETR('/models/rtdetr-l.pt')
results = model.val(data='coco.yaml')

print('\nValidation complete!')
print(f'mAP50-95: {results.box.map:.4f}')
print(f'mAP50: {results.box.map50:.4f}')
