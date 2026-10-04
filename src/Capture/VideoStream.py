import cv2
import time
from pathlib import Path
from datetime import datetime
from typing import Optional, Tuple
from dataclasses import dataclass

# ============================================================================
# GLOBAL CONFIGURATION
# ============================================================================

# Camera settings
CAMERA_INDEX: int = 0  # Change this to match your camera index from CameraFinder
RESOLUTION_WIDTH: int = 800
RESOLUTION_HEIGHT: int = 600
CAMERA_FPS: int = 30  # Set camera FPS (may improve performance)
CAMERA_BUFFER_SIZE: int = 1  # Reduce buffer to minimize lag
CAMERA_INIT_DELAY: float = 1.0  # Seconds to wait for camera to settle before reading controls

# Video recording settings
OUTPUT_FOLDER: str = "recorded_videos"  # Folder to save videos
VIDEO_PREFIX: str = "recording"  # Prefix for video filenames
VIDEO_CODEC: str = "mp4v"  # Video codec (mp4v, XVID, H264, MJPG)
VIDEO_FPS: float = 15.0  # FPS for saved video

# Stream display settings
WINDOW_NAME: str = "Camera Stream"  # Window name for video stream
SHOW_FPS: bool = True  # Display FPS counter on stream
SHOW_INFO: bool = True  # Display camera info and controls on stream
FPS_UPDATE_INTERVAL: float = 0.5  # Update FPS counter every N seconds

# Display options
TEXT_COLOR: Tuple[int, int, int] = (0, 255, 0)  # Green text (BGR format)
TEXT_FONT: int = cv2.FONT_HERSHEY_SIMPLEX
TEXT_SCALE: float = 0.6
TEXT_THICKNESS: int = 2

# ============================================================================
# CAMERA CONTROL SETTINGS
# ============================================================================

@dataclass
class CameraControl:
    """Definition for an adjustable camera property"""
    prop_id: int
    name: str
    min_val: float
    max_val: float
    step: float
    supported: bool = True


# Camera control definitions: (prop_id, name, step, min, max, enabled, default)
# default=None means use camera's current value
CAMERA_CONTROL_DEFS = [
    (cv2.CAP_PROP_BRIGHTNESS, "Brightness", 2, 0, 64, True, None),
    (cv2.CAP_PROP_CONTRAST, "Contrast", 2, 0, 64, True, None),
    (cv2.CAP_PROP_SATURATION, "Saturation", 5, 0, 125, True, None),
    (cv2.CAP_PROP_HUE, "Hue", 1, -40, 40, True, None),
    (cv2.CAP_PROP_SHARPNESS, "Sharpness", 1, 0, 6, True, None),
    (cv2.CAP_PROP_GAMMA, "Gamma", 10, 80, 500, True, None),
    (cv2.CAP_PROP_GAIN, "Gain", 5, 0, 100, True, None),
    (cv2.CAP_PROP_EXPOSURE, "Exposure", 1, -13, -1, True, None),
    (cv2.CAP_PROP_BACKLIGHT, "Backlight", 1, 0, 2, True, None),
    (cv2.CAP_PROP_WB_TEMPERATURE, "WB Temp", 400, None, None, False, None),
    (cv2.CAP_PROP_AUTO_EXPOSURE, "Auto Exp", 1, 0, 1, True, 0),
    (cv2.CAP_PROP_AUTOFOCUS, "Autofocus", 1, None, None, False, None),
    (cv2.CAP_PROP_AUTO_WB, "Auto WB", 1, 0, 1, True, 0),
    (cv2.CAP_PROP_FOCUS, "Focus", 1, None, None, False, None),
    (cv2.CAP_PROP_ZOOM, "Zoom", 1, None, None, False, None),
    (cv2.CAP_PROP_ISO_SPEED, "ISO Speed", 100, None, None, False, None),
    (cv2.CAP_PROP_TEMPERATURE, "Temp", 100, None, None, False, None),
]

# Will be populated at runtime with detected min/max values
CAMERA_CONTROLS: list = []

# Track manually set values (camera may not report changes correctly)
control_values = {}

# Fallback range for properties that can't be auto-detected
FALLBACK_RANGE: int = 255  # Use -FALLBACK_RANGE to +FALLBACK_RANGE


def initialize_camera_controls(cap: cv2.VideoCapture) -> None:
    """
    Initialize camera controls with preset limits.

    Args:
        cap: VideoCapture object to probe
    """
    global CAMERA_CONTROLS
    CAMERA_CONTROLS = []

    print("\n" + "="*50)
    print("CAMERA CONTROLS")
    print("="*50)

    for prop_id, name, step, min_val, max_val, enabled, default in CAMERA_CONTROL_DEFS:
        if not enabled:
            continue

        # Use preset limits, or infinity if None
        actual_min = min_val if min_val is not None else float('-inf')
        actual_max = max_val if max_val is not None else float('inf')
        control = CameraControl(prop_id, name, actual_min, actual_max, step, True)
        CAMERA_CONTROLS.append(control)

        # Apply default value if specified, otherwise use camera's current value
        if default is not None:
            cap.set(prop_id, default)
            control_values[prop_id] = default
            applied = default
        else:
            current = cap.get(prop_id)
            control_values[prop_id] = current
            applied = current

        # Format limit display
        min_str = str(int(min_val)) if min_val is not None else "?"
        max_str = str(int(max_val)) if max_val is not None else "?"
        default_str = f" [default: {int(default)}]" if default is not None else ""
        print(f"  {name:12s}: {min_str}-{max_str} (set: {applied}){default_str}")

    print("="*50)
    print(f"Loaded {len(CAMERA_CONTROLS)} controls\n")


def adjust_camera_property(cap: cv2.VideoCapture, control: CameraControl, increase: bool) -> Tuple[float, float]:
    """
    Adjust a camera property up or down by its step value

    Args:
        cap: VideoCapture object
        control: CameraControl definition
        increase: True to increase, False to decrease

    Returns:
        Tuple of (requested_value, actual_value)
    """
    # Get current value from our tracking or from camera
    if control.prop_id in control_values:
        current = control_values[control.prop_id]
    else:
        current = cap.get(control.prop_id)

    if increase:
        new_val = min(current + control.step, control.max_val)
    else:
        new_val = max(current - control.step, control.min_val)

    # Store the requested value
    control_values[control.prop_id] = new_val

    # Try to set on camera
    cap.set(control.prop_id, new_val)
    actual = cap.get(control.prop_id)

    return new_val, actual


def get_camera_control_values(cap: cv2.VideoCapture) -> list:
    """Get current values for all camera controls"""
    values = []
    for control in CAMERA_CONTROLS:
        val = cap.get(control.prop_id)
        values.append((control.name, val, control.min_val, control.max_val))
    return values


def save_settings_file(video_filepath: Path, frame_count: int,
                       actual_fps: float, frame_width: int, frame_height: int) -> None:
    """
    Save camera settings to a .txt file alongside the video file.

    Args:
        video_filepath: Path to the video file
        frame_count: Total frames recorded
        actual_fps: Average FPS during recording
        frame_width: Frame width
        frame_height: Frame height
    """
    settings_filepath = video_filepath.with_suffix('.txt')

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    duration = frame_count / VIDEO_FPS if frame_count > 0 else 0

    lines = [
        f"Recording Settings",
        f"=" * 50,
        f"",
        f"Date/Time:       {timestamp}",
        f"Video File:      {video_filepath.name}",
        f"",
        f"Video Settings",
        f"-" * 50,
        f"Resolution:      {frame_width}x{frame_height}",
        f"Video FPS:       {VIDEO_FPS}",
        f"Video Codec:     {VIDEO_CODEC}",
        f"Total Frames:    {frame_count}",
        f"Duration:        {duration:.2f} seconds",
        f"Avg Capture FPS: {actual_fps:.1f}",
        f"",
        f"Camera Settings",
        f"-" * 50,
        f"Camera Index:    {CAMERA_INDEX}",
        f"Camera FPS:      {CAMERA_FPS}",
        f"Buffer Size:     {CAMERA_BUFFER_SIZE}",
        f"Init Delay:      {CAMERA_INIT_DELAY}s",
        f"",
        f"Camera Controls",
        f"-" * 50,
    ]

    # Add all control values
    for control in CAMERA_CONTROLS:
        if control.prop_id in control_values:
            val = control_values[control.prop_id]
        else:
            val = -1  # Unknown if camera already released

        if val == int(val):
            val_str = str(int(val))
        else:
            val_str = f"{val:.2f}"

        lines.append(f"{control.name:12s}: {val_str}")

    lines.append("")
    lines.append("=" * 50)

    # Write to file
    with open(settings_filepath, 'w') as f:
        f.write('\n'.join(lines))

    print(f"Settings saved:      {settings_filepath}")


def setup_camera(camera_index: int, width: int, height: int) -> Optional[cv2.VideoCapture]:
    """
    Initialize and configure camera with optimized settings

    Args:
        camera_index: Camera index to open
        width: Desired frame width
        height: Desired frame height

    Returns:
        VideoCapture object if successful, None otherwise
    """
    print(f"Opening camera at index {camera_index}...")

    # On Windows, use DirectShow backend for better performance
    cap = cv2.VideoCapture(camera_index, cv2.CAP_DSHOW)

    if not cap.isOpened():
        print(f"DirectShow failed, trying default backend...")
        cap = cv2.VideoCapture(camera_index)

    if not cap.isOpened():
        print(f"Error: Could not open camera at index {camera_index}")
        print("Run CameraFinder.py to see available cameras")
        return None

    # Set FOURCC before resolution for proper format selection
    # YUY2 performs better than MJPEG on this camera (tested with CameraProbe.py)
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc('Y', 'U', 'Y', '2'))

    # Set resolution after FOURCC
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)

    # Performance optimizations
    cap.set(cv2.CAP_PROP_FPS, CAMERA_FPS)  # Set target FPS
    cap.set(cv2.CAP_PROP_BUFFERSIZE, CAMERA_BUFFER_SIZE)  # Reduce buffer lag

    # Verify actual settings
    actual_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    actual_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    actual_fps = cap.get(cv2.CAP_PROP_FPS)
    fourcc_code = int(cap.get(cv2.CAP_PROP_FOURCC))
    fourcc_str = "".join([chr((fourcc_code >> 8 * i) & 0xFF) for i in range(4)])

    print(f"Camera opened successfully!")
    print(f"Requested resolution: {width}x{height}")
    print(f"Actual resolution: {actual_width}x{actual_height}")
    print(f"Camera FPS: {actual_fps}")
    print(f"Camera Format: {fourcc_str}")

    if actual_width != width or actual_height != height:
        print(f"Warning: Camera does not support requested resolution")

    # Wait for camera to settle before reading control values
    print("Waiting for camera to initialize...")
    time.sleep(CAMERA_INIT_DELAY)

    # Detect supported camera controls and their ranges
    initialize_camera_controls(cap)

    return cap

def draw_text_with_background(frame, text: str, position: Tuple[int, int],
                              font=cv2.FONT_HERSHEY_SIMPLEX, scale: float = 0.6,
                              color: Tuple[int, int, int] = (0, 255, 0),
                              thickness: int = 2, bg_color: Tuple[int, int, int] = (0, 0, 0)):
    """
    Draw text with a background rectangle for better visibility

    Args:
        frame: Image frame to draw on
        text: Text to display
        position: (x, y) position for text
        font: OpenCV font type
        scale: Font scale
        color: Text color (BGR)
        thickness: Text thickness
        bg_color: Background color (BGR)
    """
    x, y = position

    # Get text size
    (text_width, text_height), baseline = cv2.getTextSize(text, font, scale, thickness)

    # Draw background rectangle
    padding = 5
    cv2.rectangle(frame,
                 (x - padding, y - text_height - padding),
                 (x + text_width + padding, y + baseline + padding),
                 bg_color, -1)

    # Draw text
    cv2.putText(frame, text, (x, y), font, scale, color, thickness)

def start_video_stream(camera_index: int = CAMERA_INDEX,
                      width: int = RESOLUTION_WIDTH,
                      height: int = RESOLUTION_HEIGHT,
                      window_name: str = WINDOW_NAME,
                      show_fps: bool = SHOW_FPS,
                      show_info: bool = SHOW_INFO,
                      output_folder: str = OUTPUT_FOLDER) -> None:
    """
    Start a live video stream from the camera and save to file

    Args:
        camera_index: Camera index to use
        width: Desired frame width
        height: Desired frame height
        window_name: Name of the display window
        show_fps: Whether to display FPS counter
        show_info: Whether to display camera info and controls
        output_folder: Folder to save video file

    Controls:
        - 'q' or ESC: Stop recording and quit
        - 'r': Start/Stop recording
        - 's': Save current frame as image
        - 'f': Toggle FPS display
        - 'i': Toggle info display
        - SPACE: Pause/Resume stream
    """
    # Create output folder
    output_path = Path(output_folder)
    output_path.mkdir(parents=True, exist_ok=True)

    # Generate video filename
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    video_filename = f"{VIDEO_PREFIX}_{timestamp}.mp4"
    video_filepath = output_path / video_filename

    print(f"\n{'='*80}")
    print(f"VIDEO STREAM CONFIGURATION")
    print(f"{'='*80}")
    print(f"Camera Index:        {camera_index}")
    print(f"Resolution:          {width}x{height}")
    print(f"Window Name:         {window_name}")
    print(f"Output File:         {video_filepath}")
    print(f"Video FPS:           {VIDEO_FPS}")
    print(f"Video Codec:         {VIDEO_CODEC}")
    print(f"{'='*80}\n")

    # Setup camera
    cap = setup_camera(camera_index, width, height)
    if cap is None:
        return

    # Get actual frame size for video writer
    ret, test_frame = cap.read()
    if not ret:
        print("Error: Could not read test frame")
        cap.release()
        return

    frame_height, frame_width = test_frame.shape[:2]

    # Setup video writer
    fourcc = cv2.VideoWriter_fourcc(*VIDEO_CODEC)
    video_writer = cv2.VideoWriter(
        str(video_filepath),
        fourcc,
        VIDEO_FPS,
        (frame_width, frame_height)
    )

    if not video_writer.isOpened():
        print("Error: Could not open video writer")
        cap.release()
        return

    print(f"Recording to: {video_filepath}")

    # Create window
    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)

    # FPS calculation variables
    fps = 0.0
    frame_count = 0
    fps_start_time = time.time()
    last_fps_update = time.time()

    # State variables
    paused = False
    recording = True
    show_fps_flag = show_fps
    show_info_flag = show_info
    show_controls_flag = False  # Show camera controls overlay
    saved_count = 0
    selected_control = 0  # Currently selected camera control (0-8)

    print("\nControls:")
    print("  'q' or ESC : Stop recording and quit")
    print("  'r'        : Toggle recording on/off")
    print("  's'        : Save current frame")
    print("  'f'        : Toggle FPS display")
    print("  'i'        : Toggle info display")
    print("  'c'        : Toggle camera controls overlay")
    print("  SPACE      : Pause/Resume stream")
    print("\nCamera Adjustment (when controls visible):")
    print("  UP/DOWN    : Navigate between properties")
    print("  LEFT/RIGHT : Decrease/Increase value")
    print("  +/-        : Decrease/Increase value")
    print("\nRecording started... Press 'q' or ESC to stop\n")

    try:
        while True:
            # Read frame regardless of pause state for smooth video
            ret, frame = cap.read()

            if not ret:
                print("Error: Failed to read frame from camera")
                break

            # Calculate FPS
            frame_count += 1
            current_time = time.time()
            if current_time - last_fps_update >= FPS_UPDATE_INTERVAL:
                fps = frame_count / (current_time - fps_start_time)
                last_fps_update = current_time

            # Write frame to video if recording
            if recording and not paused:
                video_writer.write(frame)

            # Display frame (work on a copy for overlay)
            display_frame = frame.copy()

            # Draw recording indicator
            if recording:
                rec_text = "REC"
                rec_color = (0, 0, 255) if int(current_time * 2) % 2 == 0 else (0, 100, 255)  # Blinking red
                draw_text_with_background(display_frame, rec_text, (frame_width - 80, 30),
                                        TEXT_FONT, TEXT_SCALE, rec_color, TEXT_THICKNESS)

            # Draw FPS
            if show_fps_flag:
                fps_text = f"FPS: {fps:.1f}"
                draw_text_with_background(display_frame, fps_text, (10, 30),
                                        TEXT_FONT, TEXT_SCALE, TEXT_COLOR, TEXT_THICKNESS)

            # Draw info
            if show_info_flag:
                y_offset = 70 if show_fps_flag else 30
                info_lines = [
                    f"Camera: {camera_index}",
                    f"Resolution: {frame.shape[1]}x{frame.shape[0]}",
                    f"Frames: {frame_count}",
                    f"Recording: {'Yes' if recording else 'No'}",
                    f"Paused: {'Yes' if paused else 'No'}"
                ]
                for i, line in enumerate(info_lines):
                    draw_text_with_background(display_frame, line,
                                            (10, y_offset + i * 30),
                                            TEXT_FONT, TEXT_SCALE - 0.1,
                                            TEXT_COLOR, TEXT_THICKNESS - 1)

            # Draw camera controls panel
            if show_controls_flag:
                panel_x = frame_width - 280
                panel_y = 70
                draw_text_with_background(display_frame, "Camera Controls",
                                        (panel_x, panel_y),
                                        TEXT_FONT, TEXT_SCALE, (255, 255, 0), TEXT_THICKNESS)

                for i, control in enumerate(CAMERA_CONTROLS):
                    # Use tracked value if available, otherwise get from camera
                    if control.prop_id in control_values:
                        val = control_values[control.prop_id]
                    else:
                        val = cap.get(control.prop_id)

                    # Highlight selected control
                    if i == selected_control:
                        color = (0, 255, 255)  # Yellow for selected
                        prefix = ">"
                    else:
                        color = TEXT_COLOR
                        prefix = " "

                    # Format value
                    if val == int(val):
                        val_str = f"{int(val)}"
                    else:
                        val_str = f"{val:.1f}"

                    text = f"{prefix}{i+1}. {control.name}: {val_str}"
                    draw_text_with_background(display_frame, text,
                                            (panel_x, panel_y + 30 + i * 25),
                                            TEXT_FONT, TEXT_SCALE - 0.1,
                                            color, TEXT_THICKNESS - 1)

                # Draw instructions at bottom of panel
                draw_text_with_background(display_frame, "UP/DOWN:Nav  LEFT/RIGHT:Adjust",
                                        (panel_x, panel_y + 30 + len(CAMERA_CONTROLS) * 25 + 10),
                                        TEXT_FONT, TEXT_SCALE - 0.15,
                                        (200, 200, 200), 1)

            cv2.imshow(window_name, display_frame)

            # Handle key presses (reduced wait time for better FPS)
            # Use waitKeyEx for proper arrow key detection on Windows
            key_raw = cv2.waitKeyEx(1)
            key = key_raw & 0xFF  # Lower byte for regular keys

            if key == ord('q') or key == 27:  # 'q' or ESC
                print("\nStopping stream...")
                break
            elif key == ord('r'):  # Toggle recording
                recording = not recording
                print(f"Recording: {'ON' if recording else 'OFF'}")
            elif key == ord('s'):  # Save frame
                timestamp = time.strftime("%Y%m%d_%H%M%S")
                filename = f"stream_capture_{timestamp}_{saved_count:03d}.jpg"
                cv2.imwrite(filename, frame)
                saved_count += 1
                print(f"ok: Saved frame: {filename}")
            elif key == ord('f'):  # Toggle FPS
                show_fps_flag = not show_fps_flag
                print(f"FPS display: {'ON' if show_fps_flag else 'OFF'}")
            elif key == ord('i'):  # Toggle info
                show_info_flag = not show_info_flag
                print(f"Info display: {'ON' if show_info_flag else 'OFF'}")
            elif key == ord('c'):  # Toggle camera controls
                show_controls_flag = not show_controls_flag
                print(f"Camera controls: {'ON' if show_controls_flag else 'OFF'}")
            elif key == 32:  # SPACE - pause/resume
                paused = not paused
                print(f"Stream: {'PAUSED' if paused else 'RESUMED'}")

            # Camera control navigation (UP/DOWN arrows)
            # Arrow key codes with waitKeyEx:
            # Windows: UP=2490368, DOWN=2621440, LEFT=2424832, RIGHT=2555904
            # Linux: UP=65362, DOWN=65364, LEFT=65361, RIGHT=65363
            elif key_raw == 2490368 or key_raw == 65362:  # UP arrow
                if show_controls_flag and CAMERA_CONTROLS and selected_control > 0:
                    selected_control -= 1
                    control = CAMERA_CONTROLS[selected_control]
                    val = cap.get(control.prop_id)
                    print(f"Selected: {control.name} = {val}")
            elif key_raw == 2621440 or key_raw == 65364:  # DOWN arrow
                if show_controls_flag and CAMERA_CONTROLS and selected_control < len(CAMERA_CONTROLS) - 1:
                    selected_control += 1
                    control = CAMERA_CONTROLS[selected_control]
                    val = cap.get(control.prop_id)
                    print(f"Selected: {control.name} = {val}")

            # Camera control adjustment (LEFT/RIGHT arrows or +/-)
            elif key_raw == 2424832 or key_raw == 65361 or key == ord('-') or key == ord('_'):  # LEFT arrow or -
                if show_controls_flag and CAMERA_CONTROLS:
                    control = CAMERA_CONTROLS[selected_control]
                    requested, actual = adjust_camera_property(cap, control, increase=False)
                    print(f"{control.name}: {requested} (camera: {actual})")
            elif key_raw == 2555904 or key_raw == 65363 or key == ord('+') or key == ord('='):  # RIGHT arrow or +
                if show_controls_flag and CAMERA_CONTROLS:
                    control = CAMERA_CONTROLS[selected_control]
                    requested, actual = adjust_camera_property(cap, control, increase=True)
                    print(f"{control.name}: {requested} (camera: {actual})")

    except KeyboardInterrupt:
        print("\n\nStream interrupted by user!")
    finally:
        # Release resources
        video_writer.release()
        cap.release()
        cv2.destroyAllWindows()

        # Calculate video duration
        duration = frame_count / VIDEO_FPS if frame_count > 0 else 0

        print(f"\n{'='*80}")
        print(f"RECORDING COMPLETE")
        print(f"{'='*80}")
        print(f"Video saved:         {video_filepath}")
        print(f"Total frames:        {frame_count}")
        print(f"Duration:            {duration:.2f} seconds")
        print(f"Average FPS:         {fps:.1f}")

        # Save settings file alongside video
        save_settings_file(video_filepath, frame_count, fps, frame_width, frame_height)

        if saved_count > 0:
            print(f"Snapshots saved:     {saved_count}")
        print(f"{'='*80}\n")

if __name__ == "__main__":
    import sys

    # Parse command line arguments
    camera_idx = CAMERA_INDEX
    res_width = RESOLUTION_WIDTH
    res_height = RESOLUTION_HEIGHT

    if len(sys.argv) > 1:
        try:
            camera_idx = int(sys.argv[1])
        except ValueError:
            print(f"Error: Invalid camera index '{sys.argv[1]}'")
            print("Usage: python VideoStream.py [camera_index] [width] [height]")
            exit(1)

    if len(sys.argv) > 2:
        try:
            res_width = int(sys.argv[2])
        except ValueError:
            print(f"Error: Invalid width '{sys.argv[2]}'")
            exit(1)

    if len(sys.argv) > 3:
        try:
            res_height = int(sys.argv[3])
        except ValueError:
            print(f"Error: Invalid height '{sys.argv[3]}'")
            exit(1)

    # Start video stream
    start_video_stream(
        camera_index=camera_idx,
        width=res_width,
        height=res_height
    )
