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
python $S\Preprocess.py .\data\images_cropped\ .\data\images --config .\data\preprocess\eq_cl_c3_t8_dn_h10_w7.json --suffix _preprocessed --quality 95
python $S\GenerateColorShift.py .\data\images\ .\data\images
python $S\GenerateGrayscales.py .\data\images\ .\data\images

Check Images:

 docker run --gpus all --rm `
  -v ${PWD}\data\images\predict:/data `
  -v ${PWD}\data\runs:/ultralytics/runs/detect `
  -v ${PWD}\data\models:/models `
  ultralytics/ultralytics:8.4.41 `
  yolo detect predict model=/models/rtdetr-x.pt source=/data save_txt=True
  
docker run --gpus all --rm `
  -v ${PWD}\data\images\predict:/data `
  -v ${PWD}\data\runs:/ultralytics/runs/detect `
  -v ${PWD}\data\models:/models `
  ultralytics/ultralytics:8.4.41 `
  yolo detect predict model=/models/yolo11x.pt source=/data save_txt=True


docker run --gpus all --rm `
  -v ${PWD}\data\images\predict:/data `
  -v ${PWD}\data\runs:/ultralytics/runs/detect `
  -v ${PWD}\data\models:/models `
  ultralytics/ultralytics:8.4.41 `
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
  ultralytics/ultralytics:8.4.41 `
  python /workspace/yolo_val.py /models/yolo11x.pt coco.yaml val_yolo11x

docker run --gpus all --rm `
  --shm-size=18g `
  -v ${PWD}\data\datasets:/datasets `
  -v ${PWD}\data\models:/models `
  -v ${PWD}\data\runs:/ultralytics/runs/detect `
  -v ${PWD}\src\Processing:/workspace `
  ultralytics/ultralytics:8.4.41 `
  python /workspace/yolo_val.py /models/yolo12x.pt /datasets/coco_nvg_clean.yaml val_yolo12x_clean
 
docker run --gpus all --rm `
  --shm-size=8g `
  -v ${PWD}\data\runs:/ultralytics/runs/detect `
  -v ${PWD}\data\models:/models `
  -v ${PWD}\data\datasets:/datasets `
  -v ${PWD}\src\Processing:/workspace `
  ultralytics/ultralytics:8.4.41 `
  python /workspace/rtdetr_val.py /models/rtdetr-x.pt /datasets/real_nvg.yaml

docker run --gpus all --rm `
  --shm-size=8g `
  -v ${PWD}\data\datasets:/datasets `
  -v ${PWD}\data\models:/models `
  -v ${PWD}\data\runs:/ultralytics/runs/detect `
  -v ${PWD}\src\Processing:/workspace `
  ultralytics/ultralytics:8.4.41 `
  bash -c "pip install --quiet rfdetr==1.2.0 transformers==4.53.3 pycocotools && python /workspace/rfdetr_val.py /models/rf-detr-large.pth /datasets/real_nvg.yaml val_rfdetr"


## Apply NVG styling to images

All ten converted COCO sets are built by one script in the repository
root, with COCO in place:

    python BuildDay2NightDatasets.py                       all ten, both splits
    python BuildDay2NightDatasets.py --splits val2017      val only, all the sweep needs
    python BuildDay2NightDatasets.py --only "coco_nvg2_*"  the v2 training four

| sets | generator | values | used for |
| --- | --- | --- | --- |
| `coco_nvg_{green,white}_{noisy,clean}` | `GenerateNVG.py` | hand-tuned, hardcoded in the script | v1 fine-tuning, validation |
| `coco_nvg2_green_{noisy,clean}` | `GenerateNVGv2.py` | `data/day2night/nvg_config_selected_green.json` (five green references) | v2 fine-tuning, validation |
| `coco_nvg2_white_{noisy,clean}` | `GenerateNVGv2.py` | `data/day2night/nvg_config_selected_white.json` (five white references) | v2 fine-tuning, validation |
| `coco_nvg_captures_green_{noisy,clean}` | `GenerateNVGv2.py` | `data/day2night/nvg_config_setup_green.json` (66 evaluation captures) | validation only |

The v2 fine-tuning trains on the references only, so that no statistic of the
evaluation captures reaches its training data; `coco_nvg2_clean.yaml` and
`coco_nvg2_noisy.yaml` pair green with white for its two stages. The captures
set is matched to the camera path the models are scored on and never trained
on, so it needs only val2017.

The clean variant of each disables grain, blur, bloom and vignette. The
script only writes images and labels; every yaml under `data/datasets` is
versioned and already points at those folders. It resumes an interrupted
run, and `--force` rebuilds a split that is already complete.

`GenerateNVG.py` is frozen and must not be edited. The v1 flags
are as recorded in `MA_Paper/supplementary/code/Readme.md`; the four-folder
layout is not, since the original calls wrote into a single `coco_nvg`.
Rebuilding the v1 sets gives complete sets, not necessarily the original
ones: the green noisy val2017 on disk came from an earlier revision of the
script.

How the configs are measured, and the commands that write them, are in
[`data/day2night/README.md`](data/day2night/README.md).

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
| `real_nvg_white.yaml` | the real captures, green shifted to the white phosphor tint |

The four single-conversion configs exist so a model can be scored against
one conversion on its own; the combined four are what training uses.

They set `path: /datasets`, which is the mount target inside the container,
not a host path. The `real_nvg` configs use `path: real_nvg...` with splits
relative to it, a different style that resolves the same way.

## Converting the annotations

The real captures (`real_nvg`) and the frames of the moving car
(`moving_car`) were annotated in labelme as polygons; their `source/` folders
hold the frames with the labelme `.json` beside them. `ConvertAnnotations.ps1`
turns a source folder into a YOLO dataset with every frame in `images/val`
and `labels/val`, through labelme2yolo, which reduces each polygon to its
enclosing box:

    .\ConvertAnnotations.ps1 -Source .\data\datasets\real_nvg\source `
      -Output .\data\datasets\real_nvg
    .\ConvertAnnotations.ps1 -Source .\data\datasets\moving_car\source `
      -Output .\data\datasets\moving_car -Background

It needs labelme2yolo 0.3.3 on the PATH and stops before touching anything
if it is missing:

    pip install labelme2yolo==0.3.3

What it does beyond calling the converter:

- **Category indices.** The names are read from `data/coco_labels.txt` in
  its order (`-Labels` for another list), so each label gets its COCO index.
- **One folder at a time.** labelme2yolo empties its output folder on every
  run, so every folder under `-Source` holding images or `.json` is converted
  into a temporary folder and merged into the dataset from there.
- **`groups.csv`.** The folder each image came from, relative to `-Source`,
  is written beside the dataset, so one run can be scored per group. For
  `moving_car` that is `<session>/<device>`, which `MovingCarTable.py`
  reads.
- **`-Background`** keeps frames without a label as background images with
  an empty label file. `moving_car` needs it; `real_nvg` has a label on
  every frame.
- **The yaml.** labelme2yolo writes an absolute host path into its
  `dataset.yaml`, which does not exist in the container. The script writes
  `<dataset>.yaml` beside the dataset folder instead, with `path` set to the
  folder name, where `RunSweep.ps1` looks.

The converted frames are added to `images/val` and `labels/val`: frames
already in the set stay, and one converted again under the same name is
replaced, as is its row in `groups.csv`. `source/` is left alone.

The images have to lie beside their `.json`: the annotations reference them
by file name and carry no image data. labelme2yolo skips an annotation whose
image is missing and still exits 0, so the script counts the images that come
out of each folder against its `.json` files and stops with the folder if any
are missing, as it does when the converter itself fails. Nothing is added
until every folder has passed, so a failed run leaves the set as it was.

`real_nvg/source/` holds only the `.json` files; their images are in
`images/val`, byte for byte. To convert it again, copy the images back beside the `.json`
under their original names, without the suffix labelme2yolo appends
(`capture_..._cropped_a4cf5093.jpg` becomes `capture_..._cropped.jpg`).

## Creating the dataset variants

`sweep.json` at the repository root drives this and the sweep below. Its
`variants` block is a list of source datasets and the generator chains to
apply to each:

    "variants": [
      { "source": "real_nvg", "chains": [["grayscale"], ["white"]] }
    ]

Every name in a chain comes from the `generators` block beside it, which
gives the script in `src/Processing`, the suffix that script appends, and
any extra arguments it takes after the input and output folders.

    .\BuildDatasets.ps1                        build whatever is missing
    .\BuildDatasets.ps1 -Only real_nvg_white   one of them
    .\BuildDatasets.ps1 -Force                 rebuild even if present
    .\BuildDatasets.ps1 -WhatIf                list without building

A chain runs its generators in order, each over the previous one's output,
so `["grayscale", "white"]` gives `real_nvg_grayscale_white` with files
suffixed `_grayscale_white`. The dataset is named for its source and those
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

An entry may name its `splits`; the default, `train` and `val`, is the layout
of the captures. A converted COCO set is laid out as `train2017` and
`val2017` and is given `["val2017"]` alone, since the sweep scores the val
split and converting the 118k training images would take hours for nothing.
Its yaml then points `train` at the val split, because the validator wants
the key. The denoised measured-conversion sets are built that way, from the
grain-only sets, which are the clean conversion with the grain left on
(blur, bloom and vignette off), so they differ from the clean set in the
grain alone:

    { "source": "coco_nvg2_green_grain", "splits": ["val2017"], "chains": [["dn_h80_w3"]] }

    python BuildDay2NightDatasets.py --only "coco_nvg2_*_grain" --splits val2017
    .\BuildDatasets.ps1 -Only "coco_nvg2_*_grain_dn_h80_w3"
    .\RunSweep.ps1 -Datasets "coco_nvg2_*_grain*"

They put the same denoising as the captures' `dn_h80_w3` on the synthetic
grain, so the `denoise_synthetic` plot can set clean, grain only and denoised
grain only beside the captures before and after it. The
`coco_nvg2_*_noisy_dn_h80_w3` sets, denoised from the full noisy conversion,
still carry blur, bloom and vignette and so do not compare with the clean
set; they stay listed only because their runs exist. `dn_h80_w3` is the denoising
setting with the highest mean mAP50-95 over all eight models on the green
captures and their white tint (0.408, against 0.351 unprocessed).

The captures reach the model scaled down to 640 pixels, while the synthetic
sets already are 640 pixels, so `dn_h80_w3` covers more of the image on the
synthetic sets. The `rs_640_lin` generators move the scaling in front of the
filter: `real_nvg*_rs_640_lin` is the captures resized as the Ultralytics
8.4.41 loader resizes them (linear), the reference at that scale, and
`real_nvg*_rs_640_lin_dn_h80_w3` denoises after the resize. The Ultralytics
validators do not scale them again; RF-DETR still scales to its 560 pixels, as
for every other set. The resize is linear because area averaging would smooth
the grain on top, so the reference would no longer be the model's input. The
`denoise_scale` plot sets the denoising at 640 against the denoising at full
size.

    .\BuildDatasets.ps1 -Only "real_nvg*rs_640_lin*"
    .\RunSweep.ps1 -Datasets "real_nvg*rs_640_lin*"

## Running every validation

    .\RunSweep.ps1

Every model in `sweep.json` against every dataset in it, one container
per pair. Seven models and seven datasets is 49 runs. For images without
labels, `-Predict` runs the same models over an image folder instead; see
Predicting on images with no labels.

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

## Predicting on images with no labels

The sweep scores against ground truth. This is the other question: point a
model at a capture nothing has labelled and see whether the subject is
detected at all.

One script per model family, named for the validator beside it:

| family | script | notes |
| --- | --- | --- |
| YOLO | `yolo_predict.py` | |
| RT-DETR | `rtdetr_predict.py` | carries the same `scale_boxes` patch as its validator |
| RF-DETR | `rfdetr_predict.py` | needs the pip install |

`data\images\` holds the images in these folders, none of them versioned:

    raw\         what the cameras wrote: D500 .NEF files and recorder captures,
                 each also kept under Captures\
    predict\     what the models see: the cropped frames through the NVD, and
                 the D500 frames without an intensified field as converted by
                 ConvertRaw.py
    vignetting\  phone photographs through the eyepieces, each beside its
                 cropped version, for what the black surround does to detection

### Every model at once

`RunSweep.ps1` runs every model in `sweep.json` over a folder under
`data\images\` with `-Predict`, one container and one run per model, through
the predict script beside each validator:

    .\RunSweep.ps1 -Predict vignetting
    .\RunSweep.ps1 -Predict predict -Models yolo12x    one model
    .\RunSweep.ps1 -Predict vignetting -Conf 0.05      lower threshold
    .\RunSweep.ps1 -Predict vignetting -WhatIf         list the runs

Runs are named `predict_<model>_<folder>`, so `data\runs\
predict_yolo12x_vignetting` is yolo12x on `data\images\vignetting\`. Existing
runs are skipped and `-Force` redoes them, as for validation. The folder is
read flat by the YOLO and RT-DETR scripts but recursively by RF-DETR, so keep
the images of one run in one folder without subfolders.

### The vignetting images

Ten phone photographs taken by hand through the eyepieces, the nine of
2025-10-26 (eight through the green device, `IMG_20251026_204827` through the
white one) and `IMG_20251029_201745`, each kept whole and cropped to the
intensified field beside it. The crops are made with the same script as every
capture, which skips anything already carrying `_cropped`, so it can be run
on the folder itself:

    python src\Processing\GenerateCrops.py data\images\vignetting data\images\vignetting

Then every model over both versions in one run each:

    .\RunSweep.ps1 -Predict vignetting

### One model at a time

The commands below mount `predict\` at `/data`. Each writes annotated images, a per-image `.txt` of the detections,
and `logs/console.log`, into `data\runs\<name>\`.

    docker run --gpus all --rm `
      --shm-size=8g `
      -v ${PWD}\data\images\predict:/data `
      -v ${PWD}\data\models:/models `
      -v ${PWD}\data\datasets:/datasets `
      -v ${PWD}\data\runs:/ultralytics/runs/detect `
      -v ${PWD}\src\Processing:/workspace `
      ultralytics/ultralytics:8.4.41 `
      python /workspace/yolo_predict.py /models/yolo12x.pt /data predict_yolo12x 0.25

    docker run --gpus all --rm `
      --shm-size=8g `
      -v ${PWD}\data\images\predict:/data `
      -v ${PWD}\data\models:/models `
      -v ${PWD}\data\datasets:/datasets `
      -v ${PWD}\data\runs:/ultralytics/runs/detect `
      -v ${PWD}\src\Processing:/workspace `
      ultralytics/ultralytics:8.4.41 `
      python /workspace/rtdetr_predict.py /models/rtdetr-x.pt /data predict_rtdetrx 0.25

    docker run --gpus all --rm `
      --shm-size=8g `
      -v ${PWD}\data\images\predict:/data `
      -v ${PWD}\data\models:/models `
      -v ${PWD}\data\datasets:/datasets `
      -v ${PWD}\data\runs:/ultralytics/runs/detect `
      -v ${PWD}\src\Processing:/workspace `
      ultralytics/ultralytics:8.4.41 `
      bash -c "pip install --quiet --root-user-action=ignore rfdetr==1.2.0 transformers==4.53.3 pycocotools && python /workspace/rfdetr_predict.py /models/rf-detr-large.pth /data predict_rfdetrl 0.25"

The last argument is the confidence threshold. 0.25 is a reasonable
threshold for looking at a picture, but the sweep validates at 0.001 to
maximise recall, so a subject can be found there and invisible here. Before
concluding a model sees nothing, try 0.05.

Nothing is scored, because there is nothing to score against. The output is
what was detected and where.

Two things to keep in mind when reading the result. The classes are COCO's,
so a subject that is not one of the 80 can only be reported as whatever it
most resembles, and an RC car has to come back as `car` or `truck` or not at
all. And `yolo detect predict` further up does the YOLO detection too, but
keeps no log in the run folder, which is why `yolo_predict.py` exists.

## Comparing the runs

    python src\Processing\CompareRuns.py

Reads the `all` row of every run under `data\runs\` and writes into
`data\results\`:

    comparison.csv          one row per run
    matrix_map50_95.csv     dataset rows, model columns

plus every figure the `plots` block of `sweep.json` names (below), so this
one command redraws all of them after a sweep. Without a `plots` block it
draws one `bars_map50_95.png`, grouped bars with one group per dataset.

`--metric` switches all of them between `map50_95`, `map50`, `precision`
and `recall`. `--no-plots` writes the tables only.

What a run was is read from the run itself, from the `Model` and `Data`
lines the validators print into `logs/console.log`, so nothing has to be
told which folders to look at and a run stays readable after the config
that produced it has moved on. It prints how many runs it found, names any
with no tables yet, and warns when a weight's size is neither measurable
nor recorded.

Every run is scored on the classes in the `classes` list of `sweep.json`
(backpack, bottle, laptop, mouse: the four the real captures contain), as
the mean of their rows in the run's per-class table. A COCO run's `all` row
averages all eighty, so without this its baseline measures a different
category mix than the real set. No inference is repeated; `--all-classes`
reports the `all` row instead.

YOLO and RT-DETR are scored by Ultralytics, RF-DETR by pycocotools in
`rfdetr_val.py`. `CrossCheckScoring.py` rescores a run Ultralytics has
already scored through `rfdetr_val.py`'s own functions, from its saved
`predictions.json`, and writes both side by side to
`data\results\scoring_crosscheck.csv`:

    python src\Processing\CrossCheckScoring.py

For yolo12x on `coco` and `real_nvg`, mAP50 and mAP50-95 agree to 0.0015
over the four classes and to 0.006 for any one class, so mAP can share a
table across the two paths. Precision and recall cannot: Ultralytics reads
both at one confidence for all classes, where mean F1 peaks, and
`rfdetr_val.py` at each class's own F1 peak. On COCO that moves them by
0.01 to 0.02; on the 66 real captures precision goes from 0.33 to 0.83,
because a class with few instances can reach its own F1 peak on its few
most confident hits (mouse: 4 of 17 found, none wrong, precision 1.0).

The csv keeps every run, but the figures show only what `sweep.json` lists:
a run is drawn when its dataset is in the sweep's `datasets` and its weight
belongs to one of the sweep's `models`. This holds for the default figures
and for every `PlotRuns.py` selection below; `--all` draws every run.

Two size columns, not one. `file_mb` is what the checkpoint costs to fetch,
`weights_mb` the model parameters inside it. They differ where a file is a
training checkpoint: `rf-detr-large.pth` is 1571 MB of which 542 MB is
parameters, and the fine-tuned `yolo11s` weights are 38 MB against 18 MB,
the same architecture as the 19 MB they came from. See
`data\models\README.md`.

### Drawing a subset

Everything at once is the record rather than the picture worth looking at,
so the figures worth keeping are named in the `plots` block of `sweep.json`,
each with a prefix, model and dataset globs and the metrics to draw:

    "plots": [
      { "prefix": "",         "models": "*",        "datasets": "*", "metrics": ["map50_95"] },
      { "prefix": "finetune", "models": "yolo11s*", "datasets": "*", "metrics": ["map50_95"] },
      { "prefix": "raw",      "models": "yolo12x,rtdetr-x,rf-detr-large", ... }
    ]

`CompareRuns.py` draws all of them, and so does `PlotRuns.py` on its own,
which redraws from the csv without collecting the runs again:

    python src\Processing\PlotRuns.py                                   every configured plot
    python src\Processing\PlotRuns.py --models "yolo11s*" --prefix test   one selection, not kept in the config

Adding a metric to `metrics` or a new entry to the block is how a figure
becomes part of the set. The `finetune` entry is one architecture trained
three ways, so the spread is the effect of fine-tuning. The `raw` entry is
the pre-trained models on their own, so
the spread is the effect of the model. Mixed together they are hard to read
apart, because the three `yolo11s` weights are the same architecture and sit
at the same parameter size.

`models` and `datasets`, in the config or as `--models` and `--datasets`,
take comma separated globs matched against the csv, the prefix keeps a
selection from overwriting the default figures, and the metrics are the same
four as above. Models and datasets are drawn in the order of the globs that
pick them, so an entry that names them one by one sets the order.

An entry can also carry:

    "kind": "lines"        one line per model across the datasets, written as
                           <prefix>_lines_<metric>.png; the default is "bars",
                           <prefix>_bars_<metric>.png
    "group": "model"       bars only: one group per model, one bar per dataset
    "colors": [...]        one color per model, in the order of "models"
    "styles": ["-", "--"]  lines only: one dash pattern per model, in the same
                           order; a dashed line gets hollow markers
    "columns": [           lines only: each point is a label and dataset globs,
      {"label": "COCO", "datasets": "coco"},       and a model's point is its
      {"label": "green best preprocessing",        highest figure over the sets
       "datasets": "real_nvg_dn_*,real_nvg_cl_*"}  matched; which set that was
    ]                                              is printed

A label in `columns` must not contain a comma, since the order is passed on
as a comma separated list. `preprocess_best` uses `columns` to put each
model's best preprocessing beside its unprocessed figure, where the best
configuration differs from model to model.

## Resampled sets

How far a score on a set as small as the 66 captures moves when the images
are drawn differently is measured on resampled copies of the set:

    python src\Processing\BuildResampledSets.py --runs 100
    .\RunResampled.ps1
    python src\Processing\CompareRuns.py --runs data/runs_resampled --out data/results_resampled --no-plots

`BuildResampledSets.py` builds `--runs` sets of the same size as the source
(`--source`, default `real_nvg`). `--unique-pct` of each set (default 66.7,
44 of 66) is drawn without replacement, the rest are duplicates drawn from
those; a duplicate is copied under its own name with its label, so the
validator scores it as one more image. Set `r` is drawn with seed
`--seed + r`, and `manifest.json` lists the files of every set, so any set
can be rebuilt. `--reuse <source>` draws nothing but rebuilds the manifest's
sets of that source from `--source`, image for image, so a preprocessed variant
holds the same captures as each set of the captures as captured and two figures
can be compared set by set (the variant's files are matched by the source's
file name, which every preprocessing step keeps as the start of its own):

    python src\Processing\BuildResampledSets.py --source real_nvg_dn_h20_w5 --reuse real_nvg --runs 100
    .\RunResampled.ps1 -Sets "real_nvg_dn_h20_w5_rs_*"

The sets go to `data\datasets\resampled\`, each as
`<source>_rs_u<pct>_r<NNN>` with its own yaml, outside the dataset folder
proper so `RunSweep.ps1` neither sweeps nor reports them. `--out` has to stay
inside `data\datasets`, since the yaml names the container path. Existing
sets are skipped; `--force` rebuilds them.

`RunResampled.ps1` runs one model (`-Model`, default `yolo12x`, YOLO
validator only) against every set (`-Sets`, a glob) in a single container,
since starting one per set would cost more than the validation. Each set
still gets its own `yolo_val.py` process and run folder,
`val_<model>_<set>`, written to `data\runs_resampled\` rather than
`data\runs\`, so the resampled runs stay out of `comparison.csv` and the
sweep figures. Existing runs are skipped, so an interrupted batch resumes;
`-WhatIf` lists what would run. `CompareRuns.py` pointed at that folder
collects them, scored on the `classes` of `sweep.json` like every other run.

    python src\Processing\ResampledStats.py --variant real_nvg_dn_h20_w5

`ResampledStats.py` summarizes the resampled runs of one model (`--model`,
default `yolo12x`) per category from each run's `per_class_metrics.csv`:
`data\results\resampled_variability.csv` for how far a single score on
`--source` moves (standard deviation, 1.96 of them, range, how many sets lie
within that band, and the standard deviation over the first 25, 50 and 75
sets), and with `--variant` `data\results\resampled_paired_<variant>.csv` for
how far the difference between the variant and the source moves when both are
scored on the same images, set by set.

## Fine-tuning

    .\RunTrain.ps1 -Stages nvg2_clean,nvg2_clean-noisy   the measured chain
    .\RunTrain.ps1 -Stages nvg2_* -WhatIf                print the commands
    .\RunTrain.ps1 -Stages nvg2_clean -Set lr0=0.0002    override any train argument

`train.json` holds the device settings (image, GPU, shared memory, batch,
workers), the hyperparameters every stage shares and one entry per stage:
starting weights, training set, own arguments, `stop_after` and the file in
`data/models` its `best.pt` is exported to. A stage keeps `epochs=100`, so it
runs on the learning-rate schedule of a 100 epoch run, and is stopped once
`results.csv` holds `stop_after` epochs, as the hand-tuned runs ended at 13
and 19. A stage whose run folder exists is skipped; `-Force` redoes it and
overwrites its export. The hand-tuned stages are in the config for the
record and export over the weights the results use, so they never run
without `-Force`. The manual commands they were run with:

Fine Tune:
docker run --gpus all --rm `
  --shm-size=12g `
  -v ${PWD}\data\datasets:/datasets `
  -v ${PWD}\data\models:/models `
  -v ${PWD}\data\runs:/ultralytics/runs/detect `
  ultralytics/ultralytics:8.3.221 `
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

Notes on these settings:

- The first attempts failed during validation in epoch 1, most likely from
  running out of resources. Dropping `workers` from 8 to 2 fixed it. After
  giving WSL more resources it ran with `workers=4`. The resources are set in
  `notepad "$env:USERPROFILE\.wslconfig"`:

      [wsl2]
      memory=28GB
      swap=8GB
      processors=12

  and take effect after `wsl --shutdown`.
- Standby was turned off so the laptop does not sleep during long runs:

      powercfg /change standby-timeout-ac 0
      powercfg /change monitor-timeout-ac 0

- `optimizer=SGD` has to be set. The default `optimizer=auto` ignores `lr0`
  and `momentum` and picks its own, which logs
  `optimizer: 'optimizer=auto' found, ignoring 'lr0=0.0001' and 'momentum=0.937'`
  and trains at `SGD(lr=0.01, momentum=0.9)`. That is far too high for this
  domain shift.
- A run with `lr0=0.0001` and `epochs=50` diverged. Losses rose every epoch
  (box 1.292 to 1.437, class 1.700 to 2.114, DFL 1.282 to 1.400 over epochs
  1 to 4), and by epoch 4 it was at P 0.0946, R 0.00114, mAP50 0.0479,
  mAP50-95 0.0352.
- The settings above keep `lr0` at 0.0001, double the epochs to 100 and use
  5 warmup epochs. That run showed a similar drop around epoch 5 to 6 but
  recovered and kept improving slowly from there. They are the settings
  stored in `train_args` of `yolo11s_clean.pt`.
- Both stages ran on Ultralytics 8.3.221, the version both checkpoints
  record, not the 8.4.41 image the validation runs use.
	
Fine Tune with noisy images ontop:

docker run --gpus all --rm `
  --shm-size=12g `
  -v ${PWD}\data\datasets:/datasets `
  -v ${PWD}\data\models:/models `
  -v ${PWD}\data\runs:/ultralytics/runs/detect `
  ultralytics/ultralytics:8.3.221 `
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
