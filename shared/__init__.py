"""
Shared utilities package for EventCalendar.

Contains common functionality used across multiple visualization types.
"""

from shared.data_models import Event, SpecialDay
from shared.date_utils import (
    adjust_end_for_monday_start,
    adjust_end_for_sunday_start,
    adjust_end_for_workweek,
    adjust_start_for_monday_start,
    adjust_start_for_sunday_start,
    adjust_start_for_workweek,
    calc_calendar_range,
    parse_date,
)

__all__ = [
    "Event",
    "SpecialDay",
    "adjust_end_for_monday_start",
    "adjust_end_for_sunday_start",
    "adjust_end_for_workweek",
    "adjust_start_for_monday_start",
    "adjust_start_for_sunday_start",
    "adjust_start_for_workweek",
    "calc_calendar_range",
    "parse_date",
]
