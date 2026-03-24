"""
SVG renderer for mini-icon calendar visualization.

Like MiniCalendarRenderer but replaces day-number text with icons drawn
from one of the six pre-defined icon sets (squares, darksquare, darkcircles,
circles, squircles, darksquircles).  Icons are loaded from the database icon
cache and scaled to fill each day cell.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from renderers.svg_base import _is_none_color
from visualizers.mini.renderer import MiniCalendarRenderer
from visualizers.mini.day_styles import DayStyle
from config.config import (
    squares,
    darksquare,
    darkcircles,
    circles,
    squircles,
    darksquircles,
)

if TYPE_CHECKING:
    from config.config import CalendarConfig

# Mapping from icon set name (CLI value) → list of 31 icon name strings.
ICON_SETS: dict[str, list[str]] = {
    "squares": squares,
    "darksquare": darksquare,
    "darkcircles": darkcircles,
    "circles": circles,
    "squircles": squircles,
    "darksquircles": darksquircles,
}

# Valid icon set names for CLI help / validation.
ICON_SET_NAMES = sorted(ICON_SETS.keys())


class MiniIconRenderer(MiniCalendarRenderer):
    """
    Mini calendar renderer that uses database icons for day numbers.

    Each day cell shows the icon for that day-of-month (1–31) instead of the
    numeric day number.  The icon is scaled to ~80 % of the cell height so it
    fills the cell visually.

    All other mini features (backgrounds, patterns, grid lines, milestone
    circles, duration bars, details page, etc.) are inherited unchanged.
    """

    def _get_day_icon_name(self, day_num: int, config: "CalendarConfig") -> str | None:
        """Return the icon name for *day_num* from the configured icon set."""
        icon_set_name = getattr(config, "mini_icon_set", "squares")
        icon_list = ICON_SETS.get(icon_set_name, squares)
        if 1 <= day_num <= 31 and len(icon_list) >= 31:
            return icon_list[day_num - 1]
        return None

    def _draw_day_cell(
        self,
        config: "CalendarConfig",
        x: float,
        y: float,
        w: float,
        h: float,
        day_num: int,
        style: DayStyle,
    ) -> None:
        """
        Draw a day cell using an icon instead of a day-number text glyph.

        Rendering order (back to front):
        1. Background shade
        2. SVG pattern decorations
        3. Legacy hash pattern
        4. Grid line (if enabled)
        5. Circle (if milestone)
        6. Icon (cell-height based size; falls back to text if icon missing)
        """
        default_color = config.theme_mini_day_color or config.mini_day_color

        # 1. Background shade
        if style.shade_color and not _is_none_color(style.shade_color):
            self._draw_rect(
                x, y, w, h,
                fill=style.shade_color,
                fill_opacity=style.shade_opacity,
            )

        # 2. SVG pattern decorations
        for dec in style.hash_decorations:
            self._draw_mini_svg_pattern(
                config, x, y, w, h,
                dec.pattern, dec.color, dec.opacity,
            )

        # 3. Legacy hash pattern
        if style.hash_pattern > 0:
            self._draw_mini_hash_lines(config, x, y, w, h)

        # 4. Grid lines
        if config.mini_grid_lines:
            grid_stroke_width = config.mini_grid_line_width
            inset = grid_stroke_width / 2
            self._draw_rect(
                x + inset, y + inset,
                max(0.0, w - grid_stroke_width),
                max(0.0, h - grid_stroke_width),
                fill="none",
                stroke=config.mini_grid_line_color,
                stroke_width=grid_stroke_width,
                stroke_opacity=config.mini_grid_line_opacity,
                stroke_dasharray=config.mini_grid_line_dasharray or None,
            )

        text_color = style.text_color or default_color
        cx = x + w / 2
        cy = y + h / 2

        # 5. Circle (milestone)
        if style.circled:
            radius = min(w, h) * 0.38
            self._draw_circle(
                cx, cy, radius,
                stroke=style.circle_color,
                fill=style.circle_fill or "none",
                stroke_width=config.mini_milestone_stroke_width,
                stroke_opacity=config.mini_milestone_stroke_opacity,
            )

        # 6. Determine which icon to draw.
        #    Priority: event icon_replace → event icon_append → day-number icon.
        icon_name = (
            style.icon_replace
            or style.icon_append
            or self._get_day_icon_name(day_num, config)
        )

        # Scale icon to fill most of the cell height.
        icon_size = min(w, h) * 0.80
        # baseline_y such that the icon is vertically centred in the cell.
        # _draw_icon_svg places the icon top at  baseline_y - size * 0.80,
        # so: top = cy - icon_size/2  →  baseline_y = cy + icon_size*0.5 - icon_size*0.80
        #                                             = cy - icon_size * 0.30
        # But the parent uses baseline_y = cy + icon_size * 0.30 which centres
        # fine in practice (accounts for descender space below visual cap).
        icon_baseline_y = cy + (icon_size * 0.30)

        drawn = self._draw_icon_svg(
            icon_name,
            cx,
            icon_baseline_y,
            icon_size,
            anchor="middle",
            color=text_color,
        )

        # Fallback: if the icon was not found in the DB, render the day number
        # as plain text so the calendar is still usable.
        if not drawn:
            display_text = self._format_day_number(day_num, config)
            font = config.mini_cell_bold_font if style.bold else config.mini_cell_font
            font_size = config.mini_cell_font_size
            text_y = cy + (font_size / 3)
            self._draw_text(
                cx, text_y, display_text,
                font, font_size,
                fill=text_color,
                fill_opacity=style.text_opacity,
                anchor="middle",
            )
