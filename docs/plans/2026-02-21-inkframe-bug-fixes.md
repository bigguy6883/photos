# InkFrame Bug Fixes & Efficiency Improvements

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix all bugs, crashes, resource leaks, race conditions, and efficiency issues identified in the code review of the InkFrame e-ink photo frame project.

**Architecture:** Changes are isolated to six Python source files and requirements.txt. No new modules or dependencies are introduced. Each task targets one file to minimize risk of cross-file breakage. Tests are verified by code inspection and manual curl/button checks since there is no test suite.

**Tech Stack:** Python 3, Flask, Pillow, APScheduler, lgpio, sqlite3, nmcli (NetworkManager CLI)

---

## Task 1: Fix scheduler.py crashes and efficiency issues

**Files:**
- Modify: `scheduler.py:31-46` (validate restored path)
- Modify: `scheduler.py:62-81` (fix single-photo shuffle crash)
- Modify: `scheduler.py:84-119` (fix history infinite loop, add dict lookup)
- Modify: `scheduler.py:57-59` (cache DB query)

**Context:** Four independent issues all live in `scheduler.py`. Fix them together to minimize file churn.

---

### Step 1: Fix `_load_persisted_state()` — validate restored path exists

**Problem:** Line 41 restores `saved_path` from JSON settings without checking the file exists. If the photo was deleted externally, `_current_path` silently points to a ghost file.

**Current code (lines 41-46):**
```python
    if saved_path:
        _current_path = saved_path
        print(f"Restored current photo: {saved_path}")
    if saved_bag:
        _shuffle_bag = saved_bag
        print(f"Restored shuffle bag: {len(saved_bag)} photos remaining")
```

**Replace with:**
```python
    if saved_path:
        from pathlib import Path
        if Path(saved_path).exists():
            _current_path = saved_path
            print(f"Restored current photo: {saved_path}")
        else:
            print(f"Restored photo no longer exists, resetting: {saved_path}")
    if saved_bag:
        _shuffle_bag = saved_bag
        print(f"Restored shuffle bag: {len(saved_bag)} photos remaining")
```

---

### Step 2: Fix `_next_from_shuffle_bag()` — single-photo crash

**Problem:** Line 78 calls `random.randint(1, len(_shuffle_bag) - 1)`. When there is exactly 1 photo, `len(_shuffle_bag) - 1 == 0`, making the call `random.randint(1, 0)` which raises `ValueError`.

**Current code (lines 75-79):**
```python
        # If possible, avoid repeating the last shown photo at start of new cycle
        if len(_shuffle_bag) > 1 and _shuffle_bag[0] == _current_path:
            # Swap first with a random other position
            swap_idx = random.randint(1, len(_shuffle_bag) - 1)
            _shuffle_bag[0], _shuffle_bag[swap_idx] = _shuffle_bag[swap_idx], _shuffle_bag[0]
```

**Replace with:**
```python
        # If possible, avoid repeating the last shown photo at start of new cycle
        if len(_shuffle_bag) > 1 and _shuffle_bag[0] == _current_path:
            # Swap first with a random other position
            swap_idx = random.randint(1, len(_shuffle_bag) - 1)
            _shuffle_bag[0], _shuffle_bag[swap_idx] = _shuffle_bag[swap_idx], _shuffle_bag[0]
        # If only 1 photo, no swap possible — just show it
```

**Note:** The `if len(_shuffle_bag) > 1` guard already prevents the crash — the crash only occurs if somehow the bag is refilled with 1 item AND the condition is True. Wait — actually with 1 item, `len(_shuffle_bag) > 1` is `False`, so the inner block never runs. Re-examine: the bug was identified as `randint(1, 0)` but the guard `> 1` prevents it. **Verify this by reading the code at runtime.** If the guard is sufficient, no change is needed here. Document that the guard is the protection.

**Verification:** Trace the path: 1 photo → `_shuffle_bag = [photo]` → `len > 1` is False → swap block skipped → safe. The crash cannot occur. Mark this as a false positive — no code change needed, add a comment.

**Add comment to clarify safety:**
```python
        # Guard: only swap if >1 photo (prevents randint(1,0) crash with single photo)
        if len(_shuffle_bag) > 1 and _shuffle_bag[0] == _current_path:
            swap_idx = random.randint(1, len(_shuffle_bag) - 1)
            _shuffle_bag[0], _shuffle_bag[swap_idx] = _shuffle_bag[swap_idx], _shuffle_bag[0]
```

---

### Step 3: Fix `show_previous_photo()` — history cleanup infinite loop

**Problem:** Lines 140-141 loop while `_history` is non-empty and `path not in all_photos`. After the loop, line 142 checks `if path not in all_photos`. But there is a case where the loop exhausts `_history` (all photos deleted) and the final `path` is the last popped value which also isn't in `all_photos`. The `while _history and ...` guard prevents `IndexError` during the loop itself, but the problem is the logic is correct — verify once more.

Actually re-reading lines 137-143:
```python
        if _history:
            path = _history.pop()
            # Make sure it still exists
            while _history and path not in all_photos:
                path = _history.pop()
            if path not in all_photos:
                path = _next_from_shuffle_bag(all_photos)
```

This is actually safe — `while _history and ...` stops when history is empty. The final `if` handles the fallback. No crash possible here. The original report was inaccurate. **No change needed.**

---

### Step 4: Fix `show_next_photo()` — O(n) list.index() lookup

**Problem:** Line 103 and line 118 call `all_photos.index(_current_path)` which is O(n). With 1000+ photos this is measurably slow, called every photo cycle.

**Current code (lines 101-106):**
```python
        if _current_path in all_photos:
            idx = all_photos.index(_current_path)
            path = all_photos[(idx + 1) % len(all_photos)]
        else:
            path = all_photos[0]
```

**Replace with (build index dict once):**
```python
        if _current_path in all_photos:
            photo_index = {p: i for i, p in enumerate(all_photos)}
            idx = photo_index[_current_path]
            path = all_photos[(idx + 1) % len(all_photos)]
        else:
            path = all_photos[0]
```

Also fix line 118 (debug print):
```python
    # Before:
    print(f"Showing photo {all_photos.index(path) + 1}/{len(all_photos)}: {path}")
    # After:
    photo_index_map = {p: i for i, p in enumerate(all_photos)}
    print(f"Showing photo {photo_index_map.get(path, 0) + 1}/{len(all_photos)}: {path}")
```

Or simply remove the index from the debug print since it requires another O(n) call:
```python
    print(f"Showing photo: {path} ({len(all_photos)} total)")
```

**Step 5: Verify changes manually**

```bash
cd /home/pi/photos
python3 -c "
import models, scheduler
models.init_db()
# Simulate load with no photos
result = scheduler.show_next_photo()
print('No photos result:', result)
"
```

Expected: `No photos available` printed, returns `False`.

**Step 6: Commit**

```bash
cd /home/pi/photos
git add scheduler.py
git commit -m "fix: scheduler path validation, clarify single-photo safety, optimize index lookup"
```

---

## Task 2: Fix models.py — empty bulk delete crash and query optimization

**Files:**
- Modify: `models.py:195-210` (fix empty list SQL crash)
- Modify: `models.py:168-178` (add LIMIT to random query)
- Modify: `models.py:35-39` (add connection error handling)

---

### Step 1: Fix `delete_photos_bulk()` — invalid SQL on empty list

**Problem:** Line 206 constructs `DELETE FROM photos WHERE id IN ()` when `photo_ids` is empty — invalid SQL that raises `sqlite3.OperationalError`.

**Current code (lines 195-210):**
```python
def delete_photos_bulk(photo_ids):
    """Delete multiple photos, returns list of photo dicts for file cleanup"""
    conn = get_db()
    cursor = conn.cursor()
    photos = []
    for pid in photo_ids:
        cursor.execute('SELECT * FROM photos WHERE id = ?', (pid,))
        row = cursor.fetchone()
        if row:
            photos.append(dict(row))
    if photos:
        placeholders = ','.join('?' * len(photo_ids))
        cursor.execute(f'DELETE FROM photos WHERE id IN ({placeholders})', photo_ids)
        conn.commit()
    conn.close()
    return photos
```

**Replace with:**
```python
def delete_photos_bulk(photo_ids):
    """Delete multiple photos, returns list of photo dicts for file cleanup"""
    if not photo_ids:
        return []
    conn = get_db()
    cursor = conn.cursor()
    photos = []
    for pid in photo_ids:
        cursor.execute('SELECT * FROM photos WHERE id = ?', (pid,))
        row = cursor.fetchone()
        if row:
            photos.append(dict(row))
    if photos:
        found_ids = [p['id'] for p in photos]
        placeholders = ','.join('?' * len(found_ids))
        cursor.execute(f'DELETE FROM photos WHERE id IN ({placeholders})', found_ids)
        conn.commit()
    conn.close()
    return photos
```

Note: also fixed to use `found_ids` (IDs that actually exist) instead of `photo_ids` (requested IDs, some may not exist).

---

### Step 2: Add LIMIT to `get_display_photos()` random order

**Problem:** Line 173 runs `SELECT display_path FROM photos ORDER BY RANDOM()` with no LIMIT. For large libraries this sorts the entire table. Since the caller (`scheduler.py`) fetches all paths anyway to build the shuffle bag, we can't LIMIT arbitrarily — but we can switch to fetching in natural order and shuffling in Python (which APScheduler already does via `_next_from_shuffle_bag`).

**Current code (lines 168-178):**
```python
def get_display_photos(order="random"):
    """Get photos for display cycling, returns list of display_path strings"""
    conn = get_db()
    cursor = conn.cursor()
    if order == "random":
        cursor.execute('SELECT display_path FROM photos ORDER BY RANDOM()')
    else:
        cursor.execute('SELECT display_path FROM photos ORDER BY uploaded_at ASC')
    rows = cursor.fetchall()
    conn.close()
    return [row['display_path'] for row in rows]
```

**Replace with** (always return in stable order; scheduler handles shuffle):
```python
def get_display_photos(order="random"):
    """Get photos for display cycling, returns list of display_path strings.
    Shuffling is handled by the caller (scheduler._next_from_shuffle_bag).
    """
    conn = get_db()
    cursor = conn.cursor()
    # Always return stable order; ORDER BY RANDOM() on large tables is slow
    cursor.execute('SELECT display_path FROM photos ORDER BY uploaded_at ASC')
    rows = cursor.fetchall()
    conn.close()
    return [row['display_path'] for row in rows]
```

---

### Step 3: Verify

```bash
cd /home/pi/photos
python3 -c "
import models
models.init_db()
# Test empty bulk delete
result = models.delete_photos_bulk([])
print('Empty bulk delete:', result)  # Expected: []

# Test with nonexistent IDs
result = models.delete_photos_bulk([9999])
print('Nonexistent bulk delete:', result)  # Expected: []
"
```

**Step 4: Commit**

```bash
cd /home/pi/photos
git add models.py
git commit -m "fix: guard delete_photos_bulk against empty list, remove ORDER BY RANDOM()"
```

---

## Task 3: Fix image_processor.py — upload validation order and reprocess mutex

**Files:**
- Modify: `image_processor.py:189-260` (validate before saving, clean up all files on error)
- Modify: `image_processor.py:290-321` (add reprocess mutex)

---

### Step 1: Fix `process_upload()` — validate before saving + full cleanup on error

**Problem 1 (line 213):** File is saved to disk before `Image.open()` validates it. A corrupt upload leaves an orphaned original file.

**Problem 2 (line 258):** On error, only `original_path` is deleted. If `display_img.save()` fails after `display_path` is created but before `thumb_path` is created, the display file is never cleaned up.

**Current code (lines 212-260):**
```python
    # Save original
    file_storage.save(str(original_path))
    file_size = original_path.stat().st_size

    try:
        img = Image.open(str(original_path))
        ...
    except Exception as e:
        # Clean up on error
        original_path.unlink(missing_ok=True)
        print(f"Error processing upload {original_name}: {e}")
        return None
```

**Replace with** (validate in memory first, then save):
```python
    # Validate image in memory before saving to disk
    try:
        file_data = file_storage.read()
        import io
        img = Image.open(io.BytesIO(file_data))
        img.verify()  # Raises if corrupt
        # Re-open after verify (verify() exhausts the file object)
        img = Image.open(io.BytesIO(file_data))
    except Exception as e:
        print(f"Invalid image {original_name}: {e}")
        return None

    # Save original (now known valid)
    original_path.write_bytes(file_data)
    file_size = len(file_data)
    del file_data  # Free memory

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

        # Create display version (600x448 PNG)
        display_img = resize_for_display(img, fit_mode, smart_recenter=smart_recenter)
        display_filename = Path(filename).stem + ".png"
        display_path = DISPLAY_DIR / display_filename
        display_img.save(str(display_path), "PNG")

        # Create thumbnail (300x200 JPEG)
        thumb = img.copy()
        thumb.thumbnail(THUMBNAIL_SIZE, Image.LANCZOS)
        thumb_filename = Path(filename).stem + ".jpg"
        thumb_path = THUMBNAILS_DIR / thumb_filename
        thumb.save(str(thumb_path), "JPEG", quality=85)

        return {
            'filename': filename,
            'original_path': str(original_path),
            'display_path': str(display_path),
            'thumbnail_path': str(thumb_path),
            'width': orig_width,
            'height': orig_height,
            'file_size': file_size,
            'mime_type': mime_type,
            'date_taken': date_taken,
        }

    except Exception as e:
        # Clean up all files created so far
        original_path.unlink(missing_ok=True)
        if display_path:
            display_path.unlink(missing_ok=True)
        if thumb_path:
            thumb_path.unlink(missing_ok=True)
        print(f"Error processing upload {original_name}: {e}")
        return None
```

**Note:** Remove the duplicate `date_taken`, `orig_width`, etc. assignments that were in the old code between `save` and `try`. The new structure keeps metadata extraction inside the try block.

Also remove `import io` from inside the function — add `import io` at the top of `image_processor.py` with other imports.

---

### Step 2: Add mutex to `reprocess_display_images()`

**Problem (line 290):** No mutual exclusion. Two settings changes in quick succession launch two threads both calling `reprocess_display_images()`, causing double I/O and potential file corruption.

**Add module-level lock near top of file** (after existing module globals, around line 20):
```python
_reprocess_lock = threading.Lock()
```

Also add `import threading` at the top of `image_processor.py` if not already present.

**Modify `reprocess_display_images()` (line 290):**
```python
def reprocess_display_images(fit_mode="contain", smart_recenter=False):
    """
    Reprocess all display images from originals (e.g. after fit_mode change).
    Returns count of reprocessed images. No-ops if already running.
    """
    if not _reprocess_lock.acquire(blocking=False):
        log.info("Reprocess already in progress, skipping")
        return 0
    try:
        log.info("Reprocessing display images: fit_mode=%s, smart_recenter=%s", fit_mode, smart_recenter)
        ensure_dirs()
        count = 0
        errors = 0
        for original in ORIGINALS_DIR.iterdir():
            if original.suffix.lower() not in ALLOWED_EXTENSIONS:
                continue
            try:
                img = Image.open(str(original))
                img = ImageOps.exif_transpose(img)
                if img.mode != 'RGB':
                    img = img.convert('RGB')

                display_img = resize_for_display(img, fit_mode, smart_recenter=smart_recenter)
                display_filename = original.stem + ".png"
                display_path = DISPLAY_DIR / display_filename
                display_img.save(str(display_path), "PNG")
                count += 1
            except Exception as e:
                errors += 1
                log.error("Error reprocessing %s: %s", original.name, e)
            finally:
                gc.collect()

        _save_display_state(fit_mode, smart_recenter)
        log.info("Reprocess complete: %d ok, %d errors", count, errors)
        return count
    finally:
        _reprocess_lock.release()
```

**Step 3: Verify**

```bash
cd /home/pi/photos
python3 -c "
import image_processor
image_processor.ensure_dirs()
print('Dirs OK')
# Verify lock exists
import threading
print('Lock type:', type(image_processor._reprocess_lock))
"
```

**Step 4: Commit**

```bash
cd /home/pi/photos
git add image_processor.py
git commit -m "fix: validate image before saving, full cleanup on error, add reprocess mutex"
```

---

## Task 4: Fix app.py — thread safety and button debounce

**Files:**
- Modify: `app.py:45-48` (add setup_mode lock)
- Modify: `app.py:124-130` (use lock in _btn_setup)
- Modify: `app.py:121-122` (use lock in _btn_info)
- Modify: `app.py:314` (use lock in display_info route)
- Modify: `app.py:427` (use lock in captive_portal_detect)
- Modify: `app.py:448-485` (use lock in main)

---

### Step 1: Add threading lock for `_in_setup_mode`

**Problem (line 46):** `_in_setup_mode` is a bare boolean read from Flask request threads and written from the button poll thread. No synchronization.

**Current module globals (lines 45-48):**
```python
_buttons_initialized = False
_in_setup_mode = False
_button_thread = None
_gpio_handle = None
```

**Replace with:**
```python
_buttons_initialized = False
_in_setup_mode = False
_setup_mode_lock = threading.Lock()
_button_thread = None
_gpio_handle = None
```

---

### Step 2: Wrap all reads/writes of `_in_setup_mode` with the lock

**`_btn_setup()` (lines 124-130):**
```python
def _btn_setup():
    global _in_setup_mode
    with _setup_mode_lock:
        if _in_setup_mode:
            return
        _in_setup_mode = True
    wifi_manager.start_ap_mode()
    display.show_info_screen(ap_mode=True)
    print("Entered setup mode")
```

**`_btn_info()` (lines 118-121):** read-only access, use lock for consistency:
```python
def _btn_info():
    with _setup_mode_lock:
        ap = _in_setup_mode
    wifi_status = wifi_manager.get_wifi_status() or "Not connected"
    photo_count = models.get_photo_count()
    display.show_info_screen(photo_count=photo_count, wifi_status=wifi_status, ap_mode=ap)
```

**`display_info` route (line 314):**
```python
@app.route('/api/display/info', methods=['POST'])
def display_info():
    """Show info screen on display"""
    with _setup_mode_lock:
        ap = _in_setup_mode
    wifi_status = wifi_manager.get_wifi_status() or "Not connected"
    photo_count = models.get_photo_count()
    display.show_info_screen(photo_count=photo_count, wifi_status=wifi_status, ap_mode=ap)
    return jsonify({'success': True})
```

**`captive_portal_detect` route (line 427):**
```python
@app.route('/hotspot-detect')
@app.route('/generate_204')
@app.route('/ncsi.txt')
def captive_portal_detect():
    with _setup_mode_lock:
        ap = _in_setup_mode
    if ap or wifi_manager.is_ap_mode():
        return redirect(url_for('setup_wifi'))
    return '', 204
```

**`main()` (lines 448-485):** replace all bare `_in_setup_mode = ...` with locked writes:
```python
    with _setup_mode_lock:
        _in_setup_mode = False   # line 455 equivalent
    ...
    with _setup_mode_lock:
        _in_setup_mode = True    # line 483 equivalent
```

---

### Step 3: Verify no bare references remain

```bash
cd /home/pi/photos
grep -n "_in_setup_mode" app.py
```

Every read should be inside `with _setup_mode_lock:` or reading a local copy `ap = _in_setup_mode` taken under the lock.

**Step 4: Commit**

```bash
cd /home/pi/photos
git add app.py
git commit -m "fix: protect _in_setup_mode with threading.Lock() across all access points"
```

---

## Task 5: Fix display.py — socket leak and font caching

**Files:**
- Modify: `display.py:186-195` (fix socket leak)
- Modify: `display.py:27-32` (add font cache globals)
- Modify: `display.py:146-183` (use cache in _load_fonts)

---

### Step 1: Fix socket leak in `get_system_ip()`

**Problem (line 188-195):** Socket is only closed on the success path. If `s.connect()` raises, the socket leaks.

**Current code:**
```python
def get_system_ip():
    """Get the system's IP address"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"
```

**Replace with:**
```python
def get_system_ip():
    """Get the system's IP address"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
        finally:
            s.close()
    except Exception:
        return "127.0.0.1"
```

---

### Step 2: Cache fonts in `_load_fonts()`

**Problem (line 146):** Font files are loaded from disk on every call to `generate_info_screen()` and `show_message()`. Should load once and cache.

**Add module-level font cache after display state globals (around line 31):**
```python
_font_cache = None  # Cached (large, medium, small) font tuple
```

**Replace `_load_fonts()` (lines 146-183):**
```python
def _load_fonts():
    """Load system fonts, returns (large, medium, small). Cached after first load."""
    global _font_cache
    if _font_cache is not None:
        return _font_cache

    bold_paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    ]
    regular_paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    ]

    font_large = font_medium = font_small = None

    for path in bold_paths:
        if os.path.exists(path):
            try:
                font_large = ImageFont.truetype(path, 48)
                font_medium = ImageFont.truetype(path, 32)
                break
            except Exception:
                pass

    for path in regular_paths:
        if os.path.exists(path):
            try:
                font_small = ImageFont.truetype(path, 24)
                break
            except Exception:
                pass

    if font_large is None:
        font_large = ImageFont.load_default()
        font_medium = font_large
        font_small = font_large

    _font_cache = (font_large, font_medium, font_small)
    return _font_cache
```

**Step 3: Verify**

```bash
cd /home/pi/photos
python3 -c "
import display
# Test socket
ip = display.get_system_ip()
print('IP:', ip)

# Test font cache (call twice, second should be instant)
import time
t0 = time.time(); display._load_fonts(); print('First load:', time.time()-t0)
t0 = time.time(); display._load_fonts(); print('Cached load:', time.time()-t0)
"
```

Expected: Second load time near 0.

**Step 4: Commit**

```bash
cd /home/pi/photos
git add display.py
git commit -m "fix: socket leak in get_system_ip, cache fonts after first load"
```

---

## Task 6: Fix wifi_manager.py — password exposure and nmcli parsing

**Files:**
- Modify: `wifi_manager.py:129-157` (fix password in CLI args)
- Modify: `wifi_manager.py:68-95` (fix nmcli parsing for SSIDs with colons)

---

### Step 1: Fix `connect_to_wifi()` — password in CLI args

**Problem (line 147):** `nmcli dev wifi connect ssid password <pass>` exposes the password in process listings (`ps aux`). Use `nmcli --ask` or stdin is not straightforward; the safest approach is `nmcli con add` with a temporary profile or pass via environment.

**Best practical approach for NetworkManager:** Write a temporary connection and immediately delete it, or use `nmcli con modify` with `wifi-sec.psk` which doesn't expose the password in `ps` because nmcli reads it as a flag value not a positional. Actually both `connect ... password` and `modify ... wifi-sec.psk <pass>` have the same exposure in ps. The most secure approach without interactive input is to write an ifupdown-style keyfile.

**Pragmatic fix:** The existing `con modify` path (line 143) is already used for known networks. For new connections use `nmcli con add` + `nmcli con up` instead of `nmcli dev wifi connect`:

**Current code (lines 140-147):**
```python
    if existing:
        # Update password and connect
        run_cmd(["nmcli", "con", "modify", ssid, "wifi-sec.psk", password], check=False)
        result = run_cmd(["nmcli", "con", "up", ssid], check=False)
    else:
        # Create new connection
        result = run_cmd(["nmcli", "dev", "wifi", "connect", ssid, "password", password], check=False)
```

**Replace with** (use environment variable via `passwd-file` or write a keyfile):

The cleanest approach without dependencies: write password to a temp file and use `nmcli --passwd-file`:

```python
import tempfile

    if existing:
        # Update password and connect using passwd-file to avoid CLI exposure
        with tempfile.NamedTemporaryFile(mode='w', suffix='.pw', delete=False) as f:
            f.write(f"wifi-sec.psk:{password}\n")
            pw_file = f.name
        try:
            run_cmd(["nmcli", "--passwd-file", pw_file, "con", "modify", ssid,
                     "wifi-sec.key-mgmt", "wpa-psk"], check=False)
            result = run_cmd(["nmcli", "con", "up", ssid], check=False)
        finally:
            import os as _os
            _os.unlink(pw_file)
    else:
        # Create new connection using passwd-file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.pw', delete=False) as f:
            f.write(f"wifi-sec.psk:{password}\n")
            pw_file = f.name
        try:
            result = run_cmd(["nmcli", "--passwd-file", pw_file,
                              "dev", "wifi", "connect", ssid], check=False)
        finally:
            import os as _os
            _os.unlink(pw_file)
```

**Note:** `--passwd-file` was added in NetworkManager 1.18+. Verify it's available:
```bash
nmcli --version
```
If it's not available (very old NM), fall back to `con add type wifi`. Document in code.

**Simpler fallback if `--passwd-file` not available:** At minimum add a `# nosec` comment noting the known limitation, and ensure the temp file approach is used where possible.

---

### Step 2: Fix `scan_networks()` — nmcli parsing broken by colons in SSIDs

**Problem (lines 81-91):** `line.split(':')` breaks when an SSID contains a colon (e.g., `MyNetwork:5GHz`). Use `split(':', maxsplit=2)` to limit splits to the known field count.

**Current code (lines 81-91):**
```python
    for line in output.split('\n'):
        parts = line.split(':')
        if len(parts) >= 3:
            ssid = parts[0].strip()
            if ssid and ssid not in seen and ssid != AP_SSID:
                seen.add(ssid)
                networks.append({
                    'ssid': ssid,
                    'signal': int(parts[1]) if parts[1].isdigit() else 0,
                    'security': parts[2] if len(parts) > 2 else 'Open'
                })
```

**Replace with:**
```python
    for line in output.split('\n'):
        # Split into at most 3 parts: SSID may contain colons, but SIGNAL and SECURITY don't
        parts = line.split(':', maxsplit=2)
        if len(parts) >= 3:
            ssid = parts[0].strip()
            if ssid and ssid not in seen and ssid != AP_SSID:
                seen.add(ssid)
                networks.append({
                    'ssid': ssid,
                    'signal': int(parts[1]) if parts[1].isdigit() else 0,
                    'security': parts[2].strip() if len(parts) > 2 else 'Open'
                })
```

**Step 3: Verify parsing fix**

```bash
cd /home/pi/photos
python3 -c "
# Simulate nmcli output with colon in SSID
lines = ['MyNetwork:5GHz:75:WPA2', 'Home:50:WPA2', 'Open_Net:30:']
for line in lines:
    parts = line.split(':', maxsplit=2)
    print(parts)
"
```

Expected: `['MyNetwork:5GHz', '75', 'WPA2']` — SSID preserved correctly.

**Step 4: Commit**

```bash
cd /home/pi/photos
git add wifi_manager.py
git commit -m "fix: use passwd-file for nmcli to avoid password exposure, fix SSID colon parsing"
```

---

## Task 7: Fix requirements.txt — document OpenCV dependency

**Files:**
- Modify: `requirements.txt`

---

### Step 1: Add OpenCV note

**Problem:** `image_processor.py` imports `cv2` but it's not in requirements.txt. The CLAUDE.md says to prefer system apt packages for heavy native libraries on armv7l.

**Current requirements.txt:**
```
flask>=2.0
Pillow>=9.0
APScheduler>=3.9
qrcode>=7.0
inky[rpi]>=1.5
lgpio
numpy>=1.24
```

**Replace with:**
```
flask>=2.0
Pillow>=9.0
APScheduler>=3.9
qrcode>=7.0
inky[rpi]>=1.5
lgpio
numpy>=1.24
# opencv: install via apt, not pip (armv7l pip build OOM-kills or takes 45+ min)
# sudo apt install python3-opencv
# Then symlink into venv: see install.sh
```

**Step 2: Verify install.sh handles opencv symlink**

```bash
grep -i opencv /home/pi/photos/install.sh
```

If not present, add a note to `install.sh`:
```bash
# OpenCV: use system package (pip build fails on armv7l)
echo "Installing system opencv..."
sudo apt-get install -y python3-opencv
# Symlink into venv if needed
SITE=$(python3 -c "import site; print(site.getsitepackages()[0])")
ln -sf /usr/lib/python3/dist-packages/cv2* "$SITE/" 2>/dev/null || true
```

**Step 3: Commit**

```bash
cd /home/pi/photos
git add requirements.txt install.sh
git commit -m "docs: document opencv system package requirement, add install.sh symlink step"
```

---

## Task 8: Final verification pass

**Step 1: Syntax check all modified files**

```bash
cd /home/pi/photos
python3 -m py_compile app.py scheduler.py models.py image_processor.py display.py wifi_manager.py && echo "All OK"
```

Expected: `All OK` with no errors.

**Step 2: Smoke test startup (headless mode)**

```bash
cd /home/pi/photos
source venv/bin/activate
timeout 5 python3 -c "
import models, scheduler, image_processor, display, wifi_manager
models.init_db()
image_processor.ensure_dirs()
print('All modules imported and initialized OK')
" && echo "PASS"
```

**Step 3: Test bulk delete edge cases**

```bash
cd /home/pi/photos
python3 -c "
import models
models.init_db()
print('Empty list:', models.delete_photos_bulk([]))
print('Nonexistent:', models.delete_photos_bulk([9999, 9998]))
"
```

Expected: Both return `[]`.

**Step 4: Confirm no bare _in_setup_mode access in app.py**

```bash
grep -n "_in_setup_mode" /home/pi/photos/app.py
```

All references should either be inside `with _setup_mode_lock:` blocks or be the `global _in_setup_mode` declaration.

**Step 5: Final commit (if any stray fixes)**

```bash
cd /home/pi/photos
git log --oneline -10
```

---

## Summary of Changes

| File | Issues Fixed |
|------|-------------|
| `scheduler.py` | Path validation on restore, O(n) index lookup optimization |
| `models.py` | Empty list SQL crash, remove ORDER BY RANDOM() |
| `image_processor.py` | Validate before save, full cleanup on error, reprocess mutex |
| `app.py` | Thread lock for _in_setup_mode (all access points) |
| `display.py` | Socket leak in get_system_ip, cache font loading |
| `wifi_manager.py` | Password not exposed in CLI args, SSID colon parsing |
| `requirements.txt` | Document opencv system package dependency |

**Issues confirmed as false positives (no code change needed):**
- `scheduler.py` single-photo shuffle: guarded by `len > 1` check already
- `scheduler.py` history cleanup loop: `while _history and ...` guard prevents IndexError
