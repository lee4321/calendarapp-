"""Tests for the unified theme loader + resolver (design §4–§6)."""

from __future__ import annotations

import pytest

from pathlib import Path

from config.unified_theme import (
    ThemeError,
    UnifiedTheme,
    parse_theme,
)

THEMES_DIR = Path(__file__).resolve().parent.parent / "config" / "themes"


# ─── parsing real themes ────────────────────────────────────────────────────


def test_basic_yaml_parses() -> None:
    theme = parse_theme(THEMES_DIR / "basic.yaml")
    assert isinstance(theme, UnifiedTheme)
    # Every section in basic.yaml should round-trip into sections{}
    for sec in ("theme", "base", "layout", "events", "weekly", "blockplan", "style_rules"):
        assert sec in theme.sections, f"basic.yaml missing top-level {sec}"
    # Token registry should contain the canonical tokens basic.yaml defines.
    tokens = set(theme.defined_tokens())
    for must_have in (
        "text:heading", "text:body", "text:day_number", "text:milestone_label",
        "box:day", "box:event", "box:duration", "box:vline",
        "box:swimlane_heading", "box:swimlane_content", "box:milestone",
        "line:grid", "line:axis", "line:today",
        "icon:event", "icon:milestone", "icon:overflow",
    ):
        assert must_have in tokens, f"basic.yaml missing definition of {must_have}"


def test_sample_yaml_parses() -> None:
    theme = parse_theme(THEMES_DIR / "SAMPLE.yaml")
    # SAMPLE adds annotated content rules — verify a representative selection.
    fed = theme.find_rules("box:day", {"federal_holiday": True})
    assert any("fill" in r.style and r.style.get("fill") == "tomato" for r in fed), \
        "SAMPLE.yaml should have a federal-holiday tint rule"


# ─── retired-section rejection ──────────────────────────────────────────────


@pytest.mark.parametrize("section", [
    "text_styles",
    "box_styles",
    "line_styles",
    "icon_styles",
    "element_styles",
    "axis",
    "swimlane_rules",
])
def test_retired_sections_are_rejected(section: str) -> None:
    minimal = {"theme": {"name": "x", "version": "3.0"}, section: {}}
    with pytest.raises(ThemeError, match="tools/migrate_theme.py"):
        parse_theme(minimal)


def test_unknown_section_is_rejected() -> None:
    minimal = {"theme": {"name": "x", "version": "3.0"}, "totally_made_up": {}}
    with pytest.raises(ThemeError, match="unknown top-level section"):
        parse_theme(minimal)


# ─── rule shape validation ──────────────────────────────────────────────────


def test_define_requires_as() -> None:
    raw = {"style_rules": [{"name": "x", "define": "text"}]}
    with pytest.raises(ThemeError, match="`as:` token name"):
        parse_theme(raw)


def test_define_rejects_apply_to() -> None:
    raw = {"style_rules": [
        {"name": "x", "define": "text", "as": "h", "apply_to": "text:h", "style": {}},
    ]}
    with pytest.raises(ThemeError, match="`apply_to:` must be omitted"):
        parse_theme(raw)


def test_apply_to_required_when_not_defining() -> None:
    raw = {"style_rules": [{"name": "x", "style": {"fill": "red"}}]}
    with pytest.raises(ThemeError, match="`apply_to:` is required"):
        parse_theme(raw)


def test_unknown_apply_to_target() -> None:
    raw = {"style_rules": [
        {"name": "x", "apply_to": "day_box", "style": {}},  # legacy target
    ]}
    with pytest.raises(ThemeError, match="apply_to target 'day_box' is not recognized"):
        parse_theme(raw)


def test_list_valued_apply_to_accepted() -> None:
    raw = {"style_rules": [
        {"name": "x", "apply_to": ["box:event", "text:event_name"], "style": {"fill": "red"}},
    ]}
    theme = parse_theme(raw)
    rule = theme.rules[0]
    assert rule.apply_to == ("box:event", "text:event_name")


def test_unknown_selector_key_rejected() -> None:
    raw = {"style_rules": [
        {"name": "x", "apply_to": "box:day", "select": {"madeup_key": 1}, "style": {}},
    ]}
    with pytest.raises(ThemeError, match="unknown selector key 'madeup_key'"):
        parse_theme(raw)


# ─── token resolution ──────────────────────────────────────────────────────


def test_resolve_token_simple() -> None:
    raw = {"style_rules": [
        {"name": "def", "define": "text", "as": "heading",
         "style": {"font": "Roboto", "size": 10, "color": "black"}},
    ]}
    theme = parse_theme(raw)
    assert theme.resolve_token("text:heading") == {"font": "Roboto", "size": 10, "color": "black"}


def test_resolve_token_papersize_override() -> None:
    raw = {"style_rules": [
        {"name": "def", "define": "text", "as": "heading",
         "style": {"font": "Roboto", "size": 10}},
        {"name": "small", "apply_to": "text:heading",
         "select": {"papersize": ["3x5", "5x8"]},
         "style": {"size": 7}},
    ]}
    theme = parse_theme(raw)
    # No context: definition wins.
    assert theme.resolve_token("text:heading")["size"] == 10
    # papersize=letter doesn't match override.
    assert theme.resolve_token("text:heading", {"papersize": "letter"})["size"] == 10
    # papersize=3x5 matches override (later rule wins).
    assert theme.resolve_token("text:heading", {"papersize": "3x5"})["size"] == 7


def test_resolve_token_use_reference() -> None:
    """Element bindings (apply_to: element) use style.use to pull another token."""
    raw = {"style_rules": [
        {"name": "def", "define": "text", "as": "heading",
         "style": {"font": "Roboto", "size": 10, "color": "black"}},
        {"name": "bind ec-heading", "apply_to": "element",
         "select": {"element": "ec-heading"},
         "style": {"use": "text:heading"}},
    ]}
    theme = parse_theme(raw)
    binding_rules = theme.find_rules("element", {"element": "ec-heading"})
    assert len(binding_rules) == 1
    assert binding_rules[0].style == {"use": "text:heading"}


# ─── find_rules + multi-target ─────────────────────────────────────────────


def test_find_rules_filters_by_target_and_context() -> None:
    raw = {"style_rules": [
        {"name": "fed", "apply_to": "box:day",
         "select": {"federal_holiday": True},
         "style": {"fill": "tomato"}},
        {"name": "co", "apply_to": "box:day",
         "select": {"company_holiday": True},
         "style": {"fill": "gold"}},
        {"name": "ev", "apply_to": "box:event",
         "style": {"fill": "blue"}},
    ]}
    theme = parse_theme(raw)
    fed = theme.find_rules("box:day", {"federal_holiday": True})
    assert len(fed) == 1
    assert fed[0].name == "fed"
    co = theme.find_rules("box:day", {"company_holiday": True})
    assert len(co) == 1
    assert co[0].name == "co"
    ev = theme.find_rules("box:event", {})
    assert len(ev) == 1


def test_find_rules_multi_target_fans_out() -> None:
    raw = {"style_rules": [
        {"name": "muted", "apply_to": ["box:event", "text:event_name"],
         "select": {"percent_complete": {"min": 100}},
         "style": {"fill": "#f4f4f4", "color": "grey"}},
    ]}
    theme = parse_theme(raw)
    box_hits = theme.find_rules("box:event", {"percent_complete": 100})
    text_hits = theme.find_rules("text:event_name", {"percent_complete": 100})
    assert len(box_hits) == 1
    assert len(text_hits) == 1
    # Same Rule object reachable from both targets (fan-out semantics).
    assert box_hits[0] is text_hits[0]


# ─── lane routing ──────────────────────────────────────────────────────────


def test_route_lane_first_match_wins() -> None:
    raw = {"style_rules": [
        {"name": "eng", "apply_to": "lane",
         "select": {"resource_group": ["engineering", "dev"]},
         "style": {"swimlane": "Engineering"}},
        {"name": "catch-all", "apply_to": "lane",
         "select": {},
         "style": {"swimlane": "Other"}},
    ]}
    theme = parse_theme(raw)
    assert theme.route_lane({"resource_group": "engineering"}) == "Engineering"
    # No match on the first rule -> falls through to catch-all.
    assert theme.route_lane({"resource_group": "sales"}) == "Other"


# ─── value matchers ────────────────────────────────────────────────────────


def test_list_selector_substring_match_on_strings() -> None:
    raw = {"style_rules": [
        {"name": "sprint", "apply_to": "box:duration",
         "select": {"task_name": ["Sprint", "Cutover"]},
         "style": {"fill": "steelblue"}},
    ]}
    theme = parse_theme(raw)
    # Substring (case-insensitive) match on strings.
    assert theme.find_rules("box:duration", {"task_name": "Sprint Planning"})
    assert theme.find_rules("box:duration", {"task_name": "release / cutover"})
    assert not theme.find_rules("box:duration", {"task_name": "Other"})


def test_range_selector() -> None:
    raw = {"style_rules": [
        {"name": "complete", "apply_to": "box:event",
         "select": {"percent_complete": {"min": 100}},
         "style": {"fill": "grey"}},
    ]}
    theme = parse_theme(raw)
    assert theme.find_rules("box:event", {"percent_complete": 100})
    assert theme.find_rules("box:event", {"percent_complete": 101})
    assert not theme.find_rules("box:event", {"percent_complete": 50})


def test_priority_min_max() -> None:
    raw = {"style_rules": [
        {"name": "high", "apply_to": "box:event",
         "select": {"priority_min": 1, "priority_max": 2},
         "style": {"fill": "red"}},
    ]}
    theme = parse_theme(raw)
    assert theme.find_rules("box:event", {"priority_min": 1, "priority_max": 2})
    # Single 'priority' context value should be accepted too — but our
    # selector keys here are priority_min/max, so context must use those keys.
