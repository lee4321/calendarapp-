"""
Candybar calendar visualizer.

Orchestrates the vertical year-strip: one row per ISO week, a week-number
column, day cells holding day-of-month numbers, and a merged month-name box
per month. Decoration and icon placement reuse the mini/mini-icon rule engine.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from visualizers.base import BaseLayout, VisualizationResult
from visualizers.mini.visualizer import MiniCalendarVisualizer
from visualizers.candybar.layout import CandybarLayout
from visualizers.candybar.renderer import CandybarRenderer

if TYPE_CHECKING:
    from config.config import CalendarConfig
    from shared.db_access import CalendarDB

logger = logging.getLogger(__name__)


class CandybarVisualizer(MiniCalendarVisualizer):
    """Vertical year-strip calendar visualization."""

    @property
    def name(self) -> str:
        return "candybar"

    @property
    def supported_options(self) -> list[str]:
        return super().supported_options + [
            "candybar_row_height",
            "candybar_week_start",
            "candybar_suppress_weekends",
            "candybar_show_week_numbers",
            "candybar_max_rows_per_page",
            "candybar_month_rotation",
            "candybar_month_label_side",
        ]

    def _create_layout(self) -> BaseLayout:
        return CandybarLayout()

    def _create_renderer(self) -> CandybarRenderer:
        return CandybarRenderer()

    def generate(
        self,
        config: "CalendarConfig",
        db: "CalendarDB",
    ) -> VisualizationResult:
        """Generate the candybar SVG.

        The requested date range is expanded out to whole-week boundaries (not
        whole months) so every row is a complete week with no blank end cells.
        """
        self._expand_to_week_boundaries(config)

        events = self._prepare_data(config, db)

        layout = CandybarLayout()
        coordinates = layout.calculate(config)

        renderer = CandybarRenderer()
        renderer.set_week_numbers(layout.week_numbers)

        return renderer.render(
            config=config,
            coordinates=coordinates,
            events=events,
            db=db,
        )

    @staticmethod
    def _expand_to_week_boundaries(config: "CalendarConfig") -> None:
        """Expand the date range to enclosing whole-week boundaries.

        Snaps the start back to its week-start day and the end forward to its
        week-end day (respecting the candybar week-start setting) so the first
        and last rows are full weeks. Expanding before data is queried means
        the boundary days also pick up their events/holidays.
        """
        from datetime import datetime, timedelta
        from visualizers.candybar.layout import candybar_week_starts_sunday

        start_str = config.userstart or config.adjustedstart
        end_str = config.userend or config.adjustedend
        if not start_str or not end_str:
            return
        try:
            start = datetime.strptime(start_str, "%Y%m%d").date()
            end = datetime.strptime(end_str, "%Y%m%d").date()
        except (ValueError, TypeError):
            return
        if end < start:
            return

        if candybar_week_starts_sunday(config):
            start_off = (start.weekday() + 1) % 7   # back to Sunday
            end_off = (5 - end.weekday()) % 7       # forward to Saturday
        else:
            start_off = start.weekday()             # back to Monday
            end_off = 6 - end.weekday()             # forward to Sunday

        config.adjustedstart = (start - timedelta(days=start_off)).strftime("%Y%m%d")
        config.adjustedend = (end + timedelta(days=end_off)).strftime("%Y%m%d")
