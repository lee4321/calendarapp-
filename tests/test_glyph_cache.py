"""Glyph lookups on a font with no Unicode character map."""

from __future__ import annotations

import pytest

from renderers import glyph_cache


class _FontWithoutUnicodeCmap:
    """Stands in for a TTFont whose getBestCmap() finds no Unicode table."""

    def getBestCmap(self):
        return None

    def getGlyphSet(self):
        return {}

    def __getitem__(self, table):
        assert table == "head"
        return type("Head", (), {"unitsPerEm": 1000})()


@pytest.fixture
def no_cmap_font(monkeypatch):
    monkeypatch.setattr(
        glyph_cache, "_load_ttfont", lambda path: _FontWithoutUnicodeCmap()
    )
    glyph_cache.get_ink_extents.cache_clear()
    yield "no-cmap.ttf"
    glyph_cache.get_ink_extents.cache_clear()


def test_glyph_path_is_empty_when_the_font_maps_no_codepoints(no_cmap_font):
    assert glyph_cache._get_glyph_path(no_cmap_font, ord("A")) == ""


def test_ink_extents_fall_back_when_the_font_maps_no_codepoints(no_cmap_font):
    assert glyph_cache.get_ink_extents(no_cmap_font) == glyph_cache._INK_FALLBACK
