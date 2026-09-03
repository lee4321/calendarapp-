"""
Shared helper for *holiday-type* timebands.

A holiday band (``unit: "holiday"``) places the country flag of every holiday
that falls on a visible day into that day's cell.  It differs from an icon
band (:mod:`shared.icon_band`) in where the icon comes from: an icon band
draws a fixed, theme-named icon when a day matches a rule, whereas a holiday
band draws the icon carried by the holiday row itself, so each country brings
its own flag and no theme configuration is needed to add a country.

It also differs in *which* holidays it shows.  Non-workday shading goes
through :func:`shared.day_classifier.classify_day`, which only reports
holidays flagged ``nonworkday=1``; observances such as Groundhog Day carry a
flag but do not close the office, so they never reach that classifier.  A
holiday band shows both, and marks which is which.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from config.config import CalendarConfig
    from shared.db_access import CalendarDB


@dataclass(frozen=True)
class HolidayMark:
    """One holiday to draw in a day cell."""

    icon: str
    title: str
    nonworkday: bool
    country: str


def compute_holiday_band_days(
    visible_days: list[date],
    db: "CalendarDB | None",
    config: "CalendarConfig",
    *,
    nonworkdays_only: bool = False,
) -> dict[date, list[HolidayMark]]:
    """
    Return ``{day: [HolidayMark, ...]}`` for every day in *visible_days*.

    Holidays are read for ``config.country``, so the band follows the same
    ``--country`` selection as the rest of the calendar.  A day with two
    holidays from one country yields one mark per holiday, but the same flag
    is never drawn twice for a day: marks are deduplicated by icon, keeping
    the first, with a nonworkday entry preferred over an observance so the
    day reads as closed when it is.

    *nonworkdays_only* narrows the band to holidays that actually close the
    office, matching what the non-workday shading shows.
    """
    result: dict[date, list[HolidayMark]] = {day: [] for day in visible_days}
    if db is None:
        return result

    getter = getattr(db, "get_holidays_for_date", None)
    if getter is None:
        return result

    country = getattr(config, "country", None)
    for day in visible_days:
        try:
            rows = getter(day.strftime("%Y%m%d"), country) or []
        except Exception:
            continue

        marks: list[HolidayMark] = []
        for row in rows:
            icon = str(row.get("icon") or "").strip()
            if not icon:
                # Nothing to draw for a holiday with no flag; the day still
                # shades normally if it is a non-workday.
                continue
            nonworkday = bool(row.get("nonworkday"))
            if nonworkdays_only and not nonworkday:
                continue
            marks.append(
                HolidayMark(
                    icon=icon,
                    title=str(row.get("displayname") or ""),
                    nonworkday=nonworkday,
                    country=str(row.get("country") or ""),
                )
            )

        # One flag per country per day: prefer the closing holiday so a day
        # carrying both an observance and a public holiday reads as closed.
        best: dict[str, HolidayMark] = {}
        for mark in marks:
            existing = best.get(mark.icon)
            if existing is None or (mark.nonworkday and not existing.nonworkday):
                best[mark.icon] = mark
        result[day] = list(best.values())

    return result
