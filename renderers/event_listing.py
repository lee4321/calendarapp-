"""
The companion details page's event listing.

What the page *says* -- the range's events chronologically, then the
holidays and special days the chart shows -- as distinct from how it is
paged, which is :mod:`renderers.details_page`.  The mini, mini-icon and
candybar details page and the compactplan key both list through here, so
a theme's ``mini_details`` columns and section names read the same on
every one of them.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Iterable

from renderers.details_page import DetailsColumn, format_datekey
from shared.holiday_labels import format_holiday_label

if TYPE_CHECKING:
    from config.config import CalendarConfig
    from shared.db_access import CalendarDB

#: Columns of the listing when the theme names none, or names headers
#: and widths that do not pair up.
DEFAULT_HEADERS: tuple[str, ...] = (
    "Start Date",
    "Name / Description",
    "Milestone",
    "Priority",
    "Group",
)
DEFAULT_WIDTHS: tuple[float, ...] = (0.16, 0.52, 0.10, 0.10, 0.12)

#: Index of the column an event's notes sit under.
NAME_COLUMN = 1


def format_details_date(value: str | None) -> str:
    """``20260403`` (or a longer timestamp) → ``2026-04-03``."""
    return format_datekey(str(value or "")[:8])


def details_columns(config: "CalendarConfig") -> list[DetailsColumn]:
    """The listing's columns, from ``mini_details.headers``.

    The first column carries dates and the second the event name, so
    those two take the date and name text tokens; the rest are plain
    body cells.  Mismatched headers and widths fall back together --
    a half-edited theme would otherwise put the wrong heading over
    every column.
    """
    headers = list(config.mini_details_headers or [])
    widths = list(config.mini_details_column_widths or [])
    if not headers or len(headers) != len(widths):
        headers, widths = list(DEFAULT_HEADERS), list(DEFAULT_WIDTHS)

    total = sum(widths)
    if total <= 0:
        headers, widths = list(DEFAULT_HEADERS), list(DEFAULT_WIDTHS)
        total = sum(widths)

    columns: list[DetailsColumn] = []
    for index, (header, width) in enumerate(zip(headers, widths)):
        if index == 0:
            token, css = "text:event_date", "ec-event-date"
            # ec-event-date binds to text:caption in the bundled
            # themes, which is where the date column's color has
            # always come from when text:event_date names none.
            fallback = config.get_text_style("ec-event-date").color
            opacity = config.get_text_style("ec-event-date").opacity
        elif index == NAME_COLUMN:
            token, css = "text:event_name", "ec-event-name"
            fallback = config.mini_details_name_text_font_color
            opacity = config.mini_details_name_text_font_opacity
        else:
            token, css = "text:event_name", "ec-event-name"
            fallback = config.mini_details_text_font_color
            opacity = config.mini_details_text_font_opacity
        columns.append(
            DetailsColumn(
                str(header),
                width / total,
                css_class=css,
                token=token,
                fallback_color=fallback,
                fallback_opacity=opacity,
            )
        )
    return columns


def listing_dict(event) -> dict:
    """*event* as the row dict the listing reads.

    Events usually arrive as database rows already; a renderer handed
    :class:`~shared.data_models.Event` objects gets the same fields
    under the same names.
    """
    if isinstance(event, dict):
        return event
    return {
        "Task_Name": event.task_name,
        "Start": event.start,
        "End": event.end,
        "Notes": event.notes,
        "Milestone": event.milestone,
        "Priority": event.priority,
        "Resource_Group": event.resource_group,
    }


def sort_key(event: dict) -> tuple[str, str, str]:
    """Where an event falls in the listing: by span, then by name."""
    return (
        event.get("Start", ""),
        event.get("End", event.get("Finish", "")),
        event.get("Task_Name", ""),
    )


def sorted_events(events: Iterable[dict]) -> list[dict]:
    """Events in the order the listing reads."""
    return sorted(events, key=sort_key)


def event_cells(event: dict, count: int) -> list[str]:
    """One event's cells, in the default column order.

    A theme that asks for fewer columns gets the leading ones; one
    that asks for more gets blanks, rather than a short row that
    would slide the next event's values left.
    """
    values = [
        format_details_date(event.get("Start")),
        event.get("Task_Name", "") or "",
        "True" if event.get("Milestone") else "",
        str(event.get("Priority") or ""),
        str(event.get("Resource_Group") or ""),
    ]
    return (values + [""] * count)[:count]


def event_note(event: dict) -> str:
    """The sub-line under an event's name: its notes, and its end date.

    The end date lives here rather than in a column of its own
    because only a multi-day event has one worth stating.
    """
    start = (event.get("Start") or "")[:8]
    end = (event.get("End") or event.get("Finish") or "")[:8]
    note = event.get("Notes") or ""
    if start and end and start != end:
        end_line = f"End: {format_details_date(end)}"
        return f"{note} | {end_line}".strip(" |") if note else end_line
    return note


def holiday_cells(row: dict, count: int) -> list[str]:
    """A holiday row's cells: date first, name second, kind last."""
    cells = [""] * count
    cells[0] = row["date_label"]
    if count > NAME_COLUMN:
        cells[NAME_COLUMN] = row["name"]
    cells[-1] = row["kind"]
    return cells


def holiday_special_rows(
    daykeys: Iterable[str],
    config: "CalendarConfig",
    db: "CalendarDB",
) -> list[dict]:
    """The deduplicated holiday + special-day entries for *daykeys*.

    A holiday or special day that recurs across several of the days is
    collapsed into a single row labelled with the date range it covers.
    Each row is ``{date_label, name, kind, notes, icon}``; ``icon`` is the
    first icon the entry carried, or ``""``.
    """
    daykeys = sorted(set(daykeys))
    if not daykeys:
        return []

    def date_label(first: str, last: str) -> str:
        if first == last:
            return format_datekey(first)
        return f"{format_datekey(first)} – {format_datekey(last)}"

    # name → {"first": daykey, "last": daykey, "notes": str, ...}
    holidays_seen: dict[str, dict[str, str]] = {}
    specials_seen: dict[str, dict[str, str]] = {}

    for dk in daykeys:
        for h in db.get_holidays_for_date(dk, config.country) or []:
            name = (h.get("displayname") or h.get("name") or "").strip()
            if not name:
                continue
            entry = holidays_seen.setdefault(
                name,
                {"first": dk, "last": dk, "notes": "", "countries": "", "icon": ""},
            )
            entry["last"] = dk
            entry["icon"] = entry["icon"] or _holiday_icon(h)
            # Countries drive the name prefix below rather than the notes
            # column: the same holiday name recurs across countries (both
            # the US and Canada have a New Year's Day), and this listing
            # keys on the name, so the code has to sit beside it to tell
            # the collapsed rows apart.
            country = (h.get("country") or "").strip()
            if country and country not in entry["countries"].split(", "):
                entry["countries"] = (
                    f"{entry['countries']}, {country}"
                    if entry["countries"] else country
                )
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
                },
            )
            entry["last"] = dk

    rows: list[dict] = []
    for name, info in sorted(holidays_seen.items(), key=lambda kv: kv[1]["first"]):
        rows.append({
            "date_label": date_label(info["first"], info["last"]),
            "name": format_holiday_label(name, info["countries"]),
            "kind": "Federal Holiday",
            "notes": info["notes"],
            "icon": info["icon"],
        })
    for name, info in sorted(specials_seen.items(), key=lambda kv: kv[1]["first"]):
        rows.append({
            "date_label": date_label(info["first"], info["last"]),
            "name": name,
            "kind": "Special Day",
            "notes": info["notes"],
            "icon": info["icon"],
        })
    return rows


def _holiday_icon(holiday: dict) -> str:
    """The icon a holiday row names, under whichever column carries it."""
    return str(
        holiday.get("icon")
        or holiday.get("displayicon")
        or holiday.get("displayiconid")
        or ""
    ).strip()
