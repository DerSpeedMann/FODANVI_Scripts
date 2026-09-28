# Nikon D500 illuminance measurement

Every number reported here comes from the scripts below, run in this order.
Nothing was produced by hand.

    SceneLux.py        src/Processing/SceneLux.py
    SceneLuxColor.py   src/Processing/SceneLuxColor.py
    SceneLuxResult.py  src/Processing/SceneLuxResult.py
    SceneLuxGain.py    src/Processing/SceneLuxGain.py
    BuildManifest.py   src/Processing/BuildManifest.py

## Result

    scene illuminance   4.59e-04 lux +/- 10 %

Two things set that 10 %. Inside the run the error is 4.1 %: the drift fit is
common to both signal frames so its 3.6 % does not average away, and the
2.0 % frame-to-frame scatter does. On top of it the two calibration frames
disagree by 8.4 % in `y_card`, which scales the result directly. Taking the
full spread rather than its standard error, 8.4 % and 4.1 % in quadrature
give 9.3 %, rounded up.

This supersedes an earlier figure of 6.87e-04 lux from a previous session.
The two are calibrated against nominally the same screen color and their
`y_mid` differ by a factor of 1.50, which passes straight into the result.
The later session is taken as the reference: the scene was under tighter
control, and its meter chose the same shutter for both frames of every pair
where the earlier one split them. The earlier figure is not averaged in.

The pattern of the disagreement supports reading it that way rather than as
a camera that drifted. White reproduces across the two sessions to 1 %:

| color | earlier `y_mid` | later `y_mid` | ratio |
| --- | --- | --- | --- |
| white | 0.064895 | 0.065730 | 1.01 |
| red | 0.010409 | 0.015535 | 1.49 |
| green | 0.073504 | 0.103644 | 1.41 |
| blue | 0.016805 | 0.030290 | 1.80 |
| target | 0.028809 | 0.043141 | 1.50 |

Every saturated color moved by 1.4 to 1.8 while white stayed put. A body that
had changed would have moved white with the rest, so what moved sits on the
scene side: the display, or what the meter did in front of it. That is the
part the second session controlled better, which is the reason for preferring
it. It remains an attribution rather than a measurement, since no capture
isolates the cause, and a third session under the same control as the second
is what would confirm it.

## The calibration illuminant has to match the scene

`y_mid` is the raw level a metered-correct mid gray reaches. It is not a
constant of the body. The camera's meter integrates all the light reaching
it, while these scripts sample the green photosites only, so the two disagree
by however much the illuminant's spectrum departs from the meter's weighting.

Six captures, same card, same TV, nothing moved between them but the color on
the screen:

| color | screen RGB | measured R/G | measured B/G | `y_mid` | scene lux it gives |
| --- | --- | --- | --- | --- | --- |
| black | (0, 0, 0) | 0.49 | 1.01 | n/a | reference only |
| white | (255, 255, 255) | 0.438 | 0.667 | 0.065730 | 3.011e-04 |
| red | (255, 0, 0) | 3.521 | 0.175 | 0.015535 | 1.274e-03 |
| green | (0, 255, 0) | 0.161 | 0.262 | 0.103644 | 1.910e-04 |
| blue | (0, 0, 255) | 0.088 | 2.610 | 0.030290 | 6.534e-04 |
| **target** | **(163, 85, 255)** | **0.533** | **1.680** | **0.043141** | **4.588e-04** |

`y_mid` spans a factor of 6.67 across the five that carry light, red to
green. Nothing about the camera changed; only what it was looking at.
Calibrating against the wrong color is not a small correction, and the
scene's own color is the only defensible choice.

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
    direct_screen_light/     12 frames, six color references
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
        --green direct_screen_light\s19_06_calibGREEN_*.NEF `
        --blue  direct_screen_light\s19_04_calibBLUE_*.NEF `
        --white direct_screen_light\s19_05_calibWHITE_*.NEF `
        --black direct_screen_light\s19_01_calibBLACK_*.NEF `
        --record color_scene.json

    reads    2 scene frames, 7 dark frames, 8 display reference frames
    writes   color_scene.json
    gives    target R/G 0.541, B/G 1.743
             suggested screen RGB (168, 83, 255)

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
        --verify direct_screen_light\s19_02_calibSCENE_*.NEF `
        --shot-at 163 85 255

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

All six colors are calibrated, so the sensitivity in the table above can be
reproduced. The `--y-mid` passed here only scales the reported lux; the
`y_card` values are what the step exists to produce. All twelve frames are
80 mm f/4 ISO 3200 in aperture priority, matching the measurement.

    $colors = [ordered]@{
        scene = "s19_02_calibSCENE"; red   = "s19_03_calibRED"
        blue  = "s19_04_calibBLUE";  white = "s19_05_calibWHITE"
        green = "s19_06_calibGREEN"
    }

Black is absent on purpose: it carries no signal to calibrate against.

    foreach ($c in $colors.Keys) {
        $files = (Get-ChildItem "direct_screen_light\$($colors[$c])_*.NEF").FullName
        python $S\SceneLux.py --rois --y-mid 0.04837403318646708 $files `
            --record "calibration_${c}_80mm.json" --overlay-dir overlay
    }

    reads    2 frames per color, 10 in total
    writes   calibration_<color>_80mm.json
    gives    y_mid 0.043141 scene, 0.015535 red, 0.030290 blue,
             0.065730 white, 0.103644 green

Only `calibration_scene_80mm.json` feeds the result. The other four exist
to show the spread.

## 3. Verification

Each color is re-run at its own derived `y_mid`, which turns the calibration
frames back into an illuminance. Read what this does and does not establish
before relying on it.

    foreach ($c in $colors.Keys) {
        $r = (Get-Content "calibration_${c}_80mm.json" | ConvertFrom-Json).captures
        $yMid = ($r.y_card | Measure-Object -Average).Average
        $files = (Get-ChildItem "direct_screen_light\$($colors[$c])_*.NEF").FullName
        python $S\SceneLux.py --rois --y-mid $yMid $files `
            --record "calibration_${c}_80mm_verified.json" --overlay-dir overlay
    }

    reads    the same ten frames
    writes   calibration_<color>_80mm_verified.json
    gives    1.10 lux red, 1.10 blue, 1.43 scene, 1.43 green, 2.76 white

Those five numbers carry no information about the calibration. `y_mid` is
defined as the mean of the same `y_card` values the step then divides by, so
when a pair shares a shutter the ratios average to exactly one and the
measurement cancels out of its own check. What is left is

    pi * K * N^2 / (rho * S * t) = 1.1031 / t

for this aperture and ISO, which the five agree with to four decimals. Red
and blue have `y_mid` a factor of two apart and return the same 1.103 lux.
The step cannot fail on a color basis, and the range across colors is the
shutter speeds restated, not a spread in anything measured.

What it is good for is the constants. The illuminance implied by the
exposure the meter chose has to be plausible for a card lit by a television
at this distance, and ones of lux is plausible. A thousand, or a thousandth,
would mean K, rho or the ISO is wrong, or that the meter chose an exposure
unrelated to the card. That is a check on the metering and on the constants
together, and it is the only claim this step supports.

The informative number here is the disagreement inside each pair, read in
`y_card` rather than in lux because the result scales as 1/y_mid and `y_mid`
is the mean of the pair. It runs 0.1 % red, 2.7 % white, 2.8 % green, 3.6 %
blue, 8.4 % target, and the target's 8.4 % is what sets the uncertainty on
the result.

In this session the meter chose the same shutter for both frames of every
pair, so lux and `y_card` spreads agree. That is worth checking rather than
assuming: where the meter splits a pair across two shutters, the exposure
difference partly cancels in lux and hides a disagreement that is still
there in `y_card` and still scales the result.

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
    gives    4.588e-04 lux, +/- 1.88e-05 statistical

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

The scene luminance passed here is 2.599e-05 cd/m2, which is 4.588e-04 lux on
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
