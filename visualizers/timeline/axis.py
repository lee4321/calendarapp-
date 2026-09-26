"""Axis frame: one coordinate vocabulary for horizontal and vertical timelines.

Everything the timeline draws beside its axis is placed by two numbers:
how far *along* the axis (a date's position) and how far *across* it (away
from the axis line, toward one side). ``AxisFrame`` maps those onto SVG x/y
for either orientation, so each drawing routine is written once:

    +------------+--------------+----------------+----------------------+
    | orientation| along        | across         | Side.PRIMARY is ...  |
    +============+==============+================+======================+
    | horizontal | x (left→right) | y             | above  (sign = -1)   |
    | vertical   | y (top→bottom) | x             | right  (sign = +1)   |
    +------------+--------------+----------------+----------------------+

The PRIMARY/SECONDARY pairing is the one labella and ``_callout_room``
already use. ``Side.BOTH`` has no single sign; callers split it first.
"""

from __future__ import annotations

from dataclasses import dataclass

import arrow

from shared.orientation import Orientation, Side


@dataclass(frozen=True)
class AxisFrame:
    """Where the axis is, and how along/across positions map to x/y."""

    orientation: Orientation
    start: arrow.Arrow  # first visible day
    end: arrow.Arrow  # last visible day
    along0: float  # axis start: left end (horizontal) or top end (vertical)
    along1: float  # axis end: right end or bottom end
    cross: float  # the axis line's own across coordinate: its y or its x

    @property
    def vertical(self) -> bool:
        return self.orientation is Orientation.VERTICAL

    def pos(self, day: arrow.Arrow) -> float:
        """Along-axis position of ``day``, clamped to the visible range."""
        span_days = max(1, (self.end.floor("day") - self.start.floor("day")).days)
        day_offset = (day.floor("day") - self.start.floor("day")).days
        clamped = max(0, min(day_offset, span_days))
        return self.along0 + ((self.along1 - self.along0) * (clamped / span_days))

    def sign(self, side: Side) -> float:
        """+1 or -1: the across direction that points to ``side``."""
        primary_is_positive = self.vertical
        return 1.0 if (side is Side.PRIMARY) == primary_is_positive else -1.0

    def side_of(self, sign: float) -> Side:
        """Inverse of :meth:`sign`."""
        return Side.PRIMARY if (sign > 0) == self.vertical else Side.SECONDARY

    def xy(self, along: float, across: float) -> tuple[float, float]:
        return (across, along) if self.vertical else (along, across)

    def rect(self, along_lo: float, along_len: float, across_lo: float, across_len: float) -> tuple[float, ...]:
        """``(x, y, w, h)`` for a box given by its low corner and extents."""
        if self.vertical:
            return (across_lo, along_lo, across_len, along_len)
        return (along_lo, across_lo, along_len, across_len)
