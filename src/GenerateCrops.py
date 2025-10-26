import os
from PIL import Image
from pathlib import Path
from typing import List, Tuple
import numpy as np
from scipy import ndimage

# Global configuration
CROP_SUFFIX: str = "_cropped"
# Percentage to crop from each edge to remove vignetting (0.0 to 0.5)
VIGNETTE_CROP_PERCENT: float = 0.05

def has_crop_suffix(filename: str) -> bool:
    """Check if filename contains the crop suffix"""
    stem: str = Path(filename).stem
    return CROP_SUFFIX in stem

def find_largest_component_bounds(img_array: np.ndarray, threshold: int = 30) -> Tuple[int, int, int, int] | None:
    """
    Find the bounding box of the largest connected non-black component.
    Returns (left, top, right, bottom) or None if not found.
    """
    # Convert to grayscale if color
    if len(img_array.shape) == 3:
        gray: np.ndarray = np.mean(img_array, axis=2).astype(np.uint8)
    else:
        gray = img_array
    
    print(f"Image shape: {img_array.shape}")
    print(f"Min pixel value: {np.min(gray)}, Max pixel value: {np.max(gray)}")
    print(f"Mean pixel value: {np.mean(gray):.1f}")
    
    # Create binary mask of non-black pixels with higher threshold
    binary_mask: np.ndarray = gray > threshold
    
    print(f"Non-black pixels (threshold={threshold}): {np.sum(binary_mask)}")
    
    # Apply morphological closing to fill small holes
    from scipy.ndimage import binary_closing
    binary_mask = binary_closing(binary_mask, structure=np.ones((5, 5)))
    
    # Label connected components
    labeled_array: np.ndarray
    num_features: int
    labeled_array, num_features = ndimage.label(binary_mask)
    
    print(f"Found {num_features} connected components")
    
    if num_features == 0:
        print("No components detected!")
        return None
    
    # Find the largest component
    component_sizes: np.ndarray = np.bincount(labeled_array.ravel())
    component_sizes[0] = 0  # Ignore background (label 0)
    
    largest_component_label: int = int(np.argmax(component_sizes))
    largest_component_size: int = int(component_sizes[largest_component_label])
    
    print(f"Largest component: label={largest_component_label}, size={largest_component_size} pixels")
    
    # Create mask of largest component
    largest_component_mask: np.ndarray = labeled_array == largest_component_label
    
    # Find bounding box of largest component
    rows: np.ndarray = np.any(largest_component_mask, axis=1)
    cols: np.ndarray = np.any(largest_component_mask, axis=0)
    
    if not np.any(rows) or not np.any(cols):
        print("Could not find bounds of largest component!")
        return None
    
    top: int = int(np.argmax(rows))
    bottom: int = int(len(rows) - np.argmax(rows[::-1]))
    left: int = int(np.argmax(cols))
    right: int = int(len(cols) - np.argmax(cols[::-1]))
    
    # Apply vignette cropping - remove edges to eliminate dark circular border
    width: int = right - left
    height: int = bottom - top
    
    crop_pixels_horizontal: int = int(width * VIGNETTE_CROP_PERCENT)
    crop_pixels_vertical: int = int(height * VIGNETTE_CROP_PERCENT)
    
    left += crop_pixels_horizontal
    right -= crop_pixels_horizontal
    top += crop_pixels_vertical
    bottom -= crop_pixels_vertical
    
    print(f"Initial bounds: left={left-crop_pixels_horizontal}, top={top-crop_pixels_vertical}, right={right+crop_pixels_horizontal}, bottom={bottom+crop_pixels_vertical}")
    print(f"After vignette crop: left={left}, top={top}, right={right}, bottom={bottom}")
    print(f"Final crop dimensions: {right-left}x{bottom-top}")
    
    return (left, top, right, bottom)

def crop_nvg_images(input_folder: str, output_folder: str | None = None, 
                    threshold: int = 30, per_image_detection: bool = False,
                    manual_crop: Tuple[int, int, int, int] | None = None) -> None:
    """
    Crop night vision images to remove black circular borders.
    
    Args:
        input_folder: Path to folder containing input images
        output_folder: Path to folder for output images. If None, uses input_folder
        threshold: Pixel brightness threshold for detecting non-black areas (default 30)
        per_image_detection: If True, detect bounds for each image separately. If False, use first image bounds for all.
        manual_crop: Manual crop box as (left, top, right, bottom). Overrides auto-detection.
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
    
    # Store detected bounds
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
            
            # Detect bounds if needed
            if detected_bounds is None or per_image_detection:
                print(f"\n{'='*60}")
                print(f"Processing: {image_file.name}")
                print(f"{'='*60}")
                img_array: np.ndarray = np.array(img)
                current_bounds: Tuple[int, int, int, int] | None = find_largest_component_bounds(img_array, threshold)
                
                if current_bounds:
                    print(f"✓ Auto-detected crop bounds: {current_bounds}\n")
                    if not per_image_detection:
                        detected_bounds = current_bounds
                else:
                    print(f"✗ Could not auto-detect bounds for {image_file.name}\n")
                    failed_count += 1
                    continue
            else:
                current_bounds = detected_bounds
            
            if current_bounds is None:
                print(f"Error: No crop bounds available for {image_file.name}")
                failed_count += 1
                continue
            
            # Crop the image
            cropped_img: Image.Image = img.crop(current_bounds)
            cropped_img.save(output_file_path)
            print(f"✓ Cropped: {image_file.name} -> {output_name}")
            cropped_count += 1
            
        except Exception as e:
            print(f"✗ Error cropping {image_file.name}: {e}")
            failed_count += 1
    
    print(f"\n{'='*60}")
    print(f"=== Summary ===")
    print(f"{'='*60}")
    print(f"Cropped: {cropped_count}")
    print(f"Skipped: {skipped_count}")
    print(f"Failed: {failed_count}")
    print(f"Total processed: {cropped_count + skipped_count + failed_count}")
    print(f"Output folder: {output_path.absolute()}")
    if detected_bounds and not per_image_detection:
        print(f"Crop bounds used for all images: {detected_bounds}")

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
        
        # Use higher threshold (30) and detect per image if they vary
        crop_nvg_images(input_folder_path, output_folder_path, 
                       threshold=30, per_image_detection=True)