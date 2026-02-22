# InkFrame Remaining Bug Fixes

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix the 8 remaining issues identified in the code review but not addressed in the first fix pass.

**Architecture:** Changes are isolated to 5 files. No new dependencies introduced. Tasks are ordered to avoid cross-file conflicts — each touches a distinct file. Verification is by code inspection and targeted smoke tests (no test framework in project).

**Tech Stack:** Python 3, Flask, sqlite3, lgpio, threading, subprocess/nmcli

---

## Task 1: app.py — GPIO startup timeout

**Files:**
- Modify: `app.py:59-74` (setup_buttons)

**Problem:** `lgpio.gpiochip_open(0)` on line 65 has no timeout. If the GPIO chip is unavailable or slow to respond, `setup_buttons()` blocks the main thread forever and the app never starts.

**Fix:** Wrap the open call in a helper that runs it in a daemon thread with `join(timeout=5.0)`. If it doesn't return in time, raise a `RuntimeError` that the existing `except Exception` in `setup_buttons()` catches and logs.

**Step 1: Add helper function above setup_buttons() — insert after line 56 (the `# --- GPIO Button Handlers ---` comment)**

```python
def _open_gpio_with_timeout(timeout=5.0):
    """Open GPIO chip in a thread to enforce a startup timeout."""
    result = [None]
    error = [None]

    def _open():
        try:
            result[0] = lgpio.gpiochip_open(0)
        except Exception as e:
            error[0] = e

    t = threading.Thread(target=_open, daemon=True)
    t.start()
    t.join(timeout=timeout)

    if t.is_alive():
        raise RuntimeError(f"lgpio.gpiochip_open(0) timed out after {timeout}s")
    if error[0] is not None:
        raise error[0]
    return result[0]
```

**Step 2: Replace the gpiochip_open call in setup_buttons() (line 65)**

Current:
```python
        _gpio_handle = lgpio.gpiochip_open(0)
```

Replace with:
```python
        _gpio_handle = _open_gpio_with_timeout(timeout=5.0)
```

**Step 3: Verify syntax**

```bash
python3 -m py_compile /home/pi/photos/app.py && echo "OK"
```

**Step 4: Verify helper is present and unreachable code path is safe**

```bash
grep -n "_open_gpio_with_timeout\|gpiochip_open" /home/pi/photos/app.py
```

Expected: `_open_gpio_with_timeout` defined once, called once in `setup_buttons`. `gpiochip_open` only appears inside the helper.

**Step 5: Commit**

```bash
cd /home/pi/photos
git add app.py
git commit -m "fix: add 5s timeout to lgpio.gpiochip_open to prevent startup hang"
```

---

## Task 2: scheduler.py — error handling in state persistence

**Files:**
- Modify: `scheduler.py:32-58`

**Problem 1 (line 38):** `_load_persisted_state()` calls `models.load_settings()` with no try/except. If the settings file is corrupt or unreadable, the uncaught exception propagates up and crashes whichever call first triggers `_load_persisted_state()` (via `_initialized` guard).

**Problem 2 (line 55):** `_persist_state()` calls `models.update_settings()` with no error handling. If the disk is full or the settings file has bad permissions, the exception propagates into `show_next_photo()` and `show_specific_photo()`, crashing the slideshow.

**Step 1: Wrap _load_persisted_state() body in try/except**

Current (lines 32-50):
```python
def _load_persisted_state():
    """Load saved current photo path and shuffle bag from settings on startup"""
    global _current_path, _shuffle_bag, _initialized
    if _initialized:
        return
    _initialized = True
    settings = models.load_settings()
    slideshow = settings.get("slideshow", {})
    saved_path = slideshow.get("current_photo_path")
    saved_bag = slideshow.get("shuffle_bag", [])
    if saved_path:
        if Path(saved_path).exists():
            _current_path = saved_path
            print(f"Restored current photo: {saved_path}")
        else:
            print(f"Restored photo no longer exists, resetting: {saved_path}")
    if saved_bag:
        _shuffle_bag = saved_bag
        print(f"Restored shuffle bag: {len(saved_bag)} photos remaining")
```

Replace with:
```python
def _load_persisted_state():
    """Load saved current photo path and shuffle bag from settings on startup"""
    global _current_path, _shuffle_bag, _initialized
    if _initialized:
        return
    _initialized = True
    try:
        settings = models.load_settings()
        slideshow = settings.get("slideshow", {})
        saved_path = slideshow.get("current_photo_path")
        saved_bag = slideshow.get("shuffle_bag", [])
        if saved_path:
            if Path(saved_path).exists():
                _current_path = saved_path
                print(f"Restored current photo: {saved_path}")
            else:
                print(f"Restored photo no longer exists, resetting: {saved_path}")
        if saved_bag:
            _shuffle_bag = saved_bag
            print(f"Restored shuffle bag: {len(saved_bag)} photos remaining")
    except Exception as e:
        print(f"Failed to load persisted slideshow state, starting fresh: {e}")
```

**Step 2: Wrap _persist_state() body in try/except**

Current (lines 53-58):
```python
def _persist_state():
    """Save current photo path and shuffle bag to settings for restart persistence"""
    models.update_settings({"slideshow": {
        "current_photo_path": _current_path,
        "shuffle_bag": _shuffle_bag,
    }})
```

Replace with:
```python
def _persist_state():
    """Save current photo path and shuffle bag to settings for restart persistence"""
    try:
        models.update_settings({"slideshow": {
            "current_photo_path": _current_path,
            "shuffle_bag": _shuffle_bag,
        }})
    except Exception as e:
        print(f"Failed to persist slideshow state: {e}")
```

**Step 3: Verify syntax**

```bash
python3 -m py_compile /home/pi/photos/scheduler.py && echo "OK"
```

**Step 4: Smoke test**

```bash
cd /home/pi/photos && python3 -c "
import scheduler
# Should not raise even if called before DB exists
try:
    scheduler._load_persisted_state()
    print('_load_persisted_state: OK')
except Exception as e:
    print('FAIL:', e)
"
```

Expected: `_load_persisted_state: OK`

**Step 5: Commit**

```bash
cd /home/pi/photos
git add scheduler.py
git commit -m "fix: add error handling to _load_persisted_state and _persist_state"
```

---

## Task 3: models.py — per-thread SQLite connection reuse

**Files:**
- Modify: `models.py:1-10` (imports)
- Modify: `models.py:35-39` (get_db)
- Modify: `models.py:42-68` (init_db — remove close)
- Modify: `models.py:116-132` (add_photo — remove close)
- Modify: `models.py:135-142` (get_photo — remove close)
- Modify: `models.py:145-155` (get_all_photos — remove close)
- Modify: `models.py:158-165` (get_photo_count — remove close)
- Modify: `models.py:168-178` (get_display_photos — remove close)
- Modify: `models.py:181-192` (delete_photo — remove close)
- Modify: `models.py:195-210` (delete_photos_bulk — remove close)
- Modify: `models.py:213-222` (toggle_favorite — remove close)
- Add: new `close_db()` function
- Modify: `app.py` — register teardown

**Problem:** Every DB function creates a new `sqlite3.connect()` and closes it immediately. With multiple concurrent Flask request threads and background APScheduler jobs, this creates unnecessary connection churn.

**Fix:** Use `threading.local()` to cache one open connection per thread. All functions share the thread's connection. A `close_db()` function is added and called from Flask's `@app.teardown_appcontext` to clean up after each request.

**Step 1: Add `import threading` to models.py imports**

Current top of models.py:
```python
import sqlite3
import json
from datetime import datetime
from pathlib import Path
```

Replace with:
```python
import sqlite3
import json
import threading
from datetime import datetime
from pathlib import Path
```

**Step 2: Replace get_db() with threading.local version, add close_db()**

Current (lines 35-39):
```python
def get_db():
    """Get database connection with row factory"""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn
```

Replace with:
```python
_db_local = threading.local()


def get_db():
    """Get per-thread database connection with row factory. Reuses connection within a thread."""
    conn = getattr(_db_local, 'conn', None)
    if conn is None:
        conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        _db_local.conn = conn
    return conn


def close_db():
    """Close the per-thread database connection. Call at end of request/job."""
    conn = getattr(_db_local, 'conn', None)
    if conn is not None:
        conn.close()
        _db_local.conn = None
```

**Step 3: Remove all `conn.close()` calls from every DB function**

In each of the following functions, delete the `conn.close()` line (connections are now long-lived per thread):

- `init_db()` — remove `conn.close()` at end
- `add_photo()` — remove `conn.close()` at end
- `get_photo()` — remove `conn.close()` at end
- `get_all_photos()` — remove `conn.close()` at end
- `get_photo_count()` — remove `conn.close()` at end
- `get_display_photos()` — remove `conn.close()` at end
- `delete_photo()` — remove `conn.close()` at end
- `delete_photos_bulk()` — remove `conn.close()` at end
- `toggle_favorite()` — remove `conn.close()` at end

**Important:** Keep all `conn.commit()` calls — writes must still be committed explicitly.

**Step 4: Register close_db in app.py teardown**

In `app.py`, after the `app = Flask(...)` line (around line 36), add:

```python
@app.teardown_appcontext
def teardown_db(exception):
    models.close_db()
```

**Step 5: Verify syntax**

```bash
python3 -m py_compile /home/pi/photos/models.py /home/pi/photos/app.py && echo "OK"
```

**Step 6: Test connection reuse and edge cases**

```bash
cd /home/pi/photos && python3 -c "
import models
models.init_db()

# Test basic operations still work
count = models.get_photo_count()
print('Photo count:', count)

photos = models.get_all_photos()
print('All photos:', len(photos))

# Test that connection is reused within same thread
c1 = models.get_db()
c2 = models.get_db()
assert c1 is c2, 'Connection not reused!'
print('Connection reuse: OK')

# Test close and reopen
models.close_db()
c3 = models.get_db()
assert c3 is not c1, 'Expected new connection after close'
print('Reopen after close: OK')

models.close_db()
print('All tests passed')
"
```

**Step 7: Commit**

```bash
cd /home/pi/photos
git add models.py app.py
git commit -m "fix: reuse SQLite connection per thread via threading.local, close on teardown"
```

---

## Task 4: image_processor.py — MIME type captured before exif_transpose

**Files:**
- Modify: `image_processor.py:234-241`

**Problem:** On line 241, `Image.MIME.get(img.format, 'image/jpeg')` is called after `ImageOps.exif_transpose(img)` on line 236. `exif_transpose` returns a new `Image` object that does not preserve the `.format` attribute — it becomes `None`. So `img.format` is always `None` at line 241, causing the fallback `'image/jpeg'` to be used for every image, including PNGs.

**Fix:** Capture `img.format` from the freshly opened image (where format is set by Pillow's decoder) before calling `exif_transpose`.

**Step 1: Reorder metadata capture in process_upload()**

Current (lines 234-245):
```python
    display_path = None
    thumb_path = None
    try:
        # Apply EXIF orientation transpose
        img = ImageOps.exif_transpose(img)

        # Get metadata before conversion
        date_taken = get_exif_date(img)
        orig_width, orig_height = img.size
        mime_type = Image.MIME.get(img.format, 'image/jpeg')

        # Convert to RGB for processing
        if img.mode != 'RGB':
            img = img.convert('RGB')
```

Replace with:
```python
    display_path = None
    thumb_path = None
    try:
        # Capture format before exif_transpose (which returns a new Image without .format)
        img_format = img.format
        mime_type = Image.MIME.get(img_format, 'image/jpeg')

        # Apply EXIF orientation transpose
        img = ImageOps.exif_transpose(img)

        # Get remaining metadata
        date_taken = get_exif_date(img)
        orig_width, orig_height = img.size

        # Convert to RGB for processing
        if img.mode != 'RGB':
            img = img.convert('RGB')
```

**Step 2: Verify syntax**

```bash
python3 -m py_compile /home/pi/photos/image_processor.py && echo "OK"
```

**Step 3: Verify fix with a quick test**

```bash
cd /home/pi/photos && python3 -c "
from PIL import Image, ImageOps
import io

# Create a small PNG in memory
img = Image.new('RGB', (10, 10), color=(255, 0, 0))
buf = io.BytesIO()
img.save(buf, format='PNG')
buf.seek(0)

# Simulate what process_upload does
loaded = Image.open(buf)
print('Before exif_transpose, format:', loaded.format)  # Should be 'PNG'
img_format = loaded.format
transposed = ImageOps.exif_transpose(loaded)
print('After exif_transpose, format:', transposed.format)  # Will be None
print('Captured format:', img_format)  # Should still be 'PNG'
from PIL import Image as PILImage
mime = PILImage.MIME.get(img_format, 'image/jpeg')
print('MIME type:', mime)  # Should be 'image/png', not 'image/jpeg'
"
```

Expected output:
```
Before exif_transpose, format: PNG
After exif_transpose, format: None
Captured format: PNG
MIME type: image/png
```

**Step 4: Commit**

```bash
cd /home/pi/photos
git add image_processor.py
git commit -m "fix: capture img.format before exif_transpose to get correct MIME type"
```

---

## Task 5: wifi_manager.py — interface detection, run_cmd logging, ensure_wifi logging

**Files:**
- Modify: `wifi_manager.py:13-26` (run_cmd — add failure logging)
- Modify: `wifi_manager.py:101-122` (start_ap_mode — detect interface dynamically)
- Modify: `wifi_manager.py:248-271` (ensure_wifi_connected — improve logging)

**Three separate problems, all in wifi_manager.py, fixed together.**

---

### Part A: run_cmd() — log non-zero exit codes when check=False

**Problem (lines 13-26):** When called with `check=False`, a failed command (e.g., nmcli can't find a network) returns `None` silently. Callers receive `None` and assume failure but have no diagnostic information.

**Current:**
```python
def run_cmd(cmd, check=True):
    """Run a command (as arg list) and return output"""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=check
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        print(f"Command failed: {cmd}")
        print(f"Error: {e.stderr}")
        return None
```

**Replace with:**
```python
def run_cmd(cmd, check=True):
    """Run a command (as arg list) and return output"""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=check
        )
        if result.returncode != 0:
            cmd_str = ' '.join(str(c) for c in cmd)
            print(f"Command exited {result.returncode}: {cmd_str}")
            if result.stderr.strip():
                print(f"  stderr: {result.stderr.strip()}")
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        print(f"Command failed: {' '.join(str(c) for c in cmd)}")
        print(f"Error: {e.stderr}")
        return None
```

---

### Part B: start_ap_mode() — detect WiFi interface dynamically

**Problem (line 110):** `"ifname", "wlan0"` is hardcoded. On Raspberry Pi OS Bookworm/Trixie with predictable network interface names, the interface may be `wlp1s0`, `wlan1`, etc.

**Add a helper function before start_ap_mode():**

```python
def get_wifi_interface():
    """Detect the first available WiFi interface name (falls back to wlan0)."""
    output = run_cmd(["nmcli", "-t", "-f", "DEVICE,TYPE", "dev"], check=False)
    if output:
        for line in output.split('\n'):
            parts = line.rsplit(':', maxsplit=1)
            if len(parts) == 2 and parts[1].strip() == 'wifi':
                iface = parts[0].strip()
                if iface:
                    return iface
    return "wlan0"
```

**Update start_ap_mode() to use it (line 110):**

Current:
```python
    result = run_cmd(["nmcli", "dev", "wifi", "hotspot", "ifname", "wlan0",
                      "ssid", AP_SSID, "password", AP_PASSWORD], check=False)
```

Replace with:
```python
    iface = get_wifi_interface()
    result = run_cmd(["nmcli", "dev", "wifi", "hotspot", "ifname", iface,
                      "ssid", AP_SSID, "password", AP_PASSWORD], check=False)
```

---

### Part C: ensure_wifi_connected() — improve diagnostic logging

**Problem (lines 248-271):** The function silently waits and then returns `False` with a terse message. When debugging connectivity failures it's hard to know what happened.

**Read the full current function first:**

```bash
sed -n '248,271p' /home/pi/photos/wifi_manager.py
```

**Replace the function with:**
```python
def ensure_wifi_connected(timeout=15):
    """
    Wait for NetworkManager to establish a saved WiFi connection.
    Returns True if connected, False if should start AP mode.
    """
    if is_wifi_connected():
        return True

    saved = get_saved_networks()
    if not saved:
        print("No saved WiFi networks — will start AP mode")
        return False

    print(f"Waiting up to {timeout}s for WiFi ({len(saved)} saved network(s): {', '.join(saved[:3])})...")
    start = time.time()
    while time.time() - start < timeout:
        if is_wifi_connected():
            ssid = get_current_ssid()
            print(f"WiFi connected: {ssid}")
            return True
        time.sleep(1)

    print(f"WiFi not connected after {timeout}s — will start AP mode")
    return False
```

---

**Step 1: Make all three changes to wifi_manager.py**

**Step 2: Verify syntax**

```bash
python3 -m py_compile /home/pi/photos/wifi_manager.py && echo "OK"
```

**Step 3: Verify interface detection logic with mock data**

```bash
python3 -c "
# Simulate nmcli output parsing
lines = ['eth0:ethernet', 'wlan0:wifi', 'lo:loopback']
for line in lines:
    parts = line.rsplit(':', maxsplit=1)
    if len(parts) == 2 and parts[1].strip() == 'wifi':
        print('Detected interface:', parts[0].strip())
"
```

Expected: `Detected interface: wlan0`

**Step 4: Verify get_wifi_interface function exists**

```bash
python3 -c "
import sys; sys.path.insert(0, '/home/pi/photos')
import wifi_manager
print(type(wifi_manager.get_wifi_interface))
"
```

**Step 5: Commit**

```bash
cd /home/pi/photos
git add wifi_manager.py
git commit -m "fix: log nmcli failures, detect WiFi interface dynamically, improve ensure_wifi logging"
```

---

## Task 6: Final verification

**Step 1: Syntax check all files**

```bash
python3 -m py_compile /home/pi/photos/app.py /home/pi/photos/scheduler.py /home/pi/photos/models.py /home/pi/photos/image_processor.py /home/pi/photos/wifi_manager.py && echo "ALL OK"
```

**Step 2: Full smoke test**

```bash
cd /home/pi/photos && python3 -c "
import sys
sys.path.insert(0, '.')
import models, scheduler, image_processor, display, wifi_manager
models.init_db()
image_processor.ensure_dirs()

# Test DB connection reuse
c1 = models.get_db()
c2 = models.get_db()
assert c1 is c2, 'DB connection not reused'
models.close_db()
print('DB reuse: OK')

# Test bulk delete still works
r = models.delete_photos_bulk([])
assert r == [], f'Expected [] got {r}'
print('Bulk delete: OK')

# Test scheduler load with error protection
scheduler._initialized = False
scheduler._load_persisted_state()
print('Scheduler load: OK')

print('All smoke tests passed')
"
```

**Step 3: Show git log**

```bash
git -C /home/pi/photos log --oneline -8
```

**Step 4: Confirm no remaining unfixed issues**

All issues from the gap analysis should now be resolved:
- `app.py:65` GPIO timeout → Task 1
- `scheduler.py:38` _load_persisted_state exception handling → Task 2
- `scheduler.py:53` _persist_state error handling → Task 2
- `models.py:35` connection per query → Task 3
- `image_processor.py:241` MIME type → Task 4
- `wifi_manager.py:110` hardcoded wlan0 → Task 5
- `wifi_manager.py:13` silent failures → Task 5
- `wifi_manager.py:248` ensure_wifi logging → Task 5
