"""The "today" date and where it falls on a span, for every view.

One place decides what day it is.  A theme or a test can pin it
(``today.date: YYYYMMDD``); otherwise the clock decides.  A day a view hides
(a Saturday, in a weekdays-only chart) still gets a mark, on the next visible
day, so "today" never silently disappears.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date

from shared.span import Span


def parse_day(value: str | date | None) -> date | None:
    """A ``date`` from ``YYYYMMDD`` or ``YYYY-MM-DD`` text; ``None`` if *value* is empty or unparseable."""
    if value is None or value == "":
        return None
    if isinstance(value, date):
        return value
    text = str(value).strip()
    try:
        if len(text) == 8 and text.isdigit():
            return date(int(text[:4]), int(text[4:6]), int(text[6:8]))
        return date.fromisoformat(text)
    except ValueError:
        return None


def resolve_today(pinned: str | date | None = None, clock: Callable[[], date] = date.today) -> date:
    """The pinned date when it parses, else the clock's."""
    return parse_day(pinned) or clock()


def today_position(today: date, span: Span) -> float | None:
    """Centre of today's cell along *span*; ``None`` when today is outside it."""
    return span.position(today)
