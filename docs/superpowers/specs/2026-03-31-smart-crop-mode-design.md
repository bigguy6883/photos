# Smart Crop Mode Design

## Problem

The current smart recenter feature has two shortcomings:
1. **Group photos**: It centers on the largest face only, cropping out other people
2. **Landscapes**: The saliency fallback (Sobel edge detection) picks arbitrary edge details, often worse than a simple center crop

## Solution

Replace the binary `smart_recenter` toggle with a `crop_mode` dropdown offering two modes: **Center** (geometric center crop) and **Smart** (auto-detecting face-aware crop with center crop fallback).

## Settings & Data Model

Replace `display.smart_recenter` (boolean) with `display.crop_mode` (string).

| `crop_mode` | Behavior |
|---|---|
| `"center"` | Always geometric center crop, no face detection |
| `"smart"` | Auto-detect per photo: 1 face -> center on it, multiple faces -> fit all/cluster, no faces -> center crop |

Default: `"smart"`.

### Migration

On startup, if `smart_recenter` exists in settings:
- `true` -> `crop_mode: "smart"`
- `false` -> `crop_mode: "center"`
- Delete `smart_recenter` key, save settings

One-time, idempotent.

## Face Detection Pipeline

Replace `find_smart_center()` with `find_crop_center(img, crop_size)`.

Parameters:
- `img`: PIL Image (original, EXIF-transposed)
- `crop_size`: `(width, height)` tuple of the crop window in original image coordinates

Returns: `(cx, cy)` in original image coordinates, or `None`.

### Logic

1. Run YuNet face detection (unchanged from current implementation)
2. **No faces** -> return `None` (caller uses geometric center)
3. **1 face** -> return center of that face
4. **Multiple faces** -> compute bounding box of all faces:
   - If bounding box fits within `crop_size` -> return bounding box center
   - If too spread out -> cluster and return center of largest cluster

### Clustering Algorithm

When all faces don't fit in the crop window:

1. Sort faces left-to-right by x coordinate
2. Compute average face width across all detected faces
3. Greedily merge adjacent faces if distance between them is within 2x average face width
4. Select the cluster with the most faces (tie-break: largest total face area)
5. Return center of that cluster's bounding box

No external dependencies -- arithmetic on YuNet face rectangles.

### Saliency Fallback Removed

The Sobel edge-based saliency code is deleted entirely. No faces = center crop.

## Crop Application

`resize_for_display()` changes:
- Accept `crop_mode` parameter instead of `smart_recenter`
- When `crop_mode == "smart"`: call `find_crop_center(img, crop_size)`, use result or fall back to geometric center
- When `crop_mode == "center"`: skip detection, use geometric center
- Crop clamping logic (already exists) unchanged

## Settings UI

In `settings.html`, replace the Smart Recenter toggle (checkbox) with a Crop Mode dropdown:

```html
<select id="cropMode" onchange="saveSetting('display', 'crop_mode', this.value)">
    <option value="center">Center</option>
    <option value="smart">Smart (face detect)</option>
</select>
```

Label: "Crop Mode" with subtitle "How cover crop positions the frame".

Only relevant when fit mode is "cover" (same visibility as current toggle).

## Reprocessing

Same existing mechanism:
- `app.py` compares current `crop_mode` against `.display_state.json`
- If changed, background thread reprocesses all display images
- Dropdown change triggers reprocessing via `/api/settings` endpoint

## Files Modified

| File | Changes |
|---|---|
| `image_processor.py` | Replace `find_smart_center()` with `find_crop_center()`, remove saliency code, update `resize_for_display()` signature |
| `models.py` | Change `DEFAULT_SETTINGS` (`smart_recenter` -> `crop_mode`), add migration in `load_settings()` |
| `app.py` | Pass `crop_mode` instead of `smart_recenter`, update display state key |
| `templates/settings.html` | Replace toggle with dropdown |

## Not Changed

- Upload flow (already passes settings through)
- Thumbnail generation (own fixed crop)
- Display/scheduler code
- YuNet model or detection parameters
