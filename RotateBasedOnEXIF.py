import os
from PIL import Image, ImageOps
from pathlib import Path
from typing import List

# Global configuration
ORIENTATION_FIX_SUFFIX: str = "_oriented"

def has_orientation_suffix(filename: str) -> bool:
    """Check if filename contains the orientation fix suffix"""
    stem: str = Path(filename).stem
    return ORIENTATION_FIX_SUFFIX in stem

def fix_image_orientation(input_folder: str, output_folder: str | None = None, 
                         in_place: bool = False) -> None:
    """
    Fix EXIF orientation for all images in a folder.
    
    Args:
        input_folder: Path to folder containing input images
        output_folder: Path to folder for output images. If None, uses input_folder
        in_place: If True, overwrites original files (ignores suffix). If False, creates new files with suffix.
    """
    input_path: Path = Path(input_folder)
    output_path: Path = Path(output_folder) if output_folder else input_path
    
    # Create output folder if it doesn't exist
    if not in_place:
        output_path.mkdir(parents=True, exist_ok=True)
    
    # Supported image extensions
    image_extensions: set[str] = {'.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.webp', '.gif'}
    
    # Get all image files
    image_files: List[Path] = [f for f in input_path.iterdir() 
                               if f.is_file() and f.suffix.lower() in image_extensions]
    
    fixed_count: int = 0
    skipped_count: int = 0
    no_change_count: int = 0
    
    for image_file in image_files:
        # Skip if filename already has orientation suffix (only if not in_place mode)
        if not in_place and has_orientation_suffix(image_file.name):
            print(f"Skipping (already oriented): {image_file.name}")
            skipped_count += 1
            continue
        
        # Determine output filename
        if in_place:
            output_file_path: Path = image_file
        else:
            output_name: str = f"{image_file.stem}{ORIENTATION_FIX_SUFFIX}{image_file.suffix}"
            output_file_path = output_path / output_name
            
            # Check if oriented version already exists
            if output_file_path.exists():
                print(f"Skipping (oriented version exists): {image_file.name}")
                skipped_count += 1
                continue
        
        # Fix orientation
        try:
            img: Image.Image = Image.open(image_file)
            
            # Check if image has EXIF orientation data
            has_exif_orientation: bool = False
            try:
                exif = img.getexif()
                if exif and 274 in exif:  # 274 is the orientation tag
                    has_exif_orientation = True
            except:
                pass
            
            # Apply EXIF orientation
            oriented_img: Image.Image = ImageOps.exif_transpose(img)
            
            # Check if image was actually rotated
            if oriented_img is None:
                oriented_img = img
                if not in_place:
                    print(f"No orientation change: {image_file.name}")
                    no_change_count += 1
            else:
                if has_exif_orientation:
                    print(f"{'Fixing' if in_place else 'Fixed'}: {image_file.name} -> {output_file_path.name if not in_place else 'in-place'}")
                    fixed_count += 1
                else:
                    if not in_place:
                        print(f"No EXIF orientation: {image_file.name}")
                        no_change_count += 1
            
            # Save the image
            # Preserve quality for JPEG
            save_kwargs = {}
            if image_file.suffix.lower() in ['.jpg', '.jpeg']:
                save_kwargs['quality'] = 95
                save_kwargs['subsampling'] = 0
            
            oriented_img.save(output_file_path, **save_kwargs)
            
            if not has_exif_orientation and not in_place:
                # Still count as processed even if no change
                pass
                
        except Exception as e:
            print(f"Error processing {image_file.name}: {e}")
    
    print(f"\n{'='*60}")
    print(f"=== Summary ===")
    print(f"{'='*60}")
    print(f"Fixed: {fixed_count}")
    print(f"No change needed: {no_change_count}")
    print(f"Skipped: {skipped_count}")
    print(f"Total processed: {fixed_count + no_change_count + skipped_count}")
    if not in_place:
        print(f"Output folder: {output_path.absolute()}")
    else:
        print(f"Mode: In-place (original files overwritten)")

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
            print(f"Saving oriented images to: {output_folder_path}")
        else:
            print(f"Saving oriented images to: {input_folder_path} (same as input)")
        print()
        
        fix_image_orientation(input_folder_path, output_folder_path, in_place_mode)