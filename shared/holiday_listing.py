"""
Holiday and special-day rows for a run's listings.

The days a chart shows can carry government holidays and company special
days.  :func:`holiday_special_rows` collapses them into one row per named
entry -- a holiday recurring across several days becomes a single row
labelled with the range it covers -- for the details document's holiday
table (and, until it is retired, the SVG details page).
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING

from shared.holiday_labels import format_holiday_label

if TYPE_CHECKING:
    from config.config import CalendarConfig
    from shared.db_access import CalendarDB

#: Special-day columns carried through to the row when the database has them.
_SPECIAL_DAY_EXTRAS: tuple[str, ...] = ("company", "language", "fullday", "starthour", "endhour", "tags")


def format_datekey(datekey: str | None) -> str:
    """``20260202`` → ``2026-02-02``; anything else passes through."""
    text = str(datekey or "").strip()
    if len(text) == 8 and text.isdigit():
        return f"{text[:4]}-{text[4:6]}-{text[6:8]}"
    return text


def holiday_special_rows(
    daykeys: Iterable[str],
    config: CalendarConfig,
    db: CalendarDB,
) -> list[dict]:
    """The deduplicated holiday + special-day entries for *daykeys*.

    Each row carries:

    * ``date_label`` / ``date`` -- the day, or the ``first – last`` range;
    * ``start_date``, ``end_date`` -- the first and last ``YYYYMMDD`` covered;
    * ``name`` (with any country prefix), ``raw_name`` (as stored);
    * ``kind`` -- ``Federal Holiday`` or ``Special Day``;
    * ``country``, ``nonworkday``, ``notes``, ``icon`` (the first icon the
      entry carried, or ``""``);
    * for special days, ``company``, ``language``, ``fullday``,
      ``starthour``, ``endhour`` and ``tags`` when the database has them.
    """
    daykeys = sorted(set(daykeys))
    if not daykeys:
        return []

    def date_label(first: str, last: str) -> str:
        if first == last:
            return format_datekey(first)
        return f"{format_datekey(first)} – {format_datekey(last)}"

    holidays_seen: dict[str, dict] = {}
    specials_seen: dict[str, dict] = {}

    for dk in daykeys:
        for h in db.get_holidays_for_date(dk, config.country) or []:
            name = (h.get("displayname") or h.get("name") or "").strip()
            if not name:
                continue
            entry = holidays_seen.setdefault(
                name,
                {"first": dk, "last": dk, "notes": "", "countries": "", "icon": "", "nonworkday": False},
            )
            entry["last"] = dk
            entry["icon"] = entry["icon"] or _holiday_icon(h)
            entry["nonworkday"] = entry["nonworkday"] or bool(h.get("nonworkday"))
            # Countries drive the name prefix below rather than the notes
            # column: the same holiday name recurs across countries (both
            # the US and Canada have a New Year's Day), and this listing
            # keys on the name, so the code has to sit beside it to tell
            # the collapsed rows apart.
            country = (h.get("country") or "").strip()
            if country and country not in entry["countries"].split(", "):
                entry["countries"] = f"{entry['countries']}, {country}" if entry["countries"] else country
        for sd in db.get_special_days_for_date(dk) or []:
            name = (sd.get("name") or "").strip()
            if not name:
                continue
            entry = specials_seen.setdefault(
                name,
                {
                    "first": dk,
                    "last": dk,
                    "notes": (sd.get("notes") or "").strip(),
                    "icon": str(sd.get("icon") or "").strip(),
                    "nonworkday": bool(sd.get("nonworkday")),
                    **{key: sd.get(key) for key in _SPECIAL_DAY_EXTRAS if sd.get(key) not in (None, "")},
                },
            )
            entry["last"] = dk

    rows: list[dict] = []
    for name, info in sorted(holidays_seen.items(), key=lambda kv: kv[1]["first"]):
        label = date_label(info["first"], info["last"])
        rows.append(
            {
                "date_label": label,
                "date": label,
                "start_date": info["first"],
                "end_date": info["last"],
                "name": format_holiday_label(name, info["countries"]),
                "raw_name": name,
                "kind": "Federal Holiday",
                "country": info["countries"],
                "nonworkday": info["nonworkday"],
                "notes": info["notes"],
                "icon": info["icon"],
            }
        )
    for name, info in sorted(specials_seen.items(), key=lambda kv: kv[1]["first"]):
        label = date_label(info["first"], info["last"])
        rows.append(
            {
                "date_label": label,
                "date": label,
                "start_date": info["first"],
                "end_date": info["last"],
                "name": name,
                "raw_name": name,
                "kind": "Special Day",
                "country": "",
                "nonworkday": info["nonworkday"],
                "notes": info["notes"],
                "icon": info["icon"],
                **{key: info[key] for key in _SPECIAL_DAY_EXTRAS if key in info},
            }
        )
    return rows


def _holiday_icon(holiday: dict) -> str:
    """The icon a holiday row names, under whichever column carries it."""
    return str(holiday.get("icon") or holiday.get("displayicon") or holiday.get("displayiconid") or "").strip()
