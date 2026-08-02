"""Duration-string parsing: units, compounds, signs, and refusals.

`parse_duration` turns the free text schedule tools write into decimal
days.  It is the only place unit semantics are decided, so the whole
grammar is pinned here.
"""

import pytest

from shared.duration_parser import (
    DAYS_PER_MONTH,
    DAYS_PER_WEEK,
    HOURS_PER_DAY,
    parse_duration,
)


@pytest.mark.parametrize(
    "text,expected",
    [
        # Minutes
        ("30m", 30 / (HOURS_PER_DAY * 60)),
        ("30min", 30 / (HOURS_PER_DAY * 60)),
        ("30mins", 30 / (HOURS_PER_DAY * 60)),
        ("30minute", 30 / (HOURS_PER_DAY * 60)),
        ("30minutes", 30 / (HOURS_PER_DAY * 60)),
        # Hours
        ("4h", 0.5),
        ("4hr", 0.5),
        ("4hrs", 0.5),
        ("4hour", 0.5),
        ("4hours", 0.5),
        ("8h", 1.0),
        # Days
        ("1d", 1.0),
        ("1dy", 1.0),
        ("1day", 1.0),
        ("2days", 2.0),
        ("0.5d", 0.5),
        # Weeks
        ("1w", DAYS_PER_WEEK),
        ("1wk", DAYS_PER_WEEK),
        ("2wks", 2 * DAYS_PER_WEEK),
        ("1week", DAYS_PER_WEEK),
        ("1.5weeks", 1.5 * DAYS_PER_WEEK),
        # Months
        ("1mo", DAYS_PER_MONTH),
        ("2mos", 2 * DAYS_PER_MONTH),
        ("1mon", DAYS_PER_MONTH),
        ("1month", DAYS_PER_MONTH),
        ("3months", 3 * DAYS_PER_MONTH),
    ],
)
def test_every_unit_spelling(text, expected):
    assert parse_duration(text) == pytest.approx(expected)


def test_bare_number_is_days():
    assert parse_duration("3") == 3.0
    assert parse_duration(".5") == 0.5


def test_case_and_spacing_are_ignored():
    assert parse_duration("4 HR") == 0.5
    assert parse_duration("  4hr  ") == 0.5
    assert parse_duration("4Hr") == 0.5


@pytest.mark.parametrize(
    "text,expected",
    [
        ("1d 4h", 1.5),
        ("1d4h", 1.5),
        ("2w3d", 2 * DAYS_PER_WEEK + 3),
        ("1d 4h 30m", 1.5 + 30 / (HOURS_PER_DAY * 60)),
    ],
)
def test_compound_terms_sum(text, expected):
    assert parse_duration(text) == pytest.approx(expected)


@pytest.mark.parametrize("text,expected", [("-4h", -0.5), ("+1d", 1.0), ("-1d 4h", -1.5)])
def test_signed_values(text, expected):
    """The variance fields carry a leading sign."""
    assert parse_duration(text) == pytest.approx(expected)


def test_m_means_minutes_not_months():
    """'m' is minutes; months need 'mo' or longer."""
    assert parse_duration("1m") == pytest.approx(1 / (HOURS_PER_DAY * 60))
    assert parse_duration("1mo") == DAYS_PER_MONTH


@pytest.mark.parametrize(
    "text,expected",
    [
        # A lone comma with fewer than three digits after it is a decimal
        # comma, not a thousands separator.
        ("1,5", 1.5),
        ("1,5d", 1.5),
        ("1,50", 1.5),
        ("1,25d", 1.25),
        ("0,5d", 0.5),
        # Three digits after the comma reads as grouping.
        ("1,200", 1200.0),
        ("1,200h", 1200 / HOURS_PER_DAY),
        ("1,234,567", 1234567.0),
    ],
)
def test_lone_comma_is_decimal_or_grouping_by_shape(text, expected):
    assert parse_duration(text) == pytest.approx(expected)


@pytest.mark.parametrize(
    "text,expected",
    [
        ("1,234.5", 1234.5),  # commas group, dot is the decimal
        ("1.234,5", 1234.5),  # dots group, comma is the decimal
        ("1,234,567.5", 1234567.5),
    ],
)
def test_when_both_separators_appear_the_later_one_is_the_decimal(text, expected):
    assert parse_duration(text) == pytest.approx(expected)


def test_three_decimal_places_resolves_as_thousands():
    """The one real ambiguity, documented: '1,500' means fifteen hundred."""
    assert parse_duration("1,500") == 1500.0


def test_plain_dot_decimals_are_unaffected():
    assert parse_duration("1.5") == pytest.approx(1.5)
    assert parse_duration("1.5d") == pytest.approx(1.5)
    assert parse_duration("0.5d") == pytest.approx(0.5)


def test_numeric_input_passes_through_as_days():
    assert parse_duration(4) == 4.0
    assert parse_duration(2.5) == 2.5


@pytest.mark.parametrize(
    "text", [None, "", "   ", "n/a", "abc", "4hr of prep", "TBD", "-"]
)
def test_unparseable_returns_none(text):
    """A bad cell costs one field, not the row -- so None, never a raise."""
    assert parse_duration(text) is None


def test_zero_is_zero_not_none():
    """0 is a real value and must survive the None-ish checks."""
    assert parse_duration("0") == 0.0
    assert parse_duration("0d") == 0.0
