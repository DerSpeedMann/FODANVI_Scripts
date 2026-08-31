Prepare Images:

cd "C:\Users\micha\Desktop\private\FH\MA\Tests"
python .\OD-A-NVI_Scripts\src\Processing\GenerateCrops.py .\captured_images\ .\images_cropped\26_04_29
Copy-Item -Path .\images_cropped\* -Destination .\images
python .\OD-A-NVI_Scripts\src\Processing\Preprocess.py .\images_cropped\ .\images   
python .\OD-A-NVI_Scripts\src\Processing\GenerateColorShift.py .\images\ .\images
python .\OD-A-NVI_Scripts\src\Processing\GenerateGrayscales.py .\images\ .\images

Check Images:

 docker run --gpus all --rm `
  -v ${PWD}\images:/data `
  -v ${PWD}\results:/ultralytics/runs/detect `
  -v ${PWD}\models:/models `
  ultralytics/ultralytics:latest `
  yolo detect predict model=/models/rtdetr-l.pt source=/data save_txt=True
  
docker run --gpus all --rm `
  -v ${PWD}\images:/data `
  -v ${PWD}\results:/ultralytics/runs/detect `
  -v ${PWD}\models:/models `
  ultralytics/ultralytics:latest `
  yolo detect predict model=/models/yolo11x.pt source=/data save_txt=True


docker run --gpus all --rm `
  -v ${PWD}\images:/data `
  -v ${PWD}\results:/ultralytics/runs/detect `
  -v ${PWD}\models:/models `
  ultralytics/ultralytics:latest `
  yolo detect predict model=/models/yolo11s_clean-noisy.pt source=/data save_txt=True



Validate models:

(All three scripts print the per-class table and write a cleaned logs/console.log
into their run folder under results/.)

docker run --gpus all --rm `
  --shm-size=18g `
  -v ${PWD}\datasets:/datasets `
  -v ${PWD}\models:/models `
  -v ${PWD}\results:/ultralytics/runs/detect `
  -v ${PWD}\OD-A-NVI_Scripts\src\Processing:/workspace `
  ultralytics/ultralytics:latest `
  python /workspace/yolo_val.py /models/yolo11x.pt coco.yaml val_yolo11x
 
docker run --gpus all --rm `
  --shm-size=8g `
  -v ${PWD}\results:/ultralytics/runs/detect `
  -v ${PWD}\models:/models `
  -v ${PWD}\datasets:/datasets `
  -v ${PWD}\OD-A-NVI_Scripts\src\Processing:/workspace `
  ultralytics/ultralytics:latest `
  python /workspace/rtdetr_val_fixed.py /models/rtdetr-x.pt /datasets/dataset.yaml

docker run --gpus all --rm `
  --shm-size=8g `
  -v ${PWD}\datasets:/datasets `
  -v ${PWD}\models:/models `
  -v ${PWD}\results:/ultralytics/runs/detect `
  -v ${PWD}\OD-A-NVI_Scripts\src\Processing:/workspace `
  ultralytics/ultralytics:latest `
  bash -c "pip install --quiet rfdetr pycocotools && python /workspace/rfdetr_val.py /models/rf-detr-seg-2xl-ft.pth /datasets/dataset.yaml val_rfdetr"


Apply NVG styling to images:

python .\OD-A-NVI_Scripts\src\Processing\GenerateNVG.py datasets/coco/images/val2017 datasets/coco_nvg_white/images/val2017 -c white
python .\OD-A-NVI_Scripts\src\Processing\CopyFilesWithSuffix.py datasets/coco/labels/val2017 datasets/coco_nvg_white/labels/val2017 _nvg_white

python .\OD-A-NVI_Scripts\src\Processing\GenerateNVG.py datasets/coco/images/val2017 datasets/coco_nvg_green/images/val2017 -c green
python .\OD-A-NVI_Scripts\src\Processing\CopyFilesWithSuffix.py datasets/coco/labels/val2017 datasets/coco_nvg_green/labels/val2017 _nvg_green

 
Test Convertet Images:

docker run --gpus all --rm `
  --shm-size=8g `
  -v ${PWD}\datasets:/datasets `
  -v ${PWD}\models:/models `
  -v ${PWD}\results:/ultralytics/runs/detect `
  -v ${PWD}\OD-A-NVI_Scripts\src\Processing:/workspace `
  ultralytics/ultralytics:latest `
  python /workspace/yolo_val.py /models/yolo11x.pt /datasets/coco_nvg_green.yaml val_yolo_nvg
  
docker run --gpus all --rm `
  --shm-size=8g `
  -v ${PWD}\results:/ultralytics/runs/detect `
  -v ${PWD}\models:/models `
  -v ${PWD}\datasets:/datasets `
  -v ${PWD}\OD-A-NVI_Scripts\src\Processing:/workspace `
  ultralytics/ultralytics:latest `
  python /workspace/rtdetr_val_fixed.py /models/rtdetr-l.pt /datasets/coco_nvg_green.yaml
  
Create converted training and validation data remove noise, blur, bloom and vignette for better training results:

python .\OD-A-NVI_Scripts\src\Processing\GenerateNVG.py datasets/coco/images/train2017 datasets/coco_nvg/images/train2017 `
  --color white  `
  --noise-intensity 0 `
  --blur-amount 0 `
  --bloom-intensity 0 `
  --vignette-intensity 0

python .\OD-A-NVI_Scripts\src\Processing\CopyFilesWithSuffix.py datasets/coco/labels/train2017 datasets/coco_nvg/labels/train2017 _nvg_white

python .\OD-A-NVI_Scripts\src\Processing\GenerateNVG.py datasets/coco/images/val2017 datasets/coco_nvg/images/val2017 `
  --color white  `
  --noise-intensity 0 `
  --blur-amount 0 `
  --bloom-intensity 0 `
  --vignette-intensity 0
  
python .\OD-A-NVI_Scripts\src\Processing\CopyFilesWithSuffix.py datasets/coco/labels/val2017 datasets/coco_nvg/labels/val2017 _nvg_white

python .\OD-A-NVI_Scripts\src\Processing\GenerateNVG.py datasets/coco/images/train2017 datasets/coco_nvg/images/train2017 `
  --color green  `
  --noise-intensity 0 `
  --blur-amount 0 `
  --bloom-intensity 0 `
  --vignette-intensity 0
  
python .\OD-A-NVI_Scripts\src\Processing\CopyFilesWithSuffix.py datasets/coco/labels/train2017 datasets/coco_nvg/labels/train2017 _nvg_green

python .\OD-A-NVI_Scripts\src\Processing\GenerateNVG.py datasets/coco/images/val2017 datasets/coco_nvg/images/val2017 `
  --color green  `
  --noise-intensity 0 `
  --blur-amount 0 `
  --bloom-intensity 0 `
  --vignette-intensity 0
  
python .\OD-A-NVI_Scripts\src\Processing\CopyFilesWithSuffix.py datasets/coco/labels/val2017 datasets/coco_nvg/labels/val2017 _nvg_green

Fine Tune:
docker run --gpus all --rm `
  --shm-size=12g `
  -v ${PWD}\datasets:/datasets `
  -v ${PWD}\models:/models `
  -v ${PWD}\results:/ultralytics/runs/detect `
  ultralytics/ultralytics:latest `
  yolo detect train `
    model=/models/yolo11s.pt `
    data=/datasets/coco_nvg_clean.yaml `
    optimizer=SGD `
    lr0=0.0001 `
    lrf=0.01 `
    momentum=0.937 `
    warmup_epochs=5.0 `
    epochs=100 `
    batch=16 `
    imgsz=640 `
    patience=30 `
    workers=4 `
    project=/ultralytics/runs/detect `
    name=finetune_yolo11s_nvg_clean
	
Fine Tune with noisy images ontop:

docker run --gpus all --rm `
  --shm-size=12g `
  -v ${PWD}\datasets:/datasets `
  -v ${PWD}\models:/models `
  -v ${PWD}\results:/ultralytics/runs/detect `
  ultralytics/ultralytics:latest `
  yolo detect train `
    model=/models/yolo11s_clean.pt `
    data=/datasets/coco_nvg_noisy.yaml `
    optimizer=SGD `
    lr0=0.0005 `
    lrf=0.01 `
    momentum=0.937 `
    warmup_epochs=5.0 `
    epochs=100 `
    batch=16 `
    imgsz=640 `
    patience=30 `
    workers=4 `
    project=/ultralytics/runs/detect `
    name=finetune_yolo11s_nvg_clean-noisy
	
	
	
Performance testing:

docker run --gpus all --rm `
  --shm-size=12g `
  -v ${PWD}\datasets:/datasets `
  -v ${PWD}\models:/models `
  -v ${PWD}\results:/ultralytics/runs/detect `
  -v ${PWD}\OD-A-NVI_Scripts\src\Processing:/workspace `
  ultralytics/ultralytics:latest `
  python /workspace/yolo_val.py /models/yolo11s_clean-noisy.pt /datasets/coco_nvg_clean.yaml validate_clean-noisy_on_clean
	
docker run --gpus all --rm `
  --shm-size=12g `
  -v ${PWD}\datasets:/datasets `
  -v ${PWD}\models:/models `
  -v ${PWD}\results:/ultralytics/runs/detect `
  -v ${PWD}\OD-A-NVI_Scripts\src\Processing:/workspace `
  ultralytics/ultralytics:latest `
  python /workspace/yolo_val.py /models/yolo11s_clean-noisy.pt /datasets/coco_nvg_noisy.yaml validate_clean-noisy_on_noisy

  
Models:

yolo11n.pt - Nano (fastest, least accurate)
yolo11s.pt - Small
yolo11m.pt - Medium
yolo11l.pt - Large
yolo11x.pt - Extra Large (slowest, most accurate)


24 = Backpack
26 = Handbag
