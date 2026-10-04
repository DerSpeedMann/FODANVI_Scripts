# Models

Nothing in this folder is versioned. Weight files are either downloaded from
the release URLs below or produced by a fine-tuning run, so none of them is
ours to keep in history, and the pre-trained set alone is about 2 GB.
`.gitignore` excludes `.pt`, `.pth`, `.onnx`, `.engine` and `.safetensors`
everywhere, which also covers the checkpoints Ultralytics writes under
`runs/`.

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

Those five are the ones the thesis reports. `rtdetr-l.pt`, 66 MB, from the
[same release](https://github.com/ultralytics/assets/releases/download/v8.3.0/rtdetr-l.pt),
is used by one `yolo detect predict` example in the main Readme and by
nothing else.

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

## Fine-tuned

| File | Trained on | From |
| --- | --- | --- |
| `yolo11s_clean.pt` | `coco_nvg_clean.yaml` | `yolo11s.pt` |
| `yolo11s_clean-noisy.pt` | `coco_nvg_noisy.yaml` | `yolo11s_clean.pt` |

Both come from the capture archive, alongside the images; see the download
section of the main Readme. They are not published upstream, so the archive
is the only source, and nothing has to be trained to use them.

They are also the only copy that matters. Re-running the two
`yolo detect train` commands in the main Readme gives new weights rather
than these, because `coco_nvg_green_clean/images/train2017` now holds about
35 000 frames where each of its three siblings holds roughly 118 000, so
`coco_nvg_clean.yaml` no longer reads the set these were trained on. The
commands stay in the Readme as the record of how the published weights were
made.

That affects training only. The validation splits are complete at 5 000
each, so every reported number recomputes from the five downloads above
plus these two files.

Ultralytics writes checkpoints to `runs/detect/<name>/weights/best.pt`. A
model trained here has to be copied into this folder under one of the names
above, because the validation commands read `/models` rather than the run
folder.
