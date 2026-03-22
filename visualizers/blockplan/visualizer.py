"""Blockplan visualizer orchestration."""

from __future__ import annotations

from visualizers.base import BaseLayout, BaseVisualizer
from visualizers.blockplan.layout import BlockPlanLayout
from visualizers.blockplan.renderer import BlockPlanRenderer


class BlockPlanVisualizer(BaseVisualizer):
    """Spreadsheet-like blockplan view with configurable swimlanes."""

    @property
    def name(self) -> str:
        return "blockplan"

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
        return BlockPlanLayout()

    def _create_renderer(self) -> BlockPlanRenderer:
        return BlockPlanRenderer()
