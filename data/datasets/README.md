# Datasets

Annotated image sets for detection training and evaluation.

What is versioned here is the part that cannot be regenerated. The images are
fetched separately and placed, as everywhere else under `data/`. The
per-image label files under `labels/` are not kept either: a YOLO `.txt` is a
projection of the annotation it was exported from, four numbers and a class
index, and it can be remade at any time.

The annotation exports under a dataset's `source/` are kept. They are the
manual labelling work, they hold polygons and class names rather than boxes,
and nothing recovers them from the `.txt` the export produced. For the real
night vision set that is 420 KB against the 66 KB of labels it generates,
which is the cheaper half to carry and the expensive half to lose.

Split definitions and class lists at a dataset root stay in git too, so a
placed set can be checked against them.
