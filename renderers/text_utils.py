"""
Text utilities for SVG rendering.

Provides functions for measuring, fitting, wrapping, and shrinking text to
specified widths using PIL (Pillow) for font metrics.
"""

from __future__ import annotations

from typing import Callable

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


#: Appended to a string shortened in place, marking what was dropped.
ELLIPSIS = "…"


def fit_lines(
    text: str,
    width: float,
    max_lines: int,
    measure: Callable[[str], float],
) -> list[str]:
    """Wrap *text* to *width*, capped at *max_lines* with an ellipsis.

    Wrapping is word-based; a single word wider than the column is broken
    mid-word rather than allowed to overflow.  The returned list is never
    longer than *max_lines*, so row height stays uniform (answer 9).

    Args:
        text: The already-formatted cell value.
        width: Usable width in the same units *measure* returns.
        max_lines: Hard cap on returned lines.
        measure: Width of a candidate string, e.g. a bound
            :func:`renderers.text_utils.string_width`.

    Returns:
        The lines to draw, or ``[]`` for empty input.
    """
    text = (text or "").strip()
    if not text or width <= 0 or max_lines <= 0:
        return []

    lines: list[str] = []
    remaining_words = text.split()

    while remaining_words and len(lines) < max_lines:
        is_last_line = len(lines) == max_lines - 1
        line, remaining_words = _take_line(remaining_words, width, measure)

        if is_last_line and remaining_words:
            line = _with_ellipsis(line, width, measure)

        lines.append(line)

    return lines


def _take_line(
    words: list[str], width: float, measure: Callable[[str], float]
) -> tuple[str, list[str]]:
    """Pack as many words as fit; returns the line and what is left over."""
    line = ""
    index = 0
    for index, word in enumerate(words):
        candidate = f"{line} {word}".strip()
        if measure(candidate) <= width:
            line = candidate
            continue
        if not line:
            # First word does not fit on its own — break it mid-word so a
            # long unbroken token cannot overflow the column.
            head, tail = _split_to_fit(word, width, measure)
            return head, ([tail] if tail else []) + words[index + 1:]
        return line, words[index:]
    return line, []


def _split_to_fit(
    word: str, width: float, measure: Callable[[str], float]
) -> tuple[str, str]:
    """Split *word* at the last character that still fits."""
    for cut in range(len(word) - 1, 0, -1):
        if measure(word[:cut]) <= width:
            return word[:cut], word[cut:]
    return word[:1], word[1:]


def _with_ellipsis(
    line: str, width: float, measure: Callable[[str], float]
) -> str:
    """Append the ellipsis, dropping characters until it fits."""
    candidate = line.rstrip()
    while candidate and measure(candidate + ELLIPSIS) > width:
        candidate = candidate[:-1].rstrip()
    return (candidate + ELLIPSIS) if candidate else ELLIPSIS
