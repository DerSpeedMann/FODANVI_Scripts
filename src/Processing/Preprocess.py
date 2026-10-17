"""
Preprocess.py

Enhance NVG images to improve detection rates with a configurable pipeline.

The json config (--config) holds only the transform: a list of steps, run in
the order listed. No module is required: each may appear any number of
times or not at all (an empty list only re-saves the images). "enabled":
false skips a step and "note" is ignored free text. Each step must give all
parameters of its module; missing, unknown or invalid keys fail before any
image is touched.
File handling (--suffix, --quality, --overwrite) is set on the command line.
There are no defaults.

    {
      "steps": [
        {"module": "equalize", "gray_only": true},
        {"module": "clahe",    "clip": 3.0, "tile": 8},
        {"module": "denoise",  "h": 10.0, "h_color": 10.0,
                               "template_window": 7, "search_window": 21}
      ]
    }

data/preprocess/preprocess_original.json (above) reproduces the original
script exactly; preprocess_denoise_first.json denoises before CLAHE so CLAHE
does not amplify grain first. All modules accept grayscale and RGB; colour
images are processed on luminance (L of LAB) so hue is preserved. Grayscale
is saved as 3-channel RGB.

Modules:
  equalize  Global histogram equalization (cv2.equalizeHist). One mapping
            for the whole image: brightens dark frames but amplifies noise
            and can blow out highlights. Mostly redundant before CLAHE.
              gray_only  skip colour images (original behaviour)

  clahe     Contrast Limited Adaptive Histogram Equalization. Equalizes each
            tile of a grid separately and blends them bilinearly, so detail
            comes out in dark and bright regions alike. Each tile histogram
            is clipped before equalizing, which limits noise amplification
            in flat regions.
              clip  contrast limit, relative to a flat histogram; 1.0 ~ no
                    effect, 2-4 typical (OpenCV default 40 is aggressive)
              tile  N -> NxN tiles; more = more local, more artefacts

  denoise   Non-Local Means (cv2.fastNlMeansDenoising[Colored]). Averages
            pixels whose surrounding patch looks similar, removing grain
            while keeping edges sharper than a blur. Colour images are
            denoised in CIELAB: L with h, a/b with h_color. OpenCV assumes
            Gaussian noise, so h may need tuning for NVG grain.
              h                strength; higher = less noise, less detail
              h_color          same for colour (10 is enough for most images)
              template_window  patch size compared, odd (recommended 7)
              search_window    area searched, odd (recommended 21); runtime
                               grows roughly with its square

Only the top level of the input folder is scanned. Inputs whose stem contains
the suffix are skipped, as are existing outputs unless --overwrite is given.

References:
  OpenCV 4.x docs: docs.opencv.org/4.x/d5/daf/tutorial_py_histogram_equalization.html
                   docs.opencv.org/4.x/d5/d69/tutorial_py_non_local_means.html
                   docs.opencv.org/4.x/d1/d79/group__photo__denoise.html
  K. Zuiderveld, "Contrast Limited Adaptive Histogram Equalization",
    Graphics Gems IV, 1994.
  A. Buades, B. Coll, J.-M. Morel, "A non-local algorithm for image
    denoising", CVPR 2005.

Usage:
    python src/Processing/Preprocess.py input/ output/ --config data/preprocess/preprocess_original.json --suffix _preprocessed --quality 95
    python src/Processing/Preprocess.py input/ --config data/preprocess/preprocess_denoise_first.json --suffix _pp --quality 95 --overwrite
"""
import argparse
import inspect
import json
import os
from PIL import Image, ImageOps
from pathlib import Path
from typing import Any, Callable, Dict, List, Tuple
import numpy as np
import cv2

IMAGE_EXTENSIONS: set[str] = {'.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.webp'}

# Keys a step may carry besides the module's own parameters.
STEP_META_KEYS: set[str] = {"module", "enabled", "note"}
REQUIRED_CONFIG_KEYS: set[str] = {"steps"}
CONFIG_KEYS: set[str] = REQUIRED_CONFIG_KEYS | {"note"}

Step = Tuple[str, Callable[..., np.ndarray], Dict[str, Any]]

def _on_luminance(img_array: np.ndarray, fn: Callable[[np.ndarray], np.ndarray]) -> np.ndarray:
    """Apply fn to a grayscale image, or to the L channel (LAB) of an RGB image"""
    if len(img_array.shape) == 2:
        return fn(img_array)
    lab = cv2.cvtColor(img_array, cv2.COLOR_RGB2LAB)
    l, a, b = cv2.split(lab)
    return cv2.cvtColor(cv2.merge([fn(l), a, b]), cv2.COLOR_LAB2RGB)

def equalize(img_array: np.ndarray, gray_only: bool) -> np.ndarray:
    """Global histogram equalization on luminance"""
    if gray_only and len(img_array.shape) != 2:
        return img_array
    return _on_luminance(img_array, cv2.equalizeHist)

def clahe(img_array: np.ndarray, clip: float, tile: int) -> np.ndarray:
    """CLAHE on luminance, preserving colour"""
    if clip <= 0 or tile < 1:
        raise ValueError(f"clahe: clip must be > 0 and tile >= 1, got clip={clip}, tile={tile}")
    op = cv2.createCLAHE(clipLimit=clip, tileGridSize=(tile, tile))
    return _on_luminance(img_array, op.apply)

def denoise(img_array: np.ndarray, h: float, h_color: float,
            template_window: int, search_window: int) -> np.ndarray:
    """Non-Local Means denoising, grayscale or colour variant"""
    for name, value in (("template_window", template_window), ("search_window", search_window)):
        if value < 1 or value % 2 == 0:
            raise ValueError(f"denoise: {name} must be a positive odd number, got {value}")
    if len(img_array.shape) == 2:
        return cv2.fastNlMeansDenoising(img_array, None, h=h,
                                        templateWindowSize=template_window,
                                        searchWindowSize=search_window)
    img_bgr = cv2.cvtColor(img_array, cv2.COLOR_RGB2BGR)
    img_bgr = cv2.fastNlMeansDenoisingColored(img_bgr, None, h=h, hColor=h_color,
                                              templateWindowSize=template_window,
                                              searchWindowSize=search_window)
    return cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)

MODULES: Dict[str, Callable[..., np.ndarray]] = {
    "equalize": equalize,
    "clahe": clahe,
    "denoise": denoise,
}

def module_params(fn: Callable[..., np.ndarray]) -> List[str]:
    """Parameter names of a module, without the image argument"""
    return list(inspect.signature(fn).parameters)[1:]

def load_config(path: str) -> Dict[str, Any]:
    """Read and check the top level of a pipeline config"""
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise SystemExit(f"{path}: top level must be a json object")
    unknown = [k for k in data if k not in CONFIG_KEYS]
    if unknown:
        raise SystemExit(f"{path}: unknown keys: {', '.join(sorted(unknown))}.\n"
                         f"  known: {', '.join(sorted(CONFIG_KEYS))}")
    missing = [k for k in REQUIRED_CONFIG_KEYS if k not in data]
    if missing:
        raise SystemExit(f"{path}: missing keys: {', '.join(sorted(missing))}")
    if not isinstance(data["steps"], list):
        raise SystemExit(f"{path}: \"steps\" must be a list of steps")
    return data

def build_pipeline(steps: List[Dict[str, Any]], source: str) -> List[Step]:
    """Validate the steps and turn them into (name, function, params) triples"""
    pipeline: List[Step] = []
    for i, step in enumerate(steps, 1):
        where = f"{source}: step {i}"
        if not isinstance(step, dict) or "module" not in step:
            raise SystemExit(f"{where}: each step needs a \"module\" key")
        name = step["module"]
        if name not in MODULES:
            raise SystemExit(f"{where}: unknown module '{name}'.\n"
                             f"  known: {', '.join(sorted(MODULES))}")
        if not step.get("enabled", True):
            continue
        fn = MODULES[name]
        known = module_params(fn)
        params = {k: v for k, v in step.items() if k not in STEP_META_KEYS}
        unknown = [k for k in params if k not in known]
        missing = [k for k in known if k not in params]
        if unknown or missing:
            raise SystemExit(f"{where} ({name}): "
                             + (f"unknown parameters: {', '.join(sorted(unknown))}. " if unknown else "")
                             + (f"missing parameters: {', '.join(missing)}. " if missing else "")
                             + f"\n  required: {', '.join(known)}")
        # Run once on a dummy image so bad values fail before any real image does.
        try:
            fn(np.zeros((32, 32, 3), dtype=np.uint8), **params)
        except Exception as e:
            raise SystemExit(f"{where} ({name}): {e}")
        pipeline.append((name, fn, params))
    return pipeline

def run_pipeline(img_array: np.ndarray, pipeline: List[Step]) -> np.ndarray:
    """Run every step in order, return an RGB image"""
    for _, fn, params in pipeline:
        img_array = fn(img_array, **params)
    if len(img_array.shape) == 2:
        img_array = cv2.cvtColor(img_array, cv2.COLOR_GRAY2RGB)
    return img_array

def process_images_for_detection(input_folder: str, output_folder: str | None,
                                  pipeline: List[Step], suffix: str, quality: int,
                                  overwrite: bool = False) -> None:
    """Preprocess NVG images to improve detection rates"""
    input_path: Path = Path(input_folder)
    output_path: Path = Path(output_folder) if output_folder else input_path

    output_path.mkdir(parents=True, exist_ok=True)

    image_files: List[Path] = [f for f in input_path.iterdir()
                               if f.is_file() and f.suffix.lower() in IMAGE_EXTENSIONS]

    processed_count: int = 0

    for image_file in image_files:
        if suffix in image_file.stem:
            continue

        output_name: str = f"{image_file.stem}{suffix}{image_file.suffix}"
        output_file_path: Path = output_path / output_name

        if output_file_path.exists() and not overwrite:
            print(f"Skipping (already processed): {image_file.name}")
            continue

        try:
            img: Image.Image = ImageOps.exif_transpose(Image.open(image_file))
            img_array: np.ndarray = np.array(img)

            # Enhance the image
            enhanced_array: np.ndarray = run_pipeline(img_array, pipeline)

            # Convert back to PIL
            enhanced_img: Image.Image = Image.fromarray(enhanced_array)

            # Save
            enhanced_img.save(output_file_path, quality=quality)
            print(f"Processed: {image_file.name} -> {output_name}")
            processed_count += 1

        except Exception as e:
            print(f"Error processing {image_file.name}: {e}")

    print(f"\n=== Summary ===")
    print(f"Processed: {processed_count}")
    print(f"Output: {output_path.absolute()}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Preprocess NVG images with a configurable pipeline "
                    "(equalize, CLAHE, denoise in any order)."
    )
    parser.add_argument("input_folder", help="Folder of source images")
    parser.add_argument("output_folder", nargs="?", default=None,
                        help="Destination folder (default: same as input)")
    parser.add_argument("--config", required=True,
                        help="json pipeline config, see the module docstring "
                             "(e.g. data/preprocess/preprocess_original.json)")
    parser.add_argument("--suffix", required=True,
                        help="Suffix appended to each output filename, e.g. _preprocessed")
    parser.add_argument("--quality", type=int, required=True,
                        help="Save quality (JPEG/WebP, 1-100), e.g. 95")
    parser.add_argument("--overwrite", action="store_true",
                        help="Reprocess even if the output file already exists")
    args = parser.parse_args()

    if not os.path.exists(args.input_folder):
        print(f"Error: Input folder '{args.input_folder}' does not exist")
        raise SystemExit(1)

    config = load_config(args.config)
    pipeline = build_pipeline(config["steps"], args.config)

    print(f"Processing images from: {args.input_folder}")
    if args.output_folder:
        print(f"Saving processed images to: {args.output_folder}")
    else:
        print(f"Saving processed images to: {args.input_folder} (same as input)")
    print(f"Config: {args.config}")
    print(f"Suffix: {args.suffix}")
    print(f"Quality: {args.quality}")
    print("Pipeline:")
    if not pipeline:
        print("  (empty, images are only re-saved)")
    for i, (name, _, params) in enumerate(pipeline, 1):
        print(f"  {i}. {name} " + ", ".join(f"{k}={v}" for k, v in params.items()))
    print()

    process_images_for_detection(args.input_folder, args.output_folder, pipeline,
                                 suffix=args.suffix, quality=args.quality, overwrite=args.overwrite)
