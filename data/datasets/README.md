# Datasets

Annotated image sets for detection training and evaluation.

What is versioned here is the part that cannot be regenerated. The images are
fetched separately and placed, as everywhere else under `data/`. The
per-image label files under `labels/` are not kept either: a YOLO `.txt` is a
projection of the annotation it was exported from, four numbers and a class
index, and it can be remade at any time.

The annotation exports under a dataset's `source/` are kept. They are the
manual labelling work, they hold polygons and class names rather than boxes,
and nothing recovers them from the `.txt` the export produced. For the real
night vision set that is 420 KB against the 66 KB of labels it generates,
which is the cheaper half to carry and the expensive half to lose.

Split definitions and class lists at a dataset root stay in git too, so a
placed set can be checked against them.

## What is in here

| sets | from | built by |
| --- | --- | --- |
| `coco` | COCO 2017, downloaded (below) | |
| `real_nvg`, `moving_car`, `phone_ref` | the project data download, see [`../README.md`](../README.md) | annotated here, see [Annotation](#annotation) |
| `coco_nvg*` | `coco` | `BuildDay2NightDatasets.py`, see the main [Readme](../../Readme.md#converted-coco-sets) |
| `real_nvg_*`, `coco_nvg2_*_dn_*` | the sets above | `BuildDatasets.ps1` from `sweep.json`, see the main [Readme](../../Readme.md#dataset-variants) |
| `resampled/` | `real_nvg` and its variants | `BuildResampledSets.py`, see the main [Readme](../../Readme.md#resampled-sets) |

Every set has its `<name>.yaml` beside the folder, versioned; the
groupings used for training are yamls only.

## COCO

The source dataset every converted set is built from. Ultralytics publishes
it in the layout these scripts expect, so the simplest route is to let it
download once and then move the tree into place. From the repository root:

    yolo settings datasets_dir="$(Resolve-Path .\data\datasets)"
    python -c "from ultralytics.utils.downloads import download; download('https://ultralytics.com/assets/coco2017labels.zip', dir='data/datasets')"

Or fetch it by hand from https://cocodataset.org/#download, taking
`train2017`, `val2017` and `annotations_trainval2017`, and arrange it as:

    data/datasets/coco/images/train2017/
    data/datasets/coco/images/val2017/
    data/datasets/coco/labels/train2017/
    data/datasets/coco/labels/val2017/
    data/datasets/coco/annotations/

About 20 GB. The whole `coco/` tree is gitignored, including the annotation
json and the split lists, since none of it is ours.

## Annotation

Every command below runs from the repository root.

The real captures (`real_nvg`), the moving car frames
(`moving_car`) and the phone reference (`phone_ref`) were annotated in
labelme as polygons, with the COCO category names of `data/coco_labels.txt`.
labelme (6.0) scans a folder recursively, saves automatically beside each
image and leaves the image data out of the `.json` unless
`--with-image-data` is given:

    labelme data\datasets\moving_car\source --labels data\coco_labels.txt

### Converting to YOLO

`ConvertAnnotations.ps1` turns a labelme source folder into a YOLO dataset
with every frame in `images/val` and `labels/val`, through labelme2yolo,
which reduces each polygon to its enclosing box:

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
`images/val`, byte for byte. To convert it again, copy the images back beside
the `.json` under their original names, without the suffix labelme2yolo
appends (`capture_..._cropped_a4cf5093.jpg` becomes `capture_..._cropped.jpg`).
