"""
Tests for StyleEngine.evaluate_day() — the unified style_rules engine that
replaced the old per-renderer hash_rules / DayHashContext system.
"""

from shared.data_models import Event
from shared.rule_engine import DayContext, StyleEngine


def _event(**kwargs) -> Event:
    defaults = dict(
        task_name="",
        start="20260115",
        end="20260115",
        milestone=False,
        notes=None,
        resource_group=None,
        resource_names=None,
        percent_complete=0.0,
        priority=0,
        wbs=None,
    )
    defaults.update(kwargs)
    return Event(**defaults)


def _ctx(**kwargs) -> DayContext:
    defaults = dict(
        date="20260115",
        federal_holiday=False,
        company_holiday=False,
        nonworkday=False,
        workday=True,
        weekend=False,
    )
    defaults.update(kwargs)
    return DayContext(**defaults)


def _engine(rules: list) -> StyleEngine:
    return StyleEngine(rules)


# ---------------------------------------------------------------------------
# Day-level criteria
# ---------------------------------------------------------------------------


def test_nonworkday_rule_matches():
    engine = _engine([{
        "name": "nwd",
        "select": {"nonworkday": True},
        "apply_to": "day_box",
        "style": {"pattern": "polka-dots", "pattern_color": "orange"},
    }])
    result = engine.evaluate_day(_ctx(nonworkday=True))
    assert result.pattern == "polka-dots"
    assert result.pattern_color == "orange"


def test_nonworkday_rule_does_not_match_workday():
    engine = _engine([{
        "name": "nwd",
        "select": {"nonworkday": True},
        "apply_to": "day_box",
        "style": {"pattern": "polka-dots"},
    }])
    result = engine.evaluate_day(_ctx(nonworkday=False))
    assert result.pattern is None


def test_federal_holiday_rule():
    engine = _engine([{
        "name": "fed",
        "select": {"federal_holiday": True},
        "apply_to": "day_box",
        "style": {"fill_color": "lightyellow"},
    }])
    result = engine.evaluate_day(_ctx(federal_holiday=True))
    assert result.fill_color == "lightyellow"


def test_company_holiday_rule():
    engine = _engine([{
        "name": "co",
        "select": {"company_holiday": True},
        "apply_to": "day_box",
        "style": {"pattern": "diagonal-stripes"},
    }])
    result = engine.evaluate_day(_ctx(company_holiday=True))
    assert result.pattern == "diagonal-stripes"


def test_weekend_rule():
    engine = _engine([{
        "name": "wknd",
        "select": {"weekend": True},
        "apply_to": "day_box",
        "style": {"pattern": "grid"},
    }])
    result_wknd = engine.evaluate_day(_ctx(weekend=True, nonworkday=True, workday=False))
    result_wkday = engine.evaluate_day(_ctx(weekend=False))
    assert result_wknd.pattern == "grid"
    assert result_wkday.pattern is None


# ---------------------------------------------------------------------------
# Event-level criteria (day_box rules with event conditions)
# ---------------------------------------------------------------------------


def test_milestone_event_triggers_rule():
    engine = _engine([{
        "name": "ms",
        "select": {"milestone": True},
        "apply_to": "day_box",
        "style": {"pattern": "zigzag"},
    }])
    events = [_event(milestone=True)]
    result = engine.evaluate_day(_ctx(), events)
    assert result.pattern == "zigzag"


def test_no_matching_events_skips_rule():
    engine = _engine([{
        "name": "ms",
        "select": {"milestone": True},
        "apply_to": "day_box",
        "style": {"pattern": "zigzag"},
    }])
    result = engine.evaluate_day(_ctx(), [_event(milestone=False)])
    assert result.pattern is None


def test_task_name_substring_match():
    engine = _engine([{
        "name": "release",
        "select": {"task_name": ["release"]},
        "apply_to": "day_box",
        "style": {"pattern": "diagonal-stripes"},
    }])
    result = engine.evaluate_day(_ctx(), [_event(task_name="Release Planning")])
    assert result.pattern == "diagonal-stripes"


def test_task_name_no_match():
    engine = _engine([{
        "name": "release",
        "select": {"task_name": ["release"]},
        "apply_to": "day_box",
        "style": {"pattern": "diagonal-stripes"},
    }])
    result = engine.evaluate_day(_ctx(), [_event(task_name="Sprint Review")])
    assert result.pattern is None


def test_duration_event_type_filter():
    engine = _engine([{
        "name": "dur",
        "select": {"event_type": "duration"},
        "apply_to": "day_box",
        "style": {"pattern": "bamboo"},
    }])
    single_day = _event(task_name="Meeting", start="20260115", end="20260115")
    multi_day = _event(task_name="Sprint", start="20260115", end="20260120")
    assert engine.evaluate_day(_ctx(), [single_day]).pattern is None
    assert engine.evaluate_day(_ctx(), [multi_day]).pattern == "bamboo"


def test_resource_group_exact_match():
    engine = _engine([{
        "name": "eng",
        "select": {"resource_group": ["eng"]},
        "apply_to": "day_box",
        "style": {"pattern": "circuit-board"},
    }])
    result = engine.evaluate_day(_ctx(), [_event(resource_group="ENG")])
    assert result.pattern == "circuit-board"


def test_notes_substring_match():
    engine = _engine([{
        "name": "launch",
        "select": {"notes": ["launch"]},
        "apply_to": "day_box",
        "style": {"pattern": "temple"},
    }])
    result = engine.evaluate_day(_ctx(), [_event(notes="Pre-launch review")])
    assert result.pattern == "temple"


# ---------------------------------------------------------------------------
# min_match (event criteria only)
# ---------------------------------------------------------------------------


def test_min_match_requires_enough_events():
    engine = _engine([{
        "name": "two-ms",
        "select": {"milestone": True},
        "apply_to": "day_box",
        "min_match": 2,
        "style": {"pattern": "polka-dots"},
    }])
    one_ms = [_event(milestone=True)]
    two_ms = [_event(milestone=True), _event(milestone=True, task_name="B")]
    assert engine.evaluate_day(_ctx(), one_ms).pattern is None
    assert engine.evaluate_day(_ctx(), two_ms).pattern == "polka-dots"


# ---------------------------------------------------------------------------
# Additive layering — later rules overwrite pattern, fill merges
# ---------------------------------------------------------------------------


def test_later_rule_overwrites_pattern():
    """When two rules match, later pattern wins (last-write semantics)."""
    engine = _engine([
        {
            "name": "r1",
            "select": {"nonworkday": True},
            "apply_to": "day_box",
            "style": {"pattern": "diagonal-stripes"},
        },
        {
            "name": "r2",
            "select": {"federal_holiday": True},
            "apply_to": "day_box",
            "style": {"pattern": "polka-dots"},
        },
    ])
    ctx = _ctx(nonworkday=True, federal_holiday=True)
    result = engine.evaluate_day(ctx)
    assert result.pattern == "polka-dots"


def test_fill_color_set_by_rule():
    engine = _engine([{
        "name": "fill",
        "select": {"nonworkday": True},
        "apply_to": "day_box",
        "style": {"fill_color": "#ffeecc"},
    }])
    result = engine.evaluate_day(_ctx(nonworkday=True))
    assert result.fill_color == "#ffeecc"


def test_pattern_opacity_propagated():
    engine = _engine([{
        "name": "op",
        "select": {"nonworkday": True},
        "apply_to": "day_box",
        "style": {"pattern": "grid", "pattern_opacity": 0.30},
    }])
    result = engine.evaluate_day(_ctx(nonworkday=True))
    assert result.pattern == "grid"
    assert result.pattern_opacity == 0.30


def test_no_matching_rule_returns_empty_result():
    engine = _engine([{
        "name": "ms",
        "select": {"milestone": True},
        "apply_to": "day_box",
        "style": {"pattern": "zigzag"},
    }])
    result = engine.evaluate_day(_ctx())
    assert result.is_empty()


def test_empty_rules_list_returns_empty_result():
    result = StyleEngine([]).evaluate_day(_ctx())
    assert result.is_empty()


# ---------------------------------------------------------------------------
# Mixed day + event criteria
# ---------------------------------------------------------------------------


def test_day_and_event_criteria_both_required():
    """A rule with both day and event criteria requires both to match."""
    engine = _engine([{
        "name": "holiday-ms",
        "select": {"federal_holiday": True, "milestone": True},
        "apply_to": "day_box",
        "style": {"pattern": "circuit-board"},
    }])
    # Holiday day but no milestone
    assert engine.evaluate_day(_ctx(federal_holiday=True), []).pattern is None
    # Milestone but not a holiday
    assert engine.evaluate_day(_ctx(), [_event(milestone=True)]).pattern is None
    # Both
    assert engine.evaluate_day(_ctx(federal_holiday=True), [_event(milestone=True)]).pattern == "circuit-board"
