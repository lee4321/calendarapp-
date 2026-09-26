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
