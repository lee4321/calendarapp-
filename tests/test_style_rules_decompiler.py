"""Tests for the style_rules → legacy-sections decompiler (runtime bridge)."""

from __future__ import annotations

from pathlib import Path

import yaml

from config.style_rules_decompiler import decompile_style_rules

THEMES_DIR = Path(__file__).resolve().parent.parent / "config" / "themes"


def test_text_define_decompiles_to_text_styles() -> None:
    theme = {
        "style_rules": [
            {"name": "def", "define": "text", "as": "heading",
             "style": {"font": "Roboto", "size": 10, "color": "black"}},
        ],
    }
    decompile_style_rules(theme)
    assert theme["text_styles"]["heading"] == {
        "font": "Roboto", "size": 10, "color": "black",
    }


def test_box_define_reverses_property_renames() -> None:
    theme = {
        "style_rules": [
            {"define": "box", "as": "cell",
             "style": {
                 "fill": "white",
                 "stroke": "grey",
                 "stroke_width": 0.5,
                 "dasharray": "4 2",
             }},
        ],
    }
    decompile_style_rules(theme)
    cell = theme["box_styles"]["cell"]
    assert cell == {
        "fill_color": "white",
        "stroke_color": "grey",
        "stroke_width": 0.5,
        "stroke_dasharray": "4 2",
    }


def test_line_and_icon_defines() -> None:
    theme = {
        "style_rules": [
            {"define": "line", "as": "grid",
             "style": {"color": "lightgrey", "width": 0.5, "opacity": 1.0}},
            {"define": "icon", "as": "overflow",
             "style": {"icon": "overflow", "color": "red", "size": 10}},
        ],
    }
    decompile_style_rules(theme)
    assert theme["line_styles"]["grid"] == {
        "color": "lightgrey", "width": 0.5, "opacity": 1.0,
    }
    assert theme["icon_styles"]["overflow"] == {
        "icon": "overflow", "color": "red", "size": 10,
    }


def test_element_binding_decompiles() -> None:
    theme = {
        "style_rules": [
            {"apply_to": "element",
             "select": {"element": "ec-heading"},
             "style": {"use": "text:heading"}},
        ],
    }
    decompile_style_rules(theme)
    assert theme["element_styles"]["ec-heading"] == {"text_style": "heading"}


def test_element_binding_with_color_override() -> None:
    theme = {
        "style_rules": [
            {"apply_to": "element",
             "select": {"element": "ec-today-label"},
             "style": {"use": "text:label", "color": "red"}},
        ],
    }
    decompile_style_rules(theme)
    assert theme["element_styles"]["ec-today-label"] == {
        "text_style": "label",
        "color": "red",
    }


def test_element_binding_list_element_value() -> None:
    """A list-valued ``select.element`` fans out to multiple binding entries."""
    theme = {
        "style_rules": [
            {"apply_to": "element",
             "select": {"element": ["ec-cell", "ec-day-box"]},
             "style": {"use": "box:cell"}},
        ],
    }
    decompile_style_rules(theme)
    assert theme["element_styles"]["ec-cell"] == {"box_style": "cell"}
    assert theme["element_styles"]["ec-day-box"] == {"box_style": "cell"}


def test_decompiler_preserves_existing_legacy_sections() -> None:
    """If text_styles is already present, the decompiler must not overwrite it."""
    theme = {
        "text_styles": {"heading": {"font": "Old-Font", "size": 99}},
        "style_rules": [
            {"define": "text", "as": "heading",
             "style": {"font": "New-Font", "size": 10}},
        ],
    }
    decompile_style_rules(theme)
    # Existing key wins.
    assert theme["text_styles"]["heading"]["font"] == "Old-Font"
    assert theme["text_styles"]["heading"]["size"] == 99


def test_decompiler_idempotent() -> None:
    """Running the decompiler twice produces the same output."""
    theme = {
        "style_rules": [
            {"define": "text", "as": "heading",
             "style": {"font": "Roboto", "size": 10}},
            {"apply_to": "element",
             "select": {"element": "ec-heading"},
             "style": {"use": "text:heading"}},
        ],
    }
    decompile_style_rules(theme)
    first = {k: theme[k] for k in ("text_styles", "element_styles") if k in theme}
    decompile_style_rules(theme)
    second = {k: theme[k] for k in ("text_styles", "element_styles") if k in theme}
    assert first == second


def test_decompiler_on_no_style_rules_is_noop() -> None:
    theme = {"theme": {"name": "x"}}
    decompile_style_rules(theme)
    assert "text_styles" not in theme
    assert "box_styles" not in theme


def test_decompiler_handles_real_basic_yaml() -> None:
    """Decompile basic.yaml and confirm every expected legacy section appears."""
    theme = yaml.safe_load((THEMES_DIR / "basic.yaml").read_text())
    decompile_style_rules(theme)
    # basic.yaml defines roughly: ~20 text tokens, ~15 box tokens, ~5 line, ~4 icon
    assert len(theme.get("text_styles", {})) >= 15
    assert len(theme.get("box_styles", {})) >= 10
    assert len(theme.get("line_styles", {})) >= 3
    assert len(theme.get("icon_styles", {})) >= 3
    # And the canonical ec-* bindings should be present.
    bindings = theme.get("element_styles", {})
    for ec in ("ec-heading", "ec-day-number", "ec-day-box", "ec-grid-line"):
        assert ec in bindings, f"basic.yaml missing binding for {ec}"


def test_content_rules_stay_in_style_rules() -> None:
    """``apply_to: box:day`` content rules don't get decompiled away."""
    theme = {
        "style_rules": [
            {"define": "box", "as": "day", "style": {"fill": "white"}},
            {"name": "fed", "apply_to": "box:day",
             "select": {"federal_holiday": True},
             "style": {"fill": "tomato"}},
        ],
    }
    before = list(theme["style_rules"])
    decompile_style_rules(theme)
    # style_rules list is unchanged in-place — content rules remain readable
    # by the existing rule engine.
    assert theme["style_rules"] == before
