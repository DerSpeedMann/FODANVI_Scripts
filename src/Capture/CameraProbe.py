"""
Camera Resolution and Format Probe

Tests various resolutions and formats to find optimal camera settings.
Measures actual FPS at each configuration.
"""

import cv2
import time
from typing import List, Tuple, Dict, Any

# Common resolutions to test (width, height)
RESOLUTIONS_TO_TEST = [
    (320, 240),    # QVGA
    (640, 480),    # VGA
    (800, 600),    # SVGA
    (1024, 768),   # XGA
    (1280, 720),   # 720p HD
    (1280, 960),   # SXGA-
    (1280, 1024),  # SXGA
    (1600, 1200),  # UXGA
    (1920, 1080),  # 1080p Full HD
    (2048, 1536),  # QXGA
    (2592, 1944),  # 5MP
    (3264, 2448),  # 8MP
]

# FOURCC codes to test
FOURCC_FORMATS = [
    ('MJPG', cv2.VideoWriter_fourcc('M', 'J', 'P', 'G')),
    ('YUY2', cv2.VideoWriter_fourcc('Y', 'U', 'Y', '2')),
    ('YUYV', cv2.VideoWriter_fourcc('Y', 'U', 'Y', 'V')),
    ('RGB3', cv2.VideoWriter_fourcc('R', 'G', 'B', '3')),
    ('BGR3', cv2.VideoWriter_fourcc('B', 'G', 'R', '3')),
    ('I420', cv2.VideoWriter_fourcc('I', '4', '2', '0')),
    ('NV12', cv2.VideoWriter_fourcc('N', 'V', '1', '2')),
]


def measure_fps(cap: cv2.VideoCapture, num_frames: int = 30) -> float:
    """Measure actual FPS by capturing frames"""
    # Warm up - discard first few frames
    for _ in range(5):
        cap.read()

    start = time.perf_counter()
    for _ in range(num_frames):
        ret, _ = cap.read()
        if not ret:
            return 0.0
    elapsed = time.perf_counter() - start

    return num_frames / elapsed if elapsed > 0 else 0.0


def get_fourcc_string(cap: cv2.VideoCapture) -> str:
    """Get the current FOURCC as a string"""
    fourcc = int(cap.get(cv2.CAP_PROP_FOURCC))
    return "".join([chr((fourcc >> 8 * i) & 0xFF) for i in range(4)])


def test_format(camera_index: int, fourcc_name: str, fourcc_code: int) -> List[Dict[str, Any]]:
    """Test all resolutions with a specific format"""
    results = []

    print(f"\n{'='*60}")
    print(f"Testing format: {fourcc_name}")
    print(f"{'='*60}")

    for width, height in RESOLUTIONS_TO_TEST:
        # Open camera fresh for each test
        cap = cv2.VideoCapture(camera_index, cv2.CAP_DSHOW)
        if not cap.isOpened():
            cap = cv2.VideoCapture(camera_index)

        if not cap.isOpened():
            print(f"  {width}x{height}: Failed to open camera")
            continue

        # Set format BEFORE resolution
        cap.set(cv2.CAP_PROP_FOURCC, fourcc_code)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)

        # Check actual values
        actual_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        actual_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        actual_fourcc = get_fourcc_string(cap)
        reported_fps = cap.get(cv2.CAP_PROP_FPS)

        # Skip if camera didn't accept this resolution
        if actual_w != width or actual_h != height:
            cap.release()
            continue

        # Measure actual FPS
        actual_fps = measure_fps(cap, num_frames=30)

        result = {
            'width': actual_w,
            'height': actual_h,
            'format': actual_fourcc,
            'requested_format': fourcc_name,
            'reported_fps': reported_fps,
            'actual_fps': actual_fps,
        }
        results.append(result)

        format_match = "✓" if actual_fourcc == fourcc_name else f"→{actual_fourcc}"
        print(f"  {width}x{height}: {actual_fps:.1f} FPS (reported: {reported_fps:.0f}) [{format_match}]")

        cap.release()

    return results


def probe_camera(camera_index: int = 0) -> Dict[str, Any]:
    """
    Probe camera for all supported resolutions and formats

    Returns dict with all results and recommendations
    """
    print("="*60)
    print(f"CAMERA PROBE - Index {camera_index}")
    print("="*60)

    # First, check what formats the camera supports
    cap = cv2.VideoCapture(camera_index, cv2.CAP_DSHOW)
    if not cap.isOpened():
        cap = cv2.VideoCapture(camera_index)

    if not cap.isOpened():
        print(f"Error: Could not open camera {camera_index}")
        return {}

    # Get default settings
    default_fourcc = get_fourcc_string(cap)
    default_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    default_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    default_fps = cap.get(cv2.CAP_PROP_FPS)
    backend = cap.getBackendName()

    print(f"Backend: {backend}")
    print(f"Default: {default_w}x{default_h} @ {default_fps} FPS [{default_fourcc}]")

    cap.release()

    # Test each format
    all_results = []

    # Test MJPG first (most important)
    mjpg_results = test_format(camera_index, 'MJPG', cv2.VideoWriter_fourcc('M', 'J', 'P', 'G'))
    all_results.extend(mjpg_results)

    # Test default/YUY2 format
    yuy2_results = test_format(camera_index, 'YUY2', cv2.VideoWriter_fourcc('Y', 'U', 'Y', '2'))
    all_results.extend(yuy2_results)

    # Summary
    print("\n" + "="*60)
    print("SUMMARY - Best configurations")
    print("="*60)

    if not all_results:
        print("No valid configurations found!")
        return {'results': [], 'recommendations': []}

    # Sort by actual FPS descending
    sorted_results = sorted(all_results, key=lambda x: x['actual_fps'], reverse=True)

    # Find best for each resolution
    seen_resolutions = set()
    best_configs = []

    for r in sorted_results:
        res_key = (r['width'], r['height'])
        if res_key not in seen_resolutions:
            seen_resolutions.add(res_key)
            best_configs.append(r)

    # Sort by resolution (megapixels)
    best_configs.sort(key=lambda x: x['width'] * x['height'], reverse=True)

    print(f"\n{'Resolution':<15} {'Format':<8} {'FPS':<10} {'Recommendation'}")
    print("-"*55)

    recommendations = []
    for cfg in best_configs:
        res_str = f"{cfg['width']}x{cfg['height']}"
        fps_str = f"{cfg['actual_fps']:.1f}"

        # Recommendation based on FPS
        if cfg['actual_fps'] >= 25:
            rec = "Excellent"
        elif cfg['actual_fps'] >= 15:
            rec = "Good"
        elif cfg['actual_fps'] >= 10:
            rec = "Acceptable"
        else:
            rec = "Slow"

        print(f"{res_str:<15} {cfg['format']:<8} {fps_str:<10} {rec}")

        if cfg['actual_fps'] >= 15:
            recommendations.append(cfg)

    # Best overall recommendation
    print("\n" + "="*60)
    print("RECOMMENDED SETTINGS")
    print("="*60)

    if recommendations:
        # Find highest resolution with good FPS
        best = max(recommendations, key=lambda x: x['width'] * x['height'])
        print(f"\nBest quality:  {best['width']}x{best['height']} [{best['format']}] @ {best['actual_fps']:.1f} FPS")

        # Find highest FPS
        fastest = max(recommendations, key=lambda x: x['actual_fps'])
        print(f"Best speed:    {fastest['width']}x{fastest['height']} [{fastest['format']}] @ {fastest['actual_fps']:.1f} FPS")

        # Check if MJPEG provides benefit
        mjpg_configs = [r for r in all_results if r['format'] == 'MJPG']
        yuy2_configs = [r for r in all_results if r['format'] != 'MJPG']

        print(f"\nMJPEG supported: {'Yes' if mjpg_configs else 'No'}")

        if mjpg_configs and yuy2_configs:
            # Compare same resolution
            for mjpg in mjpg_configs:
                for yuy2 in yuy2_configs:
                    if mjpg['width'] == yuy2['width'] and mjpg['height'] == yuy2['height']:
                        speedup = mjpg['actual_fps'] / yuy2['actual_fps'] if yuy2['actual_fps'] > 0 else 0
                        if speedup > 1.1:
                            print(f"  At {mjpg['width']}x{mjpg['height']}: MJPG is {speedup:.1f}x faster than {yuy2['format']}")
    else:
        print("No configurations with >=15 FPS found. Camera may be too slow for real-time use.")

    print("="*60)

    return {
        'results': all_results,
        'recommendations': recommendations,
        'default': {
            'width': default_w,
            'height': default_h,
            'format': default_fourcc,
            'fps': default_fps
        }
    }


if __name__ == "__main__":
    import sys

    camera_idx = 0
    if len(sys.argv) > 1:
        try:
            camera_idx = int(sys.argv[1])
        except ValueError:
            print(f"Invalid camera index: {sys.argv[1]}")
            exit(1)

    probe_camera(camera_idx)
