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
    get_camera, load_config,
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

        .config-section {
            background: #0d1117; border-radius: 5px;
            padding: 10px; margin-bottom: 10px;
        }
        .config-row {
            display: flex; align-items: center; gap: 8px;
            margin-bottom: 8px;
        }
        .config-row:last-child { margin-bottom: 0; }
        .config-row label { min-width: 50px; }
        .config-btn {
            background: #00d9ff; color: #000;
            border: none; padding: 8px 12px;
            font-size: 14px; cursor: pointer; border-radius: 4px;
        }
        .config-btn:hover { background: #00b8d4; }
        .config-upload { display: none; }

        .config-dropdown {
            position: relative; flex: 1;
        }
        .config-dropdown-btn {
            width: 100%; background: #16213e; color: #00d9ff;
            border: 1px solid #333; padding: 8px 12px;
            font-size: 14px; border-radius: 4px;
            text-align: left; cursor: pointer;
            display: flex; justify-content: space-between; align-items: center;
        }
        .config-dropdown-btn:hover { background: #1e2a4a; }
        .config-dropdown-list {
            display: none; position: absolute; top: 100%; left: 0; right: 0;
            background: #16213e; border: 1px solid #333; border-radius: 4px;
            max-height: 200px; overflow-y: auto; z-index: 100;
            margin-top: 2px;
        }
        .config-dropdown.open .config-dropdown-list { display: block; }
        .config-item {
            display: flex; align-items: center; padding: 6px 10px;
            border-bottom: 1px solid #333;
        }
        .config-item:last-child { border-bottom: none; }
        .config-item:hover { background: #1e2a4a; }
        .config-item-name {
            flex: 1; cursor: pointer; padding: 4px 0;
            white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
        }
        .config-item-btn {
            background: transparent; color: #00d9ff; border: none;
            width: 28px; height: 28px; cursor: pointer; border-radius: 4px;
            font-size: 14px;
        }
        .config-item-btn:hover { background: #333; }
        .config-item-btn.danger { color: #ff4444; }
        .config-item-btn.danger:hover { background: #3e1616; }

        .gallery {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
            gap: 10px; margin-top: 20px;
        }
        .gallery-item {
            position: relative;
        }
        .gallery-item img {
            width: 100%; height: 150px;
            object-fit: cover; border-radius: 5px;
            cursor: pointer;
        }
        .gallery-item img:hover { opacity: 0.8; }
        .gallery-item .delete-btn {
            position: absolute; top: 5px; right: 5px;
            background: rgba(255,68,68,0.9); color: #fff;
            border: none; width: 28px; height: 28px;
            border-radius: 50%; cursor: pointer;
            font-size: 20px; line-height: 28px;
            display: none; text-align: center;
        }
        .gallery-item:hover .delete-btn { display: block; }

        .modal {
            display: none; position: fixed;
            top: 0; left: 0; width: 100%; height: 100%;
            background: rgba(0,0,0,0.9);
            justify-content: center; align-items: center;
            z-index: 1000;
        }
        .modal.active { display: flex; }
        .modal img { max-width: 85%; max-height: 90%; }
        .modal-close {
            position: absolute; top: 20px; right: 30px;
            color: #fff; font-size: 40px; cursor: pointer;
        }
        .modal-nav {
            position: absolute; top: 50%; transform: translateY(-50%);
            background: rgba(255,255,255,0.2); color: #fff;
            border: none; width: 50px; height: 80px;
            font-size: 30px; cursor: pointer; border-radius: 5px;
        }
        .modal-nav:hover { background: rgba(255,255,255,0.4); }
        .modal-nav.prev { left: 15px; }
        .modal-nav.next { right: 15px; }
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
            <div class="controls-content">
                <div class="config-section">
                    <div class="config-row">
                        <label>Config:</label>
                        <div class="config-dropdown" id="config-dropdown">
                            <button class="config-dropdown-btn" onclick="toggleConfigDropdown()">
                                <span id="config-selected">-- Select --</span>
                                <span>&#9660;</span>
                            </button>
                            <div class="config-dropdown-list" id="config-list"></div>
                        </div>
                        <button class="config-btn" onclick="saveConfig()">Save</button>
                        <button class="config-btn" onclick="document.getElementById('config-upload').click()">Upload</button>
                        <input type="file" id="config-upload" class="config-upload" accept=".json" onchange="uploadConfig(this)">
                    </div>
                </div>
                <div id="controls-list"></div>
            </div>
        </div>

        <h2>Images (<span id="image-count">{{ image_count }}</span>)</h2>
        <div class="gallery" id="gallery"></div>
    </div>

    <div class="modal" id="modal" onclick="closeModal()">
        <span class="modal-close">&times;</span>
        <button class="modal-nav prev" onclick="event.stopPropagation(); navImage(-1)">&#10094;</button>
        <img id="modal-img" onclick="event.stopPropagation()">
        <button class="modal-nav next" onclick="event.stopPropagation(); navImage(1)">&#10095;</button>
    </div>

    <script>
        let imageCount = {{ image_count }};
        let controlMeta = {};

        function toggleControls() {
            const toggle = document.querySelector('.controls-toggle');
            const content = document.querySelector('.controls-content');
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

        function addImageToGallery(filename, prepend = true) {
            const gallery = document.getElementById('gallery');
            const div = document.createElement('div');
            div.className = 'gallery-item';
            div.innerHTML = `
                <img src="/image/${filename}" loading="lazy" onclick="showModal('${filename}')">
                <button class="delete-btn" onclick="deleteImage('${filename}', this.parentElement)">&#128465;</button>
            `;
            if (prepend) {
                gallery.insertBefore(div, gallery.firstChild);
            } else {
                gallery.appendChild(div);
            }
        }

        async function loadControls() {
            const container = document.getElementById('controls-list');
            if (!container) return;

            try {
                const res = await fetch('/api/controls');
                const data = await res.json();
                container.innerHTML = '';

                for (const ctrl of data.controls) {
                    const hasLimits = ctrl.min !== null && ctrl.max !== null;
                    // If no limits defined, use 10x the current value in both directions (min 64)
                    const range = Math.max(64, ctrl.value !== 0 ? Math.abs(ctrl.value) * 10 : 64);
                    const min = hasLimits ? ctrl.min : -range;
                    const max = hasLimits ? ctrl.max : range;
                    controlMeta[ctrl.control_name] = { min, max, step: ctrl.step, hasLimits };

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
            const input = document.getElementById('input-' + name);
            let newVal = parseFloat(input.value) + (direction * meta.step);
            // Only clamp if limits are defined
            if (meta.hasLimits) {
                newVal = Math.max(meta.min, Math.min(meta.max, newVal));
            }
            newVal = Math.round(newVal / meta.step) * meta.step;
            slider.value = newVal;
            input.value = newVal;
            setControl(name, newVal);
        }

        function applyInput(name) {
            const meta = controlMeta[name];
            const slider = document.getElementById('slider-' + name);
            const input = document.getElementById('input-' + name);
            let val = parseFloat(input.value);
            if (isNaN(val)) val = 0;
            // Only clamp if limits are defined
            if (meta.hasLimits) {
                val = Math.max(meta.min, Math.min(meta.max, val));
            }
            val = Math.round(val / meta.step) * meta.step;
            input.value = val;
            slider.value = val;
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

                data.images.reverse().forEach(img => addImageToGallery(img, false));
            } catch (e) {
                console.error('Failed to load gallery:', e);
            }
        }

        async function deleteImage(filename, element) {
            if (!confirm('Delete this image?')) return;
            try {
                const res = await fetch('/api/image/delete', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ filename })
                });
                const data = await res.json();
                if (data.success) {
                    element.remove();
                    imageCount--;
                    document.getElementById('image-count').innerText = imageCount;
                } else {
                    showStatus(data.message, true);
                }
            } catch (e) {
                showStatus('Error: ' + e, true);
            }
        }

        let imageList = [];
        let currentImageIndex = 0;

        function showModal(filename) {
            imageList = [...document.querySelectorAll('.gallery-item img')].map(img => img.src.split('/').pop());
            currentImageIndex = imageList.indexOf(filename);
            document.getElementById('modal-img').src = '/image/' + filename;
            document.getElementById('modal').classList.add('active');
        }
        function closeModal() {
            document.getElementById('modal').classList.remove('active');
        }
        function navImage(dir) {
            currentImageIndex += dir;
            if (currentImageIndex < 0) currentImageIndex = imageList.length - 1;
            if (currentImageIndex >= imageList.length) currentImageIndex = 0;
            document.getElementById('modal-img').src = '/image/' + imageList[currentImageIndex];
        }

        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') closeModal();
            if (e.key === 'ArrowLeft') navImage(-1);
            if (e.key === 'ArrowRight') navImage(1);
            if (e.key === ' ' || e.key === 'c') { e.preventDefault(); capture(); }
        });

        let configList = [];

        function toggleConfigDropdown() {
            document.getElementById('config-dropdown').classList.toggle('open');
        }

        // Close dropdown when clicking outside
        document.addEventListener('click', (e) => {
            const dropdown = document.getElementById('config-dropdown');
            if (!dropdown.contains(e.target)) {
                dropdown.classList.remove('open');
            }
        });

        function renderConfigList() {
            const list = document.getElementById('config-list');
            list.innerHTML = '';
            configList.forEach(name => {
                const div = document.createElement('div');
                div.className = 'config-item';
                div.innerHTML = `
                    <span class="config-item-name" onclick="applyConfig('${name}')">${name}</span>
                    <button class="config-item-btn" onclick="downloadConfig('${name}')" title="Download">&#8595;</button>
                    <button class="config-item-btn danger" onclick="deleteConfig('${name}')" title="Delete">&#128465;</button>
                `;
                list.appendChild(div);
            });
        }

        async function loadConfigs() {
            try {
                const res = await fetch('/api/configs');
                const data = await res.json();
                configList = data.configs;
                renderConfigList();
            } catch (e) {
                console.error('Failed to load configs:', e);
            }
        }

        async function applyConfig(name) {
            document.getElementById('config-dropdown').classList.remove('open');
            document.getElementById('config-selected').textContent = name;
            try {
                const res = await fetch('/api/config/apply', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ name })
                });
                const data = await res.json();
                if (data.success) {
                    loadControls();
                } else {
                    showStatus(data.message, true);
                }
            } catch (e) {
                showStatus('Error: ' + e, true);
            }
        }

        async function saveConfig() {
            const name = prompt('Enter config name (leave empty for timestamp):');
            if (name === null) return;
            try {
                const res = await fetch('/api/config/save', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ name: name.trim() })
                });
                const data = await res.json();
                if (data.success) {
                    if (!configList.includes(data.filename)) {
                        configList.push(data.filename);
                        configList.sort();
                        renderConfigList();
                    }
                    document.getElementById('config-selected').textContent = data.filename;
                    showStatus('Saved: ' + data.filename, false);
                } else {
                    showStatus(data.message, true);
                }
            } catch (e) {
                showStatus('Error: ' + e, true);
            }
        }

        function downloadConfig(name) {
            event.stopPropagation();
            window.location.href = '/api/config/download/' + encodeURIComponent(name);
        }

        async function uploadConfig(input) {
            const file = input.files[0];
            if (!file) return;
            const formData = new FormData();
            formData.append('file', file);
            try {
                const res = await fetch('/api/config/upload', {
                    method: 'POST',
                    body: formData
                });
                const data = await res.json();
                if (data.success) {
                    if (!configList.includes(data.filename)) {
                        configList.push(data.filename);
                        configList.sort();
                        renderConfigList();
                    }
                    document.getElementById('config-selected').textContent = data.filename;
                    showStatus('Uploaded: ' + data.filename, false);
                } else {
                    showStatus(data.message, true);
                }
            } catch (e) {
                showStatus('Error: ' + e, true);
            }
            input.value = '';
        }

        async function deleteConfig(name) {
            event.stopPropagation();
            if (!confirm('Delete config: ' + name + '?')) return;
            try {
                const res = await fetch('/api/config/delete', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ name })
                });
                const data = await res.json();
                if (data.success) {
                    configList = configList.filter(c => c !== name);
                    renderConfigList();
                    const selected = document.getElementById('config-selected');
                    if (selected.textContent === name) {
                        selected.textContent = '-- Select --';
                    }
                    showStatus('Deleted: ' + name, false);
                } else {
                    showStatus(data.message, true);
                }
            } catch (e) {
                showStatus('Error: ' + e, true);
            }
        }

        loadConfigs();
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
    """Get controls with their current values and definitions (excludes hidden and disabled)."""
    camera = get_camera()
    current = get_controls()
    defs = get_control_defs()

    controls = []
    for ctrl in defs:
        if ctrl.hidden:
            continue
        # Skip disabled controls
        if not camera.is_control_enabled(ctrl.control_name):
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


@app.route('/api/configs')
def api_configs():
    """List available config files."""
    if not CONFIG_FOLDER.exists():
        return jsonify({'configs': []})
    configs = sorted([
        f.name for f in CONFIG_FOLDER.iterdir()
        if f.suffix.lower() == '.json'
    ])
    return jsonify({'configs': configs})


@app.route('/api/config/apply', methods=['POST'])
def api_apply_config():
    """Apply a config file (including enabled/disabled state)."""
    data = request.json
    name = data.get('name')
    if not name:
        return jsonify({'success': False, 'message': 'No config name provided'})

    config_path = CONFIG_FOLDER / name
    if not config_path.exists():
        return jsonify({'success': False, 'message': f'Config not found: {name}'})

    try:
        config = load_config(str(config_path))
        camera = get_camera()
        # Apply full config including enabled states
        camera.apply_config(config)
        return jsonify({'success': True, 'message': f'Applied: {name}'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


@app.route('/api/config/save', methods=['POST'])
def api_save_config():
    """Save current settings to a new config file."""
    try:
        data = request.json or {}
        name = data.get('name', '').strip()

        camera = get_camera()
        if name:
            # Use custom name
            config_path = str(CONFIG_FOLDER / f"{name}.json")
            camera.export_config(config_path)
        else:
            # Auto-generate timestamped name
            config_path = camera.export_config()

        filename = Path(config_path).name
        return jsonify({'success': True, 'filename': filename})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


@app.route('/api/config/download/<filename>')
def api_download_config(filename):
    """Download a config file."""
    return send_from_directory(CONFIG_FOLDER, filename, as_attachment=True)


@app.route('/api/config/upload', methods=['POST'])
def api_upload_config():
    """Upload a config file."""
    if 'file' not in request.files:
        return jsonify({'success': False, 'message': 'No file provided'})

    file = request.files['file']
    if file.filename == '':
        return jsonify({'success': False, 'message': 'No file selected'})

    if not file.filename.endswith('.json'):
        return jsonify({'success': False, 'message': 'File must be .json'})

    try:
        CONFIG_FOLDER.mkdir(parents=True, exist_ok=True)
        filename = Path(file.filename).name  # Sanitize filename
        file.save(CONFIG_FOLDER / filename)
        return jsonify({'success': True, 'filename': filename})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


@app.route('/api/config/delete', methods=['POST'])
def api_delete_config():
    """Delete a config file."""
    data = request.json
    name = data.get('name')
    if not name:
        return jsonify({'success': False, 'message': 'No config name provided'})

    config_path = CONFIG_FOLDER / name
    if not config_path.exists():
        return jsonify({'success': False, 'message': f'Config not found: {name}'})

    try:
        config_path.unlink()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


@app.route('/api/image/delete', methods=['POST'])
def api_delete_image():
    """Delete an image file."""
    data = request.json
    filename = data.get('filename')
    if not filename:
        return jsonify({'success': False, 'message': 'No filename provided'})

    image_path = OUTPUT_FOLDER / filename
    if not image_path.exists():
        return jsonify({'success': False, 'message': f'Image not found: {filename}'})

    try:
        image_path.unlink()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


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
