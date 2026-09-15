"""
Table column model shared by every tabular output.

Columns are *layout* configuration, not style: which fields appear, in
what order, how wide, how aligned, and how a value becomes text.  The
gantt task table reads them from ``gantt.columns:``; the run's details
document and event CSV read the same schema from ``details.markdown``
and ``details.csv``, so a column list written for one pastes into the
other.

The value pipeline is one pass per cell:

    row field → :func:`cell_value` (format / date_format / icon)
              → the output's own fitting (``fit_lines`` on the chart,
                escaping in Markdown, quoting in CSV)

A "row" is anything with attributes: an :class:`~shared.data_models.Event`
on the chart, or a view that layers render-derived fields over one.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any

import arrow

from shared.date_utils import format_arrow_date

if TYPE_CHECKING:
    from collections.abc import Iterable

    from config.config import CalendarConfig

#: Synthetic column: cross-page dependency reference icons.  It has no
#: `events` field behind it — the gantt renderer supplies the icons per row
#: from the link graph, so `cell_value` and `cell_icon_visible` stay out of it.
LINK_REF_FIELD = "link_ref"

#: Fields rendered as an icon when the value is truthy and the column
#: asks for ``render: icon`` without naming one.  The values are config
#: attributes holding the icon name.
_DEFAULT_FIELD_ICONS: dict[str, str] = {
    "rollup": "gantt_rollup_icon",
    "milestone": "gantt_milestone_flag_icon",
}

#: Themes name fields after the `events` **table**, which is the
#: vocabulary the requirements use.  ``Event`` normalizes a few of those to
#: shorter attribute names, so map the spellings a user would write onto
#: the attribute that actually holds the value.  Anything absent here is
#: used as-is, which covers the majority of fields: every other `events`
#: column is spelled the same on the table and on ``Event``.
FIELD_ALIASES: dict[str, str] = {
    "id": "db_id",
    "name": "task_name",
    "task": "task_name",
    "start_date": "start",
    "finish": "end",
    "finish_date": "end",
    "end_date": "end",
}


def resolve_field(name: str) -> str:
    """Map a theme-authored field name onto the attribute holding its value."""
    return FIELD_ALIASES.get(str(name).strip().lower(), str(name).strip())


@dataclass(frozen=True)
class TableColumn:
    """One resolved table column."""

    field: str  # as authored in the theme
    attr: str  # resolved row attribute holding the value
    header: str
    width: float  # fraction of the table width; sums to 1.0
    align: str = "left"  # left | center | right
    max_lines: int = 1
    truncate: bool = True
    render: str = "text"  # text | icon
    icon: str | None = None
    value_format: str | None = None  # str.format spec, e.g. "{:.0%}"
    date_format: str | None = None  # Arrow format, `dd` supported
    indent: bool = False  # WBS depth shifts this column's text
    max_chars: int | None = None  # text outputs only: ellipsize past this


def resolve_table_columns(entries: Iterable[Any] | None, config: CalendarConfig) -> list[TableColumn]:
    """Build a column list from theme-authored *entries*.

    Entries without a ``field`` are dropped -- a theme typo costs one
    column, not the page.  Widths are renormalized to sum to 1.0 so a
    theme can write whatever scale it finds readable (fractions, points,
    percentages); a column with no usable width shares what is left
    evenly with its peers.
    """
    parsed: list[TableColumn] = []
    for entry in list(entries or []):
        if not isinstance(entry, dict):
            continue
        field = str(entry.get("field") or "").strip()
        if not field:
            continue

        render = str(entry.get("render") or "text").strip().lower()
        icon = entry.get("icon")
        if render == "icon" and not icon:
            icon_field = _DEFAULT_FIELD_ICONS.get(field)
            icon = getattr(config, icon_field, None) if icon_field else None

        parsed.append(
            TableColumn(
                field=field,
                attr=resolve_field(field),
                header=str(entry.get("header") or field),
                width=_positive_float(entry.get("width")),
                align=str(entry.get("align") or "left").strip().lower(),
                max_lines=max(1, int(entry.get("max_lines") or 1)),
                truncate=bool(entry.get("truncate", True)),
                render="icon" if render == "icon" else "text",
                icon=str(icon) if icon else None,
                value_format=entry.get("format"),
                date_format=entry.get("date_format"),
                indent=bool(entry.get("indent", False)),
                max_chars=_positive_int(entry.get("max_chars")),
            )
        )

    return _normalize_widths(parsed)


def _positive_float(value: Any) -> float:
    """A column width, or 0.0 when absent or unusable."""
    try:
        width = float(value)
    except (TypeError, ValueError):
        return 0.0
    return width if width > 0 else 0.0


def _positive_int(value: Any) -> int | None:
    """A positive integer limit, or None when absent or unusable."""
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _normalize_widths(columns: list[TableColumn]) -> list[TableColumn]:
    """Rescale widths to sum to 1.0, sharing the remainder with unsized columns."""
    if not columns:
        return columns

    sized = [c for c in columns if c.width > 0]
    unsized_count = len(columns) - len(sized)

    if not sized:
        even = 1.0 / len(columns)
        return [replace(c, width=even) for c in columns]

    total = sum(c.width for c in sized)
    if unsized_count:
        # Give the unsized columns the average of the sized ones, then
        # rescale everything together.
        average = total / len(sized)
        columns = [c if c.width > 0 else replace(c, width=average) for c in columns]
        total += average * unsized_count

    return [replace(c, width=c.width / total) for c in columns]


def cell_value(column: TableColumn, row: Any) -> str:
    """Render one cell's value as display text.

    Icon columns return ``""`` -- the output draws their glyph -- so a
    caller that only wants text does not have to special-case them.
    """
    if column.render == "icon":
        return ""

    value = getattr(row, column.attr, None)
    if value is None or value == "":
        return ""

    if column.date_format:
        return _format_date(value, column.date_format)

    if column.value_format:
        try:
            return column.value_format.format(value)
        except (ValueError, KeyError, IndexError, TypeError):
            # A format spec that does not fit the value costs the
            # formatting, not the cell.
            return str(value)

    if isinstance(value, bool):
        return "Yes" if value else ""

    return str(value)


def cell_icon_visible(column: TableColumn, row: Any) -> bool:
    """True when an icon column should draw its glyph for this row.

    The reference column is never driven from the row — its icons come
    from the chart's link graph — so it always answers False here.
    """
    if column.render != "icon" or not column.icon:
        return False
    if column.field == LINK_REF_FIELD:
        return False
    return bool(getattr(row, column.attr, None))


def _format_date(value: Any, fmt: str) -> str:
    """Format a ``YYYYMMDD`` value, passing anything unparseable through."""
    text = str(value).strip()
    if not text:
        return ""
    try:
        return format_arrow_date(arrow.get(text[:8], "YYYYMMDD"), fmt)
    except (ValueError, arrow.parser.ParserError):
        return text
