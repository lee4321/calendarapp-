"""PIT layout: page chrome plus the ``PITArea`` rectangle.

The renderer sub-lays out the axis, markers, leaders, label boxes, dates
and today line inside it.
"""

from __future__ import annotations

from visualizers.base import ContentAreaLayout


class PITLayout(ContentAreaLayout):
    """Header, footer and the ``PITArea`` content rectangle."""

    area_key = "PITArea"
