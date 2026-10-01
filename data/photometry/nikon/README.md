# Nikon D500 illuminance measurement

Every number reported here comes from the scripts below, run in this order.
Nothing was produced by hand.

    SceneLux.py        src/Processing/SceneLux.py
    SceneLuxColor.py   src/Processing/SceneLuxColor.py
    SceneLuxResult.py  src/Processing/SceneLuxResult.py
    SceneLuxGain.py    src/Processing/SceneLuxGain.py
    BuildManifest.py   src/Processing/BuildManifest.py

## Result

    scene illuminance   5.15e-04 lux +/- 10 %

Inside the run the error is 4.1 %: the drift fit is common to both signal
frames so its 3.6 % does not average away, and the 2.0 % frame-to-frame
scatter does. The two target calibration frames add 5.8 % of their own,
which scales the result directly, and those two in quadrature give 7.1 %.

The quoted 10 % is wider than that because the two sessions do not agree
quite that well with each other, which the next section sets out.

### Two sessions

Both are kept, and the reference colors are calibrated from the two of them
together. Measured one session against the other, at the same screen color:

| color | s19 `y_mid` | s20 `y_mid` | s20 / s19 |
| --- | --- | --- | --- |
| red | 0.015535 | 0.014822 | 0.95 |
| green | 0.103644 | 0.089183 | 0.86 |
| blue | 0.030290 | 0.027686 | 0.91 |
| white | 0.065730 | 0.070238 | 1.07 |

Five to fourteen percent apart, in both directions, with nothing changed
between them but the night. That is the reproducibility of this measurement
and it is the reason the quoted uncertainty is 10 % rather than the 7.1 %
a single session would suggest.

An earlier session was discarded rather than averaged in. Its lighting was
not properly controlled and its frames have been removed, so nothing here
rests on it.

### The target color

The target is calibrated from s20 alone. The color it needs is set by the
scene, and the value in use was refined against a measurement until it
matched:

| | R/G | B/G | against 0.541 / 1.743 |
| --- | --- | --- | --- |
| earlier value, (163, 85, 255) | 0.528 | 1.698 | -2.4 %, -2.6 % |
| **in use, (161, 79, 255)** | **0.534** | **1.755** | **-1.2 %, +0.7 %** |

Both were shot in s20, twenty seconds apart, to compare them under one TV
state. The refined value halves the error on both ratios and its pair is
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
target is the two from s20.

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
and the figures in step 8 are the same under any of them.

## Before running anything

The frames are not versioned. Fetch them and place them here:

    bg_noise/                 7 frames, lens covered
    dark_card/                2 frames, the measurement itself
    direct_screen_light/     22 frames, two sessions of color references
    trough_nvg/              11 frames

Set the variable every command below uses:

    $S = "..\..\..\src\Processing"

Then check the set is complete and unmodified:

    Import-Csv MANIFEST.csv | ForEach-Object {
        $p = Join-Path $_.folder $_.file
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
Python will not parse, so step 8 formats with `InvariantCulture`.

## 0. Manifest

Rebuild only if the frame set changes. Everything in it is read from the
frames, so it is safe to regenerate at any time.

    python $S\BuildManifest.py .

    reads    */*.NEF
    writes   MANIFEST.csv

## 1. Scene color

`y_mid` moves with the illuminant, by a factor of 6.67 across the colors in
the table above, so the calibration has to be shot under light of the scene's
own color. This derives that color from the scene rather than choosing it by
eye.

    python $S\SceneLuxColor.py estimate `
        --signal dark_card\*.NEF --noise bg_noise\*.NEF `
        --red   direct_screen_light\s19_03_calibRED_*.NEF `
                direct_screen_light\s20_04_calibRED_*.NEF `
        --green direct_screen_light\s19_06_calibGREEN_*.NEF `
                direct_screen_light\s20_03_calibGREEN_*.NEF `
        --blue  direct_screen_light\s19_04_calibBLUE_*.NEF `
                direct_screen_light\s20_02_calibBLUE_*.NEF `
        --white direct_screen_light\s19_05_calibWHITE_*.NEF `
                direct_screen_light\s20_05_calibWHITE_*.NEF `
        --black direct_screen_light\s19_01_calibBLACK_*.NEF `
                direct_screen_light\s20_01_calibBLACK_*.NEF `
        --record color_scene.json

    reads    2 scene frames, 7 dark frames, 20 display reference frames,
             four per color across the two sessions
    writes   color_scene.json
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

    python $S\SceneLuxColor.py refine --record color_scene.json `
        --verify direct_screen_light\s20_07_calibSCENENEW_*.NEF `
        --shot-at 161 79 255

    reads    2 frames shot under the displayed color
    writes   color_scene.json, appending the round to its history
    gives    measured R/G 0.533, B/G 1.680,
             which is -1.4 % and -3.6 % against the target,
             correcting to RGB (161, 79, 255)

`--shot-at` is what the frames were actually displayed under and is not
optional in practice: the correction is measured relative to that drive, so
letting the script assume the last suggestion silently corrects from the
wrong place.

The B/G miss of 3.6 % is outside the 3 % the script treats as close enough,
so the target frames used for the calibration below are not as well matched
as the previous session's were. Reshooting under (161, 79, 255) is the way to
close it.

## 2. Calibration

The reference colors are calibrated from both sessions together, four frames
each; the target from its own two. The `--y-mid` passed here only scales the
reported lux, and the `y_card` values are what the step exists to produce.
Every frame is 80 mm f/4 ISO 3200 in aperture priority, matching the
measurement.

    $refs = [ordered]@{
        red   = @("s19_03_calibRED",   "s20_04_calibRED")
        green = @("s19_06_calibGREEN", "s20_03_calibGREEN")
        blue  = @("s19_04_calibBLUE",  "s20_02_calibBLUE")
        white = @("s19_05_calibWHITE", "s20_05_calibWHITE")
    }

    foreach ($c in $refs.Keys) {
        $files = @()
        foreach ($pre in $refs[$c]) {
            $files += (Get-ChildItem "direct_screen_light\$($pre)_*.NEF").FullName
        }
        python $S\SceneLux.py --rois --y-mid 0.04837403318646708 $files `
            --record "calibration_${c}_80mm.json" --overlay-dir overlay
    }

    $files = (Get-ChildItem direct_screen_light\s20_07_calibSCENENEW_*.NEF).FullName
    python $S\SceneLux.py --rois --y-mid 0.04837403318646708 $files `
        --record calibration_scene_80mm.json --overlay-dir overlay

Black is absent on purpose: it carries no signal to calibrate against, and
its only job is the leak measurement in step 1.

    reads    4 frames per reference color, 2 for the target, 18 in total
    writes   calibration_<color>_80mm.json
    gives    y_mid 0.015178 red, 0.027686 blue, 0.038447 scene,
             0.067984 white, 0.096413 green

Only `calibration_scene_80mm.json` feeds the result. The other four exist to
show the spread.

Their `y_card` spreads are wider than a single session's, 4.9 % red, 11.0 %
white, 17.8 % green, 21.8 % blue, because four frames across two nights
include the session-to-session difference that two frames seconds apart do
not. That is the honest figure for a reference color and it is why the
target, which does set the result, is kept to one session.

## 3. Verification

Each color is re-run at its own derived `y_mid`, which turns the calibration
frames back into an illuminance. Read what this does and does not establish
before relying on it.

    foreach ($c in $refs.Keys + "scene") {
        $r = (Get-Content "calibration_${c}_80mm.json" | ConvertFrom-Json).captures
        $yMid = ($r.y_card | Measure-Object -Average).Average
        $files = @()
        if ($c -eq "scene") {
            $files = (Get-ChildItem direct_screen_light\s20_07_calibSCENENEW_*.NEF).FullName
        } else {
            foreach ($pre in $refs[$c]) {
                $files += (Get-ChildItem "direct_screen_light\$($pre)_*.NEF").FullName
            }
        }
        python $S\SceneLux.py --rois --y-mid $yMid $files `
            --record "calibration_${c}_80mm_verified.json" --overlay-dir overlay
    }

    reads    the same 18 frames
    writes   calibration_<color>_80mm_verified.json

What comes back carries no information about the calibration. `y_mid` is
defined as the mean of the same `y_card` values the step then divides by, so
where a set shares a shutter the ratios average to exactly one and the
measurement cancels out of its own check. What is left is

    pi * K * N^2 / (rho * S * t) = 1.1031 / t

for this aperture and ISO. Two colors whose `y_mid` differ by a factor of
two return the same lux if they were shot at the same shutter. The step
cannot fail on a color basis, and the range across colors is the shutter
speeds restated, not a spread in anything measured.

What it is good for is the constants. The illuminance implied by the
exposure the meter chose has to be plausible for a card lit by a television
at this distance, and ones of lux is plausible. A thousand, or a thousandth,
would mean K, rho or the ISO is wrong, or that the meter chose an exposure
unrelated to the card. That is a check on the metering and on the constants
together, and it is the only claim this step supports.

The informative number is the disagreement inside each set, read in `y_card`
rather than in lux because the result scales as 1/y_mid and `y_mid` is the
mean of the set. The target's 5.8 % is what sets the uncertainty on the
result.

Read it in `y_card` rather than assuming lux will show it: where the meter
splits a set across two shutters, the exposure difference partly cancels in
lux and hides a disagreement that is still there in `y_card` and still
scales the result. It happened to blue in s20, where the meter gave the two
frames 1 s and 0.769 s.

## 4 to 6. Noise, signal and result

Run against the target calibration only.

    $c = (Get-Content calibration_scene_80mm.json | ConvertFrom-Json).captures
    $yMid = ($c.y_card | Measure-Object -Average).Average

    $cov = (Get-ChildItem bg_noise\*.NEF).FullName
    python $S\SceneLux.py --rois --y-mid $yMid $cov `
        --record noise_scene.json --overlay-dir overlay

    $clr = (Get-ChildItem dark_card\*.NEF).FullName
    python $S\SceneLux.py --rois --y-mid $yMid $clr `
        --record signal_scene.json --overlay-dir overlay

    python $S\SceneLuxResult.py --dark noise_scene.json `
        --measure signal_scene.json --label scene `
        --csv result_table_scene.csv --out result_scene.json `
        --plot noise_model_scene.png

    reads    7 lens-covered and 2 lens-clear frames
    writes   noise_scene.json, signal_scene.json, result_scene.json,
             result_table_scene.csv, noise_model_scene.png
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

## 7. Through the night vision device

The gain control was stepped from its maximum down to its minimum and back,
which the naming records as g1 to g4 and then g1 again.

    $files = (Get-ChildItem trough_nvg\s5_0*.NEF).FullName
    python $S\SceneLux.py --rois rois\rois_nvg.json --y-mid $yMid `
        $files --overlay-dir overlay --record nvg_s5_record.json

This `y_mid` and the scene luminance in step 8 have to come from the same
calibration. They cancel only as a pair, and mismatching them returns a wrong
gain rather than an error.

    reads    s5_01_g1 x4, s5_02_g2 x2, s5_03_g3 x2, s5_04_g4 x2, s5_05_g1 x1
    writes   nvg_s5_record.json, eleven overlays

## 8. Gain

The screen emits rather than reflects, so the quantity to compare is
luminance. SceneLux reports the illuminance that would fall on a card of
reflectance rho to produce the level it measured, and recovering the luminance
from it cancels rho, so the assumed reflectance does not affect the gain. The
script does that per frame and divides by the scene luminance measured without
the device.

    $lux = (Get-Content result_scene.json | ConvertFrom-Json).result.lux_mean
    $L = ($lux * 0.178 / [Math]::PI).ToString("E4", [cultureinfo]::InvariantCulture)

    python $S\SceneLuxGain.py nvg_s5_record.json `
        --scene-luminance $L --csv gain_table.csv --plot gain_model.png

    reads    nvg_s5_record.json
    writes   gain_table.csv, one row per frame
             gain_model.png, the same rows plotted in capture order
    gives    7008, 6381, 6833, 6817 at g1 maximum
             1396, 1372 at g2
             423, 422 at g3
             199, 196 at g4 minimum
             6781 at g1 returned

The scene luminance passed here is 2.917e-05 cd/m2, which is 5.148e-04 lux on
a card of reflectance 0.178.

Steps 7 and 8 do not depend on the calibration and do not need rerunning when
one changes. Writing the ratio out, everything the calibration contributes
cancels:

    gain = (N^2 y / t) through the device / (N^2 y / t) of the scene

leaving only the f-numbers, the exposure times and the two measured levels.
`y_mid`, rho, K, the ISO and pi all drop out. Running the red calibration
through the scripts instead, where `y_mid` is 2.8 times smaller and the scene
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
default rectangles, which is what a bare `--rois` selects.

`rois_nvg.json` is specific to session s5. Through the tube the card fills only
the middle of a much wider field and sits off-center, so the frame-centered
defaults do not apply. The patches sit diagonally at 0.095 of frame width from
the reticle center (0.4770, 0.4657), clearing the outer ring at 0.055 by 0.020
while keeping the same box size, and so the same pixel count, as the direct
frames. A different session will need them re-placed.

## Files

| File | Written by |
| --- | --- |
| `MANIFEST.csv` | step 0, the frames to place here with sizes and checksums |
| `color_scene.json` | step 1, the derived scene color and the match history |
| `calibration_<color>_80mm.json` | step 2, five records, one per color |
| `calibration_<color>_80mm_verified.json` | step 3, five lit-scene checks |
| `noise_scene.json` | step 4, seven lens-covered frames |
| `signal_scene.json` | step 5, two lens-clear frames |
| `result_scene.json` | step 6, full log including the drift model |
| `result_table_scene.csv` | step 6, every frame, noise and signal |
| `noise_model_scene.png` | step 6, drift plot, not versioned |
| `nvg_s5_record.json` | step 7, the gain sweep |
| `gain_table.csv` | step 8, per-frame luminance gain |
| `gain_model.png` | step 8, the gain sweep plotted for checking, not versioned |
| `rois/` | input, the region definition for step 7 |
| `overlay/` | ROI overlays written alongside each record, not versioned |

Naming is `<session>_<series>_<state>_<exposure>_<HHMMSS>.NEF`.
