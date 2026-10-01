"""resolve_today / today_position and the shared holiday day-style resolver."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from config.config import CalendarConfig
from config.theme_schema import DayClass, Holidays
from shared.db_access import CalendarDB
from shared.holidays import DayStyle, resolve_day_styles, style_for
from shared.span import Span
from shared.today import parse_day, resolve_today, today_position

FRI, SAT, SUN, MON = (date(2026, 5, d) for d in (8, 9, 10, 11))


class TestToday:
    @pytest.mark.parametrize("text", ["20260509", "2026-05-09", " 20260509 "])
    def test_parses_both_forms(self, text):
        assert parse_day(text) == SAT

    @pytest.mark.parametrize("text", [None, "", "yesterday", "2026130", "20261301"])
    def test_unparseable_is_none(self, text):
        assert parse_day(text) is None

    def test_pinned_date_beats_the_clock(self):
        assert resolve_today("20260509", clock=lambda: date(2000, 1, 1)) == SAT

    def test_clock_when_nothing_is_pinned_or_the_pin_is_bad(self):
        clock = lambda: date(2000, 1, 1)  # noqa: E731
        assert resolve_today(None, clock) == date(2000, 1, 1)
        assert resolve_today("nonsense", clock) == date(2000, 1, 1)

    def test_position_is_the_cell_centre_and_none_outside(self):
        span = Span([FRI + timedelta(days=i) for i in range(4)], 0, 40)
        assert today_position(SAT, span) == 15
        assert today_position(date(2026, 6, 1), span) is None

    def test_a_hidden_saturday_lands_on_monday(self):
        span = Span([FRI, MON], 0, 20)
        assert today_position(SAT, span) == today_position(MON, span) == 15


class FakeDB(CalendarDB):
    """Just enough of CalendarDB for the classifier and the holiday band."""

    def __init__(self, federal=(), company=(), flags=None):
        self.federal, self.company, self.flags = set(federal), set(company), flags or {}

    def is_government_nonworkday(self, daykey, country=None):
        return daykey in self.federal

    def get_special_days_for_date(self, daykey):
        return [{"nonworkday": 1}] if daykey in self.company else []

    def get_holidays_for_date(self, daykey, country=None):
        return self.flags.get(daykey, [])


HOLIDAYS = Holidays(
    federal=DayClass(color="red", opacity=0.3),
    company=DayClass(color="green", opacity=0.2, icon="building"),
    weekend=DayClass(color=None, opacity=0.1, icon="moon"),
)


class TestStyleFor:
    def test_ordinary_day_has_no_style(self):
        assert style_for(frozenset(), HOLIDAYS) == (None, 1.0, None)

    def test_federal_beats_company_for_the_fill(self):
        fill, opacity, icon = style_for(frozenset({"federal_holiday", "company_holiday"}), HOLIDAYS)
        assert (fill, opacity) == ("red", 0.3)
        assert icon == "building"  # federal sets no icon, so the next class that does supplies it

    def test_weekend_without_a_colour_only_gives_its_icon(self):
        assert style_for(frozenset({"weekend"}), HOLIDAYS) == (None, 1.0, "moon")


class TestResolveDayStyles:
    def config(self):
        return CalendarConfig()

    def test_weekend_is_classified_from_the_config(self):
        cfg = self.config()
        cfg.weekend_style = 1  # weekends are shown, so Saturday and Sunday are non-working
        styles = resolve_day_styles([FRI, SAT], None, cfg, HOLIDAYS)
        assert styles[FRI] == DayStyle()
        assert styles[SAT].classes == {"weekend"}
        assert (styles[SAT].fill, styles[SAT].icon) == (None, "moon")

    def test_workweek_style_has_no_weekend_class(self):
        cfg = self.config()
        cfg.weekend_style = 0
        assert resolve_day_styles([SAT], None, cfg, HOLIDAYS)[SAT] == DayStyle()

    def test_federal_holiday_gets_fill_and_flag(self):
        flag = {"icon": "flag-us", "displayname": "Independence Day", "nonworkday": 1, "country": "US"}
        db = FakeDB(federal={"20260508"}, flags={"20260508": [flag]})
        styles = resolve_day_styles([FRI, MON], db, self.config(), HOLIDAYS)
        assert styles[FRI].fill == "red"
        assert styles[FRI].flags[0].icon == "flag-us"
        assert styles[FRI].best_icon == "flag-us"
        assert styles[MON] == DayStyle()

    def test_static_icon_is_used_when_no_flag(self):
        db = FakeDB(company={"20260511"})
        styles = resolve_day_styles([MON], db, self.config(), HOLIDAYS)
        assert (styles[MON].fill, styles[MON].icon, styles[MON].best_icon) == ("green", "building", "building")

    def test_observances_are_flagged_only_when_asked(self):
        obs = {"icon": "flag-ca", "displayname": "Groundhog Day", "nonworkday": 0, "country": "CA"}
        db = FakeDB(flags={"20260508": [obs]})
        assert resolve_day_styles([FRI], db, self.config(), HOLIDAYS)[FRI].flags == ()
        assert (
            resolve_day_styles([FRI], db, self.config(), HOLIDAYS, nonworkdays_only=False)[FRI].flags[0].icon
            == "flag-ca"
        )
