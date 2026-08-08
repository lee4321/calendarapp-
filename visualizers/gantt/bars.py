"""
Gantt bar geometry over the visible-day axis.

The axis is a list of *visible* days, so x is a column index rather than
a linear function of the date: under ``weekend_style == 0`` Saturday and
Sunday are not columns at all, and a bar spanning a weekend is drawn
across the working days it actually covers.

Everything here is pure geometry -- no drawing, no config -- so the
clipping and snapping decisions that drive both the marks and the
details page can be tested directly.
"""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class DayAxis:
    """The horizontal axis: which days are drawn, and where.

    Attributes:
        days: Visible days in ascending order (see
            :func:`shared.date_utils.visible_days`).
        x: Left edge of the chart area in page units.
        width: Full chart width; every day gets an equal slice.
    """

    days: list[date]
    x: float
    width: float

    @property
    def day_width(self) -> float:
        """Width of one day column."""
        return self.width / len(self.days) if self.days else 0.0

    @property
    def first(self) -> date | None:
        return self.days[0] if self.days else None

    @property
    def last(self) -> date | None:
        return self.days[-1] if self.days else None

    def index_at_or_after(self, day: date) -> int | None:
        """Index of the first visible day not before *day*."""
        index = bisect_left(self.days, day)
        return index if index < len(self.days) else None

    def index_at_or_before(self, day: date) -> int | None:
        """Index of the last visible day not after *day*."""
        index = bisect_right(self.days, day) - 1
        return index if index >= 0 else None

    def left_of(self, index: int) -> float:
        """Left edge of the column at *index*."""
        return self.x + index * self.day_width

    def center_of(self, index: int) -> float:
        """Horizontal center of the column at *index*."""
        return self.x + (index + 0.5) * self.day_width

    def snap_forward(self, day: date) -> int | None:
        """Column for *day*, moving to the next visible day when hidden.

        Returns ``None`` when nothing on or after *day* is visible.
        """
        return self.index_at_or_after(day)

    def is_visible(self, day: date) -> bool:
        """True when *day* has a column of its own."""
        index = bisect_left(self.days, day)
        return index < len(self.days) and self.days[index] == day


@dataclass(frozen=True)
class BarGeometry:
    """Where a span lands on the axis, and what had to be adjusted.

    Attributes:
        x: Left edge in page units.
        width: Bar width in page units.
        clipped_start: The span began before the chart's first day.
        clipped_end: The span ran past the chart's last day.
        snapped: The span's own start day is hidden, so the bar begins on
            a later column than the data says.
        visible: False when the span cannot be drawn at all -- entirely
            outside the range, or entirely inside hidden days.
    """

    x: float = 0.0
    width: float = 0.0
    clipped_start: bool = False
    clipped_end: bool = False
    snapped: bool = False
    visible: bool = False


#: Nothing to draw.
_INVISIBLE = BarGeometry()


def bar_geometry(axis: DayAxis, start: date, end: date) -> BarGeometry:
    """Place the span *start*..*end* (inclusive) on *axis*.

    A span reaching past either edge of the chart is clipped to the edge
    and flagged, so the renderer can draw a continuation icon and the
    details page can report it (answer 16).  A span whose own days are
    all hidden -- a task falling entirely on a weekend under
    ``weekend_style == 0`` -- comes back invisible.
    """
    if not axis.days or axis.day_width <= 0:
        return _INVISIBLE

    if end < start:
        start, end = end, start

    first, last = axis.first, axis.last
    if end < first or start > last:
        return _INVISIBLE

    clipped_start = start < first
    clipped_end = end > last

    start_index = axis.index_at_or_after(max(start, first))
    end_index = axis.index_at_or_before(min(end, last))
    if start_index is None or end_index is None or start_index > end_index:
        # Every day the span covers is hidden.  A *single-day* event is
        # still drawn, on the next working day (answer 22); a multi-day
        # span with no visible day at all cannot be placed sensibly and
        # is reported instead.
        if start == end and start_index is not None:
            return BarGeometry(
                x=axis.left_of(start_index),
                width=axis.day_width,
                snapped=True,
                visible=True,
            )
        return BarGeometry(snapped=True, visible=False)

    return BarGeometry(
        x=axis.left_of(start_index),
        width=(end_index - start_index + 1) * axis.day_width,
        clipped_start=clipped_start,
        clipped_end=clipped_end,
        snapped=not clipped_start and not axis.is_visible(start),
        visible=True,
    )


def progress_width(bar: BarGeometry, percent_complete: float | None) -> float:
    """Length of the progress line along *bar*.

    The fraction applies to the drawn bar, which spans working-day
    columns, so progress is measured against the working-day span rather
    than elapsed calendar time (answer 18).  100% reaches the end of the
    bar exactly.
    """
    if not bar.visible or not percent_complete:
        return 0.0
    fraction = min(max(float(percent_complete), 0.0), 1.0)
    return bar.width * fraction


def float_spans(
    event,
) -> list[tuple[str, str, str]]:
    """The four float ranges present on *event*, as ``(name, from, to)``.

    Ranges are emitted only when both ends carry a date, so a schedule
    without a critical-path export simply produces none (answer 24).
    """
    windows = (
        ("earliest_start", event.earliest_start_date, event.start),
        ("latest_start", event.start, event.latest_start_date),
        ("earliest_end", event.earliest_end_date, event.end),
        ("latest_end", event.end, event.latest_end_date),
    )
    return [
        (name, str(begin), str(finish))
        for name, begin, finish in windows
        if begin and finish
    ]
