import os
from PIL import Image, ImageOps
from pathlib import Path
from typing import List, Tuple
import numpy as np
import cv2
import math

# Global configuration
CROP_SUFFIX: str = "_cropped"
# Radius reduction factor to exclude vignette (0.0 = no reduction, 0.1 = 10% smaller radius)
RADIUS_REDUCTION_FACTOR: float = 0.10

def has_crop_suffix(filename: str) -> bool:
    """Check if filename contains the crop suffix"""
    stem: str = Path(filename).stem
    return CROP_SUFFIX in stem

def find_circular_nvg_bounds(img_array: np.ndarray) -> Tuple[int, int, int, int] | None:
    """
    Find the circular NVG view boundary using contour detection.
    Returns (left, top, right, bottom) or None if not found.
    """
    # Convert to grayscale if color
    if len(img_array.shape) == 3:
        gray: np.ndarray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
    else:
        gray = img_array

    height, width = gray.shape
    print(f"Image shape: {img_array.shape}")
    print(f"Min: {np.min(gray)}, Max: {np.max(gray)}, Mean: {np.mean(gray):.1f}")

    # Apply blur to reduce noise
    blurred: np.ndarray = cv2.GaussianBlur(gray, (5, 5), 0)

    # Use a very low fixed threshold to capture the full NVG circular region
    # The objective lens area should be brighter than the surrounding black border
    # We use a low threshold (5-10) to include dimmer edges of the lens
    _, binary = cv2.threshold(blurred, 8, 255, cv2.THRESH_BINARY)

    # Apply morphological closing to fill small gaps and smooth the boundary
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15))
    binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)

    print(f"Binary mask coverage: {np.mean(binary > 0) * 100:.1f}%")

    # Find contours
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    if not contours:
        print("No contours found")
    else:
        print(f"Found {len(contours)} contours")

        # Find the largest contour by area
        largest_contour = max(contours, key=cv2.contourArea)
        area = cv2.contourArea(largest_contour)
        print(f"Largest contour area: {area} pixels")

        # Get the minimum enclosing circle
        (cx, cy), radius = cv2.minEnclosingCircle(largest_contour)
        center_x = int(cx)
        center_y = int(cy)
        detected_radius = int(radius)

        # Verify this looks like a reasonable circle (area should be close to pi*r^2)
        expected_area = math.pi * detected_radius * detected_radius
        area_ratio = area / expected_area if expected_area > 0 else 0
        print(f"Detected circle: center=({center_x}, {center_y}), radius={detected_radius}")
        print(f"Contour area vs circle area: {area_ratio:.2f} (1.0 = perfect circle)")

        # Accept if contour fills at least 50% of the enclosing circle
        if area_ratio >= 0.5:
            # Apply radius reduction to exclude vignette
            cropped_radius: int = int(detected_radius * (1.0 - RADIUS_REDUCTION_FACTOR))

            print(f"Reduced radius by {RADIUS_REDUCTION_FACTOR*100:.1f}%: {detected_radius} -> {cropped_radius}")

            # Calculate inscribed square inside the circle
            half_side: int = int(cropped_radius / math.sqrt(2))

            left: int = max(0, center_x - half_side)
            top: int = max(0, center_y - half_side)
            right: int = min(width, center_x + half_side)
            bottom: int = min(height, center_y + half_side)

            print(f"Inscribed square half-side length: {half_side} (from radius {cropped_radius})")
            print(f"Bounding box: left={left}, top={top}, right={right}, bottom={bottom}")
            print(f"Crop dimensions: {right-left}x{bottom-top}")

            return (left, top, right, bottom)

        print(f"Contour doesn't look circular enough (ratio={area_ratio:.2f})")

    print("Contour detection failed, falling back to brightness-based detection")
    
    # Fallback: use brightness threshold
    threshold: int = 15
    binary_mask: np.ndarray = gray > threshold
    
    rows: np.ndarray = np.any(binary_mask, axis=1)
    cols: np.ndarray = np.any(binary_mask, axis=0)
    
    if not np.any(rows) or not np.any(cols):
        return None
    
    top_bound: int = int(np.argmax(rows))
    bottom_bound: int = int(len(rows) - np.argmax(rows[::-1]))
    left_bound: int = int(np.argmax(cols))
    right_bound: int = int(len(cols) - np.argmax(cols[::-1]))
    
    # Estimate center and radius
    center_x = (left_bound + right_bound) // 2
    center_y = (top_bound + bottom_bound) // 2
    radius_x: int = (right_bound - left_bound) // 2
    radius_y: int = (bottom_bound - top_bound) // 2
    estimated_radius: int = min(radius_x, radius_y)
    
    # Apply radius reduction
    cropped_radius = int(estimated_radius * (1.0 - RADIUS_REDUCTION_FACTOR))

    print(f"Fallback - estimated center=({center_x}, {center_y}), radius={estimated_radius}")
    print(f"Reduced radius by {RADIUS_REDUCTION_FACTOR*100:.1f}%: {estimated_radius} -> {cropped_radius}")

    # Calculate inscribed square inside the circle
    half_side = int(cropped_radius / math.sqrt(2))

    left = max(0, center_x - half_side)
    right = min(width, center_x + half_side)
    top = max(0, center_y - half_side)
    bottom = min(height, center_y + half_side)

    print(f"Fallback - inscribed square half-side length: {half_side} (from radius {cropped_radius})")
    print(f"Fallback bounds: left={left}, top={top}, right={right}, bottom={bottom}")
    
    return (left, top, right, bottom)

def crop_nvg_images(input_folder: str, output_folder: str | None = None, 
                    per_image_detection: bool = True,
                    manual_crop: Tuple[int, int, int, int] | None = None) -> None:
    """
    Crop night vision images to remove black circular borders.
    
    Args:
        input_folder: Path to folder containing input images
        output_folder: Path to folder for output images. If None, uses input_folder
        per_image_detection: If True, detect bounds for each image separately
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
            # A phone writes the rotation into EXIF rather than into the
            # pixels, and Image.open hands back the stored orientation, so
            # without this the circle is detected in a sideways frame and
            # the inscribed square is clipped by the edge. cv2.imread
            # applies the tag; PIL does not.
            img: Image.Image = ImageOps.exif_transpose(Image.open(image_file))
            
            # Detect bounds if needed
            if detected_bounds is None or per_image_detection:
                print(f"\n{'='*60}")
                print(f"Processing: {image_file.name}")
                print(f"{'='*60}")
                img_array: np.ndarray = np.array(img)
                current_bounds: Tuple[int, int, int, int] | None = find_circular_nvg_bounds(img_array)
                
                if current_bounds:
                    print(f"ok: Detected crop bounds: {current_bounds}\n")
                    if not per_image_detection:
                        detected_bounds = current_bounds
                else:
                    print(f"fail: Could not detect bounds for {image_file.name}\n")
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
            print(f"ok: Cropped: {image_file.name} -> {output_name}")
            cropped_count += 1
            
        except Exception as e:
            print(f"fail: Error cropping {image_file.name}: {e}")
            failed_count += 1
    
    print(f"\n{'='*60}")
    print(f"=== Summary ===")
    print(f"{'='*60}")
    print(f"Cropped: {cropped_count}")
    print(f"Skipped: {skipped_count}")
    print(f"Failed: {failed_count}")
    print(f"Total processed: {cropped_count + skipped_count + failed_count}")
    print(f"Output folder: {output_path.absolute()}")
    print(f"Radius reduction applied: {RADIUS_REDUCTION_FACTOR*100:.1f}%")
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
        
        crop_nvg_images(input_folder_path, output_folder_path, per_image_detection=True)