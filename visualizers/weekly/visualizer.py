"""
Weekly calendar visualizer.

Orchestrates the generation of weekly calendar SVGs.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from visualizers.base import BaseVisualizer, BaseLayout
from visualizers.weekly.layout import WeeklyCalendarLayout
from visualizers.weekly.renderer import WeeklyCalendarRenderer

if TYPE_CHECKING:
    pass


class WeeklyCalendarVisualizer(BaseVisualizer):
    """
    Weekly calendar visualization.

    Produces an SVG calendar with a grid of day boxes arranged by week,
    supporting various weekend styles, event placement, and multi-day
    duration spanning.
    """

    @property
    def name(self) -> str:
        """Human-readable name of this visualization type."""
        return "weekly"

    @property
    def supported_options(self) -> list[str]:
        """CLI options supported by the weekly calendar visualizer."""
        return super().supported_options + [
            "weekends",
            "monthnames",
            "monthnumbers",
            "weeknumbers",
            "shade",
            "noevents",
            "nodurations",
            "ignorecomplete",
            "milestones",
            "rollups",
            "includenotes",
        ]

    def _create_layout(self) -> BaseLayout:
        """
        Create the weekly calendar layout calculator.

        Returns:
            WeeklyCalendarLayout instance
        """
        return WeeklyCalendarLayout()

    def _create_renderer(self) -> WeeklyCalendarRenderer:
        """
        Create the weekly calendar renderer.

        Returns:
            WeeklyCalendarRenderer instance
        """
        return WeeklyCalendarRenderer()
