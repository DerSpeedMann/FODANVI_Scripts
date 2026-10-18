"""
Generate NVG, second version.

A copy of GenerateNVGLegacy.py with one change: where grain is placed.

GenerateNVGLegacy.py is kept and must not be edited. Every fine-tuning dataset in
this project was produced with it, and reproducing those datasets requires
the script exactly as it was. This file exists so the grain can be corrected
without taking that away.

WHAT CHANGED

The legacy script places grain by a bell curve peaking in the midtones and suppresses it in
shadows, on the stated reasoning that grain is "visible mainly in mid-tones,
less in dark areas". Measured against real captures through the device, that
is backwards. The 66 evaluation captures from the Pi camera behind the
eyepiece (datasets/real_nvg, val), measured the way AnalyzeNVG.py does,
inside the central square of half the field radius, give this noise profile
by brightness band:

    band        0.0-0.1  0.1-0.2  0.2-0.3  0.3-0.4  0.4-0.5
    measured       1.09     1.38     1.20     1.05     0.64
    relative       0.79     1.00     0.87     0.76     0.46
    v1 applies     0.01     0.18     0.63     1.00     1.00
    v2 applies     0.90     1.00     0.68     0.53     0.44

The device is noisiest at about 0.15 and quietens toward the midtones. v1
applies almost nothing exactly there and full strength where the device is
quieter, so it is wrong by -99 % at the bottom and +116 % at 0.45.

v2 moves the peak to 0.15 and decays above it. Against this profile it is
within 14 % in the two bands below 0.2 and at 0.45, but falls off too fast
in between, -22 % at 0.25 and -30 % at 0.35. The curve was fitted to an
earlier whole-frame measurement, which the vignette pushed toward a steeper
decay; it has not been refitted, because the coco_nvg2 sets were built with
it. The rise below the peak is nearly flat, a 0.10 exponent, there only to
avoid a hard edge at pure black.

NOISE_INTENSITY MEANS SOMETHING DIFFERENT HERE

In v1 the mask is 1.0 across the midtones, so noise_intensity set the
midtone grain. In v2 the mask peaks at 0.15 and the midtones sit near 0.5,
so noise_intensity sets the grain at the peak, in the shadows. The same
numeric value therefore produces a different image, and v1 values should not
be carried across without rechecking them against AnalyzeNVG.py.

ONE CAVEAT ON THE MEASUREMENT

Two other real sets, phone photographs and VLC frames of the device output,
show the opposite profile and would support v1. They are not used here
because a phone ISP denoises shadows hard, so that profile is the phone's
noise reduction rather than the tube's behaviour. The Pi camera is also the
path the evaluation imagery comes from, which is the one worth matching.

Nothing above 0.6 appears in the real captures, so the highlight cutoff is
carried over from v1 untested rather than fitted.
"""

import os
from PIL import Image
from pathlib import Path
from typing import List, Optional
from dataclasses import dataclass
import numpy as np
import cv2


@dataclass
class ColorSettings:
    """Color-specific settings for NVG effect"""
    suffix: str  # File suffix for this color mode (e.g., "_nvg_green")

    # Channel multipliers for color tinting
    red_multiplier: float  # Red channel multiplier (0.0-1.0)
    green_multiplier: float  # Green channel multiplier (0.0-1.0+)
    blue_multiplier: float  # Blue channel multiplier (0.0-1.0)

    # Contrast/brightness adjustments (multipliers applied to base values)
    contrast_multiplier: float  # Multiply base contrast_alpha by this
    brightness_multiplier: float  # Multiply base contrast_beta by this


# Global color mode definitions
COLOR_MODES = {
    "green": ColorSettings(
        suffix="_nvg2_green",
        red_multiplier=0.005,
        green_multiplier=1.0,
        blue_multiplier=0.005,
        contrast_multiplier=1.0,
        brightness_multiplier=1.0
    ),
    "white": ColorSettings(
        suffix="_nvg2_white",
        red_multiplier=0.60,
        green_multiplier=1.08,
        blue_multiplier=0.95,
        contrast_multiplier=0.83,  # White NVG: reduce contrast by ~17%
        brightness_multiplier=1.5   # White NVG: increase brightness by ~50%
    )
}


@dataclass
class NVGConfig:
    """Configuration for NVG effect parameters"""
    # Color mode
    color: str = "white"  # "green" or "white" - sets the NVG type

    # Base effect parameters (used for all color modes)
    equalize_histogram: bool = True  # Apply histogram equalization (can add grain-like appearance)
    noise_intensity: float = 8.0  # Grain/noise intensity (0-50) - additive grain for lightening effect
    grain_size: int = 3  # Grain particle size (1, 3, 5, 7, etc.) - higher = coarser/larger grain
    bloom_threshold: int = 235  # Brightness threshold for bloom effect (0-255) - minimal bloom
    bloom_intensity: float = 0.08  # Bloom glow intensity (0.0-1.0) - very subtle
    blur_amount: int = 9  # Slight blur kernel size (must be odd: 3, 5, 7, 9, etc.) - smooths grain
    contrast_alpha: float = 0.60  # Base contrast adjustment (0.5-1.5) - compress range to reduce extremes
    contrast_beta: int = 40  # Base brightness adjustment (-100 to 100) - shift histogram right
    vignette_intensity: float = 2.2  # Vignette strength (1.0-4.0, higher = stronger edge darkening)

    # Where grain sits against brightness. Fitted to real captures through
    # the device; see the module docstring. noise_intensity is the grain at
    # grain_peak, which is in the shadows, not in the mid-tones as in v1.
    grain_peak: float = 0.15   # normalised brightness the grain peaks at
    grain_rise: float = 0.10   # exponent below the peak, near flat
    grain_fall: float = 0.75   # exponent above the peak, the measured decay

    # Measured grain per brightness band, as AnalyzeNVG.py --config writes it:
    # {"brightness": [band centres], "sigma": [residual spread]}, both read off
    # the luma of real captures. When set it replaces the curve above, and
    # noise_intensity scales it, 1.0 applying it as measured.
    grain_profile: Optional[dict] = None

    def get_color_settings(self) -> ColorSettings:
        """Get the color settings for the current color mode"""
        return COLOR_MODES.get(self.color.lower(), COLOR_MODES["green"])

    def get_suffix(self) -> str:
        """Get the file suffix for the current color mode"""
        return self.get_color_settings().suffix


def load_config(path: str) -> "NVGConfig":
    """
    Build a config from a json file, typically one AnalyzeNVG.py wrote.

    Only keys that name a real NVGConfig field are applied, and an unknown
    key is an error rather than a shrug: a misspelled field that is silently
    ignored would leave the run looking configured while it quietly used a
    default, which is the kind of thing nobody notices until the dataset is
    already built.

    Channel multipliers live on ColorSettings rather than NVGConfig, so a
    settings block in the file is applied to the color mode it names.
    """
    import json
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)

    cfg = NVGConfig()
    fields = set(cfg.__dataclass_fields__)
    settings = data.pop("color_settings", None)

    # Anything AnalyzeNVG writes for context rather than for configuring.
    for note in ("measured", "source", "generated_utc", "note"):
        data.pop(note, None)

    unknown = [k for k in data if k not in fields]
    if unknown:
        raise SystemExit(
            f"{path}: not NVGConfig fields: {', '.join(sorted(unknown))}.\n"
            f"  known: {', '.join(sorted(fields))}")
    for k, v in data.items():
        setattr(cfg, k, v)

    if settings:
        mode = settings.pop("color", cfg.color)
        target = COLOR_MODES.get(str(mode).lower())
        if target is None:
            raise SystemExit(f"{path}: unknown color mode {mode!r}")
        known = set(target.__dataclass_fields__)
        bad = [k for k in settings if k not in known]
        if bad:
            raise SystemExit(
                f"{path}: not ColorSettings fields: {', '.join(sorted(bad))}")
        for k, v in settings.items():
            setattr(target, k, v)
        cfg.color = str(mode).lower()

    return cfg

def has_nvg_suffix(filename: str, config: NVGConfig) -> bool:
    """Check if filename contains the NVG suffix"""
    stem: str = Path(filename).stem
    return config.get_suffix() in stem

def simulate_nvg(image: np.ndarray, config: NVGConfig) -> np.ndarray:
    # Convert to grayscale
    if len(image.shape) == 3:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    else:
        gray = image

    # Normalize and enhance histogram to better match NVG distribution
    # This spreads values more evenly across the range
    if config.equalize_histogram:
        gray = cv2.equalizeHist(gray)

    # Slight blur before grain (simulates out of focus / optical limitations)
    if config.blur_amount > 0:
        # Ensure kernel size is odd
        kernel_size = config.blur_amount if config.blur_amount % 2 == 1 else config.blur_amount + 1
        gray = cv2.GaussianBlur(gray, (kernel_size, kernel_size), 0)

    # Add bloom/glow around bright areas (after equalization)
    if config.bloom_intensity > 0:
        _, bright = cv2.threshold(gray, config.bloom_threshold, 255, cv2.THRESH_BINARY)
        bloom = cv2.GaussianBlur(bright, (15, 15), 0)
        gray = cv2.addWeighted(gray, 1.0, bloom, config.bloom_intensity, 0)

    # Adjust contrast and brightness to shift histogram further right (brighter)
    # Apply color-specific multipliers to base values
    color_settings = config.get_color_settings()
    final_contrast_alpha = config.contrast_alpha * color_settings.contrast_multiplier
    final_contrast_beta = int(config.contrast_beta * color_settings.brightness_multiplier)

    gray = cv2.convertScaleAbs(gray, alpha=final_contrast_alpha, beta=final_contrast_beta)

    # Add vignetting (darker edges - characteristic of circular NVG view)
    if config.vignette_intensity > 0:
        rows, cols = gray.shape
        kernel_x = cv2.getGaussianKernel(cols, cols / config.vignette_intensity)
        kernel_y = cv2.getGaussianKernel(rows, rows / config.vignette_intensity)
        kernel = kernel_y * kernel_x.T
        mask = kernel / kernel.max()
        gray = (gray * mask).astype(np.uint8)

    # Add noise (grain) - characteristic of image intensifiers
    # Real NVG grain is ADDITIVE (lightening), not subtractive
    # Grain is strongest in the shadows and falls as the picture brightens,
    # which is what the device does and the reverse of v1.

    if config.noise_intensity > 0:
        # Create brightness-dependent noise mask (normalized 0-1)
        normalized_brightness = gray.astype(np.float32) / 255.0

        if config.grain_profile:
            # The measured profile, band by band. It was read off the luma of
            # tinted captures, while grain is added here to the gray image
            # before the tint. The tint scales luma by one factor, so the band
            # positions and the spreads are both carried back into gray levels
            # by it. np.interp holds the end values beyond the measured range.
            luma = (0.299 * color_settings.red_multiplier
                    + 0.587 * color_settings.green_multiplier
                    + 0.114 * color_settings.blue_multiplier)
            bands = np.asarray(config.grain_profile["brightness"], dtype=np.float32) / luma
            sigma = np.asarray(config.grain_profile["sigma"], dtype=np.float32) / luma
            brightness_mask = np.interp(normalized_brightness, bands, sigma)
        else:
            # Grain peaks in the shadows, not the mid-tones. Measured on real
            # captures through the device the profile peaks near 0.15 and falls
            # away as the picture brightens; see the module docstring for the
            # numbers. This is the one place v2 differs from v1.
            grain_peak = config.grain_peak        # brightness of the peak
            rise = config.grain_rise              # below the peak, near flat
            fall = config.grain_fall              # above it, the measured decay
            bright_threshold = 0.8                # carried over from v1, untested

            safe = np.maximum(normalized_brightness, 1e-6)
            brightness_mask = np.where(
                normalized_brightness < grain_peak,
                # Below the peak: almost flat, shaped only to avoid a hard edge
                # at pure black rather than to fit anything.
                (normalized_brightness / grain_peak) ** rise,
                # Above it: the decay the measurement shows.
                (grain_peak / safe) ** fall
            )
            # Highlights still lose grain, as in v1. No real capture here reaches
            # this far, so the term is inherited rather than measured.
            brightness_mask = np.where(
                normalized_brightness > bright_threshold,
                brightness_mask * ((1.0 - normalized_brightness)
                                   / (1.0 - bright_threshold)) ** 1.5,
                brightness_mask
            )

        # Generate brightness-dependent noise
        # The AMOUNT of grain varies (via standard deviation), not the intensity (mean stays constant)
        # This keeps grain additive/lightening but varies its quantity
        mean = config.noise_intensity  # Constant mean (always lightening)
        std_dev = config.noise_intensity * brightness_mask  # Variable amount based on brightness

        # Generate noise with spatially-varying standard deviation
        base_noise = np.random.normal(mean, 1.0, gray.shape)

        # Apply blur to noise to create larger grain particles (if grain_size > 1)
        if config.grain_size > 1:
            # Ensure kernel size is odd
            grain_kernel = config.grain_size if config.grain_size % 2 == 1 else config.grain_size + 1
            base_noise = cv2.GaussianBlur(base_noise.astype(np.float32), (grain_kernel, grain_kernel), 0)

        scaled_noise = (base_noise * std_dev).astype(np.int16)

        # Apply noise
        gray = cv2.add(gray.astype(np.int16), scaled_noise)
        gray = np.clip(gray, 0, 255).astype(np.uint8)

    # Create realistic NVG channels based on color-specific settings
    # Apply color multipliers from color settings
    red_channel = np.clip(gray * color_settings.red_multiplier, 0, 255).astype(np.uint8)
    green_channel = np.clip(gray * color_settings.green_multiplier, 0, 255).astype(np.uint8)
    blue_channel = np.clip(gray * color_settings.blue_multiplier, 0, 255).astype(np.uint8)

    # Merge channels (BGR format)
    nvg = cv2.merge([blue_channel, green_channel, red_channel])

    return nvg

def convert_to_nvg(input_folder: str, output_folder: str | None = None,
                   config: NVGConfig = None) -> None:
    """
    Convert all images in a folder to NVG style.

    Args:
        input_folder: Path to folder containing input images
        output_folder: Path to folder for output images. If None, uses input_folder
        config: NVGConfig object with effect parameters. If None, uses defaults
    """
    if config is None:
        config = NVGConfig()

    input_path: Path = Path(input_folder)
    output_path: Path = Path(output_folder) if output_folder else input_path

    # Create output folder if it doesn't exist
    output_path.mkdir(parents=True, exist_ok=True)

    # Supported image extensions
    image_extensions: set[str] = {'.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.webp'}

    # Get all image files
    image_files: List[Path] = [f for f in input_path.iterdir()
                               if f.is_file() and f.suffix.lower() in image_extensions]

    processed_count: int = 0
    skipped_count: int = 0
    failed_count: int = 0

    print(f"Found {len(image_files)} images to process")
    print(f"\nNVG Effect Settings:")
    print(f"  NVG Color:           {config.color.upper()}")
    print(f"  Noise Intensity:     {config.noise_intensity}")
    print(f"  Grain Size:          {config.grain_size}")
    print(f"  Bloom Threshold:     {config.bloom_threshold}")
    print(f"  Bloom Intensity:     {config.bloom_intensity}")
    print(f"  Blur Amount:         {config.blur_amount}")
    print(f"  Contrast Alpha:      {config.contrast_alpha}")
    print(f"  Contrast Beta:       {config.contrast_beta}")
    print(f"  Vignette Intensity:  {config.vignette_intensity}")
    print()

    for image_file in image_files:
        # Skip if filename already has NVG suffix
        if has_nvg_suffix(image_file.name, config):
            skipped_count += 1
            continue

        # Create output filename
        output_name: str = f"{image_file.stem}{config.get_suffix()}{image_file.suffix}"
        output_file_path: Path = output_path / output_name

        # Check if NVG version already exists
        if output_file_path.exists():
            skipped_count += 1
            continue

        # Process image
        try:
            # Read with OpenCV (BGR format)
            img_bgr = cv2.imread(str(image_file))

            if img_bgr is None:
                print(f"fail: Error: Could not read {image_file.name}")
                failed_count += 1
                continue

            # Apply NVG effect
            nvg_img = simulate_nvg(img_bgr, config)

            # Save with high quality
            save_params = []
            if image_file.suffix.lower() in ['.jpg', '.jpeg']:
                save_params = [cv2.IMWRITE_JPEG_QUALITY, 95]

            success = cv2.imwrite(str(output_file_path), nvg_img, save_params)

            if success:
                processed_count += 1
            else:
                print(f"fail: Failed to save: {output_name}")
                failed_count += 1

        except Exception as e:
            print(f"fail: Error processing {image_file.name}: {e}")
            failed_count += 1

    print(f"\n{'='*60}")
    print(f"=== Summary ===")
    print(f"{'='*60}")
    print(f"Processed: {processed_count}")
    print(f"Skipped: {skipped_count}")
    print(f"Failed: {failed_count}")
    print(f"Total: {processed_count + skipped_count + failed_count}")
    print(f"Output folder: {output_path.absolute()}")

if __name__ == "__main__":
    import argparse

    # Parse command-line arguments
    parser = argparse.ArgumentParser(description='Generate NVG (Night Vision Goggle) effect on images')
    parser.add_argument('input_folder', nargs='?', default=os.getcwd(),
                        help='Input folder containing images (default: current directory)')
    parser.add_argument('output_folder', nargs='?', default=None,
                        help='Output folder for processed images (default: same as input)')

    # NVG effect parameters
    parser.add_argument('--config', type=str, default=None,
                        help='json of NVGConfig fields, as AnalyzeNVG.py '
                             '--config writes. Command line flags given '
                             'explicitly still win over it')
    parser.add_argument('--color', '-c', type=str, default='white', choices=['green', 'white'],
                        help='NVG color mode: green or white (default: white)')
    parser.add_argument('--no-equalize', action='store_true',
                        help='Disable histogram equalization (reduces grain-like appearance)')
    parser.add_argument('--noise-intensity', type=float, default=None,
                        help='Grain/noise intensity 0-50 (default: 8.0)')
    parser.add_argument('--grain-size', type=int, default=None,
                        help='Grain particle size - must be odd (default: 3)')
    parser.add_argument('--bloom-threshold', type=int, default=None,
                        help='Brightness threshold for bloom 0-255 (default: 235)')
    parser.add_argument('--bloom-intensity', type=float, default=None,
                        help='Bloom glow intensity 0.0-1.0 (default: 0.08)')
    parser.add_argument('--blur-amount', type=int, default=None,
                        help='Blur kernel size - must be odd (default: 9)')
    parser.add_argument('--contrast-alpha', type=float, default=None,
                        help='Contrast adjustment 0.5-1.5 (default: 0.60)')
    parser.add_argument('--contrast-beta', type=int, default=None,
                        help='Brightness adjustment -100 to 100 (default: 40)')
    parser.add_argument('--vignette-intensity', type=float, default=None,
                        help='Vignette strength 1.0-4.0 (default: 2.2)')

    args = parser.parse_args()

    # Create config with defaults
    config = load_config(args.config) if args.config else NVGConfig()

    # Override with command-line arguments
    # The config file sets the color unless the flag was given explicitly,
    # which argparse cannot distinguish from the default, so compare against it.
    if args.color != parser.get_default("color") or not args.config:
        config.color = args.color
    config.equalize_histogram = not args.no_equalize
    if args.noise_intensity is not None:
        config.noise_intensity = args.noise_intensity
    if args.grain_size is not None:
        config.grain_size = args.grain_size
    if args.bloom_threshold is not None:
        config.bloom_threshold = args.bloom_threshold
    if args.bloom_intensity is not None:
        config.bloom_intensity = args.bloom_intensity
    if args.blur_amount is not None:
        config.blur_amount = args.blur_amount
    if args.contrast_alpha is not None:
        config.contrast_alpha = args.contrast_alpha
    if args.contrast_beta is not None:
        config.contrast_beta = args.contrast_beta
    if args.vignette_intensity is not None:
        config.vignette_intensity = args.vignette_intensity

    if not os.path.exists(args.input_folder):
        print(f"Error: Input folder '{args.input_folder}' does not exist")
        exit(1)

    print(f"Converting images to {config.color.upper()} NVG style from: {args.input_folder}")
    if args.output_folder:
        print(f"Saving NVG images to: {args.output_folder}")
    else:
        print(f"Saving NVG images to: {args.input_folder} (same as input)")
    print()

    convert_to_nvg(args.input_folder, args.output_folder, config)
