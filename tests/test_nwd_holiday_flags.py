"""A day that is a holiday in several countries shows every country's flag.

Blockplan and compactplan date cells used to draw only the first holiday's
flag, so a day closed in CA, GB and the US read as a Canadian holiday.  They
now lay each closed country's flag side by side in the cell, as the holiday
band does.  The weekly calendar already drew every flag in its top row; it
now draws a country's flag once when that country has two holidays that day.
"""
from __future__ import annotations

from pathlib import Path

import arrow

from config.config import create_calendar_config, setfontsizes
from visualizers.blockplan.layout import BlockPlanLayout
from visualizers.blockplan.renderer import BlockPlanRenderer
from visualizers.compactplan.layout import CompactPlanLayout
from visualizers.compactplan.renderer import CompactPlanRenderer
from visualizers.weekly.renderer import WeeklyCalendarRenderer

_SVG = '<svg viewBox="0 0 24 24"><rect width="24" height="24"/></svg>'


def _row(icon, name, nonworkday=1, country=None):
    return {
        "icon": icon,
        "displayname": name,
        "nonworkday": nonworkday,
        "country": country or icon.upper(),
    }


class _HolidayDB:
    """Stub DB whose holidays are canned rows keyed by daykey."""

    def __init__(self, rows: dict[str, list[dict]]):
        self._rows = rows

    def get_holidays_for_date(self, daykey, country=None):
        return list(self._rows.get(daykey, []))

    def is_government_nonworkday(self, daykey, country=None):
        return any(r.get("nonworkday") for r in self._rows.get(daykey, []))

    def is_nonworkday(self, daykey, country=None):
        return self.is_government_nonworkday(daykey, country)

    @staticmethod
    def get_special_days_for_date(daykey):
        return []

    @staticmethod
    def get_palette(name):
        return None

    @staticmethod
    def resolve_color_name(name):
        return name

    @staticmethod
    def get_icon_svg(name):
        return _SVG

    @staticmethod
    def get_icon_svg_map():
        return {name: _SVG for name in ("ca", "gb", "us", "in", "star")}


class _IconCapture:
    """Mixin recording icon draws and text, drawing nothing else."""

    def __init__(self):
        super().__init__()
        self.icon_calls: list[dict] = []
        self.text_values: list[str] = []

    def _draw_icon_svg(self, icon_name, x, baseline_y, size, **kwargs):
        self.icon_calls.append(
            {"icon_name": icon_name, "x": x, "size": size, **kwargs}
        )
        return True

    def _draw_text(self, x, y, text, font_name, font_size, **kwargs):
        self.text_values.append(str(text))

    def _draw_rect(self, *args, **kwargs):
        return None

    def _draw_line(self, *args, **kwargs):
        return None

    def nwd_icons(self) -> list[dict]:
        return [c for c in self.icon_calls if c.get("css_class") == "ec-nwd-icon"]


class _BlockPlan(_IconCapture, BlockPlanRenderer):
    pass


class _CompactPlan(_IconCapture, CompactPlanRenderer):
    pass


class _Weekly(_IconCapture, WeeklyCalendarRenderer):
    pass


_BP_HOLIDAY = "20260216"      # a Monday inside the blockplan range
_CP_HOLIDAY = "20260316"      # a Monday inside the compactplan range

_THREE_COUNTRIES = [
    _row("ca", "Holiday CA"),
    _row("gb", "Holiday GB"),
    _row("us", "Holiday US"),
]


def _blockplan(tmp_path: Path, rows: list[dict]) -> _BlockPlan:
    config = create_calendar_config()
    config.pageX, config.pageY = 792.0, 1224.0
    config = setfontsizes(config)
    config.weekend_style = 0
    config.userstart = config.adjustedstart = "20260209"
    config.userend = config.adjustedend = "20260220"
    config.outputfile = str(tmp_path / "bp.svg")
    config.blockplan_top_time_bands = [
        {"label": "Day", "unit": "date", "date_format": "D", "show_every": 1}
    ]
    config.blockplan_bottom_time_bands = []
    config.blockplan_swimlanes = [{"name": "Lane", "match": {}}]
    config.blockplan_federal_holiday_icon = "star"
    renderer = _BlockPlan()
    renderer.render(
        config, BlockPlanLayout().calculate(config), events=[],
        db=_HolidayDB({_BP_HOLIDAY: rows}),
    )
    return renderer


def _compactplan(tmp_path: Path, rows: list[dict]) -> _CompactPlan:
    config = create_calendar_config()
    config.pageX, config.pageY = 792.0, 612.0
    config = setfontsizes(config)
    config.weekend_style = 0
    config.adjustedstart = "20260309"
    config.adjustedend = "20260424"
    config.outputfile = str(tmp_path / "cp.svg")
    config.include_header = False
    config.include_footer = False
    config.compactplan_time_bands = [
        {"label": "Date", "unit": "date", "date_format": "D", "show_every": 1}
    ]
    config.compactplan_federal_holiday_icon = "star"
    renderer = _CompactPlan()
    renderer.render(
        config, CompactPlanLayout().calculate(config), [],
        _HolidayDB({_CP_HOLIDAY: rows}),
    )
    return renderer


# ── Blockplan / compactplan date cells ────────────────────────────────────


def test_blockplan_date_cell_shows_every_countrys_flag(tmp_path):
    renderer = _blockplan(tmp_path, _THREE_COUNTRIES)

    icons = renderer.nwd_icons()
    assert [c["icon_name"] for c in icons] == ["ca", "gb", "us"]
    # Side by side, left to right, all at the one-icon size.
    xs = [c["x"] for c in icons]
    assert xs == sorted(xs) and len(set(xs)) == 3
    assert len({c["size"] for c in icons}) == 1
    # The flags stand in for the date label, as a single flag did.
    assert "16" not in renderer.text_values


def test_compactplan_date_cell_shows_every_countrys_flag(tmp_path):
    renderer = _compactplan(tmp_path, _THREE_COUNTRIES)

    icons = renderer.nwd_icons()
    assert [c["icon_name"] for c in icons] == ["ca", "gb", "us"]
    xs = [c["x"] for c in icons]
    assert xs == sorted(xs) and len(set(xs)) == 3


def test_a_single_flag_stays_centred_in_its_cell(tmp_path):
    """One flag keeps the placement the date cell always gave it."""
    one = _blockplan(tmp_path, [_row("us", "Holiday US")]).nwd_icons()
    three = _blockplan(tmp_path, _THREE_COUNTRIES).nwd_icons()

    assert [c["icon_name"] for c in one] == ["us"]
    # The middle of three slots is the centre of the cell.
    assert one[0]["x"] == three[1]["x"]


def test_only_countries_that_close_get_a_flag(tmp_path):
    """An observance listed first no longer lends its flag to the closure."""
    renderer = _blockplan(tmp_path, [
        _row("ca", "Observance CA", nonworkday=0),
        _row("us", "Holiday US"),
    ])

    assert [c["icon_name"] for c in renderer.nwd_icons()] == ["us"]


def test_two_holidays_from_one_country_draw_one_flag(tmp_path):
    renderer = _compactplan(tmp_path, [
        _row("in", "Holiday A"),
        _row("in", "Holiday B"),
    ])

    assert [c["icon_name"] for c in renderer.nwd_icons()] == ["in"]


def test_holidays_without_flags_fall_back_to_the_config_icon(tmp_path):
    renderer = _blockplan(tmp_path, [
        {"icon": "", "displayname": "Holiday", "nonworkday": 1, "country": "US"},
    ])

    assert [c["icon_name"] for c in renderer.nwd_icons()] == ["star"]


# ── Weekly top row ────────────────────────────────────────────────────────


def _weekly_icons(holidays: list[tuple[str, str]]) -> list[str]:
    config = setfontsizes(create_calendar_config())
    oneday = arrow.get("20260501", "YYYYMMDD")
    renderer = _Weekly()
    renderer._draw_day_top_row_extras(
        config, oneday, oneday.format("YYYYMMDD"), 0, 0, 400, 100,
        has_overflow=False, holidays=holidays, day_num_width=0.0,
    )
    return [c["icon_name"] for c in renderer.icon_calls]


def test_weekly_draws_every_countrys_flag():
    assert _weekly_icons(
        [("Holiday CA", "ca"), ("Holiday GB", "gb"), ("Holiday US", "us")]
    ) == ["ca", "gb", "us"]


def test_weekly_draws_a_countrys_flag_once():
    assert _weekly_icons(
        [("Buddha Purnima", "in"), ("Labour Day", "in"), ("May Day", "us")]
    ) == ["in", "us"]
