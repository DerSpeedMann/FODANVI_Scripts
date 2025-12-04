#!/usr/bin/env python3
"""
Camera CLI - command line interface for camera capture.
Uses camera_core for actual camera operations.

Usage:
    # Interactive mode (same as original CaptureImages.py)
    python camera_cli.py [config.json] [output_folder]

    # Examples:
    python camera_cli.py                           # Default settings, auto-detect limits
    python camera_cli.py config.json               # Load config
    python camera_cli.py output_folder             # Custom output folder
    python camera_cli.py config.json output_folder # Both
"""

import sys
import os
import json
from pathlib import Path

try:
    import select
    import termios
    import tty
    TERMINAL_AVAILABLE = True
except ImportError:
    TERMINAL_AVAILABLE = False

from .camera_core import (
    CameraCore, CaptureConfig, CONTROL_DEFS,
    DEFAULT_OUTPUT_FOLDER, DEFAULT_CONFIG_FOLDER,
    load_config, get_camera, close_camera
)


def capture_interactive(config: CaptureConfig = None, output_folder: str = DEFAULT_OUTPUT_FOLDER,
                        config_folder: str = DEFAULT_CONFIG_FOLDER, auto_detect: bool = False) -> int:
    """
    Interactive image capture with terminal-based controls.

    Args:
        config: Camera configuration (uses defaults if None)
        output_folder: Folder to save captured images
        config_folder: Folder for exported configs
        auto_detect: If True, auto-detect control limits when no config controls provided

    Returns:
        Number of images captured
    """
    if not TERMINAL_AVAILABLE:
        print("Error: Interactive mode requires a Unix terminal")
        print("  termios/tty modules not available")
        return 0

    # Use provided config or create default
    if config is None:
        config = CaptureConfig()

    output_path = Path(output_folder)
    output_path.mkdir(parents=True, exist_ok=True)

    print(f"\n{'='*60}")
    print("IMAGE CAPTURE")
    print(f"{'='*60}")
    print(f"Output Folder:  {output_path.absolute()}")
    print(f"Image Format:   {config.image_format}")
    print(f"Resolution:     {config.resolution_width}x{config.resolution_height}")
    print(f"{'='*60}\n")

    # Initialize camera
    camera = get_camera()
    should_auto_detect = auto_detect and not config.controls
    if not camera.init(config, output_folder=output_folder, config_folder=config_folder,
                       auto_detect_limits=should_auto_detect):
        return 0

    # Warm up
    print("Warming up camera...")
    for _ in range(5):
        camera.read_frame()

    captured_count = 0
    selected_control = 0
    control_defs = camera.get_control_defs()

    def print_status():
        print("\n" + "-" * 50)
        print(f"Captures: {captured_count} | Output: {output_path}")
        print("-" * 50)
        print("Controls:")
        controls = camera.get_all_controls()
        for i, ctrl in enumerate(control_defs):
            val = controls.get(ctrl.control_name, 0)
            marker = ">>>" if i == selected_control else "   "
            # Format limits (? for unlimited)
            min_str = "?" if ctrl.min_val is None else (
                f"{ctrl.min_val:.1f}" if isinstance(ctrl.min_val, float) and ctrl.min_val != int(ctrl.min_val)
                else str(int(ctrl.min_val))
            )
            max_str = "?" if ctrl.max_val is None else (
                f"{ctrl.max_val:.1f}" if isinstance(ctrl.max_val, float) and ctrl.max_val != int(ctrl.max_val)
                else str(int(ctrl.max_val))
            )
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
                filename, message = camera.capture()
                if filename:
                    captured_count += 1
                    print(f"\n[{captured_count}] {message}")
                else:
                    print(f"\n{message}")

            # Help
            elif key == 'h':
                print_help()

            # Status
            elif key == 'l':
                print_status()

            # Export config
            elif key == 'e':
                config_path = camera.export_config()
                print(f"\nConfig exported to: {config_path}")

            # Select control by number (1-9 = controls 1-9, 0 = control 10)
            elif key.isdigit():
                if key == '0':
                    idx = 9
                else:
                    idx = int(key) - 1
                if 0 <= idx < len(control_defs):
                    selected_control = idx
                    ctrl = control_defs[selected_control]
                    val = camera.get_all_controls().get(ctrl.control_name, 0)
                    print(f"\nSelected: {ctrl.name} = {val}")

            # Previous control
            elif key == 'w':
                if selected_control > 0:
                    selected_control -= 1
                    ctrl = control_defs[selected_control]
                    val = camera.get_all_controls().get(ctrl.control_name, 0)
                    print(f"\nSelected: {ctrl.name} = {val}")

            # Next control
            elif key == 's':
                if selected_control < len(control_defs) - 1:
                    selected_control += 1
                    ctrl = control_defs[selected_control]
                    val = camera.get_all_controls().get(ctrl.control_name, 0)
                    print(f"\nSelected: {ctrl.name} = {val}")

            # Decrease control
            elif key == '-' or key == '_':
                ctrl = control_defs[selected_control]
                name, requested, actual = camera.adjust_control(ctrl.control_name, increase=False)
                if requested != actual:
                    print(f"\n{name}: {requested} -> actual: {actual}")
                else:
                    print(f"\n{name}: {actual}")

            # Increase control
            elif key == '+' or key == '=':
                ctrl = control_defs[selected_control]
                name, requested, actual = camera.adjust_control(ctrl.control_name, increase=True)
                if requested != actual:
                    print(f"\n{name}: {requested} -> actual: {actual}")
                else:
                    print(f"\n{name}: {actual}")

    except KeyboardInterrupt:
        print("\n\nInterrupted!")

    close_camera()

    print(f"\n{'='*60}")
    print("CAPTURE COMPLETE")
    print(f"{'='*60}")
    print(f"Images Captured: {captured_count}")
    print(f"Output:          {output_path.absolute()}")
    print(f"{'='*60}\n")

    return captured_count


def main():
    """Main entry point - parse args same as original CaptureImages.py"""
    config: CaptureConfig = CaptureConfig()
    output_dir = "captured_images"
    config_loaded = False

    # Parse arguments: [config_file.json] [output_folder]
    arg_idx = 1

    if len(sys.argv) > arg_idx:
        first_arg = sys.argv[arg_idx]
        if first_arg.endswith('.json'):
            # It's a config file
            try:
                config = load_config(first_arg)
                config_loaded = True
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
            print("No config file specified - will auto-detect control limits")
            print("Press 'e' during capture to export current settings\n")

    if len(sys.argv) > arg_idx:
        output_dir = sys.argv[arg_idx]

    # Auto-detect limits only when no config file was loaded
    captured = capture_interactive(config, output_folder=output_dir, auto_detect=not config_loaded)

    sys.exit(0 if captured > 0 else 1)


if __name__ == '__main__':
    main()
