"""Tests for the `dd` two-letter weekday format token."""

import arrow
import pytest

from shared.date_utils import format_arrow_date


@pytest.mark.parametrize(
    "year,month,day,expected",
    [
        (2026, 4, 27, "Mo"),  # Monday
        (2026, 4, 28, "Tu"),
        (2026, 4, 29, "We"),
        (2026, 4, 30, "Th"),
        (2026, 5, 1, "Fr"),
        (2026, 5, 2, "Sa"),
        (2026, 5, 3, "Su"),
    ],
)
def test_dd_token_yields_two_letter_weekday(year, month, day, expected):
    assert format_arrow_date(arrow.Arrow(year, month, day), "dd") == expected


def test_dd_combined_with_other_tokens():
    d = arrow.Arrow(2026, 4, 29)
    assert format_arrow_date(d, "dd MMM D") == "We Apr 29"
    assert format_arrow_date(d, "dd, MMM D YYYY") == "We, Apr 29 2026"
    assert format_arrow_date(d, "dd-MM") == "We-04"


def test_dd_does_not_break_ddd_or_dddd():
    d = arrow.Arrow(2026, 4, 29)
    assert format_arrow_date(d, "ddd") == "Wed"
    assert format_arrow_date(d, "dddd") == "Wednesday"
    assert format_arrow_date(d, "dddd dd") == "Wednesday We"


def test_dd_inside_literal_escape_is_preserved():
    d = arrow.Arrow(2026, 4, 29)
    assert format_arrow_date(d, "[dd]") == "dd"
    assert format_arrow_date(d, "[start dd] dd") == "start dd We"


def test_format_without_dd_unchanged():
    d = arrow.Arrow(2026, 4, 29)
    assert format_arrow_date(d, "YYYY-MM-DD") == "2026-04-29"
    assert format_arrow_date(d, "MMM D") == "Apr 29"


def test_empty_format_unchanged():
    d = arrow.Arrow(2026, 4, 29)
    assert format_arrow_date(d, "") == ""
