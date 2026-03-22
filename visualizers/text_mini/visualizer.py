"""
Text mini calendar visualizer.

Produces a UTF-8 text calendar with event markers.
"""

from __future__ import annotations

import arrow

from visualizers.base import BaseVisualizer, VisualizationResult, BaseLayout
from visualizers.mini.layout import MiniCalendarLayout
from visualizers.text_mini.renderer import TextMiniCalendarRenderer


class TextMiniCalendarVisualizer(BaseVisualizer):
    @property
    def name(self) -> str:
        return "text-mini"

    @property
    def supported_options(self) -> list[str]:
        return [
            "mini_columns",
            "mini_rows",
            "weekends",
            "weeknumbers",
            "week_number_mode",
            "week1_start",
        ]

    def _create_layout(self) -> BaseLayout:
        return MiniCalendarLayout()

    def _create_renderer(self):
        return TextMiniCalendarRenderer()

    def generate(self, config, db) -> VisualizationResult:
        self._expand_to_month_boundaries(config)
        events = self._prepare_data(config, db)

        renderer = TextMiniCalendarRenderer()
        output_path = renderer.render(config, events, db)

        return VisualizationResult(
            output_path=str(output_path),
            page_count=1,
            event_count=len(events),
            overflow_count=0,
        )

    @staticmethod
    def _expand_to_month_boundaries(config) -> None:
        start_str = config.userstart or config.adjustedstart
        end_str = config.userend or config.adjustedend
        if not start_str or not end_str:
            return

        s = arrow.get(start_str, "YYYYMMDD")
        e = arrow.get(end_str, "YYYYMMDD")

        config.adjustedstart = s.replace(day=1).format("YYYYMMDD")
        config.adjustedend = e.ceil("month").shift(days=-1).format("YYYYMMDD")
