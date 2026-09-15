"""
The field vocabulary of the run details' tables.

Each of the details document's three column lists -- events, exceptions,
holidays -- names fields from its own vocabulary.  The theme engine checks
every list against these sets when a theme loads, so a misspelt field is
an error naming the valid ones rather than a column that silently stays
empty in a document whose whole purpose is to be complete.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import fields
from typing import Any

from renderers.table_columns import FIELD_ALIASES, LINK_REF_FIELD
from shared.data_models import Event

#: Event fields the render record supplies rather than the `events` table.
EVENT_SYNTHETIC_FIELDS: tuple[str, ...] = (
    "icons",
    "icon",
    "marker",
    "event_icon",
    "assigned_color",
    "color_source",
    "category",
    "lane",
    "drawn",
    "page",
    "ref",
    LINK_REF_FIELD,
    "exceptions",
    "continues_before",
    "continues_after",
    "color_rank",
)

#: Synthetic fields shown as icon images rather than text.
ICON_FIELDS: frozenset[str] = frozenset({"icons", "icon", "marker"})

#: Fields of an exception row.
EXCEPTION_FIELDS: tuple[str, ...] = (
    "visualizer",
    "kind",
    "issue",
    "task",
    "date",
    "start",
    "end",
    "ref",
    "detail",
)

#: Fields of a holiday / special-day row (see shared.holiday_listing).
HOLIDAY_FIELDS: tuple[str, ...] = (
    "date",
    "date_label",
    "start_date",
    "end_date",
    "name",
    "raw_name",
    "kind",
    "country",
    "nonworkday",
    "notes",
    "icon",
    "icons",
    "company",
    "language",
    "fullday",
    "starthour",
    "endhour",
    "tags",
)


def event_fields() -> frozenset[str]:
    """Every field an events column may name."""
    return frozenset({f.name for f in fields(Event)} | set(FIELD_ALIASES) | set(EVENT_SYNTHETIC_FIELDS))


def invalid_fields(entries: Iterable[Any] | None, valid: Iterable[str]) -> list[str]:
    """The ``field`` values in *entries* that *valid* does not contain."""
    allowed = {str(name).lower() for name in valid}
    bad: list[str] = []
    for entry in entries or []:
        if not isinstance(entry, dict):
            bad.append(repr(entry))
            continue
        name = str(entry.get("field") or "").strip()
        if not name or name.lower() not in allowed:
            bad.append(name or "(missing field)")
    return bad
