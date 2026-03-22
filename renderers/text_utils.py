"""
Text utilities for SVG rendering.

Provides functions for measuring, fitting, and shrinking text to specified widths
using PIL (Pillow) for font metrics.
"""

from __future__ import annotations

from renderers.glyph_cache import get_pil_font as _get_font


def string_width(text: str, font_path: str, font_size: float) -> float:
    """
    Measure the width of a text string in points.

    Args:
        text: String to measure
        font_path: Path to the TTF font file
        font_size: Font size in points

    Returns:
        Width of the text in points
    """
    if not text:
        return 0.0
    font = _get_font(font_path, int(round(font_size)))
    return font.getlength(text)


def fittext(
    text: str,
    desired_width: float,
    font_path: str,
    font_size: float,
) -> str:
    """
    Truncate a string until it fits the desired width.

    Uses binary search on prefix length for O(n log n) instead of O(n²).

    Args:
        text: String to fit
        desired_width: Maximum width in points
        font_path: Path to the TTF font file
        font_size: Font size in points

    Returns:
        Truncated string that fits within desired_width
    """
    if not text or string_width(text, font_path, font_size) <= desired_width:
        return text

    lo, hi = 0, len(text)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if string_width(text[:mid], font_path, font_size) <= desired_width:
            lo = mid
        else:
            hi = mid - 1
    return text[:lo]


def shrinktext(
    text: str,
    desired_width: float,
    font_path: str,
    font_size: float,
    min_fontsize: float = 4.0,
) -> float:
    """
    Reduce font size until text fits the desired width.

    Uses binary search over 0.5-point steps for O(log n) instead of O(n).

    Args:
        text: String to fit
        desired_width: Maximum width in points
        font_path: Path to the TTF font file
        font_size: Starting font size in points
        min_fontsize: Minimum font size to return

    Returns:
        Font size that allows text to fit within desired_width
    """
    if string_width(text, font_path, font_size) <= desired_width:
        return font_size
    if string_width(text, font_path, min_fontsize) > desired_width:
        return min_fontsize

    lo, hi = min_fontsize, font_size
    while hi - lo > 0.5:
        mid = (lo + hi) / 2.0
        if string_width(text, font_path, mid) <= desired_width:
            lo = mid
        else:
            hi = mid
    return max(lo, min_fontsize)
