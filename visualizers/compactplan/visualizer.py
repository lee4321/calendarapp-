"""
Compact Activities Plan visualizer.

Orchestrates generation of a compressed timeline SVG showing durations
as colored lines above/below a central axis, grouped by resource group.
"""

from __future__ import annotations

from visualizers.base import BaseLayout, BaseVisualizer
from visualizers.compactplan.layout import CompactPlanLayout
from visualizers.compactplan.renderer import CompactPlanRenderer


class CompactPlanVisualizer(BaseVisualizer):
    """Compact activities plan visualization."""

    @property
    def name(self) -> str:
        return "compactplan"

    @property
    def supported_options(self) -> list[str]:
        return super().supported_options + [
            "shade",
            "noevents",
            "nodurations",
            "ignorecomplete",
            "milestones",
            "rollups",
            "WBS",
        ]

    def _create_layout(self) -> BaseLayout:
        return CompactPlanLayout()

    def _create_renderer(self) -> CompactPlanRenderer:
        return CompactPlanRenderer()
