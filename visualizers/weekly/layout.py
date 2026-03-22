"""
Weekly calendar layout calculation.

Calculates coordinates for day boxes, headers, footers, and other
layout elements for weekly calendar visualization.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from visualizers.base import BaseLayout, CoordinateDict
from config.config import WEEKEND_STYLES
from shared.date_utils import get_calendar_days

if TYPE_CHECKING:
    from config.config import CalendarConfig


logger = logging.getLogger(__name__)


class WeeklyCalendarLayout(BaseLayout):
    """
    Layout calculator for weekly calendar visualization.

    Calculates coordinates for:
    - Day boxes in grid layout
    - Headers and footers
    - Day name labels
    - Color key area
    - Week numbers area
    """

    def calculate(self, config: CalendarConfig) -> CoordinateDict:
        """
        Calculate all coordinates for weekly calendar layout.

        Args:
            config: Calendar configuration with page size, margins, etc.

        Returns:
            Dict mapping element names to coordinate tuples
        """
        coord: CoordinateDict = {}

        margins = self._calculate_margins(config)
        left = margins["left"]
        right = margins["right"]
        top = margins["top"]
        bottom = margins["bottom"]

        if left > 0 or right > 0 or top > 0 or bottom > 0:
            coord["Bottommargin"] = (0, 0, config.pageX, bottom)
            coord["Topmargin"] = (0, config.pageY - top, config.pageX, top)
            coord["Leftmargin"] = (0, 0, left, config.pageY)
            coord["Rightmargin"] = (config.pageX - right, 0, right, config.pageY)

        # Header coordinates
        headerY = 0.0
        if config.include_header:
            headerY = round(config.pageY * config.header_percent, 2)
            header_y_pos = config.pageY - top - headerY
            coord.update(
                self._generate_three_column_coords(
                    left, config.pageX, header_y_pos, headerY, "Header", right
                )
            )

        # Footer coordinates
        footerY = 0.0
        if config.include_footer:
            footerY = round(config.pageY * config.footer_percent, 2)
            coord.update(
                self._generate_three_column_coords(
                    left, config.pageX, bottom, footerY, "Footer", right
                )
            )

        # Color key coordinates
        colkeyY = 0.0
        if config.include_color_key:
            colkeyY = round(config.pageY * config.color_key_percent, 2)
            coord["ColorKey"] = (
                left,
                bottom + colkeyY,
                config.pageX - left - right,
                colkeyY,
            )

        # Month labels (currently disabled)
        monthlablesX = 0.0

        # Week numbers are rendered inside day boxes (no extra column)
        weeknumsX = 0.0

        # Day name label height
        daylabY = 0.0
        if config.include_day_names:
            daylabY = round(config.pageY * config.day_name_percent, 2)

        # Calculate day box canvas dimensions
        DayBoxCanvasWidth = round(
            config.pageX - left - right - monthlablesX - weeknumsX, 2
        )
        DayBoxCanvasHeight = round(
            config.pageY - top - bottom - footerY - headerY - daylabY - colkeyY, 2
        )

        baseX = round(left + monthlablesX + weeknumsX, 2)
        baseY = round(bottom + footerY + colkeyY, 2)

        coord["DayBoxCanvas"] = (baseX, baseY, DayBoxCanvasWidth, DayBoxCanvasHeight)

        # Get style configuration
        style = WEEKEND_STYLES[config.weekend_style]

        # Prepare calendar day keys (reversed for building from last to first)
        caldays = get_calendar_days(config.adjustedstart, config.adjustedend)

        # Calculate column layout
        weekday_width, weekend_width, col_widths, col_x = self._calculate_column_layout(
            DayBoxCanvasWidth, baseX, style
        )

        # Calculate row height
        row_height = round(DayBoxCanvasHeight / config.numberofweeks, 2)

        # Generate day box coordinates based on style
        if style.get("special_layout"):
            # Style 2 requires special handling
            day_coords, label_y = self._generate_day_box_grid_style2(
                baseX,
                baseY,
                row_height,
                config.numberofweeks,
                caldays,
                weekday_width,
                weekend_width,
            )
        else:
            # Standard layout for styles 0, 1, 3, 4
            day_coords, label_y = self._generate_day_box_grid_standard(
                baseX,
                baseY,
                row_height,
                config.numberofweeks,
                caldays,
                col_widths,
                col_x,
                style,
            )

        coord.update(day_coords)

        # Generate day name label coordinates
        if config.include_day_names:
            day_name_coords = self._generate_day_name_coords(
                baseX, label_y, daylabY, style["day_order"], col_widths
            )
            coord.update(day_name_coords)

        return self._to_svg_coords(coord, config.pageY)

    def _generate_day_name_coords(
        self,
        base_x: float,
        y: float,
        height: float,
        day_order: list,
        widths: list,
    ) -> dict:
        """
        Generate coordinates for day name labels.

        Args:
            base_x: Starting X coordinate
            y: Y coordinate for all labels
            height: Height of label area
            day_order: List of day names in display order
            widths: List of widths corresponding to each day

        Returns:
            Dict mapping day names to (x, y, width, height) tuples
        """
        coords = {}
        current_x = base_x
        for day, width in zip(day_order, widths):
            coords[day] = (round(current_x, 2), y, width, height)
            current_x += width
        return coords

    def _calculate_column_layout(
        self,
        canvas_width: float,
        base_x: float,
        style_config: dict,
    ) -> tuple:
        """
        Calculate column widths and X positions for day boxes.

        Args:
            canvas_width: Width of the day box canvas area
            base_x: Starting X coordinate
            style_config: Weekend style configuration dict

        Returns:
            Tuple of (weekday_width, weekend_width, col_widths list, col_x_positions list)
        """
        divisor = style_config["divisor"]
        weekend_factor = style_config["weekend_width_factor"]
        day_order = style_config["day_order"]

        weekday_width = round(canvas_width / divisor, 2)

        if weekend_factor == 0:  # No weekends (style 0)
            weekend_width = 0
            col_widths = [weekday_width] * 5
            col_x = [round(base_x + i * weekday_width, 2) for i in range(5)]

        elif weekend_factor == 1.0:  # All same size (styles 1, 3)
            weekend_width = weekday_width
            col_widths = [weekday_width] * 7
            col_x = [round(base_x + i * weekday_width, 2) for i in range(7)]

        else:  # Half-width weekends (styles 2, 4)
            weekend_width = round(weekday_width / 2, 2)

            # Build widths and positions based on day order
            col_widths = []
            col_x = []
            current_x = base_x

            for day in day_order:
                if day in ("Saturday", "Sunday"):
                    col_widths.append(weekend_width)
                else:
                    col_widths.append(weekday_width)
                col_x.append(round(current_x, 2))
                current_x += col_widths[-1]

        return weekday_width, weekend_width, col_widths, col_x

    def _generate_day_box_grid_standard(
        self,
        base_x: float,
        base_y: float,
        row_height: float,
        num_rows: int,
        caldays: list,
        col_widths: list,
        col_x: list,
        style_config: dict,
    ) -> tuple:
        """
        Generate day box coordinates for standard layouts (styles 0, 1, 3, 4).

        Args:
            base_x: Starting X coordinate
            base_y: Starting Y coordinate
            row_height: Height of each row
            num_rows: Number of rows (weeks)
            caldays: List of calendar day keys (reversed)
            col_widths: Column widths
            col_x: Column X positions
            style_config: Weekend style configuration

        Returns:
            Tuple of (coords dict, final_y position)
        """
        coords = {}
        ptr = style_config["ptr_init"]
        ptr_inc = style_config["ptr_increment"]
        days_per_week = style_config["days_per_week"]

        newY = base_y
        for row in range(num_rows):
            ptr += ptr_inc
            for col in range(days_per_week):
                key = caldays[ptr]
                newY = round(base_y + row * row_height, 2)
                coords[key] = (col_x[col], newY, col_widths[col], row_height)
                ptr -= 1

        return coords, newY + row_height

    def _generate_day_box_grid_style2(
        self,
        base_x: float,
        base_y: float,
        row_height: float,
        num_rows: int,
        caldays: list,
        weekday_width: float,
        weekend_width: float,
    ) -> tuple:
        """
        Generate day box coordinates for style 2 (half-width weekends, Sunday start).

        This style requires special handling because Sunday and Saturday are
        placed in separate loops.

        Args:
            base_x: Starting X coordinate
            base_y: Starting Y coordinate
            row_height: Height of each row
            num_rows: Number of rows (weeks)
            caldays: List of calendar day keys (reversed)
            weekday_width: Width of weekday columns
            weekend_width: Width of weekend columns

        Returns:
            Tuple of (coords dict, final_y position)
        """
        coords = {}

        # Setup all the Sunday dayboxes (first column)
        ptr = 6
        for row in range(num_rows):
            key = caldays[ptr]
            newY = round(base_y + row * row_height, 2)
            coords[key] = (base_x, newY, weekend_width, row_height)
            ptr += 7

        # Setup all the M,T,W,Th,F dayboxes (middle columns)
        temp_x = round(base_x + weekend_width, 2)
        ptr = -7
        for row in range(num_rows):
            ptr += 12
            for col in range(5):  # Mon-Fri
                key = caldays[ptr]
                newX = round(temp_x + col * weekday_width, 2)
                newY = round(base_y + row * row_height, 2)
                coords[key] = (newX, newY, weekday_width, row_height)
                ptr -= 1

        # Calculate where Saturday column starts
        sat_x = round(temp_x + 5 * weekday_width, 2)

        # Setup all the Saturday dayboxes (last column)
        ptr = 0
        for row in range(num_rows):
            key = caldays[ptr]
            newY = round(base_y + row * row_height, 2)
            coords[key] = (sat_x, newY, weekend_width, row_height)
            ptr += 7

        return coords, round(newY + row_height, 2)
