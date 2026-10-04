import os
from PIL import Image
from pathlib import Path
from typing import List, Tuple
import numpy as np

# Global configuration
COLOR_SHIFT_SUFFIX: str = "_blue"

def has_color_shift_suffix(filename: str) -> bool:
    """Check if filename contains the color shift suffix"""
    stem: str = Path(filename).stem
    return COLOR_SHIFT_SUFFIX in stem

def shift_green_to_blue(img_array: np.ndarray) -> np.ndarray:
    """
    Shift green channel to blue channel while preserving luminance.

    This converts green-tinted night vision images to blue-tinted images.
    The transformation preserves the overall brightness and contrast.

    Args:
        img_array: Input image as numpy array (RGB or RGBA)

    Returns:
        Color-shifted image as numpy array
    """
    # Work with a copy
    result = img_array.copy()

    # Handle RGB and RGBA
    if len(result.shape) == 2:
        # Grayscale - convert to RGB first
        result = np.stack([result, result, result], axis=-1)

    has_alpha = result.shape[2] == 4 if len(result.shape) == 3 else False

    # Extract channels
    if has_alpha:
        r, g, b, a = result[:, :, 0], result[:, :, 1], result[:, :, 2], result[:, :, 3]
    else:
        r, g, b = result[:, :, 0], result[:, :, 1], result[:, :, 2]

    # Shift green to blue
    # Strategy: Move green channel intensity to blue, reduce green
    new_r = r.copy()
    new_g = (g * 0.3).astype(np.uint8)  # Reduce green significantly
    new_b = np.clip(b.astype(np.float32) + g.astype(np.float32) * 0.7, 0, 255).astype(np.uint8)

    # Reconstruct image
    if has_alpha:
        result = np.stack([new_r, new_g, new_b, a], axis=-1)
    else:
        result = np.stack([new_r, new_g, new_b], axis=-1)

    return result

def color_shift_images(input_folder: str, output_folder: str | None = None,
                      shift_type: str = "green_to_blue") -> None:
    """
    Apply color shift to all images in a folder.

    Args:
        input_folder: Path to folder containing input images
        output_folder: Path to folder for output images. If None, uses input_folder
        shift_type: Type of color shift to apply (currently only "green_to_blue")
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
    print(f"Color shift type: {shift_type}")
    print()

    for image_file in image_files:
        # Skip if filename already has color shift suffix
        if has_color_shift_suffix(image_file.name):
            print(f"Skipping (already color-shifted): {image_file.name}")
            skipped_count += 1
            continue

        # Create output filename
        output_name: str = f"{image_file.stem}{COLOR_SHIFT_SUFFIX}{image_file.suffix}"
        output_file_path: Path = output_path / output_name

        # Check if shifted version already exists
        if output_file_path.exists():
            print(f"Skipping (shifted version exists): {image_file.name}")
            skipped_count += 1
            continue

        # Process image
        try:
            print(f"Processing: {image_file.name}")
            img: Image.Image = Image.open(image_file)

            # Convert to numpy array
            img_array: np.ndarray = np.array(img)

            # Apply color shift
            if shift_type == "green_to_blue":
                shifted_array: np.ndarray = shift_green_to_blue(img_array)
            else:
                print(f"Error: Unknown shift type '{shift_type}'")
                failed_count += 1
                continue

            # Convert back to PIL Image
            shifted_img: Image.Image = Image.fromarray(shifted_array)

            # Save with high quality
            save_kwargs = {}
            if image_file.suffix.lower() in ['.jpg', '.jpeg']:
                save_kwargs['quality'] = 95
                save_kwargs['subsampling'] = 0

            shifted_img.save(output_file_path, **save_kwargs)
            print(f"ok: Saved: {output_name}")
            processed_count += 1

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
        print(f"Processing images from: {input_folder_path}")
        if output_folder_path:
            print(f"Saving color-shifted images to: {output_folder_path}")
        else:
            print(f"Saving color-shifted images to: {input_folder_path} (same as input)")
        print()

        color_shift_images(input_folder_path, output_folder_path)
