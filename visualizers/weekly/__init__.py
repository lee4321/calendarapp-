"""
Weekly calendar visualization package.

Provides weekly calendar SVG generation with configurable weekend styles,
event placement, and multi-day duration support.
"""

from visualizers.weekly.layout import WeeklyCalendarLayout
from visualizers.weekly.renderer import WeeklyCalendarRenderer
from visualizers.weekly.visualizer import WeeklyCalendarVisualizer

__all__ = [
    "WeeklyCalendarVisualizer",
    "WeeklyCalendarLayout",
    "WeeklyCalendarRenderer",
]
