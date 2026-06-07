"""
PIT (Points in Time) visualizer orchestrator.

Glues PITLayout (page coords) and PITRenderer (drawing) into the
standard BaseVisualizer template-method workflow. Factory dispatch
lands here when ``args.command == "pit"``.
"""

from __future__ import annotations

from visualizers.base import BaseLayout, BaseVisualizer
from visualizers.pit.layout import PITLayout
from visualizers.pit.renderer import PITRenderer


class PITVisualizer(BaseVisualizer):
    """Points-in-Time visualization."""

    @property
    def name(self) -> str:
        return "pit"

    @property
    def supported_options(self) -> list[str]:
        # PIT honors the shared content-filter flags (--milestones,
        # --ignorecomplete, --rollups, --WBS, --includenotes, --empty,
        # --noevents) via the existing filter_events() pipeline — no
        # need to re-declare them here. These are PIT-extra options that
        # don't appear in BaseVisualizer.supported_options.
        return super().supported_options + [
            "noevents",
            "ignorecomplete",
            "milestones",
            "rollups",
            "includenotes",
            "WBS",
            "shrink",
        ]

    def _create_layout(self) -> BaseLayout:
        return PITLayout()

    def _create_renderer(self) -> PITRenderer:
        return PITRenderer()
