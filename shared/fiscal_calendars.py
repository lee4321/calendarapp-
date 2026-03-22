"""
Fiscal calendar implementations for alternative date labeling.

Provides NRF 4-5-4, 4-4-5, 5-4-4, and 13-period fiscal calendar
computations. Each calendar type can map any Gregorian date to its
fiscal year, quarter, period, and week.

Usage:
    from shared.fiscal_calendars import create_fiscal_calendar, build_fiscal_lookup

    cal = create_fiscal_calendar("nrf-454")
    info = cal.get_period_info(date(2026, 3, 15))
    # info.fiscal_year = 2026, info.fiscal_period = 2, etc.

    lookup = build_fiscal_lookup(cal, date(2026, 1, 1), date(2026, 12, 31))
    # lookup["20260315"] -> FiscalPeriodInfo(...)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date, timedelta


@dataclass(frozen=True)
class FiscalPeriodInfo:
    """Fiscal period metadata for a single Gregorian date."""

    fiscal_year: int
    fiscal_quarter: int  # 1-4
    fiscal_period: int  # 1-12 (or 1-13 for 13-period)
    fiscal_week: int  # Week within the fiscal year (1-52 or 1-53)
    period_name: str  # "Period 1", "Period 2", etc.
    period_short_name: str  # "P1", "P2", etc.
    is_period_start: bool
    is_quarter_start: bool
    is_fiscal_year_start: bool


class FiscalCalendar(ABC):
    """Base class for fiscal calendar implementations."""

    @abstractmethod
    def fiscal_year_start(self, gregorian_year: int) -> date:
        """Return the first day of the fiscal year associated with this Gregorian year."""
        ...

    @abstractmethod
    def get_period_info(self, d: date) -> FiscalPeriodInfo:
        """Return fiscal period info for a Gregorian date."""
        ...

    @abstractmethod
    def get_period_boundaries(self, fiscal_year: int) -> list[tuple[date, date, int]]:
        """Return (start, end, period_number) for each period in a fiscal year."""
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable name."""
        ...

    @property
    @abstractmethod
    def period_count(self) -> int:
        """Number of periods per year (12 or 13)."""
        ...


def _sunday_closest_to_feb1(year: int) -> date:
    """Find the Sunday closest to February 1 of the given year.

    The NRF fiscal year starts on the Sunday falling in the range
    Jan 29 – Feb 4 (i.e., the Sunday closest to Feb 1).
    """
    feb1 = date(year, 2, 1)
    # date.weekday(): Mon=0 ... Sun=6
    weekday = feb1.weekday()
    if weekday <= 2:
        # Mon(0), Tue(1), Wed(2) -> go back to previous Sunday
        return feb1 - timedelta(days=weekday + 1)
    elif weekday == 6:
        # Already Sunday
        return feb1
    else:
        # Thu(3), Fri(4), Sat(5) -> go forward to next Sunday
        return feb1 + timedelta(days=6 - weekday)


class _NRFBase(FiscalCalendar):
    """Base for NRF-style fiscal calendars (4-5-4, 4-4-5, 5-4-4).

    Subclasses only need to define PATTERN (list of 12 week-counts)
    and the name/period_count properties.
    """

    PATTERN: list[int]  # 12 entries, each 4 or 5

    def fiscal_year_start(self, gregorian_year: int) -> date:
        return _sunday_closest_to_feb1(gregorian_year)

    def _has_53_weeks(self, fiscal_year: int) -> bool:
        """Return True if this fiscal year has 53 weeks."""
        start_this = self.fiscal_year_start(fiscal_year)
        start_next = self.fiscal_year_start(fiscal_year + 1)
        return (start_next - start_this).days > 364

    def get_period_boundaries(self, fiscal_year: int) -> list[tuple[date, date, int]]:
        fy_start = self.fiscal_year_start(fiscal_year)
        has_53 = self._has_53_weeks(fiscal_year)

        boundaries = []
        current = fy_start
        for i, weeks in enumerate(self.PATTERN):
            period_num = i + 1
            # Last period gets the extra week in a 53-week year
            if has_53 and period_num == 12:
                weeks += 1
            period_end = current + timedelta(weeks=weeks) - timedelta(days=1)
            boundaries.append((current, period_end, period_num))
            current = period_end + timedelta(days=1)

        return boundaries

    def _find_fiscal_year_for_date(self, d: date) -> int:
        """Determine which fiscal year a date belongs to."""
        # Check the year of the date and the year before
        for candidate in (d.year, d.year - 1, d.year + 1):
            fy_start = self.fiscal_year_start(candidate)
            next_fy_start = self.fiscal_year_start(candidate + 1)
            if fy_start <= d < next_fy_start:
                return candidate
        # Fallback (should not happen)
        return d.year

    def get_period_info(self, d: date) -> FiscalPeriodInfo:
        fiscal_year = self._find_fiscal_year_for_date(d)
        fy_start = self.fiscal_year_start(fiscal_year)
        boundaries = self.get_period_boundaries(fiscal_year)

        day_offset = (d - fy_start).days
        fiscal_week = (day_offset // 7) + 1

        for period_start, period_end, period_num in boundaries:
            if period_start <= d <= period_end:
                quarter = ((period_num - 1) // 3) + 1
                return FiscalPeriodInfo(
                    fiscal_year=fiscal_year,
                    fiscal_quarter=quarter,
                    fiscal_period=period_num,
                    fiscal_week=fiscal_week,
                    period_name=f"Period {period_num}",
                    period_short_name=f"P{period_num}",
                    is_period_start=(d == period_start),
                    is_quarter_start=(d == period_start and (period_num - 1) % 3 == 0),
                    is_fiscal_year_start=(d == fy_start),
                )

        # Should not reach here if fiscal year logic is correct
        raise ValueError(f"Date {d} not found in fiscal year {fiscal_year} boundaries")

    @property
    def period_count(self) -> int:
        return 12


class NRF454Calendar(_NRFBase):
    """NRF 4-5-4 retail calendar."""

    PATTERN = [4, 5, 4, 4, 5, 4, 4, 5, 4, 4, 5, 4]

    @property
    def name(self) -> str:
        return "NRF 4-5-4"


class NRF445Calendar(_NRFBase):
    """NRF 4-4-5 variant."""

    PATTERN = [4, 4, 5, 4, 4, 5, 4, 4, 5, 4, 4, 5]

    @property
    def name(self) -> str:
        return "NRF 4-4-5"


class NRF544Calendar(_NRFBase):
    """NRF 5-4-4 variant."""

    PATTERN = [5, 4, 4, 5, 4, 4, 5, 4, 4, 5, 4, 4]

    @property
    def name(self) -> str:
        return "NRF 5-4-4"


class ThirteenPeriodCalendar(FiscalCalendar):
    """13-period calendar with 13 equal 4-week periods.

    Uses the same fiscal year start as NRF (Sunday closest to Feb 1).
    In a 53-week year, period 13 gets the extra week.
    """

    def fiscal_year_start(self, gregorian_year: int) -> date:
        return _sunday_closest_to_feb1(gregorian_year)

    def _has_53_weeks(self, fiscal_year: int) -> bool:
        start_this = self.fiscal_year_start(fiscal_year)
        start_next = self.fiscal_year_start(fiscal_year + 1)
        return (start_next - start_this).days > 364

    def get_period_boundaries(self, fiscal_year: int) -> list[tuple[date, date, int]]:
        fy_start = self.fiscal_year_start(fiscal_year)
        has_53 = self._has_53_weeks(fiscal_year)

        boundaries = []
        current = fy_start
        for i in range(13):
            period_num = i + 1
            weeks = 4
            if has_53 and period_num == 13:
                weeks = 5
            period_end = current + timedelta(weeks=weeks) - timedelta(days=1)
            boundaries.append((current, period_end, period_num))
            current = period_end + timedelta(days=1)

        return boundaries

    def _find_fiscal_year_for_date(self, d: date) -> int:
        for candidate in (d.year, d.year - 1, d.year + 1):
            fy_start = self.fiscal_year_start(candidate)
            next_fy_start = self.fiscal_year_start(candidate + 1)
            if fy_start <= d < next_fy_start:
                return candidate
        return d.year

    def get_period_info(self, d: date) -> FiscalPeriodInfo:
        fiscal_year = self._find_fiscal_year_for_date(d)
        fy_start = self.fiscal_year_start(fiscal_year)
        boundaries = self.get_period_boundaries(fiscal_year)

        day_offset = (d - fy_start).days
        fiscal_week = (day_offset // 7) + 1

        for period_start, period_end, period_num in boundaries:
            if period_start <= d <= period_end:
                quarter = ((period_num - 1) // 3) + 1
                if quarter > 4:
                    quarter = 4  # Period 13 belongs to Q4
                return FiscalPeriodInfo(
                    fiscal_year=fiscal_year,
                    fiscal_quarter=quarter,
                    fiscal_period=period_num,
                    fiscal_week=fiscal_week,
                    period_name=f"Period {period_num}",
                    period_short_name=f"P{period_num}",
                    is_period_start=(d == period_start),
                    is_quarter_start=(
                        d == period_start and period_num in (1, 4, 7, 10)
                    ),
                    is_fiscal_year_start=(d == fy_start),
                )

        raise ValueError(f"Date {d} not found in fiscal year {fiscal_year} boundaries")

    @property
    def name(self) -> str:
        return "13-Period"

    @property
    def period_count(self) -> int:
        return 13


# ── Factory ──────────────────────────────────────────────────────────────

FISCAL_CALENDAR_TYPES: dict[str, type[FiscalCalendar]] = {
    "nrf-454": NRF454Calendar,
    "nrf-445": NRF445Calendar,
    "nrf-544": NRF544Calendar,
    "13-period": ThirteenPeriodCalendar,
}


def create_fiscal_calendar(calendar_type: str) -> FiscalCalendar:
    """Create a fiscal calendar instance by type name.

    Args:
        calendar_type: One of "nrf-454", "nrf-445", "nrf-544", "13-period"

    Returns:
        A FiscalCalendar instance

    Raises:
        ValueError: If the calendar_type is not recognized
    """
    cls = FISCAL_CALENDAR_TYPES.get(calendar_type)
    if cls is None:
        available = ", ".join(sorted(FISCAL_CALENDAR_TYPES.keys()))
        raise ValueError(
            f"Unknown fiscal calendar type: {calendar_type!r}. Available: {available}"
        )
    return cls()


# ── Bulk lookup builder ──────────────────────────────────────────────────


def build_fiscal_lookup(
    fiscal_cal: FiscalCalendar,
    start_date: date,
    end_date: date,
) -> dict[str, FiscalPeriodInfo]:
    """Build a dict mapping YYYYMMDD -> FiscalPeriodInfo for a date range.

    This pre-computes fiscal info for every date in the range so the
    renderer can do O(1) lookups per day box.

    Args:
        fiscal_cal: A FiscalCalendar instance
        start_date: First date (inclusive)
        end_date: Last date (inclusive)

    Returns:
        Dict keyed by YYYYMMDD string
    """
    lookup: dict[str, FiscalPeriodInfo] = {}
    current = start_date
    while current <= end_date:
        key = current.strftime("%Y%m%d")
        lookup[key] = fiscal_cal.get_period_info(current)
        current += timedelta(days=1)
    return lookup
