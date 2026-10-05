## Before anything: what has to be downloaded

Nothing under `data/` is versioned. The repository holds the scripts, the
configs, the measurement records and the instructions; every image, weight
and dataset is fetched and placed. A fresh clone therefore runs nothing
until the list below is satisfied, and the commands further down assume it
has been.

### COCO

The source dataset every synthetic conversion is built from. Ultralytics
publishes it in the layout these scripts expect, so the simplest route is to
let it download once and then move the tree into place:

    yolo settings datasets_dir="$(Resolve-Path .\data\datasets)"
    python -c "from ultralytics.utils.downloads import download; download('https://ultralytics.com/assets/coco2017labels.zip', dir='data/datasets')"

Or fetch it by hand from https://cocodataset.org/#download, taking
`train2017`, `val2017` and `annotations_trainval2017`, and arrange it as:

    data/datasets/coco/images/train2017/
    data/datasets/coco/images/val2017/
    data/datasets/coco/labels/train2017/
    data/datasets/coco/labels/val2017/
    data/datasets/coco/annotations/

About 20 GB. The whole `data/datasets/coco/` tree is gitignored, including
the annotation json and the split lists, since none of it is ours.

### The capture archive

One compressed download holding everything this project produced rather than
fetched: the real captures, the photometry frames, the day to night
references, and the two fine-tuned weight files. Unpack it over `data/`, so
each folder lands where the table below says.

    <url, not yet published>

With it and COCO in place, every reported number can be recomputed here.
Nothing else is needed; in particular no model has to be trained, because
the fine-tuned weights are in the archive.

### Everything else

| what | where it goes | how |
| --- | --- | --- |
| COCO 2017 | `data/datasets/coco/` | above |
| Pre-trained weights | `data/models/` | five files, about 2 GB. Links, sizes and a download block are in [`data/models/README.md`](data/models/README.md) |
| Fine-tuned weights | `data/models/` | two files, capture archive. Not published upstream; see the same file |
| Real captures | `data/datasets/real_nvg/` | capture archive; `real_nvg.yaml` expects `images/val` |
| Converted sets | `data/datasets/coco_nvg_*/` | generated, see below |
| Photometry frames | `data/photometry/nikon/` | capture archive; `MANIFEST.csv` lists every frame with its checksum |
| Day to night references | `data/day2night/` | capture archive |

A placed set can be checked before anything is run where a manifest exists.
`data/photometry/nikon/README.md` carries the command for the photometry
frames; the others have no manifest yet.

### TODO, downloading

The download story is only half written, and these are the gaps:

- **No single fetch script.** Each of the rows above is a separate manual
  step with its own source. One script taking a destination and pulling the
  lot would remove most of the setup, and is the obvious next thing.
- **No manifest outside photometry.** Only the photometry frames can be
  checked against recorded checksums. The real captures and the day to
  night references have none, so a partial or altered copy looks identical
  to a complete one. `BuildManifest.py` already does this for a folder of
  raw frames and would want extending to jpg and png.
- **The capture archive has no published location yet.** Everything else
  above is a working link; this one is still a placeholder, and until it is
  filled in the repository is only reproducible for whoever already holds
  the archive.
- **Weights are pinned only by release tag and size.** The Ultralytics
  files come from the `v8.3.0` tag, so the name cannot drift to a later
  build, and the recorded byte sizes catch a truncated download. Neither is
  a content hash, which is what would actually pin them.
- **`data/models/` starts empty**, so every docker command below fails on a
  fresh clone until the downloads in `data/models/README.md` have run.
- **`coco_nvg_green_clean/images/train2017` is short**, about 35 000 frames
  against the roughly 118 000 in each of its three siblings, so training on
  `coco_nvg_clean.yaml` or `coco_nvg_green.yaml` no longer reads the set the
  published fine-tuned weights came from. Regenerating it gives a complete
  set, not the original one. Validation splits are all complete at 5 000, so
  this does not affect reproducing any reported number.

## Prepare Images


cd "C:\Users\micha\Desktop\private\FH\MA\Tests\FODANVI_Scripts"
$S = ".\src\Processing"
python $S\GenerateCrops.py .\data\captured_images\ .\data\images_cropped\26_04_29
Copy-Item -Path .\data\images_cropped\* -Destination .\data\images
python $S\Preprocess.py .\data\images_cropped\ .\data\images   
python $S\GenerateColorShift.py .\data\images\ .\data\images
python $S\GenerateGrayscales.py .\data\images\ .\data\images

Check Images:

 docker run --gpus all --rm `
  -v ${PWD}\data\images:/data `
  -v ${PWD}\data\runs:/ultralytics/runs/detect `
  -v ${PWD}\data\models:/models `
  ultralytics/ultralytics:latest `
  yolo detect predict model=/models/rtdetr-l.pt source=/data save_txt=True
  
docker run --gpus all --rm `
  -v ${PWD}\data\images:/data `
  -v ${PWD}\data\runs:/ultralytics/runs/detect `
  -v ${PWD}\data\models:/models `
  ultralytics/ultralytics:latest `
  yolo detect predict model=/models/yolo11x.pt source=/data save_txt=True


docker run --gpus all --rm `
  -v ${PWD}\data\images:/data `
  -v ${PWD}\data\runs:/ultralytics/runs/detect `
  -v ${PWD}\data\models:/models `
  ultralytics/ultralytics:latest `
  yolo detect predict model=/models/yolo11s_clean-noisy.pt source=/data save_txt=True



Validate models:

For the models and datasets in `sweep.json`, use `.\RunSweep.ps1` instead of
these; see Running every validation below. What follows is the single run
form, for a pair the sweep does not cover, such as the COCO baseline below,
which validates against Ultralytics' own `coco.yaml` rather than anything in
`data/datasets/`.

(All three scripts print the per-class table and write a cleaned
logs/console.log and tables/*.csv into their run folder.)

docker run --gpus all --rm `
  --shm-size=18g `
  -v ${PWD}\data\datasets:/datasets `
  -v ${PWD}\data\models:/models `
  -v ${PWD}\data\runs:/ultralytics/runs/detect `
  -v ${PWD}\src\Processing:/workspace `
  ultralytics/ultralytics:latest `
  python /workspace/yolo_val.py /models/yolo11x.pt coco.yaml val_yolo11x

docker run --gpus all --rm `
  --shm-size=18g `
  -v ${PWD}\data\datasets:/datasets `
  -v ${PWD}\data\models:/models `
  -v ${PWD}\data\runs:/ultralytics/runs/detect `
  -v ${PWD}\src\Processing:/workspace `
  ultralytics/ultralytics:latest `
  python /workspace/yolo_val.py /models/yolo12x.pt /datasets/coco_nvg_clean.yaml val_yolo12x_clean
 
docker run --gpus all --rm `
  --shm-size=8g `
  -v ${PWD}\data\runs:/ultralytics/runs/detect `
  -v ${PWD}\data\models:/models `
  -v ${PWD}\data\datasets:/datasets `
  -v ${PWD}\src\Processing:/workspace `
  ultralytics/ultralytics:latest `
  python /workspace/rtdetr_val_fixed.py /models/rtdetr-x.pt /datasets/real_nvg.yaml

docker run --gpus all --rm `
  --shm-size=8g `
  -v ${PWD}\data\datasets:/datasets `
  -v ${PWD}\data\models:/models `
  -v ${PWD}\data\runs:/ultralytics/runs/detect `
  -v ${PWD}\src\Processing:/workspace `
  ultralytics/ultralytics:latest `
  bash -c "pip install --quiet rfdetr==1.2.0 transformers==4.53.3 pycocotools && python /workspace/rfdetr_val.py /models/rf-detr-large.pth /datasets/real_nvg.yaml val_rfdetr"


## Apply NVG styling to images

The old fine-tuning data was created with `GenerateNVGLegacy.py`, which
writes the `_nvg_*` suffix:

    foreach ($c in "green", "white") {
      foreach ($split in "train2017", "val2017") {

        python $S\GenerateNVGLegacy.py `
          data\datasets\coco\images\$split `
          data\datasets\coco_nvg_${c}_noisy\images\$split --color $c
        python $S\CopyFilesWithSuffix.py `
          data\datasets\coco\labels\$split `
          data\datasets\coco_nvg_${c}_noisy\labels\$split _nvg_$c

        python $S\GenerateNVGLegacy.py `
          data\datasets\coco\images\$split `
          data\datasets\coco_nvg_${c}_clean\images\$split --color $c `
          --noise-intensity 0 `
          --blur-amount 0 `
          --bloom-intensity 0 `
          --vignette-intensity 0
        python $S\CopyFilesWithSuffix.py `
          data\datasets\coco\labels\$split `
          data\datasets\coco_nvg_${c}_clean\labels\$split _nvg_$c
      }
    }

New ones should be created with `GenerateNVG.py`, which places grain in the
shadows where the device puts it and writes `_nvg2_*`:

    foreach ($c in "green", "white") {
      foreach ($split in "train2017", "val2017") {

        python $S\GenerateNVG.py `
          data\datasets\coco\images\$split `
          data\datasets\coco_nvg2_${c}_noisy\images\$split `
          --config data\day2night\nvg_config_$c.json
        python $S\CopyFilesWithSuffix.py `
          data\datasets\coco\labels\$split `
          data\datasets\coco_nvg2_${c}_noisy\labels\$split _nvg2_$c

        python $S\GenerateNVG.py `
          data\datasets\coco\images\$split `
          data\datasets\coco_nvg2_${c}_clean\images\$split `
          --config data\day2night\nvg_config_$c.json `
          --noise-intensity 0 `
          --blur-amount 0 `
          --bloom-intensity 0 `
          --vignette-intensity 0
        python $S\CopyFilesWithSuffix.py `
          data\datasets\coco\labels\$split `
          data\datasets\coco_nvg2_${c}_clean\labels\$split _nvg2_$c
      }
    }

The configs are measured from the real captures:

    python $S\AnalyzeNVG.py data\day2night\real_green\*.jpg data\day2night\real_green\*.png `
      --label real_green --config-color green `
      --config data\day2night\nvg_config_green.json

    python $S\AnalyzeNVG.py data\day2night\real_white\*.jpg data\day2night\real_white\*.png `
      --label real_white --config-color white `
      --config data\day2night\nvg_config_white.json

`GenerateNVGLegacy.py` is frozen and must not be edited. The flags above are
as recorded in `MA_Paper/supplementary/code/Readme.md`; the four-folder
layout is not, since the original calls wrote into a single `coco_nvg`.

New yaml files are needed to point at `coco_nvg2_*`; the existing ones name
the legacy folders.

### The yaml files combine them

Each config lists several folders under `train:` and `val:`, so a grouping
is a yaml rather than a copy of the images.

| config | covers |
| --- | --- |
| `coco_nvg_clean.yaml` | green clean + white clean |
| `coco_nvg_noisy.yaml` | green noisy + white noisy |
| `coco_nvg_green.yaml` | green clean + green noisy |
| `coco_nvg_white.yaml` | white clean + white noisy |
| `coco_nvg_green_clean.yaml` | that conversion alone |
| `coco_nvg_green_noisy.yaml` | that conversion alone |
| `coco_nvg_white_clean.yaml` | that conversion alone |
| `coco_nvg_white_noisy.yaml` | that conversion alone |
| `real_nvg.yaml` | the real captures, val only |
| `real_nvg_grayscale.yaml` | the real captures, grayscaled |
| `real_nvg_blue.yaml` | the real captures, green shifted to blue |

The four single-conversion configs exist so a model can be scored against
one conversion on its own; the combined four are what training uses.

They set `path: /datasets`, which is the mount target inside the container,
not a host path. The `real_nvg` configs use `path: real_nvg...` with splits
relative to it, a different style that resolves the same way.

## Creating the dataset variants

`sweep.json` at the repository root drives this and the sweep below. Its
`variants` block is a list of source datasets and the generator chains to
apply to each:

    "variants": [
      { "source": "real_nvg", "chains": [["grayscale"], ["blue"]] }
    ]

Every name in a chain comes from the `generators` block beside it, which
gives the script in `src/Processing`, the suffix that script appends, and
any extra arguments it takes after the input and output folders.

    .\BuildDatasets.ps1                        build whatever is missing
    .\BuildDatasets.ps1 -Only real_nvg_blue    one of them
    .\BuildDatasets.ps1 -Force                 rebuild even if present
    .\BuildDatasets.ps1 -WhatIf                list without building

A chain runs its generators in order, each over the previous one's output,
so `["grayscale", "blue"]` gives `real_nvg_grayscale_blue` with files
suffixed `_grayscale_blue`. The dataset is named for its source and those
suffixes and is never named in the config, so the folder and the filenames
cannot disagree. Intermediate steps go to a staging folder that is deleted
on success, so a chain that dies half way cannot leave something that looks
like a finished dataset.

Labels are copied by `CopyFilesWithSuffix.py` with the same suffix, because
Ultralytics pairs an image with its label by stem. The script checks that
pairing and fails rather than write a dataset that would score zero without
explaining why.

The yaml it writes lands in `data/datasets/`, and that is what puts the
variant into the sweep.

## Running every validation

    .\RunSweep.ps1

Every model in `sweep.json` against every dataset in it, one container
per pair. Seven models and seven datasets is 49 runs.

    .\RunSweep.ps1 -WhatIf                list the runs without making them
    .\RunSweep.ps1 -Datasets real_nvg*    only the real captures, 21 runs
    .\RunSweep.ps1 -Models yolo12x        one model
    .\RunSweep.ps1 -Force                 redo runs that already exist

Both halves of the matrix are named in `sweep.json`, under `models` and
`datasets`. Nothing is discovered, because `data/datasets/` also holds
groupings kept for training: `coco_nvg_clean`, `coco_nvg_green`,
`coco_nvg_noisy` and `coco_nvg_white` each have a val split that is the
union of two single-conversion configs beside them. Sweeping the folder
would score every converted image three times, once alone and once in each
grouping it belongs to, and report the three as separate results, 60000
images per model where 20000 are distinct.

Naming them has a cost: building a variant is no longer enough to get it
scored, it has to be added to `datasets` too. So the script lists any config
in the folder that it was not told about, rather than let a set that was
built on purpose go quietly unmeasured. A name in the list with no file
behind it stops the sweep before the first container.

Results land in `data/runs/val_<model>_<dataset>/`, named for the pair:

| in each run folder | what |
| --- | --- |
| `logs/console.log` | the whole run, progress redraws collapsed |
| `tables/per_class_metrics.csv` | one row per class, plus an `all` row |
| `tables/supercategory_metrics.csv` | the same averaged per COCO supercategory |
| `predictions.json` | every detection, so metrics can be recomputed |
| `confusion_matrix*.png`, `Box*_curve.png` | the usual Ultralytics plots |
| `val_batch*_{labels,pred}.jpg` | sample predictions against truth |

The two CSVs are the results. Nothing has to be read back out of the
terminal.

A run whose folder already exists is skipped, so an interrupted sweep
resumes by being started again. A missing weight or config fails before the
first container rather than an hour in. `data/runs/` is not versioned.

Budget hours, not minutes: four of the seven configs are 5000 image COCO
validation splits, and RF-DETR installs itself into the container on every
run. `-Datasets real_nvg*` is 21 runs over 66 images each and checks
the whole chain first.

### Box annotations for RF-DETR

Nothing to run: `RunSweep.ps1` builds these itself when they are missing.
This is what it is doing when it prints `build box annotations for ...`.

The converted COCO sets carry segmentation polygons rather than boxes,
`cls x1 y1 x2 y2 ...`, because COCO ships masks and the conversion kept
them. Ultralytics derives the enclosing box itself, so YOLO and RT-DETR
score those sets normally. `rfdetr_val.py` has to be handed one, and it
refuses to build its own:

    python src\Processing\GenerateBoxAnnotations.py data\datasets\coco_nvg_green_clean.yaml

That writes `<config>_gt.json` beside the config. The reason the sweep runs
it on the host rather than letting the validator do it in the container per run.

## Comparing the runs

    python src\Processing\CompareRuns.py

Reads the `all` row of every finished run and writes into `data/results/`:

    comparison.csv          one row per run
    comparison.tex          the same as a booktabs longtable
    matrix_map50_95.tex     a model by dataset grid, `--metric` to change it

It prints how many of the expected runs it found and names any that have no
tables yet, and a cell with no run is a dash rather than a blank, so a
partial sweep is visible rather than quietly short.

Fine Tune:
docker run --gpus all --rm `
  --shm-size=12g `
  -v ${PWD}\data\datasets:/datasets `
  -v ${PWD}\data\models:/models `
  -v ${PWD}\data\runs:/ultralytics/runs/detect `
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
  -v ${PWD}\data\datasets:/datasets `
  -v ${PWD}\data\models:/models `
  -v ${PWD}\data\runs:/ultralytics/runs/detect `
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

Covered by `.\RunSweep.ps1`, which runs every model in `sweep.json` against
every config in `data/datasets/` and names each result for the pair. See
Running every validation.

Models:

yolo11n.pt - Nano (fastest, least accurate)
yolo11s.pt - Small
yolo11m.pt - Medium
yolo11l.pt - Large
yolo11x.pt - Extra Large (slowest, most accurate)


24 = Backpack
26 = Handbag
