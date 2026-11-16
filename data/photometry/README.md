# Photometry

Reference captures used to characterize the camera and the scene, rather than
to train or evaluate a model.

    nikon/   Nikon D500 illuminance measurement, night vision device gain and grain
    phone/   OnePlus 7 Pro dark-level drift

## The frames are not in this repository

They are 2.8 GB and are fetched separately, then placed under this folder in
the layout the records expect:

    nikon/bg_noise/             39 frames, lens covered
    nikon/dark_card/             6 frames, the measurement
    nikon/direct_screen_light/  34 frames, color references and targets
    nikon/trough_nvg/           11 frames, through the device
    phone/bg_noise/              8 frames, lens covered
    phone/dark_card/             7 frames, lens clear

`nikon/MANIFEST.csv` and `phone/MANIFEST.csv` list every required frame with
its folder, size and SHA-256, so a placed set can be checked before anything
is run. Frames and overlays are ignored by git; what is versioned is the trail
that makes the results traceable: the records SceneLux writes, the result
tables, the region definitions and the notes.

Records store bare filenames rather than paths, so they stay valid wherever
the frames came from.
