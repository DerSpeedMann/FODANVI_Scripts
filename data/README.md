# Data

Nothing under `data/` that is an image, a weight or a run is versioned. What
is versioned here is what makes a result traceable: the configs, the dataset
yamls, the measurement records, the result tables and the instructions. A
fresh clone runs nothing until the three downloads below are in place.

## What has to be downloaded

| download | what | where it goes | instructions |
| --- | --- | --- | --- |
| Project data | everything this project produced: the captured datasets, the fine-tuned weights, the photometry frames and the images, in the full `data/` structure | extracted into `data/` | below |
| COCO 2017 | the source of every converted set | `data/datasets/coco/` | [`datasets/README.md`](datasets/README.md#coco) |
| Pre-trained weights | the five detectors, from their release URLs | `data/models/` | [`models/README.md`](models/README.md#pre-trained) |

With these three in place, every reported number recomputes here. Everything
else under `data/` is generated from them by the scripts the main
[Readme](../Readme.md) describes. No model has to be trained.

### The project data

One download holding the full `data/` structure. Extract it into `data/`
as it is; nothing has to be moved or renamed afterward.

    <url, not yet published>

What it adds:

| folder | what | details |
| --- | --- | --- |
| `datasets/real_nvg/` | the real captures the models are scored on, with their labelme annotations | [`datasets/README.md`](datasets/README.md) |
| `datasets/moving_car/` | the moving car frames, with `groups.csv` | [`datasets/README.md`](datasets/README.md) |
| `datasets/phone_ref/` | the phone reference of the static scene | [`datasets/README.md`](datasets/README.md) |
| `models/yolo11s_*.pt` | the four fine-tuned weights | [`models/README.md`](models/README.md#fine-tuned) |
| `photometry/nikon/`, `photometry/phone/` | the raw frames of the illuminance, gain and grain measurements | [`photometry/README.md`](photometry/README.md) |
| `day2night/` | the green and white phosphor references the conversion configs are measured on | [`day2night/README.md`](day2night/README.md) |
| `images/` | images without labels, for prediction only (below) | |

`images/` holds:

    raw\         what the cameras wrote: D500 .NEF files and recorder captures
    predict\     what the models see: the cropped frames through the device, and
                 the D500 frames without an intensified field as converted by
                 ConvertRaw.py
    vignetting\  phone photographs through the eyepieces, each beside its
                 cropped version, for what the black surround does to detection

A placed photometry set can be checked against its `MANIFEST.csv`; the
command is in [`photometry/nikon/README.md`](photometry/nikon/README.md).

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
- **The project data has no published location yet.** Until it does, the
  repository is only reproducible for whoever already holds the files.
- **Weights are pinned only by release tag and size**, not by a content
  hash; see [`models/README.md`](models/README.md).
