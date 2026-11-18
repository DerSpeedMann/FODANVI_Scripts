# Data

Nothing under `data/` that is an image, a weight or a run is versioned. What
is versioned here is what makes a result traceable: the configs, the dataset
yamls, the measurement records, the result tables and the instructions. A
fresh clone runs nothing until the three downloads below are in place. The
original captures come in the same archive as the project data and are
needed only to prepare the datasets again.

## What has to be downloaded

| download | what | where it goes | instructions |
| --- | --- | --- | --- |
| Project data | everything this project produced, ready to use: the captured datasets as evaluated, the fine-tuned weights, the photometry frames and the images, in the full `data/` structure | extracted into `data/` | below |
| COCO 2017 | the source of every converted set | `data/datasets/coco/` | [`datasets/README.md`](datasets/README.md#coco) |
| Pre-trained weights | the five detectors, from their release URLs | `data/models/` | [`models/README.md`](models/README.md#pre-trained) |
| Captures (optional, same archive) | the images as the cameras wrote them, before cropping | anywhere outside `data/` | [below](#the-captures) |

With these three in place, every reported number recomputes here. Everything
else under `data/` is generated from them by the scripts the main
[Readme](../Readme.md) describes. No model has to be trained.

### The project data

One archive holding two folders: `data/`, the full `data/` structure, and
`captures/`, the originals (below). Extract `data/` into `data/` as it is;
nothing has to be moved or renamed afterward.

The archive is attached to the 1.0.0 release, split into two parts to stay
within the file size limit of a release asset:

    https://github.com/DerSpeedMann/FODANVI_Scripts/releases/download/1.0.0/FODANVI_data_1.0.0.zip.001
    https://github.com/DerSpeedMann/FODANVI_Scripts/releases/download/1.0.0/FODANVI_data_1.0.0.zip.002

With both parts in one folder, 7-Zip opens `.001` and reads the second part
by itself. Without 7-Zip, join the parts into a plain zip first:

    cat FODANVI_data_1.0.0.zip.0* > FODANVI_data_1.0.0.zip       # bash
    cmd /c copy /b FODANVI_data_1.0.0.zip.001+FODANVI_data_1.0.0.zip.002 FODANVI_data_1.0.0.zip   # Windows

What it adds:

| folder | what | details |
| --- | --- | --- |
| `datasets/real_nvg/` | the real captures the models are scored on, cropped, with their YOLO labels | [`datasets/README.md`](datasets/README.md) |
| `datasets/moving_car/` | the moving car frames, with their YOLO labels | [`datasets/README.md`](datasets/README.md) |
| `datasets/phone_ref/` | the phone reference of the static scene, with its YOLO labels | [`datasets/README.md`](datasets/README.md) |
| `models/yolo11s_*.pt` | the four fine-tuned weights | [`models/README.md`](models/README.md#fine-tuned) |
| `photometry/nikon/`, `photometry/phone/` | the raw frames of the illuminance, gain and grain measurements | [`photometry/README.md`](photometry/README.md) |
| `day2night/` | the green and white phosphor references the conversion configs are measured on | [`day2night/README.md`](day2night/README.md) |
| `images/` | images without labels, for prediction only (below) | |

The labelme annotations the labels were converted from, `groups.csv` and the
dataset yamls are versioned here and not part of the download.

`images/` holds:

    predict\     what the models see: the cropped frames through the device, and
                 the D500 frames without an intensified field as converted by
                 ConvertRaw.py
    vignetting\  phone photographs through the eyepieces, each beside its
                 cropped version, for what the black surround does to detection

A placed photometry set can be checked against its `MANIFEST.csv`; the
command is in [`photometry/nikon/README.md`](photometry/nikon/README.md).

### The captures

The `captures/` folder of the same archive: the images as the cameras wrote
them, uncropped, one folder per dataset or reference set. Nothing reads them
in place: they are needed only to prepare the datasets, the prediction frames
and the references again, with `ConvertRaw.py`, `GenerateCrops.py` and
`ConvertAnnotations.ps1` as in
[Preparing the captures](../Readme.md#preparing-the-captures), each given
the captures folder as its input.

| folder | what |
| --- | --- |
| `real_nvg/` | the recorder frames of the evaluation session, with the set description |
| `moving_car/<session>/{d500,recorder,phone}/` | the moving car frames per session and device, D500 as `.NEF` |
| `phone_ref/` | the phone reference of the static scene |
| `day2night/real_green/`, `day2night/real_white/` | the reference photographs through the green and white phosphor devices |

## What is generated here

| folder | what | written by |
| --- | --- | --- |
| `datasets/coco_nvg*/` | the converted COCO sets | `BuildDay2NightDatasets.py` |
| `datasets/real_nvg_*/`, `datasets/coco_nvg2_*_dn_*/` | the variants: tints and preprocessing | `BuildDatasets.ps1` |
| `datasets/resampled/` | resampled copies of the captures | `BuildResampledSets.py` |
| `datasets/*_gt.json` | box annotations for RF-DETR | `RunSweep.ps1` |
| `runs/`, `runs_resampled/` | one folder per validation or prediction run | `RunSweep.ps1`, `RunResampled.ps1` |
| `results/` | the result tables (versioned) and figures | `CompareRuns.py` and the table scripts |
| `results_resampled/` | the tables of the resampled runs (versioned) | `CompareRuns.py` |

## Versioned inputs

| path | what |
| --- | --- |
| `coco_labels.txt` | the 80 COCO category names in index order, for labelme and the conversion |
| `preprocess/*.json` | the `Preprocess.py` configs the generators in `sweep.json` name |
| `datasets/*.yaml` | every dataset definition, generated ones included |
| `day2night/nvg_config_*.json` | the conversion configs `GenerateNVGv2.py` reads |
| `models/weight_sizes.csv` | file and parameter size of every weight |

## TODO

- **No fetch script.** The three downloads are manual steps.
- **No manifest outside photometry.** The captured datasets, the references
  and the images have none, so a partial or altered copy looks identical to
  a complete one. `BuildManifest.py` does this for raw frames and would want
  extending to jpg and png.
- **Weights are pinned only by release tag and size**, not by a content
  hash; see [`models/README.md`](models/README.md).
