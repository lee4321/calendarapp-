"""Themes that ``extends:`` another: merge rules, rule overlays and derivation."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from config.theme_engine import ThemeEngine
from config.theme_inheritance import BUILTIN_THEMES_DIR, merge_rules, read_theme_file, resolve_extends
from config.unified_theme import ThemeError, parse_theme
from tools.derive_theme import derive


def _write(tmp_path: Path, name: str, data: dict) -> Path:
    path = tmp_path / f"{name}.yaml"
    path.write_text(yaml.safe_dump(data, sort_keys=False))
    return path


_PARENT = {
    "theme": {"name": "Parent"},
    "timeline": {"axis_color": "black", "axis_width": 2, "top_colors": ["red", "blue"]},
    "candybar": {"month_shade_colors": ["none", "aliceblue"]},
}


def test_sections_merge_key_by_key_and_lists_replace(tmp_path):
    _write(tmp_path, "parent", _PARENT)
    child = _write(tmp_path, "child", {"extends": "parent", "timeline": {"axis_width": 3, "top_colors": ["gold"]}})
    merged = read_theme_file(child)
    assert merged["timeline"] == {"axis_color": "black", "axis_width": 3, "top_colors": ["gold"]}
    assert merged["theme"] == {"name": "Parent"}
    assert "extends" not in merged


def test_unset_leaves_a_parent_key_at_the_built_in_default(tmp_path):
    _write(tmp_path, "parent", _PARENT)
    child = _write(tmp_path, "child", {"extends": "parent", "unset": ["candybar.month_shade_colors"]})
    merged = read_theme_file(child)
    assert merged["candybar"] == {}
    assert "unset" not in merged


@pytest.mark.parametrize(
    ("child", "message"),
    [
        ({"extends": "parent", "unset": ["timeline.nope"]}, "not set by the parent"),
        ({"extends": "no_such_theme"}, "not found"),
        ({"unset": ["timeline.axis_color"]}, "only applies"),
    ],
)
def test_mistakes_are_reported(tmp_path, child, message):
    _write(tmp_path, "parent", _PARENT)
    with pytest.raises(ThemeError, match=message):
        read_theme_file(_write(tmp_path, "child", child))


def test_a_loop_is_reported(tmp_path):
    _write(tmp_path, "a", {"extends": "b"})
    b = _write(tmp_path, "b", {"extends": "a"})
    with pytest.raises(ThemeError, match="loop"):
        read_theme_file(b)


def test_a_parent_can_extend_its_own_parent(tmp_path):
    _write(tmp_path, "grand", _PARENT)
    _write(tmp_path, "parent", {"extends": "grand", "timeline": {"axis_width": 5}})
    child = _write(tmp_path, "child", {"extends": "parent", "timeline": {"axis_color": "white"}})
    assert read_theme_file(child)["timeline"]["axis_width"] == 5
    assert read_theme_file(child)["timeline"]["axis_color"] == "white"


# ── style_rules overlay ─────────────────────────────────────────────────────

_RULES = [
    {"name": "a", "define": "text", "as": "heading", "style": {"font": "Roboto-Bold", "size": 12}},
    {"name": "b", "apply_to": "box:event", "select": {"milestone": True}, "style": {"fill": "red"}},
    {"name": "c", "apply_to": "box:event", "style": {"fill": "blue"}},
]


def test_a_named_entry_merges_into_its_rule_in_place():
    rules = merge_rules(_RULES, [{"name": "a", "style": {"size": 14}}])
    assert rules[0]["style"] == {"font": "Roboto-Bold", "size": 14}
    assert [r["name"] for r in rules] == ["a", "b", "c"]


def test_replace_and_remove():
    rules = merge_rules(_RULES, [{"name": "b", "replace": True, "apply_to": "box:day"}, {"name": "c", "remove": True}])
    assert rules[1] == {"name": "b", "apply_to": "box:day"}
    assert [r["name"] for r in rules] == ["a", "b"]


def test_a_new_rule_lands_after_the_previous_entry_s_rule():
    new = {"name": "n", "apply_to": "box:event", "style": {"fill": "green"}}
    assert [r["name"] for r in merge_rules(_RULES, [{"name": "a"}, new])] == ["a", "n", "b", "c"]
    assert [r["name"] for r in merge_rules(_RULES, [new])] == ["n", "a", "b", "c"]


@pytest.mark.parametrize(
    "overlay",
    [[{"apply_to": "box:day"}], [{"name": "x", "remove": True}], [{"name": "a"}, {"name": "a"}]],
    ids=["unnamed", "remove-unknown", "duplicate"],
)
def test_an_overlay_it_cannot_apply_is_refused(overlay):
    with pytest.raises(ThemeError):
        merge_rules(_RULES, overlay)


# ── Shipped themes and derivation ────────────────────────────────────────────

_CHILDREN = [p for p in sorted(BUILTIN_THEMES_DIR.glob("*.yaml")) if "extends" in yaml.safe_load(p.read_text())]


def test_some_shipped_themes_extend_another():
    assert len(_CHILDREN) >= 4


@pytest.mark.parametrize("path", _CHILDREN, ids=lambda p: p.stem)
def test_a_shipped_child_loads_everywhere_a_full_theme_does(path):
    merged = read_theme_file(path)
    assert parse_theme(path).sections == merged
    engine = ThemeEngine()
    engine.load(str(path))
    assert engine._theme_data == merged


def test_deriving_a_full_theme_round_trips():
    parent = read_theme_file(BUILTIN_THEMES_DIR / "corporate.yaml")
    theme = yaml.safe_load((BUILTIN_THEMES_DIR / "default.yaml").read_text())
    child = derive(parent, theme, "corporate")
    assert resolve_extends(child, BUILTIN_THEMES_DIR) == theme
    assert len(yaml.safe_dump(child).splitlines()) < len(yaml.safe_dump(theme).splitlines()) / 2
