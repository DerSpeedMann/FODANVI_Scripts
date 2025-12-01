import time
import os
import sys
import json
import select
import termios
import tty
from pathlib import Path
from datetime import datetime
from typing import Optional, Tuple, Dict
from dataclasses import dataclass, asdict

from PIL import Image
from picamera2 import Picamera2

# ============================================================================
# GLOBAL CONFIGURATION
# ============================================================================

@dataclass
class CaptureConfig:
    """Configuration for camera settings"""
    resolution_width: int = 1920
    resolution_height: int = 1080
    camera_init_delay: float = 1.0
    image_prefix: str = "capture"
    image_format: str = "jpg"
    jpeg_quality: int = 95
    # Camera control values (control_name -> value)
    control_values: Dict[str, float] = None

    def __post_init__(self):
        if self.control_values is None:
            self.control_values = {}

# Default values for backwards compatibility
RESOLUTION_WIDTH: int = 1920
RESOLUTION_HEIGHT: int = 1080
CAMERA_INIT_DELAY: float = 1.0
OUTPUT_FOLDER: str = "captured_images"
IMAGE_PREFIX: str = "capture"
IMAGE_FORMAT: str = "jpg"
JPEG_QUALITY: int = 95


# ============================================================================
# CONFIG FILE FUNCTIONS
# ============================================================================

def load_config(config_path: str) -> CaptureConfig:
    """
    Load configuration from a JSON file.

    Args:
        config_path: Path to the JSON config file

    Returns:
        CaptureConfig object with loaded settings

    Raises:
        FileNotFoundError: If config file doesn't exist
        json.JSONDecodeError: If config file is not valid JSON
        ValueError: If config contains invalid values
    """
    path = Path(config_path)

    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with open(path, 'r') as f:
        data = json.load(f)

    # Validate required fields
    if 'resolution_width' in data and not isinstance(data['resolution_width'], int):
        raise ValueError(f"resolution_width must be an integer, got {type(data['resolution_width']).__name__}")
    if 'resolution_height' in data and not isinstance(data['resolution_height'], int):
        raise ValueError(f"resolution_height must be an integer, got {type(data['resolution_height']).__name__}")
    if 'jpeg_quality' in data:
        if not isinstance(data['jpeg_quality'], int) or not (1 <= data['jpeg_quality'] <= 100):
            raise ValueError(f"jpeg_quality must be an integer between 1 and 100")

    # Extract control_values separately to handle it properly
    control_vals = data.pop('control_values', {})

    # Create config with remaining fields
    config = CaptureConfig(**data)
    config.control_values = control_vals

    return config


def save_config(config: CaptureConfig, config_path: str) -> None:
    """
    Save configuration to a JSON file.

    Args:
        config: CaptureConfig object to save
        config_path: Path to save the JSON config file
    """
    path = Path(config_path)

    # Ensure parent directory exists
    path.parent.mkdir(parents=True, exist_ok=True)

    data = asdict(config)

    with open(path, 'w') as f:
        json.dump(data, f, indent=2)

    print(f"Config saved to: {path.absolute()}")

# ============================================================================
# CAMERA CONTROL SETTINGS
# ============================================================================

@dataclass
class CameraControl:
    """Definition for an adjustable camera property"""
    name: str
    control_name: str  # libcamera control name
    min_val: Optional[float]  # None = no lower limit (discovery mode)
    max_val: Optional[float]  # None = no upper limit (discovery mode)
    step: float
    default: Optional[float] = None

# Picamera2 control definitions
# See libcamera controls: https://libcamera.org/api-html/controls_8h.html
# min_val/max_val = None means no limit (for discovering camera capabilities)
CONTROL_DEFS = [
    # Image adjustments
    CameraControl("Brightness", "Brightness", None, None, 0.1, 0.0),
    CameraControl("Contrast", "Contrast", None, None, 0.1, 1.0),
    CameraControl("Saturation", "Saturation", None, None, 0.1, 1.0),
    CameraControl("Sharpness", "Sharpness", None, None, 0.1, 1.0),
    # Exposure controls
    CameraControl("Exposure", "ExposureValue", None, None, 0.5, 0.0),
    CameraControl("Exp Time", "ExposureTime", None, None, 10000, None),  # microseconds
    CameraControl("Gain", "AnalogueGain", None, None, 0.5, 1.0),
    CameraControl("Dig Gain", "DigitalGain", None, None, 0.25, 1.0),
    # Auto controls
    CameraControl("Auto Exp", "AeEnable", 0, 1, 1, 1),
    CameraControl("Auto WB", "AwbEnable", 0, 1, 1, 1),
    # White balance (manual when AwbEnable=0)
    CameraControl("WB Red", "ColourGains", None, None, 0.1, None),  # Red gain
    # Noise reduction
    CameraControl("Denoise", "NoiseReductionMode", 0, 4, 1, 0),  # 0=off, 1=fast, 2=HQ, 3=minimal, 4=ZSL
]

# Runtime storage
control_values: dict = {}

# ============================================================================
# CAMERA FUNCTIONS
# ============================================================================

def setup_camera(width: int, height: int, config_control_values: Dict[str, float] = None) -> Optional[Picamera2]:
    """Initialize Raspberry Pi camera using picamera2."""
    print("Opening Raspberry Pi camera...")

    try:
        picam2 = Picamera2()

        config = picam2.create_still_configuration(
            main={"size": (width, height), "format": "RGB888"},
            buffer_count=2
        )
        picam2.configure(config)
        picam2.start()

        print("Waiting for camera to initialize...")
        time.sleep(CAMERA_INIT_DELAY)

        initialize_controls(picam2, config_control_values)

        print(f"Camera opened successfully!")
        print(f"Resolution: {width}x{height}")

        return picam2

    except Exception as e:
        print(f"Error opening camera: {e}")
        return None


def initialize_controls(picam2: Picamera2, config_control_values: Dict[str, float] = None) -> None:
    """Initialize camera controls, optionally using values from config."""
    global control_values
    control_values = {}

    print("\n" + "=" * 50)
    print("CAMERA CONTROLS")
    print("=" * 50)

    for ctrl in CONTROL_DEFS:
        # Priority: config value > default > 0
        if config_control_values and ctrl.control_name in config_control_values:
            value = config_control_values[ctrl.control_name]
            # Clamp to valid range if limits are defined
            if ctrl.min_val is not None:
                value = max(ctrl.min_val, value)
            if ctrl.max_val is not None:
                value = min(ctrl.max_val, value)
        elif ctrl.default is not None:
            value = ctrl.default
        else:
            # No default, use min_val if defined, otherwise 0
            value = ctrl.min_val if ctrl.min_val is not None else 0

        try:
            picam2.set_controls({ctrl.control_name: value})
            control_values[ctrl.control_name] = value
        except Exception:
            control_values[ctrl.control_name] = value

        # Format limits display
        min_str = str(ctrl.min_val) if ctrl.min_val is not None else "?"
        max_str = str(ctrl.max_val) if ctrl.max_val is not None else "?"
        print(f"  {ctrl.name:12s}: {min_str} - {max_str} (set: {control_values[ctrl.control_name]})")

    print("=" * 50)
    print(f"Loaded {len(CONTROL_DEFS)} controls\n")


def read_frame(picam2: Picamera2) -> Tuple[bool, any]:
    """Read a frame from the camera."""
    try:
        frame = picam2.capture_array()
        return True, frame  # RGB format for PIL
    except Exception:
        return False, None


def release_camera(picam2: Picamera2) -> None:
    """Release the camera."""
    try:
        picam2.stop()
        picam2.close()
    except Exception:
        pass


def adjust_control(picam2: Picamera2, ctrl: CameraControl, increase: bool) -> Tuple[str, float, float]:
    """Adjust a camera control up or down.

    Returns:
        Tuple of (name, requested_value, actual_value)
    """
    default_val = ctrl.default if ctrl.default is not None else 0
    current = control_values.get(ctrl.control_name, default_val)

    if increase:
        new_val = current + ctrl.step
        # Apply max limit only if defined
        if ctrl.max_val is not None:
            new_val = min(new_val, ctrl.max_val)
    else:
        new_val = current - ctrl.step
        # Apply min limit only if defined
        if ctrl.min_val is not None:
            new_val = max(new_val, ctrl.min_val)

    try:
        picam2.set_controls({ctrl.control_name: new_val})
        # Read back actual value from camera metadata
        metadata = picam2.capture_metadata()
        actual_val = metadata.get(ctrl.control_name, new_val)
        control_values[ctrl.control_name] = actual_val
    except Exception as e:
        print(f"Error setting {ctrl.name}: {e}")
        actual_val = current  # Keep old value on error
        control_values[ctrl.control_name] = actual_val

    return ctrl.name, new_val, actual_val


# ============================================================================
# CAPTURE FUNCTION
# ============================================================================

def capture_images(config: CaptureConfig = None, output_folder: str = OUTPUT_FOLDER) -> int:
    """Interactive image capture with terminal-based controls."""

    # Use provided config or create default
    if config is None:
        config = CaptureConfig()

    prefix = config.image_prefix
    image_format = config.image_format
    jpeg_quality = config.jpeg_quality
    width = config.resolution_width
    height = config.resolution_height

    output_path = Path(output_folder)
    output_path.mkdir(parents=True, exist_ok=True)

    print(f"\n{'='*60}")
    print(f"IMAGE CAPTURE")
    print(f"{'='*60}")
    print(f"Output Folder:  {output_path.absolute()}")
    print(f"Image Format:   {image_format}")
    print(f"Resolution:     {width}x{height}")
    print(f"{'='*60}\n")

    picam2 = setup_camera(width, height, config.control_values)
    if picam2 is None:
        return 0

    # Warm up
    print("Warming up camera...")
    for _ in range(5):
        read_frame(picam2)
    time.sleep(0.5)

    captured_count = 0
    selected_control = 0

    def print_status():
        print("\n" + "-" * 50)
        print(f"Captures: {captured_count} | Output: {output_path}")
        print("-" * 50)
        print("Controls:")
        for i, ctrl in enumerate(CONTROL_DEFS):
            val = control_values.get(ctrl.control_name, 0)
            marker = ">>>" if i == selected_control else "   "
            # Format limits (? for unlimited)
            min_str = "?" if ctrl.min_val is None else (f"{ctrl.min_val:.1f}" if isinstance(ctrl.min_val, float) and ctrl.min_val != int(ctrl.min_val) else str(int(ctrl.min_val)))
            max_str = "?" if ctrl.max_val is None else (f"{ctrl.max_val:.1f}" if isinstance(ctrl.max_val, float) and ctrl.max_val != int(ctrl.max_val) else str(int(ctrl.max_val)))
            if isinstance(val, float) and val != int(val):
                print(f"  {marker} [{i+1}] {ctrl.name}: {val:.2f} ({min_str} - {max_str})")
            else:
                print(f"  {marker} [{i+1}] {ctrl.name}: {int(val)} ({min_str} - {max_str})")
        print("-" * 50)

    def print_help():
        print("\n" + "=" * 50)
        print("COMMANDS")
        print("=" * 50)
        print("  c / ENTER    : Capture image")
        print("  q            : Quit")
        print("  l            : List status/controls")
        print("  h            : Show this help")
        print("  e            : Export current settings to config file")
        print("")
        print("  1-9, 0       : Select control by number (0=10th)")
        print("  w / s        : Select prev/next control")
        print("  + / -        : Adjust selected control")
        print("=" * 50)

    print_help()
    print_status()
    print("\nReady! (c=capture, q=quit, h=help)")

    try:
        while True:
            # Non-blocking input
            old_settings = termios.tcgetattr(sys.stdin)
            try:
                tty.setcbreak(sys.stdin.fileno())
                if select.select([sys.stdin], [], [], 0.1)[0]:
                    key = sys.stdin.read(1).lower()
                else:
                    continue
            finally:
                termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_settings)

            # Quit
            if key == 'q':
                print("\nQuitting...")
                break

            # Capture
            elif key == 'c' or key == '\r' or key == '\n':
                ret, frame = read_frame(picam2)
                if not ret or frame is None:
                    print("\nError: Could not capture frame")
                    continue

                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
                filename = f"{prefix}_{timestamp}.{image_format}"
                filepath = output_path / filename

                try:
                    img = Image.fromarray(frame)
                    if image_format.lower() in ['jpg', 'jpeg']:
                        img.save(filepath, quality=jpeg_quality)
                    else:
                        img.save(filepath)
                    success = True
                except Exception:
                    success = False

                if success:
                    file_size = os.path.getsize(filepath) / 1024
                    captured_count += 1
                    print(f"\n[{captured_count}] Captured: {filename} ({file_size:.1f} KB)")
                else:
                    print(f"\nFailed to save: {filename}")

            # Help
            elif key == 'h':
                print_help()

            # Status
            elif key == 'l':
                print_status()

            # Export config
            elif key == 'e':
                export_config = CaptureConfig(
                    resolution_width=width,
                    resolution_height=height,
                    camera_init_delay=config.camera_init_delay,
                    image_prefix=prefix,
                    image_format=image_format,
                    jpeg_quality=jpeg_quality,
                    control_values=dict(control_values)
                )
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                config_filename = f"capture_config_{timestamp}.json"
                config_path = output_path / config_filename
                save_config(export_config, str(config_path))

            # Select control by number (1-9 = controls 1-9, 0 = control 10)
            elif key.isdigit():
                if key == '0':
                    idx = 9  # 0 maps to 10th control (index 9)
                else:
                    idx = int(key) - 1
                if 0 <= idx < len(CONTROL_DEFS):
                    selected_control = idx
                    ctrl = CONTROL_DEFS[selected_control]
                    val = control_values.get(ctrl.control_name, 0)
                    print(f"\nSelected: {ctrl.name} = {val}")

            # Previous control
            elif key == 'w':
                if selected_control > 0:
                    selected_control -= 1
                    ctrl = CONTROL_DEFS[selected_control]
                    val = control_values.get(ctrl.control_name, 0)
                    print(f"\nSelected: {ctrl.name} = {val}")

            # Next control
            elif key == 's':
                if selected_control < len(CONTROL_DEFS) - 1:
                    selected_control += 1
                    ctrl = CONTROL_DEFS[selected_control]
                    val = control_values.get(ctrl.control_name, 0)
                    print(f"\nSelected: {ctrl.name} = {val}")

            # Decrease control
            elif key == '-' or key == '_':
                ctrl = CONTROL_DEFS[selected_control]
                name, requested, actual = adjust_control(picam2, ctrl, increase=False)
                if requested != actual:
                    print(f"\n{name}: {requested} -> actual: {actual}")
                else:
                    print(f"\n{name}: {actual}")

            # Increase control
            elif key == '+' or key == '=':
                ctrl = CONTROL_DEFS[selected_control]
                name, requested, actual = adjust_control(picam2, ctrl, increase=True)
                if requested != actual:
                    print(f"\n{name}: {requested} -> actual: {actual}")
                else:
                    print(f"\n{name}: {actual}")

    except KeyboardInterrupt:
        print("\n\nInterrupted!")

    release_camera(picam2)
    print(f"\nCamera released")

    print(f"\n{'='*60}")
    print(f"CAPTURE COMPLETE")
    print(f"{'='*60}")
    print(f"Images Captured: {captured_count}")
    print(f"Output:          {output_path.absolute()}")
    print(f"{'='*60}\n")

    return captured_count


if __name__ == "__main__":
    config: CaptureConfig = CaptureConfig()  # Default config
    output_dir = OUTPUT_FOLDER

    # Parse arguments: [config_file.json] [output_folder]
    # Config file is optional - if not provided, uses defaults for camera discovery
    arg_idx = 1

    if len(sys.argv) > arg_idx:
        # Check if first arg is a config file or output folder
        first_arg = sys.argv[arg_idx]
        if first_arg.endswith('.json'):
            # It's a config file
            try:
                config = load_config(first_arg)
                print(f"Loaded config from: {first_arg}")
            except FileNotFoundError as e:
                print(f"Error: {e}")
                sys.exit(1)
            except json.JSONDecodeError as e:
                print(f"Error: Invalid JSON in config file: {e}")
                sys.exit(1)
            except ValueError as e:
                print(f"Error: Invalid config value: {e}")
                sys.exit(1)
            except TypeError as e:
                print(f"Error: Unknown field in config file: {e}")
                sys.exit(1)
            arg_idx += 1
        else:
            # First arg is output folder, no config file
            output_dir = first_arg
            arg_idx += 1
            print("No config file specified, using defaults (discovery mode)")
            print("Press 'e' during capture to export current settings\n")

    if len(sys.argv) > arg_idx:
        output_dir = sys.argv[arg_idx]

    captured = capture_images(config, output_folder=output_dir)

    sys.exit(0 if captured > 0 else 1)
