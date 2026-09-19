"""
SVG pattern decoration helpers.

The `patterns` DB table stores SVG tiles (350 named patterns) that
renderers tile across day boxes / cells via `<pattern>` defs. This module
owns the string surgery those defs need:

* `parse_svg_tile_size`   — tile dimensions from viewBox or width/height,
* `normalize_tile_scale`  — shrink-only auto-normalization factor,
* `colorize_pattern_svg`  — repaint the tile's ink in a rule's color,
* `extract_pattern_inner` — strip prolog/wrapper/Inkscape metadata,
* `pattern_def_id`        — stable `pat-{name}-{color}` def id,
* `pattern_def_xml`       — the complete `<pattern>` element.

Native tile sizes in the table span 16 pt to 1920 pt, so tiling every
pattern at its own size makes the large ones show one arbitrary crop of
the artwork rather than a repeating texture.  `normalize_tile_scale`
brings oversized tiles down to a common target; see its docstring for
the exact rule.

Every tile in the table is monochrome ink on transparent, but the ink is
declared in whatever form the tile's authoring tool emitted — a `fill`
attribute, an Inkscape `style="fill:…"`, a Serif `rgb(35,31,32)`, or
`currentColor` (which resolves against the `<pattern>` def, not the
element being filled, so it never picked up a rule's color).
`colorize_pattern_svg` normalizes all of those; see its docstring.

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
    "pattern_is_recolorable",
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


#: A ``fill=`` / ``stroke=`` presentation attribute and its value.
_PAINT_ATTR_RE = re.compile(r'\b(fill|stroke)="([^"]*)"', re.IGNORECASE)

#: A ``fill:`` / ``stroke:`` declaration inside a ``style="…"`` attribute.
#: The lookbehind keeps the hyphenated properties out — ``fill-rule``,
#: ``fill-opacity``, ``stroke-width``, ``stroke-linejoin`` and friends have a
#: ``-`` rather than a ``:`` after the name, so they can never match anyway,
#: but the guard also stops a match starting mid-identifier.
_PAINT_STYLE_RE = re.compile(r'(?<![\w-])(fill|stroke)\s*:\s*([^;"}\s]+)', re.IGNORECASE)

#: Paint values that mean "draw nothing here", which must survive untouched:
#: repainting them would fill in shapes the artwork deliberately leaves
#: hollow.  ``inherit`` is left alone so it keeps resolving up the tree.
_UNPAINTED = frozenset({"none", "inherit", "transparent"})


def colorize_pattern_svg(svg: str, color: str | None) -> str:
    """
    Repaint a pattern tile's ink in *color*.

    Every tile in the ``patterns`` table is monochrome ink on transparent
    — a survey of all 350 finds exactly three ink values in use
    (``#000000``, ``#000`` and Serif's near-black ``rgb(35,31,32)``), and
    no tile mixes two.  So rather than matching a list of literals, this
    rewrites *every* paint declaration that draws something, in both the
    attribute form (``fill="…"``) and the ``style="fill:…"`` form that
    Inkscape and Serif exports use.

    ``currentColor`` is rewritten too.  Inside a ``<pattern>`` def it
    resolves against the def's own context rather than the element
    carrying ``fill="url(#pat-id)"``, so tiles declaring it used to
    render at the UA default regardless of the color a rule asked for.

    Values in :data:`_UNPAINTED` are left alone, so ``fill="none"`` keeps
    a shape hollow.  A tile that declares no paint at all inherits from
    the wrapper :func:`pattern_def_xml` emits.

    Note this flattens a tile to a single color by design.  Were a
    genuinely multi-color tile ever added to the table, it would need to
    opt out rather than be recolored.

    No-ops when *color* is None.
    """
    if not color:
        return svg

    def _attr(m: re.Match[str]) -> str:
        prop, value = m.group(1), m.group(2)
        if value.strip().lower() in _UNPAINTED:
            return m.group(0)
        return f'{prop}="{color}"'

    def _style(m: re.Match[str]) -> str:
        prop, value = m.group(1), m.group(2)
        if value.strip().lower() in _UNPAINTED:
            return m.group(0)
        return f"{prop}:{color}"

    result = _PAINT_ATTR_RE.sub(_attr, svg)
    return _PAINT_STYLE_RE.sub(_style, result)


#: A raster payload: an ``<image>`` element or an inline data URI.
_RASTER_RE = re.compile(r"<image\b|data:image/", re.IGNORECASE)


def pattern_is_recolorable(svg: str) -> bool:
    """
    Whether :func:`colorize_pattern_svg` can actually repaint this tile.

    False for a tile whose artwork is a raster image rather than vector
    geometry — the pixels carry their own color and no amount of ``fill``
    rewriting reaches them.  ``stars65`` is the only such tile in the
    shipped table (an embedded base64 PNG, which is also why it is by far
    the largest row at ~950 KB); it always renders in its baked-in black.

    Callers use this to tell a user why a pattern ignored their color,
    not to reject it: a raster tile still tiles correctly.
    """
    return not _RASTER_RE.search(svg)


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

    The artwork is wrapped in a ``<g>`` carrying ``fill`` as well as the
    scale.  ``extract_pattern_inner`` drops the source ``<svg>`` element,
    and with it any paint declared there — 25 tiles carry only a root
    ``fill="currentColor"`` — so the wrapper restores an inheritable
    color for content that declares none of its own.  It sets ``fill``
    but deliberately not ``stroke``: an unset ``fill`` defaults to black
    and so wants overriding, whereas an unset ``stroke`` defaults to
    ``none``, and setting it would outline shapes that were never
    stroked.
    """
    tile_w, tile_h = parse_svg_tile_size(raw_svg)
    inner = extract_pattern_inner(colorize_pattern_svg(raw_svg, color))

    scale = normalize_tile_scale(tile_w, tile_h, target_size, extra_scale)
    wrapper: list[str] = []
    if scale != 1.0:
        wrapper.append(f'transform="scale({scale:.6g})"')
        tile_w *= scale
        tile_h *= scale
    if color:
        wrapper.append(f'fill="{color}"')
    if wrapper:
        inner = f"<g {' '.join(wrapper)}>{inner}</g>"

    return (
        f'<pattern id="{pat_id}" x="0" y="0" '
        f'width="{tile_w:.6g}" height="{tile_h:.6g}" '
        f'patternUnits="userSpaceOnUse">'
        f"{inner}"
        f"</pattern>"
    )
