<#
    RunTrain.ps1

    Run the fine-tuning stages in train.json, one docker run each, in the
    order given, and copy each stage's best.pt into the model folder so the
    next stage and the sweep can load it.

    A stage with stop_after ends after that many epochs while its configured
    epochs stay at 100, so it trains on the learning-rate schedule of a
    100 epoch run and is cut off part way, as the original runs were. The
    container runs detached and is stopped once results.csv holds that many
    epochs. Without stop_after the stage runs until the framework ends it.

    The command passed to yolo detect train is the stage's model and data,
    then the shared settings under train, the device's batch and workers,
    the stage's own args and last any -Set, each later one winning.

        .\RunTrain.ps1 -Stages nvg2_clean,nvg2_clean-noisy   the measured chain
        .\RunTrain.ps1 -Stages nvg2_*                         the same, by pattern
        .\RunTrain.ps1 -Stages nvg2_clean -Set epochs=50,lr0=0.0002
        .\RunTrain.ps1 -Stages nvg2_clean -StopAfter 2        a short trial
        .\RunTrain.ps1 -Stages nvg2_clean -StopAfter 25       continue to 25
        .\RunTrain.ps1 -Stages nvg2_* -WhatIf                 print the commands
        .\RunTrain.ps1 -Stages nvg2_clean -Force              redo, overwrite

    A stage is never more than stopped, since epochs stays at 100, so it can
    always be taken further. Started again, a stage that already has its
    epochs is skipped; one interrupted before them resumes from its last.pt;
    and given a -StopAfter above what it has, a finished stage resumes too and
    trains on to the new count. A resumed run takes every argument from its
    checkpoint, so it continues the same learning-rate schedule as if it had
    never been stopped, and its best.pt is exported again when it ends. A
    stage trained further invalidates the stages that started from its
    weights; rerun those with -Force.

    -Force starts a stage over and overwrites its export. Weights in the
    model folder that no run here produced, such as the hand-tuned ones the
    thesis reports, are never overwritten without it.

    Paths in the config are relative to this script's folder, so the script
    can be started from anywhere.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)] [string[]] $Stages,
    [string]   $Config = "train.json",
    [string[]] $Set = @(),
    [int]      $StopAfter = 0,
    [int]      $PollSeconds = 60,
    [int]      $GraceSeconds = 180,
    [switch]   $Force,
    [switch]   $WhatIf
)

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$cfgPath = if ([IO.Path]::IsPathRooted($Config)) { $Config } else { Join-Path $root $Config }
$cfg = Get-Content $cfgPath -Raw | ConvertFrom-Json

function Resolve-Repo($rel) {
    $p = $rel -replace '/', '\'
    if ([IO.Path]::IsPathRooted($p)) { $p } else { Join-Path $root $p }
}
$datasets = Resolve-Repo $cfg.paths.datasets
$models   = Resolve-Repo $cfg.paths.models
$runs     = Resolve-Repo $cfg.paths.runs

# Stages in the order asked for, each pattern expanded in config order, so
# -Stages nvg2_* runs stage 1 before stage 2.
$all = @($cfg.stages.PSObject.Properties | Where-Object { $_.Name -notlike "_*" })
$picked = @()
foreach ($p in $Stages) {
    $hit = @($all | Where-Object { $_.Name -like $p })
    if (-not $hit) { throw "no stage matched '$p'; known: $(($all | ForEach-Object Name) -join ', ')" }
    $picked += $hit | Where-Object { $picked.Name -notcontains $_.Name }
}

# key=value pairs into an ordered table, later ones replacing earlier ones.
# Comment keys are dropped, so _note can sit beside real settings.
function Add-Settings($table, $obj) {
    if (-not $obj) { return }
    foreach ($p in $obj.PSObject.Properties) {
        if ($p.Name -like "_*") { continue }
        $table[$p.Name] = $p.Value
    }
}
$overrides = [ordered]@{}
foreach ($kv in $Set) {
    $k, $v = $kv -split '=', 2
    if (-not $v) { throw "-Set takes key=value, got '$kv'" }
    $overrides[$k.Trim()] = $v.Trim()
}

function Get-Epochs($csv) {
    if (-not (Test-Path $csv)) { return @() }
    @(Import-Csv $csv)
}

# Windows sleeps on its idle timer whatever a container is doing, and a stage
# is many hours without input. Held for as long as this process lives, as in
# RunSweep.ps1, and released at the end or when the process exits.
$keepAwake = $null
if (-not $WhatIf) {
    try {
        $keepAwake = Add-Type -PassThru -Name Power -Namespace Train `
            -MemberDefinition @'
[DllImport("kernel32.dll", SetLastError = true)]
public static extern uint SetThreadExecutionState(uint esFlags);
'@
        if ($keepAwake::SetThreadExecutionState([Convert]::ToUInt32("80000001", 16)) -eq 0) {
            Write-Warning "could not hold off standby; check the sleep timeout"
            $keepAwake = $null
        }
    } catch {
        Write-Warning "could not hold off standby: $($_.Exception.Message)"
        $keepAwake = $null
    }
}

$container = $null
try {
    foreach ($s in $picked) {
        $st = $s.Value
        $runDir = Join-Path $runs $st.name
        $export = Join-Path $models $st.export
        $stop = if ($StopAfter -gt 0) { $StopAfter } elseif ($st.stop_after) { [int]$st.stop_after } else { 0 }
        $image = if ($st.image) { $st.image } else { $cfg.device.image }

        $args_ = [ordered]@{
            model = "/models/$($st.model)"
            data  = "/datasets/$($st.data).yaml"
        }
        Add-Settings $args_ $cfg.train
        $args_["batch"]   = $cfg.device.batch
        $args_["workers"] = $cfg.device.workers
        Add-Settings $args_ $st.args
        foreach ($k in $overrides.Keys) { $args_[$k] = $overrides[$k] }
        # Fixed last, so -Set cannot send the output where this script does
        # not look for it.
        $args_["project"] = "/ultralytics/runs/detect"
        $args_["name"]    = $st.name
        $trainArgs = @($args_.Keys | ForEach-Object { "$_=$($args_[$_])" })

        Write-Host "`n=== $($s.Name)  ($image$(if ($stop) { ", stop after $stop epochs" })) ==="
        $csv  = Join-Path $runDir "results.csv"
        $last = Join-Path $runDir "weights\last.pt"
        $best = Join-Path $runDir "weights\best.pt"
        $done = @(Get-Epochs $csv).Count

        # What is on disk decides what happens, so a stage continues from
        # wherever it was left by being started again:
        #   no run, export there      weights from elsewhere, e.g. the
        #                             hand-tuned ones, never overwritten
        #   epochs reached, exported  skip
        #   epochs reached            only the copy is missing
        #   fewer epochs, last.pt     interrupted, or -StopAfter raised past
        #                             what it has: resume from last.pt
        #   otherwise                 start fresh
        $mode = "fresh"
        if (-not $Force) {
            $hasRun = Test-Path $last
            if ((Test-Path $export) -and -not $hasRun) {
                throw "$export exists and no run of this stage does; -Force to overwrite it"
            }
            $reached = $hasRun -and ($stop -eq 0 -or $done -ge $stop)
            if ($reached -and (Test-Path $export)) {
                Write-Host "skip  $($st.name) has $done epochs, exported to $($st.export)"
                continue
            }
            if ($reached) { $mode = "copy" }
            elseif ($hasRun) { $mode = "resume" }
        }

        $weight = Join-Path $models $st.model
        $yaml = Join-Path $datasets "$($st.data).yaml"
        if ($mode -eq "resume") {
            # The checkpoint carries every argument of the original run,
            # epochs and the learning-rate schedule included, so nothing is
            # passed but the checkpoint; -Set would be ignored by the framework.
            if ($Set) { Write-Warning "-Set does not apply to a resumed run" }
            $trainArgs = @("resume", "model=/ultralytics/runs/detect/$($st.name)/weights/last.pt")
        }
        if ($WhatIf) {
            switch ($mode) {
                "copy"   { Write-Host "would copy  $done epochs done, best.pt -> $export" }
                "resume" { Write-Host "would resume after epoch $done  yolo detect train $($trainArgs -join ' ')" }
                default  { Write-Host "would run  yolo detect train $($trainArgs -join ' ')"
                           Write-Host "then copy  $($st.name)\weights\best.pt -> $export" }
            }
            continue
        }

        if ($mode -ne "copy") {
            if ($mode -eq "fresh") {
                # Checked here rather than up front: stage 2 loads what stage 1
                # exports, which does not exist until stage 1 has run.
                if (-not (Test-Path $weight)) { throw "missing weight: $weight" }
                if (-not (Test-Path $yaml)) { throw "missing dataset config: $yaml" }
                # Ultralytics does not overwrite: given a name that exists it
                # writes <name>2, where nothing below would find it.
                if (Test-Path $runDir) { Remove-Item $runDir -Recurse -Force }
                $done = 0
            }

            $container = "train_$($s.Name)"
            $prevEAP = $ErrorActionPreference
            $ErrorActionPreference = "Continue"
            docker rm -f $container 2>$null | Out-Null
            docker run -d --name $container --gpus $cfg.device.gpus --rm `
                --shm-size=$($cfg.device.shm_size) `
                -v "${datasets}:/datasets" `
                -v "${models}:/models" `
                -v "${runs}:/ultralytics/runs/detect" `
                $image yolo detect train @trainArgs | Out-Null
            $ErrorActionPreference = $prevEAP
            if ($LASTEXITCODE -ne 0) { throw "docker run failed for $($s.Name)" }
            Write-Host "$(if ($mode -eq 'resume') { "resumed after epoch $done" } else { 'started' }) $container; follow it with: docker logs -f $container"

            $seen = $done
            while ($true) {
                Start-Sleep $PollSeconds
                $rows = Get-Epochs $csv
                for ($i = $seen; $i -lt $rows.Count; $i++) {
                    $r = $rows[$i]
                    Write-Host ("  epoch {0,3}  mAP50-95 {1}  {2}" -f `
                        $r.epoch.Trim(), $r.'metrics/mAP50-95(B)'.Trim(), (Get-Date -Format "MM-dd HH:mm"))
                }
                $seen = $rows.Count
                if ($stop -and $seen -ge $stop) {
                    # results.csv is written before the epoch's weights are saved.
                    Start-Sleep $GraceSeconds
                    docker stop $container | Out-Null
                    break
                }
                $running = docker ps -q --filter "name=^$container$"
                if (-not $running) {
                    if ($stop) { throw "$container ended after $seen of $stop epochs; see $runDir" }
                    break
                }
            }
            $container = $null
            $done = $seen
        }

        if (-not (Test-Path $best)) { throw "no best.pt in $runDir" }
        Copy-Item $best $export -Force
        Write-Host "done  $($st.name): $done epochs, best.pt -> $export"
    }
} finally {
    # Interrupted with Ctrl+C: stop the detached container too, rather than
    # leave a run going that nothing will cut off at its epoch count.
    if ($container) {
        Write-Warning "stopping $container"
        docker stop $container 2>$null | Out-Null
    }
    if ($keepAwake) {
        [void]$keepAwake::SetThreadExecutionState([Convert]::ToUInt32("80000000", 16))
    }
}
