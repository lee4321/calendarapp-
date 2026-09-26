"""Compact Activities Plan layout: page chrome plus the content area."""

from __future__ import annotations

from visualizers.base import ContentAreaLayout


class CompactPlanLayout(ContentAreaLayout):
    """Header, footer and the ``CompactPlanArea`` content rectangle."""

    area_key = "CompactPlanArea"
