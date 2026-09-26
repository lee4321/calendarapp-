"""
Mini calendar visualizer.

Orchestrates the generation of compact monthly calendar SVGs with
event-driven day formatting, optional week numbers, and duration bars.
The mini-icon view is the same visualizer with ``MiniIconRenderer``.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, cast

import arrow

from visualizers.base import BaseLayout, BaseVisualizer, VisualizationResult
from visualizers.mini.layout import MiniCalendarLayout
from visualizers.mini.renderer import MiniCalendarRenderer

if TYPE_CHECKING:
    from config.config import CalendarConfig
    from shared.db_access import CalendarDB
    from visualizers.candybar.layout import CandybarLayout

logger = logging.getLogger(__name__)


def expand_to_month_boundaries(config: CalendarConfig) -> None:
    """
    Set the adjusted date range to full month boundaries derived
    from the raw user-provided start/end dates.

    The mini calendars operate on whole months. They use the original
    user dates (before weekly grid adjustments) so that requesting
    Feb–Apr produces exactly Feb, Mar, Apr — not extra months
    introduced by week-alignment padding.
    """
    # Prefer the raw user dates; fall back to adjustedstart/end
    start_str = config.userstart or config.adjustedstart
    end_str = config.userend or config.adjustedend
    if not start_str or not end_str:
        return

    s = arrow.get(start_str, "YYYYMMDD")
    e = arrow.get(end_str, "YYYYMMDD")

    # Expand to first of start month … last of end month
    config.adjustedstart = s.replace(day=1).format("YYYYMMDD")
    config.adjustedend = e.ceil("month").shift(days=-1).format("YYYYMMDD")

    logger.debug(
        "Mini calendar date range: %s to %s (from user dates %s to %s)",
        config.adjustedstart,
        config.adjustedend,
        start_str,
        end_str,
    )


class MiniCalendarVisualizer(BaseVisualizer):
    """
    Mini calendar visualization.

    Produces an SVG with a grid of compact monthly calendars,
    each showing day numbers with formatting driven by events,
    holidays, and special days from the database.
    """

    def __init__(
        self,
        name: str = "mini",
        layout_cls: type[BaseLayout] = MiniCalendarLayout,
        renderer_cls: type = MiniCalendarRenderer,
    ) -> None:
        super().__init__(name, layout_cls, renderer_cls)

    def validate_config(self, config: CalendarConfig) -> list[str]:
        """Validate configuration for mini calendar."""
        warnings = super().validate_config(config)

        if config.mini_columns < 1 or config.mini_columns > 12:
            warnings.append(f"mini_columns={config.mini_columns} should be 1-12")

        if config.mini_rows < 0:
            warnings.append(f"mini_rows={config.mini_rows} must be non-negative")

        if config.mini_week_number_mode == "custom" and config.mini_show_week_numbers and not config.mini_week1_start:
            warnings.append(
                "mini_week_number_mode='custom' but mini_week1_start not set; falling back to ISO week numbers"
            )

        return warnings

    def _expand_date_range(self, config: CalendarConfig) -> None:
        expand_to_month_boundaries(config)

    def generate(
        self,
        config: CalendarConfig,
        db: CalendarDB,
    ) -> VisualizationResult:
        """Generate the SVG, passing the layout's week numbers to the renderer."""
        self._expand_date_range(config)
        events = self._prepare_data(config, db)

        # Both mini-family layouts record the week numbers they assigned.
        layout = cast("MiniCalendarLayout | CandybarLayout", self._create_layout())
        coordinates = layout.calculate(config)

        renderer = self._create_renderer()
        renderer.set_week_numbers(layout.week_numbers)

        return renderer.render(
            config=config,
            coordinates=coordinates,
            events=events,
            db=db,
        )
