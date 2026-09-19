"""
SVG pattern decoration helpers.

The `patterns` DB table stores SVG tiles (350 named patterns) that
renderers tile across day boxes / cells via `<pattern>` defs. This module
owns the string surgery those defs need:

* `parse_svg_tile_size`   — tile dimensions from viewBox or width/height,
* `normalize_tile_scale`  — shrink-only auto-normalization factor,
* `colorize_pattern_svg`  — recolor black fills to a rule's color,
* `extract_pattern_inner` — strip prolog/wrapper/Inkscape metadata,
* `pattern_def_id`        — stable `pat-{name}-{color}` def id,
* `pattern_def_xml`       — the complete `<pattern>` element.

Native tile sizes in the table span 16 pt to 1920 pt, so tiling every
pattern at its own size makes the large ones show one arbitrary crop of
the artwork rather than a repeating texture.  `normalize_tile_scale`
brings oversized tiles down to a common target; see its docstring for
the exact rule.


`BaseSVGRenderer._ensure_svg_pattern_def()` is the normal entry point for
renderers; the sheet generators in `ecalendar.py` call these functions
directly.
"""

from __future__ import annotations

import re

# DEFAULT_PATTERN_TARGET_SIZE lives in config.config so CalendarConfig can use
# it as a field default without importing this package (renderers/__init__
# imports svg_base, which imports config.config — the reverse edge is a cycle).
# Re-exported here because this module owns tile geometry.
from config.config import DEFAULT_PATTERN_TARGET_SIZE

__all__ = [
    "DEFAULT_PATTERN_TARGET_SIZE",
    "colorize_pattern_svg",
    "extract_pattern_inner",
    "normalize_tile_scale",
    "parse_svg_tile_size",
    "pattern_def_id",
    "pattern_def_xml",
]


def parse_svg_tile_size(svg: str) -> tuple[float, float]:
    """
    Extract tile width and height from an SVG string.

    Tries viewBox first (most reliable), then falls back to width/height
    attributes.  Returns (20, 20) if nothing can be parsed.
    """
    m = re.search(r'viewBox=["\'][\d.]+ [\d.]+ ([\d.]+) ([\d.]+)["\']', svg)
    if m:
        return float(m.group(1)), float(m.group(2))
    mw = re.search(r'<svg[^>]+width=["\'](\d+)(?:px)?["\']', svg)
    mh = re.search(r'<svg[^>]+height=["\'](\d+)(?:px)?["\']', svg)
    if mw and mh:
        return float(mw.group(1)), float(mh.group(1))
    return 20.0, 20.0


def normalize_tile_scale(
    tile_w: float,
    tile_h: float,
    target_size: float | None = DEFAULT_PATTERN_TARGET_SIZE,
    extra_scale: float = 1.0,
) -> float:
    """
    Return the factor that normalizes a tile to *target_size*.

    Auto-normalization is **shrink-only**: a tile whose largest dimension
    exceeds *target_size* is scaled down to it, and a tile already at or
    below the target is left alone.  Upscaling is deliberately not done —
    the goal is to stop oversized tiles from swamping a cell, not to
    inflate the small ones that already read correctly.

    *extra_scale* is a manual multiplier applied on top of the normalized
    factor, so a theme can nudge the whole library finer or coarser
    without restating the target.

    A *target_size* of None or <= 0 disables normalization, leaving only
    *extra_scale*.
    """
    scale = 1.0
    largest = max(tile_w, tile_h)
    if target_size and target_size > 0 and largest > 0:
        scale = min(1.0, target_size / largest)
    if extra_scale and extra_scale > 0:
        scale *= extra_scale
    return scale


def extract_pattern_inner(svg: str) -> str:
    """
    Return the inner content of a pattern SVG, ready to embed inside a
    ``<pattern>`` element.

    Peels off the XML prolog, doctype, and outer ``<svg>`` wrapper, then
    removes Inkscape-specific metadata (``<sodipodi:namedview>``,
    ``<metadata>``, and any leftover ``inkscape:`` / ``sodipodi:``
    attributes).  Those declarations live on the source ``<svg>`` element,
    so once that element is gone the prefixed content is no longer in
    scope and would make the embedding document invalid XML.
    """
    inner = re.sub(r"<\?xml[^>]*\?>", "", svg)
    inner = re.sub(r"<!DOCTYPE[^>]*>", "", inner)
    inner = re.sub(r"<svg[^>]*>", "", inner, count=1)
    inner = inner.rsplit("</svg>", 1)[0]
    inner = re.sub(r"<sodipodi:namedview\b[^>]*/>", "", inner)
    inner = re.sub(
        r"<sodipodi:namedview\b[^>]*>.*?</sodipodi:namedview>",
        "",
        inner,
        flags=re.DOTALL,
    )
    inner = re.sub(r"<metadata\b[^>]*>.*?</metadata>", "", inner, flags=re.DOTALL)
    inner = re.sub(r"<metadata\b[^>]*/>", "", inner)
    inner = re.sub(r'\s+(?:inkscape|sodipodi):[a-zA-Z][\w-]*="[^"]*"', "", inner)
    inner = re.sub(r"\s+(?:inkscape|sodipodi):[a-zA-Z][\w-]*='[^']*'", "", inner)
    return inner.strip()


def colorize_pattern_svg(svg: str, color: str | None) -> str:
    """
    Replace black fill declarations in a pattern SVG with *color*.

    Handles the three common forms: fill="#000000", fill="#000",
    fill="black".  No-ops when color is None.
    """
    if not color:
        return svg
    result = re.sub(r'fill="#000000"', f'fill="{color}"', svg, flags=re.IGNORECASE)
    result = re.sub(r'fill="#000"', f'fill="{color}"', result, flags=re.IGNORECASE)
    result = re.sub(r'fill="black"', f'fill="{color}"', result, flags=re.IGNORECASE)
    return result


def pattern_def_id(pattern_name: str, color: str | None) -> str:
    """Stable def id for a (pattern, color) pair: ``pat-{name}-{color}``."""
    safe_color = (color or "black").replace("#", "").replace(" ", "_")
    safe_name = re.sub(r"[^a-zA-Z0-9_-]", "_", pattern_name)
    return f"pat-{safe_name}-{safe_color}"


def pattern_def_xml(
    pat_id: str,
    raw_svg: str,
    color: str | None,
    target_size: float | None = DEFAULT_PATTERN_TARGET_SIZE,
    extra_scale: float = 1.0,
) -> str:
    """Build the complete ``<pattern>`` element for an SVG ``<defs>`` block.

    Tiles with ``patternUnits="userSpaceOnUse"`` so tile sizes are in
    document coordinates.  The tile is auto-normalized per
    :func:`normalize_tile_scale`: the artwork is wrapped in a scaling
    ``<g>`` and the pattern's reported width/height shrink by the same
    factor, so it keeps tiling seamlessly at the smaller size.

    The def id does not encode the scale, because *target_size* and
    *extra_scale* come from the config and are therefore constant across
    a single document — one pattern name resolves to one scale per
    drawing.  Pass distinct ids if that ever stops holding.

    """
    tile_w, tile_h = parse_svg_tile_size(raw_svg)
    inner = extract_pattern_inner(colorize_pattern_svg(raw_svg, color))

    scale = normalize_tile_scale(tile_w, tile_h, target_size, extra_scale)
    if scale != 1.0:
        inner = f'<g transform="scale({scale:.6g})">{inner}</g>'
        tile_w *= scale
        tile_h *= scale

    return (
        f'<pattern id="{pat_id}" x="0" y="0" '
        f'width="{tile_w:.6g}" height="{tile_h:.6g}" '
        f'patternUnits="userSpaceOnUse">'
        f"{inner}"
        f"</pattern>"
    )
