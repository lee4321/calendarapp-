"""Timeline layout: page chrome plus the timeline content area."""

from __future__ import annotations

from visualizers.base import ContentAreaLayout


class TimelineLayout(ContentAreaLayout):
    """Header, footer and the ``TimelineArea`` content rectangle."""

    area_key = "TimelineArea"
