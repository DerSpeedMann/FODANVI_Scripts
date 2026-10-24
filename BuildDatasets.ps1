<#
    BuildDatasets.ps1

    Create every dataset listed under "variants" in sweep.json.

    "variants" is a list. Each entry names a source dataset and the
    generator chains to apply to it. A chain is an ordered list of names from
    the "generators" block, so one chain can be several steps. Each generator
    names a script in src/Processing, the suffix that script appends, and any
    extra arguments it takes after the input and output folders.

    The dataset a chain produces is named for its source and the suffixes it
    applies, so real_nvg with ["grayscale","white"] becomes
    real_nvg_grayscale_white. Naming it in the config as well would only be a
    second place for it to be wrong.

    The work is done by the scripts that are already there. A generator writes
    the images with its suffix, the next one runs over that output, and
    CopyFilesWithSuffix.py finally writes the labels with the suffixes joined
    in the same order. That matches how the converted COCO sets are named and
    is what lets Ultralytics pair an image with its label by stem. Nothing is
    reimplemented here; this walks the config and calls them.

    The yaml it writes lands in the dataset folder, which is where
    RunSweep.ps1 looks, so building a variant is enough to put it in the
    sweep.

        .\BuildDatasets.ps1                        build what is missing
        .\BuildDatasets.ps1 -Only real_nvg_white   one of them
        .\BuildDatasets.ps1 -Force                 rebuild even if present
        .\BuildDatasets.ps1 -WhatIf                list what would be built
#>
[CmdletBinding()]
param(
    [string]   $Config   = "sweep.json",
    [string[]] $Only     = "*",
    [switch]   $Force,
    [switch]   $WhatIf
)

$ErrorActionPreference = "Stop"

# One config with RunSweep.ps1, so the paths are defined once and the two
# cannot disagree about where anything lives.
$cfg = Get-Content $Config -Raw | ConvertFrom-Json
$dsRoot = $cfg.paths.datasets
$proc = $cfg.paths.processing
$gens = $cfg.generators

# A console on a legacy codepage cannot encode what some generators print,
# and the exception would kill a run part way through a folder.
$env:PYTHONIOENCODING = "utf-8"

# Flatten source -> [chain, chain] into one job per dataset to build, with
# the name each chain produces. Every generator has to exist before any work
# starts, so a typo fails now rather than after an hour of conversions.
$known = $gens.PSObject.Properties.Name
$jobs = @()
foreach ($entry in $cfg.variants) {
    if (-not $entry.source) { throw "a variants entry has no source" }
    foreach ($chain in $entry.chains) {
        $steps = @($chain)
        if (-not $steps) { throw "$($entry.source) has an empty chain" }
        foreach ($g in $steps) {
            if ($known -notcontains $g) {
                throw "$($entry.source) applies '$g', which generators does not define"
            }
        }
        $defs = @($steps | ForEach-Object { $gens.$_ })
        $suffix = -join ($defs | ForEach-Object { $_.suffix })
        $jobs += [pscustomobject]@{
            Name   = "$($entry.source)$suffix"
            Source = $entry.source
            Steps  = $steps
            Chain  = $defs
            Suffix = $suffix
        }
    }
}

$dupes = $jobs | Group-Object Name | Where-Object Count -gt 1
if ($dupes) { throw "two entries produce the same dataset: $($dupes.Name -join ', ')" }

$targets = @($jobs | Where-Object { $n = $_.Name; $Only | Where-Object { $n -like $_ } })
if (-not $targets) { throw "no variant matched: $($Only -join ', ')" }

$built = 0; $skipped = 0
foreach ($job in $targets) {
    $name = $job.Name
    $chain = $job.Chain
    $suffix = $job.Suffix

    $src = Join-Path $dsRoot $job.Source
    $dst = Join-Path $dsRoot $name
    $yaml = Join-Path $dsRoot "$name.yaml"

    if (-not (Test-Path $src)) { throw "missing source dataset: $src" }
    if ((Test-Path $dst) -and -not $Force) {
        Write-Host "skip  $name (exists)"; $skipped++; continue
    }
    if ($WhatIf) {
        Write-Host "would build  $name = $($job.Source) + $($job.Steps -join ' + ')"
        continue
    }
    if (Test-Path $dst) { Remove-Item $dst -Recurse -Force }

    Write-Host "build $name  ($($job.Steps -join ' -> '))"
    $stage = Join-Path $dst ".stage"
    foreach ($split in "train", "val") {
        $srcImg = Join-Path $src "images\$split"
        if (-not (Test-Path $srcImg)) { continue }
        if (-not (Get-ChildItem $srcImg -File -EA SilentlyContinue)) { continue }

        $dstImg = Join-Path $dst "images\$split"
        $dstLbl = Join-Path $dst "labels\$split"

        # Each step reads the previous step's output. Only the last writes
        # into the dataset; the rest go to a staging folder that is removed,
        # so a half-finished chain cannot be mistaken for a dataset.
        $from = $srcImg
        for ($i = 0; $i -lt $chain.Count; $i++) {
            $to = if ($i -eq $chain.Count - 1) { $dstImg }
                  else { Join-Path $stage "$split-$i" }
            $g = $chain[$i]
            python (Join-Path $proc $g.script) $from $to @($g.args)
            if ($LASTEXITCODE -ne 0) { throw "$($g.script) failed on $from" }
            $from = $to
        }

        python (Join-Path $proc "CopyFilesWithSuffix.py") `
            (Join-Path $src "labels\$split") $dstLbl $suffix
        if ($LASTEXITCODE -ne 0) { throw "CopyFilesWithSuffix.py failed on $split" }

        # A suffix on one side and not the other gives a dataset with no
        # labels and a silent zero mAP, so the pairing is checked.
        $imgs = @(Get-ChildItem $dstImg -File | ForEach-Object { $_.BaseName })
        $lbls = @(Get-ChildItem $dstLbl -File -Filter *.txt | ForEach-Object { $_.BaseName })
        $unpaired = @(Compare-Object $imgs $lbls).Count
        if ($unpaired) { throw "$name/$split : $unpaired file(s) unpaired" }
        Write-Host ("  {0,-6} {1,4} images, {2,4} labels" -f $split, $imgs.Count, $lbls.Count)
    }
    if (Test-Path $stage) { Remove-Item $stage -Recurse -Force }

    # Same class list as the source, so only the paths differ between them.
    $srcYaml = Join-Path $dsRoot "$($job.Source).yaml"
    $raw = Get-Content $srcYaml -Raw
    # The key at the start of a line, not the first "names:" anywhere: a
    # header comment mentioning it would otherwise cut the block short.
    $at = [regex]::Match($raw, '(?m)^names:').Index
    if ($at -lt 0 -or -not [regex]::IsMatch($raw, '(?m)^names:')) {
        throw "$srcYaml has no names: block to copy"
    }
    $names = $raw.Substring($at)
    $describe = ($chain | ForEach-Object { $_.describe }) -join ", then "
    $header = @(
        "# $($job.Source) with: $describe."
        "# Built by BuildDatasets.ps1 from sweep.json. Images and labels"
        "# both carry the $suffix suffix, as the converted COCO sets do."
        "path: $name"
        "train: images/train"
        "val: images/val"
        "test:"
        ""
        ""
    ) -join "`n"
    # Set-Content -Encoding utf8 writes a BOM on PowerShell 5.1. Nothing else
    # in the repository has one, and it leaks into the first key of the yaml
    # for any reader that does not strip it.
    $full = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($yaml)
    # CRLF, because .gitattributes normalises to LF in the repository and
    # checks out CRLF here. Writing LF would leave every generated yaml
    # differing from its checked-out form, so each rebuild would show the
    # whole file as changed.
    $text = ($header + $names) -replace "`r`n", "`n" -replace "`n", "`r`n"
    [System.IO.File]::WriteAllText($full, $text,
        (New-Object System.Text.UTF8Encoding $false))
    Write-Host "  wrote $name.yaml"
    $built++
}

if (-not $WhatIf) { Write-Host "`n$built built, $skipped skipped" }
