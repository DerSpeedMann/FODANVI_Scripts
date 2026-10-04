import os
from pathlib import Path
from typing import List
import shutil

def copy_files_with_suffix(input_folder: str, output_folder: str, suffix: str) -> None:
    """
    Copy files from input folder to output folder, adding a suffix to the filename.

    Args:
        input_folder: Path to folder containing input files
        output_folder: Path to folder for output files
        suffix: Suffix to add to filenames (e.g., "_nvg_white", "_processed")
    """
    input_path: Path = Path(input_folder)
    output_path: Path = Path(output_folder)

    # Create output folder if it doesn't exist
    output_path.mkdir(parents=True, exist_ok=True)

    # Get all files (excluding directories)
    files: List[Path] = [f for f in input_path.iterdir() if f.is_file()]

    copied_count: int = 0
    skipped_count: int = 0
    failed_count: int = 0

    print(f"Found {len(files)} files to process")
    print(f"Suffix to add: '{suffix}'")
    print()

    for file in files:
        # Check if filename already has suffix
        if suffix in file.stem:
            print(f"Skipping (already has suffix): {file.name}")
            skipped_count += 1
            continue

        # Create output filename with suffix
        output_name: str = f"{file.stem}{suffix}{file.suffix}"
        output_file_path: Path = output_path / output_name

        # Check if output file already exists
        if output_file_path.exists():
            print(f"Skipping (output exists): {output_name}")
            skipped_count += 1
            continue

        # Copy file
        try:
            print(f"Copying: {file.name} -> {output_name}")
            shutil.copy2(file, output_file_path)
            copied_count += 1
        except Exception as e:
            print(f"fail: Error copying {file.name}: {e}")
            failed_count += 1

    print(f"\n{'='*60}")
    print(f"=== Summary ===")
    print(f"{'='*60}")
    print(f"Copied: {copied_count}")
    print(f"Skipped: {skipped_count}")
    print(f"Failed: {failed_count}")
    print(f"Total: {copied_count + skipped_count + failed_count}")
    print(f"Output folder: {output_path.absolute()}")

if __name__ == "__main__":
    import sys

    # Check for required arguments
    if len(sys.argv) < 4:
        print("Error: Missing required arguments")
        print("Usage: python CopyFilesWithSuffix.py <input_folder> <output_folder> <suffix>")
        print()
        print("Example:")
        print("  python CopyFilesWithSuffix.py ./labels ./labels_nvg _nvg_white")
        exit(1)

    input_folder_path: str = sys.argv[1]
    output_folder_path: str = sys.argv[2]
    suffix: str = sys.argv[3]

    if not os.path.exists(input_folder_path):
        print(f"Error: Input folder '{input_folder_path}' does not exist")
        exit(1)

    print(f"Copying files from: {input_folder_path}")
    print(f"Saving copied files to: {output_folder_path}")
    print(f"Adding suffix: '{suffix}'")
    print()

    copy_files_with_suffix(input_folder_path, output_folder_path, suffix)
