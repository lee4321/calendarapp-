"""
Gantt task-table column model.

Columns are *layout* configuration, not style: which fields appear, in
what order, how wide, how aligned, and how a value becomes text.  They
come from ``config.gantt_columns`` (themes write ``gantt.columns:``);
``style_rules`` govern only how the resulting cells look.

The value pipeline is one pass per cell:

    event field → :func:`cell_value` (format / date_format / icon)
                → :func:`fit_lines`  (wrap to the column width, then
                                      truncate with an ellipsis)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable

import arrow

from shared.date_utils import format_arrow_date

if TYPE_CHECKING:
    from config.config import CalendarConfig
    from shared.data_models import Event

#: Appended to the last line when a value does not fit its column.
ELLIPSIS = "…"

#: Synthetic column: cross-page dependency reference icons.  It has no
#: `events` field behind it — the renderer supplies the icons per row from
#: the link graph, so `cell_value` and `cell_icon_visible` stay out of it.
LINK_REF_FIELD = "link_ref"

#: Fields rendered as an icon when the value is truthy and the column
#: asks for ``render: icon`` without naming one.
_DEFAULT_FIELD_ICONS: dict[str, str] = {
    "rollup": "gantt_rollup_icon",
    "milestone": "gantt_milestone_flag_icon",
}

#: Themes name fields after the `events` **table**, which is the
#: vocabulary the requirements use -- in ``gantt.columns`` and in
#: ``gantt.sort`` alike.  ``Event`` normalizes a few of those to shorter
#: attribute names, so map the spellings a user would write onto the
#: attribute that actually holds the value.  Anything absent here is used
#: as-is, which covers the majority of fields.
FIELD_ALIASES: dict[str, str] = {
    "name": "task_name",
    "task": "task_name",
    "start_date": "start",
    "finish": "end",
    "finish_date": "end",
    "end_date": "end",
}


def resolve_field(name: str) -> str:
    """Map a theme-authored field name onto its ``Event`` attribute."""
    return FIELD_ALIASES.get(str(name).strip().lower(), str(name).strip())


@dataclass(frozen=True)
class GanttColumn:
    """One resolved task-table column."""

    field: str                      # as authored in the theme
    attr: str                       # resolved Event attribute holding the value
    header: str
    width: float                    # fraction of the table width; sums to 1.0
    align: str = "left"             # left | center | right
    max_lines: int = 1
    truncate: bool = True
    render: str = "text"            # text | icon
    icon: str | None = None
    value_format: str | None = None  # str.format spec, e.g. "{:.0%}"
    date_format: str | None = None   # Arrow format, `dd` supported
    indent: bool = False             # WBS depth shifts this column's text


def resolve_columns(config: "CalendarConfig") -> list[GanttColumn]:
    """Build the column list from ``config.gantt_columns``.

    Entries without a ``field`` are dropped -- a theme typo costs one
    column, not the page.  Widths are renormalized to sum to 1.0 so a
    theme can write whatever scale it finds readable (fractions, points,
    percentages); a column with no usable width shares what is left
    evenly with its peers.
    """
    raw_entries = list(getattr(config, "gantt_columns", None) or [])

    parsed: list[GanttColumn] = []
    for entry in raw_entries:
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
            GanttColumn(
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


def _normalize_widths(columns: list[GanttColumn]) -> list[GanttColumn]:
    """Rescale widths to sum to 1.0, sharing the remainder with unsized columns."""
    if not columns:
        return columns

    sized = [c for c in columns if c.width > 0]
    unsized_count = len(columns) - len(sized)

    if not sized:
        even = 1.0 / len(columns)
        return [_with_width(c, even) for c in columns]

    total = sum(c.width for c in sized)
    if unsized_count:
        # Give the unsized columns the average of the sized ones, then
        # rescale everything together.
        average = total / len(sized)
        columns = [c if c.width > 0 else _with_width(c, average) for c in columns]
        total += average * unsized_count

    return [_with_width(c, c.width / total) for c in columns]


def _with_width(column: GanttColumn, width: float) -> GanttColumn:
    return GanttColumn(
        field=column.field,
        attr=column.attr,
        header=column.header,
        width=width,
        align=column.align,
        max_lines=column.max_lines,
        truncate=column.truncate,
        render=column.render,
        icon=column.icon,
        value_format=column.value_format,
        date_format=column.date_format,
        indent=column.indent,
    )


def column_x_positions(
    columns: list[GanttColumn], table_x: float, table_w: float
) -> list[tuple[float, float]]:
    """Return ``(x, width)`` in page units for each column, left to right."""
    positions: list[tuple[float, float]] = []
    cursor = table_x
    for column in columns:
        width = table_w * column.width
        positions.append((cursor, width))
        cursor += width
    return positions


def cell_value(column: GanttColumn, event: "Event") -> str:
    """Render one cell's value as display text.

    Icon columns return ``""`` -- the renderer draws their glyph -- so a
    caller that only wants text does not have to special-case them.
    """
    if column.render == "icon":
        return ""

    value = getattr(event, column.attr, None)
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


def cell_icon_visible(column: GanttColumn, event: "Event") -> bool:
    """True when an icon column should draw its glyph for this row.

    The reference column is never driven from the event — its icons come
    from the chart's link graph — so it always answers False here.
    """
    if column.render != "icon" or not column.icon:
        return False
    if column.field == LINK_REF_FIELD:
        return False
    return bool(getattr(event, column.attr, None))


def _format_date(value: Any, fmt: str) -> str:
    """Format a ``YYYYMMDD`` value, passing anything unparseable through."""
    text = str(value).strip()
    if not text:
        return ""
    try:
        return format_arrow_date(arrow.get(text, "YYYYMMDD"), fmt)
    except (ValueError, arrow.parser.ParserError):
        return text


def fit_lines(
    text: str,
    width: float,
    max_lines: int,
    measure: Callable[[str], float],
) -> list[str]:
    """Wrap *text* to *width*, capped at *max_lines* with an ellipsis.

    Wrapping is word-based; a single word wider than the column is broken
    mid-word rather than allowed to overflow.  The returned list is never
    longer than *max_lines*, so row height stays uniform (answer 9).

    Args:
        text: The already-formatted cell value.
        width: Usable width in the same units *measure* returns.
        max_lines: Hard cap on returned lines.
        measure: Width of a candidate string, e.g. a bound
            :func:`renderers.text_utils.string_width`.

    Returns:
        The lines to draw, or ``[]`` for empty input.
    """
    text = (text or "").strip()
    if not text or width <= 0 or max_lines <= 0:
        return []

    lines: list[str] = []
    remaining_words = text.split()

    while remaining_words and len(lines) < max_lines:
        is_last_line = len(lines) == max_lines - 1
        line, remaining_words = _take_line(remaining_words, width, measure)

        if is_last_line and remaining_words:
            line = _with_ellipsis(line, width, measure)

        lines.append(line)

    return lines


def _take_line(
    words: list[str], width: float, measure: Callable[[str], float]
) -> tuple[str, list[str]]:
    """Pack as many words as fit; returns the line and what is left over."""
    line = ""
    index = 0
    for index, word in enumerate(words):
        candidate = f"{line} {word}".strip()
        if measure(candidate) <= width:
            line = candidate
            continue
        if not line:
            # First word does not fit on its own — break it mid-word so a
            # long unbroken token cannot overflow the column.
            head, tail = _split_to_fit(word, width, measure)
            return head, ([tail] if tail else []) + words[index + 1:]
        return line, words[index:]
    return line, []


def _split_to_fit(
    word: str, width: float, measure: Callable[[str], float]
) -> tuple[str, str]:
    """Split *word* at the last character that still fits."""
    for cut in range(len(word) - 1, 0, -1):
        if measure(word[:cut]) <= width:
            return word[:cut], word[cut:]
    return word[:1], word[1:]


def _with_ellipsis(
    line: str, width: float, measure: Callable[[str], float]
) -> str:
    """Append the ellipsis, dropping characters until it fits."""
    candidate = line.rstrip()
    while candidate and measure(candidate + ELLIPSIS) > width:
        candidate = candidate[:-1].rstrip()
    return (candidate + ELLIPSIS) if candidate else ELLIPSIS
