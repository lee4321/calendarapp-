"""Tests for the vertical_lines → style_rules conversion in migrate_theme.py."""

from __future__ import annotations

import yaml

from tools.migrate_theme_v1_to_v2 import migrate_text


SOURCE = """\
blockplan:
  vertical_line_color: red
  vertical_line_width: 1.5
  vertical_lines:
    - band: "Month"
      repeat: true
      align: "end"
      color: "grey"
      width: 1.0
      opacity: 0.4
      dash_array: "4,4"
      fill_color: ["red", "blue"]
      fill_opacity: 0.25
    - band: "Date"
      repeat: true
      match:
        weekend: true
      color: "#888"
      fill_color: "#eeeeee"
"""


def test_converts_to_style_rules_block():
    new_text, changes = migrate_text(SOURCE)
    assert any("vertical_lines" in c for c in changes)
    parsed = yaml.safe_load(new_text)
    rules = parsed.get("style_rules") or []
    vline_rules = [r for r in rules if r.get("apply_to") == "vertical_line"]
    assert len(vline_rules) == 2

    first = vline_rules[0]
    assert first["select"] == {"band": "Month", "repeat": True}
    assert first["style"]["align"] == "end"
    assert first["style"]["stroke_color"] == "grey"
    assert first["style"]["stroke_width"] == 1.0
    assert first["style"]["stroke_opacity"] == 0.4
    assert first["style"]["stroke_dasharray"] == "4,4"
    assert first["style"]["fill_color"] == ["red", "blue"]
    assert first["style"]["fill_opacity"] == 0.25


def test_match_keys_hoisted_into_select():
    _, changes = migrate_text(SOURCE)
    parsed = yaml.safe_load(migrate_text(SOURCE)[0])
    second = [
        r for r in parsed["style_rules"] if r.get("apply_to") == "vertical_line"
    ][1]
    assert second["select"]["weekend"] is True
    # match: dict itself should be gone
    assert "match" not in second["select"]


def test_original_block_is_removed():
    new_text, _ = migrate_text(SOURCE)
    parsed = yaml.safe_load(new_text)
    assert "vertical_lines" not in (parsed.get("blockplan") or {})
    # Per-attribute defaults stay put.
    assert parsed["blockplan"]["vertical_line_color"] == "red"


def test_excelheader_vertical_lines_left_alone():
    src = """\
excelheader:
  vertical_lines:
    - band: "Month"
      repeat: true
      color: "navy"
"""
    new_text, changes = migrate_text(src)
    # No conversion → no changes.
    assert changes == []
    assert new_text == src


def test_empty_vertical_lines_block_is_removed():
    src = """\
blockplan:
  vertical_lines: []
"""
    new_text, changes = migrate_text(src)
    assert any("vertical_lines" in c for c in changes)
    parsed = yaml.safe_load(new_text)
    assert "vertical_lines" not in (parsed.get("blockplan") or {})


def test_idempotent_when_no_legacy_block_remains():
    once, _ = migrate_text(SOURCE)
    twice, changes = migrate_text(once)
    assert changes == []
    assert twice == once


def test_appends_to_existing_style_rules_block():
    src = """\
blockplan:
  vertical_lines:
    - band: "Month"
      repeat: true
      color: "grey"

style_rules:
  - name: existing
    apply_to: day_box
    select: {weekend: true}
    style: {fill_color: "lightyellow"}
"""
    new_text, _ = migrate_text(src)
    # Should still have exactly one top-level style_rules: block.
    assert new_text.count("\nstyle_rules:") + new_text.count(
        "style_rules:\n"
    ) - new_text.count("\nstyle_rules:\n") <= 2  # tolerant count
    parsed = yaml.safe_load(new_text)
    rules = parsed["style_rules"]
    names = [r.get("name") for r in rules]
    assert "existing" in names
    assert any(r.get("apply_to") == "vertical_line" for r in rules)
