# InkFrame

Self-hosted e-ink photo frame with a mobile-first web interface. Drag and drop photos from your phone or computer — no cloud sync or Google account needed.

## Hardware

- Raspberry Pi (any model with GPIO and WiFi)
- [Inky Impression 5.7"](https://shop.pimoroni.com/products/inky-impression-5-7) 7-color e-ink display (600x448)
- 4 physical buttons (built into the Inky Impression)

## Features

### Photo Management
- Drag-and-drop upload from any browser (JPG, PNG, GIF, BMP, WebP, TIFF)
- Gallery view with thumbnails, bulk select, and tap-to-display
- Up to 20 MB per upload (configurable)
- EXIF orientation is automatically corrected on upload

### Display
- **Three fit modes**: contain (letterboxed with black bars), cover (fills display, crops edges), stretch (distorts to fill)
- **Smart recenter**: YuNet DNN face detection shifts cover crops toward faces, with edge-based saliency fallback when no face is detected
- **Saturation control**: adjustable e-ink color vibrancy (0.0-1.0, default 0.5)
- **Orientation setting**: horizontal or vertical
- **Display reprocessing**: changing fit mode or smart recenter triggers a background reprocess of all display images from their originals

### Slideshow
- Automatic photo cycling with configurable interval: 5, 15, or 30 minutes; 1, 3, 6, 12, or 24 hours (default: 1 hour)
- **Random** (default): shuffle-bag guarantees every photo shown once before any repeat; position survives restarts
- **Sequential**: cycles in upload order, position survives restarts; previous button goes backward in order
- Auto-starts on boot when enabled
- Auto-starts when the first photo is uploaded (if auto-start is enabled)
- History stack for navigating back through recently viewed photos (random mode)

### Physical Buttons

| Button | GPIO | Function |
|--------|------|----------|
| A | 5 | Info screen (IP, WiFi status, QR code, photo count) |
| B | 6 | Previous photo |
| C | 16 | Next photo |
| D | 24 | Short press: AP setup mode / Hold 2s: reboot |

Buttons use lgpio polling (50ms interval) with 300ms debounce. gpiozero interrupt-based GPIO is not used due to compatibility issues on Raspberry Pi OS Trixie with Python 3.13.

### WiFi Setup
- Built-in access point mode for first-time setup (SSID: `inkframe-setup`, password: `photoframe`)
- AP IP address: `192.168.4.1`
- Captive portal auto-redirects to WiFi configuration page on iOS, Android, and Windows
- QR code on info screen for quick WiFi join or browser navigation
- WiFi credentials managed via NetworkManager (`nmcli`)

### Web Interface
- **Gallery** (`/`): upload zone, photo grid, display controls (next/prev/info), slideshow start/stop
- **Settings** (`/settings`): fit mode, smart recenter toggle, saturation slider, orientation, slideshow interval and order, WiFi network
- **WiFi Setup** (`/setup/wifi`): network scanner with signal strength indicators
- Progressive Web App (PWA) — installable to home screen on mobile

## Install

```bash
git clone https://github.com/bigguy6883/inkframe.git
cd inkframe
./install.sh
```

The install script must be run as a non-root user (it will call `sudo` internally). It handles:
- System packages (including OpenCV via apt to avoid slow ARM compilation)
- Python virtual environment and pip dependencies
- Symlinking system OpenCV into the venv
- YuNet face detection model download
- Data and config directory creation
- SPI enablement via `raspi-config`
- Hostname configuration (`photos.local`)
- systemd service setup (`inkframe.service`)

Note: the install script assumes the repo is cloned to `/home/pi/photos`. Cloning elsewhere requires updating the path in `install.sh` and `inkframe.service`.

## Usage

After install, open `http://photos.local/` from any device on the same network.

```bash
# Service management
sudo systemctl start|stop|restart inkframe
sudo journalctl -u inkframe -f
```

The service runs as root (required for port 80 and GPIO access).

## Development (Headless)

On a machine without an Inky display, the app runs with `MockDisplay`, which saves output to `data/mock_display.png` instead of driving hardware.

```bash
source venv/bin/activate
python3 -c "from app import app; app.run(host='0.0.0.0', port=8080)"
```

## API

All endpoints are available at `http://photos.local/`.

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/photos/upload` | Upload a photo (multipart form) |
| GET | `/api/photos?limit=20&offset=0` | List photos (paginated) |
| DELETE | `/api/photos/<id>` | Delete a photo |
| POST | `/api/photos/delete-bulk` | Bulk delete (`{"ids": [1,2,3]}`) |
| POST | `/api/display/next` | Show next photo |
| POST | `/api/display/prev` | Show previous photo |
| POST | `/api/display/show/<id>` | Show specific photo |
| POST | `/api/display/info` | Show info screen |
| POST | `/api/slideshow/start` | Start slideshow |
| POST | `/api/slideshow/stop` | Stop slideshow |
| GET | `/api/settings` | Get all settings |
| POST | `/api/settings` | Update settings (deep merge) |
| GET | `/api/status` | System status (WiFi, slideshow, photo count, display busy flag) |

## Project Structure

```
app.py              # Flask routes, GPIO buttons, startup
display.py          # E-ink display abstraction, MockDisplay, info screens
image_processor.py  # Upload processing, resize, face detection, reprocessing
models.py           # SQLite database + JSON settings
scheduler.py        # Slideshow cycling with APScheduler, shuffle-bag, history
wifi_manager.py     # WiFi AP/client mode via NetworkManager
install.sh          # Automated setup script
inkframe.service    # systemd service definition
templates/          # Jinja2 templates
  base.html         # Shared layout, navbar, PWA manifest link
  index.html        # Gallery page
  settings.html     # Settings page
  setup_wifi.html   # WiFi configuration page
static/
  css/style.css     # All styles
  js/upload.js      # Drag-drop upload handling
  js/gallery.js     # Gallery select/delete/display actions
  icon.svg          # App icon (favicon + PWA)
  manifest.json     # PWA manifest
models/             # YuNet face detection model (downloaded by install.sh)
data/               # Runtime data (gitignored)
  originals/        # Original uploads preserved as-is
  display/          # Pre-rendered 600x448 PNG for e-ink
  thumbnails/       # 300x200 JPEG for web gallery
  mock_display.png  # MockDisplay output (headless dev only)
config/             # SQLite DB + JSON settings (gitignored)
```

## Requirements

- Raspberry Pi OS (Bookworm or Trixie)
- Python 3.11+
- SPI enabled for e-ink display
- NetworkManager for WiFi management

## License

MIT
