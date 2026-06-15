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
  * a merged month-name box spanning each month's week rows, whose label
    supports the full SVG text attribute set including rotation.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import arrow

from renderers.svg_base import _is_none_color
from visualizers.mini.renderer import MiniCalendarRenderer
from visualizers.mini.day_styles import DayStyleResolver
from shared.date_utils import (
    format_arrow_date,
    index_events_by_day as _index_events_by_day,
)
from visualizers.candybar.layout import compute_columns

if TYPE_CHECKING:
    from config.config import CalendarConfig
    from shared.db_access import CalendarDB
    from visualizers.base import CoordinateDict


class CandybarRenderer(MiniCalendarRenderer):
    """Renderer for the candybar year-strip."""

    def _render_content(
        self,
        config: "CalendarConfig",
        coordinates: "CoordinateDict",
        events: list,
        db: "CalendarDB",
    ) -> tuple[int, list]:
        self._populate_mini_tokens(config)
        resolver = DayStyleResolver(config, db)
        self._load_icon_svg_cache(db)
        self._pattern_svg_cache = db.get_all_patterns()
        self._registered_pattern_ids = set()
        effective_events = events if config.includeevents else []
        events_by_day = _index_events_by_day(effective_events)

        # Resolve every day cell's style once.
        cell_state: list[tuple[float, float, float, float, str, object]] = []
        for key in sorted(coordinates):
            if not key.startswith("Cell_"):
                continue
            x, y, w, h = coordinates[key]
            daykey = key[len("Cell_"):]
            day_events = events_by_day.get(daykey, [])
            style = resolver.resolve(daykey, day_events, is_adjacent=False)
            cell_state.append((x, y, w, h, daykey, style))

        # Pass 1 — month box fills (behind everything in the right column)
        self._draw_month_boxes(config, coordinates, fills_only=True)

        # Pass 1b — base cell shading (month banding + weekends), drawn under
        # the holiday/rule shade so those override it.
        self._draw_base_shading(config, cell_state)

        # Pass 2 — day-cell backgrounds (shade, SVG patterns, hash)
        for x, y, w, h, daykey, style in cell_state:
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

        # Pass 7 — month-box labels (rotated text)
        self._draw_month_boxes(config, coordinates, fills_only=False)

        return 0, []

    # ------------------------------------------------------------------
    # Base shading (month banding + weekends)
    # ------------------------------------------------------------------

    def _draw_base_shading(self, config: "CalendarConfig", cell_state: list) -> None:
        """Shade day cells by month band and/or weekend, under the rule shade."""
        month_colors = self._resolve_month_shade_colors(config)
        weekend_fill = config.candybar_weekend_fill
        weekend_on = bool(weekend_fill) and not _is_none_color(weekend_fill)

        if not month_colors and not weekend_on:
            return

        for x, y, w, h, daykey, _style in cell_state:
            year = int(daykey[0:4])
            month = int(daykey[4:6])
            day = int(daykey[6:8])

            # Month banding: cycle the palette by absolute calendar month so
            # consecutive months alternate deterministically.
            if month_colors:
                color = month_colors[(year * 12 + month) % len(month_colors)]
                if color and not _is_none_color(color):
                    self._draw_rect(
                        x, y, w, h,
                        fill=color,
                        fill_opacity=config.candybar_month_shade_opacity,
                        css_class="ec-month-band",
                    )

            # Weekend column tint (Sat=5, Sun=6); only present when shown.
            if weekend_on:
                from datetime import date
                if date(year, month, day).weekday() >= 5:
                    self._draw_rect(
                        x, y, w, h,
                        fill=weekend_fill,
                        fill_opacity=config.candybar_weekend_opacity,
                        css_class="ec-weekend",
                    )

    @staticmethod
    def _resolve_month_shade_colors(config: "CalendarConfig") -> list[str]:
        """Return the month-band color cycle, or [] when banding is off."""
        if not config.candybar_month_shading:
            return []
        colors = list(config.candybar_month_shade_colors or [])
        if not colors:
            # Default: every other month gets a subtle tint.
            colors = ["none", "gainsboro"]
        return colors

    # ------------------------------------------------------------------
    # Grid
    # ------------------------------------------------------------------

    def _draw_grid(self, config: "CalendarConfig", coordinates: "CoordinateDict") -> None:
        if not config.candybar_grid_lines:
            return
        color = config.candybar_grid_line_color
        if _is_none_color(color):
            return
        for key, (x, y, w, h) in coordinates.items():
            if key.startswith((
                "Cell_", "WeekNum_", "WeekNumHeader_", "DayHeader_",
            )):
                self._draw_rect(
                    x, y, w, h,
                    fill="none", stroke=color, stroke_width=0.5,
                    css_class="ec-grid-line",
                )

    # ------------------------------------------------------------------
    # Header
    # ------------------------------------------------------------------

    def _draw_headers(self, config: "CalendarConfig", coordinates: "CoordinateDict") -> None:
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
                    x + w / 2, y + h * 0.7, "W#",
                    tk_wn.get("font") or _ts_wn.font, label_size,
                    fill=tk_wn.get("color") or _ts_wn.color,
                    anchor="middle", css_class="ec-label",
                )
            elif key.startswith("DayHeader_"):
                x, y, w, h = coordinates[key]
                idx = int(key.rsplit("_", 1)[1])
                if 0 <= idx < len(cols.day_labels):
                    self._draw_text(
                        x + w / 2, y + h * 0.7, cols.day_labels[idx],
                        label_font, label_size, fill=label_color,
                        anchor="middle", css_class="ec-label",
                    )

    # ------------------------------------------------------------------
    # Month box
    # ------------------------------------------------------------------

    def _draw_month_boxes(
        self,
        config: "CalendarConfig",
        coordinates: "CoordinateDict",
        *,
        fills_only: bool,
    ) -> None:
        for key in sorted(coordinates):
            if not key.startswith("MonthBox_"):
                continue
            x, y, w, h = coordinates[key]
            ym = key.rsplit("_", 1)[1]  # YYYYMM
            year, month = int(ym[:4]), int(ym[4:6])

            if fills_only:
                fill = config.candybar_month_box_fill
                stroke = config.candybar_month_box_stroke
                if (fill and not _is_none_color(fill)) or (
                    stroke and not _is_none_color(stroke)
                ):
                    self._draw_rect(
                        x, y, w, h,
                        fill=fill if (fill and not _is_none_color(fill)) else "none",
                        fill_opacity=config.candybar_month_box_opacity,
                        stroke=stroke if (stroke and not _is_none_color(stroke)) else None,
                        stroke_width=0.5,
                        css_class="ec-month-box",
                    )
                continue

            # Label text
            label = format_arrow_date(arrow.Arrow(year, month, 1), config.candybar_month_format)
            font = config.candybar_month_font
            font_size = config.candybar_month_font_size or max(
                6.0, min(w * 0.55, 12.0)
            )
            cx = x + w / 2
            cy = y + h / 2
            text_y = cy + font_size / 3
            rotation = config.candybar_month_rotation or 0.0
            transform = (
                f"rotate({rotation} {cx:.3f} {cy:.3f})" if rotation else None
            )
            self._draw_text(
                cx, text_y, label, font, font_size,
                fill=config.candybar_month_color,
                fill_opacity=config.candybar_month_opacity,
                anchor=config.candybar_month_anchor,
                transform=transform,
                css_class="ec-month-box-label",
            )
