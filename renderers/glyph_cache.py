"""
Glyph path extraction and caching for text-to-path SVG rendering.

Converts font glyphs to SVG path data, caching results per (font, codepoint) pair.
Uses fonttools to extract outlines and PIL for per-character advance widths.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.ttLib import TTFont
from PIL import ImageFont


@dataclass(frozen=True)
class GlyphPath:
    """SVG path data for a single glyph."""

    path_d: str  # SVG path d attribute (in font units, Y-up)
    advance_width: float  # Advance width in points at the given font size


@lru_cache(maxsize=16)
def _load_ttfont(font_path: str) -> TTFont:
    """Load and cache a fonttools TTFont."""
    return TTFont(font_path)


@lru_cache(maxsize=64)
def _load_pil_font(font_path: str, font_size: int) -> ImageFont.FreeTypeFont:
    """Load and cache a PIL font for advance width measurement."""
    return ImageFont.truetype(font_path, font_size)


def get_pil_font(font_path: str, font_size_int: int) -> ImageFont.FreeTypeFont:
    """Return a cached PIL FreeTypeFont (shared with glyph rendering cache)."""
    return _load_pil_font(font_path, font_size_int)


def _get_glyph_path(font_path: str, codepoint: int) -> str:
    """
    Extract SVG path commands for a single codepoint.

    Returns empty string if the glyph is not found or has no outlines.
    """
    ttfont = _load_ttfont(font_path)
    cmap = ttfont.getBestCmap()
    if codepoint not in cmap:
        return ""
    glyph_name = cmap[codepoint]
    gs = ttfont.getGlyphSet()
    pen = SVGPathPen(gs)
    gs[glyph_name].draw(pen)
    return pen.getCommands()


@lru_cache(maxsize=4096)
def get_glyph(font_path: str, codepoint: int, font_size_int: int) -> GlyphPath:
    """
    Get cached glyph path and advance width for a codepoint.

    Args:
        font_path: Path to the TTF file.
        codepoint: Unicode codepoint.
        font_size_int: Integer font size (for cache key stability).

    Returns:
        GlyphPath with SVG path data and advance width in points.
    """
    path_d = _get_glyph_path(font_path, codepoint)
    pil_font = _load_pil_font(font_path, font_size_int)
    char = chr(codepoint)
    advance = pil_font.getlength(char)
    return GlyphPath(path_d=path_d, advance_width=advance)


def get_font_codepoints(font_path: str) -> list[int]:
    """Return sorted Unicode codepoints mapped by the font's best cmap."""
    ttfont = _load_ttfont(font_path)
    cmap = ttfont.getBestCmap()
    return sorted(cmap.keys()) if cmap else []


def get_font_metrics(font_path: str) -> tuple[int, int, int]:
    """
    Return (units_per_em, ascender, descender) for a font.

    Ascender is positive (above baseline), descender is negative (below).
    """
    ttfont = _load_ttfont(font_path)
    upm = ttfont["head"].unitsPerEm
    os2 = ttfont["OS/2"]
    return upm, os2.sTypoAscender, os2.sTypoDescender


def text_to_svg_group(
    text: str,
    font_path: str,
    font_size: float,
    x: float,
    y: float,
    *,
    fill: str = "black",
    fill_opacity: float = 1.0,
    anchor: str = "start",
    css_class: str | None = None,
) -> str:
    """
    Convert a text string to an SVG <g> element containing <path> elements.

    Each character is rendered as a separate <path>, positioned using PIL's
    advance widths (which account for kerning via the GPOS table).

    The coordinate system matches SVG conventions: Y increases downward,
    (x, y) is the text baseline position.

    Args:
        text: The string to render.
        font_path: Path to the TTF font file.
        font_size: Font size in points.
        x: X position of the text anchor point (SVG coordinates).
        y: Y position of the text baseline (SVG coordinates).
        fill: Fill color.
        fill_opacity: Fill opacity (0-1).
        anchor: Text alignment — 'start', 'middle', or 'end'.

    Returns:
        SVG markup string for a <g> element containing glyph paths.
    """
    if not text:
        return ""

    font_size_int = int(round(font_size))
    if font_size_int < 1:
        return ""

    upm, ascender, descender = get_font_metrics(font_path)
    scale = font_size / upm

    # Compute per-character advance positions using PIL (handles kerning)
    pil_font = _load_pil_font(font_path, font_size_int)
    char_advances: list[float] = []
    cumulative = 0.0
    for i, ch in enumerate(text):
        char_advances.append(cumulative)
        # Use PIL to get the advance for this character in context
        # getlength of substring up to i+1 gives cumulative advance
        cumulative = pil_font.getlength(text[: i + 1])

    total_width = cumulative

    # Adjust starting X for text anchor
    if anchor == "middle":
        x_offset = x - total_width / 2
    elif anchor == "end":
        x_offset = x - total_width
    else:
        x_offset = x

    # Build paths
    paths: list[str] = []
    for i, ch in enumerate(text):
        cp = ord(ch)
        glyph = get_glyph(font_path, cp, font_size_int)
        if not glyph.path_d:
            continue

        char_x = x_offset + char_advances[i]
        # Transform: scale from font units to points, flip Y (font Y-up → SVG Y-down)
        # translate to character position
        tx = char_x
        ty = y
        paths.append(
            f'<path d="{glyph.path_d}" '
            f'transform="translate({tx:.2f},{ty:.2f}) scale({scale:.6f},{-scale:.6f})"/>'
        )

    if not paths:
        return ""

    opacity_attr = f' fill-opacity="{fill_opacity}"' if fill_opacity < 1.0 else ""
    class_attr = f' class="{css_class}"' if css_class else ""
    inner = "".join(paths)
    return f'<g fill="{fill}"{opacity_attr}{class_attr}>{inner}</g>'
