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

    An entry may name its "splits". The default, train and val, is the layout
    of the captures; a converted COCO set is laid out as train2017 and
    val2017 and names both. A set built without a training split points its
    train key at the val split, because the validator requires the key to be
    there.

    Each split is checked on its own: one holding as many images and labels
    as the source's is left alone, an incomplete one is cleared and built
    again, and a dataset with every split complete is skipped. So a split
    added to an entry later is built without redoing the others.

        .\BuildDatasets.ps1                        build what is missing
        .\BuildDatasets.ps1 -Only real_nvg_white   one of them
        .\BuildDatasets.ps1 -Force                 rebuild even if complete
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
        $splits = if ($entry.splits) { @($entry.splits) } else { @("train", "val") }
        $jobs += [pscustomobject]@{
            Name   = "$($entry.source)$suffix"
            Source = $entry.source
            Steps  = $steps
            Chain  = $defs
            Suffix = $suffix
            Splits = $splits
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

    # A split is complete when it holds as many images and labels as the
    # source's. Only the incomplete ones are built, so a split added to an
    # entry later is built without redoing the others, and a split left
    # half-written by an interrupted run is built again from scratch.
    $todo = @()
    foreach ($split in $job.Splits) {
        $srcImg = Join-Path $src "images\$split"
        $nSrc = @(Get-ChildItem $srcImg -File -EA SilentlyContinue).Count
        if (-not $nSrc) { continue }
        $nSrcLbl = @(Get-ChildItem (Join-Path $src "labels\$split") -File -Filter *.txt -EA SilentlyContinue).Count
        $nImg = @(Get-ChildItem (Join-Path $dst "images\$split") -File -EA SilentlyContinue).Count
        $nLbl = @(Get-ChildItem (Join-Path $dst "labels\$split") -File -Filter *.txt -EA SilentlyContinue).Count
        if ($Force -or $nImg -ne $nSrc -or $nLbl -ne $nSrcLbl) { $todo += $split }
    }
    if (-not $todo) {
        Write-Host "skip  $name (complete)"; $skipped++; continue
    }
    if ($WhatIf) {
        Write-Host "would build  $name [$($todo -join ', ')] = $($job.Source) + $($job.Steps -join ' + ')"
        continue
    }
    if ($Force -and (Test-Path $dst)) { Remove-Item $dst -Recurse -Force }

    Write-Host "build $name [$($todo -join ', ')]  ($($job.Steps -join ' -> '))"
    $stage = Join-Path $dst ".stage"
    foreach ($split in $todo) {
        $srcImg = Join-Path $src "images\$split"

        $dstImg = Join-Path $dst "images\$split"
        $dstLbl = Join-Path $dst "labels\$split"
        foreach ($d in $dstImg, $dstLbl) {
            if (Test-Path $d) { Remove-Item $d -Recurse -Force }
        }

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
        # labels and a silent zero mAP, so the pairing is checked. A label
        # must always have its image. An image may lack a label only as often
        # as in the source: COCO's val2017 holds 48 images with no annotated
        # object and so no label file, which score as background, and every
        # set converted from it inherits them.
        $imgs = @(Get-ChildItem $dstImg -File | ForEach-Object { $_.BaseName })
        $lbls = @(Get-ChildItem $dstLbl -File -Filter *.txt | ForEach-Object { $_.BaseName })
        $diff = @(Compare-Object $imgs $lbls)
        $orphanLabels = @($diff | Where-Object SideIndicator -eq "=>").Count
        $bareImages = @($diff | Where-Object SideIndicator -eq "<=").Count
        $srcImgs = @(Get-ChildItem $srcImg -File).Count
        $srcLbls = @(Get-ChildItem (Join-Path $src "labels\$split") -File -Filter *.txt).Count
        $srcBare = $srcImgs - $srcLbls
        if ($orphanLabels) { throw "$name/$split : $orphanLabels label(s) without an image" }
        if ($bareImages -ne $srcBare) {
            throw "$name/$split : $bareImages image(s) without a label, the source has $srcBare"
        }
        $note = if ($bareImages) { ", $bareImages without objects as in the source" } else { "" }
        Write-Host ("  {0,-6} {1,4} images, {2,4} labels{3}" -f $split, $imgs.Count, $lbls.Count, $note)
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
    $valSplit = @($job.Splits | Where-Object { $_ -like "val*" })[0]
    $trainSplit = @($job.Splits | Where-Object { $_ -like "train*" })[0]
    if (-not $valSplit) { throw "$name builds no val split" }
    if (-not $trainSplit) { $trainSplit = $valSplit }
    $header = @(
        "# $($job.Source) with: $describe."
        "# Built by BuildDatasets.ps1 from sweep.json. Images and labels"
        "# both carry the $suffix suffix, as the converted COCO sets do."
        "path: $name"
        "train: images/$trainSplit"
        "val: images/$valSplit"
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
