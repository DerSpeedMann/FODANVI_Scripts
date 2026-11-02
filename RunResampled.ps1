<#
    RunResampled.ps1

    Score one model against every set BuildResampledSets.py built, in a
    single container: the sets are many and small, so starting a container
    per set, as RunSweep.ps1 does, would cost more than the validation.

    Run names are val_<model>_<set>, as in the sweep, written to
    data/runs_resampled rather than data/runs, so the resampled runs stay
    out of comparison.csv and the sweep figures. A run whose folder already
    exists is skipped, so an interrupted batch resumes by being started
    again. Collect the results with
        python src\Processing\CompareRuns.py --runs data/runs_resampled --out data/results_resampled --no-plots

        .\RunResampled.ps1                          yolo12x on every set
        .\RunResampled.ps1 -Sets "real_nvg_rs_*"    only these sets
        .\RunResampled.ps1 -WhatIf                  list what would run
#>

[CmdletBinding()]
param(
    [string] $Config  = "sweep.json",
    [string] $Model   = "yolo12x",
    [string] $Sets    = "*",
    [string] $Folder  = "resampled",
    [string] $Runs    = "data/runs_resampled",
    [string] $Image   = "ultralytics/ultralytics:8.4.41",
    [string] $ShmSize = "18g",
    [switch] $WhatIf
)

$ErrorActionPreference = "Stop"
$cfg = Get-Content $Config -Raw | ConvertFrom-Json

$m = $cfg.models.$Model
if (-not $m) { throw "$Config has no model '$Model'" }
if ($m.validator -ne "yolo") {
    throw "$Model uses the '$($m.validator)' validator; this batch runs yolo_val.py only"
}
$weight = Join-Path $cfg.paths.models $m.weight
if (-not (Test-Path $weight)) { throw "missing weight: $weight" }

$setDir = Join-Path $cfg.paths.datasets $Folder
$yamls = @(Get-ChildItem (Join-Path $setDir "$Sets.yaml") -File | Sort-Object Name)
if (-not $yamls) { throw "no set matched $Sets.yaml in $setDir; run BuildResampledSets.py first" }

New-Item -ItemType Directory -Force $Runs | Out-Null
$todo = @($yamls | Where-Object {
    -not (Test-Path (Join-Path $Runs "val_${Model}_$($_.BaseName)")) })
Write-Host "$($yamls.Count) set(s), $($todo.Count) to run, $($yamls.Count - $todo.Count) exist"
if ($WhatIf) {
    $todo | ForEach-Object { Write-Host "would run  val_${Model}_$($_.BaseName)" }
    return
}
if (-not $todo) { return }

# One shell loop in one container. Each set still gets its own python
# process and so its own run folder and console log, exactly as a sweep run.
$lines = $todo | ForEach-Object {
    $n = "val_${Model}_$($_.BaseName)"
    "echo run $n; python /workspace/$($cfg.validators.yolo.script) /models/$($m.weight) /datasets/$Folder/$($_.Name) $n || echo FAILED $n"
}
$script = ($lines -join "`n")

$prevEAP = $ErrorActionPreference
$ErrorActionPreference = "Continue"
$cache = Join-Path $PWD ".cache\$Model"
New-Item -ItemType Directory -Force $cache | Out-Null
docker run --gpus all --rm --shm-size=$ShmSize `
    -v "${cache}:/root/.cache" `
    -v "${PWD}\$($cfg.paths.datasets -replace '/','\'):/datasets" `
    -v "${PWD}\$($cfg.paths.models   -replace '/','\'):/models" `
    -v "${PWD}\$($Runs -replace '/','\'):/ultralytics/runs/detect" `
    -v "${PWD}\$($cfg.paths.processing -replace '/','\'):/workspace" `
    $Image bash -c $script
$ErrorActionPreference = $prevEAP

$done = @($todo | Where-Object {
    Test-Path (Join-Path $Runs "val_${Model}_$($_.BaseName)\tables") })
Write-Host "`n$($done.Count) of $($todo.Count) completed"
