"""Coverage for holiday-category loading in :mod:`shared.db_access`.

The loader must pull *every* category the ``holidays`` package reports for a
country, not a fixed list, and must classify them into shaded non-working days
versus informational titles.
"""

from datetime import date

import pytest

from shared.db_access import CalendarDB


class _FakeHolidays(dict):
    """Stand-in for a ``holidays`` country object: a {date: name} mapping."""

    def __init__(self, mapping, supported):
        super().__init__(mapping)
        self.supported_categories = supported


class _FakeLib:
    """Stand-in for the ``holidays`` module with scripted per-category data."""

    def __init__(self, supported, by_category):
        self._supported = supported
        self._by_category = by_category
        self.requested: list[str] = []

    def country_holidays(self, country, years, categories=None):
        if categories is None:
            return _FakeHolidays({}, self._supported)
        (cat,) = categories
        self.requested.append(cat)
        return _FakeHolidays(self._by_category.get(cat, {}), self._supported)


def _entries(db, daykey):
    return [(e["displayname"], e["nonworkday"]) for e in db._python_holidays[daykey]]


def test_every_supported_category_is_loaded(tmp_path):
    """Categories outside the old hard-coded five must still be loaded."""
    lib = _FakeLib(
        supported={"public", "bank", "school", "hebrew", "workday", "catholic"},
        by_category={
            "public": {date(2026, 1, 1): "New Year"},
            "bank": {date(2026, 12, 31): "Bank Closure"},
            "school": {date(2026, 4, 6): "Spring Break"},
            "hebrew": {date(2026, 12, 5): "Hanukkah"},
            "workday": {date(2026, 5, 9): "Make-up Workday"},
            "catholic": {date(2026, 4, 3): "Good Friday"},
        },
    )
    db = CalendarDB(str(tmp_path / "cal.sqlite"))
    db._load_country_holidays(lib, "XX", [2026])

    assert set(lib.requested) == lib._supported
    assert _entries(db, "20260101") == [("New Year", 1)]
    # 'bank' counts as non-working; the rest are informational.
    assert _entries(db, "20261231") == [("Bank Closure", 1)]
    assert _entries(db, "20260406") == [("Spring Break", 0)]
    assert _entries(db, "20261205") == [("Hanukkah", 0)]
    assert _entries(db, "20260509") == [("Make-up Workday", 0)]
    assert _entries(db, "20260403") == [("Good Friday", 0)]


def test_unknown_category_is_loaded_as_informational(tmp_path):
    """A category this codebase has never heard of must not be dropped."""
    lib = _FakeLib(
        supported={"public", "brand_new_category"},
        by_category={
            "public": {date(2026, 1, 1): "New Year"},
            "brand_new_category": {date(2026, 7, 4): "Something Novel"},
        },
    )
    db = CalendarDB(str(tmp_path / "cal.sqlite"))
    db._load_country_holidays(lib, "XX", [2026])

    assert _entries(db, "20260704") == [("Something Novel", 0)]


def test_combined_holiday_names_are_split(tmp_path):
    """Dates carrying several holidays arrive joined; each becomes an entry."""
    lib = _FakeLib(
        supported={"public"},
        by_category={"public": {date(2026, 10, 2): "Dussehra; Gandhi Jayanti"}},
    )
    db = CalendarDB(str(tmp_path / "cal.sqlite"))
    db._load_country_holidays(lib, "XX", [2026])

    assert _entries(db, "20261002") == [("Dussehra", 1), ("Gandhi Jayanti", 1)]


def test_nonwork_category_precedence_and_union(tmp_path):
    """'public' names win a shared date; other nonwork categories add dates."""
    lib = _FakeLib(
        supported={"public", "government", "bank"},
        by_category={
            "public": {date(2026, 1, 1): "New Year"},
            "government": {
                date(2026, 1, 1): "Federal New Year",
                date(2026, 12, 26): "Boxing Day",
            },
            "bank": {date(2026, 12, 24): "Christmas Eve"},
        },
    )
    db = CalendarDB(str(tmp_path / "cal.sqlite"))
    db._load_country_holidays(lib, "XX", [2026])

    assert _entries(db, "20260101") == [("New Year", 1)]
    assert _entries(db, "20261226") == [("Boxing Day", 1)]
    assert _entries(db, "20261224") == [("Christmas Eve", 1)]


def test_informational_holiday_shares_a_nonwork_date(tmp_path):
    """An informational name on a shaded date is kept, but ranked after it."""
    lib = _FakeLib(
        supported={"public", "unofficial"},
        by_category={
            "public": {date(2026, 12, 25): "Christmas Day"},
            "unofficial": {
                date(2026, 12, 25): "Christmas Day",  # duplicate name, dropped
                date(2026, 12, 26): "Boxing Day",
            },
        },
    )
    db = CalendarDB(str(tmp_path / "cal.sqlite"))
    db._load_country_holidays(lib, "XX", [2026])

    assert _entries(db, "20261225") == [("Christmas Day", 1)]
    assert _entries(db, "20261226") == [("Boxing Day", 0)]

    # The shaded holiday stays first, so single-title callers keep showing it.
    lib2 = _FakeLib(
        supported={"public", "christian"},
        by_category={
            "public": {date(2026, 4, 5): "Easter Sunday"},
            "christian": {date(2026, 4, 5): "Resurrection Sunday"},
        },
    )
    db2 = CalendarDB(str(tmp_path / "cal2.sqlite"))
    db2._load_country_holidays(lib2, "XX", [2026])
    assert _entries(db2, "20260405") == [
        ("Easter Sunday", 1),
        ("Resurrection Sunday", 0),
    ]
    assert db2.is_government_nonworkday("20260405", "XX") is True


def test_unsupported_country_is_skipped(tmp_path):
    class _Missing:
        def country_holidays(self, country, years, categories=None):
            raise NotImplementedError(country)

    db = CalendarDB(str(tmp_path / "cal.sqlite"))
    db._load_country_holidays(_Missing(), "ZZ", [2026])

    assert db._python_holidays == {}


def test_real_package_loads_beyond_public_category(tmp_path):
    """Smoke test against the installed package for a non-public category."""
    holidays_lib = pytest.importorskip("holidays")

    supported = set(
        holidays_lib.country_holidays("JP", years=[2026]).supported_categories
    )
    if "bank" not in supported:
        pytest.skip("installed 'holidays' has no bank category for JP")

    db = CalendarDB(str(tmp_path / "cal.sqlite"))
    db.load_python_holidays("JP", "20260101", "20261231")

    bank_only = holidays_lib.country_holidays("JP", years=[2026], categories=("bank",))
    public = holidays_lib.country_holidays("JP", years=[2026], categories=("public",))
    extra = [d for d in bank_only if d not in public]
    assert extra, "expected JP bank holidays outside the public category"
    for d in extra:
        assert db._python_holidays.get(d.strftime("%Y%m%d")), (
            f"{d} missing from loaded holidays"
        )
