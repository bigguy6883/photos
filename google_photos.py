"""Google Photos Picker API integration"""

import os
import json
import requests
import time
from pathlib import Path
from datetime import datetime, timedelta
from urllib.parse import urlencode

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from google.auth.transport.requests import Request

CONFIG_DIR = Path(__file__).parent / "config"
TOKEN_PATH = CONFIG_DIR / "token.json"
CREDENTIALS_PATH = CONFIG_DIR / "google_credentials.json"
CACHE_DIR = Path(__file__).parent / "cache"

# Google Photos Picker API endpoints
PICKER_API_BASE = "https://photospicker.googleapis.com/v1"

# OAuth scopes for Photos Picker
SCOPES = [
    "https://www.googleapis.com/auth/photospicker.mediaitems.readonly"
]


def get_credentials_config():
    """Load OAuth credentials configuration"""
    # Try environment variables first
    client_id = os.environ.get("GOOGLE_CLIENT_ID")
    client_secret = os.environ.get("GOOGLE_CLIENT_SECRET")

    if client_id and client_secret:
        return {
            "web": {
                "client_id": client_id,
                "client_secret": client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": ["http://localhost/auth/callback", "http://photos.local/auth/callback"]
            }
        }

    # Try credentials file
    if CREDENTIALS_PATH.exists():
        with open(CREDENTIALS_PATH, 'r') as f:
            return json.load(f)

    return None


def get_credentials():
    """Get valid OAuth credentials, refreshing if needed"""
    creds = None

    if TOKEN_PATH.exists():
        try:
            with open(TOKEN_PATH, 'r') as f:
                token_data = json.load(f)
            creds = Credentials.from_authorized_user_info(token_data, SCOPES)
        except Exception as e:
            print(f"Error loading token: {e}")

    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            save_credentials(creds)
        except Exception as e:
            print(f"Error refreshing token: {e}")
            creds = None

    return creds


def save_credentials(creds):
    """Save credentials to token file"""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(TOKEN_PATH, 'w') as f:
        f.write(creds.to_json())


def is_authenticated():
    """Check if we have valid Google credentials"""
    creds = get_credentials()
    return creds is not None and creds.valid


def get_auth_url(redirect_uri):
    """Get the OAuth authorization URL"""
    config = get_credentials_config()
    if not config:
        raise ValueError("No Google credentials configured")

    flow = Flow.from_client_config(
        config,
        scopes=SCOPES,
        redirect_uri=redirect_uri
    )

    auth_url, state = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true',
        prompt='consent'
    )

    return auth_url, state


def handle_auth_callback(code, redirect_uri):
    """Handle the OAuth callback and save credentials"""
    config = get_credentials_config()
    if not config:
        raise ValueError("No Google credentials configured")

    flow = Flow.from_client_config(
        config,
        scopes=SCOPES,
        redirect_uri=redirect_uri
    )

    flow.fetch_token(code=code)
    creds = flow.credentials
    save_credentials(creds)

    return True


def revoke_credentials():
    """Revoke and delete stored credentials"""
    creds = get_credentials()

    if creds:
        try:
            requests.post(
                'https://oauth2.googleapis.com/revoke',
                params={'token': creds.token},
                headers={'content-type': 'application/x-www-form-urlencoded'}
            )
        except Exception as e:
            print(f"Error revoking token: {e}")

    if TOKEN_PATH.exists():
        TOKEN_PATH.unlink()


# Picker API functions

def create_picker_session():
    """
    Create a new Google Photos Picker session.
    Returns session info including the picker URI for the user.
    """
    creds = get_credentials()
    if not creds or not creds.valid:
        raise ValueError("Not authenticated with Google Photos")

    headers = {
        "Authorization": f"Bearer {creds.token}",
        "Content-Type": "application/json"
    }

    response = requests.post(
        f"{PICKER_API_BASE}/sessions",
        headers=headers,
        json={}
    )

    if response.status_code != 200:
        raise Exception(f"Failed to create picker session: {response.text}")

    session = response.json()
    return {
        "id": session.get("id"),
        "pickerUri": session.get("pickerUri"),
        "expireTime": session.get("expireTime"),
        "mediaItemsSet": session.get("mediaItemsSet", False)
    }


def get_picker_session(session_id):
    """Get the status of a picker session"""
    creds = get_credentials()
    if not creds or not creds.valid:
        raise ValueError("Not authenticated with Google Photos")

    headers = {
        "Authorization": f"Bearer {creds.token}"
    }

    response = requests.get(
        f"{PICKER_API_BASE}/sessions/{session_id}",
        headers=headers
    )

    if response.status_code != 200:
        raise Exception(f"Failed to get picker session: {response.text}")

    return response.json()


def poll_picker_session(session_id, timeout=300, interval=3):
    """
    Poll a picker session until the user completes selection.

    Args:
        session_id: The picker session ID
        timeout: Maximum seconds to wait
        interval: Seconds between polls

    Returns:
        Session data when complete, or None if timeout/cancelled
    """
    start_time = time.time()

    while time.time() - start_time < timeout:
        try:
            session = get_picker_session(session_id)

            if session.get("mediaItemsSet"):
                return session

            # Check if session expired
            expire_time = session.get("expireTime")
            if expire_time:
                # Parse ISO format
                expire_dt = datetime.fromisoformat(expire_time.replace('Z', '+00:00'))
                if datetime.now(expire_dt.tzinfo) > expire_dt:
                    print("Picker session expired")
                    return None

        except Exception as e:
            print(f"Error polling session: {e}")

        time.sleep(interval)

    print("Picker session timed out")
    return None


def list_picker_media_items(session_id, page_size=100, page_token=None):
    """
    List media items selected in a picker session.

    Returns:
        Dict with 'mediaItems' list and optional 'nextPageToken'
    """
    creds = get_credentials()
    if not creds or not creds.valid:
        raise ValueError("Not authenticated with Google Photos")

    headers = {
        "Authorization": f"Bearer {creds.token}"
    }

    params = {"pageSize": page_size}
    if page_token:
        params["pageToken"] = page_token

    response = requests.get(
        f"{PICKER_API_BASE}/sessions/{session_id}/mediaItems",
        headers=headers,
        params=params
    )

    if response.status_code != 200:
        raise Exception(f"Failed to list media items: {response.text}")

    return response.json()


def get_all_picker_media_items(session_id):
    """Get all media items from a picker session (handles pagination)"""
    all_items = []
    page_token = None

    while True:
        result = list_picker_media_items(session_id, page_token=page_token)
        items = result.get("mediaItems", [])
        all_items.extend(items)

        page_token = result.get("nextPageToken")
        if not page_token:
            break

    return all_items


def download_photo(media_item, max_width=1600, max_height=1200):
    """
    Download a photo from Google Photos.

    Args:
        media_item: Media item dict from picker API
        max_width: Maximum width for downloaded image
        max_height: Maximum height for downloaded image

    Returns:
        Path to downloaded file, or None if failed
    """
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    # Get media item ID and type
    item_id = media_item.get("id") or media_item.get("mediaFile", {}).get("id")
    if not item_id:
        print("No media item ID found")
        return None

    # Construct filename
    mime_type = media_item.get("mediaFile", {}).get("mimeType", "image/jpeg")
    extension = ".jpg"
    if "png" in mime_type:
        extension = ".png"
    elif "gif" in mime_type:
        extension = ".gif"
    elif "webp" in mime_type:
        extension = ".webp"

    filename = f"{item_id}{extension}"
    filepath = CACHE_DIR / filename

    # Skip if already cached
    if filepath.exists():
        return filepath

    # Get the base URL for downloading
    base_url = media_item.get("mediaFile", {}).get("baseUrl")
    if not base_url:
        print(f"No base URL for media item {item_id}")
        return None

    # Append size parameters
    download_url = f"{base_url}=w{max_width}-h{max_height}"

    try:
        creds = get_credentials()
        headers = {}
        if creds and creds.valid:
            headers["Authorization"] = f"Bearer {creds.token}"

        response = requests.get(download_url, headers=headers, stream=True)
        response.raise_for_status()

        with open(filepath, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)

        print(f"Downloaded: {filename}")
        return filepath

    except Exception as e:
        print(f"Failed to download {item_id}: {e}")
        return None


def sync_picker_session(session_id, progress_callback=None):
    """
    Download all photos from a completed picker session.

    Args:
        session_id: The picker session ID
        progress_callback: Optional callback(current, total) for progress

    Returns:
        List of downloaded file paths
    """
    media_items = get_all_picker_media_items(session_id)
    total = len(media_items)
    downloaded = []

    for i, item in enumerate(media_items):
        if progress_callback:
            progress_callback(i + 1, total)

        filepath = download_photo(item)
        if filepath:
            downloaded.append(filepath)

    return downloaded


def get_cached_photos():
    """Get list of cached photo files"""
    if not CACHE_DIR.exists():
        return []

    extensions = {'.jpg', '.jpeg', '.png', '.gif', '.webp'}
    photos = []

    for f in CACHE_DIR.iterdir():
        if f.is_file() and f.suffix.lower() in extensions:
            # Exclude info screen
            if f.name != "info_screen.png":
                photos.append(f)

    return sorted(photos, key=lambda x: x.stat().st_mtime, reverse=True)


def clear_cache():
    """Delete all cached photos"""
    photos = get_cached_photos()
    for photo in photos:
        try:
            photo.unlink()
        except Exception as e:
            print(f"Failed to delete {photo}: {e}")

    return len(photos)


def get_cache_size():
    """Get total size of cached photos in bytes"""
    photos = get_cached_photos()
    return sum(p.stat().st_size for p in photos)


def get_cache_stats():
    """Get cache statistics"""
    photos = get_cached_photos()
    total_size = sum(p.stat().st_size for p in photos)

    return {
        "count": len(photos),
        "size_bytes": total_size,
        "size_mb": round(total_size / (1024 * 1024), 2)
    }
