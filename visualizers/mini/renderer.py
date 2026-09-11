"""
SVG renderer for mini calendar visualization.

Draws compact monthly calendars with day-number formatting driven by
events, holidays, and special days via the DayStyle system.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import arrow

from renderers.svg_base import BaseSVGRenderer, _is_none_color
from visualizers.mini.day_styles import DayStyleResolver, DayStyle
from config.config import day_short, weekend_style_is_workweek, weekend_style_starts_sunday
from shared.date_utils import (
    format_arrow_date,
    index_events_by_day as _index_events_by_day,
)
from renderers import event_listing
from shared.rule_engine import StyleEngine

if TYPE_CHECKING:
    from config.config import CalendarConfig
    from shared.db_access import CalendarDB
    from visualizers.base import CoordinateDict

logger = logging.getLogger(__name__)


def _mini_style_rules(config: "CalendarConfig") -> list:
    """Return the raw style_rules list to feed StyleEngine.

    Prefers the parsed UnifiedTheme's section so the renderer no longer
    depends on the legacy ``theme_style_rules`` field.
    """
    theme = getattr(config, "theme", None)
    if theme is not None:
        rules = theme.sections.get("style_rules")
        if isinstance(rules, list):
            return rules
    return list(getattr(config, "theme_style_rules", None) or [])


class MiniCalendarRenderer(BaseSVGRenderer):
    """
    Renderer for mini calendar visualization.

    Draws month titles, day-of-week headers, styled day numbers,
    week numbers, and duration color bars.
    """

    # Tokens pre-resolved once per render; see BaseSVGRenderer._populate_tokens.
    # Candybar inherits these (it reuses the mini decoration engine).
    TOKEN_VISUALIZER = "mini"
    TOKENS = (
        "text:day_number", "text:month_title", "text:week_number",
        "text:label", "text:fiscal_label", "text:event_name",
        "text:event_notes", "text:event_date", "text:heading",
        "text:holiday_title",
        "box:day", "box:cell",
        "line:grid", "line:hash", "line:strikethrough", "line:separator",
        "line:duration_bar",
        "icon:milestone", "icon:event",
    )

    def __init__(self):
        super().__init__()
        self._week_numbers: dict[str, int] = {}

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
        self._populate_tokens(config)
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

        # First pass: month outlines (drawn behind titles, headers, cells).
        # The outline is a mini-specific border around the whole month grid
        # (not the cell stroke), so no unified token applies — these reads
        # stay on CalendarConfig and will be reconsidered in Phase 2.
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

        # Resolve every cell's DayStyle once, then render in three sub-passes
        # so duration bars land between the day-cell background (shade,
        # patterns, grid lines) and the foreground (numbers, circles, icons).
        # Drawing patterns inside _draw_day_cell after _draw_all_duration_bars
        # painted the bars on top of the duration line.
        cell_render_state: list[tuple[float, float, float, float, int, DayStyle]] = []
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
            cell_render_state.append((x, y, w, h, day_num, style))

        # Pass 3a: day-cell backgrounds (shade, SVG patterns, hash, grid lines)
        for x, y, w, h, day_num, style in cell_render_state:
            self._draw_day_cell_background(config, x, y, w, h, style)

        # Pass 3b: duration bars (drawn over backgrounds, under foregrounds)
        if config.includedurations:
            self._draw_all_duration_bars(config, coordinates, events)

        # Pass 3c: day-cell foregrounds (numbers, circles, boxes, icons)
        for x, y, w, h, day_num, style in cell_render_state:
            self._draw_day_cell_foreground(config, x, y, w, h, day_num, style)

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
            # The listing paginates, so it is worth as many pages as it took.
            result.page_count += self._render_details_svg(
                config, coordinates, events, db
            )
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
        title = format_arrow_date(dt, config.mini_title_format)

        tk = self._tk("text:month_title")
        _ts = config.get_text_style("ec-month-title")
        self._draw_text(
            x + w / 2,
            y + h * 0.8,
            title,
            tk.get("font") or _ts.font,
            tk.get("size"),
            fill=tk.get("color") or _ts.color,
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
        tk_label = self._tk("text:label")
        header_size = tk_label.get("size")

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
            tk_wn = self._tk("text:week_number")
            self._draw_text(
                x + wn_col_width / 2,
                y + h * 0.75,
                "W#",
                tk_wn.get("font") or _ts_wn.font,
                tk_wn.get("size"),
                fill=tk_wn.get("color") or _ts_wn.color,
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
                tk_label.get("font") or _ts_label.font,
                header_size,
                fill=tk_label.get("color") or _ts_label.color,
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
        self._ensure_tokens(config)
        _ts = config.get_text_style("ec-week-number")
        tk = self._tk("text:week_number")
        font_size = tk.get("size")
        try:
            label = config.mini_week_number_label_format.format(num=wn_value)
        except (KeyError, ValueError):
            label = f"W{wn_value}"

        self._draw_text(
            x + w / 2,
            y + (h / 2) + (font_size / 3),
            label,
            tk.get("font") or _ts.font,
            font_size,
            fill=tk.get("color") or _ts.color,
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

        Combines the background pass (shade, patterns, grid lines) with the
        foreground pass (numbers, circles, icons, etc.).  Callers wanting to
        sandwich other artwork between them should call
        :meth:`_draw_day_cell_background` and :meth:`_draw_day_cell_foreground`
        directly — see :meth:`_render_content` for the layered ordering.
        """
        self._ensure_tokens(config)
        self._draw_day_cell_background(config, x, y, w, h, style)
        self._draw_day_cell_foreground(config, x, y, w, h, day_num, style)

    def _draw_day_cell_background(
        self,
        config: CalendarConfig,
        x: float,
        y: float,
        w: float,
        h: float,
        style: DayStyle,
    ) -> None:
        """Draw the layers that belong *under* duration bars.

        Order (back to front):
        1. Background shade
        2. SVG pattern decorations
        3. Legacy hash pattern
        4. Grid line (if enabled)
        """
        tk_grid = self._tk("line:grid")

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
            grid_stroke_width = float(
                tk_grid.get("width") if tk_grid.get("width") is not None
                else _ls_grid.width
            )
            inset = grid_stroke_width / 2
            self._draw_rect(
                x + inset,
                y + inset,
                max(0.0, w - grid_stroke_width),
                max(0.0, h - grid_stroke_width),
                fill="none",
                stroke=tk_grid.get("color") or _ls_grid.color,
                stroke_width=grid_stroke_width,
                stroke_opacity=float(
                    tk_grid.get("opacity") if tk_grid.get("opacity") is not None
                    else _ls_grid.opacity
                ),
                stroke_dasharray=tk_grid.get("dasharray") or _ls_grid.dasharray or None,
                css_class="ec-day-box",
            )

    def _resolve_day_number_color(
        self, config: CalendarConfig, token_style: dict
    ) -> str:
        """Base day-number color, before any per-day override.

        One chain for the whole mini family (mini, mini-icon, candybar), so a
        theme colors every one of them the same way: the ``text:day_number``
        token, then an ``ec-day-number`` element binding, then
        ``colors.mini_calendar.day_color``, then ``mini_calendar.day_color``.
        mini-icon used to skip the element binding and mini/candybar used to
        skip ``colors.mini_calendar.day_color``, so the same theme could paint
        the views differently.

        Per-day overrides — adjacent month, holiday, resource group, a
        ``style_rules`` entry — arrive as ``DayStyle.text_color`` and win over
        whatever this returns.

        Args:
            token_style: the already-resolved ``text:day_number`` token dict
                (the two renderers resolve tokens by different routes).
        """
        return token_style.get("color") or config.get_element_color(
            "ec-day-number",
            config.theme_mini_day_color or config.mini_day_color,
        )

    def _draw_day_cell_foreground(
        self,
        config: CalendarConfig,
        x: float,
        y: float,
        w: float,
        h: float,
        day_num: int,
        style: DayStyle,
    ) -> None:
        """Draw the layers that belong *over* duration bars.

        Order (back to front):
        5. Circle (if milestone)
        6. Box around number (if boxed)
        7. Day number text or replacement icon
        7b. Fiscal period start label
        8. Strikethrough line
        """
        tk_day = self._tk("text:day_number")
        tk_milestone = self._tk("icon:milestone")
        default_color = self._resolve_day_number_color(config, tk_day)

        # The day number is always drawn. An event's icon used to stand in
        # for it, which cost the cell the one thing every cell has to say;
        # icons now go in the corners around it (step 7c).
        display_text = self._format_day_number(day_num, config)

        # Determine font
        _ts_day = config.get_text_style("ec-day-number")
        if style.font_name:
            font = style.font_name
        elif style.bold:
            font = config.mini_cell_bold_font
        else:
            font = tk_day.get("font") or _ts_day.font

        # Determine color and opacity
        text_color = style.text_color or default_color
        text_opacity = style.text_opacity

        # Position: centered in cell (horizontally and vertically)
        cx = x + w / 2
        cy = y + h / 2
        # Vertical centering: place baseline at cell midpoint, adjusted
        # down by ~1/3 of font size (baseline sits below the visual center in SVG Y-down)
        font_size = tk_day.get("size")
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
                stroke_width=float(
                    tk_milestone.get("stroke_width")
                    if tk_milestone.get("stroke_width") is not None
                    else _ls_milestone.width
                ),
                stroke_opacity=float(
                    tk_milestone.get("stroke_opacity")
                    if tk_milestone.get("stroke_opacity") is not None
                    else _ls_milestone.opacity
                ),
                css_class="ec-milestone-marker",
            )

        # 6. Box around number
        if style.boxed:
            from renderers.text_utils import string_width
            from config.config import get_font_path

            font_path = get_font_path(font)
            tw = string_width(display_text, font_path, font_size)
            box_pad = 2.0
            box_x = cx - tw / 2 - box_pad
            box_w = tw + 2 * box_pad
            box_h = font_size * 1.2
            box_y_svg = text_y - box_h + font_size * 0.2
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
        if style.outlined:
            # Outlined: draw with very low opacity fill, rely on stroke
            # Since text_to_svg_group produces <path> elements, we
            # can't directly set stroke on them via _draw_text.
            # Instead, draw normally with reduced opacity for an outline effect.
            self._draw_text(
                cx,
                text_y,
                display_text,
                font,
                font_size,
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
                font_size,
                fill=text_color,
                fill_opacity=text_opacity,
                anchor="middle",
                css_class=day_num_css,
            )

        # 7c. Corner icons, over the day number.
        self._draw_corner_icons(config, x, y, w, h, style, text_color)

        # 7b. Fiscal period start label (small text at bottom of cell)
        if style.fiscal_period_label:
            _ts_fiscal = config.get_text_style("ec-fiscal-label")
            tk_fiscal = self._tk("text:fiscal_label")
            label_font_size = max(
                4.0, tk_fiscal.get("size") or font_size * 0.6
            )
            label_y = y + h - label_font_size * 0.3
            self._draw_text(
                cx,
                label_y,
                style.fiscal_period_label,
                tk_fiscal.get("font") or _ts_fiscal.font,
                label_font_size,
                fill=tk_fiscal.get("color") or _ts_fiscal.color,
                fill_opacity=0.85,
                anchor="middle",
                css_class="ec-fiscal-label",
            )

        # 7. Strikethrough
        if style.strikethrough:
            from renderers.text_utils import string_width
            from config.config import get_font_path

            font_path = get_font_path(font)
            tw = string_width(display_text, font_path, font_size)
            strike_y = text_y + font_size * 0.3
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

    # _draw_circle() is inherited from BaseSVGRenderer.

    #: Corner order for a cell's icons: top-right first, then clockwise.
    #: Each entry is the (x, y) corner as fractions of the cell, so the
    #: geometry reads the same for any cell size.
    _ICON_CORNERS = ((1, 0), (1, 1), (0, 1), (0, 0))

    def _draw_corner_icons(
        self,
        config: "CalendarConfig",
        x: float,
        y: float,
        w: float,
        h: float,
        style: DayStyle,
        default_color: str,
    ) -> None:
        """Draw a day's event / holiday icons in the cell's corners.

        Up to four — one per corner, filled top-right first and then
        clockwise, highest-ranked icon in the first corner.  A fifth icon on
        one day has nowhere to go and is dropped; ``corner_icons`` sheds the
        lowest-ranked ones so what survives is what the reader most needs.

        The icons are drawn over the day number at
        ``mini_calendar.event_icon_opacity`` so the number stays readable
        underneath — a cell that shows only an icon has lost the one thing
        every cell has to say, which is what these used to do.
        """
        icons = style.corner_icons(len(self._ICON_CORNERS))
        if not icons:
            return

        scale = max(0.0, float(config.mini_event_icon_scale))
        size = min(w, h) * scale
        if size <= 0:
            return
        opacity = max(0.0, min(1.0, float(config.mini_event_icon_opacity)))
        # Half a stroke keeps an icon off the grid line it would otherwise
        # sit on; the cell's own inset is already applied by the caller.
        pad = config.mini_grid_line_width

        for icon, (fx, fy) in zip(icons, self._ICON_CORNERS):
            cx = x + pad + (size / 2.0) if fx == 0 else x + w - pad - (size / 2.0)
            cy = y + pad + (size / 2.0) if fy == 0 else y + h - pad - (size / 2.0)
            self._draw_icon_svg(
                icon.name,
                cx,
                self._icon_baseline(cy, size),
                size,
                anchor="middle",
                color=default_color,
                fallback_name=config.default_missing_icon,
                fallback_size=config.default_missing_icon_size,
                fallback_color=default_color,
                css_class="ec-event-icon",
                opacity=opacity,
            )

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

    # _ensure_svg_pattern_def() is inherited from BaseSVGRenderer; the
    # pattern string helpers live in renderers/svg_patterns.py.

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

        # Assign a distinct color and StyleResult to each duration event.
        palette = config.group_colors or ["lightsteelblue"]
        style_engine = StyleEngine(_mini_style_rules(config))
        from visualizers.mini.day_styles import DayStyleResolver
        from shared.rule_engine import StyleResult
        event_styles: dict[int, tuple[str, StyleResult]] = {}
        for idx, event in enumerate(duration_events):
            color = palette[idx % len(palette)]
            sr = StyleResult()
            try:
                evt_obj = DayStyleResolver._dict_to_event(event)
                sr = style_engine.evaluate_event(evt_obj)
                if sr.fill_color:
                    color = sr.fill_color
            except Exception:
                pass
            event_styles[id(event)] = (color, sr)

        # Build a day -> list of (color, StyleResult) per overlapping duration.
        bars_by_day: dict[str, list[tuple[str, StyleResult]]] = {}
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
            bar_entry = event_styles.get(id(event), ("lightsteelblue", StyleResult()))

            for dt in arrow.Arrow.range("day", s_arrow, e_arrow):
                daykey = dt.format("YYYYMMDD")
                bars_by_day.setdefault(daykey, []).append(bar_entry)

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
        for daykey, entries in bars_by_day.items():
            for cell_key in day_cell_keys.get(daykey, []):
                cx, cy, cw, ch = coordinates[cell_key]
                max_bars = int(ch // (stroke_w + gap)) if stroke_w > 0 else 0
                for idx, (color, sr) in enumerate(entries):
                    if max_bars and idx >= max_bars:
                        break
                    line_y = (cy + ch) - idx * (stroke_w + gap) - stroke_w / 2
                    bar_stroke = sr.stroke_color if sr.stroke_color is not None else color
                    bar_stroke_width = (
                        sr.stroke_width if sr.stroke_width is not None else stroke_w
                    )
                    bar_stroke_opacity = (
                        sr.stroke_opacity
                        if sr.stroke_opacity is not None
                        else _ls_dur.opacity
                    )
                    bar_dash = (
                        sr.stroke_dasharray
                        if sr.stroke_dasharray is not None
                        else (_ls_dur.dasharray or None)
                    )
                    self._draw_line(
                        cx,
                        line_y,
                        cx + cw,
                        line_y,
                        stroke=bar_stroke,
                        stroke_width=bar_stroke_width,
                        stroke_opacity=bar_stroke_opacity,
                        stroke_dasharray=bar_dash,
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
        db: "CalendarDB | None" = None,
    ) -> int:
        """Render the companion details page; returns how many were written.

        The range's events chronologically -- date, name over notes, and
        whatever else the theme's columns ask for -- then the holidays
        and special days the calendar shows.  Built through the shared
        :class:`~renderers.details_page.DetailsPageWriter`, so it is the
        same page the gantt details and weekly overflow companions are,
        with mini's content in it.  Written next to the main output with
        the ``mini_details_output_suffix`` suffix; ``--no-mini-details``
        suppresses it.  The month-grid drawing is restored afterwards.
        """
        from renderers.details_page import (
            DetailsPageWriter,
            details_output_path,
            numbered_page_path,
        )

        self._ensure_tokens(config)
        saved_drawing = self._drawing

        def page_path(number: int) -> str:
            base = details_output_path(
                config.outputfile, config.mini_details_output_suffix
            )
            return numbered_page_path(base, number)

        writer = DetailsPageWriter(
            self, config, coordinates, page_path, config.mini_details_title_text
        )
        columns = self._details_columns(config)

        writer.section(config.mini_details_events_section_text, columns)
        for event in self._details_sorted_events(events):
            writer.row(
                self._details_event_cells(event, len(columns)),
                columns,
                sub_line=(1, self._details_event_note(event)),
            )

        if db is not None:
            extra_rows = self._collect_holiday_special_rows(coordinates, config, db)
            if extra_rows:
                writer.section(config.mini_details_holidays_section_text, columns)
                for row in extra_rows:
                    writer.row(
                        event_listing.holiday_cells(row, len(columns)),
                        columns,
                        sub_line=(1, row.get("notes") or ""),
                    )

        pages = writer.finish()
        self._drawing = saved_drawing
        return pages

    # The listing's content is shared with the compactplan key; these
    # names stay so the details page reads as the renderer's own.
    _details_columns = staticmethod(event_listing.details_columns)
    _details_sorted_events = staticmethod(event_listing.sorted_events)
    _details_event_cells = staticmethod(event_listing.event_cells)
    _details_event_note = staticmethod(event_listing.event_note)

    @staticmethod
    def _collect_holiday_special_rows(
        coordinates: "CoordinateDict",
        config: "CalendarConfig",
        db: "CalendarDB",
    ) -> list[dict]:
        """The holiday + special-day rows for the days the grid shows.

        Walks the primary day-cell coordinates so the result matches what's
        visible on the calendar; see
        :func:`renderers.event_listing.holiday_special_rows`.
        """
        # Primary daykeys only — adjacent-month cells share dates with their
        # owning month elsewhere in the grid and should not double-count.
        daykeys = [
            key[len("Cell_") :]
            for key in coordinates
            if key.startswith("Cell_") and not key.endswith("__adj")
        ]
        return event_listing.holiday_special_rows(daykeys, config, db)
