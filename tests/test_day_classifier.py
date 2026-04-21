"""Tests for shared.day_classifier."""
from datetime import date

import pytest

from config.config import create_calendar_config
from shared.day_classifier import (
    classify_day,
    classify_days,
    day_rule_matches,
    rule_has_day_keys,
)


class _DB:
    def __init__(
        self,
        govt: set[str] | None = None,
        company: set[str] | None = None,
    ) -> None:
        self._govt = govt or set()
        self._company = company or set()

    def is_government_nonworkday(self, daykey, country=None):
        return daykey in self._govt

    def get_special_days_for_date(self, daykey):
        if daykey in self._company:
            return [{"nonworkday": 1, "name": "Co. Holiday"}]
        return []


def _cfg(**kw):
    c = create_calendar_config()
    for k, v in kw.items():
        setattr(c, k, v)
    return c


def test_weekend_only():
    c = _cfg(weekend_style=1)  # weekends visible → derives {5, 6}
    assert classify_day(date(2026, 4, 25), None, c) == frozenset({"weekend"})  # Sat
    assert classify_day(date(2026, 4, 27), None, c) == frozenset()  # Mon


def test_custom_weekend_days_middle_east():
    c = _cfg(weekend_days=[4, 5])  # Fri/Sat
    assert "weekend" in classify_day(date(2026, 4, 24), None, c)  # Fri
    assert "weekend" in classify_day(date(2026, 4, 25), None, c)  # Sat
    assert "weekend" not in classify_day(date(2026, 4, 26), None, c)  # Sun


def test_federal_holiday_detected():
    c = _cfg()
    db = _DB(govt={"20260526"})
    classes = classify_day(date(2026, 5, 26), db, c)
    assert "federal_holiday" in classes


def test_company_holiday_detected():
    c = _cfg()
    db = _DB(company={"20260701"})
    classes = classify_day(date(2026, 7, 1), db, c)
    assert "company_holiday" in classes


def test_overlapping_classes():
    c = _cfg(weekend_days=[5, 6])
    # Sat + federal → two classes returned
    db = _DB(govt={"20260704"})
    classes = classify_day(date(2026, 7, 4), db, c)  # Sat, Independence Day
    assert classes >= frozenset({"federal_holiday", "weekend"})


def test_db_none_only_weekend_runs():
    c = _cfg(weekend_days=[5, 6])
    assert classify_day(date(2026, 5, 2), None, c) == frozenset({"weekend"})
    assert classify_day(date(2026, 5, 4), None, c) == frozenset()


def test_classify_days_batch():
    c = _cfg(weekend_days=[5, 6])
    days = [date(2026, 5, 1), date(2026, 5, 2), date(2026, 5, 3)]
    out = classify_days(days, None, c)
    assert out[date(2026, 5, 1)] == frozenset()      # Fri
    assert out[date(2026, 5, 2)] == frozenset({"weekend"})
    assert out[date(2026, 5, 3)] == frozenset({"weekend"})


def test_day_rule_matches_keys():
    # Positive matches
    assert day_rule_matches(frozenset({"weekend"}), {"weekend": True})
    assert day_rule_matches(frozenset({"federal_holiday"}), {"federal_holiday": True})
    assert day_rule_matches(frozenset({"company_holiday"}), {"nonworkday": True})
    # Negative match (False means "absent")
    assert day_rule_matches(frozenset(), {"weekend": False})
    assert not day_rule_matches(frozenset({"weekend"}), {"weekend": False})
    # Rule with no day keys → False
    assert not day_rule_matches(frozenset({"weekend"}), {"milestone": True})


def test_rule_has_day_keys():
    assert rule_has_day_keys({"weekend": True})
    assert rule_has_day_keys({"nonworkday": True})
    assert not rule_has_day_keys({"milestone": True, "icon": "flag"})


def test_weekend_days_validation_rejects_bad_input():
    from config.config import CalendarConfig

    with pytest.raises(ValueError):
        CalendarConfig(weekend_days=[7])
    with pytest.raises(ValueError):
        CalendarConfig(weekend_days=[0, 0])


def test_get_weekend_days_style_zero_is_empty():
    c = _cfg(weekend_style=0)
    assert c.get_weekend_days() == frozenset()


def test_get_weekend_days_explicit_override():
    c = _cfg(weekend_style=0, weekend_days=[5, 6])
    assert c.get_weekend_days() == frozenset({5, 6})
