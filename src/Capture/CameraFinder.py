import cv2
import importlib
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional

MAX_CAMERAS_TO_CHECK: int = 10

REPO_ROOT = Path(__file__).resolve().parents[2]

SUMMARY = "Find cameras and report which properties they really support."

INFO_TEXT = f"""\
{SUMMARY}

Scanning is read-only. --validate write-tests one camera you name and restores
the values afterwards; a full reset needs the device re-enumerated.

Usage:
  CameraFinder.py [N]                        scan indices 0..N-1 (default 10)
  CameraFinder.py -i 2                       scan one index
  CameraFinder.py --validate -i 2 -b dshow   write-test one camera
  CameraFinder.py --validate -i 2 --save cam1 --store report.log

  -i, --index N     camera index, repeatable when scanning
  -b, --backend X   auto, dshow or msmf; each exposes different controls
  --validate        write-test one named index
  --yes             skip the confirmation prompt
  --save NAME       write configs/NAME.json in the camera_core format
  --store PATH      also write the report to a file
  --info            this text
  -h, --help        flag syntax\
"""

BACKENDS = {
    "auto": cv2.CAP_ANY,
    "dshow": cv2.CAP_DSHOW,
    "msmf": cv2.CAP_MSMF,
}

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

# {manual property: (auto property, values meaning "manual")}
# DSHOW encodes Auto Exposure as 0.25 = manual / 0.75 = auto, MSMF as 0 / 1.
AUTO_DEPENDENCIES = {
    "Exposure": ("Auto Exposure", (0.25, 0.0)),
    "Focus": ("Autofocus", (0.0,)),
    "WB Temperature": ("Auto WB", (0.0,)),
}

# 0.5 covers the DSHOW quarter-step auto flags, the larger steps cover
# coarsely quantised controls.
PROBE_DELTAS = (1, -1, 0.5, -0.5, 10, -10, 100, -100)

STATUS_WRITABLE = "writable"        # write test changed the value
STATUS_READONLY = "readonly"        # readable, but ignores writes
STATUS_REPORTED = "reported"        # readable, not write-tested (passive mode)
STATUS_UNSUPPORTED = "unsupported"  # not reported by the driver at all


def import_from(module_name: str, folder: Path, needed_by: str):
    if str(folder) not in sys.path:
        # Ahead of site-packages, so local packages win over same-named ones.
        sys.path.insert(0, str(folder))
    try:
        return importlib.import_module(module_name)
    except ImportError as exc:
        raise ImportError(f"{needed_by} needs {module_name} from {folder}: {exc}") from exc


def camera_core():
    return import_from("picamera.camera_core", REPO_ROOT, "--save")


def console_logging():
    return import_from("console_logging", REPO_ROOT / "src" / "Processing", "--store")


def read_property(cap: cv2.VideoCapture, prop_id: int) -> float:
    try:
        return cap.get(prop_id)
    except cv2.error:
        return -1.0


def check_property_support(cap: cv2.VideoCapture, prop_id: int,
                           validate: bool = False) -> Tuple[str, float]:
    """
    Passive mode only separates readable from unreadable: a driver returning 0
    for a control it does not implement looks the same as one that is genuinely
    0. Validation writes a value *different* from the current one, because
    writing the current value back is a no-op every driver accepts.
    """
    value = read_property(cap, prop_id)
    if value == -1:
        return STATUS_UNSUPPORTED, value

    if not validate:
        return STATUS_REPORTED, value

    for delta in PROBE_DELTAS:
        try:
            accepted = cap.set(prop_id, value + delta)
        except cv2.error:
            break
        if not accepted:
            continue
        if read_property(cap, prop_id) != value:
            cap.set(prop_id, value)
            return STATUS_WRITABLE, value

    cap.set(prop_id, value)
    return STATUS_READONLY, value


def disable_auto_modes(cap: cv2.VideoCapture, verbose: bool = True) -> Dict[int, float]:
    """
    Exposure always looks read-only while auto exposure is on, because the
    driver overwrites whatever gets written to it. Returns the original values
    for restore_values().
    """
    originals: Dict[int, float] = {}

    for manual_name, (auto_name, manual_values) in AUTO_DEPENDENCIES.items():
        auto_id = CAMERA_PROPERTIES[auto_name]
        before = read_property(cap, auto_id)
        if before == -1:
            if verbose:
                print(f"    {auto_name:16s} not reported - {manual_name} probed as-is")
            continue

        for candidate in manual_values:
            cap.set(auto_id, candidate)
            if read_property(cap, auto_id) == candidate:
                originals[auto_id] = before
                if verbose:
                    print(f"    {auto_name:16s} {before} -> {candidate} (manual, for {manual_name})")
                break
        else:
            if verbose:
                print(f"    {auto_name:16s} stuck at {before} - {manual_name} result unreliable")

    return originals


def restore_values(cap: cv2.VideoCapture, originals: Dict[int, float]) -> None:
    for prop_id, value in originals.items():
        cap.set(prop_id, value)


def get_supported_properties(cap: cv2.VideoCapture, validate: bool = False,
                             verbose: bool = True) -> Dict[str, Dict[str, Any]]:
    originals: Dict[int, float] = {}
    if validate:
        if verbose:
            print("  Switching auto controls off for validation:")
        originals = disable_auto_modes(cap, verbose=verbose)

    supported = {}
    for name, prop_id in CAMERA_PROPERTIES.items():
        status, value = check_property_support(cap, prop_id, validate=validate)
        supported[name] = {
            "id": prop_id,
            "value": value,
            "status": status,
            "supported": status in (STATUS_WRITABLE, STATUS_REPORTED),
        }

    if validate:
        restore_values(cap, originals)

    return supported


def get_camera_properties(cap: cv2.VideoCapture, validate: bool = False,
                          verbose: bool = True) -> Dict[str, Any]:
    properties: Dict[str, Any] = {}

    ret, frame = cap.read()
    if ret:
        properties['actual_width'] = frame.shape[1]
        properties['actual_height'] = frame.shape[0]
        properties['channels'] = frame.shape[2] if len(frame.shape) == 3 else 1

    properties['width'] = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    properties['height'] = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    properties['fps'] = cap.get(cv2.CAP_PROP_FPS)
    properties['backend'] = cap.getBackendName()
    properties['fourcc'] = int(cap.get(cv2.CAP_PROP_FOURCC))
    properties['validated'] = validate
    properties['supported_properties'] = get_supported_properties(
        cap, validate=validate, verbose=verbose)

    return properties


def find_all_cameras(max_cameras: int = MAX_CAMERAS_TO_CHECK, verbose: bool = True,
                     validate: bool = False, backend: str = "auto",
                     indices: Optional[List[int]] = None) -> List[Dict[str, Any]]:
    cameras = []
    to_check = indices if indices is not None else list(range(max_cameras))
    api = BACKENDS[backend]

    # Validation writes to the camera, so it may never sweep a range: the caller
    # has to name one index it already identified in a passive scan.
    if validate and len(to_check) != 1:
        raise ValueError(
            "validate=True writes to the camera and requires exactly one "
            f"explicit index, got {to_check or 'a full scan'}. Run a passive "
            "scan first, then validate the index you want."
        )

    if verbose:
        mode = "validate (writes to camera)" if validate else "passive (read-only)"
        print("=" * 80)
        print("SEARCHING FOR CAMERAS")
        print("=" * 80)
        print(f"Backend: {backend}    Mode: {mode}")
        print(f"Checking camera indices {', '.join(str(i) for i in to_check)}...\n")

    for i in to_check:
        if verbose:
            print(f"Checking index {i}...", end=" ")

        cap = cv2.VideoCapture(i, api)

        if cap.isOpened():
            ret, frame = cap.read()
            if ret:
                if verbose:
                    print("FOUND!")

                properties = get_camera_properties(cap, validate=validate, verbose=verbose)
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


def prop_constant_name(prop_id: int) -> Optional[str]:
    matches = sorted(k for k, v in vars(cv2).items()
                     if k.startswith("CAP_PROP_") and v == prop_id)
    return matches[0] if matches else None


def save_validation_profile(name: str, camera: Dict[str, Any], backend: str,
                            folder: Optional[Path] = None) -> Path:
    """
    Builds a camera_core.CaptureConfig and hands it to that module's
    save_config(), so the schema and its defaults have one definition. Control
    keys are OpenCV property names, not libcamera ones - the two namespaces do
    not correspond, so each entry carries the prop_id needed to replay it.
    """
    props = camera["properties"]
    validated = props["supported_properties"]

    controls: Dict[str, Any] = {
        # Ignored by camera_core, which looks controls up by CONTROL_DEFS name.
        "_meta": {
            "source": "CameraFinder --validate",
            "backend": backend,
            "backend_name": props["backend"],
            "camera_index": camera["index"],
            "opencv_version": cv2.__version__,
            "validated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
    }

    for prop_name, info in validated.items():
        if info["status"] == STATUS_UNSUPPORTED:
            continue
        controls[prop_name] = {
            "enabled": info["status"] == STATUS_WRITABLE,
            "value": format_value(info["value"]),
            # Validation proves a control responds; it does not measure range.
            "min_val": None,
            "max_val": None,
            "step": None,
            "prop_id": info["id"],
            "prop_constant": prop_constant_name(info["id"]),
            "status": info["status"],
        }

    core = camera_core()
    profile = core.CaptureConfig(
        resolution_width=props["width"],
        resolution_height=props["height"],
        image_prefix=name,
        controls=controls,
    )

    target_folder = folder if folder is not None else REPO_ROOT / core.DEFAULT_CONFIG_FOLDER
    path = target_folder / f"{name}.json"
    core.save_config(profile, str(path))

    return path


def confirm_validation_target(index: int, backend: str, assume_yes: bool = False) -> bool:
    """Identify the camera and get consent before writing to it. Reads only."""
    cap = cv2.VideoCapture(index, BACKENDS[backend])
    if not cap.isOpened():
        print(f"Index {index}: no camera found - nothing to validate")
        cap.release()
        return False

    ret, _ = cap.read()
    identity = {
        "backend": cap.getBackendName(),
        "width": int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
        "height": int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
    }
    cap.release()

    if not ret:
        print(f"Index {index}: opens but delivers no frames - nothing to validate")
        return False

    print("=" * 80)
    print("VALIDATION TARGET")
    print("=" * 80)
    print(f"  Index:      {index}")
    print(f"  Backend:    {identity['backend']}")
    print(f"  Resolution: {identity['width']}x{identity['height']}")
    print()
    print("  Validation WRITES test values to this camera, including FPS and")
    print("  FOURCC. Values are restored afterwards, but a clean reset needs the")
    print("  device re-enumerated: unplug/replug, or Device Manager disable/enable")
    print("  for a built-in camera.")
    print("=" * 80)

    if assume_yes:
        print("Proceeding (--yes)\n")
        return True

    try:
        answer = input(f"Write test values to camera {index}? [y/N]: ").strip().lower()
    except EOFError:
        answer = ""
    print()
    if answer in ("y", "yes"):
        return True

    print("Aborted - nothing was written.")
    return False


def format_value(value: float) -> Any:
    if isinstance(value, float) and value == int(value):
        return int(value)
    return value


def print_shutter_verdict(props: Dict[str, Dict[str, Any]]) -> None:
    exposure = props.get("Exposure", {})
    auto_exposure = props.get("Auto Exposure", {})
    status = exposure.get("status")

    print("\n--- MANUAL SHUTTER SPEED ---")
    if status == STATUS_WRITABLE:
        print("  YES - Exposure accepted a new value with auto exposure off")
        print(f"    cv2.CAP_PROP_AUTO_EXPOSURE -> manual, then cv2.CAP_PROP_EXPOSURE "
              f"(idle value: {format_value(exposure['value'])})")
    elif status == STATUS_READONLY:
        print("  NO - Exposure is readable but ignores writes")
        if auto_exposure.get("status") != STATUS_WRITABLE:
            print("    Auto exposure could not be switched off - retry with --backend dshow")
    elif status == STATUS_UNSUPPORTED:
        print("  NO - Exposure is not reported by this backend")
        print("    Try --backend dshow / --backend msmf, they expose different controls")
    else:
        print("  UNKNOWN - run with --validate to test it")


def print_camera_details(cameras: List[Dict[str, Any]]) -> None:
    print("=" * 80)
    print(f"SUMMARY: {len(cameras)} CAMERA(S) FOUND")
    print("=" * 80)

    if not cameras:
        print("No cameras detected!")
        return

    for camera in cameras:
        idx = camera['index']
        props = camera['properties']
        validated = props.get('validated', False)

        print(f"\n{'=' * 80}")
        print(f"CAMERA INDEX: {idx}")
        print(f"{'=' * 80}")

        print(f"Backend:           {props['backend']}")
        print(f"Actual Resolution: {props['actual_width']}x{props['actual_height']}")
        print(f"Set Resolution:    {props['width']}x{props['height']}")
        print(f"FPS:               {props['fps']}")
        print(f"Channels:          {props['channels']}")
        print(f"FOURCC Code:       {props['fourcc']}")

        supported_props = props.get('supported_properties', {})
        by_status = {
            status: {k: v for k, v in supported_props.items() if v['status'] == status}
            for status in (STATUS_WRITABLE, STATUS_READONLY, STATUS_REPORTED, STATUS_UNSUPPORTED)
        }

        if validated:
            groups = [
                (STATUS_WRITABLE, "WRITABLE (verified - camera followed the write)"),
                (STATUS_READONLY, "READ-ONLY (reported, but writes are ignored)"),
            ]
        else:
            groups = [
                (STATUS_REPORTED, "REPORTED BY DRIVER (not write-tested, run --validate)"),
            ]

        for status, heading in groups:
            entries = by_status[status]
            print(f"\n--- {heading} ({len(entries)}) ---")
            if entries:
                for name, info in entries.items():
                    print(f"  {name:20s} = {format_value(info['value'])}")
            else:
                print("  None detected")

        unsupported = by_status[STATUS_UNSUPPORTED]
        print(f"\n--- UNSUPPORTED ({len(unsupported)}) ---")
        if unsupported:
            names = list(unsupported.keys())
            for i in range(0, len(names), 4):
                print(f"  {', '.join(names[i:i + 4])}")
        else:
            print("  All properties reported")

        print_shutter_verdict(supported_props)

    print(f"\n{'=' * 80}")
    print("To use a camera, note its index number and use it in the Capture script")
    print("Supported properties can be controlled via cv2.CAP_PROP_* constants")
    if any(c['properties'].get('validated') for c in cameras):
        print("Validation wrote to the camera; values were restored, and a")
        print("disconnect / reconnect resets anything that stuck.")
    print(f"{'=' * 80}\n")


def store_report(capture, target: str) -> Path:
    path = Path(target)
    if path.suffix:
        return capture.write_log_to(path)
    return capture.write_log(path)


def run(args) -> int:
    cameras = find_all_cameras(
        max_cameras=args.max_cameras if args.max_cameras is not None else MAX_CAMERAS_TO_CHECK,
        verbose=True,
        validate=args.validate,
        backend=args.backend,
        indices=args.indices,
    )

    print_camera_details(cameras)

    if cameras and args.save:
        save_validation_profile(args.save, cameras[0], args.backend)
        print(f"  Profile '{args.save}' loads with camera_core.load_config()")
        print("  Reuse it with cv2.VideoCapture.set() via each control's prop_id;")
        print("  enabled=true marks the controls the camera actually honoured.\n")

    if cameras:
        print(f"Success! Found {len(cameras)} camera(s)")
        return 0

    print("No cameras found!")
    return 1


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description=SUMMARY)
    parser.add_argument("max_cameras", nargs="?", type=int, default=None,
                        help=f"how many indices to scan, 0..N-1 (default {MAX_CAMERAS_TO_CHECK})")
    parser.add_argument("--index", "-i", type=int, action="append", dest="indices",
                        help="check only this index (repeatable; exactly one with --validate)")
    parser.add_argument("--backend", "-b", choices=sorted(BACKENDS), default="auto",
                        help="capture backend (default auto)")
    parser.add_argument("--validate", action="store_true",
                        help="WRITES test values to one named camera to verify each property")
    parser.add_argument("--yes", action="store_true",
                        help="skip the confirmation prompt before validating")
    parser.add_argument("--save", metavar="NAME",
                        help="save the validation result as a named config profile")
    parser.add_argument("--store", metavar="PATH",
                        help="also write the report to PATH")
    parser.add_argument("--info", action="store_true",
                        help="print an overview and usage, then exit")
    args = parser.parse_args()

    if args.info:
        print(INFO_TEXT)
        return 0

    if args.save and not args.validate:
        parser.error("--save stores validation results, so it needs --validate")
    if args.save and (Path(args.save).name != args.save or not args.save.strip()):
        parser.error(f"--save takes a profile name, not a path: {args.save!r}")

    if args.validate:
        # Writing to the wrong camera is not something to discover afterwards,
        # so validation takes one deliberately named index and nothing else.
        if args.max_cameras is not None:
            parser.error("--validate does not scan; drop the count and name one index with -i")
        if not args.indices:
            parser.error("--validate needs one index: scan first (no flags), then "
                         "pass -i <index> for the camera you want to test")
        if len(args.indices) > 1:
            parser.error(f"--validate takes exactly one index, got {args.indices}")
        if not confirm_validation_target(args.indices[0], args.backend, assume_yes=args.yes):
            return 1
    elif args.yes:
        parser.error("--yes only applies to --validate")

    if not args.store:
        return run(args)

    with console_logging().capture_console() as capture:
        status = run(args)
    print(f"Report written to: {store_report(capture, args.store)}")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
