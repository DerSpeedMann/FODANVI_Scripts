import cv2
import time
from pathlib import Path
from datetime import datetime
from typing import Optional, Tuple

# ============================================================================
# GLOBAL CONFIGURATION
# ============================================================================

# Camera settings
CAMERA_INDEX: int = 0  # Change this to match your camera index from CameraFinder
RESOLUTION_WIDTH: int = 1600
RESOLUTION_HEIGHT: int = 1200
CAMERA_FPS: int = 30  # Set camera FPS (may improve performance)
CAMERA_BUFFER_SIZE: int = 1  # Reduce buffer to minimize lag

# Video recording settings
OUTPUT_FOLDER: str = "recorded_videos"  # Folder to save videos
VIDEO_PREFIX: str = "recording"  # Prefix for video filenames
VIDEO_CODEC: str = "mp4v"  # Video codec (mp4v, XVID, H264, MJPG)
VIDEO_FPS: float = 30.0  # FPS for saved video

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
    cap = cv2.VideoCapture(camera_index)

    if not cap.isOpened():
        print(f"Error: Could not open camera at index {camera_index}")
        print("Run CameraFinder.py to see available cameras")
        return None

    # Set resolution
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)

    # Performance optimizations
    cap.set(cv2.CAP_PROP_FPS, CAMERA_FPS)  # Set target FPS
    cap.set(cv2.CAP_PROP_BUFFERSIZE, CAMERA_BUFFER_SIZE)  # Reduce buffer lag

    # Try to set MJPEG codec for better performance
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc('M', 'J', 'P', 'G'))

    # Verify actual resolution
    actual_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    actual_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    actual_fps = cap.get(cv2.CAP_PROP_FPS)

    print(f"Camera opened successfully!")
    print(f"Requested resolution: {width}x{height}")
    print(f"Actual resolution: {actual_width}x{actual_height}")
    print(f"Camera FPS: {actual_fps}")

    if actual_width != width or actual_height != height:
        print(f"Warning: Camera does not support requested resolution")

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
    saved_count = 0

    print("\nControls:")
    print("  'q' or ESC : Stop recording and quit")
    print("  'r'        : Toggle recording on/off")
    print("  's'        : Save current frame")
    print("  'f'        : Toggle FPS display")
    print("  'i'        : Toggle info display")
    print("  SPACE      : Pause/Resume stream")
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

            cv2.imshow(window_name, display_frame)

            # Handle key presses (reduced wait time for better FPS)
            key = cv2.waitKey(1) & 0xFF

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
                print(f"✓ Saved frame: {filename}")
            elif key == ord('f'):  # Toggle FPS
                show_fps_flag = not show_fps_flag
                print(f"FPS display: {'ON' if show_fps_flag else 'OFF'}")
            elif key == ord('i'):  # Toggle info
                show_info_flag = not show_info_flag
                print(f"Info display: {'ON' if show_info_flag else 'OFF'}")
            elif key == 32:  # SPACE - pause/resume
                paused = not paused
                print(f"Stream: {'PAUSED' if paused else 'RESUMED'}")

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
