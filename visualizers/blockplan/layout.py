"""Blockplan layout: page chrome plus the blockplan content area."""

from __future__ import annotations

from visualizers.base import ContentAreaLayout


class BlockPlanLayout(ContentAreaLayout):
    """Header, footer and the ``BlockPlanArea`` content rectangle."""

    area_key = "BlockPlanArea"
