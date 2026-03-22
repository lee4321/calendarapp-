"""
Timeline visualizer.

Orchestrates generation of timeline SVG output.
"""

from __future__ import annotations

from visualizers.base import BaseLayout, BaseVisualizer
from visualizers.timeline.layout import TimelineLayout
from visualizers.timeline.renderer import TimelineRenderer


class TimelineVisualizer(BaseVisualizer):
    """Timeline visualization."""

    @property
    def name(self) -> str:
        return "timeline"

    @property
    def supported_options(self) -> list[str]:
        return super().supported_options + [
            "noevents",
            "nodurations",
            "ignorecomplete",
            "milestones",
            "rollups",
            "includenotes",
            "WBS",
        ]

    def _create_layout(self) -> BaseLayout:
        return TimelineLayout()

    def _create_renderer(self) -> TimelineRenderer:
        return TimelineRenderer()
