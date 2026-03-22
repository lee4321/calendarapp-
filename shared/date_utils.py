"""
Date utilities for calendar calculations.

Provides date parsing and range calculation functions used by all
visualization types.
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import TYPE_CHECKING

import arrow

from config.config import (
    weekend_style_is_workweek,
    weekend_style_starts_sunday,
)

if TYPE_CHECKING:
    from config.config import CalendarConfig


logger = logging.getLogger(__name__)


class InvalidDateError(Exception):
    """Raised when a date format is invalid."""

    pass


def get_week_number(
    d: arrow.Arrow | date | datetime,
    mode: str = "iso",
    anchor: arrow.Arrow | date | datetime | None = None,
) -> int:
    """
    Compute the week number for a given date.

    Args:
        d: The date to compute the week number for.
        mode: "iso" for ISO 8601 week numbers, "custom" for anchor-based.
        anchor: Start date of week 1 when mode is "custom".

    Returns:
        The week number (1-based). Returns 0 if the date is before
        the custom anchor.
    """
    d_arrow = d if isinstance(d, arrow.Arrow) else arrow.get(d)
    anchor_arrow = None
    if anchor is not None:
        anchor_arrow = anchor if isinstance(anchor, arrow.Arrow) else arrow.get(anchor)

    if mode == "custom" and anchor_arrow is not None:
        delta = (d_arrow.date() - anchor_arrow.date()).days
        if delta < 0:
            return 0
        return delta // 7 + 1
    return d_arrow.isocalendar()[1]


def parse_date(date_str: str, label: str = "date") -> arrow.Arrow:
    """
    Parse a date string in YYYYMMDD format.

    Args:
        date_str: Date string to parse
        label: Label for error messages (e.g., "start", "end")

    Returns:
        Arrow date object

    Raises:
        InvalidDateError: If the date format is invalid
    """
    try:
        return arrow.get(date_str, "YYYYMMDD")
    except (ValueError, arrow.parser.ParserError) as e:
        raise InvalidDateError(f"Invalid {label} date '{date_str}': {e}")


def adjust_start_for_workweek(startdate: arrow.Arrow) -> arrow.Arrow:
    """
    Adjust start date to Monday for work-week-only calendar (style 0).

    Args:
        startdate: Original start date

    Returns:
        Adjusted date (Monday)
    """
    weekday = startdate.isoweekday()
    if weekday == 6:  # Saturday -> next Monday
        return startdate.shift(days=2)
    elif weekday == 7:  # Sunday -> next Monday
        return startdate.shift(days=1)
    elif weekday > 1:  # Tue-Fri -> previous Monday
        return startdate.shift(days=-(weekday - 1))
    return startdate  # Already Monday


def adjust_start_for_sunday_start(startdate: arrow.Arrow) -> arrow.Arrow:
    """
    Adjust start date to previous Sunday (styles 1, 2).

    Args:
        startdate: Original start date

    Returns:
        Adjusted date (Sunday)
    """
    weekday = startdate.isoweekday()
    if weekday <= 6:  # Mon-Sat -> previous Sunday
        return startdate.shift(days=-weekday)
    return startdate  # Already Sunday


def adjust_start_for_monday_start(startdate: arrow.Arrow) -> arrow.Arrow:
    """
    Adjust start date to Monday (styles 3, 4).

    Args:
        startdate: Original start date

    Returns:
        Adjusted date (Monday)
    """
    weekday = startdate.isoweekday()
    if weekday == 1:  # Already Monday
        return startdate
    # Tue-Sun -> previous Monday
    return startdate.shift(days=-(weekday - 1))


def adjust_end_for_workweek(enddate: arrow.Arrow) -> arrow.Arrow:
    """
    Adjust end date to Friday for work-week-only calendar (style 0).

    Args:
        enddate: Original end date

    Returns:
        Adjusted date (Friday)
    """
    weekday = enddate.isoweekday()
    if weekday >= 6:  # Sat/Sun -> previous Friday
        return enddate.shift(days=-(weekday - 5))
    elif weekday < 5:  # Mon-Thu -> next Friday
        return enddate.shift(days=(5 - weekday))
    return enddate  # Already Friday


def adjust_end_for_sunday_start(enddate: arrow.Arrow) -> arrow.Arrow:
    """
    Adjust end date to Saturday (styles 1, 2).

    Args:
        enddate: Original end date

    Returns:
        Adjusted date (Saturday)
    """
    weekday = enddate.isoweekday()
    if weekday != 6:  # Not Saturday -> next Saturday
        return enddate.shift(days=(6 - weekday))
    return enddate  # Already Saturday


def adjust_end_for_monday_start(enddate: arrow.Arrow) -> arrow.Arrow:
    """
    Adjust end date to Sunday (styles 3, 4).

    Args:
        enddate: Original end date

    Returns:
        Adjusted date (Sunday)
    """
    weekday = enddate.isoweekday()
    if weekday == 7:  # Already Sunday
        return enddate
    # Mon-Sat -> next Sunday
    return enddate.shift(days=(7 - weekday))


def calc_calendar_range(config: CalendarConfig, start: str, end: str) -> None:
    """
    Calculate adjusted date range based on weekend style.

    Adjusts start and end dates to ensure complete weeks are displayed.
    Updates config with adjustedstart, adjustedend, duration, and numberofweeks.

    Args:
        config: Calendar configuration to update
        start: Start date in YYYYMMDD format
        end: End date in YYYYMMDD format

    Raises:
        InvalidDateError: If date format is invalid
    """
    startdate = parse_date(start, "start")
    enddate = parse_date(end, "end")

    # Swap if dates are backwards
    if enddate < startdate:
        logger.debug("Swapping start and end dates (were reversed)")
        startdate, enddate = enddate, startdate

    # Adjust start date based on weekend style
    if weekend_style_is_workweek(config.weekend_style):
        adjusted_start = adjust_start_for_workweek(startdate)
    elif weekend_style_starts_sunday(config.weekend_style):
        adjusted_start = adjust_start_for_sunday_start(startdate)
    else:  # styles 3, 4 (Monday start)
        adjusted_start = adjust_start_for_monday_start(startdate)

    # Adjust end date based on weekend style
    if weekend_style_is_workweek(config.weekend_style):
        adjusted_end = adjust_end_for_workweek(enddate)
    elif weekend_style_starts_sunday(config.weekend_style):
        adjusted_end = adjust_end_for_sunday_start(enddate)
    else:  # styles 3, 4 (Monday start)
        adjusted_end = adjust_end_for_monday_start(enddate)

    # Calculate duration and number of weeks
    config.duration = adjusted_end - adjusted_start
    if weekend_style_is_workweek(config.weekend_style):
        config.numberofweeks = int((config.duration.days / 7) + 1)
    else:
        config.numberofweeks = int(config.duration.days / 7 + 1)

    config.adjustedstart = adjusted_start.format("YYYYMMDD")
    config.adjustedend = adjusted_end.format("YYYYMMDD")

    logger.debug(
        f"Date range adjusted: {config.adjustedstart} to {config.adjustedend} "
        f"({config.numberofweeks} weeks)"
    )


def get_months_in_range(start: str, end: str) -> list[tuple[int, int]]:
    """
    Return list of (year, month) tuples spanning the date range.

    Args:
        start: Start date in YYYYMMDD format
        end: End date in YYYYMMDD format

    Returns:
        List of (year, month) tuples
    """
    if not start or not end:
        return []

    s = arrow.get(start, "YYYYMMDD")
    e = arrow.get(end, "YYYYMMDD")

    months: list[tuple[int, int]] = []
    current = s.replace(day=1)
    while current <= e:
        months.append((current.year, current.month))
        current = current.shift(months=1)

    return months


def get_calendar_days(adjusted_start: str, adjusted_end: str) -> list[str]:
    """
    Generate list of calendar day keys in reverse order.

    Args:
        adjusted_start: Start date in YYYYMMDD format
        adjusted_end: End date in YYYYMMDD format

    Returns:
        List of date keys (YYYYMMDD) in reverse order
    """
    start = arrow.get(adjusted_start, "YYYYMMDD")
    end = arrow.get(adjusted_end, "YYYYMMDD")

    caldays = [dt.format("YYYYMMDD") for dt in arrow.Arrow.range("day", start, end)]
    caldays.reverse()
    return caldays


def index_events_by_day(events: list) -> dict[str, list]:
    """
    Build a mapping from YYYYMMDD day key to list of events on that day.

    Single-day events are indexed by their start date. Multi-day events are
    indexed on every day they span, using the Start and End/Finish fields.

    Args:
        events: List of event dicts with "Start", "End"/"Finish" keys (YYYYMMDD)

    Returns:
        Dict mapping YYYYMMDD strings to lists of events
    """
    by_day: dict[str, list] = {}

    for event in events:
        start = (event.get("Start") or "")[:8]
        end = (event.get("End") or event.get("Finish") or start)[:8]
        if not start:
            continue

        if start == end:
            by_day.setdefault(start, []).append(event)
        else:
            try:
                s_arrow = arrow.get(start, "YYYYMMDD")
                e_arrow = arrow.get(end, "YYYYMMDD")
                for dt in arrow.Arrow.range("day", s_arrow, e_arrow):
                    by_day.setdefault(dt.format("YYYYMMDD"), []).append(event)
            except Exception:
                by_day.setdefault(start, []).append(event)

    return by_day
