<#
    ConvertAnnotations.ps1

    Convert a folder of labelme annotations into a YOLO dataset, with every
    frame in the one validation split.

    Every folder under -Source that holds images or labelme .json files is
    converted on its own, since labelme2yolo empties its output folder on every run: each
    goes into a temporary folder, and its images and labels are moved from
    there into images/val and labels/val of -Output. The folder each image
    came from, relative to -Source, is written to groups.csv beside them, so
    that the frames can be scored per group from a single run; for the moving
    car that is <session>/<device>. -Background takes the frames without a
    label in as background images with an empty label file
    (--include_background).

    The category names are read from -Labels, with any leading index number,
    surrounding whitespace and empty lines removed, and passed to labelme2yolo
    in the order of the list, so that the index of each name is its COCO
    index.

    labelme2yolo writes a dataset.yaml whose path is the absolute folder on
    the host, which does not exist inside the container the runs execute in,
    and no option of the converter changes it. The definition is therefore
    written beside the dataset folder as <dataset>.yaml, where RunSweep.ps1
    looks, with its path reduced to the folder name.

    images/val and labels/val of -Output are emptied first, so a rerun
    rebuilds the set; anything else in -Output, such as the source, is kept.

        .\ConvertAnnotations.ps1 -Source .\data\datasets\real_nvg\source `
          -Output .\data\datasets\real_nvg
        .\ConvertAnnotations.ps1 -Source .\data\datasets\moving_car\source `
          -Output .\data\datasets\moving_car -Background
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)] [string] $Source,
    [Parameter(Mandatory)] [string] $Output,
    [string] $Labels = ".\data\coco_labels.txt",
    [switch] $Background
)
$ErrorActionPreference = "Stop"

if (-not (Get-Command labelme2yolo -ErrorAction SilentlyContinue)) {
    throw "labelme2yolo not found on PATH; install it with " +
          "'pip install labelme2yolo==0.3.3' and run again."
}

$names = Get-Content $Labels | ForEach-Object {
    ($_ -replace '^\s*\d+\s+', '').Trim()
} | Where-Object { $_ -ne '' }
$flags = @("--val_size", "1", "--deterministic_labels")
if ($Background) { $flags += "--include_background" }

$Source = (Resolve-Path $Source).Path.TrimEnd('\')
$name   = Split-Path -Leaf $Output
$yaml   = Join-Path (Split-Path -Parent $Output) "$name.yaml"
foreach ($sub in "images\val", "labels\val") {
    Remove-Item -Recurse -Force "$Output\$sub" -ErrorAction SilentlyContinue
    New-Item -ItemType Directory -Force "$Output\$sub" | Out-Null
}

$folders = @(Get-Item $Source) + @(Get-ChildItem -Directory -Recurse $Source) |
  Where-Object {
      Get-ChildItem -File "$($_.FullName)\*" -Include *.json, *.jpg, *.jpeg, *.png
  }
$rows = foreach ($d in $folders) {
    $group = $d.FullName.Substring($Source.Length).TrimStart('\') -replace '\\', '/'
    $tmp = Join-Path $Output ("convert_" + ($group -replace '/', '_'))
    # labelme2yolo logs to stderr, which Windows PowerShell turns into
    # errors once redirected; "Stop" would abort on the first log line, so
    # its exit code is checked instead.
    $ErrorActionPreference = "Continue"
    labelme2yolo --json_dir $d.FullName --output_dir $tmp @flags @names |
      Out-Null
    $ErrorActionPreference = "Stop"
    if ($LASTEXITCODE -ne 0) {
        throw "labelme2yolo failed on $($d.FullName) (exit code $LASTEXITCODE)"
    }
    # It exits 0 even when it skips an annotation whose image is missing, so
    # check that every .json came out as an image.
    $json = @(Get-ChildItem -File -Filter *.json $d.FullName).Count
    $out  = @(Get-ChildItem -File "$tmp\images\val" -ErrorAction SilentlyContinue).Count
    if ($out -lt $json) {
        throw "labelme2yolo converted $out of $json annotations in " +
              "$($d.FullName); are the images beside the .json files?"
    }
    foreach ($img in Get-ChildItem "$tmp\images\val") {
        [pscustomobject]@{ file = $img.BaseName; group = $group }
    }
    Move-Item "$tmp\images\val\*" "$Output\images\val\"
    Move-Item "$tmp\labels\val\*" "$Output\labels\val\"
    (Get-Content "$tmp\dataset.yaml") -replace '^path: .*$', "path: $name" |
      Set-Content -Encoding ascii $yaml
    Remove-Item -Recurse $tmp
}
$rows | Sort-Object group, file |
  Export-Csv "$Output\groups.csv" -NoTypeInformation -Encoding ascii
