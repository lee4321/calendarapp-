"""An event's color comes from style_rules in every visualizer.

A rule on ``box:event`` / ``box:duration`` whose ``style`` sets ``fill`` is
the one way a theme colors events -- by resource group, priority, WBS or
any other event criterion.  Views that draw an event as a bar or marker fill
it; views that draw it as text (weekly event names, mini day numbers) color
the text.  Bar-drawing views are covered in their own suites; these are the
views that once read ``colors.resource_groups`` or ignored the rule.
"""

from pathlib import Path

from fakes import FakeCalendarDB

from config.config import create_calendar_config, setfontsizes
from shared.data_models import Event
from shared.rule_engine import StyleEngine
from visualizers.mini.day_styles import DayStyleResolver


def _group_rule(group, color, name=None):
    return {
        "name": name or f"resource group {group}",
        "apply_to": ["box:event", "box:duration"],
        "select": {"resource_group": group},
        "style": {"fill": color},
    }


def _config(**fields):
    config = create_calendar_config()
    config.pageX, config.pageY = 792.0, 1224.0
    config.shade_current_day = False
    config = setfontsizes(config)
    for key, value in fields.items():
        setattr(config, key, value)
    return config


# ── rule engine ─────────────────────────────────────────────────────────────


def test_a_resource_group_matches_regardless_of_case():
    engine = StyleEngine([_group_rule("dev", "#aa0000")])

    event = Event(task_name="T", start="20260105", end="20260105", resource_group="Dev")
    assert engine.evaluate_event(event).fill_color == "#aa0000"


def test_the_winning_fill_carries_its_rule_name():
    engine = StyleEngine([_group_rule("dev", "#0000aa"), _group_rule("dev", "#aa0000", name="urgent dev")])

    event = Event(task_name="T", start="20260105", end="20260105", resource_group="dev")
    result = engine.evaluate_event(event)
    assert (result.fill_color, result.fill_source) == ("#aa0000", "urgent dev")


def test_event_fills_lists_event_rules_in_declaration_order():
    rules = [
        _group_rule("a", "#111111"),
        {"name": "day shade", "apply_to": "box:day", "style": {"fill": "#222222"}},
        _group_rule("b", "#333333"),
    ]

    assert StyleEngine(rules).event_fills() == [("resource group a", "#111111"), ("resource group b", "#333333")]


# ── weekly: event name and icon ─────────────────────────────────────────────


def _weekly_name_fill(config, event):
    from visualizers.weekly.renderer import WeeklyCalendarRenderer

    fills = []

    class _Capture(WeeklyCalendarRenderer):
        def _draw_text(self, x, y, text, font_name, font_size, **kwargs):
            fills.append(kwargs.get("fill"))

    _Capture()._place_event_text(config, event.task_name, 0.0, 0.0, 100.0, 10.0, 0.0, 0.0, event)
    return fills[0]


def test_weekly_colors_an_event_name_by_its_rule():
    config = _config(theme_style_rules=[_group_rule("dev", "#aa0000")])
    event = Event(task_name="Build", start="20260105", end="20260105", resource_group="Dev")

    assert _weekly_name_fill(config, event) == "#aa0000"


def test_weekly_keeps_the_theme_color_for_an_unmatched_event():
    config = _config(theme_style_rules=[_group_rule("ops", "#aa0000")])
    event = Event(task_name="Build", start="20260105", end="20260105", resource_group="Dev")

    assert _weekly_name_fill(config, event) != "#aa0000"


def test_weekly_an_event_name_text_rule_beats_the_fill():
    rules = [
        _group_rule("dev", "#aa0000"),
        {"name": "names", "apply_to": "event", "style": {"text": {"event_name": {"font_color": "#00aa00"}}}},
    ]
    config = _config(theme_style_rules=rules)
    event = Event(task_name="Build", start="20260105", end="20260105", resource_group="Dev")

    assert _weekly_name_fill(config, event) == "#00aa00"


# ── mini family: the day number ─────────────────────────────────────────────


class _NoHolidaysDB(FakeCalendarDB):
    def get_holidays_for_date(self, daykey, country=None):
        return []

    def get_special_days_for_date(self, daykey):
        return []


def _mini_day(config, group):
    event = {"Task_Name": "Build", "Start": "20260105", "End": "20260105", "Resource_Group": group}
    return DayStyleResolver(config, _NoHolidaysDB()).resolve("20260105", [event])


def test_mini_colors_a_day_number_by_its_events_rule():
    config = _config(theme_style_rules=[_group_rule("dev", "#aa0000")])

    assert _mini_day(config, "Dev").text_color == "#aa0000"


def test_mini_leaves_a_day_number_no_rule_matches():
    config = _config(theme_style_rules=[_group_rule("ops", "#aa0000")])

    assert _mini_day(config, "Dev").text_color is None


# ── pit: the axis marker ────────────────────────────────────────────────────


def _render_pit(tmp_path: Path, rules) -> str:
    from visualizers.pit.layout import PITLayout
    from visualizers.pit.renderer import PITRenderer

    config = _config(theme_style_rules=rules)
    config.pageX, config.pageY = 792.0, 612.0
    config = setfontsizes(config)
    config.adjustedstart = config.userstart = "20260101"
    config.adjustedend = config.userend = "20261231"
    config.outputfile = str(tmp_path / "pit.svg")
    config.include_header = False
    config.include_footer = False
    events = [{"Task_Name": "Launch", "Start": "20260601", "End": "20260601", "Resource_Group": "Dev"}]
    PITRenderer().render(config, PITLayout().calculate(config), events, FakeCalendarDB())
    return Path(config.outputfile).read_text(encoding="utf-8")


def test_pit_fills_an_events_marker_by_its_rule(tmp_path):
    assert "#aa0000" in _render_pit(tmp_path, [_group_rule("dev", "#aa0000")])
    assert "#aa0000" not in _render_pit(tmp_path, [_group_rule("ops", "#aa0000")])


# ── the unified theme agrees with the rule engine ───────────────────────────


def test_a_resource_group_selector_matches_the_whole_group_name():
    """find_rules matches task names and notes by substring, but a resource
    group of "d" must not pick up "Product"."""
    from config.unified_theme import parse_theme

    theme = parse_theme({"style_rules": [_group_rule("d", "grey")]})

    assert theme.find_rules("box:event", {"resource_group": "Product"}) == []
    assert len(theme.find_rules("box:event", {"resource_group": "D"})) == 1


def _halo_rects(rules, box_token):
    from config.unified_theme import parse_theme
    from visualizers.weekly.renderer import WeeklyCalendarRenderer

    rects = []

    class _Capture(WeeklyCalendarRenderer):
        def _draw_rect(self, x, y, w, h, **kwargs):
            rects.append(kwargs)

    renderer = _Capture()
    renderer._config = _config(theme=parse_theme({"style_rules": rules}))
    renderer._maybe_draw_icon_halo(box_token, {"resource_group": "dev"}, 0.0, 0.0, 10.0)
    return rects


def test_an_event_fill_colors_the_event_not_a_box_behind_its_icon():
    assert _halo_rects([_group_rule("dev", "#aa0000")], "box:event") == []
    assert _halo_rects([_group_rule("dev", "#aa0000")], "box:duration") == []


def test_an_event_rule_stroke_still_outlines_its_icon():
    rule = _group_rule("dev", "#aa0000") | {"style": {"fill": "#aa0000", "stroke": "crimson", "stroke_width": 1}}

    [halo] = _halo_rects([rule], "box:event")
    assert (halo["fill"], halo["stroke"]) == ("none", "crimson")
