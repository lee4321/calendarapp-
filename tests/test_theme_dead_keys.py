"""Shipped themes carry no keys the runtime ignores.

``find_unconsumed_keys`` walks a theme and returns every dotted key path that
no consumer reads: not in ``THEME_TO_CONFIG_MAP`` (directly or by cascade),
not a size_rule / layout margin / colors / pit-block / band-placement key,
and not inside a section consumed wholesale (``style_rules``, ``time_bands``,
``element_overrides``, ``swimlane_rules``).  A dead key in a shipped theme
reads as a working setting to anyone copying from it, so the bundled themes
must stay clean.
"""

from __future__ import annotations

import logging

import pytest

from config.theme_engine import ThemeEngine, find_unconsumed_keys
from config.theme_inheritance import read_theme_file

THEME_FILES = sorted(ThemeEngine.BUILTIN_THEMES_DIR.glob("*.yaml"))


@pytest.mark.parametrize("theme_path", THEME_FILES, ids=lambda p: p.stem)
def test_shipped_theme_has_no_unconsumed_keys(theme_path):
    data = read_theme_file(theme_path)
    assert find_unconsumed_keys(data) == []


class TestFindUnconsumedKeys:
    def test_mapped_key_is_consumed(self):
        assert find_unconsumed_keys({"timeline": {"axis_width": 2}}) == []

    def test_unmapped_key_is_reported(self):
        assert find_unconsumed_keys({"timeline": {"background_color": "white"}}) == ["timeline.background_color"]

    def test_nested_unmapped_key_is_reported(self):
        data = {"details": {"markdown": {"title_text": "Details", "bogus": 1}}}
        assert find_unconsumed_keys(data) == ["details.markdown.bogus"]

    def test_section_level_cascade_is_consumed(self):
        # timeline.font_size cascades into timeline.name_text / notes_text.
        assert find_unconsumed_keys({"timeline": {"font_size": 11}}) == []

    def test_base_cascade_is_consumed(self):
        assert find_unconsumed_keys({"base": {"font_family": "Roboto-Regular", "font_size": 9}}) == []

    def test_wholesale_sections_are_not_descended(self):
        data = {
            "style_rules": [{"define": "text", "as": "anything", "style": {"whatever": 1}}],
            "time_bands": {"q": {"unit": "fiscal_quarter", "made_up": True}},
            "element_overrides": {"ec-label": {"use": "text:label"}},
        }
        assert find_unconsumed_keys(data) == []

    def test_special_handlers_are_consumed(self):
        data = {
            "theme": {"name": "t", "version": "3.0", "description": "d"},
            "layout": {"margin": {"top": "0.5in", "left": {"value": 0.25, "unit": "in"}}},
            "colors": {"months": {"01": "red"}, "federal_holiday": {"color": "red", "alpha": 0.2}},
            "pit": {"axis": {"color": "grey"}, "leader_primary": {"color": "red"}},
            "blockplan": {"top_bands": ["q"], "size_rule": [{"when": {"papersize": ["letter"]}}]},
        }
        assert find_unconsumed_keys(data) == []

    def test_pit_block_extras_are_reported(self):
        data = {"pit": {"leader_secondary": {"color": "red", "dasharray": "2 2"}}}
        assert find_unconsumed_keys(data) == ["pit.leader_secondary.dasharray"]

    def test_unknown_section_is_left_to_section_validation(self):
        # Unknown top-level sections already get their own warning.
        assert find_unconsumed_keys({"not_a_section": {"x": 1}}) == []

    def test_engine_logs_a_warning(self, tmp_path, caplog):
        theme = tmp_path / "t.yaml"
        theme.write_text("theme:\n  name: t\ntimeline:\n  background_color: white\n")
        with caplog.at_level(logging.WARNING, logger="config.theme_engine"):
            ThemeEngine().load(str(theme))
        assert "timeline.background_color" in caplog.text
