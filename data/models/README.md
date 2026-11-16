# Models

No weight in this folder is versioned. Weight files are either downloaded
from the release URLs below or come with the project data, so none of them is
ours to keep in history, and the pre-trained set alone is about 2 GB.
`.gitignore` excludes `.pt`, `.pth`, `.onnx`, `.engine` and `.safetensors`
everywhere, which also covers the checkpoints Ultralytics writes under
`data/runs/`.

Every docker command in the main Readme mounts this folder at `/models`, so
a file placed here as `yolo12x.pt` is `/models/yolo12x.pt` inside the
container.

## Pre-trained

| Model | File | Size | Source |
| --- | --- | --- | --- |
| YOLO11 extra large | `yolo11x.pt` | 114 MB | [ultralytics/assets v8.3.0](https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11x.pt) |
| YOLO11 small | `yolo11s.pt` | 19 MB | [ultralytics/assets v8.3.0](https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11s.pt) |
| YOLO12 extra large | `yolo12x.pt` | 119 MB | [ultralytics/assets v8.3.0](https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo12x.pt) |
| RT-DETR extra large | `rtdetr-x.pt` | 135 MB | [ultralytics/assets v8.3.0](https://github.com/ultralytics/assets/releases/download/v8.3.0/rtdetr-x.pt) |
| RF-DETR large | `rf-detr-large.pth` | 1572 MB | [storage.googleapis.com/rfdetr](https://storage.googleapis.com/rfdetr/rf-detr-large.pth) |

Those five are the ones the thesis reports. `yolo11x.pt` is not in the
sweep; it is kept for single runs against the COCO baseline.

Run from the repository root:

    $assets = "https://github.com/ultralytics/assets/releases/download/v8.3.0"
    foreach ($w in "yolo11x.pt", "yolo11s.pt", "yolo12x.pt", "rtdetr-x.pt") {
        Invoke-WebRequest "$assets/$w" -OutFile "data\models\$w"
    }
    Invoke-WebRequest "https://storage.googleapis.com/rfdetr/rf-detr-large.pth" `
        -OutFile "data\models\rf-detr-large.pth"

Then check what landed, since a truncated download fails later and looks
like a model problem:

    $want = @{ "yolo11x.pt" = 114636239; "yolo11s.pt" = 19313732
               "yolo12x.pt" = 119322638; "rtdetr-x.pt" = 135755662
               "rf-detr-large.pth" = 1571684963 }
    foreach ($f in $want.Keys) {
        $p = "data\models\$f"
        if (-not (Test-Path $p)) { "missing: $f"; continue }
        $got = (Get-Item $p).Length
        if ($got -ne $want[$f]) { "wrong size: $f, $got not $($want[$f])" }
    }

Anything printed is a file that is absent or incomplete. Silence means the
set is complete.

The `v8.3.0` tag is what pins the Ultralytics weights: the same four file
names under a later tag are different files. The byte sizes above are the
weak second check, and they match the weight table in the thesis appendix.

## What a weight file weighs

`weight_sizes.csv` records two numbers per file: its size on disk, and the
bytes of model parameters inside it. They are not the same thing. A released
Ultralytics checkpoint is the model and nothing else, but a training
checkpoint also carries optimiser state:

| file | on disk | parameters |
| --- | --- | --- |
| `rf-detr-large.pth` | 1571 MB | 542 MB |
| `yolo11s_clean.pt` | 38 MB | 18 MB |
| `yolo12x.pt` | 119 MB | 118 MB |

Both matter. The first is what a setup costs to move, the second what it
costs to run, and comparing one model's file size against another's is only
meaningful when they are the same kind of file.

`CompareRuns.py` writes this file, measuring any weight it finds here whose
size does not match the record. It is versioned rather than derived on
demand because no weight file is in the repository: without the record, a
fresh clone could not report a size until the whole set had been downloaded.

## Fine-tuned

| File | Trained on | From | Stage in `train.json` |
| --- | --- | --- | --- |
| `yolo11s_clean.pt` | `coco_nvg_clean.yaml` | `yolo11s.pt` | `nvg_clean`, by hand |
| `yolo11s_clean-noisy.pt` | `coco_nvg_noisy.yaml` | `yolo11s_clean.pt` | `nvg_clean-noisy`, by hand |
| `yolo11s_nvg2_clean.pt` | `coco_nvg2_clean.yaml` | `yolo11s.pt` | `nvg2_clean` |
| `yolo11s_nvg2_clean-noisy.pt` | `coco_nvg2_noisy.yaml` | `yolo11s_nvg2_clean.pt` | `nvg2_clean-noisy` |

All four are part of the project data download, see
[`../README.md`](../README.md). They are not published upstream, so that
download is the only source, and nothing has to be trained to use them.

They are also the only copy that matters. Training again gives new weights
rather than these. For the two v1 files it cannot even read the same data:
the `coco_nvg_*` sets they were trained on came partly from earlier
revisions of `GenerateNVG.py`, and rebuilding them with the frozen script
gives complete sets, not the original ones. The commands stay in the main
Readme as the record of how they were made.

That affects training only. Every reported number recomputes from the five
downloads above plus these four files.

Training here is described under Fine-tuning in the main
[Readme](../../Readme.md#fine-tuning); `RunTrain.ps1` exports each stage
into this folder under the name above.
