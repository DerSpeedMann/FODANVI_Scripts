<#
    RunSweep.ps1

    Score every model in configs/sweep.json against every dataset in it, one
    docker run each, into a result folder named for the pair.

    Run names are val_<model>_<dataset>, so runs/detect/val_yolo12x_green_noisy
    is yolo12x on the noisy green conversion. Each validation script writes
    logs/console.log, per_class_metrics.csv and supercategory_metrics.csv into
    its own run folder, so no result has to be read back out of the terminal.

    A run whose folder already exists is skipped, so an interrupted sweep
    resumes by being started again.

        .\RunSweep.ps1                      everything in the config
        .\RunSweep.ps1 -Datasets real*      only the real captures
        .\RunSweep.ps1 -Models yolo12x      one model
        .\RunSweep.ps1 -WhatIf              list what would run
        .\RunSweep.ps1 -Force               redo runs that already exist
#>
[CmdletBinding()]
param(
    [string]   $Config   = "sweep.json",
    [string[]] $Models   = "*",
    [string[]] $Datasets = "*",
    [string]   $Image    = "ultralytics/ultralytics:latest",
    [string]   $ShmSize  = "18g",
    [switch]   $Force,
    [switch]   $WhatIf
)

$ErrorActionPreference = "Stop"
$cfg = Get-Content $Config -Raw | ConvertFrom-Json

function Select-Entries($node, $patterns) {
    $node.PSObject.Properties |
        Where-Object { $_.Name -notlike "_*" } |
        Where-Object { $n = $_.Name; $patterns | Where-Object { $n -like $_ } }
}

$pickedModels = @(Select-Entries $cfg.models $Models)
if (-not $pickedModels) { throw "no model matched: $($Models -join ', ')" }

# Every config in the dataset folder, so dropping one in is enough to put it
# in the sweep. Only the models need naming, since a weight file and the
# validator that drives it cannot be worked out by looking.
$pickedSets = @(Get-ChildItem (Join-Path $cfg.paths.datasets "*.yaml") -File |
    Sort-Object Name |
    Where-Object { $n = $_.BaseName; $Datasets | Where-Object { $n -like $_ } })
if (-not $pickedSets) { throw "no dataset yaml matched: $($Datasets -join ', ')" }

# Fail before the first container rather than part way through a long sweep.
if (-not $WhatIf) {
    foreach ($m in $pickedModels) {
        $p = Join-Path $cfg.paths.models $m.Value.weight
        if (-not (Test-Path $p)) {
            throw "missing weight: $p (see $($cfg.paths.models)\README.md)"
        }
    }
}

$planned = $pickedModels.Count * $pickedSets.Count
Write-Host "$planned run(s): $($pickedModels.Count) model(s) x $($pickedSets.Count) dataset(s)`n"

$done = 0; $skipped = 0; $failed = @()
foreach ($m in $pickedModels) {
    $v = $cfg.validators.($m.Value.validator)
    if (-not $v) { throw "$($m.Name) names validator '$($m.Value.validator)', which the config does not define" }

    foreach ($d in $pickedSets) {
        $name = "val_$($m.Name)_$($d.BaseName)"
        $out = Join-Path $cfg.paths.runs $name

        if ((Test-Path $out) -and -not $Force) {
            Write-Host "skip  $name (exists)"; $skipped++; continue
        }
        if ($WhatIf) { Write-Host "would run  $name"; continue }

        # Ultralytics does not overwrite: pointed at a name that exists it
        # writes <name>-2 instead, so -Force has to clear the folder or the
        # result lands somewhere the next run will not find it.
        if (Test-Path $out) { Remove-Item $out -Recurse -Force }

        $weight = "/models/" + $m.Value.weight
        $data = "/datasets/" + $d.Name
        $script = "/workspace/" + $v.script

        # A validator needing packages the image lacks installs them first,
        # inside the same container, so nothing is left behind.
        if ($v.PSObject.Properties.Name -contains "pip") {
            $cmd = @("bash", "-c",
                     "pip install --quiet $($v.pip) && python $script $weight $data $name")
        } else {
            $cmd = @("python", $script, $weight, $data, $name)
        }

        Write-Host "run   $name"
        docker run --gpus all --rm --shm-size=$ShmSize `
            -v "${PWD}\$($cfg.paths.datasets -replace '/','\'):/datasets" `
            -v "${PWD}\$($cfg.paths.models   -replace '/','\'):/models" `
            -v "${PWD}\runs:/ultralytics/runs/detect" `
            -v "${PWD}\$($cfg.paths.processing -replace '/','\'):/workspace" `
            $Image @cmd

        if ($LASTEXITCODE -ne 0) {
            Write-Warning "$name exited $LASTEXITCODE"
            $failed += $name
        } else { $done++ }
    }
}

if (-not $WhatIf) {
    Write-Host "`n$done completed, $skipped skipped, $($failed.Count) failed"
    $failed | ForEach-Object { Write-Host "  failed: $_" }
}
