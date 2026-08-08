"""
Gantt companion details page.

Written next to the chart as ``<output>_details.svg``, following the
format of the other details pages (see
``visualizers/mini/renderer.py::_render_details_svg``): its own document,
the same page chrome, a title, then tables.

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
from typing import TYPE_CHECKING, Callable

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

#: Vertical breathing room between a section heading and its table.
_SECTION_GAP = 8.0

#: Narrowest share of the page any details column may take.  The chart's
#: table can afford 2%-wide icon columns because it draws a glyph; here
#: the same column has to fit a word, so the widths are re-floored.
_MIN_COLUMN_WIDTH = 0.04

#: Horizontal padding inside a details cell, in points.
_CELL_PAD = 3.0


def format_datekey(datekey: str) -> str:
    """``20260202`` → ``2026-02-02``; anything else passes through."""
    text = str(datekey or "").strip()
    if len(text) == 8 and text.isdigit():
        return f"{text[:4]}-{text[4:6]}-{text[6:8]}"
    return text


def details_output_path(output_path: str, suffix: str) -> str:
    """``chart.svg`` → ``chart_details.svg``."""
    if output_path.lower().endswith(".svg"):
        return f"{output_path[:-4]}{suffix}.svg"
    return f"{output_path}{suffix}.svg"


class DetailsPageWriter:
    """Flows the details content down the page, breaking into new pages.

    The writer borrows the renderer's drawing helpers and swaps its
    ``_drawing`` for each page, exactly as the mini details page does.
    The caller restores the chart's drawing afterwards.
    """

    def __init__(
        self,
        renderer,
        config: "CalendarConfig",
        coordinates: "CoordinateDict",
        page_path: Callable[[int], str],
    ):
        self._renderer = renderer
        self._config = config
        self._coordinates = coordinates
        self._page_path = page_path
        self._page_number = 0
        self._cursor = 0.0
        self._pages_written = 0
        self._repeat: Callable[[], None] | None = None

        from config.config import resolve_page_margins

        margins = resolve_page_margins(config)
        header_h = (
            round(config.pageY * config.header_percent, 2)
            if config.include_header
            else 0.0
        )
        footer_h = (
            round(config.pageY * config.footer_percent, 2)
            if config.include_footer
            else 0.0
        )
        self.left = margins["left"]
        self.right = config.pageX - margins["right"]
        self.width = self.right - self.left
        self.top = margins["top"] + header_h
        self.bottom = config.pageY - margins["bottom"] - footer_h

        heading = renderer._tk("text:heading")
        label = renderer._tk("text:label")
        body = renderer._tk("text:body")
        self._title_font = heading.get("font") or config.get_text_style(
            "ec-heading"
        ).font
        self._title_size = float(heading.get("size") or 12.0)
        self._title_color = heading.get("color") or "black"
        self._label_font = label.get("font") or self._title_font
        self._label_size = float(label.get("size") or 8.0)
        self._label_color = label.get("color") or "black"
        self._body_font = body.get("font") or self._title_font
        self._body_size = float(body.get("size") or 8.0)
        self._body_color = body.get("color") or "black"
        self._row_height = self._body_size + 4.0

    # ── Page lifecycle ────────────────────────────────────────────────────

    def start_page(self) -> None:
        """Begin a new details page: fresh drawing, chrome, and title."""
        renderer, config = self._renderer, self._config

        if self._page_number:
            self._save_page()

        self._page_number += 1
        renderer._drawing = renderer._create_drawing(config)
        renderer._content_bbox_svg = None
        renderer._add_desc(config)
        renderer._inject_css()
        if config.watermark_text:
            renderer._render_text_watermark(config)
        if config.watermark_image:
            renderer._render_image_watermark(config)
        renderer._render_decorations(config, self._coordinates)

        self._cursor = self.top + self._title_size + 4.0
        renderer._draw_text(
            self.left + self.width / 2,
            self._cursor,
            config.gantt_details_title_text,
            self._title_font,
            self._title_size,
            fill=self._title_color,
            anchor="middle",
            css_class="ec-heading",
        )
        self._cursor += self._title_size + _SECTION_GAP

        if self._repeat is not None:
            self._repeat()

    def finish(self) -> int:
        """Write the last page; returns how many pages were produced."""
        if self._page_number:
            self._save_page()
        return self._pages_written

    def _save_page(self) -> None:
        self._renderer._drawing.save_svg(self._page_path(self._page_number))
        self._pages_written += 1

    # ── Content ───────────────────────────────────────────────────────────

    def section(self, title: str, columns: list[tuple[str, float]]) -> None:
        """Start a section: a heading plus a repeating column-header row."""

        def repeat() -> None:
            self._heading(title)
            self._header_row(columns)

        # Cleared first so a page break *here* does not replay the section
        # that is ending, and so starting the first page does not draw
        # this section's own heading twice.
        self._repeat = None
        self._ensure(self._row_height * 3)
        repeat()
        self._repeat = repeat

    def row(self, cells: list[str], columns: list[tuple[str, float]]) -> None:
        """Draw one data row, breaking to a new page when out of space."""
        self._ensure(self._row_height)
        self._cells(cells, columns, self._body_font, self._body_size, self._body_color)
        self._cursor += self._row_height

    def note(self, text: str) -> None:
        """A single free-standing line, e.g. "No exceptions"."""
        self._ensure(self._row_height)
        self._renderer._draw_text(
            self.left + _CELL_PAD, self._cursor, text,
            self._body_font, self._body_size,
            fill=self._body_color, css_class="ec-task-cell",
        )
        self._cursor += self._row_height

    # ── Internals ─────────────────────────────────────────────────────────

    def _ensure(self, needed: float) -> None:
        """Break to a new page when *needed* points will not fit."""
        if self._page_number == 0:
            self.start_page()
        elif self._cursor + needed > self.bottom:
            self.start_page()

    def _heading(self, title: str) -> None:
        self._renderer._draw_text(
            self.left, self._cursor, title, self._label_font,
            self._label_size * 1.2, fill=self._title_color,
            css_class="ec-heading",
        )
        self._cursor += self._label_size * 1.2 + 2.0

    def _header_row(self, columns: list[tuple[str, float]]) -> None:
        self._cells(
            [heading for heading, _w in columns], columns,
            self._label_font, self._label_size, self._label_color,
            css_class="ec-column-header",
        )
        self._cursor += self._label_size + 2.0
        self._renderer._draw_line(
            self.left, self._cursor, self.right, self._cursor,
            stroke="grey", stroke_opacity=0.5, css_class="ec-separator",
        )
        # Text grows upward from its baseline, so clear a full line height
        # or the first row's glyphs sit on the rule.
        self._cursor += self._body_size + 2.0

    def _cells(
        self,
        values: list[str],
        columns: list[tuple[str, float]],
        font: str,
        size: float,
        color: str,
        css_class: str = "ec-task-cell",
    ) -> None:
        """Draw one row of cells, each clipped to its column."""
        from visualizers.gantt.columns import fit_lines

        cursor_x = self.left
        for value, (_heading, fraction) in zip(values, columns):
            cell_w = self.width * fraction
            usable = cell_w - _CELL_PAD * 2
            lines = fit_lines(
                str(value or ""), usable, 1,
                lambda text: self._renderer._measure(text, font, size),
            )
            if lines:
                self._renderer._draw_text(
                    cursor_x + _CELL_PAD, self._cursor, lines[0], font, size,
                    fill=color, max_width=usable, css_class=css_class,
                )
            cursor_x += cell_w


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
        if number == 1:
            return base
        return f"{base[:-4]}_p{number}.svg"

    writer = DetailsPageWriter(renderer, config, coordinates, page_path)

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
