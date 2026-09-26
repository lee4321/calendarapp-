"""tools/convert_style_keys.py moves retired section style keys into token rules."""

from __future__ import annotations

import pytest
import yaml

from config.config import CalendarConfig
from config.theme_engine import ThemeEngine, ThemeError
from config.unified_theme import parse_theme
from tools.convert_style_keys import convert_text

_CELL_DEFINED = """\
weekly:
  day_box:
    stroke_color: red        # the token below defines stroke, so this never applied
    stroke_dasharray: 8 2    # ...but it defines no dasharray, so this did
style_rules:
  - name: define box:cell
    define: box
    as: cell
    style: {fill: white, stroke: navy}
  - name: cell on letter paper
    apply_to: box:cell
    select: {papersize: letter}
    style: {dasharray: 1 1}
"""


def test_only_attributes_the_definition_leaves_unset_become_rules():
    text, changes = convert_text(_CELL_DEFINED)
    data = yaml.safe_load(text)
    assert "weekly" not in data  # the emptied section goes too
    added = [r for r in data["style_rules"] if r.get("select") == {"visualizer": "weekly"}]
    # stroke came from the definition; the other three came from the key or
    # the old built-in defaults.
    assert [r["style"] for r in added] == [{"stroke_opacity": 0.25, "stroke_width": 2, "dasharray": "8 2"}]
    assert any("remove key: weekly.day_box.stroke_color" in c for c in changes)


def test_the_converted_rule_sits_before_the_tokens_other_conditional_rules():
    """A later conditional rule that matched before must still win."""
    data = yaml.safe_load(convert_text(_CELL_DEFINED)[0])
    theme = parse_theme(data)
    assert theme.resolve_token("box:cell", {"visualizer": "weekly"})["dasharray"] == "8 2"
    assert theme.resolve_token("box:cell", {"visualizer": "weekly", "papersize": "letter"})["dasharray"] == "1 1"


def test_an_old_default_that_was_in_effect_is_written_out():
    theme = "style_rules:\n  - name: define box:cell\n    define: box\n    as: cell\n    style: {stroke: grey}\n"
    data = yaml.safe_load(convert_text(theme)[0])
    added = [r for r in data["style_rules"] if r.get("select") == {"visualizer": "weekly"}]
    assert added[0]["style"] == {"stroke_opacity": 0.25, "stroke_width": 2}


def test_the_loader_rejects_a_retired_key_and_names_the_converter():
    engine = ThemeEngine()
    engine._theme_data = {"weekly": {"day_box": {"stroke_width": 1}}}
    with pytest.raises(ThemeError, match="convert_style_keys"):
        engine.apply(CalendarConfig())


_PIT_FONT = """\
timeline:
  name_text:
    font_name: Offside-Regular   # PIT read this ahead of any token
style_rules:
  - name: define text:event_name
    define: text
    as: event_name
    style: {font: Roboto-Regular}
"""


def test_a_key_read_ahead_of_the_token_is_written_even_when_the_token_sets_it():
    text, _changes = convert_text(_PIT_FONT)
    theme = parse_theme(yaml.safe_load(text))
    assert theme.resolve_token("text:event_name", {"visualizer": "pit"})["font"] == "Offside-Regular"
    # The timeline read the token first, so it keeps the definition's font.
    assert theme.resolve_token("text:event_name", {"visualizer": "timeline"})["font"] == "Roboto-Regular"


def test_converting_twice_changes_nothing():
    once, _ = convert_text(_PIT_FONT)
    twice, changes = convert_text(once)
    assert twice == once
    assert changes == []


# Rule items at column 0 (yaml.dump style), nested lists at column 2, and
# rules for two tokens that insert at different places in the list.
_MANY_TARGETS = """\
blockplan:
  timeband_line_width: 2.5   # falls back to the grid key when unset
  grid_color: silver
  duration_stroke_color: red
style_rules:
- name: event colors
  apply_to:
  - box:event
  - box:duration
  style: {fill: blue}
- name: grid on letter paper
  apply_to: line:grid
  select: {papersize: letter}
  style: {width: 3}
"""


def test_rules_land_before_their_own_token_s_rules():
    text, _changes = convert_text(_MANY_TARGETS)
    names = [r["name"] for r in yaml.safe_load(text)["style_rules"]]
    assert names.index("box:duration — blockplan (from blockplan)") < names.index("event colors")
    assert names.index("line:grid — blockplan (from blockplan)") < names.index("grid on letter paper")
    assert names.index("event colors") < names.index("line:grid — blockplan (from blockplan)")


def test_a_key_left_unset_takes_its_fallback_key_s_value():
    theme = parse_theme(yaml.safe_load(convert_text(_MANY_TARGETS)[0]))
    band = theme.resolve_token("box:band", {"visualizer": "blockplan"})
    assert band["stroke_width"] == 2.5  # its own key
    assert band["stroke"] == "silver"  # timeband_line_color unset: grid_color
    assert band["stroke_opacity"] == 0.6  # neither set: the grid's old default
