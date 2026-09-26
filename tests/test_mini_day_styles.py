import pytest
from fakes import FakeCalendarDB, apply_style_rules, define

from config.config import create_calendar_config, setfontsizes
from visualizers.mini.day_styles import DayStyle, DayStyleResolver
from visualizers.mini.renderer import MiniCalendarRenderer


class _StubDB(FakeCalendarDB):
    def __init__(self, holidays=None, special_days=None):
        self._holidays = holidays or []
        self._special_days = special_days or []

    def get_holidays_for_date(self, daykey, country=None):
        return list(self._holidays)

    def get_special_days_for_date(self, daykey):
        return list(self._special_days)

    def get_all_patterns(self):
        return {"brick-wall": '<svg viewBox="0 0 10 10"><rect width="10" height="10" fill="black"/></svg>'}


def _config():
    config = create_calendar_config()
    config.pageX, config.pageY = 792.0, 1224.0
    # The resolver shades whichever daykey equals date.today() last, over every
    # other layer; off here so the hardcoded daykeys below never collide with
    # the real date the suite runs on.
    config.shade_current_day = False
    return setfontsizes(config)


def test_mini_circle_milestones_can_be_disabled():
    config = _config()
    config.mini_circle_milestones = False
    style = DayStyleResolver(config, _StubDB()).resolve(
        "20260115",
        [{"Start": "20260115", "End": "20260115", "Milestone": True}],
    )

    assert style.circled is False


def test_mini_style_rules_apply_pattern_decoration():
    config = _config()
    config.theme_style_rules = [
        {
            "name": "milestone-pattern",
            "select": {"milestone": True, "notes": ["launch"]},
            "apply_to": "day_box",
            "style": {
                "pattern": "brick-wall",
                "pattern_color": "gold",
                "pattern_opacity": 0.25,
            },
        }
    ]
    style = DayStyleResolver(config, _StubDB()).resolve(
        "20260115",
        [
            {
                "Start": "20260115",
                "End": "20260115",
                "Task": "Release",
                "Milestone": True,
                "Notes": "Launch prep",
                "Resource_Group": "ENG",
            }
        ],
    )

    assert len(style.hash_decorations) == 1
    assert style.hash_decorations[0].pattern == "brick-wall"
    assert style.hash_decorations[0].color == "gold"
    assert style.hash_decorations[0].opacity == 0.25


def test_mini_circle_stroke_style_is_configurable():
    config = _config()
    config.mini_circle_milestones = True
    config.mini_milestone_stroke_width = 2.5
    config.mini_milestone_stroke_opacity = 0.35

    class _CaptureRenderer(MiniCalendarRenderer):
        def __init__(self):
            super().__init__()
            self.circle_calls = []

        def _draw_circle(self, *args, **kwargs):
            self.circle_calls.append(kwargs)

        def _draw_rect(self, *args, **kwargs):
            return None

        def _draw_text(self, *args, **kwargs):
            return None

        def _draw_icon_svg(self, *args, **kwargs):
            return None

        def _resolve_icon_svg(self, icon_name):
            return None

    renderer = _CaptureRenderer()
    style = DayStyleResolver(config, _StubDB()).resolve(
        "20260115",
        [{"Start": "20260115", "End": "20260115", "Milestone": True}],
    )
    renderer._draw_day_cell(config, 0, 0, 20, 20, 15, style)

    assert renderer.circle_calls
    assert renderer.circle_calls[0]["stroke_width"] == 2.5
    assert renderer.circle_calls[0]["stroke_opacity"] == 0.35


# ── Corner icons ──────────────────────────────────────────────────────────
#
# An event's icon used to be drawn in place of the day number, so a day
# carrying one said nothing about which day it was — and a second event, or a
# holiday landing on the same day, silently overwrote the first one's mark.
# Icons now ring the number in the cell's corners: top-right first, then
# clockwise, four at most, drawn semi-transparent over the number.


class _IconCapture(MiniCalendarRenderer):
    """Captures icon and text draws without touching a real drawing."""

    def __init__(self):
        super().__init__()
        self.icon_calls = []
        self.text_calls = []

    def _draw_rect(self, *args, **kwargs):
        return None

    def _draw_line(self, *args, **kwargs):
        return None

    def _draw_circle(self, *args, **kwargs):
        return None

    def _draw_text(self, x, y, text, font_name, font_size, **kwargs):
        self.text_calls.append(text)

    def _draw_icon_svg(self, icon_name, x, baseline_y, size, **kwargs):
        self.icon_calls.append({"icon_name": icon_name, "x": x, "baseline_y": baseline_y, "size": size, **kwargs})
        return True

    def _resolve_icon_svg(self, icon_name):
        return "<svg viewBox='0 0 24 24'></svg>" if icon_name else None


def _corner_cy(call, size):
    """Recover a corner's centre y from the baseline _draw_icon_svg took."""
    return call["baseline_y"] - size * 0.30


def _drawn(config, style, x=0.0, y=0.0, w=20.0, h=20.0, day=15):
    renderer = _IconCapture()
    renderer._draw_day_cell(config, x, y, w, h, day, style)
    return renderer


def test_the_day_number_survives_an_event_icon():
    """The whole point: a cell never trades its day number for an icon."""
    config = _config()
    style = DayStyleResolver(config, _StubDB()).resolve(
        "20260115",
        [{"Start": "20260115", "End": "20260115", "Icon": "star"}],
    )
    renderer = _drawn(config, style)

    assert [c["icon_name"] for c in renderer.icon_calls] == ["star"]
    assert renderer.text_calls == ["15"]


def test_icons_fill_the_corners_clockwise_from_the_top_right():
    config = _config()
    style = DayStyle()
    for name in ("a", "b", "c", "d"):
        style.add_icon(name)
    renderer = _drawn(config, style, x=0.0, y=0.0, w=20.0, h=20.0)

    size = 20.0 * config.mini_event_icon_scale
    pad = config.mini_grid_line_width
    lo = pad + size / 2.0
    hi = 20.0 - pad - size / 2.0
    placed = [(round(c["x"], 4), round(_corner_cy(c, size), 4)) for c in renderer.icon_calls]
    assert placed == [
        (round(hi, 4), round(lo, 4)),  # top-right
        (round(hi, 4), round(hi, 4)),  # bottom-right
        (round(lo, 4), round(hi, 4)),  # bottom-left
        (round(lo, 4), round(lo, 4)),  # top-left
    ]


def test_only_four_icons_fit_and_the_lowest_ranked_are_dropped():
    from visualizers.mini.day_styles import (
        ICON_RANK_EVENT,
        ICON_RANK_HOLIDAY,
        ICON_RANK_MILESTONE,
    )

    config = _config()
    style = DayStyle()
    style.add_icon("event1", ICON_RANK_EVENT)
    style.add_icon("event2", ICON_RANK_EVENT)
    style.add_icon("event3", ICON_RANK_EVENT)
    style.add_icon("milestone", ICON_RANK_MILESTONE)
    style.add_icon("holiday", ICON_RANK_HOLIDAY)

    names = [c["icon_name"] for c in _drawn(config, style).icon_calls]
    assert len(names) == 4
    # There are only four corners, so the fifth mark goes — the least
    # important one, not whichever happened to be added last.
    assert names[0] == "holiday"
    assert names[1] == "milestone"
    assert "event3" not in names


def test_a_holiday_and_an_event_on_one_day_both_get_a_corner():
    """Neither used to survive the other: both wrote the same field."""
    config = _config()
    db = _StubDB(holidays=[{"displayname": "Holiday", "icon": "flag-us"}])
    style = DayStyleResolver(config, db).resolve(
        "20260115",
        [{"Start": "20260115", "End": "20260115", "Icon": "star"}],
    )

    names = [c["icon_name"] for c in _drawn(config, style).icon_calls]
    assert names == ["flag-us", "star"]  # holiday outranks the event


def test_holidays_from_several_countries_each_get_a_corner():
    """Only the first holiday's country icon used to be drawn."""
    config = _config()
    db = _StubDB(
        holidays=[
            {"displayname": "Labour Day", "icon": "ca", "country": "CA"},
            {"displayname": "Labor Day", "icon": "us", "country": "US"},
            {"displayname": "Labour Day", "icon": "gb", "country": "GB"},
        ]
    )
    style = DayStyleResolver(config, db).resolve(
        "20260907",
        [{"Start": "20260907", "End": "20260907", "Icon": "star"}],
    )

    names = [c["icon_name"] for c in _drawn(config, style).icon_calls]
    assert names == ["ca", "us", "gb", "star"]  # holidays outrank the event


def test_two_holidays_from_one_country_take_one_corner():
    config = _config()
    db = _StubDB(
        holidays=[
            {"displayname": "Christmas Eve", "icon": "us", "country": "US"},
            {"displayname": "Other", "icon": "us", "country": "US"},
        ]
    )
    style = DayStyleResolver(config, db).resolve("20261224", [])

    assert [c["icon_name"] for c in _drawn(config, style).icon_calls] == ["us"]


def test_any_nonworking_holiday_shades_the_day():
    """A nonworking holiday listed after an informational one still shades."""
    config = _config()
    db = _StubDB(
        holidays=[
            {"displayname": "Observance", "icon": "ca", "nonworkday": 0},
            {"displayname": "Holiday", "icon": "us", "nonworkday": 1},
        ]
    )
    style = DayStyleResolver(config, db).resolve("20260115", [])

    assert style.shade_color == (config.theme_mini_nonworkday_fill_color or config.mini_nonworkday_fill_color)


def test_the_same_icon_from_two_sources_takes_one_corner():
    config = _config()
    db = _StubDB(special_days=[{"name": "Company Day", "icon": "star"}])
    style = DayStyleResolver(config, db).resolve(
        "20260115",
        [{"Start": "20260115", "End": "20260115", "Icon": "star"}],
    )

    assert [c["icon_name"] for c in _drawn(config, style).icon_calls] == ["star"]


def test_two_events_on_one_day_each_keep_their_icon():
    config = _config()
    style = DayStyleResolver(config, _StubDB()).resolve(
        "20260115",
        [
            {"Start": "20260115", "End": "20260115", "Icon": "star"},
            {"Start": "20260115", "End": "20260115", "Icon": "rocket"},
        ],
    )

    names = [c["icon_name"] for c in _drawn(config, style).icon_calls]
    assert names == ["star", "rocket"]


def test_the_icon_size_and_opacity_come_from_the_theme():
    config = _config()
    config.mini_event_icon_scale = 0.4
    config.mini_event_icon_opacity = 0.25
    style = DayStyle()
    style.add_icon("star")

    call = _drawn(config, style, w=30.0, h=20.0).icon_calls[0]
    # A fraction of the cell's shorter side, so an oblong cell stays square.
    assert call["size"] == pytest.approx(20.0 * 0.4)
    assert call["opacity"] == pytest.approx(0.25)


def test_a_day_with_no_icons_draws_none():
    config = _config()
    renderer = _drawn(config, DayStyle())
    assert renderer.icon_calls == []
    assert renderer.text_calls == ["15"]


def test_mini_grid_lines_are_inset_to_avoid_bottom_clip():
    config = _config()
    config.mini_grid_lines = True
    apply_style_rules(config, [define("line", "grid", color="orange", width=0.5, opacity=0.3)])

    class _CaptureRenderer(MiniCalendarRenderer):
        def __init__(self):
            super().__init__()
            self.rect_calls = []

        def _draw_rect(self, x, y, w, h, **kwargs):
            self.rect_calls.append({"x": x, "y": y, "w": w, "h": h, **kwargs})

        def _draw_text(self, *args, **kwargs):
            return None

        def _draw_icon_svg(self, *args, **kwargs):
            return None

        def _resolve_icon_svg(self, icon_name):
            return None

    renderer = _CaptureRenderer()
    renderer._draw_day_cell(config, 0, 0, 20, 20, 15, DayStyle())

    grid_rects = [r for r in renderer.rect_calls if r.get("stroke") == "orange"]
    assert len(grid_rects) == 1
    grid = grid_rects[0]
    assert grid["x"] == 0.25
    assert grid["y"] == 0.25
    assert grid["w"] == 19.5
    assert grid["h"] == 19.5
    assert grid["stroke_width"] == 0.5
    assert grid["stroke_opacity"] == 0.3


def test_mini_day_number_digits_are_substituted():
    config = _config()
    config.mini_day_number_digits = ["a", "b", "c", "d", "e", "f", "g", "h", "i", "j"]

    class _CaptureRenderer(MiniCalendarRenderer):
        def __init__(self):
            super().__init__()
            self.text_calls = []

        def _draw_rect(self, *args, **kwargs):
            return None

        def _draw_text(self, x, y, text, font_name, font_size, **kwargs):
            self.text_calls.append(text)

        def _draw_icon_svg(self, *args, **kwargs):
            return None

        def _resolve_icon_svg(self, icon_name):
            return None

    renderer = _CaptureRenderer()
    renderer._draw_day_cell(config, 0, 0, 20, 20, 12, DayStyle())

    assert renderer.text_calls == ["bc"]


def test_mini_day_number_digits_invalid_length_falls_back_to_ascii():
    config = _config()
    config.mini_day_number_digits = ["①", "②", "③"]

    class _CaptureRenderer(MiniCalendarRenderer):
        def __init__(self):
            super().__init__()
            self.text_calls = []

        def _draw_rect(self, *args, **kwargs):
            return None

        def _draw_text(self, x, y, text, font_name, font_size, **kwargs):
            self.text_calls.append(text)

        def _draw_icon_svg(self, *args, **kwargs):
            return None

        def _resolve_icon_svg(self, icon_name):
            return None

    renderer = _CaptureRenderer()
    renderer._draw_day_cell(config, 0, 0, 20, 20, 12, DayStyle())

    assert renderer.text_calls == ["12"]


def test_mini_day_number_glyphs_are_supported():
    config = _config()
    config.mini_day_number_glyphs = [f"G{i}" for i in range(1, 32)]

    class _CaptureRenderer(MiniCalendarRenderer):
        def __init__(self):
            super().__init__()
            self.text_calls = []

        def _draw_rect(self, *args, **kwargs):
            return None

        def _draw_text(self, x, y, text, font_name, font_size, **kwargs):
            self.text_calls.append(text)

        def _draw_icon_svg(self, *args, **kwargs):
            return None

        def _resolve_icon_svg(self, icon_name):
            return None

    renderer = _CaptureRenderer()
    renderer._draw_day_cell(config, 0, 0, 20, 20, 12, DayStyle())

    assert renderer.text_calls == ["G12"]


def test_mini_day_number_glyphs_take_precedence_over_digits():
    config = _config()
    config.mini_day_number_glyphs = [f"G{i}" for i in range(1, 32)]
    config.mini_day_number_digits = ["a", "b", "c", "d", "e", "f", "g", "h", "i", "j"]

    class _CaptureRenderer(MiniCalendarRenderer):
        def __init__(self):
            super().__init__()
            self.text_calls = []

        def _draw_rect(self, *args, **kwargs):
            return None

        def _draw_text(self, x, y, text, font_name, font_size, **kwargs):
            self.text_calls.append(text)

        def _draw_icon_svg(self, *args, **kwargs):
            return None

        def _resolve_icon_svg(self, icon_name):
            return None

    renderer = _CaptureRenderer()
    renderer._draw_day_cell(config, 0, 0, 20, 20, 12, DayStyle())

    assert renderer.text_calls == ["G12"]


def test_day_number_color_chain_is_shared_across_the_mini_family():
    """mini, mini-icon and candybar resolve the base day-number color the same
    way: the resolved ``text:day_number`` token, then the ``ec-day-number``
    element style (its ``element_overrides`` color, else its token's color)."""
    from visualizers.candybar.renderer import CandybarRenderer
    from visualizers.mini_icon.renderer import MiniIconRenderer

    renderers = (MiniCalendarRenderer(), MiniIconRenderer(), CandybarRenderer())

    # Bottom of the chain: the element style's own token color.
    config = _config()
    apply_style_rules(config, [define("text", "day_number", color="teal")])
    for r in renderers:
        assert r._resolve_day_number_color(config, {}) == "teal"

    # An ec-day-number element override beats it.
    class _Styles:
        def get_element_color(self, element_class):
            return "orchid" if element_class == "ec-day-number" else None

    config.theme_styles = _Styles()
    for r in renderers:
        assert r._resolve_day_number_color(config, {}) == "orchid"

    # The per-view text:day_number token beats everything below it.
    for r in renderers:
        assert r._resolve_day_number_color(config, {"color": "crimson"}) == "crimson"


def test_a_fill_list_on_a_day_rule_shades_with_its_first_color():
    config = _config()
    config.theme_style_rules = [{"apply_to": "day_box", "select": {}, "style": {"fill": ["red", "blue"]}}]
    # A fixed past weekday: on today's date the current-day highlight
    # replaces the rule's fill.
    style = DayStyleResolver(config, _StubDB()).resolve("20260115", [])
    assert style.shade_color == "red"


def _fiscal_config(weekend_style):
    """A mini config with an NRF 4-5-4 lookup over calendar year 2026."""
    from datetime import date

    from shared.fiscal_calendars import build_fiscal_lookup, create_fiscal_calendar

    config = _config()
    config.weekend_style = weekend_style
    config.fiscal_lookup = build_fiscal_lookup(create_fiscal_calendar("nrf-454"), date(2026, 1, 1), date(2026, 12, 31))
    return config


def test_fiscal_period_label_falls_forward_when_its_start_day_is_hidden():
    """NRF periods open on a Sunday, which a workweek-only mini never draws.

    Without the fall-forward the label was simply dropped, so `--fiscal` on a
    default mini produced output identical to no fiscal calendar at all.
    """
    resolver = DayStyleResolver(_fiscal_config(weekend_style=0), _StubDB())
    # 2026-01-04 is the Sunday that opens NRF period 1; 01-05 is the Monday.
    assert resolver.resolve("20260104", []).fiscal_period_label is None
    assert resolver.resolve("20260105", []).fiscal_period_label


def test_fiscal_period_label_stays_on_the_start_day_when_weekends_render():
    """Weekend-showing styles are untouched: the label keeps its real start day."""
    resolver = DayStyleResolver(_fiscal_config(weekend_style=1), _StubDB())
    assert resolver.resolve("20260104", []).fiscal_period_label
    assert resolver.resolve("20260105", []).fiscal_period_label is None


def test_every_fiscal_period_is_labelled_exactly_once_either_way():
    from shared.fiscal_renderer import period_label_days

    lookup = _fiscal_config(weekend_style=0).fiscal_lookup
    starts = sum(1 for info in lookup.values() if info.is_period_start)
    for weekend_style in (0, 1, 2, 3, 4):
        labelled = period_label_days(lookup, weekend_style)
        assert len(labelled) == starts, weekend_style
        # One label per (fiscal year, period), never two for the same period.
        idents = {(i.fiscal_year, i.fiscal_period) for i in labelled.values()}
        assert len(idents) == starts, weekend_style
