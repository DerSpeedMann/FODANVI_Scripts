# Nikon D500 illuminance measurement

Every number reported here comes from the scripts below, run in this order.
Nothing was produced by hand.

    SceneLux.py        src/Processing/SceneLux.py
    SceneLuxResult.py  src/Processing/SceneLuxResult.py
    SceneLuxGain.py    src/Processing/SceneLuxGain.py
    BuildManifest.py   src/Processing/BuildManifest.py

## Result

    scene illuminance   5.025e-04 lux  +/- 2.05e-05  (4.1 %, statistical only)
    range               4.820e-04 to 5.231e-04

The uncertainty has two parts. The same drift fit is subtracted from both
signal frames, so its error is common to them and does not average away: that
is 3.6 %. The frame-to-frame scatter is 2.0 % and does average. In quadrature,
4.1 %.

This covers the dark subtraction only. It excludes the card reflectance
rho = 0.178 and the mid-gray reference `y_mid`, which are the larger terms.

## Before running anything

The frames are not versioned. Fetch them and place them here:

    ceiling_light_card_against_wall/   4 frames
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
reported lux; the `y_card` values are what matter.

    python $S\SceneLux.py --rois --y-mid 0.04837403318646708 `
        ceiling_light_card_against_wall\s5_01_calib_30th_212653.NEF `
        ceiling_light_card_against_wall\s5_01_calib_30th_212712.NEF `
        --record calibration_ceiling_80mm.json --overlay-dir overlay

    $cal  = (Get-Content calibration_ceiling_80mm.json | ConvertFrom-Json).captures
    $yMid = ($cal.y_card | Measure-Object -Average).Average

    reads    s5_01_calib_30th_212653.NEF, s5_01_calib_30th_212712.NEF
    writes   calibration_ceiling_80mm.json, two overlays
    gives    y_mid = 0.039383788213016

## 2. Verification

The same frames at the derived `y_mid` return 32.8 and 33.4 lux for the lit
ceiling scene, a plausible indoor level.

    python $S\SceneLux.py --rois --y-mid $yMid `
        ceiling_light_card_against_wall\s5_01_calib_30th_212653.NEF `
        ceiling_light_card_against_wall\s5_01_calib_30th_212712.NEF `
        --record calibration_ceiling_80mm_verified.json

    reads    the same two calibration frames
    writes   calibration_ceiling_80mm_verified.json

## 3. Noise

Seven lens-covered frames, shot either side of the measurement.

    $cov = (Get-ChildItem dark_card\s2_01_lensCOV_*.NEF,
                          dark_card\s2_04_lensCOV_*.NEF).FullName
    python $S\SceneLux.py --rois --y-mid $yMid `
        $cov --record noise_record.json --overlay-dir overlay

    reads    s2_01_lensCOV_30s_040215, _040319, _040423
             s2_04_lensCOV_30s_040839, _040943, _041047, _041151
    writes   noise_record.json, seven overlays

## 4. Signal

Two lens-clear frames of the dark scene.

    $clr = (Get-ChildItem dark_card\s2_03_lensCLEAR_*.NEF).FullName
    python $S\SceneLux.py --rois --y-mid $yMid `
        $clr --record signal_record.json --overlay-dir overlay

    reads    s2_03_lensCLEAR_lapON_30s_040631, _040735
    writes   signal_record.json, two overlays

## 5. Subtraction and result

SceneLux measures one frame at a time and subtracts nothing, so this is a
separate script. The flags are named `--dark` and `--measure`; they take the
noise and signal records.

    python $S\SceneLuxResult.py --dark noise_record.json `
        --measure signal_record.json --label d500 `
        --csv result_table.csv --out result.json --plot noise_model.png

    reads    noise_record.json, signal_record.json
    writes   result.json, result_table.csv, noise_model.png

Dark current rises while the sensor works, so one averaged dark frame only
describes the moment it was taken. The covered frames sit either side of the
measurement and a straight line through them in capture time gives each signal
frame the offset for its own timestamp, taken from `exif.datetime`.

Over this run the drift is +0.17 DN/min with a residual scatter of 0.81 DN
against a signal of 8.6 DN. The fit standard error is smallest at the centroid
of the covered frames and grows away from it, so `dark_model_se_dn` runs
0.53 DN at the first frame, down to 0.31 DN at the signal frames, and back up
to 0.50 DN at the last. The measurements sit almost exactly at the centroid,
which is what bracketing buys. Every series in `noise_model.png` comes from
`result_table.csv`.

## 6. Through the night vision device

The gain control was stepped from its maximum down to its minimum and back,
which the naming records as g1 to g4 and then g1 again.

    $files = (Get-ChildItem trough_nvg\s5_0*.NEF).FullName
    python $S\SceneLux.py --rois rois\rois_nvg.json --y-mid $yMid `
        $files --overlay-dir overlay --record nvg_s5_record.json

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

The scene luminance comes from step 5: 5.025e-04 lux on a card of reflectance
0.178 is 2.847e-05 cd/m2.

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
| `calibration_ceiling_80mm.json` | step 1, gives `y_mid` |
| `calibration_ceiling_80mm_verified.json` | step 2, lit-scene check |
| `noise_record.json` | step 3, seven lens-covered frames |
| `signal_record.json` | step 4, two lens-clear frames |
| `result.json` | step 5, full log including the drift model |
| `result_table.csv` | step 5, the result: every frame, noise and signal |
| `noise_model.png` | step 5, drift plot |
| `nvg_s5_record.json` | step 6, the gain sweep |
| `gain_table.csv` | step 7, per-frame luminance gain |
| `gain_model.png` | step 7, the gain sweep plotted for checking |
| `rois/` | input, the region definition for step 6 |
| `overlay/` | written alongside each record, not versioned |

Naming is `<session>_<series>_<state>_<exposure>_<HHMMSS>.NEF`.
