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
    get_controls, get_control_defs, close_camera, is_camera_ready,
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
        h1 { color: #00d9ff; margin: 0; }
        h2 { color: #00d9ff; border-bottom: 1px solid #333; padding-bottom: 10px; }
        .container { max-width: 800px; margin: 0 auto; }

        .header {
            display: flex; justify-content: space-between; align-items: center;
            margin-bottom: 20px;
        }
        .status-indicators {
            display: flex; gap: 15px; font-size: 14px;
        }
        .status-item {
            display: flex; align-items: center; gap: 5px;
        }
        .status-dot {
            width: 10px; height: 10px; border-radius: 50%;
        }
        .status-dot.green { background: #00ff88; }
        .status-dot.red { background: #ff4444; }

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
            display: none;
        }
        .status.visible { display: block; }
        .status.error { background: #3e1616; color: #ff6b6b; }

        .controls-section {
            margin: 20px 0;
        }
        .controls-toggle {
            background: #16213e; color: #00d9ff;
            border: 1px solid #333; padding: 10px 15px;
            font-size: 16px; cursor: pointer;
            border-radius: 5px; width: 100%;
            text-align: left;
            display: flex; justify-content: space-between; align-items: center;
        }
        .controls-toggle:hover { background: #1e2a4a; }
        .controls-toggle .arrow { transition: transform 0.2s; }
        .controls-toggle.open .arrow { transform: rotate(180deg); }
        .controls-content {
            display: none;
            padding-top: 10px;
        }
        .controls-content.open { display: block; }

        .control-group {
            background: #16213e; padding: 15px;
            border-radius: 5px; margin: 10px 0;
        }
        .control-group label { display: block; margin-bottom: 8px; }
        .control-row {
            display: flex; align-items: center; gap: 8px;
        }
        .control-row input[type="range"] { flex: 1; }
        .step-btn {
            background: #333; color: #00d9ff;
            border: 1px solid #444; width: 36px; height: 36px;
            font-size: 18px; cursor: pointer; border-radius: 4px;
        }
        .step-btn:hover { background: #444; }
        .step-btn:active { transform: scale(0.95); }
        .value-input {
            width: 70px; background: #0d1117; color: #00d9ff;
            border: 1px solid #333; padding: 6px 8px;
            font-size: 14px; border-radius: 4px; text-align: center;
        }
        .value-input:focus { outline: 1px solid #00d9ff; }

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
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Pi Camera</h1>
            <div class="status-indicators">
                <div class="status-item">
                    <span class="status-dot {{ 'green' if camera_ready else 'red' }}"></span>
                    <span>CAM</span>
                </div>
                <div class="status-item">
                    <span class="status-dot {{ 'green' if gpio_available else 'red' }}"></span>
                    <span>GPIO {{ gpio_pin }}</span>
                </div>
            </div>
        </div>

        <button class="btn" onclick="capture()">Capture</button>
        <button class="btn" onclick="refreshGallery()">Refresh</button>

        <div class="status" id="status"></div>

        <div class="controls-section">
            <button class="controls-toggle" onclick="toggleControls()">
                <span>Controls</span>
                <span class="arrow">&#9660;</span>
            </button>
            <div class="controls-content" id="controls"></div>
        </div>

        <h2>Images (<span id="image-count">{{ image_count }}</span>)</h2>
        <div class="gallery" id="gallery"></div>
    </div>

    <div class="modal" id="modal" onclick="closeModal()">
        <span class="modal-close">&times;</span>
        <img id="modal-img">
    </div>

    <script>
        let imageCount = {{ image_count }};
        let controlMeta = {};

        function toggleControls() {
            const toggle = document.querySelector('.controls-toggle');
            const content = document.getElementById('controls');
            toggle.classList.toggle('open');
            content.classList.toggle('open');
        }

        function showStatus(msg, isError = false) {
            const el = document.getElementById('status');
            el.innerText = msg;
            el.classList.add('visible');
            el.classList.toggle('error', isError);
            if (!isError) {
                setTimeout(() => el.classList.remove('visible'), 3000);
            }
        }

        async function capture() {
            const statusEl = document.getElementById('status');
            statusEl.classList.remove('visible', 'error');
            try {
                const res = await fetch('/api/capture', { method: 'POST' });
                const data = await res.json();
                if (data.success) {
                    imageCount++;
                    document.getElementById('image-count').innerText = imageCount;
                    addImageToGallery(data.filename);
                } else {
                    showStatus(data.message, true);
                }
            } catch (e) {
                showStatus('Error: ' + e, true);
            }
        }

        function addImageToGallery(filename) {
            const gallery = document.getElementById('gallery');
            const el = document.createElement('img');
            el.src = '/image/' + filename;
            el.loading = 'lazy';
            el.onclick = () => showModal('/image/' + filename);
            gallery.insertBefore(el, gallery.firstChild);
        }

        async function loadControls() {
            const container = document.getElementById('controls');
            if (!container) return;

            try {
                const res = await fetch('/api/controls');
                const data = await res.json();
                container.innerHTML = '';

                for (const ctrl of data.controls) {
                    const min = ctrl.min !== null ? ctrl.min : -10;
                    const max = ctrl.max !== null ? ctrl.max : 10;
                    controlMeta[ctrl.control_name] = { min, max, step: ctrl.step };

                    const div = document.createElement('div');
                    div.className = 'control-group';
                    div.innerHTML = `
                        <label>${ctrl.name}</label>
                        <div class="control-row">
                            <button class="step-btn" onclick="stepControl('${ctrl.control_name}', -1)">-</button>
                            <input type="range" id="slider-${ctrl.control_name}"
                                   min="${min}" max="${max}" step="${ctrl.step}"
                                   value="${ctrl.value}"
                                   oninput="updateFromSlider('${ctrl.control_name}', this.value)"
                                   onchange="setControl('${ctrl.control_name}', this.value)">
                            <button class="step-btn" onclick="stepControl('${ctrl.control_name}', 1)">+</button>
                            <input type="text" class="value-input" id="input-${ctrl.control_name}"
                                   value="${ctrl.value}"
                                   onkeydown="if(event.key==='Enter')applyInput('${ctrl.control_name}')"
                                   onblur="applyInput('${ctrl.control_name}')">
                        </div>
                    `;
                    container.appendChild(div);
                }
            } catch (e) {
                console.error('Failed to load controls:', e);
            }
        }

        function updateFromSlider(name, value) {
            document.getElementById('input-' + name).value = value;
        }

        function stepControl(name, direction) {
            const meta = controlMeta[name];
            const slider = document.getElementById('slider-' + name);
            let newVal = parseFloat(slider.value) + (direction * meta.step);
            newVal = Math.max(meta.min, Math.min(meta.max, newVal));
            newVal = Math.round(newVal / meta.step) * meta.step;
            slider.value = newVal;
            document.getElementById('input-' + name).value = newVal;
            setControl(name, newVal);
        }

        function applyInput(name) {
            const meta = controlMeta[name];
            const input = document.getElementById('input-' + name);
            let val = parseFloat(input.value);
            if (isNaN(val)) val = 0;
            val = Math.max(meta.min, Math.min(meta.max, val));
            val = Math.round(val / meta.step) * meta.step;
            input.value = val;
            document.getElementById('slider-' + name).value = val;
            setControl(name, val);
        }

        async function setControl(name, value) {
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

                imageCount = data.images.length;
                document.getElementById('image-count').innerText = imageCount;

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
    </script>
</body>
</html>
"""


@app.route('/')
def index():
    image_count = len(list(OUTPUT_FOLDER.glob('*.jpg'))) if OUTPUT_FOLDER.exists() else 0
    return render_template_string(
        HTML_TEMPLATE,
        image_count=image_count,
        camera_ready=is_camera_ready(),
        gpio_available=is_gpio_available(),
        gpio_pin=GPIO_PIN
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
    """Get controls with their current values and definitions (excludes hidden)."""
    current = get_controls()
    defs = get_control_defs()

    controls = []
    for ctrl in defs:
        if ctrl.hidden:
            continue
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
