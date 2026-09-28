# Nikon D500 illuminance measurement

Every number reported here comes from the scripts below, run in this order.
Nothing was produced by hand.

    SceneLux.py        src/Processing/SceneLux.py
    SceneLuxColor.py   src/Processing/SceneLuxColor.py
    SceneLuxResult.py  src/Processing/SceneLuxResult.py
    SceneLuxGain.py    src/Processing/SceneLuxGain.py
    BuildManifest.py   src/Processing/BuildManifest.py

## Result

    scene illuminance   6.87e-04 lux +/- 10 %

The statistical error inside the run is 4.1 %: the drift fit is common to both
signal frames so its 3.6 % does not average away, and the 2.0 % frame-to-frame
scatter does. The quoted 10 % is wider because the two target calibration
frames disagree by 8.5 % in `y_card`, the meter having chosen 1 s for one and
0.769 s for the other. That scales the result directly, and taking the full
spread rather than its standard error, 8.5 % and 4.1 % in quadrature give
9.4 %, rounded up.

## The calibration illuminant has to match the scene

`y_mid` is the raw level a metered-correct mid gray reaches. It is not a
constant of the body. The camera's meter integrates all the light reaching
it, while these scripts sample the green photosites only, so the two disagree
by however much the illuminant's spectrum departs from the meter's weighting.

Six calibrations, same card, same TV, nothing moved between them but the
color on the screen:

| color | screen RGB | measured R/G | measured B/G | `y_mid` | scene lux it gives |
| --- | --- | --- | --- | --- | --- |
| white | (255, 255, 255) | 0.443 | 0.667 | 0.064895 | 3.050e-04 |
| red | (255, 0, 0) | 3.400 | 0.194 | 0.010409 | 1.901e-03 |
| green | (0, 255, 0) | 0.160 | 0.260 | 0.073504 | 2.693e-04 |
| blue | (0, 0, 255) | 0.095 | 2.743 | 0.016805 | 1.178e-03 |
| first guess | (173, 112, 255) | 0.511 | 1.461 | 0.036873 | 5.368e-04 |
| **target** | **(163, 85, 255)** | **0.537** | **1.756** | **0.028809** | **6.870e-04** |

`y_mid` spans a factor of 7.06 across them, red to green. Nothing about the
camera changed; only what it was looking at. Calibrating against the wrong
color is therefore not a small correction, and the scene's own color is the
only defensible choice.

The target color is not a guess. The measured scene is a laptop screen in an
otherwise dark room, and subtracting the noise frames from the signal frames
per Bayer channel, over the same four ROI boxes everything else is sampled
with, gives its net response: R 0.000290, G 0.000536, B 0.000934, or 4.6, 8.6
and 14.9 DN. That green figure is the same 8.6 DN the result table reports as
`delta`, which is the check that the derivation and the measurement are
sampling the same thing.

The ratios are R/G 0.541 and B/G 1.743. RGB (163, 85, 255) on the TV measures
0.537 and 1.756, reproducing both to 0.7 %, which is why it and no other color
is used to scale the result.

The first guess is kept because it sets the tolerance. It is close to the
target by eye, and still off by 6 % in R/G and 16 % in B/G, which moves the
result by 28 %. Matching the scene color approximately is not good enough;
it has to be derived.

Its screen RGB is reconstructed from the frames rather than read off a log:
the pure-primary frames give the camera's response to each display primary,
and that model predicts the target frames to within about 2 %, which is
enough to separate (173, 112, 255) from the other candidates of that session.
The other five values are as they were entered.

What none of this touches is the night vision gain. It is a ratio of two
luminances computed with the same `y_mid`, so the calibration cancels exactly
and the figures in step 8 are the same under any of the six.

## Before running anything

The frames are not versioned. Fetch them and place them here:

    bg_noise/                 7 frames, lens covered
    dark_card/                2 frames, the measurement itself
    direct_screen_light/     12 frames, the calibrations
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

`y_mid` moves with the illuminant, by a factor of 7 across the colors in the
table above, so the calibration has to be shot under light of the scene's own
color. This derives that color from the scene rather than choosing it by eye.

    python $S\SceneLuxColor.py estimate `
        --signal dark_card\*.NEF --noise bg_noise\*.NEF `
        --red   direct_screen_light\s17_02_calibRED_*.NEF `
        --green direct_screen_light\s17_03_calibGREEN_*.NEF `
        --blue  direct_screen_light\s17_04_calibBLUE_*.NEF `
        --white direct_screen_light\s17_01_calibWHITE_*.NEF `
        --record color_scene.json

    reads    2 scene frames, 7 dark frames, 8 display reference frames
    writes   color_scene.json
    gives    target R/G 0.541, B/G 1.743
             suggested screen RGB (167, 88, 255)

The three primaries give the camera's response to each, as the columns of a
3x3 matrix; the scene's net response, signal minus dark, is the target; and
solving the one against the other gives the drive to display.

The white frames are not a fourth primary. Three primaries already span the
space, so the matrix is fully determined without white, and white is captured
because it is the only frame that can show the model to be wrong: an additive
display driven at full white produces exactly what its primaries produce
together. This TV falls 8.8 % short of that, but uniformly across all three
channels, which is a backlight dimming on bright content and cancels, since
the solve matches the direction of a response and lets exposure carry the
magnitude. What would not cancel is the part left after that uniform factor
divides out, and here it is within 1.3 %.

Display the color, shoot the card under it, and check what the camera
actually sees against the target:

    python $S\SceneLuxColor.py refine --record color_scene.json `
        --verify direct_screen_light\s18_01_calibSCENE_*.NEF `
        --shot-at 163 85 255

    reads    2 frames shot under the displayed color
    writes   color_scene.json, appending the round to its history
    gives    measured R/G 0.547, B/G 1.719,
             which is +1.1 % and -1.4 % against the target

`--shot-at` is what the frames were actually displayed under and is not
optional in practice: the correction is measured relative to that drive, so
letting the script assume the last suggestion silently corrects from the
wrong place.

The calibration frames here were shot under RGB (163, 85, 255), derived by
hand before this script existed, rather than the (167, 88, 255) the script
now suggests. The verification above puts the value actually used within
1.4 % of the target, which is inside the 3 % tolerance, so the calibration
was not reshot.

## 2. Calibration

All six colors are calibrated, so the sensitivity in the table above can be
reproduced. The `--y-mid` passed here only scales the reported lux; the
`y_card` values are what the step exists to produce. All twelve frames are
80 mm f/4 ISO 3200 in aperture priority, matching the measurement.

    $colors = [ordered]@{
        white = "s17_01_calibWHITE"; red   = "s17_02_calibRED"
        green = "s17_03_calibGREEN"; blue  = "s17_04_calibBLUE"
        firstguess = "s17_05_calibFIRSTGUESS"
        scene      = "s18_01_calibSCENE"
    }

    foreach ($c in $colors.Keys) {
        $files = (Get-ChildItem "direct_screen_light\$($colors[$c])_*.NEF").FullName
        python $S\SceneLux.py --rois --y-mid 0.04837403318646708 $files `
            --record "calibration_${c}_80mm.json" --overlay-dir overlay
    }

    reads    2 frames per color, 12 in total
    writes   calibration_<color>_80mm.json
    gives    y_mid 0.064895 white, 0.010409 red, 0.073504 green,
             0.016805 blue, 0.036873 first guess, 0.028809 scene

Only `calibration_scene_80mm.json` feeds the result. The other five exist to
show the spread.

## 3. Verification

Each color is re-run at its own derived `y_mid`. The frames are
metered-correct exposures of the lit scene, so the lux that comes back should
be the illuminance actually falling on the card, and the two frames of a pair
should agree.

    foreach ($c in $colors.Keys) {
        $r = (Get-Content "calibration_${c}_80mm.json" | ConvertFrom-Json).captures
        $yMid = ($r.y_card | Measure-Object -Average).Average
        $files = (Get-ChildItem "direct_screen_light\$($colors[$c])_*.NEF").FullName
        python $S\SceneLux.py --rois --y-mid $yMid $files `
            --record "calibration_${c}_80mm_verified.json" --overlay-dir overlay
    }

    reads    the same twelve frames
    writes   calibration_<color>_80mm_verified.json
    gives    1.76 lux white, 1.10 red, 1.25 green, 1.26 blue,
             1.10 first guess, 1.26 scene

All six land between 1.1 and 1.8 lux for the same lit card, which is the
consistency check: the round trip returns the real illuminance whatever color
it was calibrated on, because there `y_mid` divides out the same value it was
derived from.

Pair agreement is worth reading in `y_card` rather than in lux. Where the
meter gave the two frames a different shutter, the exposure difference partly
cancels in lux and hides the disagreement: green's pair agrees to 2.9 % in lux
but 23.2 % in `y_card`. The `y_card` spread is what matters, because the
result scales as 1/y_mid and `y_mid` is the mean of the pair. It runs 0.7 %
red, 3.0 % first guess, 3.1 % white, 8.5 % target, 14.7 % blue, 23.2 % green.
The target's 8.5 % is what sets the 10 % on the result.

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
    gives    6.870e-04 lux, +/- 2.81e-05 statistical

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

The scene luminance passed here is 3.892e-05 cd/m2, which is 6.870e-04 lux on
a card of reflectance 0.178.

Steps 7 and 8 do not depend on the calibration and do not need rerunning when
one changes. Writing the ratio out, everything the calibration contributes
cancels:

    gain = (N^2 y / t) through the device / (N^2 y / t) of the scene

leaving only the f-numbers, the exposure times and the two measured levels.
`y_mid`, rho, K, the ISO and pi all drop out. Running the red calibration
through the scripts instead, where `y_mid` is 2.8 times smaller and the scene
comes out at 1.901e-03 lux, returns the same 7008 down to 196 and the same
factor of 35.8.

This makes the gain the firmest number here. The illuminance carries the
calibration spread; the gain carries none of it. The factor of 7.06 that
separates the six calibrations, and which is why the calibration color has to
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
| `calibration_<color>_80mm.json` | step 2, six records, one per color |
| `calibration_<color>_80mm_verified.json` | step 3, six lit-scene checks |
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
