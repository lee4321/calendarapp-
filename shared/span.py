"""Day-to-position mapping shared by every view that lays days along a distance.

A :class:`Span` divides a distance (part of the canvas width or height) evenly
among a list of visible days.  Each day owns one cell of that distance, so a
segment of a timescale row, a tick, an event marker and the today line all sit
at positions taken from the same mapping.  Days a view hides (weekends) own no
cell; a segment covering them stretches over the days that remain.

A :class:`Frame` adds orientation: it turns the two numbers "along the span" and
"across it" into x and y for a horizontal or vertical axis, so each drawing
routine is written once.

:func:`paginate` splits a long list of days into pages and :func:`clip_segments`
fits segments onto a page.  A segment that would be cut by a page break is
kept whole by moving the break earlier; one too long to fit any page is
clipped on every page it crosses.
"""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from itertools import pairwise
from typing import Any

from shared.orientation import Orientation, Side


class Span:
    """Maps visible days to positions along ``[along0, along1]``."""

    def __init__(self, days: Sequence[date], along0: float, along1: float) -> None:
        if not days:
            raise ValueError("a span needs at least one day")
        ordered = list(days)
        if any(b <= a for a, b in pairwise(ordered)):
            raise ValueError("span days must be strictly increasing")
        self.days: tuple[date, ...] = tuple(ordered)
        self.along0 = float(along0)
        self.along1 = float(along1)
        self._index = {d: i for i, d in enumerate(self.days)}
        self.day_width = (self.along1 - self.along0) / len(self.days)

    @property
    def first(self) -> date:
        return self.days[0]

    @property
    def last(self) -> date:
        return self.days[-1]

    def __len__(self) -> int:
        return len(self.days)

    def is_visible(self, day: date) -> bool:
        """True when *day* has a cell of its own."""
        return day in self._index

    def index_at_or_after(self, day: date) -> int | None:
        """Index of the first visible day not before *day*; ``None`` when there is none."""
        index = bisect_left(self.days, day)
        return index if index < len(self.days) else None

    def index_at_or_before(self, day: date) -> int | None:
        """Index of the last visible day not after *day*; ``None`` when there is none."""
        index = bisect_right(self.days, day) - 1
        return index if index >= 0 else None

    def left_of(self, index: int) -> float:
        """Left edge of the cell at *index*."""
        return self.along0 + index * self.day_width

    def center_of(self, index: int) -> float:
        """Centre of the cell at *index*."""
        return self.along0 + (index + 0.5) * self.day_width

    def boundary(self, day: date) -> float:
        """The edge before *day*: after every visible day strictly earlier.

        Pass a segment's ``end_exclusive`` to get its far edge.  Hidden days
        collapse to nothing, and a *day* past the last gives the span's far end.
        """
        return self.along0 + bisect_left(self.days, day) * self.day_width

    def snap_forward(self, day: date) -> date | None:
        """*day* if visible, else the next visible day; ``None`` when past the last."""
        if day in self._index:
            return day
        for d in self.days:
            if d >= day:
                return d
        return None

    def _clamped_index(self, day: date) -> int:
        """Index of *day*'s cell; a hidden day takes the next visible cell, one past the end the last."""
        if day <= self.first:
            return 0
        snapped = self.snap_forward(day)
        return self._index[snapped] if snapped is not None else len(self.days) - 1

    def start(self, day: date) -> float:
        """Where *day*'s cell begins."""
        return self.along0 + self._clamped_index(day) * self.day_width

    def end(self, day: date) -> float:
        """Where *day*'s cell ends."""
        return self.start(day) + self.day_width

    def center(self, day: date) -> float:
        return self.start(day) + self.day_width / 2

    def extent(self, start: date, end_exclusive: date) -> tuple[float, float] | None:
        """``(a, b)`` covering the visible days in ``[start, end_exclusive)``; ``None`` if there are none."""
        inside = [d for d in self.days if start <= d < end_exclusive]
        if not inside:
            return None
        return self.start(inside[0]), self.end(inside[-1])

    def position(self, day: date) -> float | None:
        """Centre of *day*'s cell, snapping a hidden day forward; ``None`` outside the span."""
        if day < self.first or day > self.last:
            return None
        snapped = self.snap_forward(day)
        return None if snapped is None else self.center(snapped)


@dataclass(frozen=True)
class Frame:
    """A span placed on the page: which way it runs and where the axis line sits.

    ============ ============== ============= ======================
    orientation  along          across        ``Side.PRIMARY`` is
    ============ ============== ============= ======================
    horizontal   x, left→right  y             above (sign -1)
    vertical     y, top→bottom  x             right (sign +1)
    ============ ============== ============= ======================
    """

    span: Span
    orientation: Orientation = Orientation.HORIZONTAL
    #: The axis line's own across coordinate: its y (horizontal) or x (vertical).
    cross: float = 0.0

    @classmethod
    def over_range(
        cls,
        orientation: Orientation,
        first: date | Any,
        last: date | Any,
        along0: float,
        along1: float,
        cross: float,
    ) -> Frame:
        """A frame over every calendar day from *first* to *last* (dates or arrow objects) inclusive."""
        start, end = _as_date(first), _as_date(last)
        if end < start:
            start, end = end, start
        days = [start + timedelta(days=i) for i in range((end - start).days + 1)]
        return cls(Span(days, along0, along1), orientation, cross)

    @property
    def vertical(self) -> bool:
        return self.orientation is Orientation.VERTICAL

    @property
    def along0(self) -> float:
        return self.span.along0

    @property
    def along1(self) -> float:
        return self.span.along1

    @property
    def start(self) -> Any:
        """First day as an arrow object, for callers still working in arrow terms."""
        import arrow

        return arrow.get(self.span.first)

    @property
    def end(self) -> Any:
        """Last day as an arrow object, for callers still working in arrow terms."""
        import arrow

        return arrow.get(self.span.last)

    def pos(self, day: date | Any) -> float:
        """The edge before *day*'s cell (a date or an arrow object); a day past the last gives the far end."""
        return self.span.boundary(_as_date(day))

    def mid(self, day: date | Any) -> float:
        """The centre of *day*'s cell, clamped to the span."""
        return self.span.center(_as_date(day))

    def side_of(self, sign: float) -> Side:
        """Inverse of :meth:`sign`."""
        return Side.PRIMARY if (sign > 0) == self.vertical else Side.SECONDARY

    def sign(self, side: Side) -> float:
        """+1 or -1: the across direction that points to *side*."""
        if side is Side.BOTH:
            raise ValueError("a concrete side is required, not BOTH")
        return 1.0 if (side is Side.PRIMARY) == self.vertical else -1.0

    def xy(self, along: float, across: float) -> tuple[float, float]:
        return (across, along) if self.vertical else (along, across)

    def rect(
        self, along_lo: float, along_len: float, across_lo: float, across_len: float
    ) -> tuple[float, float, float, float]:
        """``(x, y, w, h)`` for a box given by its low corner and extents."""
        if self.vertical:
            return (across_lo, along_lo, across_len, along_len)
        return (along_lo, across_lo, along_len, across_len)


# ─── Segments and pages ──────────────────────────────────────────────────────


@dataclass(frozen=True)
class Piece:
    """A segment as it appears on one page."""

    start: date
    end_exclusive: date
    label: str
    #: The segment began on an earlier page / ends on a later one.
    continues_before: bool = False
    continues_after: bool = False


def clip_segments(
    segments: Sequence[tuple[date, date, str]],
    page_days: Sequence[date],
) -> list[Piece]:
    """The pieces of *segments* ``(start, end_exclusive, label)`` that fall on a page.

    A segment wholly inside the page comes back whole.  One crossing the page's
    edge comes back cut at the edge, flagged ``continues_before`` /
    ``continues_after``, with its label intact so a long segment is labelled on
    every page it crosses.
    """
    if not page_days:
        return []
    first, last = page_days[0], page_days[-1]
    visible = set(page_days)
    pieces: list[Piece] = []
    for start, end_exclusive, label in segments:
        if not any(start <= d < end_exclusive for d in visible):
            continue
        inside = [d for d in page_days if start <= d < end_exclusive]
        pieces.append(
            Piece(
                start=inside[0],
                end_exclusive=inside[-1] + timedelta(days=1),
                label=label,
                continues_before=start < first,
                continues_after=end_exclusive > last + timedelta(days=1),
            )
        )
    return pieces


def paginate(
    days: Sequence[date],
    capacity: int,
    rows: Sequence[Sequence[tuple[date, date]]] = (),
) -> list[list[date]]:
    """Split *days* into pages of at most *capacity* days without cutting a segment that fits a page.

    *rows* holds the segments ``(start, end_exclusive)`` of each timescale row,
    ordered finest first.  A break is *clean* for a row when no segment of that
    row spans it.  Each page ends at the latest break that is clean for as many
    rows as possible, working from the finest row to the coarsest; a row with a
    segment longer than *capacity* is ignored, since it cannot be kept whole and
    is clipped instead.
    """
    if capacity < 1:
        raise ValueError("capacity must be at least 1")
    ordered = list(days)
    cuttable = [row for row in rows if all(_visible_count(ordered, s, e) <= capacity for s, e in row)]
    pages: list[list[date]] = []
    start = 0
    while len(ordered) - start > capacity:
        candidates = list(range(start + 1, start + capacity + 1))
        for row in cuttable:
            clean = [b for b in candidates if _clean_break(ordered, b, row)]
            if clean:
                candidates = clean
        end = max(candidates)
        pages.append(ordered[start:end])
        start = end
    pages.append(ordered[start:])
    return pages


def _visible_count(days: Sequence[date], start: date, end_exclusive: date) -> int:
    return sum(1 for d in days if start <= d < end_exclusive)


def _clean_break(days: Sequence[date], b: int, row: Sequence[tuple[date, date]]) -> bool:
    """True when no segment of *row* contains both ``days[b - 1]`` and ``days[b]``."""
    before, after = days[b - 1], days[b]
    return not any(s <= before < e and s <= after < e for s, e in row)


def _as_date(value: date | Any) -> date:
    """A ``date`` from a date, a datetime, or an arrow object."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return value.date()  # an arrow object
