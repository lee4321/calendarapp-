"""The holiday band draws the flag carried by each holiday row.

Non-workday shading goes through ``classify_day``, which only reports
holidays flagged ``nonworkday=1``.  The holiday band reads the holiday rows
themselves, so it shows observances too, and each country brings its own
flag without any theme configuration.
"""

from __future__ import annotations

from datetime import date

import pytest

from config.config import CalendarConfig
from shared.holiday_band import HolidayMark, compute_holiday_band_days
from shared.timeband import build_segments
from test_gantt_marks import _DummyDB, render, task


class _HolidayDB:
    """Returns canned holiday rows keyed by daykey."""

    def __init__(self, rows: dict[str, list[dict]]):
        self._rows = rows
        self.asked_country: str | None = "unset"

    def get_holidays_for_date(self, daykey, country=None):
        self.asked_country = country
        return self._rows.get(daykey, [])


def _row(icon, name, nonworkday=1, country="US"):
    return {
        "icon": icon,
        "displayname": name,
        "nonworkday": nonworkday,
        "country": country,
    }


@pytest.fixture
def config() -> CalendarConfig:
    config = CalendarConfig()
    config.country = "US,UA"
    return config


DAYS = [date(2026, 1, 19), date(2026, 1, 20), date(2026, 2, 2)]


# ── Segment builder ───────────────────────────────────────────────────────


def test_holiday_bands_have_no_labelled_segments(config):
    """Like an icon band, the marks come from the visualizer, not here."""
    segments = build_segments(
        {"unit": "holiday", "label": "Holidays"},
        date(2026, 1, 1), date(2026, 3, 1), config,
    )
    assert segments == []


# ── Mark computation ──────────────────────────────────────────────────────


def test_every_visible_day_gets_an_entry(config):
    db = _HolidayDB({})
    marks = compute_holiday_band_days(DAYS, db, config)
    assert set(marks) == set(DAYS)
    assert all(value == [] for value in marks.values())


def test_flag_comes_from_the_holiday_row(config):
    db = _HolidayDB({"20260119": [_row("us", "Martin Luther King Jr. Day")]})
    marks = compute_holiday_band_days(DAYS, db, config)
    assert marks[date(2026, 1, 19)] == [
        HolidayMark(icon="us", title="Martin Luther King Jr. Day",
                    nonworkday=True, country="US")
    ]
    assert marks[date(2026, 1, 20)] == []


def test_observances_are_shown_even_though_shading_skips_them(config):
    """nonworkday=0 never reaches classify_day, so the band is its only home."""
    db = _HolidayDB({"20260202": [_row("us", "Groundhog Day", nonworkday=0)]})
    marks = compute_holiday_band_days(DAYS, db, config)
    assert [m.title for m in marks[date(2026, 2, 2)]] == ["Groundhog Day"]
    assert marks[date(2026, 2, 2)][0].nonworkday is False


def test_nonworkdays_only_drops_observances(config):
    db = _HolidayDB({"20260202": [_row("us", "Groundhog Day", nonworkday=0)]})
    marks = compute_holiday_band_days(DAYS, db, config, nonworkdays_only=True)
    assert marks[date(2026, 2, 2)] == []


def test_each_country_brings_its_own_flag(config):
    db = _HolidayDB({
        "20260119": [
            _row("us", "Martin Luther King Jr. Day"),
            _row("ua", "День праці", country="UA"),
        ]
    })
    marks = compute_holiday_band_days(DAYS, db, config)
    assert [m.icon for m in marks[date(2026, 1, 19)]] == ["us", "ua"]


def test_one_flag_per_country_and_the_closing_holiday_wins(config):
    """Two US holidays on one day must not draw the same flag twice."""
    db = _HolidayDB({
        "20260119": [
            _row("us", "An Observance", nonworkday=0),
            _row("us", "A Public Holiday", nonworkday=1),
        ]
    })
    marks = compute_holiday_band_days(DAYS, db, config)
    assert len(marks[date(2026, 1, 19)]) == 1
    assert marks[date(2026, 1, 19)][0].title == "A Public Holiday"


def test_a_holiday_without_an_icon_is_skipped(config):
    db = _HolidayDB({"20260119": [_row("", "Nameless Icon")]})
    marks = compute_holiday_band_days(DAYS, db, config)
    assert marks[date(2026, 1, 19)] == []


def test_the_band_follows_the_country_selection(config):
    db = _HolidayDB({})
    compute_holiday_band_days(DAYS, db, config)
    assert db.asked_country == "US,UA"


def test_no_db_yields_empty_marks(config):
    assert compute_holiday_band_days(DAYS, None, config) == {d: [] for d in DAYS}


def test_a_failing_lookup_does_not_break_the_render(config):
    class _Boom:
        @staticmethod
        def get_holidays_for_date(daykey, country=None):
            raise RuntimeError("db is unhappy")

    marks = compute_holiday_band_days(DAYS, _Boom(), config)
    assert marks == {d: [] for d in DAYS}


# ── Gantt rendering ───────────────────────────────────────────────────────
#
# These drive the real renderer through the shared gantt harness, so they
# catch a band that computes its marks but never draws them.


class _FlagDB(_DummyDB):
    """A gantt DummyDB that also answers holiday lookups."""

    def __init__(self, rows: dict[str, list[dict]] | None = None):
        self.rows = rows or {}

    def get_holidays_for_date(self, daykey, country=None):
        return self.rows.get(daykey, [])

    @staticmethod
    def get_icon_svg_map():
        return {"us": "<svg/>", "ua": "<svg/>"}


def _holiday_band(**overrides):
    band = {"label": "Holidays", "unit": "holiday"}
    band.update(overrides)
    return [band]


def test_the_gantt_draws_a_flag_in_the_holiday_band():
    db = _FlagDB({"20260204": [_row("us", "A Holiday")]})
    renderer = render(
        [task()], db=db,
        gantt_top_time_bands=_holiday_band(),
        gantt_bottom_time_bands=[],
    )
    flags = renderer.of_class(renderer.icons, "ec-holiday-icon")
    assert [f["icon"] for f in flags] == ["us"]


def test_two_countries_on_one_day_draw_two_flags():
    db = _FlagDB(
        {"20260204": [_row("us", "US Day"), _row("ua", "UA Day", country="UA")]}
    )
    renderer = render(
        [task()], db=db,
        gantt_top_time_bands=_holiday_band(),
        gantt_bottom_time_bands=[],
    )
    flags = renderer.of_class(renderer.icons, "ec-holiday-icon")
    assert sorted(f["icon"] for f in flags) == ["ua", "us"]
    # Side by side, not stacked on one x.
    assert len({round(f["x"], 3) for f in flags}) == 2


def test_the_band_draws_no_flag_on_an_ordinary_day():
    db = _FlagDB()
    renderer = render(
        [task()], db=db,
        gantt_top_time_bands=_holiday_band(),
        gantt_bottom_time_bands=[],
    )
    assert renderer.of_class(renderer.icons, "ec-holiday-icon") == []


def test_nonworkdays_only_hides_an_observance_in_the_gantt():
    db = _FlagDB({"20260204": [_row("us", "An Observance", nonworkday=0)]})
    renderer = render(
        [task()], db=db,
        gantt_top_time_bands=_holiday_band(nonworkdays_only=True),
        gantt_bottom_time_bands=[],
    )
    assert renderer.of_class(renderer.icons, "ec-holiday-icon") == []


def test_the_holiday_row_still_draws_its_cells():
    """The grid stays continuous with the bands above it."""
    db = _FlagDB()
    renderer = render(
        [task()], db=db,
        gantt_top_time_bands=_holiday_band(),
        gantt_bottom_time_bands=[],
    )
    assert renderer.of_class(renderer.rects, "ec-band-cell")
