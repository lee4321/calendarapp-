"""Calendar quarter and year units of the shared segment builder."""

from __future__ import annotations

from datetime import date

from config.config import CalendarConfig
from shared.timeband import build_segments


def seg(band, start, end):
    return [(s.start, s.end_exclusive, s.label) for s in build_segments(band, start, end, CalendarConfig())]


def test_quarters_are_labelled_and_clipped_to_the_range():
    got = seg({"unit": "quarter"}, date(2026, 2, 10), date(2026, 8, 20))
    assert got == [
        (date(2026, 2, 10), date(2026, 4, 1), "Q1"),
        (date(2026, 4, 1), date(2026, 7, 1), "Q2"),
        (date(2026, 7, 1), date(2026, 8, 21), "Q3"),
    ]


def test_quarter_label_format_placeholders():
    got = seg({"unit": "quarter", "label_format": "Q{q}-{yy}"}, date(2026, 1, 1), date(2026, 3, 31))
    assert [g[2] for g in got] == ["Q1-26"]


def test_a_range_across_a_year_boundary_numbers_quarters_from_each_year():
    got = seg({"unit": "quarter", "label_format": "{year}Q{q}"}, date(2025, 11, 1), date(2026, 2, 1))
    assert [g[2] for g in got] == ["2025Q4", "2026Q1"]


def test_years_default_to_four_digits():
    got = seg({"unit": "year"}, date(2025, 11, 1), date(2027, 2, 1))
    assert [g[2] for g in got] == ["2025", "2026", "2027"]
    assert got[0][:2] == (date(2025, 11, 1), date(2026, 1, 1))
    assert got[-1][:2] == (date(2027, 1, 1), date(2027, 2, 2))


def test_year_format_can_be_two_digits():
    assert [g[2] for g in seg({"unit": "year", "date_format": "YY"}, date(2026, 1, 1), date(2026, 12, 31))] == ["26"]
