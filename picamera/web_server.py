"""
Web server for Pi camera control.
Uses camera_core for camera operations.

Run:
    python -m picamera.web_server

Access at: http://192.168.42.1:5000
"""

import atexit
from pathlib import Path
from flask import Flask, render_template_string, jsonify, request, send_from_directory

from .camera_core import (
    CaptureConfig, init_camera, capture_image, set_control,
    get_controls, get_control_defs, close_camera,
    DEFAULT_OUTPUT_FOLDER, DEFAULT_CONFIG_FOLDER
)
from .gpio_button import setup_button, cleanup_button, is_gpio_available

# ============================================================================
# CONFIGURATION
# ============================================================================

OUTPUT_FOLDER = Path(__file__).parent.parent / DEFAULT_OUTPUT_FOLDER
CONFIG_FOLDER = Path(__file__).parent.parent / DEFAULT_CONFIG_FOLDER
GPIO_PIN = 17
SERVER_HOST = '0.0.0.0'
SERVER_PORT = 5000

# ============================================================================
# FLASK APP
# ============================================================================

app = Flask(__name__)

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Pi Camera</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        * { box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, sans-serif;
            margin: 0; padding: 20px;
            background: #1a1a2e; color: #eee;
        }
        h1 { color: #00d9ff; }
        h2 { color: #00d9ff; border-bottom: 1px solid #333; padding-bottom: 10px; }
        .container { max-width: 800px; margin: 0 auto; }

        .btn {
            background: #00d9ff; color: #000;
            border: none; padding: 15px 30px;
            font-size: 18px; cursor: pointer;
            border-radius: 5px; margin: 5px;
        }
        .btn:hover { background: #00b8d4; }
        .btn:active { transform: scale(0.98); }

        .status {
            background: #16213e; padding: 15px;
            border-radius: 5px; margin: 20px 0;
            font-family: monospace;
        }

        .control-group {
            background: #16213e; padding: 15px;
            border-radius: 5px; margin: 10px 0;
        }
        .control-group label { display: block; margin-bottom: 5px; }
        .control-group input[type="range"] { width: 100%; margin: 10px 0; }
        .control-value { color: #00d9ff; font-weight: bold; }

        .gallery {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
            gap: 10px; margin-top: 20px;
        }
        .gallery img {
            width: 100%; height: 150px;
            object-fit: cover; border-radius: 5px;
            cursor: pointer;
        }
        .gallery img:hover { opacity: 0.8; }

        .modal {
            display: none; position: fixed;
            top: 0; left: 0; width: 100%; height: 100%;
            background: rgba(0,0,0,0.9);
            justify-content: center; align-items: center;
            z-index: 1000;
        }
        .modal.active { display: flex; }
        .modal img { max-width: 95%; max-height: 95%; }
        .modal-close {
            position: absolute; top: 20px; right: 30px;
            color: #fff; font-size: 40px; cursor: pointer;
        }

        .info { color: #888; font-size: 14px; margin-top: 10px; }
    </style>
</head>
<body>
    <div class="container">
        <h1>Pi Camera</h1>

        <button class="btn" onclick="capture()">Capture</button>
        <button class="btn" onclick="refreshGallery()">Refresh</button>

        <div class="status" id="status">Ready</div>
        <div class="info">GPIO button on pin {{ gpio_pin }} {{ gpio_status }}</div>

        <h2>Controls</h2>
        <div id="controls"></div>

        <h2>Images ({{ image_count }})</h2>
        <div class="gallery" id="gallery"></div>
    </div>

    <div class="modal" id="modal" onclick="closeModal()">
        <span class="modal-close">&times;</span>
        <img id="modal-img">
    </div>

    <script>
        async function capture() {
            document.getElementById('status').innerText = 'Capturing...';
            try {
                const res = await fetch('/api/capture', { method: 'POST' });
                const data = await res.json();
                document.getElementById('status').innerText = data.message;
                if (data.success) refreshGallery();
            } catch (e) {
                document.getElementById('status').innerText = 'Error: ' + e;
            }
        }

        async function loadControls() {
            try {
                const res = await fetch('/api/controls');
                const data = await res.json();
                const container = document.getElementById('controls');
                container.innerHTML = '';

                for (const ctrl of data.controls) {
                    const div = document.createElement('div');
                    div.className = 'control-group';

                    // Handle controls with unknown limits
                    const min = ctrl.min !== null ? ctrl.min : -10;
                    const max = ctrl.max !== null ? ctrl.max : 10;

                    div.innerHTML = `
                        <label>${ctrl.name}: <span class="control-value" id="val-${ctrl.control_name}">${ctrl.value}</span></label>
                        <input type="range"
                               min="${min}" max="${max}" step="${ctrl.step}"
                               value="${ctrl.value}"
                               onchange="setControl('${ctrl.control_name}', this.value)">
                    `;
                    container.appendChild(div);
                }
            } catch (e) {
                console.error('Failed to load controls:', e);
            }
        }

        async function setControl(name, value) {
            document.getElementById('val-' + name).innerText = value;
            try {
                await fetch('/api/control', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ control_name: name, value: parseFloat(value) })
                });
            } catch (e) {
                console.error('Failed to set control:', e);
            }
        }

        async function refreshGallery() {
            try {
                const res = await fetch('/api/images');
                const data = await res.json();
                const gallery = document.getElementById('gallery');
                gallery.innerHTML = '';

                data.images.reverse().forEach(img => {
                    const el = document.createElement('img');
                    el.src = '/image/' + img;
                    el.loading = 'lazy';
                    el.onclick = () => showModal('/image/' + img);
                    gallery.appendChild(el);
                });
            } catch (e) {
                console.error('Failed to load gallery:', e);
            }
        }

        function showModal(src) {
            document.getElementById('modal-img').src = src;
            document.getElementById('modal').classList.add('active');
        }
        function closeModal() {
            document.getElementById('modal').classList.remove('active');
        }

        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') closeModal();
            if (e.key === ' ' || e.key === 'c') { e.preventDefault(); capture(); }
        });

        loadControls();
        refreshGallery();
        setInterval(refreshGallery, 5000);
    </script>
</body>
</html>
"""


@app.route('/')
def index():
    image_count = len(list(OUTPUT_FOLDER.glob('*.jpg'))) if OUTPUT_FOLDER.exists() else 0
    gpio_status = "(active)" if is_gpio_available() else "(not available)"
    return render_template_string(
        HTML_TEMPLATE,
        gpio_pin=GPIO_PIN,
        gpio_status=gpio_status,
        image_count=image_count
    )


@app.route('/api/capture', methods=['POST'])
def api_capture():
    filename, message = capture_image()
    return jsonify({
        'success': filename is not None,
        'filename': filename,
        'message': message
    })


@app.route('/api/controls')
def api_controls():
    """Get controls with their current values and definitions."""
    current = get_controls()
    defs = get_control_defs()

    controls = []
    for ctrl in defs:
        controls.append({
            'name': ctrl.name,
            'control_name': ctrl.control_name,
            'value': current.get(ctrl.control_name, ctrl.default if ctrl.default is not None else 0),
            'min': ctrl.min_val,
            'max': ctrl.max_val,
            'step': ctrl.step,
            'default': ctrl.default
        })

    return jsonify({'controls': controls})


@app.route('/api/control', methods=['POST'])
def api_set_control():
    data = request.json
    success, message, actual = set_control(data['control_name'], data['value'])
    return jsonify({'success': success, 'message': message, 'actual': actual})


@app.route('/api/images')
def api_images():
    if not OUTPUT_FOLDER.exists():
        return jsonify({'images': []})
    images = sorted([
        f.name for f in OUTPUT_FOLDER.iterdir()
        if f.suffix.lower() in ['.jpg', '.jpeg', '.png']
    ])
    return jsonify({'images': images})


@app.route('/image/<filename>')
def serve_image(filename):
    return send_from_directory(OUTPUT_FOLDER, filename)


# ============================================================================
# GPIO BUTTON HANDLER
# ============================================================================

def on_button_press():
    """Called when GPIO button is pressed."""
    print("Button pressed!")
    _, message = capture_image()
    print(f"  {message}")


# ============================================================================
# MAIN
# ============================================================================

def main():
    """Main entry point."""
    print("=" * 50)
    print("Pi Camera Web Server")
    print("=" * 50)

    OUTPUT_FOLDER.mkdir(parents=True, exist_ok=True)
    CONFIG_FOLDER.mkdir(parents=True, exist_ok=True)

    # Initialize camera
    print("\nInitializing camera...")
    config = CaptureConfig()
    if init_camera(config, output_folder=str(OUTPUT_FOLDER), config_folder=str(CONFIG_FOLDER)):
        print("Camera ready")
    else:
        print("Camera not available - running in demo mode")

    # Setup GPIO button
    print(f"\nSetting up GPIO button on pin {GPIO_PIN}...")
    if setup_button(pin=GPIO_PIN, callback=on_button_press):
        print("GPIO button ready")
    else:
        print("GPIO not available")

    # Register cleanup
    atexit.register(cleanup_button)
    atexit.register(close_camera)

    # Start server
    print(f"\n{'=' * 50}")
    print(f"Server: http://{SERVER_HOST}:{SERVER_PORT}")
    print(f"Images: {OUTPUT_FOLDER}")
    print(f"{'=' * 50}\n")

    app.run(host=SERVER_HOST, port=SERVER_PORT, debug=False, threaded=True)


if __name__ == '__main__':
    main()
