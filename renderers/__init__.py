"""
Renderers package - Shared rendering utilities for SVG generation.

Provides base renderer classes and common utilities for text fitting,
header/footer rendering, and watermarks.
"""

from renderers.svg_base import BaseSVGRenderer
from renderers.text_utils import fittext, shrinktext, string_width

__all__ = [
    "BaseSVGRenderer",
    "fittext",
    "shrinktext",
    "string_width",
]
