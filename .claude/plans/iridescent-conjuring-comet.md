# Plan: Round SVG Attributes to 2 Decimal Places

## Context

The drawsvg library outputs float values with full Python precision (e.g., `x="10.123456789"`). Layout calculations already `round(value, 2)` in PDF space, but the `_to_svg_coords()` transformation introduces new precision (e.g., `page_height - y - h` on rounded values), and some values bypass rounding entirely. Reducing precision to 2 decimal places produces cleaner, smaller SVG files with no visual impact at calendar scale.

## Approach: Round in the drawing helper methods

Apply rounding at the **drawing layer** in `renderers/svg_base.py` — the central bottleneck through which almost all SVG output flows. This avoids scattering rounding logic across every layout/renderer file.

Add a small utility function `_r(value, ndigits=2)` and apply it to numeric SVG attributes in each drawing method.

## Changes

### 1. `renderers/svg_base.py` — Add `_r()` helper and apply in drawing methods

Add at module level:
```python
def _r(v: float, n: int = 2) -> float:
    return round(v, n)
```

Apply in:
- **`_draw_rect()`**: Round `x, y, w, h, stroke_width, rx`
- **`_draw_line()`**: Round `x1, y1, x2, y2, stroke_width`
- **`_draw_lines()`**: Round `x1, y1, x2, y2, stroke_width`
- **`_draw_image()`**: Round `x, y, w, h`
- **`_draw_text()`**: Round the `x, y` values in the `scale_x` transform string (already uses `.6f` — change to `.2f` for translate coords)
- **Watermark nested SVG** (line ~609): Round `x, y, target_width, target_height` in the f-string
- **Icon nested SVG** (line ~712): Round `draw_x, draw_y, size` in the f-string

### 2. `renderers/glyph_cache.py` — Already handled

`text_to_svg_group()` already formats positions with `:.2f` and scale with `:.6f`. No changes needed.

### 3. `visualizers/compactplan/renderer.py` — Round icon transform

Line ~671: `f'translate({icon_x},{icon_y}) scale({icon_size/24:.4f})'` — apply `:.2f` to `icon_x, icon_y`.

### 4. `visualizers/timeline/renderer.py` — Round background rect

Lines 123-129: The direct `drawsvg.Rectangle(0, 0, config.pageX, config.pageY, ...)` uses config values that are already integers/rounded, but apply `_r()` for consistency.

### 5. `renderers/svg_base.py` shrink-to-content — Reduce from 4 to 2 decimals

Lines ~403-410: Change `round(value, 4)` to `round(value, 2)` for viewBox values.

## Files to modify

1. `renderers/svg_base.py` — Primary changes (helper + 6 methods)
2. `visualizers/compactplan/renderer.py` — Icon transform string
3. `visualizers/timeline/renderer.py` — Background rect (minor)

## Verification

1. Run tests: `uv run python -m pytest tests/ -v`
2. Generate a sample calendar and inspect the SVG output to confirm attributes are rounded to 2 decimal places
3. Visually compare output before/after to confirm no rendering differences
