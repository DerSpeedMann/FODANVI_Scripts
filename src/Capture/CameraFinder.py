import cv2
from typing import List, Dict, Any, Tuple

# Global configuration
MAX_CAMERAS_TO_CHECK: int = 10  # Maximum number of camera indices to check

# All camera properties to check for support
CAMERA_PROPERTIES = {
    # Basic properties
    "Frame Width": cv2.CAP_PROP_FRAME_WIDTH,
    "Frame Height": cv2.CAP_PROP_FRAME_HEIGHT,
    "FPS": cv2.CAP_PROP_FPS,
    "FOURCC": cv2.CAP_PROP_FOURCC,
    "Format": cv2.CAP_PROP_FORMAT,
    "Buffer Size": cv2.CAP_PROP_BUFFERSIZE,

    # Exposure & ISO
    "Exposure": cv2.CAP_PROP_EXPOSURE,
    "Auto Exposure": cv2.CAP_PROP_AUTO_EXPOSURE,
    "ISO Speed": cv2.CAP_PROP_ISO_SPEED,
    "Gain": cv2.CAP_PROP_GAIN,

    # Focus
    "Focus": cv2.CAP_PROP_FOCUS,
    "Autofocus": cv2.CAP_PROP_AUTOFOCUS,

    # White Balance
    "WB Temperature": cv2.CAP_PROP_WB_TEMPERATURE,
    "Auto WB": cv2.CAP_PROP_AUTO_WB,

    # Image adjustments
    "Brightness": cv2.CAP_PROP_BRIGHTNESS,
    "Contrast": cv2.CAP_PROP_CONTRAST,
    "Saturation": cv2.CAP_PROP_SATURATION,
    "Hue": cv2.CAP_PROP_HUE,
    "Sharpness": cv2.CAP_PROP_SHARPNESS,
    "Gamma": cv2.CAP_PROP_GAMMA,
    "Backlight": cv2.CAP_PROP_BACKLIGHT,

    # PTZ (Pan-Tilt-Zoom)
    "Zoom": cv2.CAP_PROP_ZOOM,
    "Pan": cv2.CAP_PROP_PAN,
    "Tilt": cv2.CAP_PROP_TILT,

    # Other
    "Temperature": cv2.CAP_PROP_TEMPERATURE,
    "Trigger": cv2.CAP_PROP_TRIGGER,
    "Trigger Delay": cv2.CAP_PROP_TRIGGER_DELAY,
    "Roll": cv2.CAP_PROP_ROLL,
    "Iris": cv2.CAP_PROP_IRIS,
}


def check_property_support(cap: cv2.VideoCapture, prop_id: int) -> Tuple[bool, float]:
    """
    Check if a camera property is supported and get its current value

    Args:
        cap: OpenCV VideoCapture object
        prop_id: Property ID to check

    Returns:
        Tuple of (is_supported, current_value)
    """
    try:
        value = cap.get(prop_id)
        # Property is typically unsupported if it returns 0 or -1
        # But some valid properties can be 0, so we also try to set it
        if value == -1:
            return False, value

        # Try to set the same value to verify write support
        original = value
        cap.set(prop_id, value)
        new_value = cap.get(prop_id)

        # If we can read a non-negative value, consider it supported
        return value >= 0, value
    except:
        return False, -1


def get_supported_properties(cap: cv2.VideoCapture) -> Dict[str, Dict[str, Any]]:
    """
    Check all camera properties and return supported ones with their values

    Args:
        cap: OpenCV VideoCapture object

    Returns:
        Dictionary with property info: {name: {id, value, supported}}
    """
    supported = {}

    for name, prop_id in CAMERA_PROPERTIES.items():
        is_supported, value = check_property_support(cap, prop_id)
        supported[name] = {
            "id": prop_id,
            "value": value,
            "supported": is_supported
        }

    return supported


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

    # Additional properties
    properties['backend'] = cap.getBackendName()
    properties['fourcc'] = int(cap.get(cv2.CAP_PROP_FOURCC))

    # Get all supported properties
    properties['supported_properties'] = get_supported_properties(cap)

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

        # Print supported properties
        supported_props = props.get('supported_properties', {})

        # Separate supported and unsupported
        supported = {k: v for k, v in supported_props.items() if v['supported']}
        unsupported = {k: v for k, v in supported_props.items() if not v['supported']}

        print(f"\n--- SUPPORTED PROPERTIES ({len(supported)}) ---")
        if supported:
            for name, info in supported.items():
                value = info['value']
                # Format value nicely
                if isinstance(value, float) and value == int(value):
                    value = int(value)
                print(f"  {name:20s} = {value}")
        else:
            print("  None detected")

        print(f"\n--- UNSUPPORTED PROPERTIES ({len(unsupported)}) ---")
        if unsupported:
            unsupported_names = [name for name in unsupported.keys()]
            # Print in rows of 4
            for i in range(0, len(unsupported_names), 4):
                row = unsupported_names[i:i+4]
                print(f"  {', '.join(row)}")
        else:
            print("  All properties supported!")

    print(f"\n{'=' * 80}")
    print("To use a camera, note its index number and use it in the Capture script")
    print("Supported properties can be controlled via cv2.CAP_PROP_* constants")
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
