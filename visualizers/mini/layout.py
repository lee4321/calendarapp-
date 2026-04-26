"""
Layout calculator for mini calendar visualization.

Arranges multiple months in a grid and calculates coordinates for
each element: month title, day-of-week header, day cells, week number
cells, and month bounding boxes.

Uses Python's standard library `calendar` module to determine week
structure for each month.
"""

from __future__ import annotations

import calendar
import logging
import math
from datetime import date, datetime
from typing import TYPE_CHECKING

import arrow

from shared.date_utils import get_week_number, get_months_in_range
from config.config import weekend_style_is_workweek, weekend_style_starts_sunday
from visualizers.base import BaseLayout, CoordinateDict

if TYPE_CHECKING:
    from config.config import CalendarConfig

logger = logging.getLogger(__name__)


class MiniCalendarLayout(BaseLayout):
    """
    Layout calculator for mini calendar grid-of-months.

    Produces a CoordinateDict with keys:
        MonthTitle_YYYYMM    — title row for each month
        DowHeader_YYYYMM     — day-of-week header row area
        WeekNum_YYYYMM_R{n}  — week number cell (when enabled)
        Cell_YYYYMMDD         — day cell for a primary-month day
        Cell_YYYYMMDD__adj    — day cell for an adjacent-month day
        MonthGrid_YYYYMM      — bounding box for the entire month grid

    Also populates self.week_numbers: dict mapping WeekNum keys to int values.
    """

    def __init__(self):
        super().__init__()
        self.week_numbers: dict[str, int] = {}

    def calculate(self, config: CalendarConfig) -> CoordinateDict:
        """
        Calculate coordinates for all months arranged in a grid.

        Args:
            config: Calendar configuration with page size, margins, etc.

        Returns:
            Dict mapping element names to coordinate tuples (x, y, w, h)
        """
        coord: CoordinateDict = {}
        self.week_numbers = {}

        # Determine months in the date range
        months = get_months_in_range(config.adjustedstart, config.adjustedend)
        num_months = len(months)
        if num_months == 0:
            logger.warning("No months in date range")
            return coord

        # Grid dimensions
        cols = config.mini_columns
        rows = (
            config.mini_rows if config.mini_rows > 0 else math.ceil(num_months / cols)
        )

        # Margins and header/footer
        margins = self._calculate_margins(config)
        hf = self._calculate_header_footer(config, margins)

        # Generate standard header/footer coordinates
        self._emit_header_footer_coords(coord, config, margins, hf)

        # Available content area
        content_x = margins["left"]
        content_width = margins["usable_width"]
        # PDF coordinates: Y increases upward, bottom is y=0
        content_bottom = margins["bottom"] + hf["footer_height"]
        content_height = (
            margins["usable_height"] - hf["header_height"] - hf["footer_height"]
        )

        # Per-month grid width
        gap = config.mini_month_gap
        month_width = (content_width - (cols - 1) * gap) / cols

        # Week start
        week_start_sunday = self._week_starts_sunday(config)
        firstweekday = 6 if week_start_sunday else 0

        # Pre-compute the maximum number of week rows across all months
        # so every month uses the same cell height for uniform day boxes.
        cal = calendar.Calendar(firstweekday=firstweekday)
        max_week_rows = 0
        for year, month in months:
            num_rows = len(cal.monthdatescalendar(year, month))
            max_week_rows = max(max_week_rows, num_rows)
        # Safety: ensure at least 4 (minimum for any month)
        max_week_rows = max(max_week_rows, 4)

        # Compute cell size subject to two constraints:
        #   1. Width constraint  — cells are square: cell = day_col_width
        #   2. Height constraint — all row-grids must fit within content_height
        # The binding constraint is whichever produces the smaller cell.
        days_per_week = 5 if weekend_style_is_workweek(config.weekend_style) else 7
        show_wn = config.mini_show_week_numbers
        if show_wn:
            day_col_width = month_width / (days_per_week + 0.6)
        else:
            day_col_width = month_width / days_per_week

        title_height = config.mini_title_font_size * 1.8
        header_height = config.mini_header_font_size * 1.8

        # Height available per row of months (after subtracting inter-row gaps)
        available_per_row = (content_height - (rows - 1) * gap) / max(rows, 1)
        max_cell_from_height = (
            available_per_row - title_height - header_height
        ) / max(max_week_rows, 1)

        # Use the smaller of the two constraints so every row fits on the page.
        cell_height = min(day_col_width, max(1.0, max_cell_from_height))

        month_height = title_height + header_height + max_week_rows * cell_height

        # Parse custom anchor date for week numbers
        wn_anchor: date | None = None
        if config.mini_show_week_numbers and config.mini_week_number_mode == "custom":
            if config.mini_week1_start:
                try:
                    wn_anchor = datetime.strptime(
                        config.mini_week1_start, "%Y%m%d"
                    ).date()
                except ValueError:
                    logger.warning(
                        "Invalid mini_week1_start: %s, falling back to ISO",
                        config.mini_week1_start,
                    )

        # Place each month — position from the top of the content area
        content_top = content_bottom + content_height
        for idx, (year, month) in enumerate(months):
            if idx >= rows * cols:
                logger.warning(
                    "More months (%d) than grid cells (%d×%d), truncating",
                    num_months,
                    rows,
                    cols,
                )
                break

            grid_row = idx // cols
            grid_col = idx % cols

            # Month origin (PDF coordinates: bottom-left, Y up)
            mx = content_x + grid_col * (month_width + gap)
            # Top row = grid_row 0 → highest Y; position month top at
            # content_top minus accumulated rows and gaps
            my = content_top - (grid_row + 1) * month_height - grid_row * gap

            self._layout_month(
                coord,
                config,
                year,
                month,
                mx,
                my,
                month_width,
                month_height,
                week_start_sunday,
                wn_anchor,
                max_week_rows,
                cell_height,
            )

        return self._to_svg_coords(coord, config.pageY)

    def _layout_month(
        self,
        coord: CoordinateDict,
        config: CalendarConfig,
        year: int,
        month: int,
        x: float,
        y: float,
        width: float,
        height: float,
        week_start_sunday: bool,
        wn_anchor: date | None,
        max_week_rows: int = 6,
        cell_height: float | None = None,
    ) -> None:
        """
        Layout a single month grid at (x, y) with given dimensions.

        Divides vertical space into:
        - Title row (top)
        - Day-of-week header row
        - ``max_week_rows`` day number rows (uniform across all months)

        When week numbers are enabled, adds a narrower W# column
        on the left side.

        ``cell_height`` may be pre-computed by the caller (e.g. when the
        height constraint is tighter than the square-cell width constraint).
        When omitted it falls back to ``day_col_width`` (square cells).
        """
        month_key = f"{year}{str(month).zfill(2)}"

        # Build week structure using stdlib calendar
        firstweekday = 6 if week_start_sunday else 0
        cal = calendar.Calendar(firstweekday=firstweekday)
        weeks_dates = cal.monthdatescalendar(year, month)

        # Workweek mode (--weekends 0) drops Sat/Sun columns
        is_workweek = weekend_style_is_workweek(config.weekend_style)
        days_per_week = 5 if is_workweek else 7

        # Horizontal allocation: optional W# column + day columns
        show_wn = config.mini_show_week_numbers
        if show_wn:
            # W# column is ~60% the width of a day column
            # Solve: wn_w + N * day_w = width, wn_w = 0.6 * day_w
            day_col_width = width / (days_per_week + 0.6)
            wn_col_width = day_col_width * 0.6
        else:
            wn_col_width = 0.0
            day_col_width = width / days_per_week

        # Vertical allocation — cell height is provided by the caller when
        # the height constraint is tighter than the square-cell width
        # constraint; otherwise default to square cells (height == width).
        title_height = config.mini_title_font_size * 1.8
        header_height = config.mini_header_font_size * 1.8
        if cell_height is None:
            cell_height = day_col_width  # Square cells: height == width

        day_area_x = x + wn_col_width  # X origin of day columns

        # Title coordinate (spans full width)
        title_y = y + height - title_height
        coord[f"MonthTitle_{month_key}"] = (x, title_y, width, title_height)

        # Day-of-week header coordinate (spans full width; renderer splits columns)
        dow_y = title_y - header_height
        coord[f"DowHeader_{month_key}"] = (x, dow_y, width, header_height)

        # Week rows: day cells + optional week number cells
        for week_idx, week in enumerate(weeks_dates):
            row_y = dow_y - (week_idx + 1) * cell_height

            # Week number cell
            if show_wn:
                wn_key = f"WeekNum_{month_key}_R{week_idx}"
                coord[wn_key] = (x, row_y, wn_col_width, cell_height)

                # Compute the week number from the first day in this row
                row_date = week[0]  # first day of the row
                wn_value = get_week_number(
                    row_date,
                    config.mini_week_number_mode,
                    wn_anchor,
                )
                self.week_numbers[wn_key] = wn_value

            # Day cells — in workweek mode, skip Sat/Sun and reflow columns
            visible_days = (
                [d for d in week if d.weekday() < 5] if is_workweek else list(week)
            )
            for col_idx, d in enumerate(visible_days):
                cell_x = day_area_x + col_idx * day_col_width
                is_adj = d.month != month

                if is_adj and not config.mini_show_adjacent:
                    continue

                daykey = d.strftime("%Y%m%d")
                suffix = "__adj" if is_adj else ""
                cell_key = f"Cell_{daykey}{suffix}"

                # Avoid coordinate collisions: adjacent days from the same
                # date appearing in two different months. The __adj suffix
                # plus the fact that each month's grid is spatially separate
                # prevents visual overlap, but we must also avoid dict key
                # collisions if the same adj date appears in two adjacent
                # months. Prefix with month_key to guarantee uniqueness.
                if is_adj:
                    cell_key = f"Cell_{month_key}_{daykey}__adj"

                coord[cell_key] = (cell_x, row_y, day_col_width, cell_height)

        # Month grid bounding box
        coord[f"MonthGrid_{month_key}"] = (x, y, width, height)

    def _emit_header_footer_coords(
        self,
        coord: CoordinateDict,
        config: CalendarConfig,
        margins: dict,
        hf: dict,
    ) -> None:
        """
        Emit header and footer coordinates using the shared three-column helper.
        """
        left = margins["left"]
        top = config.pageY - margins["top"]

        if config.include_header and hf["header_height"] > 0:
            h_height = hf["header_height"]
            header_y = top - h_height
            coord.update(
                self._generate_three_column_coords(
                    left,
                    config.pageX,
                    header_y,
                    h_height,
                    "Header",
                    margins["right"],
                )
            )

        if config.include_footer and hf["footer_height"] > 0:
            f_height = hf["footer_height"]
            footer_y = margins["bottom"]
            coord.update(
                self._generate_three_column_coords(
                    left,
                    config.pageX,
                    footer_y,
                    f_height,
                    "Footer",
                    margins["right"],
                )
            )

    @staticmethod
    def _week_starts_sunday(config: CalendarConfig) -> bool:
        """
        Determine if weeks start on Sunday based on config.

        Args:
            config: Calendar configuration

        Returns:
            True if weeks should start on Sunday
        """
        if config.mini_week_start == 0:
            return True
        elif config.mini_week_start == 1:
            return False
        else:  # -1 = inherit from weekend_style
            return weekend_style_starts_sunday(config.weekend_style)
