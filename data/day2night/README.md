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
