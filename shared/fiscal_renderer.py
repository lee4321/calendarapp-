"""
Shared fiscal calendar rendering utilities.

Provides color lookup, label formatting, and segment-building functions
used by all visualizers to render fiscal period/quarter data uniformly.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from config.config import CalendarConfig
    from shared.fiscal_calendars import FiscalPeriodInfo


@dataclass(frozen=True)
class FiscalSegment:
    """A contiguous date range corresponding to one fiscal period or quarter."""

    start: date           # first day (inclusive)
    end_exclusive: date   # first day of the NEXT segment (exclusive)
    label: str


# ---------------------------------------------------------------------------
# Color lookup
# ---------------------------------------------------------------------------


def get_fiscal_period_color(fiscal_info: "FiscalPeriodInfo", config: "CalendarConfig") -> str:
    """Resolve the fill color for a fiscal period.

    Returns the color from config.theme_fiscalperiodcolors keyed by
    zero-padded period number (e.g. "01"), falling back to the
    module-level fiscalperiodcolors default, then "lightgrey".
    """
    from config.config import fiscalperiodcolors as _default_colors

    colors = config.theme_fiscalperiodcolors or _default_colors
    period_key = str(fiscal_info.fiscal_period).zfill(2)
    return colors.get(period_key, "lightgrey")


# ---------------------------------------------------------------------------
# Label formatting
# ---------------------------------------------------------------------------


def format_fiscal_period_label(
    fiscal_info: "FiscalPeriodInfo",
    config: "CalendarConfig",
) -> str:
    """Format a fiscal period start label string using config template.

    Returns the formatted label (e.g. "Q1 FY26 P1") or falls back to
    the period_short_name ("P1") on template errors.
    """
    _fy_offset = config.fiscal_year_offset if config.fiscal_year_offset is not None else 0
    effective_year = fiscal_info.fiscal_year + _fy_offset
    quarter_label = (
        f"Q{fiscal_info.fiscal_quarter}"
        if config.fiscal_show_quarter_labels and fiscal_info.is_quarter_start
        else ""
    )
    year_label = f"FY{effective_year % 100}" if fiscal_info.is_fiscal_year_start else ""
    prefix = quarter_label + (" " if quarter_label else "")
    if year_label:
        prefix = f"{year_label} {prefix}".strip() + " "

    try:
        return config.fiscal_period_label_format.format(
            prefix=prefix,
            period_short=fiscal_info.period_short_name,
            period=fiscal_info.fiscal_period,
            quarter=fiscal_info.fiscal_quarter,
            year=effective_year,
            fy=effective_year % 100,
            quarter_label=quarter_label,
            year_label=year_label,
        )
    except (KeyError, ValueError):
        return f"{prefix}{fiscal_info.period_short_name}".strip()


def format_fiscal_period_end_label(
    fiscal_info: "FiscalPeriodInfo",
    config: "CalendarConfig",
) -> str:
    """Format a fiscal period end label string using config template."""
    _fy_offset = config.fiscal_year_offset if config.fiscal_year_offset is not None else 0
    effective_year = fiscal_info.fiscal_year + _fy_offset
    try:
        return config.fiscal_period_end_label_format.format(
            period_short=fiscal_info.period_short_name,
            period=fiscal_info.fiscal_period,
            quarter=fiscal_info.fiscal_quarter,
            year=effective_year,
            fy=effective_year % 100,
        )
    except (KeyError, ValueError):
        return f"{fiscal_info.period_short_name} End"


# ---------------------------------------------------------------------------
# Segment building helpers
# ---------------------------------------------------------------------------


def _shift_months(d: date, months: int) -> date:
    """Shift a date by an integer number of months (always returns the 1st)."""
    month_index = (d.month - 1) + months
    year = d.year + (month_index // 12)
    month = (month_index % 12) + 1
    return date(year, month, 1)


def _fiscal_quarter_start_gregorian(day: date, fiscal_start_month: int) -> date:
    """Return the first day of the Gregorian fiscal quarter containing day."""
    fy_start_year = day.year if day.month >= fiscal_start_month else day.year - 1
    offset = (day.month - fiscal_start_month) % 12
    q_index = offset // 3
    month_index = (fiscal_start_month - 1) + (q_index * 3)
    year = fy_start_year + (month_index // 12)
    month = (month_index % 12) + 1
    return date(year, month, 1)


# ---------------------------------------------------------------------------
# Period segments (NRF-only — requires fiscal_lookup)
# ---------------------------------------------------------------------------


def build_fiscal_period_segments(
    start: date,
    end: date,
    config: "CalendarConfig",
) -> list[FiscalSegment]:
    """Build one FiscalSegment per fiscal period in [start, end].

    Requires config.fiscal_lookup to be populated; returns [] otherwise.
    The segment label is generated from the first day of each period
    present in the range.
    """
    if not config.fiscal_lookup:
        return []

    segments: list[FiscalSegment] = []
    one_day = timedelta(days=1)
    cursor = start

    seg_start: date | None = None
    current_key: tuple[int, int] | None = None  # (fiscal_year, fiscal_period)
    seg_first_info = None  # fiscal info for the first day of current segment

    while cursor <= end:
        daykey = cursor.strftime("%Y%m%d")
        info = config.fiscal_lookup.get(daykey)
        if info is not None:
            key = (info.fiscal_year, info.fiscal_period)
            if current_key is None or key != current_key:
                # Flush previous segment
                if seg_start is not None and seg_first_info is not None:
                    segments.append(FiscalSegment(
                        start=seg_start,
                        end_exclusive=cursor,
                        label=format_fiscal_period_label(seg_first_info, config),
                    ))
                seg_start = cursor
                current_key = key
                seg_first_info = info
        cursor += one_day

    # Flush final segment
    if seg_start is not None and seg_first_info is not None:
        segments.append(FiscalSegment(
            start=seg_start,
            end_exclusive=end + one_day,
            label=format_fiscal_period_label(seg_first_info, config),
        ))

    return segments


# ---------------------------------------------------------------------------
# Quarter segments (NRF-aware with Gregorian fallback)
# ---------------------------------------------------------------------------


def build_fiscal_quarter_segments(
    start: date,
    end: date,
    config: "CalendarConfig",
    *,
    fiscal_start_month: int | None = None,
    label_format: str = "FY{fy} Q{q}",
) -> list[FiscalSegment]:
    """Build one FiscalSegment per fiscal quarter in [start, end].

    When config.fiscal_lookup is available (NRF-based), derives quarter
    boundaries directly from the lookup.  Falls back to Gregorian quarter
    calculation using fiscal_start_month (or
    config.blockplan_fiscal_year_start_month when not provided).
    """
    one_day = timedelta(days=1)
    segments: list[FiscalSegment] = []

    def _make_label(fy_raw: int, q: int) -> str:
        _fy_offset = config.fiscal_year_offset if config.fiscal_year_offset is not None else 0
        fy = fy_raw + _fy_offset
        try:
            return label_format.format(fy=fy, fy2=fy % 100, q=q)
        except (KeyError, ValueError):
            return f"FY{fy} Q{q}"

    if config.fiscal_lookup:
        # NRF-aware path: identify quarter boundaries via the lookup dict.
        cursor = start
        seg_start: date | None = None
        current_key: tuple[int, int] | None = None  # (fiscal_year, fiscal_quarter)
        seg_first_info = None

        while cursor <= end:
            daykey = cursor.strftime("%Y%m%d")
            info = config.fiscal_lookup.get(daykey)
            if info is not None:
                key = (info.fiscal_year, info.fiscal_quarter)
                if current_key is None or key != current_key:
                    if seg_start is not None and seg_first_info is not None:
                        segments.append(FiscalSegment(
                            start=seg_start,
                            end_exclusive=cursor,
                            label=_make_label(seg_first_info.fiscal_year, seg_first_info.fiscal_quarter),
                        ))
                    seg_start = cursor
                    current_key = key
                    seg_first_info = info
            cursor += one_day

        if seg_start is not None and seg_first_info is not None:
            segments.append(FiscalSegment(
                start=seg_start,
                end_exclusive=end + one_day,
                label=_make_label(seg_first_info.fiscal_year, seg_first_info.fiscal_quarter),
            ))
        return segments

    # Gregorian fallback path (no fiscal_lookup / --fiscal not set).
    fs_month = (
        fiscal_start_month
        if fiscal_start_month is not None
        else getattr(config, "blockplan_fiscal_year_start_month", 10)
    )
    cursor_date = _fiscal_quarter_start_gregorian(start, fs_month)
    while cursor_date <= end:
        next_cursor = _shift_months(cursor_date, 3)
        if next_cursor > start:
            q_num = (((cursor_date.month - fs_month) % 12) // 3) + 1
            _offset = config.fiscal_year_offset
            if _offset is None:
                fy_raw = cursor_date.year if fs_month == 1 else cursor_date.year + 1
            else:
                fy_raw = cursor_date.year + _offset
            seg_s = max(cursor_date, start)
            seg_e = min(next_cursor, end + one_day)
            if seg_s < seg_e:
                segments.append(FiscalSegment(
                    start=seg_s,
                    end_exclusive=seg_e,
                    label=_make_label(fy_raw, q_num),
                ))
        cursor_date = next_cursor
    return segments
