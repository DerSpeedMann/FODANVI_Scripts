import os
from PIL import Image
from pathlib import Path
from typing import List
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
        suffix="_nvg_green",
        red_multiplier=0.005,
        green_multiplier=1.0,
        blue_multiplier=0.005,
        contrast_multiplier=1.0,
        brightness_multiplier=1.0
    ),
    "white": ColorSettings(
        suffix="_nvg_white",
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

    def get_color_settings(self) -> ColorSettings:
        """Get the color settings for the current color mode"""
        return COLOR_MODES.get(self.color.lower(), COLOR_MODES["green"])

    def get_suffix(self) -> str:
        """Get the file suffix for the current color mode"""
        return self.get_color_settings().suffix


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
    # Grain should be visible mainly in mid-tones, less in dark areas, and cutoff in very bright areas

    if config.noise_intensity > 0:
        # Create brightness-dependent noise mask (normalized 0-1)
        normalized_brightness = gray.astype(np.float32) / 255.0

        # Create a bell curve for grain: low grain in dark and bright areas, peak in mid-tones
        # Use power functions to shape the distribution
        dark_threshold = 0.3  # Below this, grain decreases rapidly
        bright_threshold = 0.8  # Above this, grain decreases

        # Calculate grain mask with bell curve shape
        brightness_mask = np.where(
            normalized_brightness < dark_threshold,
            # Dark areas: quadratic falloff (very little grain in shadows)
            (normalized_brightness / dark_threshold) ** 2.5,
            np.where(
                normalized_brightness > bright_threshold,
                # Bright areas: decrease grain (bloom/saturation effect)
                ((1.0 - normalized_brightness) / (1.0 - bright_threshold)) ** 1.5,
                # Mid-tones: full grain
                1.0
            )
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
            print(f"Skipping (already NVG): {image_file.name}")
            skipped_count += 1
            continue

        # Create output filename
        output_name: str = f"{image_file.stem}{config.get_suffix()}{image_file.suffix}"
        output_file_path: Path = output_path / output_name

        # Check if NVG version already exists
        if output_file_path.exists():
            print(f"Skipping (NVG version exists): {image_file.name}")
            skipped_count += 1
            continue

        # Process image
        try:
            print(f"Processing: {image_file.name}")

            # Read with OpenCV (BGR format)
            img_bgr = cv2.imread(str(image_file))

            if img_bgr is None:
                print(f"✗ Error: Could not read {image_file.name}")
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
                print(f"✓ Saved: {output_name}")
                processed_count += 1
            else:
                print(f"✗ Failed to save: {output_name}")
                failed_count += 1

        except Exception as e:
            print(f"✗ Error processing {image_file.name}: {e}")
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
    config = NVGConfig()

    # Override with command-line arguments
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
