import cv2
from typing import List, Dict, Any

# Global configuration
MAX_CAMERAS_TO_CHECK: int = 10  # Maximum number of camera indices to check

def get_camera_properties(cap: cv2.VideoCapture) -> Dict[str, Any]:
    """
    Get detailed properties of a camera

    Args:
        cap: OpenCV VideoCapture object

    Returns:
        Dictionary with camera properties
    """
    properties = {}

    # Try to get a frame to determine actual resolution
    ret, frame = cap.read()
    if ret:
        properties['actual_width'] = frame.shape[1]
        properties['actual_height'] = frame.shape[0]
        properties['channels'] = frame.shape[2] if len(frame.shape) == 3 else 1

    # Get camera properties
    properties['width'] = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    properties['height'] = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    properties['fps'] = cap.get(cv2.CAP_PROP_FPS)
    properties['brightness'] = cap.get(cv2.CAP_PROP_BRIGHTNESS)
    properties['contrast'] = cap.get(cv2.CAP_PROP_CONTRAST)
    properties['saturation'] = cap.get(cv2.CAP_PROP_SATURATION)
    properties['hue'] = cap.get(cv2.CAP_PROP_HUE)
    properties['gain'] = cap.get(cv2.CAP_PROP_GAIN)
    properties['exposure'] = cap.get(cv2.CAP_PROP_EXPOSURE)

    # Additional properties
    properties['backend'] = cap.getBackendName()
    properties['fourcc'] = int(cap.get(cv2.CAP_PROP_FOURCC))

    # Try to get format
    try:
        properties['format'] = cap.get(cv2.CAP_PROP_FORMAT)
    except:
        properties['format'] = 'N/A'

    # Buffer size
    try:
        properties['buffer_size'] = int(cap.get(cv2.CAP_PROP_BUFFERSIZE))
    except:
        properties['buffer_size'] = 'N/A'

    return properties

def find_all_cameras(max_cameras: int = MAX_CAMERAS_TO_CHECK, verbose: bool = True) -> List[Dict[str, Any]]:
    """
    Find all available USB cameras and gather their information

    Args:
        max_cameras: Maximum number of camera indices to check
        verbose: Print detailed information while searching

    Returns:
        List of dictionaries containing camera information
    """
    cameras = []

    if verbose:
        print("=" * 80)
        print("SEARCHING FOR CAMERAS")
        print("=" * 80)
        print(f"Checking camera indices 0 to {max_cameras - 1}...\n")

    for i in range(max_cameras):
        if verbose:
            print(f"Checking index {i}...", end=" ")

        cap = cv2.VideoCapture(i)

        if cap.isOpened():
            ret, frame = cap.read()
            if ret:
                if verbose:
                    print("FOUND!")

                properties = get_camera_properties(cap)
                camera_info = {
                    'index': i,
                    'properties': properties
                }
                cameras.append(camera_info)

                if verbose:
                    print(f"  Backend: {properties['backend']}")
                    print(f"  Resolution: {properties['actual_width']}x{properties['actual_height']}")
                    print(f"  FPS: {properties['fps']}")
                    print(f"  Channels: {properties['channels']}")
                    print()
            else:
                if verbose:
                    print("Not accessible")

            cap.release()
        else:
            if verbose:
                print("Not found")

    return cameras

def print_camera_details(cameras: List[Dict[str, Any]]) -> None:
    """
    Print detailed information about found cameras

    Args:
        cameras: List of camera information dictionaries
    """
    print("=" * 80)
    print(f"SUMMARY: {len(cameras)} CAMERA(S) FOUND")
    print("=" * 80)

    if not cameras:
        print("No cameras detected!")
        return

    for camera in cameras:
        idx = camera['index']
        props = camera['properties']

        print(f"\n{'=' * 80}")
        print(f"CAMERA INDEX: {idx}")
        print(f"{'=' * 80}")

        print(f"Backend:           {props['backend']}")
        print(f"Actual Resolution: {props['actual_width']}x{props['actual_height']}")
        print(f"Set Resolution:    {props['width']}x{props['height']}")
        print(f"FPS:               {props['fps']}")
        print(f"Channels:          {props['channels']}")
        print(f"FOURCC Code:       {props['fourcc']}")
        print(f"Format:            {props['format']}")
        print(f"Buffer Size:       {props['buffer_size']}")

        print(f"\nCamera Controls:")
        print(f"  Brightness:      {props['brightness']}")
        print(f"  Contrast:        {props['contrast']}")
        print(f"  Saturation:      {props['saturation']}")
        print(f"  Hue:             {props['hue']}")
        print(f"  Gain:            {props['gain']}")
        print(f"  Exposure:        {props['exposure']}")

    print(f"\n{'=' * 80}")
    print("To use a camera, note its index number and use it in the Capture script")
    print(f"{'=' * 80}\n")

if __name__ == "__main__":
    import sys

    max_cameras = MAX_CAMERAS_TO_CHECK

    # Check if user provided max cameras argument
    if len(sys.argv) > 1:
        try:
            max_cameras = int(sys.argv[1])
        except ValueError:
            print(f"Warning: Invalid number '{sys.argv[1]}', using default {MAX_CAMERAS_TO_CHECK}")
            max_cameras = MAX_CAMERAS_TO_CHECK

    # Find all cameras
    cameras = find_all_cameras(max_cameras=max_cameras, verbose=True)

    # Print detailed summary
    print_camera_details(cameras)

    # Exit with status code
    if cameras:
        print(f"Success! Found {len(cameras)} camera(s)")
        exit(0)
    else:
        print("No cameras found!")
        exit(1)
