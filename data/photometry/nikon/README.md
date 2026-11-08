# Nikon D500 illuminance measurement

Every number reported here comes from the scripts below, run in this order.

    SceneLux.py        src/Processing/SceneLux.py
    SceneLuxColor.py   src/Processing/SceneLuxColor.py
    SceneLuxResult.py  src/Processing/SceneLuxResult.py
    SceneLuxGain.py    src/Processing/SceneLuxGain.py
    BuildManifest.py   src/Processing/BuildManifest.py

## Result

Two scenes were measured, and every record here carries the one it belongs to
in its name.

    static   5.15e-04 lux +/- 10 %     the dark scene, 80 mm f/4 ISO 3200
    moving   1.98e-02 lux +/- 1.5 %    the vehicle scene, 38 mm f/4 ISO 51200

The steps below are written for the static measurement. The moving one runs
the same scripts against its own frames; what differs is listed under The
moving measurement near the end.

Its 1.5 % is a within-session figure and not comparable to the static 10 %,
which is widened by a disagreement between two reference sessions that the
moving set has no equivalent measurement of.

### The static measurement

Inside the run the error is 4.1 %: the drift fit is common to both signal
frames so its 3.6 % does not average away, and the 2.0 % frame-to-frame
scatter does. The two target calibration frames add 5.8 % of their own,
which scales the result directly, and those two in quadrature give 7.1 %.

The quoted 10 % is wider than that because the two reference nights do not
agree quite that well with each other, which the next section sets out.

### Two reference sessions

The reference colors were shot twice, s18 on 09-28 and s19 on 10-02, four
days apart, and both are kept: the references are calibrated from the two of
them together. Measured one against the other, at the same screen color:

| color | s18 `y_mid` | s19 `y_mid` | s19 / s18 |
| --- | --- | --- | --- |
| red | 0.015535 | 0.014822 | 0.95 |
| green | 0.103644 | 0.089183 | 0.86 |
| blue | 0.030290 | 0.027686 | 0.91 |
| white | 0.065730 | 0.070238 | 1.07 |

Five to fourteen percent apart, in both directions, with nothing changed
between them but the four days. That is the reproducibility of this measurement
and it is the reason the quoted uncertainty is 10 % rather than the 7.1 %
a single session would suggest.

An earlier session was discarded rather than averaged in. Its lighting was
not properly controlled and its frames have been removed, so nothing here
rests on it.

### The target color

The target has its own session, s20, two frames shot a minute after the
s19 references and under the same configuration. The color it needs is
set by the scene, and the value in use was refined against a measurement
until it matched:

| | R/G | B/G | against 0.541 / 1.743 |
| --- | --- | --- | --- |
| earlier value, (163, 85, 255) | 0.528 | 1.698 | -2.4 %, -2.6 % |
| **in use, (161, 79, 255)** | **0.534** | **1.755** | **-1.2 %, +0.7 %** |

Both were shot twenty seconds apart, to compare them under one TV state. The refined value halves the error on both ratios and its pair is
three times tighter, 5.8 % against 17.5 %, so it is the one kept and the
earlier frames were removed.

It is worth knowing that the color beats the model that produced it. For
(161, 79, 255) the matrix predicts R/G 0.500 where the camera measures
0.534, a 6.9 % error in red, and the matrix's own best guess would have
landed further from the scene. The value came from refining a measurement,
not from solving the matrix, which is what the refine step is for.

### Against the earlier figures

    4.09e-04      the figure the thesis carries, calibrated near white
    2.94e-04      to 5.03e-04, the range from whitish calibrations
    5.15e-04      this measurement

26 % above the figure the thesis carries, and the reason is in the table
below: white gives 2.91e-04 where the scene's own color gives 5.15e-04. The
old figure was low because it was calibrated near white, which is what the
color work exists to fix.

## The calibration illuminant has to match the scene

`y_mid` is the raw level a metered-correct mid gray reaches. It is not a
constant of the body. The camera's meter integrates all the light reaching
it, while these scripts sample the green photosites only, so the two disagree
by however much the illuminant's spectrum departs from the meter's weighting.

Six colors, same card, nothing changed between them but the color on the
screen. The references are four frames each, two from each session; the
target is the pair in s20.

| color | screen RGB | measured R/G | measured B/G | `y_mid` | scene lux it gives |
| --- | --- | --- | --- | --- | --- |
| black | (0, 0, 0) | 0.432 | 1.156 | n/a | reference only |
| blue | (0, 0, 255) | 0.087 | 2.613 | 0.028988 | 6.828e-04 |
| green | (0, 255, 0) | 0.161 | 0.264 | 0.096413 | 2.053e-04 |
| red | (255, 0, 0) | 3.523 | 0.171 | 0.015178 | 1.304e-03 |
| white | (255, 255, 255) | 0.437 | 0.671 | 0.067984 | 2.911e-04 |
| **target** | **(161, 79, 255)** | **0.534** | **1.755** | **0.038447** | **5.148e-04** |

`y_mid` spans a factor of 6.35 across the colors that carry light, red to
green, and the illuminance with it. Nothing about the camera changed; only
what it was looking at.

Black carries no usable signal and is not calibrated against. It is captured
to measure what the panel emits with all three channels at zero, which every
other reference frame carries on top of what was asked for. See step 1.

The target color is not a guess. The measured scene is a laptop screen in an
otherwise dark room, and subtracting the noise frames from the signal frames
per Bayer channel, over the same four ROI boxes everything else is sampled
with, gives its net response: R 0.000290, G 0.000536, B 0.000934, or 4.6, 8.6
and 14.9 DN. That green figure is the same 8.6 DN the result table reports as
`delta`, which is the check that the derivation and the measurement sample
the same thing. The ratios are R/G 0.541 and B/G 1.743.

What none of this touches is the night vision gain. It is a ratio of two
luminances computed with the same `y_mid`, so the calibration cancels exactly
and the figures in step 7 are the same under any of them.

## Before running anything

The frames are not versioned. Fetch them and place them here:

    bg_noise/                39 frames, lens covered, s02 and s21
    dark_card/                6 frames, the measurements themselves
    direct_screen_light/     34 frames, the color references and the targets
    trough_nvg/              11 frames, the gain sweep

Every command below runs from the repository root, with these two variables
set:

    $S = "src\Processing"
    $N = "data\photometry\nikon"

Then check the set is complete and unmodified:

    Import-Csv $N\MANIFEST.csv | ForEach-Object {
        $p = Join-Path $N (Join-Path $_.folder $_.file)
        if (-not (Test-Path $p)) { "missing: $p" }
        elseif ((Get-FileHash $p -Algorithm SHA256).Hash -ne $_.sha256.ToUpper()) {
            "changed: $p" }
    }

Anything printed is a frame that is absent or not the one these results were
computed from. Silence means the set is complete.

Nothing rendered from the frames is versioned either. The overlays and the two
plots are written into this folder when the steps below run, and are there to
be looked at rather than committed.

PowerShell does not expand wildcards for native commands, so paths containing
one are resolved with `Get-ChildItem` before being passed. The same applies to
decimal formatting: on a German locale `"{0:E4}" -f $x` produces a comma, which
Python will not parse, so step 7 formats with `InvariantCulture`.

## 0. Manifest

Rebuild only if the frame set changes. Everything in it is read from the
frames, so it is safe to regenerate at any time.

    python $S\BuildManifest.py $N

    reads    */*.NEF
    writes   MANIFEST.csv

## 1. Scene color

`y_mid` moves with the illuminant, by a factor of 6.67 across the colors in
the table above, so the calibration has to be shot under light of the scene's
own color. This derives that color from the scene rather than choosing it by
eye.

    python $S\SceneLuxColor.py estimate `
        --signal $N\dark_card\s02_*.NEF --noise $N\bg_noise\s02_*.NEF `
        --red   $N\direct_screen_light\s1[89]_*_calibRED_*.NEF `
        --green $N\direct_screen_light\s1[89]_*_calibGREEN_*.NEF `
        --blue  $N\direct_screen_light\s1[89]_*_calibBLUE_*.NEF `
        --white $N\direct_screen_light\s1[89]_*_calibWHITE_*.NEF `
        --black $N\direct_screen_light\s1[89]_*_calibBLACK_*.NEF `
        --record $N\color_static.json

    reads    2 scene frames, 7 dark frames, 20 display reference frames,
             four per color across the two sessions
    writes   color_static.json
    gives    target R/G 0.541, B/G 1.743
             suggested screen RGB (171, 83, 255), which is not the
             value used; see The target color above

The three primaries give the camera's response to each, as the columns of a
3x3 matrix; the scene's net response, signal minus dark, is the target; and
solving the one against the other gives the drive to display.

White and black are not primaries and are not part of that solve. Three
primaries already span the space, so the matrix is determined without them.

White is captured because it is the only frame that can show the model to be
wrong: an additive display driven at full white produces exactly what its
primaries produce together. This TV falls 7.5 % short of that, but uniformly
across all three channels, which cancels, since the solve matches the
direction of a response and lets exposure carry the magnitude. What would not
cancel is the part left after the uniform factor divides out, and that is
within 2 %.

Black is captured because a backlit panel still emits with every channel at
zero, and every other reference frame carries that leak on top of what was
asked for. Left in, it inflates all three matrix columns by the same vector,
which the diagonal barely notices but which can exceed the off-diagonal terms
outright. Here it measures 0.3 to 0.5 % of white and moves the suggestion by
one code value, so on this display it is a small correction; that it is small
is a measurement, not an assumption. Omit `--black` only on a screen with no
backlight, OLED for instance, where a black pixel is off and the frame would
hold nothing but sensor noise.

Without it the white deficit is ambiguous, because a leak of k makes white
fall short by exactly 2k and a dimming backlight does the same thing. Inferred
that way the leak came out twelve times its measured size, which is the
argument for the capture.

Display the color, shoot the card under it, and check what the camera
actually sees against the target:

    python $S\SceneLuxColor.py refine --record $N\color_static.json `
        --verify $N\direct_screen_light\s20_01_calibSTATIC_*.NEF `
        --shot-at 161 79 255

    reads    2 frames shot under the displayed color
    writes   color_static.json, appending the round to its history
    gives    measured R/G 0.534, B/G 1.755,
             which is -1.2 % and +0.7 % against the target,
             correcting to RGB (163, 80, 255)

`--shot-at` is what the frames were actually displayed under and is not
optional in practice: the correction is measured relative to that drive, so
letting the script assume the last suggestion silently corrects from the
wrong place.

Both misses are inside the 3 % the script treats as close enough, so the
value in use stands and the correction it offers is not acted on. Shooting
(163, 80, 255) would chase a difference smaller than the frame-to-frame
scatter of the pair that measured it.

## 2. Calibration

Only the target calibration is kept, because it is the only one the result
reads. Every frame is 80 mm f/4 ISO 3200 in aperture priority, matching the
measurement.

    $files = (Get-ChildItem $N\direct_screen_light\s20_01_calibSTATIC_*.NEF).FullName
    python $S\SceneLux.py --rois --y-mid 0.04837403318646708 $files `
        --record $N\calibration_static.json --overlay-dir $N\overlay

The `--y-mid` passed here only scales the reported lux, and the `y_card`
values are what the step exists to produce.

    reads    2 target frames
    writes   calibration_static.json
    gives    y_mid 0.038447

Black is absent on purpose: it carries no signal to calibrate against, and
its only job is the leak measurement in step 1.

### The reference colors

The four reference colors in the table above are calibrated the same way, and
their records are not kept. Nothing downstream reads them; their whole output
is the `y_mid` column of that table, which is written down there. Anyone who
wants the records back can run:

    foreach ($c in "RED", "GREEN", "BLUE", "WHITE") {
        $files = (Get-ChildItem "$N\direct_screen_light\s1?_*_calib$($c)_*.NEF").FullName
        python $S\SceneLux.py --rois --y-mid 0.04837403318646708 $files `
            --record "$N\calibration_ref_$($c.ToLower()).json" --overlay-dir $N\overlay
    }

    reads    4 frames per color, 16 in total
    gives    y_mid 0.015178 red, 0.028988 blue, 0.067984 white, 0.096413 green

They are named `ref` rather than `static`: the frames are s18 and s19, and
the measured scene is s02, a different week again, so nothing ties them to
the static measurement beyond being on the same display.

Their `y_card` spreads are wider than a single session's, 4.9 % red, 11.0 %
white, 17.8 % green, 21.8 % blue, because four frames across two sessions
four days apart include a difference that two frames seconds apart do not.
That is the honest figure for a reference color and it is why the target,
which does set the result, is kept to one sitting.

## 3 to 5. Noise, signal and result

Run against the target calibration only.

    $c = (Get-Content $N\calibration_static.json | ConvertFrom-Json).captures
    $yMid = ($c.y_card | Measure-Object -Average).Average

    $cov = (Get-ChildItem $N\bg_noise\s02_*.NEF).FullName
    python $S\SceneLux.py --rois --y-mid $yMid $cov `
        --record $N\noise_static.json --overlay-dir $N\overlay

    $clr = (Get-ChildItem $N\dark_card\s02_*.NEF).FullName
    python $S\SceneLux.py --rois --y-mid $yMid $clr `
        --record $N\signal_static.json --overlay-dir $N\overlay

    python $S\SceneLuxResult.py --dark $N\noise_static.json `
        --measure $N\signal_static.json --label static `
        --csv $N\result_table_static.csv --out $N\result_static.json `
        --plot $N\noise_model_static.png

    reads    7 lens-covered and 2 lens-clear frames
    writes   noise_static.json, signal_static.json, result_static.json,
             result_table_static.csv, noise_model_static.png
    gives    5.148e-04 lux, +/- 2.10e-05 statistical

Dark current rises while the sensor works, so one averaged dark frame only
describes the moment it was taken. The covered frames sit either side of the
measurement and a straight line through them in capture time gives each signal
frame the offset for its own timestamp, taken from `exif.datetime`.

Over this run the drift is +0.17 DN/min with a residual scatter of 0.81 DN
against a signal of 8.4 and 8.8 DN. The fit standard error is smallest at the
centroid of the covered frames and grows away from it, so `dark_model_se_dn`
runs 0.53 DN at the first frame, down to 0.31 DN at the signal frames, and
back up to 0.50 DN at the last. The measurements sit almost exactly at the
centroid, which is what bracketing buys.

The subtraction itself is independent of the calibration. It returns the same
8.432 and 8.774 DN whichever color was used; only the scaling to lux differs.

## 6. Through the night vision device

The gain control was stepped from its maximum down to its minimum and back,
which the naming records as g1 to g4 and then g1 again.

    $files = (Get-ChildItem $N\trough_nvg\s05_0*.NEF).FullName
    python $S\SceneLux.py --rois $N\rois\rois_nvg.json --y-mid $yMid `
        $files --overlay-dir $N\overlay --record $N\nvg_s05_record.json

This `y_mid` and the scene luminance in step 7 have to come from the same
calibration. They cancel only as a pair, and mismatching them returns a wrong
gain rather than an error.

    reads    s05_01_g1 x4, s05_02_g2 x2, s05_03_g3 x2, s05_04_g4 x2, s05_05_g1 x1
    writes   nvg_s05_record.json, eleven overlays

## 7. Gain

The screen emits rather than reflects, so the quantity to compare is
luminance. SceneLux reports the illuminance that would fall on a card of
reflectance rho to produce the level it measured, and recovering the luminance
from it cancels rho, so the assumed reflectance does not affect the gain. The
script does that per frame and divides by the scene luminance measured without
the device.

    $lux = (Get-Content $N\result_static.json | ConvertFrom-Json).result.lux_mean
    $L = ($lux * 0.178 / [Math]::PI).ToString("E4", [cultureinfo]::InvariantCulture)

    python $S\SceneLuxGain.py $N\nvg_s05_record.json `
        --scene-luminance $L --csv $N\gain_table.csv --plot $N\gain_model.png

    reads    nvg_s05_record.json
    writes   gain_table.csv, one row per frame
             gain_model.png, the same rows plotted in capture order
    gives    7008, 6381, 6833, 6817 at g1 maximum
             1396, 1372 at g2
             423, 422 at g3
             199, 196 at g4 minimum
             6781 at g1 returned

The scene luminance passed here is 2.917e-05 cd/m2, which is 5.148e-04 lux on
a card of reflectance 0.178.

Steps 6 and 7 do not depend on the calibration and do not need rerunning when
one changes. Writing the ratio out, everything the calibration contributes
cancels:

    gain = (N^2 y / t) through the device / (N^2 y / t) of the scene

leaving only the f-numbers, the exposure times and the two measured levels.
`y_mid`, rho, K, the ISO and pi all drop out. Running the red calibration
through the scripts instead, where `y_mid` is 2.53 times smaller and the scene
comes out at a different lux entirely, returns the same 7007 down to 196 and
the same factor of 35.8.

This makes the gain the firmest number here. The illuminance carries the
calibration spread; the gain carries none of it. The factor of 6.67 that
separates the calibrations, and which is why the calibration color has to
be matched at all, has no effect here.

The control was turned from maximum to minimum and back, a range of 35.8x,
and the returned maximum reproduces the first to within the frame-to-frame
scatter of the four maximum frames, which is itself about 4 %.

This is a floor, not the device's datasheet gain. Coupling between eyepiece
and camera loses light to vignetting and exit pupil mismatch, and a datasheet
figure in cd/m2 per lux refers to illuminance at the photocathode, which the
objective concentrates first.

## Why the calibration is at 80 mm f/4

The equation accounts for aperture and exposure explicitly, so their absolute
values do not matter, but anything it does not model, such as lens
transmission and vignetting, only cancels when the calibration is shot in the
same optical configuration as the measurement. The signal frames are 80 mm f/4
ISO 3200, so the calibration is too.

The calibration also has to be metered with room to move. In shutter priority
at 80 mm the lens is already wide open at f/4 and cannot compensate, so
aperture priority is used and the camera varies the shutter instead.

## Regions

Every direct frame, calibration, noise and signal, uses SceneLux's built-in
default rectangles, which is what a bare `--rois` selects, except the noise
and signal frames of the moving scene.

`rois_moving.json` holds the defaults moved 356 px to the right (0.063571 of
frame width), for the s21 noise and signal frames only. The camera was not
put back on the same framing for that scene: the reticle sits about 356 px
further right in the s21 frames than in the s23 calibration, which the
defaults still fit. On the s21 frames the defaults lay on the reticle rings,
the left pair on the outer ring and the right pair on the inner one, and the
bright lines raised the card level; the moved boxes sit on plain card between
the rings, in the same place relative to the reticle as the defaults in the
calibration. Measured on the defaults, the moving scene came out at
3.79e-02 lux.

`rois_nvg.json` is specific to session s05. Through the tube the card fills only
the middle of a much wider field and sits off-center, so the frame-centered
defaults do not apply. The patches sit diagonally at 0.095 of frame width from
the reticle center (0.4770, 0.4657), clearing the outer ring at 0.055 by 0.020
while keeping the same box size, and so the same pixel count, as the direct
frames. A different session will need them re-placed.

## Files

| File | Written by |
| --- | --- |
| `MANIFEST.csv` | step 0, the frames to place here with sizes and checksums |
| `color_static.json` | step 1, the derived scene color and the match history |
| `calibration_static.json` | step 2, the target color, the only one kept |
| `noise_static.json` | step 3, seven lens-covered frames |
| `signal_static.json` | step 4, two lens-clear frames |
| `result_static.json` | step 5, full log including the drift model |
| `result_table_static.csv` | step 5, every frame, noise and signal |
| `noise_model_static.png` | step 5, drift plot, not versioned |
| `nvg_s05_record.json` | step 6, the gain sweep |
| `gain_table.csv` | step 7, per-frame luminance gain |
| `gain_model.png` | step 7, the gain sweep plotted for checking, not versioned |
| `rois/` | input, the region definition for step 6 |
| `overlay/` | ROI overlays written alongside each record, not versioned |
| `*_moving.json`, `*_moving.csv` | the vehicle scene, the same steps against its own frames |

Naming is `<session>_<series>_<state>_<exposure>_<HHMMSS>.NEF`, with the
session number zero-padded to two digits. Unpadded, `s2` sorts between `s19`
and `s20` in every directory listing, which puts the earliest session in the
middle of the set; `s02` sorts where it was shot.

Both `bg_noise/` and `dark_card/` hold two measurements now, so every command
above globs on the session rather than on the folder.

## The moving measurement

Same scripts, same order, different frames. Every frame in it is 38 mm f/4
ISO 51200, the scene in manual at 1/3 s and the calibration in aperture
priority.

RGB (203, 201, 207) was found by shooting the card, measuring how far its
ratios fell from the scene's, and stepping the drive until they matched; the
matrix was not solved for it, because this display does not mix additively
enough for the solve to be worth anything.

    python $S\SceneLuxColor.py estimate `
        --signal $N\dark_card\s21_*.NEF --noise $N\bg_noise\s21_*.NEF `
        --red   $N\direct_screen_light\s21_07_calibRED_*.NEF `
        --green $N\direct_screen_light\s21_06_calibGREEN_*.NEF `
        --blue  $N\direct_screen_light\s21_04_calibBLUE_*.NEF `
        --white $N\direct_screen_light\s21_08_calibWHITE_*.NEF `
        --black $N\direct_screen_light\s21_05_calibBLACK_*.NEF `
        --record $N\color_moving.json

    reads    4 scene frames, 32 dark frames, 10 display reference frames
    writes   color_moving.json
    gives    target R/G 0.397, B/G 0.781
             chromatic component 3.9 %, past the 3 % the model tolerates,
             so its suggestion of (239, 238, 255) is unsound and unused

That 3.9 % is the measurement behind the sentence above, and it is the one
place the two scenes differ in kind rather than in numbers: the static
display passes the same check under 2 %.

    python $S\SceneLuxColor.py refine --record $N\color_moving.json `
        --verify $N\direct_screen_light\s23_02_calibMOVING_*.NEF `
        --shot-at 203 201 207

    reads    2 frames shot under the displayed color
    writes   color_moving.json, appending the round to its history
    gives    measured R/G 0.391, B/G 0.797,
             which is -1.5 % and +2.1 % against the target

Both steps above ran on the default rectangles, which on the s21 scene frames
lie on the reticle (see Regions). Run with `--rois rois\rois_moving.json`,
the estimate gives a target of R/G 0.396, B/G 0.753, against which the
displayed color measures -1.3 % and +5.8 %. `color_moving.json` still holds
the run on the defaults.

Then the calibration, the two scene records and the result:

    python $S\SceneLux.py --rois --y-mid 0.04837403318646708 `
        (Get-ChildItem $N\direct_screen_light\s23_02_calibMOVING_*.NEF).FullName `
        --record $N\calibration_moving.json --overlay-dir $N\overlay

    $c = (Get-Content $N\calibration_moving.json | ConvertFrom-Json).captures
    $yMid = ($c.y_card | Measure-Object -Average).Average

    python $S\SceneLux.py --rois $N\rois\rois_moving.json --y-mid $yMid `
        (Get-ChildItem $N\bg_noise\s21_*.NEF).FullName `
        --record $N\noise_moving.json --overlay-dir $N\overlay

    python $S\SceneLux.py --rois $N\rois\rois_moving.json --y-mid $yMid `
        (Get-ChildItem $N\dark_card\s21_*.NEF).FullName `
        --record $N\signal_moving.json --overlay-dir $N\overlay

    python $S\SceneLuxResult.py --dark $N\noise_moving.json `
        --measure $N\signal_moving.json --label moving `
        --csv $N\result_table_moving.csv --out $N\result_moving.json `
        --plot $N\noise_model_moving.png

    reads    2 calibration frames, 32 lens-covered and 4 lens-clear
    writes   calibration_moving.json, noise_moving.json, signal_moving.json,
             result_moving.json, result_table_moving.csv,
             noise_model_moving.png
    gives    y_mid 0.078478, 1.978e-02 lux +/- 2.97e-04

The calibration took three attempts: a 40 mm pair against a 38 mm scene,
which put `y_mid` 6.4 % low and the illuminance 6.0 % high at 4.038e-02, then
a 38 mm pair under poor light control that measured 7 to 11 % off target,
then the pair in use. Neither of the first two is kept.

## Sessions

Numbers run in capture order, so a higher number was shot later. They are
assigned here and mean nothing outside this repository, so the gaps are not
missing data: more was shot than these results need, and what the steps
below read is listed and placed in this folder. The rest belongs to the same
capture set and can be fetched the same way if anyone wants to look.

| session | what it is | when | frames kept |
| --- | --- | --- | --- |
| s02 | the static scene, lens covered and clear | 09-26 04:02 | yes |
| s05 | the gain sweep through the device | 09-26 22:44 | yes |
| s18 | display color references, first pass | 09-28 20:58 | yes |
| s19 | display color references, second pass | 10-02 01:07 | yes |
| s20 | the static target color | 10-02 01:11 | yes |
| s21 | the moving scene and its color references | 10-02 04:49, 05:19 | yes |
| s23 | the moving target color | 10-03 21:09 | yes |

A target color and a set of color references are different captures doing
different jobs, so they do not share a number. The references characterize
the display; the target is the one calibration a result is computed from.
s20 and s23 are those two targets, and each is read by exactly one record.

s18 and s19 are the same reference set shot twice, four days apart. The
second pass exists because the first alone could not show how well the set
repeats, and the answer, 5 to 14 %, is what widens the quoted uncertainty.

s21 is one continuous run, the scene at 04:49 and its references half an
hour later.

s22 is absent and s23 starts at `_02`: both were earlier attempts at the
moving target and their frames were discarded. What they measured is in the
section above; it is not in any record, because regenerating
`color_moving.json` from the frames that are here dropped their rounds.

The state token says what the camera was pointed at, so `calibSTATIC` and
`calibMOVING` are the two targets. An earlier `calibSCENENEW` and `calibSCENE`
meant those and are gone, because with two scenes neither name said which.

Every frame any step reads is in this folder, and every record here was
written by one of those steps. Nothing is hand-edited.
