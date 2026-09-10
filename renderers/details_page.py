"""
Companion details page: a paginating writer for tabular listings.

Several views write a second document next to their chart -- the gantt
details page, the weekly overflow report -- with the same shape: page
chrome, a title, then sections of a heading plus a table.  This module
owns that shape so those pages stay identical to each other, and so the
one that runs long breaks onto ``_p2`` rather than dropping rows.

The writer borrows its host renderer's drawing helpers and swaps the
renderer's ``_drawing`` for each page.  The caller restores whatever was
there before -- ``finish()`` leaves the last details page in it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable

from renderers.text_utils import fit_lines

if TYPE_CHECKING:
    from config.config import CalendarConfig
    from visualizers.base import CoordinateDict

#: Vertical breathing room between a section heading and its table.
_SECTION_GAP = 8.0

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
        ctx = {
            "visualizer": getattr(renderer, "TOKEN_VISUALIZER", None),
            "papersize": config.papersize,
        }
        heading = renderer._resolve_token(config, "text:heading", ctx)
        label = renderer._resolve_token(config, "text:label", ctx)
        body = renderer._resolve_token(config, "text:body", ctx)
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
        renderer._render_decorations(config, self._coordinates, day_names=False)

        self._cursor = self.top + self._title_size + 4.0
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
