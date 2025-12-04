"""
Camera core module - shared camera functionality.
Used by both web_server.py and camera_cli.py.

Based on src/Capture/CaptureImages.py with full feature parity.
"""

import os
import time
import json
import threading
from pathlib import Path
from datetime import datetime
from typing import Optional, Tuple, Dict
from dataclasses import dataclass, asdict

try:
    from picamera2 import Picamera2
    from PIL import Image
    CAMERA_AVAILABLE = True
except ImportError:
    CAMERA_AVAILABLE = False


# ============================================================================
# CONFIGURATION
# ============================================================================

@dataclass
class CaptureConfig:
    """Configuration for camera settings (per-camera config, no folder paths)"""
    resolution_width: int = 1920
    resolution_height: int = 1080
    camera_init_delay: float = 1.0
    image_prefix: str = "capture"
    image_format: str = "jpg"
    jpeg_quality: int = 95
    # Camera control settings (control_name -> dict with value, min_val, max_val, step)
    controls: Dict[str, dict] = None

    def __post_init__(self):
        if self.controls is None:
            self.controls = {}


# Default folders (not part of config)
DEFAULT_OUTPUT_FOLDER = "captured_images"
DEFAULT_CONFIG_FOLDER = "configs"


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
    # Auto exposure modes
    CameraControl("AE Meter", "AeMeteringMode", 0, 3, 1, 0),
    CameraControl("AE Constr", "AeConstraintMode", 0, 3, 1, 0),
    CameraControl("AE Mode", "AeExposureMode", 0, 3, 1, 0),
    # White balance mode
    CameraControl("AWB Mode", "AwbMode", 0, 7, 1, 0),
    # Noise reduction
    CameraControl("Denoise", "NoiseReductionMode", 0, 4, 1, 0),
    # Focus (may not be available on all cameras)
    CameraControl("AF Mode", "AfMode", 0, 2, 1, 0),
    CameraControl("Lens Pos", "LensPosition", None, None, 0.1, 0.0),
]


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
            raise ValueError("jpeg_quality must be an integer between 1 and 100")

    # Extract controls separately to handle it properly
    controls = data.pop('controls', {})

    # Also support old 'control_values' format for backwards compatibility
    if 'control_values' in data:
        old_values = data.pop('control_values')
        for name, val in old_values.items():
            if name not in controls:
                controls[name] = {"value": val}

    # Create config with remaining fields
    config = CaptureConfig(**data)
    config.controls = controls

    return config


def save_config(config: CaptureConfig, config_path: str) -> None:
    """
    Save configuration to a JSON file.

    Args:
        config: CaptureConfig object to save
        config_path: Path to save the JSON config file
    """
    path = Path(config_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    data = asdict(config)

    with open(path, 'w') as f:
        json.dump(data, f, indent=2)

    print(f"Config saved to: {path.absolute()}")


# ============================================================================
# CONTROL LIMIT DETECTION
# ============================================================================

def detect_control_limits(picam2, control_name: str,
                          search_min: float = -10000, search_max: float = 10000,
                          max_iterations: int = 30,
                          debug: bool = False) -> Tuple[Optional[float], Optional[float]]:
    """
    Auto-detect min and max limits for a control using binary search.
    """
    def get_actual_value(test_val: float) -> Optional[float]:
        try:
            picam2.set_controls({control_name: test_val})
            time.sleep(0.05)
            metadata = picam2.capture_metadata()
            if control_name in metadata:
                return metadata[control_name]
            return None
        except Exception:
            return None

    baseline = get_actual_value(0)
    if baseline is None:
        baseline = get_actual_value(1)
    if baseline is None:
        return None, None

    if debug:
        print(f"\n    [DEBUG] {control_name}: baseline={baseline}")

    def value_accepted(requested: float, actual: float) -> bool:
        if actual is None:
            return False
        return round(actual, 2) == round(requested, 2)

    # Binary search for minimum
    low, high = float(search_min), float(baseline)
    for i in range(max_iterations):
        if high - low < 0.01:
            break
        mid = round((low + high) / 2, 2)
        actual = get_actual_value(mid)
        accepted = value_accepted(mid, actual)
        if debug and i < 5:
            print(f"    [DEBUG] min search: mid={mid}, actual={actual}, accepted={accepted}")
        if accepted:
            high = mid
        else:
            low = mid
    detected_min = round(high, 2)

    # Binary search for maximum
    low, high = float(baseline), float(search_max)
    for i in range(max_iterations):
        if high - low < 0.01:
            break
        mid = round((low + high) / 2, 2)
        actual = get_actual_value(mid)
        accepted = value_accepted(mid, actual)
        if debug and i < 5:
            print(f"    [DEBUG] max search: mid={mid}, actual={actual}, accepted={accepted}")
        if accepted:
            low = mid
        else:
            high = mid
    detected_max = round(low, 2)

    get_actual_value(baseline)
    return detected_min, detected_max


def auto_detect_all_limits(picam2, debug: bool = True) -> None:
    """
    Auto-detect min/max limits for all controls that have None limits.
    Updates CONTROL_DEFS in place.
    """
    global CONTROL_DEFS

    print("\n" + "=" * 50)
    print("AUTO-DETECTING CONTROL LIMITS")
    print("=" * 50)

    first_detection = True

    for i, ctrl in enumerate(CONTROL_DEFS):
        if ctrl.min_val is not None and ctrl.max_val is not None:
            print(f"  {ctrl.name:12s}: using preset {ctrl.min_val} - {ctrl.max_val}")
            continue

        print(f"  {ctrl.name:12s}: detecting...", end="", flush=True)

        if ctrl.control_name == "ExposureTime":
            search_min = 0 if ctrl.min_val is None else ctrl.min_val
            search_max = 10000000 if ctrl.max_val is None else ctrl.max_val
        elif ctrl.control_name == "AnalogueGain":
            search_min = 1.0 if ctrl.min_val is None else ctrl.min_val
            search_max = 64.0 if ctrl.max_val is None else ctrl.max_val
        elif ctrl.control_name == "DigitalGain":
            search_min = 1.0 if ctrl.min_val is None else ctrl.min_val
            search_max = 16.0 if ctrl.max_val is None else ctrl.max_val
        else:
            search_min = -10000 if ctrl.min_val is None else ctrl.min_val
            search_max = 10000 if ctrl.max_val is None else ctrl.max_val

        detected_min, detected_max = detect_control_limits(
            picam2, ctrl.control_name,
            search_min=search_min,
            search_max=search_max,
            debug=debug and first_detection
        )
        first_detection = False

        if detected_min is not None and detected_max is not None:
            detected_min = round(detected_min, 2)
            detected_max = round(detected_max, 2)
            CONTROL_DEFS[i] = CameraControl(
                ctrl.name, ctrl.control_name,
                detected_min, detected_max,
                ctrl.step, ctrl.default
            )
            print(f" {detected_min} - {detected_max}")
        else:
            print(" failed (keeping defaults)")

    print("=" * 50 + "\n")


# ============================================================================
# CAMERA CLASS
# ============================================================================

class CameraCore:
    """
    Thread-safe camera singleton.

    Usage:
        from camera_core import CameraCore

        cam = CameraCore()
        cam.init()
        filename, msg = cam.capture()
    """
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self.picam2 = None
        self.config: CaptureConfig = CaptureConfig()
        self.output_folder: str = DEFAULT_OUTPUT_FOLDER
        self.config_folder: str = DEFAULT_CONFIG_FOLDER
        self.control_values: Dict[str, float] = {}
        self._capture_lock = threading.Lock()
        self._capture_callbacks = []

    def init(self, config: CaptureConfig = None, output_folder: str = None,
             config_folder: str = None, auto_detect_limits: bool = False) -> bool:
        """
        Initialize the camera.

        Args:
            config: Optional CaptureConfig, uses defaults if not provided
            output_folder: Folder for captured images
            config_folder: Folder for exported configs
            auto_detect_limits: If True, auto-detect control limits

        Returns:
            True if successful, False otherwise
        """
        if not CAMERA_AVAILABLE:
            print("Error: picamera2 not available")
            return False

        if config:
            self.config = config
        if output_folder:
            self.output_folder = output_folder
        if config_folder:
            self.config_folder = config_folder

        print("Opening Raspberry Pi camera...")

        try:
            self.picam2 = Picamera2()
        except IndexError:
            print("Error: No camera detected!")
            print("  - Check camera cable connection")
            print("  - Verify camera: libcamera-hello --list-cameras")
            print("  - Check /boot/config.txt for camera settings")
            print("  - Reboot if recently connected")
            return False
        except Exception as e:
            print(f"Error initializing Picamera2: {e}")
            return False

        try:
            cam_config = self.picam2.create_still_configuration(
                main={
                    "size": (self.config.resolution_width, self.config.resolution_height),
                    "format": "RGB888"
                },
                buffer_count=2
            )
            self.picam2.configure(cam_config)
            self.picam2.start()

            print("Waiting for camera to initialize...")
            time.sleep(self.config.camera_init_delay)

            # Auto-detect limits if requested and no config controls provided
            if auto_detect_limits and not self.config.controls:
                auto_detect_all_limits(self.picam2)

            # Initialize controls
            self._init_controls()

            print(f"Camera opened successfully!")
            print(f"Resolution: {self.config.resolution_width}x{self.config.resolution_height}")
            return True

        except Exception as e:
            print(f"Error configuring camera: {e}")
            try:
                self.picam2.close()
            except Exception:
                pass
            self.picam2 = None
            return False

    def _init_controls(self) -> None:
        """Initialize camera controls, optionally using values from config."""
        global CONTROL_DEFS
        self.control_values = {}

        # Apply config overrides to CONTROL_DEFS
        if self.config.controls:
            for i, ctrl in enumerate(CONTROL_DEFS):
                if ctrl.control_name in self.config.controls:
                    cfg = self.config.controls[ctrl.control_name]
                    new_min = cfg.get('min_val', ctrl.min_val)
                    new_max = cfg.get('max_val', ctrl.max_val)
                    new_step = cfg.get('step', ctrl.step)
                    new_default = cfg.get('value', ctrl.default)
                    CONTROL_DEFS[i] = CameraControl(
                        ctrl.name, ctrl.control_name,
                        new_min, new_max, new_step, new_default
                    )

        print("\n" + "=" * 50)
        print("CAMERA CONTROLS")
        print("=" * 50)

        for ctrl in CONTROL_DEFS:
            # Priority: config value > default > 0
            if self.config.controls and ctrl.control_name in self.config.controls:
                cfg = self.config.controls[ctrl.control_name]
                value = cfg.get('value', ctrl.default if ctrl.default is not None else 0)
                if ctrl.min_val is not None:
                    value = max(ctrl.min_val, value)
                if ctrl.max_val is not None:
                    value = min(ctrl.max_val, value)
            elif ctrl.default is not None:
                value = ctrl.default
            else:
                value = ctrl.min_val if ctrl.min_val is not None else 0

            try:
                self.picam2.set_controls({ctrl.control_name: value})
                self.control_values[ctrl.control_name] = value
            except Exception:
                self.control_values[ctrl.control_name] = value

            min_str = str(ctrl.min_val) if ctrl.min_val is not None else "?"
            max_str = str(ctrl.max_val) if ctrl.max_val is not None else "?"
            print(f"  {ctrl.name:12s}: {min_str} - {max_str} (set: {self.control_values[ctrl.control_name]})")

        print("=" * 50)
        print(f"Loaded {len(CONTROL_DEFS)} controls\n")

    def is_ready(self) -> bool:
        """Check if camera is initialized and ready."""
        return self.picam2 is not None

    def read_frame(self) -> Tuple[bool, any]:
        """Read a frame from the camera."""
        if not self.is_ready():
            return False, None
        try:
            with self._capture_lock:
                frame = self.picam2.capture_array()
            return True, frame
        except Exception:
            return False, None

    def capture(self) -> Tuple[Optional[str], str]:
        """
        Capture an image and save it.

        Returns:
            Tuple of (filename, message)
            filename is None if capture failed
        """
        if not self.is_ready():
            return None, "Camera not initialized"

        output_path = Path(self.output_folder)
        output_path.mkdir(parents=True, exist_ok=True)

        ret, frame = self.read_frame()
        if not ret or frame is None:
            return None, "Could not capture frame"

        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
            filename = f"{self.config.image_prefix}_{timestamp}.{self.config.image_format}"
            filepath = output_path / filename

            img = Image.fromarray(frame)
            if self.config.image_format.lower() in ['jpg', 'jpeg']:
                img.save(filepath, quality=self.config.jpeg_quality)
            else:
                img.save(filepath)

            file_size = os.path.getsize(filepath) / 1024
            message = f"Captured: {filename} ({file_size:.1f} KB)"

            # Notify callbacks
            for callback in self._capture_callbacks:
                try:
                    callback(filename, str(filepath))
                except Exception:
                    pass

            return filename, message

        except Exception as e:
            return None, f"Capture failed: {e}"

    def set_control(self, control_name: str, value: float) -> Tuple[bool, str, float]:
        """
        Set a camera control value.

        Args:
            control_name: Control name (e.g., "Brightness")
            value: Value to set

        Returns:
            Tuple of (success, message, actual_value)
        """
        if not self.is_ready():
            return False, "Camera not initialized", 0

        # Find control definition
        ctrl_def = None
        for ctrl in CONTROL_DEFS:
            if ctrl.control_name == control_name:
                ctrl_def = ctrl
                break

        if ctrl_def is None:
            return False, f"Unknown control: {control_name}", 0

        # Clamp to valid range if limits defined
        if ctrl_def.min_val is not None:
            value = max(ctrl_def.min_val, value)
        if ctrl_def.max_val is not None:
            value = min(ctrl_def.max_val, value)

        actual_val = value
        try:
            with self._capture_lock:
                self.picam2.set_controls({control_name: value})
                # Read back actual value
                try:
                    metadata = self.picam2.capture_metadata()
                    if control_name in metadata:
                        actual_val = metadata[control_name]
                except Exception:
                    pass
            self.control_values[control_name] = actual_val
            return True, f"Set {ctrl_def.name} to {actual_val}", actual_val
        except Exception as e:
            return False, f"Failed to set {ctrl_def.name}: {e}", self.control_values.get(control_name, 0)

    def adjust_control(self, control_name: str, increase: bool) -> Tuple[str, float, float]:
        """
        Adjust a camera control up or down by its step value.

        Returns:
            Tuple of (name, requested_value, actual_value)
        """
        ctrl_def = None
        for ctrl in CONTROL_DEFS:
            if ctrl.control_name == control_name:
                ctrl_def = ctrl
                break

        if ctrl_def is None:
            return control_name, 0, 0

        default_val = ctrl_def.default if ctrl_def.default is not None else 0
        current = self.control_values.get(control_name, default_val)

        if increase:
            new_val = current + ctrl_def.step
            if ctrl_def.max_val is not None:
                new_val = min(new_val, ctrl_def.max_val)
        else:
            new_val = current - ctrl_def.step
            if ctrl_def.min_val is not None:
                new_val = max(new_val, ctrl_def.min_val)

        success, msg, actual_val = self.set_control(control_name, new_val)
        return ctrl_def.name, new_val, actual_val

    def get_control(self, control_name: str) -> Optional[float]:
        """Get current value of a control."""
        return self.control_values.get(control_name)

    def get_all_controls(self) -> Dict[str, float]:
        """Get all current control values."""
        return self.control_values.copy()

    def get_control_defs(self) -> list:
        """Get control definitions."""
        return CONTROL_DEFS.copy()

    def export_config(self, config_path: str = None) -> str:
        """
        Export current settings to a config file.

        Args:
            config_path: Optional path. If None, auto-generates in config_folder.

        Returns:
            Path to the saved config file.
        """
        if config_path is None:
            cfg_folder = Path(self.config_folder)
            cfg_folder.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            config_path = str(cfg_folder / f"capture_config_{timestamp}.json")

        export_controls = {}
        for ctrl in CONTROL_DEFS:
            export_controls[ctrl.control_name] = {
                "value": self.control_values.get(ctrl.control_name, 0),
                "min_val": ctrl.min_val,
                "max_val": ctrl.max_val,
                "step": ctrl.step
            }

        export_config = CaptureConfig(
            resolution_width=self.config.resolution_width,
            resolution_height=self.config.resolution_height,
            camera_init_delay=self.config.camera_init_delay,
            image_prefix=self.config.image_prefix,
            image_format=self.config.image_format,
            jpeg_quality=self.config.jpeg_quality,
            controls=export_controls
        )
        save_config(export_config, config_path)
        return config_path

    def on_capture(self, callback) -> None:
        """Register a callback to be called after each capture."""
        self._capture_callbacks.append(callback)

    def close(self) -> None:
        """Release the camera."""
        if self.picam2:
            try:
                self.picam2.stop()
                self.picam2.close()
            except Exception:
                pass
            self.picam2 = None
            print("Camera released")


# ============================================================================
# MODULE-LEVEL CONVENIENCE FUNCTIONS
# ============================================================================

_camera: Optional[CameraCore] = None


def get_camera() -> CameraCore:
    """Get or create the global camera instance."""
    global _camera
    if _camera is None:
        _camera = CameraCore()
    return _camera


def init_camera(config: CaptureConfig = None, output_folder: str = None,
                config_folder: str = None, auto_detect_limits: bool = False) -> bool:
    """Initialize the global camera instance."""
    return get_camera().init(config, output_folder, config_folder, auto_detect_limits)


def capture_image() -> Tuple[Optional[str], str]:
    """Capture an image using the global camera instance."""
    return get_camera().capture()


def set_control(control_name: str, value: float) -> Tuple[bool, str, float]:
    """Set a camera control on the global camera instance."""
    return get_camera().set_control(control_name, value)


def get_controls() -> Dict[str, float]:
    """Get all control values from the global camera instance."""
    return get_camera().get_all_controls()


def get_control_defs() -> list:
    """Get control definitions."""
    return get_camera().get_control_defs()


def is_camera_ready() -> bool:
    """Check if global camera is ready."""
    return get_camera().is_ready()


def close_camera() -> None:
    """Close the global camera instance."""
    get_camera().close()
