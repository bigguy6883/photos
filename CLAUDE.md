# photos.local - Google Photos E-Ink Frame

## Overview

A standalone e-ink photo frame that displays photos from Google Photos albums on a Pimoroni Inky Impression display. Features WiFi AP mode for easy setup and configurable photo cycling.

## Project Structure

```
/home/pi/photos/
├── app.py                    # Main Flask app + display controller
├── wifi_manager.py           # WiFi AP/client mode switching
├── google_photos.py          # Google Photos Picker API integration
├── display.py                # E-ink display abstraction
├── scheduler.py              # Photo cycling scheduler
├── models.py                 # SQLite database models
├── requirements.txt
├── photos.service            # systemd service
├── install.sh                # Installation script
├── config/
│   └── settings.json         # Runtime settings
├── static/
│   ├── style.css
│   └── setup.js
├── templates/
│   ├── base.html
│   ├── setup_wifi.html       # WiFi configuration
│   ├── setup_google.html     # Google Photos auth
│   ├── setup_album.html      # Album selection
│   ├── slideshow.html        # Normal mode settings
│   └── info.html             # Info screen template
├── cache/                    # Cached photos from Google
└── venv/
```

## Key Commands

```bash
# Development
source venv/bin/activate
python app.py

# Service management
sudo systemctl start photos
sudo systemctl stop photos
sudo systemctl restart photos
sudo journalctl -u photos -f

# WiFi Management
sudo nmcli device wifi list
sudo nmcli device wifi hotspot ssid "photos-setup" password "" ifname wlan0
sudo nmcli connection show

# Google OAuth
# Credentials stored in config/google_credentials.json
# Token cached in config/token.json
```

## Button Functions (BCM Pins)

| Pin | Button | Function |
|-----|--------|----------|
| 5 | A | Show info screen (IP, status, photo count) |
| 6 | B | Previous photo |
| 16 | C | Next photo |
| 24 | D | Enter setup mode / Long press: reboot |

## Settings Schema

Settings stored in `config/settings.json`:
- `wifi.ssid` - Connected WiFi network name
- `wifi.configured` - Whether WiFi is set up
- `google.authenticated` - Whether Google Photos is connected
- `google.albums` - List of selected album IDs
- `display.orientation` - "horizontal" or "vertical"
- `display.fit_mode` - "contain", "cover", or "stretch"
- `slideshow.order` - "random" or "sequential"
- `slideshow.interval_minutes` - Minutes between photo changes
- `slideshow.enabled` - Whether auto-cycling is on

## Database

SQLite database at `config/photos.db`:
- `photos` table: id, google_id, album_id, filename, width, height, created_at, cached_at
- `albums` table: id, google_id, title, cover_photo_url, photo_count, synced_at

## API Endpoints

- `GET /` - Main slideshow settings page (or setup wizard if not configured)
- `GET /setup` - Force setup wizard
- `POST /setup/wifi` - Save WiFi credentials
- `GET /auth/google` - Start Google OAuth flow
- `GET /auth/callback` - Google OAuth callback
- `POST /albums` - Update selected albums
- `POST /sync` - Trigger manual photo sync
- `POST /next` - Show next photo
- `POST /prev` - Show previous photo
- `GET /info` - Show info screen
- `POST /settings` - Update display/slideshow settings

## Environment Variables

- `GOOGLE_CLIENT_ID` - Google OAuth client ID
- `GOOGLE_CLIENT_SECRET` - Google OAuth client secret
- `FLASK_SECRET_KEY` - Flask session secret (generated if not set)
