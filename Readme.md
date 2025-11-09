Prepare Images:

cd "C:\Users\micha\Desktop\private\FH\MA\Tests\"
python .\GenerateCrops.py .\images_prepared .\images_cropped
Copy-Item -Path .\images_cropped\* -Destination .\images
python .\scripts\src\Preprocess.py .\images_cropped\ .\images   
python .\scripts\src\GenerateColorShift.py .\images\ .\images
python .\scripts\src\GenerateGrayscales.py .\images\ .\images

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


Validate models:

docker run --gpus all --rm `
  --shm-size=18g `
  -v ${PWD}\datasets:/datasets `
  -v ${PWD}\models:/models `
  -v ${PWD}\results:/ultralytics/runs/detect `
  ultralytics/ultralytics:latest `
  yolo detect val model=/models/yolo11x.pt data=coco.yaml
 
docker run --gpus all --rm `
  --shm-size=8g `
  -v ${PWD}\results:/ultralytics/runs/detect `
  -v ${PWD}\models:/models `
  -v ${PWD}\datasets:/datasets `
  -v ${PWD}\scripts\src:/workspace `
  ultralytics/ultralytics:latest `
  python /workspace/rtdetr_val_fixed.py


Apply NVG styling to images:

python .\scripts\src\GenerateNVG.py datasets/coco/images/val2017 datasets/coco_nvg_white/images/val2017 white
python .\scripts\src\CopyFilesWithSuffix.py datasets/coco/labels/val2017 datasets/coco_nvg_white/labels/val2017 _nvg_white

python .\scripts\src\GenerateNVG.py datasets/coco/images/val2017 datasets/coco_nvg_green/images/val2017 green
python .\scripts\src\CopyFilesWithSuffix.py datasets/coco/labels/val2017 datasets/coco_nvg_green/labels/val2017 _nvg_green

 
Test Convertet Images:

docker run --gpus all --rm `
  --shm-size=8g `
  -v ${PWD}\datasets:/datasets `
  -v ${PWD}\models:/models `
  -v ${PWD}\results:/ultralytics/runs/detect `
  ultralytics/ultralytics:latest `
  yolo detect val model=/models/yolo11x.pt data=/datasets/coco_nvg_green.yaml name=val_yolo_nvg
  
docker run --gpus all --rm `
  --shm-size=8g `
  -v ${PWD}\results:/ultralytics/runs/detect `
  -v ${PWD}\models:/models `
  -v ${PWD}\datasets:/datasets `
  -v ${PWD}\scripts\src:/workspace `
  ultralytics/ultralytics:latest `
  python /workspace/rtdetr_val_fixed.py /models/rtdetr-l.pt /datasets/coco_nvg_green.yaml
  
Create converted training and validation data remove noise, blur, bloom and vignette for better training results:

python .\scripts\src\GenerateNVG.py datasets/coco/images/train2017 datasets/coco_nvg/images/train2017 `
  --color white  `
  --noise-intensity 0 `
  --blur-amount 0 `
  --bloom-intensity 0 `
  --vignette-intensity 0

python .\scripts\src\CopyFilesWithSuffix.py datasets/coco/labels/train2017 datasets/coco_nvg/labels/train2017 _nvg_white

python .\scripts\src\GenerateNVG.py datasets/coco/images/val2017 datasets/coco_nvg/images/val2017 `
  --color white  `
  --noise-intensity 0 `
  --blur-amount 0 `
  --bloom-intensity 0 `
  --vignette-intensity 0
  
python .\scripts\src\CopyFilesWithSuffix.py datasets/coco/labels/val2017 datasets/coco_nvg/labels/val2017 _nvg_white

python .\scripts\src\GenerateNVG.py datasets/coco/images/train2017 datasets/coco_nvg/images/train2017 `
  --color green  `
  --noise-intensity 0 `
  --blur-amount 0 `
  --bloom-intensity 0 `
  --vignette-intensity 0
  
python .\scripts\src\CopyFilesWithSuffix.py datasets/coco/labels/train2017 datasets/coco_nvg/labels/train2017 _nvg_green

python .\scripts\src\GenerateNVG.py datasets/coco/images/val2017 datasets/coco_nvg/images/val2017 `
  --color green  `
  --noise-intensity 0 `
  --blur-amount 0 `
  --bloom-intensity 0 `
  --vignette-intensity 0
  
python .\scripts\src\CopyFilesWithSuffix.py datasets/coco/labels/val2017 datasets/coco_nvg/labels/val2017 _nvg_green

Fine Tune:
docker run --gpus all --rm `
  --shm-size=12g `
  -v ${PWD}\datasets:/datasets `
  -v ${PWD}\models:/models `
  -v ${PWD}\results:/ultralytics/runs/detect `
  ultralytics/ultralytics:latest `
  yolo detect train `
    model=/models/yolo11s.pt `
    data=/datasets/coco_nvg.yaml `
	lr0=0.0001 `
	lrf=0.001 `
	warmup_epochs=5.0 `
	epochs=100 `
    batch=16 `
    imgsz=640 `
    patience=30 `
	workers=4 `
    project=/ultralytics/runs/detect `
    name=finetune_yolo11s_nvg

  
Modesl:

yolo11n.pt - Nano (fastest, least accurate)
yolo11s.pt - Small
yolo11m.pt - Medium
yolo11l.pt - Large
yolo11x.pt - Extra Large (slowest, most accurate)


24 = Backpack
26 = Handbag
