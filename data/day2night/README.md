# Day to night

Measurements of real night vision captures and of the synthetic conversions
meant to imitate them, used to tune `GenerateNVG.py` against numbers rather
than by eye.

    AnalyzeNVG.py         src/Processing/AnalyzeNVG.py
    GenerateCrops.py      src/Processing/GenerateCrops.py
    GenerateNVG.py        src/Processing/GenerateNVG.py
    GenerateNVGLegacy.py  src/Processing/GenerateNVGLegacy.py

`GenerateNVGLegacy.py` is frozen and produced every fine-tuning dataset in
this project. `GenerateNVG.py` is the current one and differs in where it
puts grain: the legacy curve suppresses grain in the shadows, which the
measurements here showed to be backwards, so the current one peaks it at
0.15 instead. Measurements of a legacy-generated set should be read against
the legacy curve, not the current one.

## The images are not versioned

They are copied in from the datasets outside this repository and placed under
this folder. Every image format is ignored here, as under `data/photometry`,
so what stays in git is the measurement trail: the per-image table and
whatever is plotted from it.

Beware that a file placed here will not show up in `git status` at all. That
is deliberate, but it means an image that failed to copy looks exactly like
one that copied fine. The row count the script reports is the check.

Both sets have to be cropped the same way before they are comparable.
`GenerateCrops.py` finds the circular field and trims the outer tenth of the
radius to drop the vignette, so a cropped capture has already lost the
steepest part of its falloff. Measuring a cropped real set against an
uncropped synthetic one compares two different things, and the vignette and
noise columns are where it shows.

## Running it

One set per run, appended to one file, so the rows carry a `group` column to
plot or tabulate against each other.

    cd <the folder holding datasets/>
    $A = "FODANVI_Scripts\src\Processing\AnalyzeNVG.py"
    $OUT = "FODANVI_Scripts\data\day2night\nvg_stats.csv"

    python $A datasets\real_nvg\images\val\*.jpg `
        --label real --csv $OUT

    python $A datasets\coco_nvg_green_clean\images\train2017\*.jpg `
        --label green_clean --csv $OUT --append

The script globs its own arguments, so a bare wildcard works and
`Get-ChildItem` is not needed. That cuts both ways: the COCO folders hold
tens of thousands of images and a bare wildcard takes them all. Point it at a
subset unless the whole set is wanted.

`--append` adds to an existing file and creates one with a header if it is
absent, saying which it did. `--per-image` prints every row instead of the
first and last five; the csv always holds all of them.

## The groups in the csv

The references are phone photographs only. One video frame per phosphor,
taken with another camera, was moved to `excluded_other_camera/`, its rows
dropped from the csv and both configs regenerated from the remaining five.
The `coco_nvg2_*` sets were built before that, from six references each, and
the whole-frame and region figures quoted below are from those six.

Two families of config, each measured whole on one set:

| config | measured on | compares against |
| --- | --- | --- |
| `nvg_config_selected_green.json` | `real_green`, 5 phone photographs | the hand-tuned green, tuned on the same images |
| `nvg_config_selected_white.json` | `real_white`, 5 phone photographs | the hand-tuned white; the only white source there is |
| `nvg_config_setup_green.json` | `real_dataset`, the 66 evaluation captures | selected green: same device, other camera path |

Selected against hand-tuned isolates tuning by eye against tuning by script,
on the same references. Selected green against setup green isolates the
camera behind the eyepiece. There is no setup white, as the capture pipeline
was only run with the green device. `BuildNvg2Datasets.py` reads the
selected pair.

    cd data/day2night
    $A = "../../src/Processing/AnalyzeNVG.py"
    python $A "real_green/*" --config nvg_config_selected_green.json --config-color green --no-plot
    python $A "real_white/*" --config nvg_config_selected_white.json --config-color white --no-plot
    python $A "../datasets/real_nvg/images/val/*.jpg" --label real_dataset `
        --config nvg_config_setup_green.json --config-color green --no-plot

Two values are not usable as written. Selected white grain is NaN: it is read
from the band below 0.3, where none of the five white photographs has enough
pixels. Setup green vignette is 1.0, the lower bound of the solver: the
evaluation captures read 0.956 edge over center, flatter than any setting
produces.

Eleven of them, 1676 rows. The `real_*` groups are the measurements
everything else is scored against; the rest are conversions of COCO, sampled
at 200 images each with `--sample 200`.

| group | n | what it is |
| --- | --- | --- |
| `real_green` | 5 | green phosphor photographs, the green target |
| `real_white` | 5 | white phosphor photographs, the white target |
| `real_dataset` | 66 | the captures the models are scored on |
| `coco_green_clean`, `coco_green_noisy` | 200 each | legacy conversion, `GenerateNVGLegacy.py` |
| `coco_white_clean`, `coco_white_noisy` | 200 each | the same, white |
| `coco_nvg2_green`, `coco_nvg2_green_clean` | 200 each | current conversion, `GenerateNVG.py` |
| `coco_nvg2_white`, `coco_nvg2_white_clean` | 200 each | the same, white |

The `nvg2` groups are the corrected sets, built by `BuildNvg2Datasets.py` in
the repository root from the multipliers in `nvg_config_*.json`. Measured
against their target the legacy green conversion carried almost no blue,
`bg` 0.018 against 0.119 on the clean set and 0.084 on the noisy one, because
the hardcoded `blue_multiplier` is 0.005; the current sets land at 0.115.
Legacy white was closer to begin with and its `rg` moved from 0.555 to 0.438
against a target of 0.441.

## The measurement region

Every statistic here except `edge_over_center` is taken inside a centred disc
of half the inscribed radius, set by `REGION_FRAC` in `AnalyzeNVG.py`. Before
that it was the whole frame, which measured the vignette as much as the thing
being asked about, and did so differently on each side: the references are
square crops of the circular field while the conversions are 4:3 and 3:2 COCO
frames. What the whole frame cost, on the references:

| | green whole | green region | white whole | white region |
| --- | --- | --- | --- | --- |
| `luma_mean` | 83.3 | 96.6 | 126.4 | 150.3 |
| `luma_sd` | 21.6 | 18.0 | 37.4 | 26.3 |
| `bg` | 0.119 | 0.136 | 0.910 | 0.901 |
| `rg` | 0.012 | 0.012 | 0.441 | 0.483 |

The mean reads low because the dark annulus is averaged in, and the spread
reads high because the falloff gradient itself counts as contrast, which then
propagates into `contrast_alpha`. Channel ratios barely move, a quotient of
two means being scale invariant under a vignette, which is why the colour
figures above survive the change and the tone ones do not. Green `bg` is the
exception: that annulus is noise dominated and biased it down 14 per cent.

`edge_over_center` is deliberately still whole frame, that being the one
measurement whose subject is the falloff. Its radius is now normalised by the
inscribed circle rather than the corner, because on a 4:3 conversion the old
`rad >= 0.8` band reached into corners outside any circular field while on a
square capture it was the outer fifth of the field, so the two were never the
same annulus. On the green references it reads 0.816 where it read 0.642, and
`vignette_intensity` falls from 1.6 to 1.09 with it.

Two further things are worth knowing when reading these numbers.

`contrast_alpha` and `contrast_beta` are still only a starting point.
`GenerateNVG` multiplies the vignette in after `convertScaleAbs`, and across
the region that mask averages about 0.93, so the levels `build_config`
predicts come out a few per cent dark. Over a whole frame that error was 51
per cent for green and 38 for white, which is what the region fixes. Hitting
the target exactly still wants the pair solved against the pipeline, as the
`TONE` note in `BuildNvg2Datasets.py` does.

What is corrected nowhere is the vignette's shape. `GenerateNVG` builds it
from two 1-D Gaussians scaled to the frame's own width and height, which is
elliptical on a non-square frame where the device's is circular. That is in
the conversion rather than the measurement, so neither the region nor the
normalisation addresses it.

`real_dataset` and `real_green` disagree about color, `rg` 0.236 against
0.012 and `bg` 0.010 against 0.119, although both are green phosphor
captures. The conversions are tuned to `real_green`, so whichever of the two
describes the imagery the models are actually scored on is an open question
and not one these measurements answer.

## What it measures

`GenerateNVG` builds its output from one grayscale image, tinted by a fixed
triple of channel multipliers, so every pixel carries the same R:G:B ratio
until something clips. Two numbers therefore describe the color of a device,
and they can be read off a capture and used as multipliers directly. The
`rg_sd` and `bg_sd` columns say whether that single-tint model holds: above
about 0.15 the ratio is not constant across the frame and no setting of the
multipliers will reproduce the image.

The rest map onto the other `NVGConfig` fields:

| column | tunes |
| --- | --- |
| `rg`, `bg` | `red_multiplier`, `green_multiplier`, `blue_multiplier` |
| `luma_mean` | `contrast_beta` |
| `luma_sd` | `contrast_alpha` |
| `p01`, `p50`, `p99`, `clip_low`, `clip_high` | whether alpha and beta push the range off either end |
| `bright_235` | `bloom_threshold`, `bloom_intensity` |
| `noise_sd`, `noise_dark`, `noise_mid`, `noise_bright` | `noise_intensity`, and which curve places it |
| `grain_px` | `grain_size` |
| `edge_over_center` | `vignette_intensity` |

## Files

| File | Written by |
| --- | --- |
| `nvg_stats.csv` | `AnalyzeNVG.py`, one row per image, one `group` per run |
