"""
Gantt layout calculation.

Splits the page into the header/footer chrome, the task-table column
block on the left, and the timescale chart area on the right, then
divides both vertically into the column-header row, the top and bottom
time-band rows, and the task body between them.

Everything here depends only on config, matching ``BaseLayout``'s
config-only signature.  Anything event-dependent -- row count, day
columns, cell text -- is resolved by the renderer.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from visualizers.base import BaseLayout, CoordinateDict

if TYPE_CHECKING:
    from config.config import CalendarConfig


#: Largest share of the content height the chrome (column header plus both
#: band stacks) may take.  Band stacks are unbounded -- a theme may declare
#: as many rows as it likes in either -- so this is what keeps the task body
#: alive when it declares a lot of them: past this share every chrome row is
#: scaled down proportionally rather than any band being dropped.
MAX_CHROME_SHARE = 0.75


@dataclass(frozen=True)
class GanttPage:
    """One page's slice of the chart.

    Row and day ranges are half-open, indexing the full ordered row list
    and the full visible-day axis respectively -- so a page knows both
    what it shows and where it sits in the whole.
    """

    number: int          # 1-based; page 1 keeps the base filename
    row_start: int
    row_end: int
    day_start: int
    day_end: int

    @property
    def row_count(self) -> int:
        return max(0, self.row_end - self.row_start)

    @property
    def is_first(self) -> bool:
        return self.number == 1


def plan_pages(
    row_count: int,
    day_count: int,
    rows_per_page: int,
    days_per_page: int,
) -> list[GanttPage]:
    """Split the chart into pages, row-major.

    All horizontal pages for the first block of rows come first, then the
    next block -- so a reader following one task's bar across the date
    range turns consecutive pages.

    Both per-page counts are floored at 1: a page too short for even one
    row would otherwise produce pages forever.  A chart with no rows
    still yields one page, so the frame, timescale and column headers
    render.
    """
    rows_per_page = max(1, rows_per_page)
    days_per_page = max(1, days_per_page)

    row_starts = list(range(0, row_count, rows_per_page)) or [0]
    day_starts = list(range(0, day_count, days_per_page)) or [0]

    pages: list[GanttPage] = []
    number = 1
    for row_start in row_starts:
        for day_start in day_starts:
            pages.append(
                GanttPage(
                    number=number,
                    row_start=row_start,
                    row_end=min(row_start + rows_per_page, row_count),
                    day_start=day_start,
                    day_end=min(day_start + days_per_page, day_count),
                )
            )
            number += 1
    return pages


class GanttLayout(BaseLayout):
    """Layout calculator for the Gantt visualization."""

    def calculate(self, config: "CalendarConfig") -> CoordinateDict:
        """Calculate the page frame: header, footer, table and chart areas."""
        coord: CoordinateDict = {}

        margins = self._calculate_margins(config)
        hf = self._calculate_header_footer(config, margins)

        if config.include_header and hf["header_height"] > 0:
            header_y = config.pageY - margins["top"] - hf["header_height"]
            coord.update(
                self._generate_three_column_coords(
                    margins["left"],
                    config.pageX,
                    header_y,
                    hf["header_height"],
                    "Header",
                    margins["right"],
                )
            )

        if config.include_footer and hf["footer_height"] > 0:
            coord.update(
                self._generate_three_column_coords(
                    margins["left"],
                    config.pageX,
                    margins["bottom"],
                    hf["footer_height"],
                    "Footer",
                    margins["right"],
                )
            )

        content_x = margins["left"]
        content_y = margins["bottom"] + hf["footer_height"]
        content_w = margins["usable_width"]
        content_h = (
            margins["usable_height"] - hf["header_height"] - hf["footer_height"]
        )

        # The table takes its configured share of the content width; the
        # chart takes the rest.  Clamped so a mis-set ratio cannot leave
        # either side with zero or negative width.
        ratio = min(max(float(config.gantt_table_width_ratio), 0.05), 0.95)
        table_w = round(content_w * ratio, 2)

        coord["GanttArea"] = (
            round(content_x, 2),
            round(content_y, 2),
            round(content_w, 2),
            round(content_h, 2),
        )
        coord["GanttTableArea"] = (
            round(content_x, 2),
            round(content_y, 2),
            table_w,
            round(content_h, 2),
        )
        chart_x = content_x + table_w
        chart_w = content_w - table_w
        coord["GanttChartArea"] = (
            round(chart_x, 2),
            round(content_y, 2),
            round(chart_w, 2),
            round(content_h, 2),
        )

        # Vertical split, top to bottom: the time bands sit on the top
        # edge (chart side only), the column-header row runs beneath them
        # across the table, the task body fills the middle, and the bottom
        # bands sit on the bottom edge.  Either stack may hold any number
        # of bands; the total is capped so the body always survives.
        header_h = max(float(config.gantt_header_row_height), 0.0)
        top_bands_h = self._bands_height(config, config.gantt_top_time_bands)
        bottom_bands_h = self._bands_height(config, config.get_gantt_bottom_bands())

        chrome_h = header_h + top_bands_h + bottom_bands_h
        max_chrome = content_h * MAX_CHROME_SHARE
        if chrome_h > max_chrome and chrome_h > 0:
            scale = max_chrome / chrome_h
            header_h *= scale
            top_bands_h *= scale
            bottom_bands_h *= scale

        # PDF space: y grows upward, so the top edge is the high y.
        top_y = content_y + content_h
        top_bands_y = top_y - top_bands_h
        header_y = top_bands_y - header_h
        body_y = content_y + bottom_bands_h
        body_h = header_y - body_y

        coord["GanttColumnHeader"] = (
            round(content_x, 2), round(header_y, 2), table_w, round(header_h, 2),
        )
        coord["GanttTopBands"] = (
            round(chart_x, 2), round(top_bands_y, 2),
            round(chart_w, 2), round(top_bands_h, 2),
        )
        coord["GanttBottomBands"] = (
            round(chart_x, 2), round(content_y, 2),
            round(chart_w, 2), round(bottom_bands_h, 2),
        )
        coord["GanttTableBody"] = (
            round(content_x, 2), round(body_y, 2), table_w, round(body_h, 2),
        )
        coord["GanttChartBody"] = (
            round(chart_x, 2), round(body_y, 2), round(chart_w, 2), round(body_h, 2),
        )

        return self._to_svg_coords(coord, config.pageY)

    @staticmethod
    def _bands_height(config: "CalendarConfig", bands: list) -> float:
        """Total height of a band stack of any length.

        Each band may state its own ``row_height``; those that do not fall
        back to ``gantt_band_row_height``.  Non-dict entries are ignored so
        a malformed theme costs one band, not the page.
        """
        default_h = float(config.gantt_band_row_height)
        return sum(
            float(band.get("row_height", default_h))
            for band in (bands or [])
            if isinstance(band, dict)
        )
