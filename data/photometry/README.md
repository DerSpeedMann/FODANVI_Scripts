# Photometry

Reference captures used to characterize the camera and the scene, rather than
to train or evaluate a model.

    nikon/   Nikon D500 illuminance measurement and night vision device gain

## The frames are not in this repository

They are 578 MB and are fetched separately, then placed under this folder in
the layout the records expect:

    data/photometry/nikon/ceiling_light_card_against_wall/   4 frames
    data/photometry/nikon/dark_card/                         9 frames
    data/photometry/nikon/trough_nvg/                       11 frames

`nikon/MANIFEST.csv` lists every required frame with its folder, size and
SHA-256, so a placed set can be checked before anything is run. Frames and
overlays are ignored by git; what is versioned is the trail that makes the
results traceable: the records SceneLux writes, the result tables, the region
definitions and the notes.

Records store bare filenames rather than paths, so they stay valid wherever
the frames came from.
