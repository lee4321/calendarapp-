"""Glyph groups named by the theme reach the grid views from the database."""

from __future__ import annotations

import pytest
from band_helpers import update_theme
from fakes import FakeCalendarDB, GlyphsFromSeed, seeded_glyphs

from cli.errors import ConfigError
from config.config import CalendarConfig
from shared.glyphs import DEFAULT_DURATION_FILL, mini_glyph_sets, resolve_group, text_mini_glyph_sets


class _DB(GlyphsFromSeed, FakeCalendarDB):
    pass


def test_an_unset_group_is_none():
    assert resolve_group(None, _DB(), "role") is None


def test_a_group_is_read_from_the_database():
    assert resolve_group("digits-superscript", _DB(), "role") == seeded_glyphs("digits-superscript")


def test_an_unknown_group_names_the_role_and_the_groups_that_exist():
    with pytest.raises(ConfigError, match=r"text_mini\.glyphs\.event.*digits-ascii"):
        resolve_group("nope", _DB(), "text_mini.glyphs.event")


def test_mini_uses_the_fonts_own_digits_until_a_theme_names_a_group():
    config = CalendarConfig()
    assert mini_glyph_sets(config, _DB()).day_number_digits is None
    update_theme(config, mini_calendar={"glyphs": {"day_number": "day-circled"}})
    assert mini_glyph_sets(config, _DB()).day_number == seeded_glyphs("day-circled")


def test_text_mini_symbols_default_to_the_seeded_groups():
    sets = text_mini_glyph_sets(CalendarConfig(), _DB())
    assert sets.event == seeded_glyphs("text-mini-event")
    assert sets.duration_fill == seeded_glyphs("duration-fill")[0]
    assert sets.day_number_digits is None


def test_text_mini_without_a_fill_group_uses_the_default_glyph():
    config = CalendarConfig()
    update_theme(config, text_mini={"glyphs": {"duration_fill": None}})
    assert text_mini_glyph_sets(config, _DB()).duration_fill == DEFAULT_DURATION_FILL
