from config.config import create_calendar_config
from visualizers.weekly.renderer import (
    DayHashContext,
    HashDecoration,
    WeeklyCalendarRenderer,
)


def _renderer() -> WeeklyCalendarRenderer:
    return WeeklyCalendarRenderer()


# ---------------------------------------------------------------------------
# Single-rule behaviour (backward-compatible)
# ---------------------------------------------------------------------------


def test_single_rule_matches_any_condition_by_default():
    """A rule with min_match omitted fires when any listed condition is true."""
    config = create_calendar_config()
    config.theme_weekly_hash_rules = [
        {
            "pattern": "polka-dots",
            "color": "orange",
            "when": {
                "milestone": True,
                "nonworkday": True,
            },
        }
    ]
    ctx = DayHashContext(milestone=False, nonworkday=True)
    decs = _renderer()._resolve_day_hash_decorations(config, ctx)

    assert len(decs) == 1
    assert decs[0].pattern == "polka-dots"
    assert decs[0].color == "orange"


def test_single_rule_requires_min_match():
    """A rule with min_match: 2 only fires when both conditions are met."""
    config = create_calendar_config()
    config.theme_weekly_hash_rules = [
        {
            "pattern": "brick-wall",
            "min_match": 2,
            "when": {
                "milestone": True,
                "nonworkday": True,
            },
        }
    ]
    renderer = _renderer()

    # Only one condition met — no decoration
    decs_1 = renderer._resolve_day_hash_decorations(
        config,
        DayHashContext(milestone=True, nonworkday=False),
    )
    assert decs_1 == []

    # Both conditions met — decoration returned
    decs_2 = renderer._resolve_day_hash_decorations(
        config,
        DayHashContext(milestone=True, nonworkday=True),
    )
    assert len(decs_2) == 1
    assert decs_2[0].pattern == "brick-wall"


def test_name_matching_for_events_and_durations():
    """event_names and duration_names use case-insensitive substring matching."""
    config = create_calendar_config()
    config.theme_weekly_hash_rules = [
        {"pattern": "diagonal-stripes", "when": {"event_names": ["release"]}},
        {"pattern": "bamboo", "when": {"duration_names": ["sprint"]}},
    ]
    renderer = _renderer()

    event_decs = renderer._resolve_day_hash_decorations(
        config,
        DayHashContext(event_names=("Release Planning",)),
    )
    duration_decs = renderer._resolve_day_hash_decorations(
        config,
        DayHashContext(duration_names=("Sprint Alpha",)),
    )

    assert len(event_decs) == 1
    assert event_decs[0].pattern == "diagonal-stripes"
    assert len(duration_decs) == 1
    assert duration_decs[0].pattern == "bamboo"


# ---------------------------------------------------------------------------
# Multi-rule behaviour (new capability)
# ---------------------------------------------------------------------------


def test_multiple_independent_rules_all_apply():
    """Every rule that matches contributes a separate decoration layer."""
    config = create_calendar_config()
    config.theme_weekly_hash_rules = [
        {"pattern": "diagonal-stripes", "color": "gold", "when": {"milestone": True}},
        {"pattern": "grid", "color": "silver", "when": {"nonworkday": True}},
        {
            "pattern": "polka-dots",
            "color": "crimson",
            "when": {"federal_holiday": True},
        },
    ]

    # Day that is both a milestone and a nonworkday (but not a holiday)
    ctx = DayHashContext(milestone=True, nonworkday=True, federal_holiday=False)
    decs = _renderer()._resolve_day_hash_decorations(config, ctx)

    assert len(decs) == 2
    assert decs[0].pattern == "diagonal-stripes"
    assert decs[0].color == "gold"
    assert decs[1].pattern == "grid"
    assert decs[1].color == "silver"


def test_all_three_rules_fire_when_all_conditions_met():
    """All three rules fire when all conditions are satisfied."""
    config = create_calendar_config()
    config.theme_weekly_hash_rules = [
        {"pattern": "diagonal-stripes", "when": {"milestone": True}},
        {"pattern": "grid", "when": {"nonworkday": True}},
        {"pattern": "polka-dots", "when": {"federal_holiday": True}},
    ]

    ctx = DayHashContext(milestone=True, nonworkday=True, federal_holiday=True)
    decs = _renderer()._resolve_day_hash_decorations(config, ctx)

    assert len(decs) == 3
    assert [d.pattern for d in decs] == ["diagonal-stripes", "grid", "polka-dots"]


def test_no_rule_fires_returns_empty_list():
    """Returns an empty list when no rule conditions are met."""
    config = create_calendar_config()
    config.theme_weekly_hash_rules = [
        {"pattern": "diagonal-stripes", "when": {"milestone": True}},
    ]
    ctx = DayHashContext(milestone=False)
    decs = _renderer()._resolve_day_hash_decorations(config, ctx)

    assert decs == []


def test_fallback_to_theme_weekly_hash_pattern():
    """When no rule matches, theme_weekly_hash_pattern is used as a fallback."""
    config = create_calendar_config()
    config.theme_weekly_hash_rules = [
        {"pattern": "diagonal-stripes", "when": {"milestone": True}},
    ]
    config.theme_weekly_hash_pattern = "bamboo"

    ctx = DayHashContext(milestone=False)
    decs = _renderer()._resolve_day_hash_decorations(config, ctx)

    assert len(decs) == 1
    assert decs[0].pattern == "bamboo"
    assert decs[0].color is None
    assert decs[0].opacity is None


# ---------------------------------------------------------------------------
# Per-rule opacity
# ---------------------------------------------------------------------------


def test_per_rule_opacity_is_captured():
    """opacity key in a rule populates HashDecoration.opacity."""
    config = create_calendar_config()
    config.theme_weekly_hash_rules = [
        {
            "pattern": "diagonal-stripes",
            "color": "gold",
            "opacity": 0.30,
            "when": {"milestone": True},
        },
        {"pattern": "grid", "when": {"nonworkday": True}},
    ]

    ctx = DayHashContext(milestone=True, nonworkday=True)
    decs = _renderer()._resolve_day_hash_decorations(config, ctx)

    assert len(decs) == 2
    assert decs[0].opacity == 0.30  # explicit override
    assert (
        decs[1].opacity is None
    )  # falls back to config.hash_pattern_opacity at draw time


def test_invalid_opacity_is_ignored():
    """A non-numeric opacity value is silently ignored (opacity stays None)."""
    config = create_calendar_config()
    config.theme_weekly_hash_rules = [
        {
            "pattern": "diagonal-stripes",
            "opacity": "not-a-number",
            "when": {"milestone": True},
        },
    ]

    ctx = DayHashContext(milestone=True)
    decs = _renderer()._resolve_day_hash_decorations(config, ctx)

    assert len(decs) == 1
    assert decs[0].opacity is None


# ---------------------------------------------------------------------------
# Rule ordering
# ---------------------------------------------------------------------------


def test_decoration_order_follows_rule_declaration_order():
    """Decorations are returned in the same order as their rules."""
    config = create_calendar_config()
    config.theme_weekly_hash_rules = [
        {"pattern": "zigzag", "when": {"nonworkday": True}},
        {"pattern": "circuit-board", "when": {"milestone": True}},
        {"pattern": "bamboo", "when": {"federal_holiday": True}},
    ]

    ctx = DayHashContext(nonworkday=True, milestone=True, federal_holiday=True)
    decs = _renderer()._resolve_day_hash_decorations(config, ctx)

    assert [d.pattern for d in decs] == ["zigzag", "circuit-board", "bamboo"]
