import os
from PIL import Image
from pathlib import Path
from typing import List, Tuple
import numpy as np

# Global configuration
CROP_SUFFIX: str = "_cropped"

def has_crop_suffix(filename: str) -> bool:
    """Check if filename contains the crop suffix"""
    stem: str = Path(filename).stem
    return CROP_SUFFIX in stem

def find_circular_bounds(img_array: np.ndarray) -> Tuple[int, int, int, int] | None:
    """
    Find the bounding box of the circular night vision view.
    Returns (left, top, right, bottom) or None if not found.
    """
    # Convert to grayscale if color
    if len(img_array.shape) == 3:
        gray: np.ndarray = np.mean(img_array, axis=2).astype(np.uint8)
    else:
        gray = img_array
    
    # Find non-black pixels (threshold at 10 to account for noise)
    threshold: int = 10
    non_black: np.ndarray = gray > threshold
    
    # Find rows and columns with content
    rows_with_content: np.ndarray = np.any(non_black, axis=1)
    cols_with_content: np.ndarray = np.any(non_black, axis=0)
    
    if not np.any(rows_with_content) or not np.any(cols_with_content):
        return None
    
    # Find bounds
    top: int = int(np.argmax(rows_with_content))
    bottom: int = int(len(rows_with_content) - np.argmax(rows_with_content[::-1]))
    left: int = int(np.argmax(cols_with_content))
    right: int = int(len(cols_with_content) - np.argmax(cols_with_content[::-1]))
    
    return (left, top, right, bottom)

def crop_nvg_images(input_folder: str, output_folder: str | None = None, 
                    auto_detect: bool = True, manual_crop: Tuple[int, int, int, int] | None = None) -> None:
    """
    Crop night vision images to remove black circular borders.
    
    Args:
        input_folder: Path to folder containing input images
        output_folder: Path to folder for output images. If None, uses input_folder
        auto_detect: Automatically detect circular bounds (default True)
        manual_crop: Manual crop box as (left, top, right, bottom). Overrides auto_detect.
    """
    input_path: Path = Path(input_folder)
    output_path: Path = Path(output_folder) if output_folder else input_path
    
    # Create output folder if it doesn't exist
    output_path.mkdir(parents=True, exist_ok=True)
    
    # Supported image extensions
    image_extensions: set[str] = {'.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.webp', '.gif'}
    
    # Get all image files
    image_files: List[Path] = [f for f in input_path.iterdir() 
                               if f.is_file() and f.suffix.lower() in image_extensions]
    
    cropped_count: int = 0
    skipped_count: int = 0
    failed_count: int = 0
    
    # Store detected bounds for consistent cropping
    detected_bounds: Tuple[int, int, int, int] | None = manual_crop
    
    for image_file in image_files:
        # Skip if filename already has crop suffix
        if has_crop_suffix(image_file.name):
            print(f"Skipping (already cropped): {image_file.name}")
            skipped_count += 1
            continue
        
        # Create output filename
        output_name: str = f"{image_file.stem}{CROP_SUFFIX}{image_file.suffix}"
        output_file_path: Path = output_path / output_name
        
        # Check if cropped version already exists
        if output_file_path.exists():
            print(f"Skipping (cropped version exists): {image_file.name}")
            skipped_count += 1
            continue
        
        # Crop image
        try:
            img: Image.Image = Image.open(image_file)
            
            # Detect bounds if not already detected and auto_detect is True
            if detected_bounds is None and auto_detect:
                img_array: np.ndarray = np.array(img)
                detected_bounds = find_circular_bounds(img_array)
                
                if detected_bounds:
                    print(f"Auto-detected crop bounds: {detected_bounds}")
                else:
                    print(f"Warning: Could not auto-detect bounds for {image_file.name}")
                    failed_count += 1
                    continue
            
            if detected_bounds is None:
                print(f"Error: No crop bounds available for {image_file.name}")
                failed_count += 1
                continue
            
            # Crop the image
            cropped_img: Image.Image = img.crop(detected_bounds)
            cropped_img.save(output_file_path)
            print(f"Cropped: {image_file.name} -> {output_name}")
            cropped_count += 1
            
        except Exception as e:
            print(f"Error cropping {image_file.name}: {e}")
            failed_count += 1
    
    print(f"\n=== Summary ===")
    print(f"Cropped: {cropped_count}")
    print(f"Skipped: {skipped_count}")
    print(f"Failed: {failed_count}")
    print(f"Total processed: {cropped_count + skipped_count + failed_count}")
    print(f"Output folder: {output_path.absolute()}")
    if detected_bounds:
        print(f"Crop bounds used: {detected_bounds}")

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
            print(f"Saving cropped images to: {output_folder_path}")
        else:
            print(f"Saving cropped images to: {input_folder_path} (same as input)")
        print()
        
        # You can set manual crop bounds here if needed
        # Example: manual_bounds = (100, 100, 900, 700)
        manual_bounds: Tuple[int, int, int, int] | None = None
        
        crop_nvg_images(input_folder_path, output_folder_path, 
                       auto_detect=True, manual_crop=manual_bounds)