import os
from PIL import Image, ImageOps
from pathlib import Path
from typing import List

# Global configuration
GRAYSCALE_SUFFIX: str = "_grayscale"

def has_grayscale_suffix(filename: str) -> bool:
    """Check if filename contains the grayscale suffix"""
    stem: str = Path(filename).stem
    return GRAYSCALE_SUFFIX in stem

def convert_folder_to_grayscale(input_folder: str, output_folder: str | None = None) -> None:
    """Convert all images in folder to grayscale with _grayscale suffix
    
    Args:
        input_folder: Path to folder containing input images
        output_folder: Path to folder for output images. If None, uses input_folder
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
    
    converted_count: int = 0
    skipped_count: int = 0
    
    for image_file in image_files:
        # Skip if filename already has grayscale suffix
        if has_grayscale_suffix(image_file.name):
            print(f"Skipping (already grayscale version): {image_file.name}")
            skipped_count += 1
            continue
        
        # Create output filename
        output_name: str = f"{image_file.stem}{GRAYSCALE_SUFFIX}{image_file.suffix}"
        output_file_path: Path = output_path / output_name
        
        # Check if grayscale version already exists in output folder
        if output_file_path.exists():
            print(f"Skipping (grayscale version exists): {image_file.name}")
            skipped_count += 1
            continue
        
        # Convert to grayscale
        try:
            img: Image.Image = ImageOps.exif_transpose(Image.open(image_file))
            grayscale_img: Image.Image = img.convert('L').convert('RGB')
            grayscale_img.save(output_file_path)
            print(f"Converted: {image_file.name} -> {output_name}")
            converted_count += 1
        except Exception as e:
            print(f"Error converting {image_file.name}: {e}")
    
    print(f"\n=== Summary ===")
    print(f"Converted: {converted_count}")
    print(f"Skipped: {skipped_count}")
    print(f"Total processed: {converted_count + skipped_count}")
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
        input_folder_path = os.getcwd()  # Use current working directory
    
    if not os.path.exists(input_folder_path):
        print(f"Error: Input folder '{input_folder_path}' does not exist")
    else:
        print(f"Processing images from: {input_folder_path}")
        if output_folder_path:
            print(f"Saving grayscale images to: {output_folder_path}")
        else:
            print(f"Saving grayscale images to: {input_folder_path} (same as input)")
        print()
        convert_folder_to_grayscale(input_folder_path, output_folder_path)