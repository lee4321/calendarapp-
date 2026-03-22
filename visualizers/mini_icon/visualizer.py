"""
Mini-icon calendar visualizer.

Like the mini calendar but uses icons from the database for each day's
number cell instead of text glyphs.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from visualizers.mini.visualizer import MiniCalendarVisualizer
from visualizers.mini.layout import MiniCalendarLayout
from visualizers.mini_icon.renderer import MiniIconRenderer

if TYPE_CHECKING:
    from config.config import CalendarConfig
    from shared.db_access import CalendarDB
    from visualizers.base import VisualizationResult


class MiniIconCalendarVisualizer(MiniCalendarVisualizer):
    """
    Mini-icon calendar visualization.

    Produces the same multi-month grid as the mini visualizer but replaces
    each day's numeric label with an SVG icon drawn from the database.
    Supported icon sets: squares, darksquare, darkcircles, circles,
    squircles, darksquircles.
    """

    @property
    def name(self) -> str:
        return "mini-icon"

    @property
    def supported_options(self) -> list[str]:
        return super().supported_options + ["mini_icon_set"]

    def generate(
        self,
        config: "CalendarConfig",
        db: "CalendarDB",
    ) -> "VisualizationResult":
        """Generate the mini-icon calendar SVG."""
        self._expand_to_month_boundaries(config)

        events = self._prepare_data(config, db)

        layout = MiniCalendarLayout()
        coordinates = layout.calculate(config)

        renderer = MiniIconRenderer()
        renderer.set_week_numbers(layout.week_numbers)

        return renderer.render(
            config=config,
            coordinates=coordinates,
            events=events,
            db=db,
        )
