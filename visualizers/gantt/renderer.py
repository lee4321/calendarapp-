"""
Gantt SVG renderer.

Page structure::

    ┌──────────────────────────────────────────────────────────────┐
    │ header                                                       │
    ├───────────────────────┬──────────────────────────────────────┤
    │                       │ top time bands                       │
    ├───────────────────────┼──────────────────────────────────────┤
    │ column headers        │                                      │
    ├───────────────────────┼──────────────────────────────────────┤
    │ task table            │ bars, marks, dependency arrows        │
    │ (one row per task)    │ over non-working-day shading         │
    ├───────────────────────┼──────────────────────────────────────┤
    │                       │ bottom time bands                    │
    ├───────────────────────┴──────────────────────────────────────┤
    │ footer                                                       │
    └──────────────────────────────────────────────────────────────┘

The day axis is a list of *visible* days: with ``weekend_style == 0``
non-working days are dropped from the axis entirely, so all horizontal
geometry is column-index based rather than linear in date (answer 13).
Every other weekend style keeps all seven days and shades the
non-working ones behind the content.

Phase 3 draws the frame, bands, shading, rows and cells.  Bars, marks
and dependency arrows arrive in phases 4-5; pagination in phase 6, so
rows past the bottom of the body are not drawn yet.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import TYPE_CHECKING, Any, ClassVar

import arrow

from renderers.svg_base import BaseSVGRenderer
from renderers.text_utils import string_width
from shared.date_utils import visible_days
from shared.day_classifier import classify_day
from shared.holiday_band import HolidayMark, compute_holiday_band_days
from shared.rule_engine import StyleEngine, StyleResult
from shared.timeband import BandSegment, build_segments
from visualizers.gantt.bars import (
    BarGeometry,
    DayAxis,
    bar_geometry,
    float_spans,
    progress_width,
)
from visualizers.gantt.columns import (
    LINK_REF_FIELD,
    cell_icon_visible,
    cell_value,
    column_x_positions,
    fit_lines,
    resolve_columns,
)
from visualizers.gantt.dependencies import (
    ARROW_STYLE_TARGET,
    DEFAULT_STUB,
    ArrowRoute,
    CrossPageReference,
    RowAnchor,
    arrow_head,
    assign_cross_page_references,
    resolve_dependencies,
    route_arrow,
    stub_route,
)
from visualizers.gantt.layout import plan_pages
from visualizers.gantt.details import (
    render_details_pages,
    KIND_CLIPPED_END,
    KIND_OFFCHART_DEPENDENCY,
    KIND_CLIPPED_START,
    KIND_HIDDEN_HOLIDAY,
    KIND_SNAPPED_EVENT,
    KIND_UNDRAWN,
    GanttException,
)
from visualizers.gantt.rows import build_rows

if TYPE_CHECKING:
    from config.config import CalendarConfig
    from shared.db_access import CalendarDB
    from visualizers.base import CoordinateDict
    from visualizers.gantt.columns import GanttColumn

#: Horizontal breathing room inside a table cell, in points.
_CELL_PAD = 2.0

#: Fallback bar fill when neither a rule, the event, nor the theme says.
_DEFAULT_BAR_FILL = "#888888"

#: Horizontal gap between two flags sharing one holiday-band day cell.
_HOLIDAY_FLAG_GAP = 1.0


def _page_output_path(output_path: str, page_number: int) -> str:
    """``chart.svg`` → ``chart_p2.svg`` (answer 12).

    Unpadded on purpose: ``visualizers/sheets.py`` zero-pads its own page
    numbers, but the Gantt was specified as ``_p2``/``_p3``.
    """
    if output_path.lower().endswith(".svg"):
        return f"{output_path[:-4]}_p{page_number}.svg"
    return f"{output_path}_p{page_number}.svg"


def _gantt_style_rules(config: "CalendarConfig") -> list:
    """Source the raw style_rules list for StyleEngine, UnifiedTheme-first.

    Mirrors blockplan / compactplan / weekly.
    """
    theme = getattr(config, "theme", None)
    if theme is not None:
        rules = theme.sections.get("style_rules")
        if isinstance(rules, list):
            return rules
    return list(getattr(config, "theme_style_rules", None) or [])


def _to_date(value) -> date | None:
    """Parse a ``YYYYMMDD`` field into a date, or None when unusable."""
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return arrow.get(text, "YYYYMMDD").date()
    except (ValueError, arrow.parser.ParserError):
        return None


class GanttRenderer(BaseSVGRenderer):
    """Renderer for the Gantt visualization.

    Per-render state is populated by `_render_content()`: the token cache
    (``self._tokens`` via ``TOKENS``) and, from phase 5, the style engine
    over the theme's ``style_rules``.  Entry point is ``render()`` on the
    base class.
    """

    # Tokens pre-resolved once per render; see BaseSVGRenderer._populate_tokens.
    TOKEN_VISUALIZER = "gantt"
    TOKENS = (
        "text:heading", "text:label", "text:body", "text:band_label",
        "text:event_name", "text:event_notes", "text:duration_date",
        "box:cell", "box:header", "box:band", "box:duration", "box:milestone",
        "line:grid", "line:axis", "line:separator", "line:today",
        "icon:event", "icon:duration", "icon:milestone",
    )

    #: Holiday marks per visible day, resolved once per render in
    #: _render_content.  Empty until then so a band row drawn without a
    #: render pass (tests, subclasses) simply shows no flags.
    _holiday_days: ClassVar["dict[date, list[HolidayMark]]"] = {}

    def _render_content(
        self,
        config: "CalendarConfig",
        coordinates: "CoordinateDict",
        events: list,
        db: "CalendarDB",
    ) -> tuple[int, list]:
        """Draw the chart.

        Returns ``(0, [])``: the Gantt never uses the weekly overflow
        page -- items that cannot be drawn faithfully are reported on the
        companion details page instead (see the plan, §8).
        """
        area = coordinates.get("GanttArea")
        if area is None:
            return 0, []

        self._populate_tokens(config)
        self._load_icon_svg_cache(db)

        start, end = self._range(config)
        days = visible_days(start, end, int(config.weekend_style))
        if not days:
            return 0, []

        self._exceptions = []
        self._extra_page_count = 0
        self._details_page_count = 0
        self._style_engine = StyleEngine(_gantt_style_rules(config))

        rows = build_rows(events, config)
        columns = resolve_columns(config)

        # Band segments are built once over the whole range and sliced per
        # page, so a sprint or month keeps its identity and its numbering
        # across horizontal page breaks (answer 11).
        segments = self._build_all_segments(config, start, end, days, db)
        # Holiday bands draw the flag on the holiday row itself, so the marks
        # are resolved once here (db in hand) and sliced per page like the
        # band segments are.
        self._holiday_days = compute_holiday_band_days(days, db, config)
        self._log_hidden_holidays(config, start, end, days, db)

        pages = self._plan_pages(config, coordinates, rows, days)
        self._build_link_graph(config, rows, pages)
        page_one_drawing = self._drawing

        for page in pages:
            if not page.is_first:
                # Each continuation page is its own document with the same
                # chrome, following the details-page pattern in mini.
                self._drawing = self._create_drawing(config)
                self._content_bbox_svg = None
                self._add_desc(config)
                self._inject_css()
                if config.watermark_text:
                    self._render_text_watermark(config)
                if config.watermark_image:
                    self._render_image_watermark(config)
                self._render_decorations(config, coordinates)

            self._draw_page(config, coordinates, page, rows, columns, days, segments, db)

            if not page.is_first:
                self._drawing.save_svg(
                    _page_output_path(config.outputfile, page.number)
                )

        self._extra_page_count = len(pages) - 1

        if config.include_gantt_details:
            self._details_page_count = render_details_pages(
                self, config, coordinates, rows, columns, self.exceptions,
            )

        # The base class saves whatever is in _drawing as page 1.
        self._drawing = page_one_drawing

        return 0, []

    def render(self, config, coordinates, events, db):
        """Render, reporting every page written.

        The base class saves page 1 and counts it; the chart's
        continuation pages and the companion details pages are written
        during ``_render_content`` and added here, so ``page_count``
        matches the number of files produced.
        """
        result = super().render(config, coordinates, events, db)
        result.page_count += getattr(self, "_extra_page_count", 0)
        result.page_count += getattr(self, "_details_page_count", 0)
        return result

    def _plan_pages(
        self,
        config: "CalendarConfig",
        coordinates: "CoordinateDict",
        rows: list,
        days: list[date],
    ) -> list:
        """Decide how the rows and days divide into pages."""
        _tx, _ty, _tw, table_h = coordinates["GanttTableBody"]
        _cx, _cy, chart_w, _ch = coordinates["GanttChartBody"]

        min_day_width = max(float(config.gantt_min_day_width), 0.0)
        days_per_page = (
            int(chart_w // min_day_width) if min_day_width > 0 else len(days)
        )

        return plan_pages(
            row_count=len(rows),
            day_count=len(days),
            rows_per_page=self._rows_that_fit(config, table_h),
            days_per_page=max(1, min(days_per_page or 1, len(days))),
        )

    def _draw_page(
        self,
        config: "CalendarConfig",
        coordinates: "CoordinateDict",
        page,
        rows: list,
        columns: list["GanttColumn"],
        days: list[date],
        segments: dict[int, list[BandSegment]],
        db: "CalendarDB",
    ) -> None:
        """Draw one page: its slice of rows over its slice of the axis."""
        page_days = days[page.day_start : page.day_end]
        page_rows = rows[page.row_start : page.row_end]
        if not page_days:
            return

        chart_x, _cy, chart_w, _ch = coordinates["GanttChartBody"]
        axis = DayAxis(days=page_days, x=chart_x, width=chart_w)

        # Back to front: shading, bands and table first, then the today
        # line, then the marks that must sit above it.
        self._draw_frame(coordinates)
        self._draw_nonworking_shading(config, coordinates, page_days, db)
        self._draw_bands(config, coordinates, page_days, segments)
        self._draw_column_headers(config, coordinates, columns)
        self._draw_rows(config, coordinates, page_rows, columns, page.row_start)
        self._draw_today_line(config, coordinates, axis)
        anchors = self._draw_marks(config, coordinates, page_rows, axis, page.row_start)
        # Every row, not just this page's: resolution has to tell "on another
        # page" apart from "no such task", and only the full list can.
        self._draw_dependencies(config, rows, anchors)

    @property
    def exceptions(self) -> list[GanttException]:
        """What the last render could not show faithfully (see details.py)."""
        return list(getattr(self, "_exceptions", []))

    def _note(
        self, kind: str, task: str, datekey: str = "", detail: str = "",
    ) -> None:
        """Record one exception for the companion details page."""
        if not hasattr(self, "_exceptions"):
            self._exceptions = []
        self._exceptions.append(
            GanttException(kind=kind, task=task, datekey=datekey, detail=detail)
        )

    # ── Geometry helpers ──────────────────────────────────────────────────

    @staticmethod
    def _range(config: "CalendarConfig") -> tuple[date, date]:
        """The chart's date range, taken from the calendar range like every view."""
        range_start = str(config.userstart or config.adjustedstart)
        range_end = str(config.userend or config.adjustedend)
        start = arrow.get(range_start, "YYYYMMDD").date()
        end = arrow.get(range_end, "YYYYMMDD").date()
        return (end, start) if end < start else (start, end)

    @staticmethod
    def _day_width(chart_w: float, days: list[date]) -> float:
        """Width of one visible-day column."""
        return chart_w / len(days) if days else 0.0

    def _rows_that_fit(self, config: "CalendarConfig", body_h: float) -> int:
        """How many task rows the body can show.

        Rows past this are dropped for now; phase 6 turns the remainder
        into continuation pages rather than discarding it.
        """
        row_h = max(float(config.gantt_row_height), 1.0)
        return max(0, int(body_h // row_h))

    # ── Drawing ───────────────────────────────────────────────────────────

    def _draw_frame(self, coordinates: "CoordinateDict") -> None:
        """Outer rule plus the divider between the table and the chart."""
        area_x, area_y, area_w, area_h = coordinates["GanttArea"]
        _tx, _ty, table_w, _th = coordinates["GanttTableArea"]

        color, width, opacity = self._grid_style()

        self._draw_rect(
            area_x, area_y, area_w, area_h,
            stroke=color, stroke_width=width, stroke_opacity=opacity,
            css_class="ec-grid-line",
        )

        divider_x = area_x + table_w
        self._draw_line(
            divider_x, area_y, divider_x, area_y + area_h,
            stroke=color, stroke_width=width, stroke_opacity=opacity,
            css_class="ec-separator",
        )

    def _draw_nonworking_shading(
        self,
        config: "CalendarConfig",
        coordinates: "CoordinateDict",
        days: list[date],
        db: "CalendarDB",
    ) -> None:
        """Shade non-working day columns behind everything else.

        Only reachable when the weekend style keeps weekends on the axis;
        under ``weekend_style == 0`` those days are not columns at all.
        Holidays are always columns and always shaded, so the axis does
        not silently change shape with ``--country`` (answer 14).
        """
        chart_x, chart_y, chart_w, chart_h = coordinates["GanttChartBody"]
        day_w = self._day_width(chart_w, days)
        if day_w <= 0:
            return

        style = config.get_box_style("ec-cell")
        fill = style.fill or "#000000"
        opacity = float(style.fill_opacity if style.fill_opacity is not None else 0.08)

        for index, day in enumerate(days):
            if not classify_day(day, db, config):
                continue
            self._draw_rect(
                chart_x + index * day_w, chart_y, day_w, chart_h,
                fill=fill, fill_opacity=opacity,
                css_class="ec-cell",
            )

    def _build_all_segments(
        self,
        config: "CalendarConfig",
        start: date,
        end: date,
        days: list[date],
        db: "CalendarDB",
    ) -> dict[tuple[str, int], list[BandSegment]]:
        """Build every band's segments once, over the whole date range.

        Building per page would restart interval counters at each break,
        so ``Sprint 7`` would come back as ``Sprint 1`` on page 2.  Pages
        slice these instead, and a segment straddling a break simply
        draws its overlapping part on both pages under the same label.
        """
        segments: dict[tuple[str, int], list[BandSegment]] = {}
        stacks = (
            ("top", config.gantt_top_time_bands),
            ("bottom", config.get_gantt_bottom_bands()),
        )
        for stack, bands in stacks:
            for index, band in enumerate(bands or []):
                if not isinstance(band, dict):
                    continue
                segments[(stack, index)] = build_segments(
                    band, start, end, config, visible_days=days, db=db,
                )
        return segments

    def _draw_bands(
        self,
        config: "CalendarConfig",
        coordinates: "CoordinateDict",
        days: list[date],
        segments: dict[tuple[str, int], list[BandSegment]],
    ) -> None:
        """Draw the top and bottom time-band stacks for this page's days."""
        top = coordinates.get("GanttTopBands")
        bottom = coordinates.get("GanttBottomBands")
        if top:
            self._draw_band_stack(
                config, top, config.gantt_top_time_bands, days, segments, "top",
            )
        if bottom:
            self._draw_band_stack(
                config, bottom, config.get_gantt_bottom_bands(), days,
                segments, "bottom",
            )

    def _draw_band_stack(
        self,
        config: "CalendarConfig",
        region: tuple[float, float, float, float],
        bands: list[dict[str, Any]],
        days: list[date],
        segments: dict[tuple[str, int], list[BandSegment]],
        stack: str,
    ) -> None:
        """Draw one stack of band rows, top to bottom, within *region*."""
        region_x, region_y, region_w, region_h = region
        bands = [band for band in (bands or []) if isinstance(band, dict)]
        if not bands or region_h <= 0:
            return

        default_h = float(config.gantt_band_row_height)
        heights = [float(band.get("row_height", default_h)) for band in bands]
        total = sum(heights) or 1.0
        scale = region_h / total if total > region_h else 1.0

        cursor_y = region_y
        for index, (band, height) in enumerate(zip(bands, heights)):
            row_h = height * scale
            self._draw_band_row(
                config, band, segments.get((stack, index), []), days,
                region_x, cursor_y, region_w, row_h,
            )
            cursor_y += row_h

    def _draw_band_row(
        self,
        config: "CalendarConfig",
        band: dict[str, Any],
        segments: list[BandSegment],
        days: list[date],
        x: float,
        y: float,
        w: float,
        h: float,
    ) -> None:
        """Draw one band row: a cell per segment, each with a centered label."""
        day_w = self._day_width(w, days)
        if day_w <= 0 or h <= 0:
            return

        # A holiday band has no labeled segments — it draws one flag per day.
        if str(band.get("unit", "date")).strip().lower() == "holiday":
            self._draw_holiday_band_row(config, band, days, x, y, w, h)
            return

        day_index = {day: index for index, day in enumerate(days)}
        color, width, opacity = self._grid_style()
        box = config.get_box_style("ec-band-cell")
        token = self._tk("text:band_label")
        font = token.get("font") or config.get_text_style("ec-tick-label").font
        font_size = min(float(token.get("size") or 8.0), max(h - 2.0, 4.0))

        for segment in segments:
            span = [
                index
                for day, index in day_index.items()
                if segment.start <= day < segment.end_exclusive
            ]
            if not span:
                # Every day of this segment is hidden (a weekend-only
                # segment under weekend_style 0) — nothing to draw.
                continue

            seg_x = x + min(span) * day_w
            seg_w = (max(span) - min(span) + 1) * day_w

            self._draw_rect(
                seg_x, y, seg_w, h,
                fill=box.fill or "none",
                fill_opacity=float(
                    box.fill_opacity if box.fill_opacity is not None else 1.0
                ),
                stroke=color, stroke_width=width, stroke_opacity=opacity,
                css_class="ec-band-cell",
            )
            self._draw_clipped_text(
                segment.label, seg_x, y + h / 2 + font_size / 3, seg_w,
                font, font_size, token.get("color") or "black",
                align="center", css_class="ec-tick-label",
            )

    def _draw_holiday_band_row(
        self,
        config: "CalendarConfig",
        band: dict[str, Any],
        days: list[date],
        x: float,
        y: float,
        w: float,
        h: float,
    ) -> None:
        """Draw one flag per holiday in this page's day columns.

        Unlike a labelled band every cell is a single day, so the row is drawn
        per day rather than per segment.  Days with no holiday still get their
        cell, keeping the row's grid continuous with the bands above it.
        """
        day_w = self._day_width(w, days)
        color, width, opacity = self._grid_style()
        box = config.get_box_style("ec-band-cell")
        # Leave a little air around the flag so it does not touch the grid.
        icon_size = max(min(h - 2.0, day_w - 2.0), 3.0)
        show_all = not bool(band.get("nonworkdays_only", False))

        for index, day in enumerate(days):
            cell_x = x + index * day_w
            self._draw_rect(
                cell_x, y, day_w, h,
                fill=box.fill or "none",
                fill_opacity=float(
                    box.fill_opacity if box.fill_opacity is not None else 1.0
                ),
                stroke=color, stroke_width=width, stroke_opacity=opacity,
                css_class="ec-band-cell",
            )

            marks = [
                m
                for m in self._holiday_days.get(day, ())
                if show_all or m.nonworkday
            ]
            if not marks:
                continue

            # More flags than the column can hold would overlap illegibly;
            # draw what fits, centred as a group.
            per_icon = icon_size + _HOLIDAY_FLAG_GAP
            max_icons = max(int((day_w - 1.0) // per_icon), 1)
            drawn = marks[:max_icons]
            group_w = len(drawn) * per_icon - _HOLIDAY_FLAG_GAP
            icon_x = cell_x + (day_w - group_w) / 2.0
            baseline = y + h / 2.0 + icon_size / 2.0

            for mark in drawn:
                self._draw_icon_svg(
                    mark.icon, icon_x, baseline, icon_size,
                    css_class="ec-holiday-icon",
                )
                icon_x += per_icon

    def _draw_column_headers(
        self,
        config: "CalendarConfig",
        coordinates: "CoordinateDict",
        columns: list["GanttColumn"],
    ) -> None:
        """Draw the task-table header row."""
        header = coordinates.get("GanttColumnHeader")
        if not header or not columns:
            return

        head_x, head_y, head_w, head_h = header
        box = config.get_box_style("ec-heading-cell")
        token = self._tk("text:label")
        font = token.get("font") or config.get_text_style("ec-column-header").font
        font_size = min(float(token.get("size") or 8.0), max(head_h - 2.0, 4.0))
        color, width, opacity = self._grid_style()

        fill = box.fill or "none"
        if str(fill).strip().lower() not in {"", "none", "transparent"}:
            self._draw_rect(
                head_x, head_y, head_w, head_h,
                fill=fill,
                fill_opacity=float(
                    box.fill_opacity if box.fill_opacity is not None else 1.0
                ),
                css_class="ec-heading-cell",
            )

        for column, (col_x, col_w) in zip(
            columns, column_x_positions(columns, head_x, head_w)
        ):
            usable = col_w - _CELL_PAD * 2
            # Truncate rather than let _draw_text squeeze the glyphs: a
            # narrow column should lose characters, not legibility.
            header_lines = fit_lines(
                column.header, usable, 1,
                lambda text: self._measure(text, font, font_size),
            )
            if header_lines:
                self._draw_clipped_text(
                    header_lines[0],
                    col_x + _CELL_PAD, head_y + head_h / 2 + font_size / 3, usable,
                    font, font_size, token.get("color") or "black",
                    align=column.align, css_class="ec-column-header",
                )
            self._draw_line(
                col_x, head_y, col_x, head_y + head_h,
                stroke=color, stroke_width=width, stroke_opacity=opacity,
                css_class="ec-grid-line",
            )

        self._draw_line(
            head_x, head_y + head_h, head_x + head_w, head_y + head_h,
            stroke=color, stroke_width=width, stroke_opacity=opacity,
            css_class="ec-separator",
        )

    def _draw_rows(
        self,
        config: "CalendarConfig",
        coordinates: "CoordinateDict",
        rows: list,
        columns: list["GanttColumn"],
        row_offset: int = 0,
    ) -> None:
        """Draw this page's task rows: banding, grid lines and cell content.

        *rows* is already the page's slice; *row_offset* is the index of
        its first row in the whole chart, so the page draws from its own
        top edge while row banding stays consistent across pages.
        """
        table = coordinates.get("GanttTableBody")
        chart = coordinates.get("GanttChartBody")
        if not table or not chart or not rows:
            return

        table_x, table_y, table_w, _table_h = table
        chart_x, _cy, chart_w, _ch = chart
        row_h = max(float(config.gantt_row_height), 1.0)
        visible_rows = rows

        band = config.get_box_style("ec-row-band")
        band_fill = band.fill or "none"
        band_opacity = float(
            band.fill_opacity if band.fill_opacity is not None else 0.15
        )
        banded = str(band_fill).strip().lower() not in {"", "none", "transparent"}

        token = self._tk("text:body")
        font = token.get("font") or config.get_text_style("ec-task-cell").font
        font_size = float(token.get("size") or 8.0)
        text_color = token.get("color") or "black"
        color, width, opacity = self._grid_style()
        positions = column_x_positions(columns, table_x, table_w)

        for row in visible_rows:
            row_y = table_y + (row.index - row_offset) * row_h

            if banded and row.index % 2 == 1:
                self._draw_rect(
                    table_x, row_y, table_w + chart_w, row_h,
                    fill=band_fill, fill_opacity=band_opacity,
                    css_class="ec-row-band",
                )

            self._draw_line(
                table_x, row_y + row_h, table_x + table_w + chart_w, row_y + row_h,
                stroke=color, stroke_width=width, stroke_opacity=opacity,
                css_class="ec-grid-line",
            )

            self._draw_row_cells(
                config, row, columns, positions, row_y, row_h,
                font, font_size, text_color,
            )

    def _draw_row_cells(
        self,
        config: "CalendarConfig",
        row,
        columns: list["GanttColumn"],
        positions: list[tuple[float, float]],
        row_y: float,
        row_h: float,
        font: str,
        font_size: float,
        text_color: str,
    ) -> None:
        """Draw one row's cells across every column."""
        indent = float(config.gantt_indent_per_level) * row.depth

        for column, (col_x, col_w) in zip(columns, positions):
            left = col_x + _CELL_PAD + (indent if column.indent else 0.0)
            usable = col_w - _CELL_PAD * 2 - (indent if column.indent else 0.0)
            if usable <= 0:
                continue

            if column.field == LINK_REF_FIELD:
                self._draw_reference_cell(
                    config, row, col_x, col_w, row_y, row_h, font_size,
                )
                continue

            if column.render == "icon":
                if cell_icon_visible(column, row.event):
                    self._draw_icon_svg(
                        column.icon,
                        col_x + col_w / 2,
                        row_y + row_h / 2 + font_size / 3,
                        min(font_size, row_h - 1.0),
                        anchor="middle",
                        css_class="ec-event-icon",
                    )
                continue

            lines = fit_lines(
                cell_value(column, row.event),
                usable,
                min(column.max_lines, max(1, int(row_h // max(font_size, 1.0)))),
                lambda text: self._measure(text, font, font_size),
            )
            if not lines:
                continue

            # Vertically center the block of lines within the row.
            block_h = len(lines) * font_size
            first_baseline = row_y + (row_h - block_h) / 2 + font_size * 0.8
            for line_index, line in enumerate(lines):
                self._draw_clipped_text(
                    line, left, first_baseline + line_index * font_size, usable,
                    font, font_size, text_color,
                    align=column.align, css_class="ec-task-cell",
                )

    # ── Marks: bars, progress, floats, brackets, icons ────────────────────

    def _draw_today_line(
        self,
        config: "CalendarConfig",
        coordinates: "CoordinateDict",
        axis: DayAxis,
    ) -> None:
        """Vertical rule at the as-of date, PIT semantics (answer 32).

        ``gantt_today_date`` overrides the wall clock so a forward-dated
        presentation still lines up; a date outside the range draws
        nothing.  A hidden day snaps forward to the next column so a
        Saturday "today" does not silently vanish.
        """
        if not config.gantt_show_today_line or not axis.days:
            return

        today = _to_date(config.gantt_today_date) or arrow.now().date()
        if today < axis.first or today > axis.last:
            return

        index = axis.snap_forward(today)
        if index is None:
            return

        _bx, body_y, _bw, body_h = coordinates["GanttChartBody"]
        token = self._tk("line:today")
        self._draw_line(
            axis.left_of(index), body_y, axis.left_of(index), body_y + body_h,
            stroke=token.get("color") or "#FF4444",
            stroke_width=float(token.get("width") or 1.5),
            stroke_opacity=float(token.get("opacity") or 1.0),
            stroke_dasharray=token.get("dasharray"),
            css_class="ec-today-line",
        )

    def _draw_marks(
        self,
        config: "CalendarConfig",
        coordinates: "CoordinateDict",
        rows: list,
        axis: DayAxis,
        row_offset: int = 0,
    ) -> dict[int, RowAnchor]:
        """Draw this page's chart-side marks; return where each one landed.

        The anchors feed the dependency pass, which has to attach to the
        mark that was actually drawn -- bar, bracket or glyph.
        """
        anchors: dict[int, RowAnchor] = {}
        table = coordinates.get("GanttTableBody")
        if not table or not rows or not axis.days:
            return anchors

        _tx, table_y, _tw, _table_h = table
        row_h = max(float(config.gantt_row_height), 1.0)

        for row in rows:
            anchor = self._draw_row_marks(
                config, row, axis, table_y + (row.index - row_offset) * row_h, row_h,
            )
            if anchor is not None:
                anchors[row.index] = anchor
        return anchors

    def _draw_row_marks(
        self,
        config: "CalendarConfig",
        row,
        axis: DayAxis,
        row_y: float,
        row_h: float,
    ) -> RowAnchor | None:
        """Draw one row: rollup bracket, milestone, or bar with its trimmings.

        Returns where the mark landed so dependency arrows can attach to
        it, or None when nothing was drawn.
        """
        event = row.event
        start, end = _to_date(event.start), _to_date(event.end)
        if start is None or end is None:
            return None

        engine = getattr(self, "_style_engine", None)
        style = engine.evaluate_event(event) if engine is not None else StyleResult()

        bar_h = max(min(float(config.gantt_bar_height), row_h - 2.0), 1.0)
        bar_y = row_y + (row_h - bar_h) / 2

        if event.rollup:
            # Brackets only: no progress line, no float bars (answer 19).
            anchor = self._draw_rollup_bracket(
                config, axis, start, end, bar_y, bar_h, style
            )
        elif event.milestone:
            anchor = self._draw_milestone(
                config, axis, event, end, row_y, row_h, style
            )
        else:
            anchor = self._draw_task_bar(
                config, event, axis, start, end, bar_y, bar_h, row_h, style,
            )

        self._draw_deadline(config, axis, event, row_y, row_h)
        return anchor

    def _draw_task_bar(
        self,
        config: "CalendarConfig",
        event,
        axis: DayAxis,
        start: date,
        end: date,
        bar_y: float,
        bar_h: float,
        row_h: float,
        style: StyleResult,
    ) -> RowAnchor | None:
        """Duration bar (or single-day rectangle) plus float, progress and icons."""
        geometry = bar_geometry(axis, start, end)
        if not geometry.visible:
            self._note(
                KIND_UNDRAWN, event.task_name, event.start,
                "every day of the span is hidden",
            )
            return None

        fill = self._bar_fill(config, event, style)

        # Float windows sit under the bar at reduced opacity (answer 67).
        self._draw_float_bars(config, event, axis, bar_y, bar_h, fill)

        token = self._tk("box:duration")
        self._draw_rect(
            geometry.x, bar_y, geometry.width, bar_h,
            fill=fill,
            fill_opacity=float(
                style.fill_opacity
                if style.fill_opacity is not None
                else (token.get("fill_opacity") or 0.85)
            ),
            stroke=style.stroke_color or token.get("stroke") or "none",
            stroke_width=float(style.stroke_width or token.get("stroke_width") or 0),
            stroke_dasharray=style.stroke_dasharray,
            css_class="ec-duration-bar",
        )

        self._draw_progress(config, event, geometry, bar_y, bar_h, style)
        self._draw_continuations(config, geometry, bar_y, bar_h)

        if geometry.clipped_start:
            self._note(
                KIND_CLIPPED_START, event.task_name, event.start,
                f"starts {event.start}, before the range",
            )
        if geometry.clipped_end:
            self._note(
                KIND_CLIPPED_END, event.task_name, event.end,
                f"ends {event.end}, after the range",
            )

        if start == end and geometry.snapped:
            # A single-day event whose own day is not on the axis was
            # moved forward; mark it and report it (answer 22).
            self._draw_icon_svg(
                config.gantt_snapped_event_icon,
                geometry.x + geometry.width / 2,
                bar_y + bar_h,
                bar_h,
                anchor="middle",
                css_class="ec-event-icon",
            )
            self._note(
                KIND_SNAPPED_EVENT, event.task_name, event.start,
                "drawn on the next working day",
            )

        return RowAnchor(
            left=geometry.x,
            right=geometry.x + geometry.width,
            y=bar_y + bar_h / 2,
        )

    def _draw_float_bars(
        self,
        config: "CalendarConfig",
        event,
        axis: DayAxis,
        bar_y: float,
        bar_h: float,
        fill: str,
    ) -> None:
        """Draw the earliest/latest windows around the task's own dates."""
        scale = float(config.gantt_float_opacity_scale)
        for _name, begin, finish in float_spans(event):
            begin_date, finish_date = _to_date(begin), _to_date(finish)
            if begin_date is None or finish_date is None:
                continue
            span = bar_geometry(axis, begin_date, finish_date)
            if not span.visible:
                continue
            self._draw_rect(
                span.x, bar_y, span.width, bar_h,
                fill=fill, fill_opacity=scale,
                css_class="ec-float-bar",
            )

    def _draw_progress(
        self,
        config: "CalendarConfig",
        event,
        geometry: BarGeometry,
        bar_y: float,
        bar_h: float,
        style: StyleResult,
    ) -> None:
        """Percent-complete line along the bar, measured in working days."""
        width = progress_width(geometry, event.percent_complete)
        if width <= 0:
            return

        line_y = bar_y + bar_h / 2
        self._draw_line(
            geometry.x, line_y, geometry.x + width, line_y,
            stroke=config.gantt_progress_color,
            stroke_width=float(config.gantt_progress_width),
            stroke_dasharray=style.stroke_dasharray,
            css_class="ec-progress-line",
        )

    def _draw_continuations(
        self,
        config: "CalendarConfig",
        geometry: BarGeometry,
        bar_y: float,
        bar_h: float,
    ) -> None:
        """Icons inside the bar edges where the span leaves the range."""
        if geometry.clipped_start:
            self._draw_icon_svg(
                "arrow-bar-left", geometry.x + bar_h / 2, bar_y + bar_h, bar_h,
                anchor="middle", css_class="ec-continuation-icon",
            )
        if geometry.clipped_end:
            self._draw_icon_svg(
                config.gantt_continuation_icon,
                geometry.x + geometry.width - bar_h / 2, bar_y + bar_h, bar_h,
                anchor="middle", css_class="ec-continuation-icon",
            )

    def _draw_rollup_bracket(
        self,
        config: "CalendarConfig",
        axis: DayAxis,
        start: date,
        end: date,
        bar_y: float,
        bar_h: float,
        style: StyleResult,
    ) -> RowAnchor | None:
        """Downward-facing bracket spanning the rollup's own dates.

        Suppressed when either date is missing -- children are never
        consulted, so a rollup row with no dates simply has no bracket
        (answer 20).
        """
        geometry = bar_geometry(axis, start, end)
        if not geometry.visible:
            return None

        token = self._tk("line:axis")
        color = style.stroke_color or token.get("color") or "black"
        width = float(style.stroke_width or token.get("width") or 1.5)
        top = bar_y
        foot = bar_y + bar_h
        right = geometry.x + geometry.width

        self._draw_lines(
            [
                (geometry.x, foot, geometry.x, top),
                (geometry.x, top, right, top),
                (right, top, right, foot),
            ],
            stroke=color,
            stroke_width=width,
            stroke_dasharray=style.stroke_dasharray,
            css_class="ec-rollup-bracket",
        )

        return RowAnchor(left=geometry.x, right=right, y=(top + foot) / 2)

    def _draw_milestone(
        self,
        config: "CalendarConfig",
        axis: DayAxis,
        event,
        anchor_day: date,
        row_y: float,
        row_h: float,
        style: StyleResult,
    ) -> RowAnchor | None:
        """Milestone glyph, anchored on the end date (answer 23)."""
        index = axis.snap_forward(anchor_day)
        if index is None or anchor_day < axis.first or anchor_day > axis.last:
            return None

        size = max(min(float(config.gantt_bar_height) * 1.3, row_h - 1.0), 1.0)
        self._draw_icon_svg(
            style.icon or config.gantt_milestone_icon,
            axis.center_of(index),
            row_y + (row_h + size) / 2,
            size,
            anchor="middle",
            color=style.icon_color or self._tk("icon:milestone").get("color"),
            css_class="ec-milestone-marker",
        )

        center_x = axis.center_of(index)
        return RowAnchor(
            left=center_x - size / 2, right=center_x + size / 2, y=row_y + row_h / 2,
        )

    def _draw_deadline(
        self,
        config: "CalendarConfig",
        axis: DayAxis,
        event,
        row_y: float,
        row_h: float,
    ) -> None:
        """Deadline glyph on the chart, when the task carries one (answer 21)."""
        deadline = _to_date(event.deadline)
        if deadline is None or not axis.days:
            return
        if deadline < axis.first or deadline > axis.last:
            return

        index = axis.snap_forward(deadline)
        if index is None:
            return

        size = max(min(float(config.gantt_bar_height), row_h - 2.0), 1.0)
        self._draw_icon_svg(
            config.gantt_deadline_icon,
            axis.center_of(index),
            row_y + (row_h + size) / 2,
            size,
            anchor="middle",
            css_class="ec-event-icon",
        )

    def _bar_fill(
        self, config: "CalendarConfig", event, style: StyleResult
    ) -> str:
        """Bar color: a matching style_rule, then the event, then the theme."""
        if style.fill_color and not isinstance(style.fill_color, list):
            return str(style.fill_color)
        if event.color:
            return str(event.color)
        return self._tk("box:duration").get("fill") or _DEFAULT_BAR_FILL

    def _log_hidden_holidays(
        self,
        config: "CalendarConfig",
        start: date,
        end: date,
        days: list[date],
        db: "CalendarDB",
    ) -> None:
        """Report holidays that fall on days the axis does not show.

        Under ``weekend_style == 0`` a holiday landing on a weekend has
        no column to shade, so it is reported rather than lost (answer 14).
        """
        from config.config import weekend_style_is_workweek

        if not weekend_style_is_workweek(int(config.weekend_style)):
            return

        visible = set(days)
        cursor = start
        while cursor <= end:
            if cursor not in visible:
                classes = classify_day(cursor, db, config)
                if classes & {"federal_holiday", "company_holiday"}:
                    self._note(
                        KIND_HIDDEN_HOLIDAY,
                        "",
                        cursor.strftime("%Y%m%d"),
                        "falls on a hidden weekend day",
                    )
            cursor += timedelta(days=1)

    # ── Dependencies ──────────────────────────────────────────────────────

    def _build_link_graph(
        self, config: "CalendarConfig", rows: list, pages: list
    ) -> None:
        """Resolve every link once and number the ones pagination breaks.

        Resolution runs against the whole chart, so "on another page" stays
        distinct from "no such task".  Numbering is chart-level for the
        same reason a page number is: ⑦ has to mean one thing in every
        file.
        """
        self._dependencies = []
        self._references = {}
        self._reference_marks = {}

        if not rows:
            return

        dependencies, exceptions = resolve_dependencies(
            rows, {row.index for row in rows}
        )
        for exception in exceptions:
            self._note(
                exception.kind, exception.task, exception.datekey, exception.detail
            )
        self._dependencies = dependencies

        # Rows share a page when they fall in the same row block; horizontal
        # pages repeat every row, so the block is what decides it.
        block_of: dict[int, int] = {}
        for page in pages:
            for index in range(page.row_start, page.row_end):
                block_of.setdefault(index, page.row_start)

        def same_page(a: int, b: int) -> bool:
            return block_of.get(a) == block_of.get(b)

        references, _unnumbered = assign_cross_page_references(
            dependencies,
            same_page,
            list(config.gantt_link_ref_icon_families),
            int(config.gantt_link_ref_family_size),
            set(getattr(self, "_icon_svg_map", {}) or {}) or None,
        )
        self._references = references

        by_index = {row.index: row for row in rows}
        for reference in references.values():
            source = by_index.get(reference.source_index)
            for target_index in reference.target_indexes:
                self._reference_marks.setdefault(target_index, []).append(
                    reference.icon
                )
                target = by_index.get(target_index)
                self._note(
                    KIND_OFFCHART_DEPENDENCY,
                    target.event.task_name if target else "",
                    "",
                    f"{reference.icon}: depends on "
                    f"{source.event.task_name if source else '?'}, "
                    "drawn on another page",
                )

    def _draw_dependencies(
        self,
        config: "CalendarConfig",
        rows: list,
        anchors: dict[int, RowAnchor],
    ) -> None:
        """Draw an arrow for every resolvable link between drawn rows.

        Arrows appear whenever the data supports them (answer 28); a
        predecessor that is not on the chart becomes a stub ending in the
        off-chart icon, and every unresolved or unparseable reference is
        reported for the details page (answer 27).
        """
        if not config.gantt_show_dependencies or not anchors:
            return

        dependencies = list(getattr(self, "_dependencies", []))
        by_index = {row.index: row for row in rows}

        # One numbered stub per source event whose successors are elsewhere.
        for reference in getattr(self, "_references", {}).values():
            if reference.source_index in anchors:
                self._draw_reference_stub(config, reference, anchors, by_index)

        if not dependencies:
            return
        engine = getattr(self, "_style_engine", None)
        token = self._tk("line:grid")

        for dependency in dependencies:
            successor = anchors.get(dependency.successor_index)
            if successor is None:
                continue

            style = StyleResult()
            row = by_index.get(dependency.successor_index)
            if engine is not None and row is not None:
                style = engine.evaluate_target(ARROW_STYLE_TARGET, row.event)

            if dependency.predecessor_index is None:
                # No far end anywhere: an unnumbered stub, as before.
                route = stub_route(successor, length=DEFAULT_STUB * 3)
                self._draw_arrow(config, route, style)
                tail_x, tail_y = route.points[0]
                self._draw_icon_svg(
                    config.gantt_offchart_dep_icon,
                    tail_x,
                    tail_y + DEFAULT_STUB,
                    DEFAULT_STUB * 2,
                    anchor="middle",
                    css_class="ec-event-icon",
                )
                continue

            predecessor = anchors.get(dependency.predecessor_index)
            if predecessor is None:
                # The far end is on another page; its stub is drawn there
                # and this row carries the number in its reference column.
                continue

            self._draw_arrow(
                config,
                route_arrow(predecessor, successor, dependency.link_type),
                style,
            )

    def _draw_reference_stub(
        self,
        config: "CalendarConfig",
        reference: CrossPageReference,
        anchors: dict[int, RowAnchor],
        by_index: dict,
    ) -> None:
        """Draw one forward stub from a source event to its numbered icon.

        One stub per event however many successors it could not reach
        (answer 3) — the number, not the arrow, carries the detail.
        """
        source = anchors[reference.source_index]
        length = DEFAULT_STUB * 3

        style = StyleResult()
        engine = getattr(self, "_style_engine", None)
        row = by_index.get(reference.source_index)
        if engine is not None and row is not None:
            style = engine.evaluate_target(ARROW_STYLE_TARGET, row.event)

        route = ArrowRoute(
            points=[(source.right, source.y), (source.right + length, source.y)],
            head_dir=+1,
        )
        self._draw_arrow(config, route, style)
        self._draw_icon_svg(
            reference.icon,
            source.right + length + DEFAULT_STUB,
            source.y + DEFAULT_STUB,
            DEFAULT_STUB * 2,
            anchor="middle",
            css_class="ec-event-icon",
        )

    def _draw_arrow(
        self,
        config: "CalendarConfig",
        route,
        style: StyleResult,
    ) -> None:
        """Stroke one route and its head, both themed as one line."""
        token = self._tk("line:grid")
        color = style.stroke_color or token.get("color") or "grey"
        width = float(style.stroke_width or token.get("width") or 1.0)
        opacity = float(
            style.stroke_opacity
            if style.stroke_opacity is not None
            else (token.get("opacity") or 0.9)
        )

        self._draw_lines(
            route.segments,
            stroke=color,
            stroke_width=width,
            stroke_opacity=opacity,
            stroke_dasharray=style.stroke_dasharray,
            css_class="ec-dependency-arrow",
        )
        # The head is never dashed — a dashed arrowhead reads as noise.
        self._draw_lines(
            arrow_head(route.tip, route.head_dir, DEFAULT_STUB),
            stroke=color,
            stroke_width=width,
            stroke_opacity=opacity,
            css_class="ec-dependency-arrow",
        )

    def _draw_reference_cell(
        self,
        config: "CalendarConfig",
        row,
        col_x: float,
        col_w: float,
        row_y: float,
        row_h: float,
        font_size: float,
    ) -> None:
        """Draw this row's cross-page reference icons, if it has any.

        A row can be the far end of links from several source events, so
        the cell may hold more than one icon.  The details page lists every
        reference, so capping the drawn count costs nothing but ink.
        """
        icons = getattr(self, "_reference_marks", {}).get(row.index)
        if not icons:
            return

        icons = icons[: max(1, int(config.gantt_link_ref_max_icons))]
        size = min(font_size, row_h - 1.0)
        step = min(size, col_w / len(icons))
        # Centre the run of icons within the cell.
        first_x = col_x + col_w / 2 - step * (len(icons) - 1) / 2

        for position, icon in enumerate(icons):
            self._draw_icon_svg(
                icon,
                first_x + position * step,
                row_y + row_h / 2 + font_size / 3,
                size,
                anchor="middle",
                css_class="ec-event-icon",
            )

    # ── Small shared helpers ──────────────────────────────────────────────

    def _grid_style(self) -> tuple[str, float, float]:
        """``(color, width, opacity)`` for grid and separator strokes."""
        token = self._tk("line:grid")
        return (
            token.get("color") or "grey",
            float(token.get("width") or 0.5),
            float(token.get("opacity") or 0.5),
        )

    def _measure(self, text: str, font: str, size: float) -> float:
        """Width of *text*, resolving the font name to its registered path."""
        from config.config import get_font_path

        try:
            path = get_font_path(font)
        except KeyError:
            return len(text) * size * 0.5
        return string_width(text, path, size)

    def _draw_clipped_text(
        self,
        text: str,
        x: float,
        baseline_y: float,
        width: float,
        font: str,
        font_size: float,
        color: str,
        *,
        align: str = "left",
        css_class: str | None = None,
    ) -> None:
        """Draw one line inside *width*, honoring the column's alignment."""
        if not text or width <= 0 or font_size <= 0:
            return

        anchor = {"left": "start", "center": "middle", "right": "end"}.get(
            align, "start"
        )
        if anchor == "middle":
            draw_x = x + width / 2
        elif anchor == "end":
            draw_x = x + width
        else:
            draw_x = x

        self._draw_text(
            draw_x, baseline_y, text, font, font_size,
            fill=color, anchor=anchor, max_width=width, css_class=css_class,
        )
