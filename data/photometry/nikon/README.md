# Nikon D500 illuminance measurement

Every number reported here comes from the scripts below, run in this order.
Nothing was produced by hand.

    SceneLux.py        src/Processing/SceneLux.py
    SceneLuxResult.py  src/Processing/SceneLuxResult.py
    SceneLuxGain.py    src/Processing/SceneLuxGain.py
    BuildManifest.py   src/Processing/BuildManifest.py

## Result

    scene illuminance   4.27e-04 lux, expected within 2.76e-04 to 5.78e-04

The same measurement scaled by two calibrations, both shot at the
measurement's own 80 mm f/4 ISO 3200 in aperture priority, one under the
ceiling light and one in daylight:

| calibration | y_mid | illuminance | statistical |
| --- | --- | --- | --- |
| ceiling, 21:26 | 0.039384 | 5.025e-04 | +/- 2.05e-05, 4.1 % |
| daylight, 17:45 | 0.056290 | 3.516e-04 | +/- 1.44e-05, 4.1 % |

The two disagree by 1.51e-04, and the quoted range is their midpoint plus and
minus that difference. Taking only the span between them would assume the
true value lies between the two calibrations, which nothing establishes: they
are two samples of a quantity that is not reproducing, so the same amount of
disagreement is allowed beyond either end.

The statistical error within each run is 4.1 %: the drift fit is common to
both signal frames so its 3.6 % does not average away, and the 2.0 %
frame-to-frame scatter does. It is an order below the calibration spread and
does not affect the range.

`y_mid` is meant to be a property of the body at a given ISO, and it is not
reproducing. What has been ruled out is the card's position: shot against a
wall and lying on the floor, the two daylight calibrations agree to 4.1 %,
while daylight against ceiling light differs by 43 % at identical settings.
The illuminants are far apart, red to blue 3.0 against 0.73, and the camera's
meter and the sensor disagree across them by 1.42, which is close to the 1.43
that separates the two values of `y_mid`. Until that is pinned down the honest
figure is the range rather than either end, and the second digit of any single
value should not be relied on.

What is not affected is the measurement itself. The dark subtraction returns
the same 8.432 and 8.774 DN under either calibration, so only the scaling
differs. Nor is the night vision gain affected: it is a ratio of two
luminances computed with the same `y_mid`, which cancels exactly.

## Before running anything

The frames are not versioned. Fetch them and place them here:

    ceiling_light_card_against_wall/   4 frames
    sunlight_card_against_wall/        4 frames
    dark_card/                         9 frames
    trough_nvg/                       11 frames

Set the two variables every command below uses:

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
one are resolved with `Get-ChildItem` before being passed.

## 0. Manifest

Rebuild only if the frame set changes. Everything in it is read from the
frames, so it is safe to regenerate at any time.

    python $S\BuildManifest.py .

    reads    */*.NEF
    writes   MANIFEST.csv

## 1. Calibration

`y_mid` is the raw level a metered-correct mid gray reaches, so it is read off
the calibration frames themselves. The `--y-mid` passed here only scales the
reported lux; the `y_card` values are what matter. Both sets are 80 mm f/4
ISO 3200 in aperture priority, matching the measurement.

    python $S\SceneLux.py --rois --y-mid 0.04837403318646708 `
        ceiling_light_card_against_wall\s5_01_calib_30th_212653.NEF `
        ceiling_light_card_against_wall\s5_01_calib_30th_212712.NEF `
        --record calibration_ceiling_80mm.json --overlay-dir overlay

    python $S\SceneLux.py --rois --y-mid 0.04837403318646708 `
        sunlight_card_against_wall\s7_0*.NEF `
        --record calibration_daylight_80mm.json --overlay-dir overlay

    reads    2 ceiling frames, 4 daylight frames
    writes   calibration_ceiling_80mm.json, calibration_daylight_80mm.json
    gives    y_mid 0.039384 from the ceiling set
             y_mid 0.056290 from the daylight set

## 2. Verification

The same frames at the derived `y_mid` return 32.8 and 33.4 lux for the lit
ceiling scene, a plausible indoor level.

    python $S\SceneLux.py --rois --y-mid $yMid `
        ceiling_light_card_against_wall\s5_01_calib_30th_212653.NEF `
        ceiling_light_card_against_wall\s5_01_calib_30th_212712.NEF `
        --record calibration_ceiling_80mm_verified.json

    reads    the same two calibration frames
    writes   calibration_ceiling_80mm_verified.json

## 3 to 5. Noise, signal and result, once per calibration

The frames are the same in both passes; only the `y_mid` carried in the record
differs, which is what scales the result. The drift plot is written once,
since it is in DN and identical either way.

    foreach ($cal in "ceiling", "daylight") {
        $c = (Get-Content "calibration_${cal}_80mm.json" | ConvertFrom-Json).captures
        $yMid = ($c.y_card | Measure-Object -Average).Average

        $cov = (Get-ChildItem dark_card\s2_01_lensCOV_*.NEF,
                              dark_card\s2_04_lensCOV_*.NEF).FullName
        python $S\SceneLux.py --rois --y-mid $yMid $cov `
            --record "noise_$cal.json" --overlay-dir overlay

        $clr = (Get-ChildItem dark_card\s2_03_lensCLEAR_*.NEF).FullName
        python $S\SceneLux.py --rois --y-mid $yMid $clr `
            --record "signal_$cal.json" --overlay-dir overlay

        python $S\SceneLuxResult.py --dark "noise_$cal.json" `
            --measure "signal_$cal.json" --label $cal `
            --csv "result_table_$cal.csv" --out "result_$cal.json" `
            --plot "noise_model_$cal.png"
    }

    reads    7 lens-covered and 2 lens-clear frames, both passes
    writes   noise_<cal>.json, signal_<cal>.json, result_<cal>.json,
             result_table_<cal>.csv, noise_model_<cal>.png
    gives    5.025e-04 lux under the ceiling calibration
             3.516e-04 lux under the daylight one

The two drift plots come out byte-identical: the plot is in DN, and `y_mid`
only scales the lux, so it cannot change the drift.

Dark current rises while the sensor works, so one averaged dark frame only
describes the moment it was taken. The covered frames sit either side of the
measurement and a straight line through them in capture time gives each signal
frame the offset for its own timestamp, taken from `exif.datetime`.

Over this run the drift is +0.17 DN/min with a residual scatter of 0.81 DN
against a signal of 8.6 DN. The fit standard error is smallest at the centroid
of the covered frames and grows away from it, so `dark_model_se_dn` runs
0.53 DN at the first frame, down to 0.31 DN at the signal frames, and back up
to 0.50 DN at the last. The measurements sit almost exactly at the centroid,
which is what bracketing buys.

## 6. Through the night vision device

The gain control was stepped from its maximum down to its minimum and back,
which the naming records as g1 to g4 and then g1 again.

    $c = (Get-Content calibration_ceiling_80mm.json | ConvertFrom-Json).captures
    $yMidNvg = ($c.y_card | Measure-Object -Average).Average

    $files = (Get-ChildItem trough_nvg\s5_0*.NEF).FullName
    python $S\SceneLux.py --rois rois\rois_nvg.json --y-mid $yMidNvg `
        $files --overlay-dir overlay --record nvg_s5_record.json

This `y_mid` and the scene luminance in step 7 have to come from the same
calibration. They cancel only as a pair, and mismatching them returns a
wrong gain rather than an error.

    reads    s5_01_g1 x4, s5_02_g2 x2, s5_03_g3 x2, s5_04_g4 x2, s5_05_g1 x1
    writes   nvg_s5_record.json, eleven overlays

## 7. Gain

The screen emits rather than reflects, so the quantity to compare is
luminance. SceneLux reports the illuminance that would fall on a card of
reflectance rho to produce the level it measured, and recovering the luminance
from it cancels rho, so the assumed reflectance does not affect the gain. The
script does that per frame and divides by the scene luminance measured without
the device.

    python $S\SceneLuxGain.py nvg_s5_record.json `
        --scene-luminance 2.847e-05 --csv gain_table.csv --plot gain_model.png

    reads    nvg_s5_record.json
    writes   gain_table.csv, one row per frame
             gain_model.png, the same rows plotted in capture order
    gives    7008, 6382, 6834, 6817 at g1 maximum
             1396, 1372 at g2
             423, 422 at g3
             199, 196 at g4 minimum
             6782 at g1 returned

The scene luminance passed here is 2.847e-05 cd/m2, which is 5.025e-04 lux on
a card of reflectance 0.178, from the ceiling calibration.

Steps 6 and 7 do not depend on the calibration and do not need rerunning when
one changes. Writing the ratio out, everything the calibration contributes
cancels:

    gain = (N^2 y / t) through the device / (N^2 y / t) of the scene

leaving only the f-numbers, the exposure times and the two measured levels.
`y_mid`, rho, K, the ISO and pi all drop out. Substituting the numbers by
hand gives 7007 for the first frame, and running the daylight calibration
through the scripts instead of the ceiling one returns the same figures and
the same factor of 35.8.

This makes the gain the firmest number here. The illuminance carries the
calibration spread as a factor of 1.43; the gain carries none of it. The 43 % that separates the
two calibrations, and which sets the range on the illuminance, has no effect
here at all.

The control was turned from maximum to minimum and back, a range of about 34x,
and the returned maximum reproduces the first to within the frame-to-frame
scatter of the four maximum frames, which is itself about 4 %.

This is a floor, not the device's datasheet gain. Coupling between eyepiece
and camera loses light to vignetting and exit pupil mismatch, and a datasheet
figure in cd/m2 per lux refers to illuminance at the photocathode, which the
objective concentrates first.

## Why the calibration is at 80 mm f/4

`y_mid` is the raw level a metered-correct mid gray reaches. The equation
accounts for aperture and exposure explicitly, so their absolute values do not
matter, but anything it does not model, such as lens transmission and
vignetting, only cancels when the calibration is shot in the same optical
configuration as the measurement. The signal frames are 80 mm f/4 ISO 3200, so
the calibration is too.

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
| `calibration_ceiling_80mm.json` | step 1, gives the ceiling `y_mid` |
| `calibration_daylight_80mm.json` | step 1, gives the daylight `y_mid` |
| `calibration_ceiling_80mm_verified.json` | step 2, lit-scene check |
| `noise_ceiling.json`, `noise_daylight.json` | step 3, seven lens-covered frames |
| `signal_ceiling.json`, `signal_daylight.json` | step 4, two lens-clear frames |
| `result_ceiling.json`, `result_daylight.json` | step 5, full log including the drift model |
| `result_table_ceiling.csv`, `result_table_daylight.csv` | step 5, every frame, noise and signal |
| `noise_model_ceiling.png`, `noise_model_daylight.png` | step 5, drift plot, identical for both, not versioned |
| `nvg_s5_record.json` | step 6, the gain sweep |
| `gain_table.csv` | step 7, per-frame luminance gain |
| `gain_model.png` | step 7, the gain sweep plotted for checking, not versioned |
| `rois/` | input, the region definition for step 6 |
| `overlay/` | ROI overlays written alongside each record, not versioned |

Naming is `<session>_<series>_<state>_<exposure>_<HHMMSS>.NEF`.
