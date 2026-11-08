# OnePlus 7 Pro dark-level drift

The smartphone was the first instrument for the illuminance measurement and
was replaced by the Nikon D500 (`../nikon/`). This folder holds the drift
measurement behind that, run through the same scripts as the Nikon:

    SceneLux.py        src/Processing/SceneLux.py
    SceneLuxResult.py  src/Processing/SceneLuxResult.py
    BuildManifest.py   src/Processing/BuildManifest.py

## Result

    dark drift       +0.0045 DN/s, residual RMS 0.24 DN over 8 frames
    dark level       11.9 DN at the first signal frame, 14.2 DN at the last dark
    net signal       0.22 to 0.45 DN in six frames, 0.98 DN in the last
    dark model SE    0.45 DN at the first signal frame, 0.19 DN at the last

The dark frames all follow the signal frames, so the model extrapolates
backwards. The lux the scripts print uses the phone's daylight `y_mid`, not a
calibration under the scene's color, and is not used.

## Frames

Session 3, 2026-09-18, all 30 s, ISO 3193, f/1.65, DNG, display blanketed.
Copies of the originals in `Captures/phone/`.

    dark_card/   7 frames, s3_01, lens clear, 06:02-06:06
    bg_noise/    8 frames, s3_02, lens covered, 06:07-06:10

Session 3 is the only one with lens-covered frames at the signal exposure.

## Run

From the repository root, with `$P = "data\photometry\phone"`:

    python src\Processing\BuildManifest.py $P --pattern "*/*.dng"

    python src\Processing\SceneLux.py "$P\bg_noise\s3_02_*.dng" `
        --rois $P\rois\rois_s3.json --record $P\noise_s3.json --overlay-dir $P\overlay
    python src\Processing\SceneLux.py "$P\dark_card\s3_01_*.dng" `
        --rois $P\rois\rois_s3.json --record $P\signal_s3.json --overlay-dir $P\overlay
    python src\Processing\SceneLuxResult.py --dark $P\noise_s3.json `
        --measure $P\signal_s3.json --label s3 --csv $P\result_table_s3.csv `
        --out $P\result_s3.json --plot $P\noise_model_s3.png

`--rois` takes the region mean, since at about 12 DN on a 10-bit raw the
median moves in whole steps. The single frames are too dim to show the
reticle, so `rois/rois_s3.json` was placed on the mean of the seven signal
frames: reticle center at (0.566, 0.563), the four regions on the diagonals
between the inner circle and the outer ring. Every frame, dark and signal,
reads the same four 120 x 120 px rectangles, 7200 green photosites each. The
line detector flags them all `check placement`; at this level it is driven by
the noise. `overlay/stack_s3_01_rois.jpg` (and its `_crop`) shows the
placement on that mean.
