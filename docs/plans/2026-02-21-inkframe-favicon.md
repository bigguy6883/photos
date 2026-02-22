# InkFrame Favicon & PWA Icons Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a landscape-style SVG favicon and PWA manifest to InkFrame so bookmarks and home screen shortcuts show a recognizable icon.

**Architecture:** Three file changes — create `static/icon.svg` (the icon), create `static/manifest.json` (PWA metadata), modify `templates/base.html` (add `<link>` tags). No backend changes needed.

**Tech Stack:** SVG, HTML, Flask/Jinja2

---

### Task 1: Create `static/icon.svg`

**Files:**
- Create: `static/icon.svg`

No tests for static assets. Visual verification only.

**Step 1: Create the SVG file**

Create `static/icon.svg` with this exact content:

```svg
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
  <defs>
    <linearGradient id="sky" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#1565C0"/>
      <stop offset="70%" stop-color="#FF8C42"/>
      <stop offset="100%" stop-color="#E85D04"/>
    </linearGradient>
    <clipPath id="rounded">
      <rect width="100" height="100" rx="18"/>
    </clipPath>
  </defs>
  <!-- Background sky gradient -->
  <rect width="100" height="100" rx="18" fill="url(#sky)"/>
  <!-- Sun -->
  <circle cx="72" cy="32" r="13" fill="#FFE566" opacity="0.95"/>
  <!-- Far mountain (lighter) -->
  <polygon points="0,100 40,42 80,100" fill="#1B3A2D" opacity="0.7"/>
  <!-- Near mountain (darker) -->
  <polygon points="20,100 58,38 96,100" fill="#0D2218"/>
  <!-- Foreground strip -->
  <rect x="0" y="88" width="100" height="12" rx="0" fill="#0D2218" clip-path="url(#rounded)"/>
</svg>
```

**Step 2: Verify it renders correctly**

Open `static/icon.svg` in a browser and confirm:
- Blue-to-orange gradient sky
- Yellow sun in upper-right
- Two overlapping dark mountain silhouettes
- Rounded corners on the overall shape

**Step 3: Commit**

```bash
git add static/icon.svg
git commit -m "feat: add landscape SVG icon for InkFrame favicon"
```

---

### Task 2: Create `static/manifest.json`

**Files:**
- Create: `static/manifest.json`

**Step 1: Create the manifest**

Create `static/manifest.json`:

```json
{
  "name": "InkFrame",
  "short_name": "InkFrame",
  "description": "E-ink photo frame — upload and display your photos",
  "start_url": "/",
  "display": "standalone",
  "background_color": "#1a1a2e",
  "theme_color": "#E8763A",
  "icons": [
    {
      "src": "/static/icon.svg",
      "sizes": "any",
      "type": "image/svg+xml",
      "purpose": "any maskable"
    }
  ]
}
```

**Step 2: Commit**

```bash
git add static/manifest.json
git commit -m "feat: add PWA manifest for InkFrame"
```

---

### Task 3: Wire up `templates/base.html`

**Files:**
- Modify: `templates/base.html:7` (after the existing `<link rel="stylesheet">` line)

**Step 1: Add favicon and manifest links**

In `templates/base.html`, insert these three lines after line 7 (the stylesheet link):

```html
    <link rel="icon" type="image/svg+xml" href="{{ url_for('static', filename='icon.svg') }}">
    <link rel="apple-touch-icon" href="{{ url_for('static', filename='icon.svg') }}">
    <link rel="manifest" href="{{ url_for('static', filename='manifest.json') }}">
```

The `<head>` block should look like:

```html
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{% block title %}InkFrame{% endblock %}</title>
    <link rel="stylesheet" href="{{ url_for('static', filename='css/style.css') }}">
    <link rel="icon" type="image/svg+xml" href="{{ url_for('static', filename='icon.svg') }}">
    <link rel="apple-touch-icon" href="{{ url_for('static', filename='icon.svg') }}">
    <link rel="manifest" href="{{ url_for('static', filename='manifest.json') }}">
    {% block head %}{% endblock %}
</head>
```

**Step 2: Verify in browser**

- Navigate to `http://photos.local` (or `http://homelab-ip:8080` for local dev)
- Check the browser tab — it should show the landscape icon
- Try bookmarking — the icon should appear in the bookmark

**Step 3: Commit**

```bash
git add templates/base.html
git commit -m "feat: add favicon and PWA manifest links to base template"
```

---

### Task 4: Deploy and verify on photos.local

**Step 1: Rsync to photos.local**

```bash
rsync -av --exclude='config/' --exclude='data/' --exclude='venv/' --exclude='__pycache__' --exclude='.git' ~/photos/ pi@photos.local:/home/pi/photos/
```

**Step 2: Restart service**

```bash
ssh pi@photos.local "sudo systemctl restart inkframe && sudo systemctl status inkframe --no-pager | head -5"
```

Expected: `active (running)`

**Step 3: Verify favicon in browser**

Open `http://photos.local` in a browser. The tab should show the landscape icon.

**Step 4: Push to GitHub**

```bash
git push origin main
```
