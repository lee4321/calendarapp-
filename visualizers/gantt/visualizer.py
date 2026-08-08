"""Gantt visualizer orchestration."""

from __future__ import annotations

from visualizers.base import BaseLayout, BaseVisualizer
from visualizers.gantt.layout import GanttLayout
from visualizers.gantt.renderer import GanttRenderer


class GanttVisualizer(BaseVisualizer):
    """Task table plus timescale chart with dependencies and progress."""

    @property
    def name(self) -> str:
        return "gantt"

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
        return GanttLayout()

    def _create_renderer(self) -> GanttRenderer:
        return GanttRenderer()
