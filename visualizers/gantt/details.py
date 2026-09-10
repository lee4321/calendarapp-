"""
Gantt companion details page.

Written next to the chart as ``<output>_details.svg`` through the
shared :mod:`renderers.details_page` writer, which is also what the
weekly overflow report is built on: its own document, the same page
chrome, a title, then tables.  What lives here is the gantt's own
content -- the exception vocabulary and the column model.

Two sections:

1. **Tasks** -- every row in chart order, through the same column model
   the chart's table uses.
2. **Exceptions** -- one line per thing the chart could not show
   faithfully.  Several requirements accept that the chart cannot always
   be faithful (a bar clipped at the range edge, an event moved off a
   hidden weekend, a dependency pointing off-chart) and ask for the
   compromise to be reported rather than hidden.  Because the log is the
   whole point, it paginates rather than truncating: entries that do not
   fit continue on ``_details_p2.svg``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from renderers.details_page import (
    DetailsPageWriter,
    details_output_path,
    format_datekey,
    numbered_page_path,
)

if TYPE_CHECKING:
    from config.config import CalendarConfig
    from visualizers.base import CoordinateDict
    from visualizers.gantt.columns import GanttColumn

#: A duration bar reaching past the chart's last day (answer 16).
KIND_CLIPPED_END = "clipped_end"

#: A duration bar beginning before the chart's first day (answer 16).
KIND_CLIPPED_START = "clipped_start"

#: A single-day event drawn on the next working day because its own day
#: is not on the axis (answer 22).
KIND_SNAPPED_EVENT = "snapped_event"

#: A holiday that cannot be shaded because it falls on a hidden weekend
#: (answer 14).
KIND_HIDDEN_HOLIDAY = "hidden_holiday"

#: A task whose whole span is hidden, so nothing is drawn for it.
KIND_UNDRAWN = "undrawn"

#: A dependency whose predecessor is not on the chart (answer 27).
KIND_OFFCHART_DEPENDENCY = "offchart_dependency"

#: A predecessor token that could not be parsed at all.
KIND_UNPARSEABLE_PREDECESSOR = "unparseable_predecessor"

#: A predecessor referencing a source_id no task carries.
KIND_UNRESOLVED_PREDECESSOR = "unresolved_predecessor"

#: Human-readable summaries, keyed by kind.
KIND_LABELS: dict[str, str] = {
    KIND_CLIPPED_END: "Bar continues past the end of the range",
    KIND_CLIPPED_START: "Bar begins before the start of the range",
    KIND_SNAPPED_EVENT: "Moved to the next working day",
    KIND_HIDDEN_HOLIDAY: "Holiday hidden with its weekend",
    KIND_UNDRAWN: "Not drawn — every day of the span is hidden",
    KIND_OFFCHART_DEPENDENCY: "Predecessor is not on the chart",
    KIND_UNPARSEABLE_PREDECESSOR: "Predecessor could not be parsed",
    KIND_UNRESOLVED_PREDECESSOR: "Predecessor does not match any task",
}


@dataclass(frozen=True)
class GanttException:
    """One thing the chart could not show faithfully.

    Attributes:
        kind: One of the ``KIND_*`` constants above.
        task: The task name the entry belongs to.
        datekey: ``YYYYMMDD`` the entry concerns, or ``""``.
        detail: Extra context, e.g. the date a bar was clipped to.
    """

    kind: str
    task: str
    datekey: str = ""
    detail: str = ""

    @property
    def label(self) -> str:
        """The human-readable summary for this entry's kind."""
        return KIND_LABELS.get(self.kind, self.kind)


#: Columns of the exception table, as ``(heading, width fraction)``.
_EXCEPTION_COLUMNS: tuple[tuple[str, float], ...] = (
    ("Task", 0.26),
    ("Date", 0.11),
    ("Ref", 0.08),
    ("Issue", 0.25),
    ("Detail", 0.30),
)

#: Shown in the Ref column when an entry carries no cross-page number.
_NO_REF = "—"

#: Narrowest share of the page any details column may take.  The chart's
#: table can afford 2%-wide icon columns because it draws a glyph; here
#: the same column has to fit a word, so the widths are re-floored.
_MIN_COLUMN_WIDTH = 0.04


def _split_reference(detail: str) -> tuple[str, str]:
    """Pull a leading ``"<icon>: "`` tag out of an exception's detail.

    Cross-page dependency entries are recorded as ``"circle-7: depends on
    …"`` so the number and the prose can be shown in their own columns
    without a second field on every exception.
    """
    text = str(detail or "")
    icon, separator, rest = text.partition(": ")
    if separator and " " not in icon:
        return icon, rest
    return "", text


def _details_columns(
    columns: list["GanttColumn"],
) -> list[tuple[str, float]]:
    """Column headings and widths for the details listing.

    Chart widths are reused for proportion, but floored so a column that
    only ever holds a glyph on the chart can still hold a word here, then
    renormalized so the row still spans the page exactly once.
    """
    if not columns:
        return []
    widths = [max(column.width, _MIN_COLUMN_WIDTH) for column in columns]
    total = sum(widths)
    return [
        (column.header, width / total)
        for column, width in zip(columns, widths)
    ]


def render_details_pages(
    renderer,
    config: "CalendarConfig",
    coordinates: "CoordinateDict",
    rows: list,
    columns: list["GanttColumn"],
    exceptions: list[GanttException],
) -> int:
    """Draw the companion details page(s); returns how many were written.

    The caller is responsible for restoring ``renderer._drawing`` -- this
    leaves the last details page in it.
    """
    from visualizers.gantt.columns import cell_icon_visible, cell_value

    def text_for(column, event) -> str:
        """Icon columns have no glyph here, so state the value in words."""
        if column.render == "icon":
            return "Yes" if cell_icon_visible(column, event) else ""
        return cell_value(column, event)

    def page_path(number: int) -> str:
        base = details_output_path(
            config.outputfile, config.gantt_details_output_suffix
        )
        return numbered_page_path(base, number)

    writer = DetailsPageWriter(
        renderer, config, coordinates, page_path,
        config.gantt_details_title_text,
    )

    task_columns = _details_columns(columns)
    if task_columns:
        writer.section("Tasks", task_columns)
        for row in rows:
            writer.row(
                [text_for(column, row.event) for column in columns], task_columns,
            )

    writer.section("Exceptions", list(_EXCEPTION_COLUMNS))
    if exceptions:
        for entry in exceptions:
            reference, detail = _split_reference(entry.detail)
            writer.row(
                [
                    entry.task,
                    format_datekey(entry.datekey),
                    reference or _NO_REF,
                    entry.label,
                    detail,
                ],
                list(_EXCEPTION_COLUMNS),
            )
    else:
        writer.note("Every item was drawn as scheduled.")

    return writer.finish()
