import os
from PIL import Image, ImageEnhance
from pathlib import Path
from typing import List
import numpy as np
import cv2

PROCESSED_SUFFIX: str = "_processed"

def enhance_nvg_image(img_array: np.ndarray) -> np.ndarray:
    """
    Enhance NVG image while preserving color information
    """
    # Handle grayscale images
    if len(img_array.shape) == 2:
        # Grayscale processing
        equalized = cv2.equalizeHist(img_array)
        clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8,8))
        enhanced = clahe.apply(equalized)
        denoised = cv2.fastNlMeansDenoising(enhanced, None, h=10, templateWindowSize=7, searchWindowSize=21)
        # Convert to RGB by duplicating channel
        return cv2.cvtColor(denoised, cv2.COLOR_GRAY2RGB)

    # Color image processing - preserve color!
    img_bgr = cv2.cvtColor(img_array, cv2.COLOR_RGB2BGR)

    # Apply CLAHE to each color channel separately to preserve color
    # Convert to LAB color space to enhance only luminance
    lab = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)

    # Apply CLAHE to L channel (luminance) only
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8,8))
    l_enhanced = clahe.apply(l)

    # Merge back
    lab_enhanced = cv2.merge([l_enhanced, a, b])
    enhanced_bgr = cv2.cvtColor(lab_enhanced, cv2.COLOR_LAB2BGR)

    # Denoise in color
    denoised = cv2.fastNlMeansDenoisingColored(enhanced_bgr, None, h=10, hColor=10,
                                                templateWindowSize=7, searchWindowSize=21)

    # Convert back to RGB
    return cv2.cvtColor(denoised, cv2.COLOR_BGR2RGB)

def process_images_for_detection(input_folder: str, output_folder: str | None = None) -> None:
    """Preprocess NVG images to improve detection rates"""
    input_path: Path = Path(input_folder)
    output_path: Path = Path(output_folder) if output_folder else input_path
    
    output_path.mkdir(parents=True, exist_ok=True)
    
    image_extensions: set[str] = {'.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.webp'}
    image_files: List[Path] = [f for f in input_path.iterdir() 
                               if f.is_file() and f.suffix.lower() in image_extensions]
    
    processed_count: int = 0
    
    for image_file in image_files:
        if PROCESSED_SUFFIX in image_file.stem:
            continue
            
        output_name: str = f"{image_file.stem}{PROCESSED_SUFFIX}{image_file.suffix}"
        output_file_path: Path = output_path / output_name
        
        if output_file_path.exists():
            print(f"Skipping (already processed): {image_file.name}")
            continue
        
        try:
            img: Image.Image = Image.open(image_file)
            img_array: np.ndarray = np.array(img)
            
            # Enhance the image
            enhanced_array: np.ndarray = enhance_nvg_image(img_array)
            
            # Convert back to PIL
            enhanced_img: Image.Image = Image.fromarray(enhanced_array)
            
            # Save
            enhanced_img.save(output_file_path, quality=95)
            print(f"Processed: {image_file.name} -> {output_name}")
            processed_count += 1
            
        except Exception as e:
            print(f"Error processing {image_file.name}: {e}")
    
    print(f"\n=== Summary ===")
    print(f"Processed: {processed_count}")
    print(f"Output: {output_path.absolute()}")

if __name__ == "__main__":
    import sys
    
    input_folder_path: str
    output_folder_path: str | None = None
    in_place_mode: bool = False
    
    if len(sys.argv) > 1:
        input_folder_path = sys.argv[1]
        
        # Check for --in-place flag
        if '--in-place' in sys.argv:
            in_place_mode = True
            print("WARNING: In-place mode enabled - original files will be overwritten!")
            response: str = input("Continue? (yes/no): ")
            if response.lower() not in ['yes', 'y']:
                print("Aborted.")
                exit(0)
        elif len(sys.argv) > 2 and sys.argv[2] != '--in-place':
            output_folder_path = sys.argv[2]
    else:
        input_folder_path = os.getcwd()
    
    if not os.path.exists(input_folder_path):
        print(f"Error: Input folder '{input_folder_path}' does not exist")
    else:
        print(f"Processing images from: {input_folder_path}")
        if in_place_mode:
            print(f"Mode: In-place (will overwrite originals)")
        elif output_folder_path:
            print(f"Saving processed images to: {output_folder_path}")
        else:
            print(f"Saving processed images to: {input_folder_path} (same as input)")
        print()
        
    process_images_for_detection(input_folder_path, output_folder_path)