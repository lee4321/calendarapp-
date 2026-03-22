"""Tests for fiscal calendar implementations."""

import unittest
from datetime import date, timedelta

from shared.fiscal_calendars import (
    NRF454Calendar,
    NRF445Calendar,
    NRF544Calendar,
    ThirteenPeriodCalendar,
    build_fiscal_lookup,
    create_fiscal_calendar,
)


class TestNRF454FiscalYearStart(unittest.TestCase):
    """Test that fiscal year start dates match NRF calendar rules.

    The NRF fiscal year starts on the Sunday closest to February 1.
    """

    def setUp(self):
        self.cal = NRF454Calendar()

    def test_fy2026_feb1_is_sunday(self):
        # Feb 1, 2026 is a Sunday -> fiscal year starts Feb 1
        start = self.cal.fiscal_year_start(2026)
        self.assertEqual(start, date(2026, 2, 1))
        self.assertEqual(start.weekday(), 6)  # Sunday

    def test_fy2025_closest_sunday(self):
        # Feb 1, 2025 is Saturday -> closest Sunday is Feb 2
        start = self.cal.fiscal_year_start(2025)
        self.assertEqual(start, date(2025, 2, 2))
        self.assertEqual(start.weekday(), 6)

    def test_fy2024_closest_sunday(self):
        # Feb 1, 2024 is Thursday -> closest Sunday is Jan 28
        start = self.cal.fiscal_year_start(2024)
        self.assertEqual(start, date(2024, 2, 4))
        self.assertEqual(start.weekday(), 6)

    def test_fy2023_closest_sunday(self):
        # Feb 1, 2023 is Wednesday -> closest Sunday is Jan 29
        start = self.cal.fiscal_year_start(2023)
        self.assertEqual(start, date(2023, 1, 29))
        self.assertEqual(start.weekday(), 6)

    def test_fy2022_closest_sunday(self):
        # Feb 1, 2022 is Tuesday -> closest Sunday is Jan 30
        start = self.cal.fiscal_year_start(2022)
        self.assertEqual(start, date(2022, 1, 30))
        self.assertEqual(start.weekday(), 6)

    def test_all_start_on_sunday(self):
        """Every fiscal year must start on a Sunday."""
        for year in range(2020, 2035):
            start = self.cal.fiscal_year_start(year)
            self.assertEqual(
                start.weekday(), 6, f"FY{year} starts on {start} which is not Sunday"
            )

    def test_start_within_jan29_feb4_range(self):
        """Fiscal year start must fall in the Jan 29 - Feb 4 window."""
        for year in range(2020, 2035):
            start = self.cal.fiscal_year_start(year)
            jan29 = date(year, 1, 29)
            feb4 = date(year, 2, 4)
            self.assertTrue(
                jan29 <= start <= feb4,
                f"FY{year} starts on {start}, outside Jan 29 - Feb 4",
            )


class TestNRF454PeriodBoundaries(unittest.TestCase):
    """Test that period boundaries follow the 4-5-4 week pattern."""

    def setUp(self):
        self.cal = NRF454Calendar()

    def test_fy2026_has_12_periods(self):
        boundaries = self.cal.get_period_boundaries(2026)
        self.assertEqual(len(boundaries), 12)

    def test_fy2026_pattern_is_454(self):
        """Period lengths should be 4-5-4-4-5-4-4-5-4-4-5-4 weeks."""
        boundaries = self.cal.get_period_boundaries(2026)
        expected = [4, 5, 4, 4, 5, 4, 4, 5, 4, 4, 5, 4]
        for (start, end, _), exp_weeks in zip(boundaries, expected):
            actual_days = (end - start).days + 1
            actual_weeks = actual_days // 7
            self.assertEqual(
                actual_weeks,
                exp_weeks,
                f"Period starting {start}: expected {exp_weeks} weeks, got {actual_weeks}",
            )

    def test_periods_are_contiguous(self):
        """Each period must start the day after the previous period ends."""
        boundaries = self.cal.get_period_boundaries(2026)
        for i in range(1, len(boundaries)):
            prev_end = boundaries[i - 1][1]
            curr_start = boundaries[i][0]
            self.assertEqual(
                curr_start,
                prev_end + timedelta(days=1),
                f"Gap between period {i} and {i + 1}",
            )

    def test_first_period_starts_on_fy_start(self):
        boundaries = self.cal.get_period_boundaries(2026)
        fy_start = self.cal.fiscal_year_start(2026)
        self.assertEqual(boundaries[0][0], fy_start)

    def test_last_period_ends_before_next_fy(self):
        boundaries = self.cal.get_period_boundaries(2026)
        next_fy_start = self.cal.fiscal_year_start(2027)
        last_end = boundaries[-1][1]
        self.assertEqual(last_end + timedelta(days=1), next_fy_start)

    def test_each_quarter_is_13_weeks(self):
        """Each quarter (3 periods) should total exactly 13 weeks."""
        boundaries = self.cal.get_period_boundaries(2026)
        for q in range(4):
            q_periods = boundaries[q * 3 : (q + 1) * 3]
            total_days = sum((end - start).days + 1 for start, end, _ in q_periods)
            self.assertEqual(
                total_days, 91, f"Q{q + 1} has {total_days} days, expected 91"
            )


class TestNRF454_53WeekYear(unittest.TestCase):
    """Test 53-week year detection and handling."""

    def setUp(self):
        self.cal = NRF454Calendar()

    def test_53_week_year_detection(self):
        """Known 53-week years: the gap between consecutive FY starts is 371 days."""
        # Check a range for 53-week years
        fifty_three_week_years = []
        for year in range(2015, 2035):
            if self.cal._has_53_weeks(year):
                fifty_three_week_years.append(year)
        # There should be some 53-week years in the range
        self.assertTrue(len(fifty_three_week_years) > 0)

    def test_53_week_year_last_period_gets_extra_week(self):
        """In a 53-week year, period 12 should be 5 weeks instead of 4."""
        for year in range(2015, 2035):
            if self.cal._has_53_weeks(year):
                boundaries = self.cal.get_period_boundaries(year)
                last_start, last_end, _ = boundaries[-1]
                last_weeks = ((last_end - last_start).days + 1) // 7
                self.assertEqual(
                    last_weeks, 5, f"FY{year} period 12 should be 5 weeks (53-wk year)"
                )
                break

    def test_52_week_year_total(self):
        """A standard 52-week year has exactly 364 days."""
        for year in range(2020, 2035):
            if not self.cal._has_53_weeks(year):
                boundaries = self.cal.get_period_boundaries(year)
                total = sum((end - start).days + 1 for start, end, _ in boundaries)
                self.assertEqual(total, 364, f"FY{year} should have 364 days")
                break

    def test_53_week_year_total(self):
        """A 53-week year has exactly 371 days."""
        for year in range(2020, 2035):
            if self.cal._has_53_weeks(year):
                boundaries = self.cal.get_period_boundaries(year)
                total = sum((end - start).days + 1 for start, end, _ in boundaries)
                self.assertEqual(total, 371, f"FY{year} should have 371 days")
                break


class TestNRF454PeriodInfo(unittest.TestCase):
    """Test get_period_info for specific dates."""

    def setUp(self):
        self.cal = NRF454Calendar()

    def test_first_day_of_fy(self):
        fy_start = self.cal.fiscal_year_start(2026)
        info = self.cal.get_period_info(fy_start)
        self.assertEqual(info.fiscal_year, 2026)
        self.assertEqual(info.fiscal_period, 1)
        self.assertEqual(info.fiscal_quarter, 1)
        self.assertEqual(info.fiscal_week, 1)
        self.assertTrue(info.is_period_start)
        self.assertTrue(info.is_quarter_start)
        self.assertTrue(info.is_fiscal_year_start)

    def test_mid_period_date(self):
        fy_start = self.cal.fiscal_year_start(2026)
        mid = fy_start + timedelta(days=10)
        info = self.cal.get_period_info(mid)
        self.assertEqual(info.fiscal_period, 1)
        self.assertFalse(info.is_period_start)
        self.assertFalse(info.is_fiscal_year_start)

    def test_second_period_start(self):
        boundaries = self.cal.get_period_boundaries(2026)
        p2_start = boundaries[1][0]
        info = self.cal.get_period_info(p2_start)
        self.assertEqual(info.fiscal_period, 2)
        self.assertTrue(info.is_period_start)
        self.assertFalse(info.is_quarter_start)  # P2 is not a quarter start

    def test_quarter_2_start(self):
        """Period 4 is the start of Q2."""
        boundaries = self.cal.get_period_boundaries(2026)
        p4_start = boundaries[3][0]
        info = self.cal.get_period_info(p4_start)
        self.assertEqual(info.fiscal_period, 4)
        self.assertEqual(info.fiscal_quarter, 2)
        self.assertTrue(info.is_quarter_start)

    def test_date_before_fy_start(self):
        """A date before FY2026 start should belong to FY2025."""
        fy_start = self.cal.fiscal_year_start(2026)
        before = fy_start - timedelta(days=1)
        info = self.cal.get_period_info(before)
        self.assertEqual(info.fiscal_year, 2025)
        self.assertEqual(info.fiscal_period, 12)

    def test_short_name_format(self):
        fy_start = self.cal.fiscal_year_start(2026)
        info = self.cal.get_period_info(fy_start)
        self.assertEqual(info.period_short_name, "P1")
        self.assertEqual(info.period_name, "Period 1")


class TestNRF445Variant(unittest.TestCase):
    """Test the 4-4-5 variant."""

    def setUp(self):
        self.cal = NRF445Calendar()

    def test_pattern_is_445(self):
        boundaries = self.cal.get_period_boundaries(2026)
        expected = [4, 4, 5, 4, 4, 5, 4, 4, 5, 4, 4, 5]
        for (start, end, _), exp_weeks in zip(boundaries, expected):
            actual_weeks = ((end - start).days + 1) // 7
            self.assertEqual(actual_weeks, exp_weeks)

    def test_same_fy_start_as_454(self):
        cal454 = NRF454Calendar()
        for year in range(2020, 2030):
            self.assertEqual(
                self.cal.fiscal_year_start(year), cal454.fiscal_year_start(year)
            )


class TestNRF544Variant(unittest.TestCase):
    """Test the 5-4-4 variant."""

    def setUp(self):
        self.cal = NRF544Calendar()

    def test_pattern_is_544(self):
        boundaries = self.cal.get_period_boundaries(2026)
        expected = [5, 4, 4, 5, 4, 4, 5, 4, 4, 5, 4, 4]
        for (start, end, _), exp_weeks in zip(boundaries, expected):
            actual_weeks = ((end - start).days + 1) // 7
            self.assertEqual(actual_weeks, exp_weeks)


class TestThirteenPeriodCalendar(unittest.TestCase):
    """Test the 13-period calendar."""

    def setUp(self):
        self.cal = ThirteenPeriodCalendar()

    def test_has_13_periods(self):
        boundaries = self.cal.get_period_boundaries(2026)
        self.assertEqual(len(boundaries), 13)

    def test_all_periods_4_weeks_in_52_week_year(self):
        for year in range(2020, 2035):
            if not self.cal._has_53_weeks(year):
                boundaries = self.cal.get_period_boundaries(year)
                for start, end, num in boundaries:
                    weeks = ((end - start).days + 1) // 7
                    self.assertEqual(
                        weeks, 4, f"FY{year} P{num}: expected 4 weeks, got {weeks}"
                    )
                break

    def test_period_13_gets_5_weeks_in_53_week_year(self):
        for year in range(2020, 2035):
            if self.cal._has_53_weeks(year):
                boundaries = self.cal.get_period_boundaries(year)
                last_start, last_end, _ = boundaries[-1]
                weeks = ((last_end - last_start).days + 1) // 7
                self.assertEqual(weeks, 5)
                break

    def test_period_count_property(self):
        self.assertEqual(self.cal.period_count, 13)

    def test_quarter_assignment_for_period_13(self):
        """Period 13 should be assigned to Q4."""
        for year in range(2020, 2035):
            boundaries = self.cal.get_period_boundaries(year)
            p13_start = boundaries[12][0]
            info = self.cal.get_period_info(p13_start)
            self.assertEqual(info.fiscal_quarter, 4)
            break


class TestBuildFiscalLookup(unittest.TestCase):
    """Test the bulk lookup builder."""

    def setUp(self):
        self.cal = NRF454Calendar()

    def test_lookup_covers_all_dates(self):
        start = date(2026, 1, 25)
        end = date(2026, 3, 15)
        lookup = build_fiscal_lookup(self.cal, start, end)

        d = start
        while d <= end:
            key = d.strftime("%Y%m%d")
            self.assertIn(key, lookup, f"Missing lookup entry for {d}")
            d += timedelta(days=1)

    def test_lookup_values_match_direct_call(self):
        start = date(2026, 2, 1)
        end = date(2026, 2, 28)
        lookup = build_fiscal_lookup(self.cal, start, end)

        for d_offset in range(28):
            d = start + timedelta(days=d_offset)
            key = d.strftime("%Y%m%d")
            direct = self.cal.get_period_info(d)
            self.assertEqual(lookup[key], direct)

    def test_lookup_spans_fiscal_year_boundary(self):
        """Lookup across two fiscal years should work correctly."""
        start = date(2026, 1, 1)
        end = date(2026, 3, 1)
        lookup = build_fiscal_lookup(self.cal, start, end)

        # Jan dates should be FY2025
        self.assertEqual(lookup["20260115"].fiscal_year, 2025)
        # Feb dates (after FY start) should be FY2026
        self.assertEqual(lookup["20260201"].fiscal_year, 2026)


class TestCreateFiscalCalendar(unittest.TestCase):
    """Test the factory function."""

    def test_creates_nrf454(self):
        cal = create_fiscal_calendar("nrf-454")
        self.assertIsInstance(cal, NRF454Calendar)

    def test_creates_nrf445(self):
        cal = create_fiscal_calendar("nrf-445")
        self.assertIsInstance(cal, NRF445Calendar)

    def test_creates_nrf544(self):
        cal = create_fiscal_calendar("nrf-544")
        self.assertIsInstance(cal, NRF544Calendar)

    def test_creates_13_period(self):
        cal = create_fiscal_calendar("13-period")
        self.assertIsInstance(cal, ThirteenPeriodCalendar)

    def test_unknown_type_raises(self):
        with self.assertRaises(ValueError):
            create_fiscal_calendar("unknown")


if __name__ == "__main__":
    unittest.main()
