import os
from PIL import Image
from pathlib import Path
from typing import List
import numpy as np
import cv2

# Global configuration
NVG_SUFFIX: str = "_nvg"

# NVG Effect Parameters
NOISE_INTENSITY: float = 25.0  # Grain/noise intensity (0-50)
BLOOM_THRESHOLD: int = 200  # Brightness threshold for bloom effect (0-255)
BLOOM_INTENSITY: float = 0.3  # Bloom glow intensity (0.0-1.0)
BLUR_AMOUNT: int = 3  # Slight blur kernel size (must be odd: 3, 5, 7, etc.)
CONTRAST_ALPHA: float = 0.9  # Contrast adjustment (0.5-1.5)
CONTRAST_BETA: int = 10  # Brightness adjustment (-100 to 100)
VIGNETTE_INTENSITY: float = 2.0  # Vignette strength (1.0-4.0, higher = stronger edge darkening)

def has_nvg_suffix(filename: str) -> bool:
    """Check if filename contains the NVG suffix"""
    stem: str = Path(filename).stem
    return NVG_SUFFIX in stem

def simulate_nvg(image: np.ndarray) -> np.ndarray:
    """
    Convert a normal image to Night Vision Goggle (NVG) style.

    This simulates the characteristic green monochrome look of NVG with:
    - Green monochrome tint
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

    # Add green tint (green channel only)
    nvg = cv2.merge([np.zeros_like(gray), gray, np.zeros_like(gray)])

    # Add noise (grain) - characteristic of image intensifiers
    noise = np.random.normal(0, NOISE_INTENSITY, nvg.shape).astype(np.int16)
    nvg = cv2.add(nvg.astype(np.int16), noise)
    nvg = np.clip(nvg, 0, 255).astype(np.uint8)

    # Add bloom/glow around bright areas
    _, bright = cv2.threshold(gray, BLOOM_THRESHOLD, 255, cv2.THRESH_BINARY)
    bloom = cv2.GaussianBlur(bright, (15, 15), 0)
    bloom_overlay = cv2.merge([np.zeros_like(bloom), bloom, np.zeros_like(bloom)])
    nvg = cv2.addWeighted(nvg, 1.0, bloom_overlay, BLOOM_INTENSITY, 0)

    # Slight blur (simulates out of focus / optical limitations)
    if BLUR_AMOUNT > 0:
        # Ensure kernel size is odd
        kernel_size = BLUR_AMOUNT if BLUR_AMOUNT % 2 == 1 else BLUR_AMOUNT + 1
        nvg = cv2.GaussianBlur(nvg, (kernel_size, kernel_size), 0)

    # Reduce contrast slightly and adjust brightness
    nvg = cv2.convertScaleAbs(nvg, alpha=CONTRAST_ALPHA, beta=CONTRAST_BETA)

    # Add vignetting (darker edges - characteristic of circular NVG view)
    rows, cols = gray.shape
    kernel_x = cv2.getGaussianKernel(cols, cols / VIGNETTE_INTENSITY)
    kernel_y = cv2.getGaussianKernel(rows, rows / VIGNETTE_INTENSITY)
    kernel = kernel_y * kernel_x.T
    mask = kernel / kernel.max()

    # Apply vignette to all channels
    nvg = (nvg * np.stack([mask] * 3, axis=2)).astype(np.uint8)

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
    print(f"  Noise Intensity:     {NOISE_INTENSITY}")
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
