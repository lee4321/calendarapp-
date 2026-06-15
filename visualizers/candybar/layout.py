"""
Layout calculator for the candybar (vertical year-strip) visualization.

Each week is one horizontal row:

    [week#] [Mon] [Tue] [Wed] [Thu] [Fri] [Sat] [Sun] [ month box ]

Day cells hold the day-of-month number. The month box on the right (or left)
is a single merged cell spanning every week row attributed to that month,
mirroring the merged column-I cell in the Candybar.xlsx reference.

When the date range produces more rows than ``candybar_max_rows_per_page``,
the weeks are split into multiple side-by-side strips ("chunks") across the
page width so the calendar stays readable on a single page.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING

from shared.date_utils import get_week_number
from config.config import (
    weekend_style_starts_sunday,
)
from visualizers.base import BaseLayout, CoordinateDict

if TYPE_CHECKING:
    from config.config import CalendarConfig

logger = logging.getLogger(__name__)

# Column width ratios, expressed as multiples of a single day-column width.
# Fallback column-width ratios (× day-cell width) when config omits them.
WN_RATIO = 0.6  # week-number column
MONTH_RATIO = 1.6  # month-name box column


@dataclass(frozen=True)
class ColumnGeometry:
    """Horizontal layout of one candybar strip, shared by layout and renderer."""

    show_wn: bool
    suppress_weekends: bool
    week_start_sunday: bool
    days_per_week: int
    day_labels: list[str]
    weekday_order: list[int]  # weekday() values (0=Mon) in visible column order
    wn_x: float
    wn_w: float
    day_x0: float
    day_col_w: float
    month_x: float
    month_w: float
    strip_width: float  # total width of all columns in the strip


def resolve_cell_width(config: "CalendarConfig", cell_height: float) -> float:
    """Resolve the day-cell width.

    Defaults to ``cell_height`` so day cells are square; a positive
    ``candybar_cell_width`` (CLI / theme) overrides with a fixed point width.
    """
    cw = getattr(config, "candybar_cell_width", 0.0) or 0.0
    return float(cw) if cw > 0 else float(cell_height)


def _ordered_weekdays(week_start_sunday: bool, suppress_weekends: bool) -> list[int]:
    """Return weekday() values (0=Mon..6=Sun) in visible column order."""
    order = [6, 0, 1, 2, 3, 4, 5] if week_start_sunday else [0, 1, 2, 3, 4, 5, 6]
    if suppress_weekends:
        order = [wd for wd in order if wd < 5]
    return order


def candybar_suppress_weekends(config: "CalendarConfig") -> bool:
    """Resolve weekend suppression.

    Candybar shows weekends by default; Sat/Sun are dropped only when
    ``candybar_suppress_weekends`` is explicitly set (CLI
    ``--candybar-suppress-weekends`` or a theme's ``candybar.suppress_weekends``).
    It intentionally does *not* inherit ``weekend_style`` so the default
    full-week strip is independent of the workweek setting.
    """
    return bool(getattr(config, "candybar_suppress_weekends", None))


def candybar_week_starts_sunday(config: "CalendarConfig") -> bool:
    """Resolve week start: candybar_week_start overrides, else weekend_style."""
    ws = getattr(config, "candybar_week_start", -1)
    if ws == 0:
        return True
    if ws == 1:
        return False
    return weekend_style_starts_sunday(config.weekend_style)


def compute_columns(
    config: "CalendarConfig",
    strip_x: float,
    day_col_w: float,
) -> ColumnGeometry:
    """Compute the horizontal column geometry for a single strip.

    ``day_col_w`` is the resolved day-cell width; the week-number and
    month-box columns are sized as configurable multiples of it
    (``candybar_weeknum_col_ratio`` / ``candybar_month_col_ratio``).  The
    total ``strip_width`` is returned for the caller to place/center strips.

    Used by both the layout (to place cells) and the renderer (to place the
    header labels), so the two never drift out of alignment.
    """
    from config.config import day_short

    week_start_sunday = candybar_week_starts_sunday(config)
    suppress_weekends = candybar_suppress_weekends(config)
    weekday_order = _ordered_weekdays(week_start_sunday, suppress_weekends)
    days_per_week = len(weekday_order)
    show_wn = bool(config.candybar_show_week_numbers)

    labels = list(day_short)
    if len(labels) != 7:
        labels = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    day_labels = [labels[wd] for wd in weekday_order]

    wn_ratio = float(getattr(config, "candybar_weeknum_col_ratio", WN_RATIO) or 0.0)
    month_ratio = float(getattr(config, "candybar_month_col_ratio", MONTH_RATIO) or 0.0)
    wn_w = day_col_w * wn_ratio if show_wn else 0.0
    month_w = day_col_w * month_ratio
    strip_width = wn_w + days_per_week * day_col_w + month_w

    month_on_left = getattr(config, "candybar_month_label_side", "right") == "left"
    if month_on_left:
        month_x = strip_x
        wn_x = strip_x + month_w
        day_x0 = wn_x + wn_w
    else:
        wn_x = strip_x
        day_x0 = strip_x + wn_w
        month_x = day_x0 + days_per_week * day_col_w

    return ColumnGeometry(
        show_wn=show_wn,
        suppress_weekends=suppress_weekends,
        week_start_sunday=week_start_sunday,
        days_per_week=days_per_week,
        day_labels=day_labels,
        weekday_order=weekday_order,
        wn_x=wn_x,
        wn_w=wn_w,
        day_x0=day_x0,
        day_col_w=day_col_w,
        month_x=month_x,
        month_w=month_w,
        strip_width=strip_width,
    )


class CandybarLayout(BaseLayout):
    """Layout calculator for the candybar year-strip.

    Produces a CoordinateDict with keys:
        WeekNumHeader_C{c}        — "W#" header cell for chunk c (when enabled)
        DayHeader_C{c}_{i:02d}    — weekday header cell i for chunk c
        WeekNum_C{c}_R{r:03d}     — week-number cell (when enabled)
        Cell_YYYYMMDD             — day cell for an in-range day
        MonthBox_C{c}_YYYYMM      — merged month box spanning a month's rows

    Also populates self.week_numbers mapping WeekNum keys to int values.
    """

    def __init__(self):
        super().__init__()
        self.week_numbers: dict[str, int] = {}

    def calculate(self, config: "CalendarConfig") -> CoordinateDict:
        coord: CoordinateDict = {}
        self.week_numbers = {}

        try:
            start = datetime.strptime(config.adjustedstart, "%Y%m%d").date()
            end = datetime.strptime(config.adjustedend, "%Y%m%d").date()
        except (ValueError, TypeError):
            logger.warning("Invalid candybar date range")
            return coord
        if end < start:
            logger.warning("Candybar end before start")
            return coord

        week_start_sunday = candybar_week_starts_sunday(config)
        suppress_weekends = candybar_suppress_weekends(config)
        weekday_order = _ordered_weekdays(week_start_sunday, suppress_weekends)

        weeks = self._enumerate_weeks(start, end, week_start_sunday)
        # Drop leading/trailing weeks that contain no visible in-range day —
        # e.g. when the range starts/ends on a suppressed weekend, the first
        # week's only in-range days are Sat/Sun, which would render as a blank
        # row.
        weeks = [
            w for w in weeks
            if self._week_has_visible_day(w, weekday_order, start, end)
        ]
        if not weeks:
            return coord

        # Margins / header / footer (shared helpers)
        margins = self._calculate_margins(config)
        hf = self._calculate_header_footer(config, margins)
        self._emit_header_footer_coords(coord, config, margins, hf)

        content_x = margins["left"]
        content_width = margins["usable_width"]
        content_bottom = margins["bottom"] + hf["footer_height"]
        content_height = (
            margins["usable_height"] - hf["header_height"] - hf["footer_height"]
        )
        content_top = content_bottom + content_height

        # Split weeks into chunks (side-by-side strips).
        max_rows = max(0, int(config.candybar_max_rows_per_page or 0))
        if max_rows > 0 and len(weeks) > max_rows:
            chunk_size = max_rows
        else:
            chunk_size = len(weeks)
        num_chunks = math.ceil(len(weeks) / chunk_size)

        # Row height: fixed when configured, else fit chunk_size rows + 1 header
        # row into the available height so every strip aligns vertically.
        rows_for_height = chunk_size + 1  # +1 = header row
        if config.candybar_row_height and config.candybar_row_height > 0:
            row_h = float(config.candybar_row_height)
        else:
            row_h = content_height / rows_for_height
        header_h = row_h

        # Day-cell width: square by default (== row height), or a fixed width
        # / configurable column ratios from the theme.  Strip width follows
        # from the column geometry, so the strip no longer auto-stretches to
        # fill the page; instead the block of strips is centered horizontally.
        day_col_w = resolve_cell_width(config, row_h)
        gap = config.mini_month_gap
        strip_width = compute_columns(config, 0.0, day_col_w).strip_width
        block_width = num_chunks * strip_width + (num_chunks - 1) * gap
        start_x = content_x + max(0.0, (content_width - block_width) / 2.0)

        for c in range(num_chunks):
            chunk = weeks[c * chunk_size : (c + 1) * chunk_size]
            strip_x = start_x + c * (strip_width + gap)
            cols = compute_columns(config, strip_x, day_col_w)
            self._layout_chunk(
                coord, config, c, chunk, cols,
                content_top, header_h, row_h,
                start, end, suppress_weekends,
            )

        return self._to_svg_coords(coord, config.pageY)

    def _enumerate_weeks(
        self, start: date, end: date, week_start_sunday: bool
    ) -> list[date]:
        """Return the first-day-of-week date for every week overlapping the range."""
        if week_start_sunday:
            offset = (start.weekday() + 1) % 7  # days since most recent Sunday
        else:
            offset = start.weekday()  # days since most recent Monday
        first = start - timedelta(days=offset)
        weeks: list[date] = []
        cur = first
        while cur <= end:
            weeks.append(cur)
            cur = cur + timedelta(days=7)
        return weeks

    @staticmethod
    def _week_has_visible_day(
        week_start: date,
        weekday_order: list[int],
        start: date,
        end: date,
    ) -> bool:
        """True if the week has at least one visible (non-suppressed) day in range."""
        for n in range(7):
            d = week_start + timedelta(days=n)
            if d.weekday() in weekday_order and start <= d <= end:
                return True
        return False

    def _layout_chunk(
        self,
        coord: CoordinateDict,
        config: "CalendarConfig",
        chunk_idx: int,
        chunk: list[date],
        cols: ColumnGeometry,
        content_top: float,
        header_h: float,
        row_h: float,
        start: date,
        end: date,
        suppress_weekends: bool,
    ) -> None:
        """Place the header, week rows, and month boxes for one strip."""
        # Header row (top of the strip)
        header_y = content_top - header_h
        if cols.show_wn:
            coord[f"WeekNumHeader_C{chunk_idx}"] = (
                cols.wn_x, header_y, cols.wn_w, header_h
            )
        for i in range(cols.days_per_week):
            cell_x = cols.day_x0 + i * cols.day_col_w
            coord[f"DayHeader_C{chunk_idx}_{i:02d}"] = (
                cell_x, header_y, cols.day_col_w, header_h
            )

        # Track month -> list of row indices (within this chunk) for box spans.
        month_rows: list[tuple[tuple[int, int], int]] = []

        for r, week_start in enumerate(chunk):
            row_y = content_top - header_h - (r + 1) * row_h

            week_days = [week_start + timedelta(days=n) for n in range(7)]
            visible = [d for d in week_days if d.weekday() in cols.weekday_order]
            # Re-order to visible column order
            visible = sorted(visible, key=lambda d: cols.weekday_order.index(d.weekday()))

            in_range_visible: list[date] = []
            for col_idx, d in enumerate(visible):
                if d < start or d > end:
                    continue  # suppress out-of-range days at the ends
                in_range_visible.append(d)
                cell_x = cols.day_x0 + col_idx * cols.day_col_w
                coord[f"Cell_{d.strftime('%Y%m%d')}"] = (
                    cell_x, row_y, cols.day_col_w, row_h
                )

            # Week-number cell
            if cols.show_wn:
                wn_key = f"WeekNum_C{chunk_idx}_R{r:03d}"
                coord[wn_key] = (cols.wn_x, row_y, cols.wn_w, row_h)
                anchor = self._wn_anchor(config)
                self.week_numbers[wn_key] = get_week_number(
                    week_start, config.mini_week_number_mode, anchor
                )

            # Attribute the row to a month by its last visible in-range day.
            if in_range_visible:
                last = in_range_visible[-1]
                month_rows.append(((last.year, last.month), r))

        # Build merged month boxes from consecutive same-month rows.
        self._emit_month_boxes(
            coord, chunk_idx, month_rows, cols, content_top, header_h, row_h
        )

    def _emit_month_boxes(
        self,
        coord: CoordinateDict,
        chunk_idx: int,
        month_rows: list[tuple[tuple[int, int], int]],
        cols: ColumnGeometry,
        content_top: float,
        header_h: float,
        row_h: float,
    ) -> None:
        """Group consecutive rows of the same month into one merged box."""
        if not month_rows:
            return
        run_month = month_rows[0][0]
        run_first = month_rows[0][1]
        run_last = month_rows[0][1]

        def flush(ym: tuple[int, int], first_r: int, last_r: int) -> None:
            top_y = content_top - header_h - first_r * row_h
            height = (last_r - first_r + 1) * row_h
            box_y = top_y - height
            key = f"MonthBox_C{chunk_idx}_{ym[0]}{ym[1]:02d}"
            coord[key] = (cols.month_x, box_y, cols.month_w, height)

        for ym, r in month_rows[1:]:
            if ym == run_month and r == run_last + 1:
                run_last = r
            else:
                flush(run_month, run_first, run_last)
                run_month, run_first, run_last = ym, r, r
        flush(run_month, run_first, run_last)

    @staticmethod
    def _wn_anchor(config: "CalendarConfig") -> date | None:
        if config.mini_week_number_mode != "custom" or not config.mini_week1_start:
            return None
        try:
            return datetime.strptime(config.mini_week1_start, "%Y%m%d").date()
        except ValueError:
            logger.warning("Invalid mini_week1_start: %s", config.mini_week1_start)
            return None

    def _emit_header_footer_coords(
        self,
        coord: CoordinateDict,
        config: "CalendarConfig",
        margins: dict,
        hf: dict,
    ) -> None:
        """Emit page header/footer coords via the shared three-column helper."""
        left = margins["left"]
        top = config.pageY - margins["top"]

        if config.include_header and hf["header_height"] > 0:
            h_height = hf["header_height"]
            coord.update(
                self._generate_three_column_coords(
                    left, config.pageX, top - h_height, h_height,
                    "Header", margins["right"],
                )
            )
        if config.include_footer and hf["footer_height"] > 0:
            f_height = hf["footer_height"]
            coord.update(
                self._generate_three_column_coords(
                    left, config.pageX, margins["bottom"], f_height,
                    "Footer", margins["right"],
                )
            )
