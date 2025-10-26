import os
from PIL import Image
from pathlib import Path
from typing import List

# Global configuration
GRAYSCALE_SUFFIX: str = "_grayscale"

def has_grayscale_suffix(filename: str) -> bool:
    """Check if filename contains the grayscale suffix"""
    stem: str = Path(filename).stem
    return GRAYSCALE_SUFFIX in stem

def convert_folder_to_grayscale(input_folder: str) -> None:
    """Convert all images in folder to grayscale with _grayscale suffix"""
    input_path: Path = Path(input_folder)
    
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
        output_path: Path = input_path / output_name
        
        # Check if grayscale version already exists
        if output_path.exists():
            print(f"Skipping (grayscale version exists): {image_file.name}")
            skipped_count += 1
            continue
        
        # Convert to grayscale
        try:
            img: Image.Image = Image.open(image_file)
            grayscale_img: Image.Image = img.convert('L')
            grayscale_img.save(output_path)
            print(f"Converted: {image_file.name} -> {output_name}")
            converted_count += 1
        except Exception as e:
            print(f"Error converting {image_file.name}: {e}")
    
    print(f"\n=== Summary ===")
    print(f"Converted: {converted_count}")
    print(f"Skipped: {skipped_count}")
    print(f"Total processed: {converted_count + skipped_count}")

if __name__ == "__main__":
    import sys
    
    folder_path: str
    if len(sys.argv) > 1:
        folder_path = sys.argv[1]
    else:
        folder_path = os.getcwd()  # Use current working directory
    
    if not os.path.exists(folder_path):
        print(f"Error: Folder '{folder_path}' does not exist")
    else:
        print(f"Processing images in: {folder_path}\n")
        convert_folder_to_grayscale(folder_path)