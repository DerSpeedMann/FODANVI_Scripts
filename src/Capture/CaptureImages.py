import cv2
import time
import os
from pathlib import Path
from datetime import datetime
from typing import Optional

# ============================================================================
# GLOBAL CONFIGURATION
# ============================================================================

# Camera settings
CAMERA_INDEX: int = 0  # Change this to match your camera index from CameraFinder
RESOLUTION_WIDTH: int = 1920
RESOLUTION_HEIGHT: int = 1080

# Capture settings
NUM_IMAGES: int = 5  # Number of images to capture
DELAY_BETWEEN_CAPTURES: float = 2.0  # Delay in seconds between captures

# Output settings
OUTPUT_FOLDER: str = "captured_images"  # Folder to save images
IMAGE_PREFIX: str = "capture"  # Prefix for image filenames
IMAGE_FORMAT: str = "jpg"  # Image format (jpg, png, bmp, etc.)
JPEG_QUALITY: int = 95  # JPEG quality (0-100, only applies to jpg format)

# ============================================================================

def setup_camera(camera_index: int, width: int, height: int) -> Optional[cv2.VideoCapture]:
    """
    Initialize and configure camera

    Args:
        camera_index: Camera index to open
        width: Desired frame width
        height: Desired frame height

    Returns:
        VideoCapture object if successful, None otherwise
    """
    print(f"Opening camera at index {camera_index}...")
    cap = cv2.VideoCapture(camera_index)

    if not cap.isOpened():
        print(f"Error: Could not open camera at index {camera_index}")
        print("Run CameraFinder.py to see available cameras")
        return None

    # Set resolution
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)

    # Verify actual resolution
    actual_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    actual_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    print(f"Camera opened successfully!")
    print(f"Requested resolution: {width}x{height}")
    print(f"Actual resolution: {actual_width}x{actual_height}")

    if actual_width != width or actual_height != height:
        print(f"Warning: Camera does not support requested resolution")

    return cap

def capture_images(camera_index: int = CAMERA_INDEX,
                  num_images: int = NUM_IMAGES,
                  delay: float = DELAY_BETWEEN_CAPTURES,
                  output_folder: str = OUTPUT_FOLDER,
                  prefix: str = IMAGE_PREFIX,
                  image_format: str = IMAGE_FORMAT,
                  width: int = RESOLUTION_WIDTH,
                  height: int = RESOLUTION_HEIGHT) -> int:
    """
    Capture multiple images from camera with delay between captures

    Args:
        camera_index: Camera index to use
        num_images: Number of images to capture
        delay: Delay in seconds between captures
        output_folder: Folder to save images
        prefix: Prefix for image filenames
        image_format: Image format (jpg, png, etc.)
        width: Desired frame width
        height: Desired frame height

    Returns:
        Number of images successfully captured
    """
    # Create output folder
    output_path = Path(output_folder)
    output_path.mkdir(parents=True, exist_ok=True)

    print(f"\n{'='*80}")
    print(f"CAPTURE CONFIGURATION")
    print(f"{'='*80}")
    print(f"Camera Index:        {camera_index}")
    print(f"Number of Images:    {num_images}")
    print(f"Delay Between:       {delay} seconds")
    print(f"Output Folder:       {output_path.absolute()}")
    print(f"Image Format:        {image_format}")
    print(f"Resolution:          {width}x{height}")
    print(f"{'='*80}\n")

    # Setup camera
    cap = setup_camera(camera_index, width, height)
    if cap is None:
        return 0

    # Warm up camera
    print("Warming up camera...")
    for _ in range(5):
        cap.read()
    time.sleep(0.5)

    print(f"\nStarting capture sequence...\n")

    captured_count = 0

    try:
        for i in range(num_images):
            # Countdown
            if delay > 0 and i > 0:
                print(f"Waiting {delay} seconds...", end=" ", flush=True)
                time.sleep(delay)
                print("Ready!")

            # Capture frame
            ret, frame = cap.read()

            if not ret:
                print(f"Error: Could not capture image {i + 1}")
                continue

            # Generate filename with timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
            filename = f"{prefix}_{timestamp}.{image_format}"
            filepath = output_path / filename

            # Save image
            save_params = []
            if image_format.lower() in ['jpg', 'jpeg']:
                save_params = [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY]

            success = cv2.imwrite(str(filepath), frame, save_params)

            if success:
                file_size = os.path.getsize(filepath) / 1024  # Size in KB
                print(f"✓ [{i + 1}/{num_images}] Captured: {filename} ({file_size:.1f} KB)")
                captured_count += 1
            else:
                print(f"✗ [{i + 1}/{num_images}] Failed to save: {filename}")

    except KeyboardInterrupt:
        print("\n\nCapture interrupted by user!")
    finally:
        cap.release()
        print(f"\nCamera released")

    print(f"\n{'='*80}")
    print(f"CAPTURE COMPLETE")
    print(f"{'='*80}")
    print(f"Images Captured:     {captured_count}/{num_images}")
    print(f"Output Location:     {output_path.absolute()}")
    print(f"{'='*80}\n")

    return captured_count

if __name__ == "__main__":
    import sys

    # Parse command line arguments
    camera_idx = CAMERA_INDEX
    num_imgs = NUM_IMAGES
    delay_sec = DELAY_BETWEEN_CAPTURES

    if len(sys.argv) > 1:
        try:
            camera_idx = int(sys.argv[1])
        except ValueError:
            print(f"Error: Invalid camera index '{sys.argv[1]}'")
            print("Usage: python CaptureImages.py [camera_index] [num_images] [delay]")
            exit(1)

    if len(sys.argv) > 2:
        try:
            num_imgs = int(sys.argv[2])
        except ValueError:
            print(f"Error: Invalid number of images '{sys.argv[2]}'")
            exit(1)

    if len(sys.argv) > 3:
        try:
            delay_sec = float(sys.argv[3])
        except ValueError:
            print(f"Error: Invalid delay '{sys.argv[3]}'")
            exit(1)

    # Capture images
    captured = capture_images(
        camera_index=camera_idx,
        num_images=num_imgs,
        delay=delay_sec
    )

    # Exit with appropriate code
    exit(0 if captured > 0 else 1)
