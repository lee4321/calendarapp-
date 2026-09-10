"""
Companion details page: a paginating writer for tabular listings.

Every SVG visualization that writes a second document beside its chart --
the gantt details page, the weekly overflow report, the mini/candybar
event listing -- writes it through this module, so the three are one page
with three sets of content.  The shape is: page chrome, a title, then
sections of a heading plus a banded table, continued onto as many pages
as the rows need.

The writer borrows its host renderer's drawing helpers and swaps the
renderer's ``_drawing`` for each page.  The caller restores whatever was
there before -- ``finish()`` leaves the last details page in it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable, Sequence

from renderers.text_utils import fit_lines

if TYPE_CHECKING:
    from config.config import CalendarConfig
    from visualizers.base import CoordinateDict

#: Vertical breathing room between a section heading and its table.
_SECTION_GAP = 8.0

#: Horizontal padding inside a details cell, in points.
_CELL_PAD = 3.0


@dataclass(frozen=True)
class DetailsColumn:
    """One column of a details table.

    Attributes:
        heading: The column-header text.
        width: Share of the table width; a section's widths sum to 1.0.
        align: ``left`` | ``center`` | ``right`` within the cell.
        css_class: Class on the cell's text, for external CSS.
        token: ``text:`` token supplying the cell's color and opacity.
            ``None`` takes the page's body color, which is what a column
            with nothing particular to say wants.
        fallback_color: Color when the token supplies none -- a legacy
            config field, for a theme predating the token.
        fallback_opacity: Opacity on the same terms.
    """

    heading: str
    width: float
    align: str = "left"
    css_class: str = "ec-task-cell"
    token: str | None = None
    fallback_color: str | None = None
    fallback_opacity: float | None = None


def as_columns(specs: Sequence) -> list[DetailsColumn]:
    """Normalize a caller's column list into :class:`DetailsColumn` values.

    A caller may pass the full description or the ``(heading, width)``
    pair that covers the common case.
    """
    columns: list[DetailsColumn] = []
    for spec in specs:
        if isinstance(spec, DetailsColumn):
            columns.append(spec)
        else:
            heading, width = spec
            columns.append(DetailsColumn(str(heading), float(width)))
    return columns


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


def numbered_page_path(base: str, number: int) -> str:
    """``chart_details.svg`` → itself, then ``chart_details_p2.svg``."""
    if number == 1:
        return base
    return f"{base[:-4]}_p{number}.svg"


class DetailsPageWriter:
    """Flows details content down the page, breaking into new pages."""

    def __init__(
        self,
        renderer,
        config: "CalendarConfig",
        coordinates: "CoordinateDict",
        page_path: Callable[[int], str],
        title_text: str,
    ):
        self._renderer = renderer
        self._config = config
        self._coordinates = coordinates
        self._page_path = page_path
        self._title_text = title_text
        self._page_number = 0
        self._cursor = 0.0
        self._top_ink = 0.0
        self._row_index = 0
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

        # Resolved here rather than read from the renderer's token cache:
        # a details page is written by whichever renderer hosts it, and
        # only some of them list these tokens in TOKENS.  The ctx carries
        # the host's own visualizer so a theme's per-view overrides still
        # apply, and the global text:heading / text:label / text:body
        # definitions answer for everyone else.
        self._ctx = {
            "visualizer": getattr(renderer, "TOKEN_VISUALIZER", None),
            "papersize": config.papersize,
        }
        heading = self._token("text:heading")
        label = self._token("text:label")
        # text:details_body carries this page's own size (setfontsizes
        # scales it with the paper); everything else comes from text:body,
        # so a theme that restyles body text restyles the listing too.
        body = {**self._token("text:body"), **self._token("text:details_body")}
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

        # The optional second line under a row's main cell, e.g. an
        # event's notes beneath its name.
        notes = self._token("text:event_notes")
        self._note_font = notes.get("font") or self._body_font
        self._note_size = float(notes.get("size") or self._body_size * 0.9)
        self._note_color = notes.get("color") or self._body_color
        self._note_opacity = notes.get("opacity")

        self._separator_dash = config.get_line_style("ec-separator").dasharray or None
        # Banding is themed through the same element class the gantt
        # chart's own task table bands with, so the chart and its listing
        # stripe alike.  A theme turns it off by painting it none.
        band = config.get_box_style("ec-row-band")
        self._band_color = band.fill or "none"
        self._band_opacity = float(
            band.fill_opacity if band.fill_opacity is not None else 0.15
        )
        self._band_on = str(self._band_color).strip().lower() not in {
            "", "none", "transparent",
        }

    def _token(self, name: str) -> dict:
        return self._renderer._resolve_token(self._config, name, self._ctx)

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
        self._paint_background()
        if config.watermark_text:
            renderer._render_text_watermark(config)
        if config.watermark_image:
            renderer._render_image_watermark(config)
        renderer._render_decorations(config, self._coordinates, day_names=False)

        self._cursor = self.top + self._title_size + 4.0
        self._top_ink = self._cursor - self._title_size
        renderer._draw_text(
            self.left + self.width / 2,
            self._cursor,
            self._title_text,
            self._title_font,
            self._title_size,
            fill=self._title_color,
            anchor="middle",
            css_class="ec-heading",
        )
        self._cursor += self._title_size + _SECTION_GAP

        # Every page opens on an unbanded row, so a break mid-table does
        # not shift the stripe onto the other foot.
        self._row_index = 0
        if self._repeat is not None:
            self._repeat()

    def finish(self) -> int:
        """Write the last page; returns how many pages were produced."""
        if self._page_number:
            self._save_page()
        return self._pages_written

    def _save_page(self) -> None:
        if self._config.shrink_to_content:
            self._renderer._shrink_drawing_to_content(
                {
                    "DetailsContent": (
                        self.left,
                        self._top_ink,
                        self.width,
                        max(0.0, self._cursor - self._top_ink),
                    )
                }
            )
        self._renderer._drawing.save_svg(self._page_path(self._page_number))
        self._pages_written += 1

    # ── Content ───────────────────────────────────────────────────────────

    def section(self, title: str, columns: Sequence) -> list[DetailsColumn]:
        """Start a section: a heading plus a repeating column-header row.

        Returns the normalized columns, so a caller that passed
        ``(heading, width)`` pairs can hand the same value back to
        :meth:`row` without converting them twice.
        """
        resolved = as_columns(columns)

        def repeat() -> None:
            self._heading(title)
            self._header_row(resolved)

        # Cleared first so a page break *here* does not replay the section
        # that is ending, and so starting the first page does not draw
        # this section's own heading twice.
        self._repeat = None
        self._ensure(self._row_height * 3)
        repeat()
        self._repeat = repeat
        self._row_index = 0
        return resolved

    def row(
        self,
        cells: Sequence[str],
        columns: Sequence,
        sub_line: tuple[int, str] | None = None,
    ) -> None:
        """Draw one data row, breaking to a new page when out of space.

        ``sub_line`` is an optional ``(column index, text)`` second line
        drawn in the notes style beneath that column, which is how an
        event carries its notes under its name.  The row grows to hold
        it, so the band still covers the whole entry.
        """
        resolved = as_columns(columns)
        has_note = sub_line is not None and bool(sub_line[1])
        height = self._row_height + (self._note_size + 2.0 if has_note else 0.0)
        self._ensure(height)
        self._band(height)
        self._cells(resolved, cells)

        if has_note:
            index, text = sub_line
            if 0 <= index < len(resolved):
                x, cell_w = self._cell_x(resolved, index)
                self._renderer._draw_text(
                    x + _CELL_PAD,
                    self._cursor + self._note_size + 2.0,
                    text,
                    self._note_font,
                    self._note_size,
                    fill=self._note_color,
                    fill_opacity=(
                        1.0 if self._note_opacity is None else self._note_opacity
                    ),
                    max_width=cell_w - _CELL_PAD * 2,
                    css_class="ec-event-notes",
                )

        self._cursor += height
        self._row_index += 1

    def note(self, text: str) -> None:
        """A single free-standing line, e.g. "No exceptions"."""
        self._ensure(self._row_height)
        self._renderer._draw_text(
            self.left + _CELL_PAD, self._cursor, text,
            self._body_font, self._body_size,
            fill=self._body_color, css_class="ec-task-cell",
        )
        self._cursor += self._row_height
        self._row_index += 1

    # ── Internals ─────────────────────────────────────────────────────────

    def _ensure(self, needed: float) -> None:
        """Break to a new page when *needed* points will not fit."""
        if self._page_number == 0:
            self.start_page()
        elif self._cursor + needed > self.bottom:
            self.start_page()

    def _paint_background(self) -> None:
        """Lay the theme's page ground down first.

        A dark theme's listing is light text, and the banding is a tint
        meant to sit on that ground; drawn on nothing, both land on white
        and the page cannot be read.  Follows the same ``ec-background``
        convention the timeline and blockplan pages already use.
        """
        style = self._config.get_box_style("ec-background")
        fill = str(style.fill or "").strip().lower()
        if fill in {"", "none", "transparent"}:
            return
        self._renderer._draw_rect(
            0, 0,
            round(self._config.pageX, 2),
            round(self._config.pageY, 2),
            fill=style.fill,
            css_class="ec-background",
        )

    def _band(self, height: float) -> None:
        """Tint every other row, so a wide row is read across, not down."""
        if not self._band_on or self._row_index % 2 == 0:
            return
        self._renderer._draw_rect(
            self.left,
            self._cursor - self._body_size,
            self.width,
            height,
            fill=self._band_color,
            fill_opacity=self._band_opacity,
            css_class="ec-row-band",
        )

    def _heading(self, title: str) -> None:
        self._renderer._draw_text(
            self.left, self._cursor, title, self._label_font,
            self._label_size * 1.2, fill=self._title_color,
            css_class="ec-heading",
        )
        self._cursor += self._label_size * 1.2 + 2.0

    def _header_row(self, columns: list[DetailsColumn]) -> None:
        self._cells(
            columns,
            [column.heading for column in columns],
            font=self._label_font,
            size=self._label_size,
            color=self._label_color,
            css_class="ec-column-header",
        )
        self._cursor += self._label_size + 2.0
        self._renderer._draw_line(
            self.left, self._cursor, self.right, self._cursor,
            stroke="grey", stroke_opacity=0.5,
            stroke_dasharray=self._separator_dash,
            css_class="ec-separator",
        )
        # Text grows upward from its baseline, so clear a full line height
        # or the first row's glyphs sit on the rule.
        self._cursor += self._body_size + 2.0

    def _cell_x(
        self, columns: list[DetailsColumn], index: int
    ) -> tuple[float, float]:
        """Left edge and width of one column, in page units."""
        cursor_x = self.left
        for column in columns[:index]:
            cursor_x += self.width * column.width
        return cursor_x, self.width * columns[index].width

    def _cells(
        self,
        columns: list[DetailsColumn],
        values: Sequence[str],
        font: str | None = None,
        size: float | None = None,
        color: str | None = None,
        css_class: str | None = None,
    ) -> None:
        """Draw one row of cells, each clipped and aligned to its column."""
        font = font or self._body_font
        size = self._body_size if size is None else size
        cursor_x = self.left
        for value, column in zip(values, columns):
            cell_w = self.width * column.width
            usable = cell_w - _CELL_PAD * 2
            # One line per cell: the row height is uniform, so a value
            # that wants two is truncated with an ellipsis rather than
            # written over the row below it.
            lines = fit_lines(
                str(value or ""), usable, 1,
                lambda text: self._renderer._measure(text, font, size),
            )
            if lines:
                style = self._token(column.token) if column.token else {}
                opacity = style.get("opacity")
                if opacity is None:
                    opacity = column.fallback_opacity
                x, anchor = self._align(cursor_x, cell_w, column.align)
                self._renderer._draw_text(
                    x, self._cursor, lines[0], font, size,
                    fill=(
                        color
                        or style.get("color")
                        or column.fallback_color
                        or self._body_color
                    ),
                    fill_opacity=1.0 if opacity is None else opacity,
                    anchor=anchor,
                    max_width=usable,
                    css_class=css_class or column.css_class,
                )
            cursor_x += cell_w

    @staticmethod
    def _align(cell_x: float, cell_w: float, align: str) -> tuple[float, str]:
        """Anchor point and SVG text-anchor for one cell's alignment."""
        if align == "right":
            return cell_x + cell_w - _CELL_PAD, "end"
        if align == "center":
            return cell_x + cell_w / 2, "middle"
        return cell_x + _CELL_PAD, "start"
