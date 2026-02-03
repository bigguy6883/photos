"""SQLite database models for photos.local"""

import sqlite3
import os
import json
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent / "config" / "photos.db"
SETTINGS_PATH = Path(__file__).parent / "config" / "settings.json"

DEFAULT_SETTINGS = {
    "wifi": {
        "ssid": "",
        "configured": False
    },
    "google": {
        "authenticated": False,
        "albums": []
    },
    "display": {
        "orientation": "horizontal",
        "fit_mode": "contain"
    },
    "slideshow": {
        "order": "random",
        "interval_minutes": 60,
        "enabled": True,
        "current_index": 0
    }
}


def get_db():
    """Get database connection with row factory"""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Initialize database tables"""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    conn = get_db()
    cursor = conn.cursor()

    # Photos table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS photos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            google_id TEXT UNIQUE NOT NULL,
            album_id TEXT,
            filename TEXT NOT NULL,
            width INTEGER,
            height INTEGER,
            mime_type TEXT,
            created_at TEXT,
            cached_at TEXT NOT NULL
        )
    ''')

    # Albums table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS albums (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            google_id TEXT UNIQUE NOT NULL,
            title TEXT NOT NULL,
            cover_photo_url TEXT,
            photo_count INTEGER DEFAULT 0,
            synced_at TEXT
        )
    ''')

    # Picker sessions table (for Google Photos Picker API)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS picker_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT UNIQUE NOT NULL,
            picker_uri TEXT,
            state TEXT DEFAULT 'pending',
            created_at TEXT NOT NULL,
            expires_at TEXT
        )
    ''')

    conn.commit()
    conn.close()


def load_settings():
    """Load settings from JSON file"""
    if not SETTINGS_PATH.exists():
        save_settings(DEFAULT_SETTINGS)
        return DEFAULT_SETTINGS.copy()

    try:
        with open(SETTINGS_PATH, 'r') as f:
            settings = json.load(f)
        # Merge with defaults to handle missing keys
        merged = DEFAULT_SETTINGS.copy()
        for key in DEFAULT_SETTINGS:
            if key in settings:
                if isinstance(DEFAULT_SETTINGS[key], dict):
                    merged[key] = {**DEFAULT_SETTINGS[key], **settings.get(key, {})}
                else:
                    merged[key] = settings[key]
        return merged
    except (json.JSONDecodeError, IOError):
        return DEFAULT_SETTINGS.copy()


def save_settings(settings):
    """Save settings to JSON file"""
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(SETTINGS_PATH, 'w') as f:
        json.dump(settings, f, indent=2)


def update_settings(updates):
    """Update specific settings keys"""
    settings = load_settings()
    for key, value in updates.items():
        if isinstance(value, dict) and key in settings and isinstance(settings[key], dict):
            settings[key].update(value)
        else:
            settings[key] = value
    save_settings(settings)
    return settings


# Photo CRUD operations

def add_photo(google_id, album_id, filename, width=None, height=None, mime_type=None, created_at=None):
    """Add or update a photo record"""
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute('''
        INSERT INTO photos (google_id, album_id, filename, width, height, mime_type, created_at, cached_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(google_id) DO UPDATE SET
            album_id = excluded.album_id,
            filename = excluded.filename,
            width = excluded.width,
            height = excluded.height,
            mime_type = excluded.mime_type,
            cached_at = excluded.cached_at
    ''', (google_id, album_id, filename, width, height, mime_type, created_at, datetime.now().isoformat()))

    conn.commit()
    photo_id = cursor.lastrowid
    conn.close()
    return photo_id


def get_photo(photo_id):
    """Get a photo by ID"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM photos WHERE id = ?', (photo_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def get_photo_by_google_id(google_id):
    """Get a photo by Google ID"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM photos WHERE google_id = ?', (google_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def get_all_photos():
    """Get all photos"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM photos ORDER BY cached_at DESC')
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_photo_count():
    """Get total photo count"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM photos')
    count = cursor.fetchone()[0]
    conn.close()
    return count


def delete_photo(photo_id):
    """Delete a photo record"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM photos WHERE id = ?', (photo_id,))
    conn.commit()
    conn.close()


def delete_photos_by_album(album_id):
    """Delete all photos from an album"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM photos WHERE album_id = ?', (album_id,))
    conn.commit()
    conn.close()


def clear_all_photos():
    """Delete all photo records"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM photos')
    conn.commit()
    conn.close()


# Album CRUD operations

def add_album(google_id, title, cover_photo_url=None, photo_count=0):
    """Add or update an album record"""
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute('''
        INSERT INTO albums (google_id, title, cover_photo_url, photo_count, synced_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(google_id) DO UPDATE SET
            title = excluded.title,
            cover_photo_url = excluded.cover_photo_url,
            photo_count = excluded.photo_count,
            synced_at = excluded.synced_at
    ''', (google_id, title, cover_photo_url, photo_count, datetime.now().isoformat()))

    conn.commit()
    album_id = cursor.lastrowid
    conn.close()
    return album_id


def get_album(album_id):
    """Get an album by ID"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM albums WHERE id = ?', (album_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def get_album_by_google_id(google_id):
    """Get an album by Google ID"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM albums WHERE google_id = ?', (google_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def get_all_albums():
    """Get all albums"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM albums ORDER BY title')
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def delete_album(album_id):
    """Delete an album record"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM albums WHERE id = ?', (album_id,))
    conn.commit()
    conn.close()


# Picker session operations

def create_picker_session(session_id, picker_uri, expires_at=None):
    """Create a picker session record"""
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute('''
        INSERT INTO picker_sessions (session_id, picker_uri, state, created_at, expires_at)
        VALUES (?, ?, 'pending', ?, ?)
    ''', (session_id, picker_uri, datetime.now().isoformat(), expires_at))

    conn.commit()
    conn.close()


def update_picker_session_state(session_id, state):
    """Update picker session state"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('UPDATE picker_sessions SET state = ? WHERE session_id = ?', (state, session_id))
    conn.commit()
    conn.close()


def get_picker_session(session_id):
    """Get a picker session by ID"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM picker_sessions WHERE session_id = ?', (session_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def get_latest_picker_session():
    """Get the most recent picker session"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM picker_sessions ORDER BY created_at DESC LIMIT 1')
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


# Initialize database on module import
init_db()
