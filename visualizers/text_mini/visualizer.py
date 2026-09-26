"""
Text mini calendar visualizer.

Produces a UTF-8 text calendar with event markers.
"""

from __future__ import annotations

from visualizers.base import BaseVisualizer, VisualizationResult
from visualizers.mini.layout import MiniCalendarLayout
from visualizers.mini.visualizer import expand_to_month_boundaries
from visualizers.text_mini.renderer import TextMiniCalendarRenderer


class TextMiniCalendarVisualizer(BaseVisualizer):
    """Month grid as UTF-8 text. It has no SVG page, so no page-chrome options."""

    supported_options: frozenset[str] = frozenset()

    def __init__(self) -> None:
        super().__init__("text-mini", MiniCalendarLayout, TextMiniCalendarRenderer)

    def generate(self, config, db) -> VisualizationResult:
        expand_to_month_boundaries(config)
        events = self._prepare_data(config, db)

        renderer = TextMiniCalendarRenderer()
        output_path = renderer.render(config, events, db)

        run_paths = getattr(config, "run_paths", None)
        if run_paths is not None:
            from renderers.run_details import write_run_details

            write_run_details(renderer.details_record, config, db, run_paths)

        return VisualizationResult(
            output_path=str(output_path),
            page_count=1,
            event_count=len(events),
            overflow_count=0,
        )
