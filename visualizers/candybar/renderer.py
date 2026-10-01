"""
SVG renderer for the candybar (vertical year-strip) visualization.

Subclasses :class:`MiniCalendarRenderer` so it inherits the full day-cell
decoration engine — background shade, SVG patterns, legacy hash, milestone
circles, and the number-or-icon foreground driven by ``DayStyleResolver`` and
theme ``style_rules`` / ``box:day`` rules (the same rules mini-icon uses).

What this renderer adds on top:
  * a per-strip header row (week-number column + weekday labels),
  * a week-number column down the left edge,
  * a table grid around every cell, and
  * the timescale's month row laid down the week rows, one merged cell per month.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date
from typing import TYPE_CHECKING

from renderers.svg_base import _is_none_color
from renderers.timescale import ScaleContext, draw_cells, plan_rows
from shared.date_utils import (
    index_events_by_day as _index_events_by_day,
)
from shared.glyphs import mini_glyph_sets
from shared.orientation import Orientation
from shared.palettes import resolve_theme_palettes
from shared.span import Frame, Span
from visualizers.candybar.layout import compute_columns
from visualizers.mini.day_styles import DayStyle, DayStyleResolver
from visualizers.mini.renderer import MiniCalendarRenderer

if TYPE_CHECKING:
    from config.config import CalendarConfig
    from shared.db_access import CalendarDB
    from visualizers.base import CoordinateDict


class CandybarRenderer(MiniCalendarRenderer):
    """Renderer for the candybar year-strip."""

    DETAILS_VISUALIZER = "candybar"

    def _render_content(
        self,
        config: CalendarConfig,
        coordinates: CoordinateDict,
        events: list,
        db: CalendarDB,
    ) -> tuple[int, list]:
        self._db = db
        resolve_theme_palettes(config, db)
        self._glyphs = mini_glyph_sets(config, db)
        self._populate_tokens(config)
        resolver = DayStyleResolver(config, db)
        self._period_text = resolver.period_labels.text if resolver.period_labels else None
        self._load_icon_svg_cache(db)
        self._pattern_svg_cache = db.get_all_patterns()
        self._registered_pattern_ids = set()
        effective_events = events if config.includeevents else []
        events_by_day = _index_events_by_day(effective_events)

        # Resolve every day cell's style once.
        cell_state: list[tuple[float, float, float, float, str, DayStyle]] = []
        for key in sorted(coordinates):
            if not key.startswith("Cell_"):
                continue
            x, y, w, h = coordinates[key]
            daykey = key[len("Cell_") :]
            day_events = events_by_day.get(daykey, [])
            style = resolver.resolve(daykey, day_events, is_adjacent=False)
            cell_state.append((x, y, w, h, daykey, style))

        self._note_grid_days(config, (state[4] for state in cell_state), events_by_day)

        # Pass 1 — the month column
        self._draw_month_column(config, coordinates)

        # Pass 1b — base cell shading (month banding + weekends), drawn under
        # the holiday/rule shade so those override it.
        self._draw_base_shading(config, cell_state)

        # Pass 2 — day-cell backgrounds (shade, SVG patterns, hash)
        for x, y, w, h, _daykey, style in cell_state:
            self._draw_day_cell_background(config, x, y, w, h, style)

        # Pass 3 — table grid around every structural cell
        self._draw_grid(config, coordinates)

        # Pass 4 — day numbers / icons (foreground)
        for x, y, w, h, daykey, style in cell_state:
            self._draw_day_cell_foreground(config, x, y, w, h, int(daykey[6:8]), style)

        # Pass 5 — week-number column
        for key in sorted(coordinates):
            if key.startswith("WeekNum_"):
                wn = self._week_numbers.get(key)
                if wn is not None:
                    x, y, w, h = coordinates[key]
                    self._draw_week_number(config, x, y, w, h, wn)

        # Pass 6 — header row (week-number header + weekday labels)
        self._draw_headers(config, coordinates)

        return 0, []

    # ------------------------------------------------------------------
    # Base shading (month banding + weekends)
    # ------------------------------------------------------------------

    def _draw_base_shading(self, config: CalendarConfig, cell_state: list) -> None:
        """Shade day cells by month band and/or weekend, under the rule shade."""
        theme = config.theme_v3
        month_colors = theme.palettes.month_colors if config.theme_v3.candybar.month_shading else {}
        weekend = theme.holidays.weekend
        weekend_on = bool(weekend.color) and not _is_none_color(weekend.color)

        if not month_colors and not weekend_on:
            return

        for x, y, w, h, daykey, _style in cell_state:
            year = int(daykey[0:4])
            month = int(daykey[4:6])
            day = int(daykey[6:8])

            # Month banding: each calendar month takes its own palette colour.
            if month_colors:
                color = month_colors.get(f"{month:02d}")
                if color and not _is_none_color(color):
                    self._draw_rect(
                        x,
                        y,
                        w,
                        h,
                        fill=color,
                        fill_opacity=theme.shading.month_opacity,
                        css_class="ec-month-band",
                    )

            # Weekend column tint (Sat=5, Sun=6); only present when shown.
            if weekend_on:
                from datetime import date

                if date(year, month, day).weekday() >= 5:
                    self._draw_rect(
                        x,
                        y,
                        w,
                        h,
                        fill=weekend.color,
                        fill_opacity=weekend.opacity,
                        css_class="ec-weekend",
                    )

    # ------------------------------------------------------------------
    # Grid
    # ------------------------------------------------------------------

    def _draw_grid(self, config: CalendarConfig, coordinates: CoordinateDict) -> None:
        if not config.theme_v3.candybar.grid_lines:
            return
        color = config.theme_v3.lines.grid.color
        if _is_none_color(color):
            return
        for key, (x, y, w, h) in coordinates.items():
            if key.startswith(
                (
                    "Cell_",
                    "WeekNum_",
                    "WeekNumHeader_",
                    "DayHeader_",
                )
            ):
                self._draw_rect(
                    x,
                    y,
                    w,
                    h,
                    fill="none",
                    stroke=color,
                    stroke_width=0.5,
                    css_class="ec-grid-line",
                )

    # ------------------------------------------------------------------
    # Header
    # ------------------------------------------------------------------

    def _draw_headers(self, config: CalendarConfig, coordinates: CoordinateDict) -> None:
        _ts_label = config.get_text_style("ec-label")
        tk_label = self._tk("text:label")
        label_font = tk_label.get("font") or _ts_label.font
        label_size = tk_label.get("size")
        label_color = tk_label.get("color") or _ts_label.color

        _ts_wn = config.get_text_style("ec-week-number")
        tk_wn = self._tk("text:week_number")

        # Per-chunk weekday labels come from the shared column geometry so the
        # column order (week start + weekend suppression) matches the layout.
        cols = compute_columns(config, 0.0, 1.0)  # only need day_labels here

        for key in sorted(coordinates):
            if key.startswith("WeekNumHeader_"):
                x, y, w, h = coordinates[key]
                self._draw_text(
                    x + w / 2,
                    y + h * 0.7,
                    "W#",
                    tk_wn.get("font") or _ts_wn.font,
                    label_size,
                    fill=tk_wn.get("color") or _ts_wn.color,
                    anchor="middle",
                    css_class="ec-label",
                )
            elif key.startswith("DayHeader_"):
                x, y, w, h = coordinates[key]
                idx = int(key.rsplit("_", 1)[1])
                if 0 <= idx < len(cols.day_labels):
                    self._draw_text(
                        x + w / 2,
                        y + h * 0.7,
                        cols.day_labels[idx],
                        label_font,
                        label_size,
                        fill=label_color,
                        anchor="middle",
                        css_class="ec-label",
                    )

    # ------------------------------------------------------------------
    # Month box
    # ------------------------------------------------------------------

    @staticmethod
    def _month_row(config: CalendarConfig):
        """The timescale row that makes the month column: the first ``month`` row on the primary side."""
        return next((r for r in config.theme_v3.timescale.primary if r.unit == "month"), None)

    def _draw_month_column(self, config: CalendarConfig, coordinates: CoordinateDict) -> None:
        """Lay the month row of the timescale down each strip's week rows.

        A strip's rows are positions on a vertical span, each owned by the last
        visible day of its week, so the engine groups consecutive rows of one
        month into a single cell and styles it like any month row.
        """
        row = self._month_row(config)
        if row is None:
            return
        theme = config.theme_v3
        ctx = ScaleContext(theme, config, self._db, [])
        rows_by_chunk: dict[str, list[tuple[date, tuple[float, float, float, float]]]] = {}
        for key, rect in coordinates.items():
            if key.startswith("MonthRow_"):
                _, chunk, stamp = key.split("_")
                day = date(int(stamp[:4]), int(stamp[4:6]), int(stamp[6:8]))
                rows_by_chunk.setdefault(chunk, []).append((day, rect))
        for chunk_rows in rows_by_chunk.values():
            chunk_rows.sort(key=lambda item: item[0])
            days = [d for d, _ in chunk_rows]
            x, _, width, _ = chunk_rows[0][1]
            top = min(r[1] for _, r in chunk_rows)
            bottom = max(r[1] + r[3] for _, r in chunk_rows)
            frame = Frame(Span(days, top, bottom), Orientation.VERTICAL, x)
            column = replace(row, height=width)
            plan = plan_rows([column], frame.span, ctx, full_days=days, min_segment_width=0)
            draw_cells(self, plan, frame, x)
