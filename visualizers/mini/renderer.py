"""
SVG renderer for mini calendar visualization.

Draws compact monthly calendars with day-number formatting driven by
events, holidays, and special days via the DayStyle system.
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

import arrow
import drawsvg

from renderers.svg_base import BaseSVGRenderer, _is_none_color
from visualizers.mini.day_styles import DayStyleResolver, DayStyle
from config.config import day_short, weekend_style_is_workweek, weekend_style_starts_sunday
from shared.date_utils import index_events_by_day as _index_events_by_day
from shared.rule_engine import StyleEngine
from visualizers.weekly.renderer import WeeklyCalendarRenderer

if TYPE_CHECKING:
    from config.config import CalendarConfig
    from shared.db_access import CalendarDB
    from visualizers.base import CoordinateDict

logger = logging.getLogger(__name__)


class MiniCalendarRenderer(BaseSVGRenderer):
    """
    Renderer for mini calendar visualization.

    Draws month titles, day-of-week headers, styled day numbers,
    week numbers, and duration color bars.
    """

    def __init__(self):
        super().__init__()
        self._week_numbers: dict[str, int] = {}
        self._pattern_svg_cache: dict[str, str] = {}
        self._registered_pattern_ids: set[str] = set()

    def set_week_numbers(self, week_numbers: dict[str, int]) -> None:
        """
        Provide pre-computed week number values from the layout.

        Args:
            week_numbers: Dict mapping WeekNum_YYYYMM_R{n} keys to int values.
        """
        self._week_numbers = week_numbers

    def _render_content(
        self,
        config: CalendarConfig,
        coordinates: CoordinateDict,
        events: list,
        db: CalendarDB,
    ) -> tuple[int, list]:
        """
        Render all month grids with styled day numbers.

        Args:
            config: Calendar configuration
            coordinates: Layout coordinates
            events: Event list
            db: Database access instance

        Returns:
            Tuple of (overflow_count, overflow_entries) — always (0, []).
        """
        resolver = DayStyleResolver(config, db)
        self._load_icon_svg_cache(db)
        self._pattern_svg_cache = db.get_all_patterns()
        self._registered_pattern_ids = set()
        effective_events = events if config.includeevents else []
        events_by_day = self._index_events_by_day(effective_events)

        # Determine week start for DOW header rendering
        week_start_sunday = config.mini_week_start == 0 or (
            config.mini_week_start == -1
            and weekend_style_starts_sunday(config.weekend_style)
        )

        # First pass: month outlines (drawn behind titles, headers, cells)
        outline_color = config.mini_month_outline_color
        if outline_color and not _is_none_color(outline_color):
            for key in sorted(coordinates):
                if not key.startswith("MonthGrid_"):
                    continue
                x, y, w, h = coordinates[key]
                self._draw_rect(
                    x, y, w, h,
                    fill="none",
                    stroke=outline_color,
                    stroke_width=config.mini_month_outline_width,
                    stroke_opacity=config.mini_month_outline_opacity,
                    stroke_dasharray=config.mini_month_outline_dasharray or None,
                )

        # Second pass: titles, headers, week numbers
        for key in sorted(coordinates):
            x, y, w, h = coordinates[key]

            if key.startswith("MonthTitle_"):
                month_key = key[len("MonthTitle_") :]
                self._draw_month_title(config, x, y, w, h, month_key)

            elif key.startswith("DowHeader_"):
                self._draw_dow_header(config, x, y, w, h, week_start_sunday)

            elif key.startswith("WeekNum_"):
                wn_value = self._week_numbers.get(key)
                if wn_value is not None:
                    self._draw_week_number(config, x, y, w, h, wn_value)

        # Third pass: duration bars (behind day numbers and icons)
        if config.includedurations:
            self._draw_all_duration_bars(config, coordinates, events)

        # Fourth pass: day cells (day numbers, icons, backgrounds)
        for key in sorted(coordinates):
            if not key.startswith("Cell_"):
                continue
            x, y, w, h = coordinates[key]
            rest = key[len("Cell_") :]
            is_adjacent = rest.endswith("__adj")
            # Extract daykey: may have month_key prefix for adj cells
            if is_adjacent:
                # Format: Cell_YYYYMM_YYYYMMDD__adj
                parts = rest.replace("__adj", "").split("_")
                daykey = parts[-1] if len(parts) > 1 else parts[0]
            else:
                daykey = rest

            day_events = events_by_day.get(daykey, [])
            style = resolver.resolve(daykey, day_events, is_adjacent)

            day_num = int(daykey[6:8])
            self._draw_day_cell(config, x, y, w, h, day_num, style)

        return 0, []

    def render(
        self,
        config: CalendarConfig,
        coordinates: CoordinateDict,
        events: list,
        db: CalendarDB,
    ):
        result = super().render(config, coordinates, events, db)
        if config.include_mini_details:
            effective_events = events if config.includeevents else []
            self._render_details_svg(config, coordinates, effective_events)
            result.page_count += 1
        return result

    # =========================================================================
    # Month title
    # =========================================================================

    def _draw_month_title(
        self,
        config: CalendarConfig,
        x: float,
        y: float,
        w: float,
        h: float,
        month_key: str,
    ) -> None:
        """Draw the YYYY-MM title centered above the month grid."""
        year = int(month_key[:4])
        month = int(month_key[4:6])
        dt = arrow.Arrow(year, month, 1)
        title = dt.format(config.mini_title_format)

        _ts = config.get_text_style("ec-month-title")
        self._draw_text(
            x + w / 2,
            y + h * 0.8,
            title,
            _ts.font,
            config.mini_title_font_size,
            fill=_ts.color,
            anchor="middle",
            css_class="ec-month-title",
        )

    # =========================================================================
    # Day-of-week header
    # =========================================================================

    def _draw_dow_header(
        self,
        config: CalendarConfig,
        x: float,
        y: float,
        w: float,
        h: float,
        week_start_sunday: bool,
    ) -> None:
        """
        Draw the day-of-week abbreviation header row.

        When week numbers are enabled, draws "W#" as the first label
        in a narrower column, with 7 day labels in the remaining space.
        """
        _ts_label = config.get_text_style("ec-label")

        is_workweek = weekend_style_is_workweek(config.weekend_style)
        labels = self._ordered_day_labels(week_start_sunday, is_workweek)
        days_per_week = len(labels)

        show_wn = config.mini_show_week_numbers
        if show_wn:
            day_col_width = w / (days_per_week + 0.6)
            wn_col_width = day_col_width * 0.6
            day_area_x = x + wn_col_width

            # Draw "W#" label
            _ts_wn = config.get_text_style("ec-week-number")
            self._draw_text(
                x + wn_col_width / 2,
                y + h * 0.75,
                "W#",
                _ts_wn.font,
                config.mini_header_font_size,
                fill=_ts_wn.color,
                anchor="middle",
                css_class="ec-label",
            )
        else:
            day_col_width = w / days_per_week
            day_area_x = x

        for i, label in enumerate(labels):
            cx = day_area_x + i * day_col_width + day_col_width / 2
            self._draw_text(
                cx,
                y + h * 0.75,
                label,
                _ts_label.font,
                config.mini_header_font_size,
                fill=_ts_label.color,
                anchor="middle",
                css_class="ec-label",
            )

    @staticmethod
    def _ordered_day_labels(
        week_start_sunday: bool, workweek_only: bool = False
    ) -> list[str]:
        """
        Return weekday labels derived from shared global config values.

        Uses config.config.day_short to keep mini headers configurable from one place.
        When ``workweek_only`` is True, drops Sat and Sun from the returned list.
        """
        labels = list(day_short)
        if len(labels) != 7:
            labels = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        ordered = [labels[6], *labels[:6]] if week_start_sunday else labels
        if workweek_only:
            # day_short is Mon..Sun, so weekday() < 5 maps to Sat/Sun being the
            # last two positions in Monday-start ordering and the first/last
            # positions in Sunday-start ordering. Filter by the source weekday
            # rather than position to stay correct under both orderings.
            mon_to_sun = labels  # canonical Mon..Sun
            wd = [mon_to_sun.index(lbl) for lbl in ordered]
            return [lbl for lbl, w in zip(ordered, wd) if w < 5]
        return ordered

    # =========================================================================
    # Week number cell
    # =========================================================================

    def _draw_week_number(
        self,
        config: CalendarConfig,
        x: float,
        y: float,
        w: float,
        h: float,
        wn_value: int,
    ) -> None:
        """Draw a week number in the W# column cell."""
        _ts = config.get_text_style("ec-week-number")
        font_size = config.mini_week_number_font_size
        try:
            label = config.mini_week_number_label_format.format(num=wn_value)
        except (KeyError, ValueError):
            label = f"W{wn_value}"

        self._draw_text(
            x + w / 2,
            y + (h / 2) + (font_size / 3),
            label,
            _ts.font,
            font_size,
            fill=_ts.color,
            anchor="middle",
            css_class="ec-week-number",
        )

    # =========================================================================
    # Day cell rendering
    # =========================================================================

    def _draw_day_cell(
        self,
        config: CalendarConfig,
        x: float,
        y: float,
        w: float,
        h: float,
        day_num: int,
        style: DayStyle,
    ) -> None:
        """
        Draw a single day cell with all visual treatments from DayStyle.

        Rendering order (back to front):
        1. Background shade
        2. Hash pattern
        3. SVG pattern decorations
        4. Legacy hash pattern
        5. Grid line (if enabled)
        6. Circle (if milestone)
        7. Box (if boxed)
        8. Day number text (with bold/outlined/color/font overrides)
        9. Strikethrough line
        10. Icon (append or replace)
        """
        default_color = config.get_element_color("ec-day-number", config.mini_day_color)

        # 1. Background shade
        if style.shade_color and not _is_none_color(style.shade_color):
            self._draw_rect(
                x,
                y,
                w,
                h,
                fill=style.shade_color,
                fill_opacity=style.shade_opacity,
                css_class="ec-cell",
            )

        # 2. SVG pattern decorations
        for dec in style.hash_decorations:
            self._draw_mini_svg_pattern(
                config,
                x,
                y,
                w,
                h,
                dec.pattern,
                dec.color,
                dec.opacity,
            )

        # 3. Legacy hash pattern
        if style.hash_pattern > 0:
            self._draw_mini_hash_lines(config, x, y, w, h)

        # 4. Grid lines
        if config.mini_grid_lines:
            _ls_grid = config.get_line_style("ec-grid-line")
            grid_stroke_width = _ls_grid.width
            inset = grid_stroke_width / 2
            self._draw_rect(
                x + inset,
                y + inset,
                max(0.0, w - grid_stroke_width),
                max(0.0, h - grid_stroke_width),
                fill="none",
                stroke=_ls_grid.color,
                stroke_width=grid_stroke_width,
                stroke_opacity=_ls_grid.opacity,
                stroke_dasharray=_ls_grid.dasharray or None,
                css_class="ec-day-box",
            )

        # Determine text to display
        display_text = self._format_day_number(day_num, config)
        replace_icon_name = style.icon_replace or style.icon_append
        has_replace_icon = bool(self._resolve_icon_svg(replace_icon_name))
        if has_replace_icon:
            display_text = ""

        # Determine font
        _ts_day = config.get_text_style("ec-day-number")
        if style.font_name:
            font = style.font_name
        elif style.bold:
            font = config.mini_cell_bold_font
        else:
            font = _ts_day.font

        # Determine color and opacity
        text_color = style.text_color or default_color
        text_opacity = style.text_opacity

        # Position: centered in cell (horizontally and vertically)
        cx = x + w / 2
        cy = y + h / 2
        # Vertical centering: place baseline at cell midpoint, adjusted
        # down by ~1/3 of font size (baseline sits below the visual center in SVG Y-down)
        font_size = config.mini_cell_font_size
        text_y = cy + (font_size / 3)

        # 5. Circle (milestone)
        if style.circled:
            _ls_milestone = config.get_line_style("ec-milestone-marker")
            radius = min(w, h) * 0.38
            self._draw_circle(
                cx,
                cy,
                radius,
                stroke=style.circle_color,
                fill=style.circle_fill or "none",
                stroke_width=_ls_milestone.width,
                stroke_opacity=_ls_milestone.opacity,
                css_class="ec-milestone-marker",
            )

        # 6. Box around number
        if style.boxed:
            from renderers.text_utils import string_width
            from config.config import get_font_path

            font_path = get_font_path(font)
            tw = string_width(display_text, font_path, config.mini_cell_font_size)
            box_pad = 2.0
            box_x = cx - tw / 2 - box_pad
            box_w = tw + 2 * box_pad
            box_h = config.mini_cell_font_size * 1.2
            box_y_svg = text_y - box_h + config.mini_cell_font_size * 0.2
            self._draw_rect(
                box_x,
                box_y_svg,
                box_w,
                box_h,
                fill="none",
                stroke=style.box_color,
                stroke_width=0.75,
                stroke_dasharray=config.get_box_style("ec-cell").stroke_dasharray or None,
                css_class="ec-day-box",
            )

        # 7. Draw day number text
        day_num_css = "ec-day-number ec-adjacent" if style.is_adjacent_month else "ec-day-number"
        if has_replace_icon:
            icon_size = config.mini_cell_font_size * 0.85
            icon_baseline_y = cy + (icon_size * 0.30)
            self._draw_icon_svg(
                replace_icon_name,
                cx,
                icon_baseline_y,
                icon_size,
                anchor="middle",
                color=text_color,
                css_class="ec-event-icon",
            )
        elif style.outlined:
            # Outlined: draw with very low opacity fill, rely on stroke
            # Since text_to_svg_group produces <path> elements, we
            # can't directly set stroke on them via _draw_text.
            # Instead, draw normally with reduced opacity for an outline effect.
            self._draw_text(
                cx,
                text_y,
                display_text,
                font,
                config.mini_cell_font_size,
                fill=text_color,
                fill_opacity=0.15,
                anchor="middle",
                css_class=day_num_css,
            )
        else:
            self._draw_text(
                cx,
                text_y,
                display_text,
                font,
                config.mini_cell_font_size,
                fill=text_color,
                fill_opacity=text_opacity,
                anchor="middle",
                css_class=day_num_css,
            )

        # 7b. Fiscal period start label (small text at bottom of cell)
        if style.fiscal_period_label:
            _ts_fiscal = config.get_text_style("ec-fiscal-label")
            label_font_size = max(
                4.0,
                (config.fiscal_period_label_font_size or config.mini_cell_font_size * 0.6),
            )
            label_y = y + h - label_font_size * 0.3
            self._draw_text(
                cx,
                label_y,
                style.fiscal_period_label,
                _ts_fiscal.font,
                label_font_size,
                fill=_ts_fiscal.color,
                fill_opacity=0.85,
                anchor="middle",
                css_class="ec-fiscal-label",
            )

        # 7. Strikethrough
        if style.strikethrough:
            from renderers.text_utils import string_width
            from config.config import get_font_path

            font_path = get_font_path(font)
            tw = string_width(display_text, font_path, config.mini_cell_font_size)
            strike_y = text_y + config.mini_cell_font_size * 0.3
            self._draw_line(
                cx - tw / 2,
                strike_y,
                cx + tw / 2,
                strike_y,
                stroke=text_color,
                stroke_width=0.75,
                stroke_dasharray=config.get_line_style("ec-strikethrough").dasharray or None,
                css_class="ec-strikethrough",
            )

    # =========================================================================
    # Drawing helpers
    # =========================================================================

    def _draw_circle(
        self,
        cx: float,
        cy: float,
        radius: float,
        stroke: str = "black",
        fill: str = "none",
        stroke_width: float = 1.0,
        stroke_opacity: float = 1.0,
        css_class: str | None = None,
    ) -> None:
        """
        Draw a circle in SVG coordinates.

        Args:
            cx: Center X in SVG coordinates
            cy: Center Y in SVG coordinates (origin top-left, Y-down)
            radius: Circle radius in points
            stroke: Stroke color
            fill: Fill color
            stroke_width: Stroke width
            stroke_opacity: Stroke opacity
            css_class: Optional CSS class name(s) for the element
        """
        if _is_none_color(stroke) and _is_none_color(fill):
            return
        extra: dict = {}
        if css_class:
            extra["class_"] = css_class
        circle = drawsvg.Circle(
            cx,
            cy,
            radius,
            fill=fill,
            stroke=stroke,
            stroke_width=stroke_width,
            stroke_opacity=stroke_opacity,
            **extra,
        )
        self._drawing.append(circle)

    def _draw_mini_hash_lines(
        self,
        config: "CalendarConfig",
        x: float,
        y: float,
        w: float,
        h: float,
    ) -> None:
        """Draw simplified hash pattern lines for small cells."""
        divisions = 5
        lines: list[tuple[float, float, float, float]] = []
        for i in range(divisions + 1):
            frac = i / divisions
            # Diagonal lines (top-left to bottom-right) in SVG coordinates (Y-down)
            lines.append((x, y + h * (1 - frac), x + w * frac, y + h))
            lines.append((x + w * frac, y, x + w, y + h * (1 - frac)))

        if lines:
            self._draw_lines(
                lines,
                stroke="lightgrey",
                stroke_width=0.3,
                stroke_opacity=0.5,
                stroke_dasharray=config.get_line_style("ec-hash-line").dasharray or None,
                css_class="ec-hash-line",
            )

    @staticmethod
    def _format_day_number(day_num: int, config: "CalendarConfig") -> str:
        """Format a mini SVG day number with optional digit substitutions."""
        glyphs = config.mini_day_number_glyphs
        if glyphs and len(glyphs) >= 31 and 1 <= day_num <= 31:
            try:
                return str(glyphs[day_num - 1])
            except (TypeError, ValueError, IndexError):
                return str(day_num)
        digits = config.mini_day_number_digits
        if digits and len(digits) == 10:
            try:
                return "".join(digits[int(d)] for d in str(day_num))
            except (TypeError, ValueError, IndexError):
                return str(day_num)
        return str(day_num)

    @staticmethod
    def _parse_svg_tile_size(svg: str) -> tuple[float, float]:
        """Extract tile width and height from a pattern SVG."""
        return WeeklyCalendarRenderer._parse_svg_tile_size(svg)

    @staticmethod
    def _colorize_pattern_svg(svg: str, color: str | None) -> str:
        """Replace black fills in a pattern SVG with the requested color."""
        return WeeklyCalendarRenderer._colorize_pattern_svg(svg, color)

    def _ensure_svg_pattern_def(
        self,
        pattern_name: str,
        color: str | None,
    ) -> str | None:
        """Register a named SVG pattern in defs and return its id."""
        raw_svg = self._pattern_svg_cache.get(pattern_name)
        if not raw_svg:
            return None

        safe_color = (color or "black").replace("#", "").replace(" ", "_")
        safe_name = re.sub(r"[^a-zA-Z0-9_-]", "_", pattern_name)
        pat_id = f"pat-{safe_name}-{safe_color}"

        if pat_id in self._registered_pattern_ids:
            return pat_id

        tile_w, tile_h = self._parse_svg_tile_size(raw_svg)
        colorized = self._colorize_pattern_svg(raw_svg, color)
        inner = re.sub(r"<\?xml[^>]*\?>", "", colorized)
        inner = re.sub(r"<!DOCTYPE[^>]*>", "", inner)
        inner = re.sub(r"<svg[^>]*>", "", inner, count=1)
        inner = inner.rsplit("</svg>", 1)[0].strip()

        pattern_xml = (
            f'<pattern id="{pat_id}" x="0" y="0" '
            f'width="{tile_w}" height="{tile_h}" '
            f'patternUnits="userSpaceOnUse">'
            f"{inner}"
            f"</pattern>"
        )
        self._drawing.append_def(drawsvg.Raw(pattern_xml))
        self._registered_pattern_ids.add(pat_id)
        return pat_id

    def _draw_mini_svg_pattern(
        self,
        config: "CalendarConfig",
        x: float,
        y: float,
        w: float,
        h: float,
        pattern_name: str,
        color: str | None,
        opacity: float | None = None,
    ) -> None:
        """Draw an SVG pattern across the full mini day cell."""
        pat_id = self._ensure_svg_pattern_def(pattern_name, color)
        if not pat_id:
            logger.warning("SVG pattern '%s' not found in database", pattern_name)
            return

        effective_opacity = (
            opacity if opacity is not None else config.hash_pattern_opacity
        )
        self._draw_rect(
            x,
            y,
            w,
            h,
            fill=f"url(#{pat_id})",
            fill_opacity=effective_opacity,
            stroke="none",
            css_class="ec-pattern-fill",
        )

    # =========================================================================
    # Duration bars
    # =========================================================================

    def _draw_all_duration_bars(
        self,
        config: CalendarConfig,
        coordinates: CoordinateDict,
        events: list,
    ) -> None:
        """
        Draw duration bar lines for multi-day events.

        For each multi-day event, finds the cells it spans and draws
        stacked horizontal lines with configurable stroke attributes.
        """
        duration_events = []
        for event in events:
            start = event.get("Start", "")
            end = event.get("End", event.get("Finish", ""))
            if not start or not end:
                continue
            start = start[:8]
            end = end[:8]
            if start == end:
                continue
            duration_events.append(event)

        if not duration_events:
            return

        # Assign a distinct color to each duration event (cycle palette if needed)
        palette = config.group_colors or ["lightsteelblue"]
        style_engine = StyleEngine(config.theme_style_rules or [])
        from visualizers.mini.day_styles import DayStyleResolver
        event_colors: dict[int, str] = {}
        for idx, event in enumerate(duration_events):
            color = palette[idx % len(palette)]
            try:
                evt_obj = DayStyleResolver._dict_to_event(event)
                sr = style_engine.evaluate_event(evt_obj)
                if sr.fill_color:
                    color = sr.fill_color
            except Exception:
                pass
            event_colors[id(event)] = color

        # Build a day -> list of bar colors (one entry per overlapping duration)
        bars_by_day: dict[str, list[str]] = {}
        for event in duration_events:
            start = event.get("Start", "")[:8]
            end = event.get("End", event.get("Finish", ""))[:8]
            if not start or not end:
                continue

            try:
                s_arrow = arrow.get(start, "YYYYMMDD")
                e_arrow = arrow.get(end, "YYYYMMDD")
            except Exception:
                continue

            # Use palette-based color to ensure distinct bars
            bar_color = event_colors.get(id(event), "lightsteelblue")

            for dt in arrow.Arrow.range("day", s_arrow, e_arrow):
                daykey = dt.format("YYYYMMDD")
                bars_by_day.setdefault(daykey, []).append(bar_color)

        # Build daykey → all cell keys (primary + adjacent) from coordinates.
        # Adjacent keys have format Cell_{month_key}_{daykey}__adj; primary
        # keys have format Cell_{daykey}. Adjacent cells are absent from
        # coordinates when --mini-no-adjacent is active, so that case is
        # handled automatically.
        day_cell_keys: dict[str, list[str]] = {}
        for key in coordinates:
            if not key.startswith("Cell_"):
                continue
            if key.endswith("__adj"):
                # Cell_{month_key}_{daykey}__adj — daykey is the last segment
                inner = key[len("Cell_") :].removesuffix("__adj")
                daykey = inner.split("_")[-1]
            else:
                daykey = key[len("Cell_") :]
            day_cell_keys.setdefault(daykey, []).append(key)

        # Draw stacked bar lines per day (bottom-up) for every matching cell.
        _ls_dur = config.get_line_style("ec-duration-bar")
        stroke_w = config.mini_duration_bar_height  # keep: behavioral dimension, not styling
        gap = stroke_w * 0.5
        for daykey, colors in bars_by_day.items():
            for cell_key in day_cell_keys.get(daykey, []):
                cx, cy, cw, ch = coordinates[cell_key]
                max_bars = int(ch // (stroke_w + gap)) if stroke_w > 0 else 0
                for idx, color in enumerate(colors):
                    if max_bars and idx >= max_bars:
                        break
                    line_y = (cy + ch) - idx * (stroke_w + gap) - stroke_w / 2
                    self._draw_line(
                        cx,
                        line_y,
                        cx + cw,
                        line_y,
                        stroke=color,
                        stroke_width=stroke_w,
                        stroke_opacity=_ls_dur.opacity,
                        stroke_dasharray=_ls_dur.dasharray or None,
                        css_class="ec-duration-bar",
                    )

    # =========================================================================
    # Event indexing
    # =========================================================================

    @staticmethod
    def _index_events_by_day(events: list) -> dict[str, list]:
        """Build a dict mapping YYYYMMDD daykey to list of events on that day."""
        return _index_events_by_day(events)

    # =========================================================================
    # Details page (second SVG)
    # =========================================================================

    def _render_details_svg(
        self,
        config: CalendarConfig,
        coordinates: CoordinateDict,
        events: list,
    ) -> None:
        saved_drawing = self._drawing
        self._drawing = self._create_drawing(config)
        self._content_bbox_svg = None
        self._add_desc(config)
        self._inject_css()
        if config.shrink_to_content:
            self._shrink_drawing_to_content(coordinates)
        if config.watermark_text:
            self._render_text_watermark(config)
        if config.watermark_image:
            self._render_image_watermark(config)
        self._render_decorations(config, coordinates)

        from config.config import resolve_page_margins

        margins = resolve_page_margins(config)
        header_height = (
            round(config.pageY * config.header_percent, 2)
            if config.include_header
            else 0.0
        )
        footer_height = (
            round(config.pageY * config.footer_percent, 2)
            if config.include_footer
            else 0.0
        )

        content_left = margins["left"]
        content_right = config.pageX - margins["right"]
        content_width = content_right - content_left
        content_top = margins["top"] + header_height
        content_bottom = config.pageY - margins["bottom"] - footer_height

        # Title
        _ts_heading = config.get_text_style("ec-heading")
        title_font_size = config.mini_details_title_font_size
        title_text = config.mini_details_title_text
        title_y = content_top + title_font_size + 10
        self._draw_text(
            content_left + content_width / 2,
            title_y,
            title_text,
            _ts_heading.font,
            title_font_size,
            fill=_ts_heading.color,
            anchor="middle",
            css_class="ec-heading",
        )

        # Column layout
        headers = config.mini_details_headers
        widths = config.mini_details_column_widths
        if len(headers) != len(widths):
            headers = [
                "Start Date",
                "Name / Description",
                "Milestone",
                "Priority",
                "Group",
            ]
            widths = [0.16, 0.52, 0.10, 0.10, 0.12]

        total = sum(widths) if widths else 0.0
        if total <= 0:
            widths = [0.16, 0.52, 0.10, 0.10, 0.12]
            total = sum(widths)
        col_widths = [content_width * (w / total) for w in widths]
        col_x = [content_left]
        for w in col_widths[:-1]:
            col_x.append(col_x[-1] + w)

        _ts_det_label = config.get_text_style("ec-label")
        header_font_size = config.mini_details_header_font_size
        header_y = title_y + header_font_size + 6
        _ts_event_name = config.get_text_style("ec-event-name")
        row_font = _ts_event_name.font
        row_font_size = config.mini_details_name_text_font_size
        _ts_event_notes = config.get_text_style("ec-event-notes")
        notes_font = _ts_event_notes.font
        notes_font_size = config.mini_details_notes_text_font_size

        # Header row
        for idx, head in enumerate(headers):
            self._draw_text(
                col_x[idx] + 4,
                header_y,
                head,
                _ts_det_label.font,
                header_font_size,
                fill=_ts_det_label.color,
                css_class="ec-label",
            )

        # Separator
        _ls_sep = config.get_line_style("ec-separator")
        sep_y = header_y + (header_font_size * 0.6)
        self._draw_line(
            content_left,
            sep_y,
            content_right,
            sep_y,
            stroke="grey",
            stroke_opacity=0.5,
            stroke_dasharray=_ls_sep.dasharray or None,
            css_class="ec-separator",
        )

        # Rows
        row_height = row_font_size + notes_font_size + 6
        current_y = sep_y + 15

        def fmt_date(value: str) -> str:
            if value and len(value) >= 8:
                return f"{value[:4]}-{value[4:6]}-{value[6:8]}"
            return value or ""

        events_sorted = sorted(
            events,
            key=lambda e: (
                e.get("Start", ""),
                e.get("End", e.get("Finish", "")),
                e.get("Task_Name", ""),
            ),
        )

        for event in events_sorted:
            if current_y + row_height > content_bottom:
                break

            start = (event.get("Start") or "")[:8]
            end = (event.get("End") or event.get("Finish") or "")[:8]
            start_fmt = fmt_date(start)
            end_fmt = fmt_date(end)

            name = event.get("Task_Name", "") or ""
            milestone = "True" if event.get("Milestone") else ""
            priority = str(event.get("Priority") or "")
            group = str(event.get("Resource_Group") or "")

            name_width = col_widths[1] - 8

            self._draw_text(
                col_x[0] + 4,
                current_y,
                start_fmt,
                row_font,
                row_font_size,
                fill=_ts_event_name.color,
                fill_opacity=_ts_event_name.opacity,
                css_class="ec-event-date",
            )
            self._draw_text(
                col_x[1] + 4,
                current_y,
                name,
                row_font,
                row_font_size,
                fill=_ts_event_name.color,
                fill_opacity=_ts_event_name.opacity,
                max_width=name_width,
                css_class="ec-event-name",
            )
            self._draw_text(
                col_x[2] + 4,
                current_y,
                milestone,
                row_font,
                row_font_size,
                fill=_ts_event_name.color,
                fill_opacity=_ts_event_name.opacity,
                css_class="ec-event-name",
            )
            self._draw_text(
                col_x[3] + 4,
                current_y,
                priority,
                row_font,
                row_font_size,
                fill=_ts_event_name.color,
                fill_opacity=_ts_event_name.opacity,
                css_class="ec-event-name",
            )
            self._draw_text(
                col_x[4] + 4,
                current_y,
                group,
                row_font,
                row_font_size,
                fill=_ts_event_name.color,
                fill_opacity=_ts_event_name.opacity,
                css_class="ec-event-name",
            )

            notes = event.get("Notes") or ""
            detail_line = notes
            if start and end and start != end:
                end_line = f"End: {end_fmt}"
                detail_line = (
                    f"{detail_line} | {end_line}".strip(" |")
                    if detail_line
                    else end_line
                )

            if detail_line:
                self._draw_text(
                    col_x[1] + 4,
                    current_y + (notes_font_size + 2),
                    detail_line,
                    notes_font,
                    notes_font_size,
                    fill=_ts_event_notes.color,
                    fill_opacity=_ts_event_notes.opacity,
                    max_width=name_width,
                    css_class="ec-event-notes",
                )

            current_y += row_height

        # Save details SVG
        if config.outputfile.endswith(".svg"):
            details_path = config.outputfile.replace(
                ".svg", f"{config.mini_details_output_suffix}.svg"
            )
        else:
            details_path = f"{config.outputfile}{config.mini_details_output_suffix}.svg"
        self._drawing.save_svg(details_path)
        self._drawing = saved_drawing
