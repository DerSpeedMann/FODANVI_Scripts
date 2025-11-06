import os
from PIL import Image
from pathlib import Path
from typing import List
import numpy as np
import cv2

# Global configuration
NVG_SUFFIX: str = "_nvg"
NVG_COLOR: str = "white"  # "green" or "white" - sets the NVG type (white = cyan color)

# NVG Effect Parameters (Green NVG)
NOISE_INTENSITY: float = 8.0  # Grain/noise intensity (0-50) - additive grain for lightening effect
GRAIN_SIZE: int = 3  # Grain particle size (1, 3, 5, 7, etc.) - higher = coarser/larger grain
BLOOM_THRESHOLD: int = 235  # Brightness threshold for bloom effect (0-255) - minimal bloom
BLOOM_INTENSITY: float = 0.08  # Bloom glow intensity (0.0-1.0) - very subtle
BLUR_AMOUNT: int = 9  # Slight blur kernel size (must be odd: 3, 5, 7, 9, etc.) - smooths grain
CONTRAST_ALPHA: float = 0.60  # Contrast adjustment (0.5-1.5) - compress range to reduce extremes
CONTRAST_BETA: int = 40  # Brightness adjustment (-100 to 100) - shift histogram right
VIGNETTE_INTENSITY: float = 2.2  # Vignette strength (1.0-4.0, higher = stronger edge darkening)


def has_nvg_suffix(filename: str) -> bool:
    """Check if filename contains the NVG suffix"""
    stem: str = Path(filename).stem
    return NVG_SUFFIX in stem

def simulate_nvg(image: np.ndarray) -> np.ndarray:
    """
    Convert a normal image to Night Vision Goggle (NVG) style.

    This simulates the characteristic green monochrome look of NVG with:
    - Pure green monochrome (no red/blue channels)
    - Grain/noise
    - Bloom/glow around bright areas
    - Slight blur (out of focus effect)
    - Reduced contrast
    - Vignetting (darker edges)

    Args:
        image: Input image as numpy array (BGR format from OpenCV)

    Returns:
        NVG-styled image as numpy array
    """
    # Convert to grayscale
    if len(image.shape) == 3:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    else:
        gray = image

    # Normalize and enhance histogram to better match NVG distribution
    # This spreads values more evenly across the range
    gray = cv2.equalizeHist(gray)

    # Slight blur before grain (simulates out of focus / optical limitations)
    if BLUR_AMOUNT > 0:
        # Ensure kernel size is odd
        kernel_size = BLUR_AMOUNT if BLUR_AMOUNT % 2 == 1 else BLUR_AMOUNT + 1
        gray = cv2.GaussianBlur(gray, (kernel_size, kernel_size), 0)

    # Add bloom/glow around bright areas (after equalization)
    _, bright = cv2.threshold(gray, BLOOM_THRESHOLD, 255, cv2.THRESH_BINARY)
    bloom = cv2.GaussianBlur(bright, (15, 15), 0)
    gray = cv2.addWeighted(gray, 1.0, bloom, BLOOM_INTENSITY, 0)

    # Adjust contrast and brightness to shift histogram further right (brighter)
    # White NVG uses higher brightness and similar contrast to green NVG
    contrast_alpha = CONTRAST_ALPHA
    contrast_beta = CONTRAST_BETA
    if NVG_COLOR.lower() == "white":
        # White NVG: keep contrast similar, increase brightness by ~25%
        contrast_alpha = CONTRAST_ALPHA * 1.0
        contrast_beta = int(CONTRAST_BETA * 1.25)

    gray = cv2.convertScaleAbs(gray, alpha=contrast_alpha, beta=contrast_beta)

    # Add vignetting (darker edges - characteristic of circular NVG view)
    rows, cols = gray.shape
    kernel_x = cv2.getGaussianKernel(cols, cols / VIGNETTE_INTENSITY)
    kernel_y = cv2.getGaussianKernel(rows, rows / VIGNETTE_INTENSITY)
    kernel = kernel_y * kernel_x.T
    mask = kernel / kernel.max()
    gray = (gray * mask).astype(np.uint8)

    # Add noise (grain) - characteristic of image intensifiers
    # Real NVG grain is ADDITIVE (lightening), not subtractive
    # Grain should be visible mainly in mid-tones, less in dark areas, and cutoff in very bright areas

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
    mean = NOISE_INTENSITY  # Constant mean (always lightening)
    std_dev = NOISE_INTENSITY * brightness_mask  # Variable amount based on brightness

    # Generate noise with spatially-varying standard deviation
    base_noise = np.random.normal(mean, 1.0, gray.shape)

    # Apply blur to noise to create larger grain particles (if GRAIN_SIZE > 1)
    if GRAIN_SIZE > 1:
        # Ensure kernel size is odd
        grain_kernel = GRAIN_SIZE if GRAIN_SIZE % 2 == 1 else GRAIN_SIZE + 1
        base_noise = cv2.GaussianBlur(base_noise.astype(np.float32), (grain_kernel, grain_kernel), 0)

    scaled_noise = (base_noise * std_dev).astype(np.int16)

    # Apply noise
    gray = cv2.add(gray.astype(np.int16), scaled_noise)
    gray = np.clip(gray, 0, 255).astype(np.uint8)

    # Create realistic NVG channels based on real histogram analysis
    # Support green and white (cyan-colored) NVG types

    if NVG_COLOR.lower() == "white":
        # White NVG (very desaturated - nearly equal RGB with subtle cyan shift)
        # Histogram shows all channels close together with slight separation
        blue_channel = gray
        green_channel = gray

        # Red channel: reduce to 60% of gray for more visible cyan tint
        # Creates cyan tint while keeping it mostly neutral
        red_channel = np.clip(gray * 0.60, 0, 255).astype(np.uint8)

    else:  # Default green NVG
        # Green channel: main image data (centered, not too spread)
        green_channel = gray

        # Red channel: minimal red (most values should be 0-3)
        # Real NVG shows red spike at very lowest values (0-3 range)
        red_channel = np.clip(gray * 0.005, 0, 3).astype(np.uint8)

        # Blue channel: slight blue cast (shifted further right, 6-20 range)
        # Real NVG shows blue distribution significantly higher than red
        blue_channel = np.clip(gray * 0.04 + 6, 6, 20).astype(np.uint8)

    # Merge channels (BGR format)
    nvg = cv2.merge([blue_channel, green_channel, red_channel])

    return nvg

def convert_to_nvg(input_folder: str, output_folder: str | None = None) -> None:
    """
    Convert all images in a folder to NVG style.

    Args:
        input_folder: Path to folder containing input images
        output_folder: Path to folder for output images. If None, uses input_folder
    """
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
    print(f"  NVG Color:           {NVG_COLOR.upper()}")
    print(f"  Noise Intensity:     {NOISE_INTENSITY}")
    print(f"  Grain Size:          {GRAIN_SIZE}")
    print(f"  Bloom Threshold:     {BLOOM_THRESHOLD}")
    print(f"  Bloom Intensity:     {BLOOM_INTENSITY}")
    print(f"  Blur Amount:         {BLUR_AMOUNT}")
    print(f"  Contrast Alpha:      {CONTRAST_ALPHA}")
    print(f"  Contrast Beta:       {CONTRAST_BETA}")
    print(f"  Vignette Intensity:  {VIGNETTE_INTENSITY}")
    print()

    for image_file in image_files:
        # Skip if filename already has NVG suffix
        if has_nvg_suffix(image_file.name):
            print(f"Skipping (already NVG): {image_file.name}")
            skipped_count += 1
            continue

        # Create output filename
        output_name: str = f"{image_file.stem}{NVG_SUFFIX}{image_file.suffix}"
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
            nvg_img = simulate_nvg(img_bgr)

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
    import sys

    input_folder_path: str
    output_folder_path: str | None = None

    if len(sys.argv) > 1:
        input_folder_path = sys.argv[1]
        if len(sys.argv) > 2:
            output_folder_path = sys.argv[2]
    else:
        input_folder_path = os.getcwd()

    if not os.path.exists(input_folder_path):
        print(f"Error: Input folder '{input_folder_path}' does not exist")
    else:
        print(f"Converting images to NVG style from: {input_folder_path}")
        if output_folder_path:
            print(f"Saving NVG images to: {output_folder_path}")
        else:
            print(f"Saving NVG images to: {input_folder_path} (same as input)")
        print()

        convert_to_nvg(input_folder_path, output_folder_path)
