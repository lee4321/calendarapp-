"""
Candybar calendar visualizer.

Orchestrates the vertical year-strip: one row per ISO week, a week-number
column, day cells holding day-of-month numbers, and a merged month-name box
per month. Decoration and icon placement reuse the mini/mini-icon rule engine.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from visualizers.candybar.layout import CandybarLayout
from visualizers.candybar.renderer import CandybarRenderer
from visualizers.mini.visualizer import MiniCalendarVisualizer

if TYPE_CHECKING:
    from config.config import CalendarConfig


class CandybarVisualizer(MiniCalendarVisualizer):
    """Vertical year-strip calendar visualization.

    Same workflow as the mini calendar, but the date range expands to whole
    weeks (not whole months) so every row is a complete week with no blank
    end cells.
    """

    def __init__(self) -> None:
        super().__init__("candybar", CandybarLayout, CandybarRenderer)

    def _expand_date_range(self, config: CalendarConfig) -> None:
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
            start_off = (start.weekday() + 1) % 7  # back to Sunday
            end_off = (5 - end.weekday()) % 7  # forward to Saturday
        else:
            start_off = start.weekday()  # back to Monday
            end_off = 6 - end.weekday()  # forward to Sunday

        config.adjustedstart = (start - timedelta(days=start_off)).strftime("%Y%m%d")
        config.adjustedend = (end + timedelta(days=end_off)).strftime("%Y%m%d")
