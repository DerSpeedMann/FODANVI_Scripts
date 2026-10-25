<#
    RunSweep.ps1

    Score every model in configs/sweep.json against every dataset in it, one
    docker run each, into a result folder named for the pair.

    Run names are val_<model>_<dataset>, so data/runs/val_yolo12x_green_noisy
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
    [string]   $Image    = "ultralytics/ultralytics:8.4.41",
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
# Named, not discovered. The folder also holds groupings kept for training,
# whose val split is the union of two single-conversion configs beside them,
# and sweeping those would score the same images three times and report it
# as three results.
$named = @($cfg.datasets)
if (-not $named) { throw "$Config lists no datasets" }

# Filtered before the existence check, so a listed set that is not built yet
# only stops a sweep that actually asks for it.
$pickedSets = @($named |
    Where-Object { $n = $_; $Datasets | Where-Object { $n -like $_ } } |
    ForEach-Object {
        $f = Join-Path $cfg.paths.datasets "$_.yaml"
        if (-not (Test-Path $f)) { throw "$Config lists '$_', but $f does not exist" }
        Get-Item $f
    })
if (-not $pickedSets) { throw "no dataset matched: $($Datasets -join ', ')" }

# A variant built but never added to the list would otherwise be missing
# from the results with nothing to show for it.
$unlisted = @(Get-ChildItem (Join-Path $cfg.paths.datasets "*.yaml") -File |
    Where-Object { $named -notcontains $_.BaseName } | ForEach-Object BaseName)
if ($unlisted) {
    Write-Host "not in $Config, not swept: $($unlisted -join ', ')`n"
}

# Fail before the first container rather than part way through a long sweep.
if (-not $WhatIf) {
    foreach ($m in $pickedModels) {
        $p = Join-Path $cfg.paths.models $m.Value.weight
        if (-not (Test-Path $p)) {
            throw "missing weight: $p (see $($cfg.paths.models)\README.md)"
        }
    }
}

# Windows sleeps on its idle timer regardless of a container working, and
# a sweep is hours of no keyboard or mouse. This asks it to stay awake for
# as long as this process lives, which needs no settings change and cannot
# be left switched on afterwards. The display is left free to turn off; it
# does not stop the GPU.
$keepAwake = $null
if (-not $WhatIf) {
    try {
        $keepAwake = Add-Type -PassThru -Name Power -Namespace Sweep `
            -MemberDefinition @'
[DllImport("kernel32.dll", SetLastError = true)]
public static extern uint SetThreadExecutionState(uint esFlags);
'@
        # ES_CONTINUOUS | ES_SYSTEM_REQUIRED. Converted rather than written
        # as a literal: 0x80000001 is a negative Int32 to PowerShell and will
        # not cast to the UInt32 the call takes.
        $hold = [Convert]::ToUInt32("80000001", 16)
        if ($keepAwake::SetThreadExecutionState($hold) -eq 0) {
            Write-Warning "could not hold off standby; check the sleep timeout"
            $keepAwake = $null
        }
    } catch {
        Write-Warning "could not hold off standby: $($_.Exception.Message)"
        $keepAwake = $null
    }
}

# A validator that needs prebuilt box annotations gets them built here,
# on the host. Doing it in the container reads an image header and a label
# file per image across the bind mount, which is hours per 5000 image split
# against under a minute here, and it is the same file on every run.
# rfdetr_val.py itself refuses to build one, so a gap cannot turn into a
# silent four hour rebuild inside a run.
if (-not $WhatIf) {
    $needGt = @()
    foreach ($m in $pickedModels) {
        if (-not $cfg.validators.($m.Value.validator).needs_box_annotations) { continue }
        foreach ($d in $pickedSets) { $needGt += $d }
    }
    foreach ($d in @($needGt | Sort-Object -Property BaseName -Unique)) {
        $gt = Join-Path $cfg.paths.datasets "$($d.BaseName)_gt.json"
        if (Test-Path $gt) { continue }
        Write-Host "build box annotations for $($d.BaseName)"
        $prevEAP = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        python (Join-Path $cfg.paths.processing "GenerateBoxAnnotations.py") `
            $d.FullName $gt
        $code = $LASTEXITCODE
        $ErrorActionPreference = $prevEAP
        if ($code -ne 0 -or -not (Test-Path $gt)) {
            throw "could not build box annotations for $($d.BaseName)"
        }
    }
    if ($needGt) { Write-Host "" }
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
            # Checked above, so it is there.
            $gtArg = if ($v.needs_box_annotations) { " /datasets/$($d.BaseName)_gt.json" } else { "" }
            # The image sets PIP_NO_CACHE_DIR, and pip disables its cache
            # whatever value that holds, so it is removed for this one
            # command. Otherwise nothing reaches the mounted cache below and
            # every run downloads the packages again.
            $cmd = @("bash", "-c",
                     "env -u PIP_NO_CACHE_DIR pip install --quiet --root-user-action=ignore $($v.pip) && python $script $weight $data $name$gtArg")
        } else {
            $cmd = @("python", $script, $weight, $data, $name)
        }

        Write-Host "run   $name"
        # Anything a container writes to stderr becomes an ErrorRecord under
        # ErrorActionPreference Stop, and a pip notice would end the sweep.
        # The exit code is what says whether the run worked.
        $prevEAP = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        # /root/.cache holds pip's wheels and the Hugging Face hub, which a
        # --rm container would otherwise fetch again on every run. Kept in
        # .cache\<model> at the repo root, which is gitignored, one folder per
        # model so pins that differ between models cannot collide.
        $cache = Join-Path $PWD ".cache\$($m.Name)"
        New-Item -ItemType Directory -Force $cache | Out-Null
        docker run --gpus all --rm --shm-size=$ShmSize `
            -v "${cache}:/root/.cache" `
            -v "${PWD}\$($cfg.paths.datasets -replace '/','\'):/datasets" `
            -v "${PWD}\$($cfg.paths.models   -replace '/','\'):/models" `
            -v "${PWD}\$($cfg.paths.runs -replace '/','\\'):/ultralytics/runs/detect" `
            -v "${PWD}\$($cfg.paths.processing -replace '/','\'):/workspace" `
            $Image @cmd

        $ErrorActionPreference = $prevEAP
        if ($LASTEXITCODE -ne 0) {
            Write-Warning "$name exited $LASTEXITCODE"
            $failed += $name
        } else { $done++ }
    }
}

# ES_CONTINUOUS alone, which drops the request. It also lapses when the
# process exits, so an interrupted sweep does not leave the machine awake.
if ($keepAwake) {
    [void]$keepAwake::SetThreadExecutionState([Convert]::ToUInt32("80000000", 16))
}

if (-not $WhatIf) {
    Write-Host "`n$done completed, $skipped skipped, $($failed.Count) failed"
    $failed | ForEach-Object { Write-Host "  failed: $_" }
}
