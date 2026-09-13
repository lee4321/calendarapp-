"""
Mini calendar visualization package.

Provides a compact monthly grid calendar with event-driven day formatting,
optional week numbers, and duration color bars.
"""

from visualizers.mini.layout import MiniCalendarLayout
from visualizers.mini.renderer import MiniCalendarRenderer
from visualizers.mini.visualizer import MiniCalendarVisualizer

__all__ = [
    "MiniCalendarVisualizer",
    "MiniCalendarLayout",
    "MiniCalendarRenderer",
]
