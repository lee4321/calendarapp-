"""Tests for auto-normalization of decoration pattern tile sizes.

Native tiles in the ``patterns`` table span 16 pt to 1920 pt.  Rendered at
native size the large ones show a single crop of the artwork instead of a
repeating texture, so ``pattern_def_xml`` shrinks oversized tiles to a
common target.  These tests pin the shrink-only rule, the seamlessness of
the scaled def, and the config/theme plumbing that feeds it.
"""

from __future__ import annotations

import re
import tempfile

import pytest
import yaml

from config.config import DEFAULT_PATTERN_TARGET_SIZE, CalendarConfig, create_calendar_config
from config.theme_engine import ThemeEngine
from renderers.svg_patterns import (
    normalize_tile_scale,
    parse_svg_tile_size,
    pattern_def_xml,
)

TINY_TILE = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16"><rect fill="#000" width="8" height="8"/></svg>'
HUGE_TILE = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1920 1920">'
    '<circle fill="#000000" cx="960" cy="960" r="400"/></svg>'
)
OBLONG_TILE = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 20"><rect fill="black" width="50" height="10"/></svg>'
)


def _tile_size_of(def_xml: str) -> tuple[float, float]:
    """Read width/height back off a generated ``<pattern>`` element."""
    w = re.search(r'<pattern[^>]*\bwidth="([\d.]+)"', def_xml)
    h = re.search(r'<pattern[^>]*\bheight="([\d.]+)"', def_xml)
    assert w and h, def_xml
    return float(w.group(1)), float(h.group(1))


class TestNormalizeTileScale:
    """The shrink-only normalization factor."""

    def test_oversized_tile_shrinks_to_target(self):
        assert normalize_tile_scale(1920, 1920, 18.0) == pytest.approx(18.0 / 1920)

    def test_tile_at_target_is_untouched(self):
        assert normalize_tile_scale(18, 18, 18.0) == 1.0

    def test_undersized_tile_is_not_upscaled(self):
        # Shrink-only: a 16 pt tile already reads as texture, so leave it.
        assert normalize_tile_scale(16, 16, 18.0) == 1.0

    def test_scale_is_driven_by_the_largest_dimension(self):
        # 100x20 must come down by 100, not by 20, or it still overflows.
        assert normalize_tile_scale(100, 20, 18.0) == pytest.approx(0.18)

    def test_zero_target_disables_normalization(self):
        assert normalize_tile_scale(1920, 1920, 0) == 1.0

    def test_none_target_disables_normalization(self):
        assert normalize_tile_scale(1920, 1920, None) == 1.0

    def test_extra_scale_multiplies_the_normalized_factor(self):
        assert normalize_tile_scale(1920, 1920, 18.0, 0.5) == pytest.approx(18.0 / 1920 * 0.5)

    def test_extra_scale_applies_even_when_normalization_is_off(self):
        assert normalize_tile_scale(40, 40, 0, 0.25) == 0.25

    def test_extra_scale_can_enlarge_a_tile_left_alone_by_the_target(self):
        assert normalize_tile_scale(16, 16, 18.0, 2.0) == 2.0

    def test_degenerate_tile_does_not_divide_by_zero(self):
        assert normalize_tile_scale(0, 0, 18.0) == 1.0


class TestPatternDefXml:
    """The generated ``<pattern>`` element."""

    def test_oversized_tile_reports_the_target_size(self):
        xml = pattern_def_xml("pat-x", HUGE_TILE, None, target_size=18.0)
        assert _tile_size_of(xml) == (pytest.approx(18.0), pytest.approx(18.0))

    def test_oversized_tile_wraps_content_in_a_scaling_group(self):
        xml = pattern_def_xml("pat-x", HUGE_TILE, None, target_size=18.0)
        assert '<g transform="scale(' in xml
        assert "<circle" in xml

    def test_reported_size_and_group_scale_agree(self):
        # If these diverge the pattern tiles with gaps or overlaps.
        xml = pattern_def_xml("pat-x", OBLONG_TILE, None, target_size=18.0)
        m = re.search(r'<g transform="scale\(([\d.e-]+)\)"', xml)
        assert m, xml
        scale = float(m.group(1))
        native_w, native_h = parse_svg_tile_size(OBLONG_TILE)
        tile_w, tile_h = _tile_size_of(xml)
        assert tile_w == pytest.approx(native_w * scale, rel=1e-4)
        assert tile_h == pytest.approx(native_h * scale, rel=1e-4)

    def test_tile_at_or_below_target_gets_no_scaling_group(self):
        xml = pattern_def_xml("pat-x", TINY_TILE, None, target_size=18.0)
        assert "transform=" not in xml
        assert _tile_size_of(xml) == (16.0, 16.0)

    def test_disabled_target_keeps_the_native_size(self):
        xml = pattern_def_xml("pat-x", HUGE_TILE, None, target_size=0)
        assert _tile_size_of(xml) == (1920.0, 1920.0)

    def test_colorization_still_applies_under_scaling(self):
        xml = pattern_def_xml("pat-x", HUGE_TILE, "red", target_size=18.0)
        assert 'fill="red"' in xml
        assert 'fill="#000000"' not in xml

    def test_default_target_is_applied_when_unspecified(self):
        xml = pattern_def_xml("pat-x", HUGE_TILE, None)
        assert _tile_size_of(xml) == (
            pytest.approx(DEFAULT_PATTERN_TARGET_SIZE),
            pytest.approx(DEFAULT_PATTERN_TARGET_SIZE),
        )


class TestPatternScaleConfig:
    """Config defaults, validation, and the theme keys that set them."""

    def test_defaults(self):
        config = CalendarConfig()
        assert config.hash_pattern_target_size == DEFAULT_PATTERN_TARGET_SIZE
        assert config.hash_pattern_scale == 1.0

    def test_zero_target_is_allowed_as_the_disable_switch(self):
        assert CalendarConfig(hash_pattern_target_size=0).hash_pattern_target_size == 0

    def test_negative_target_is_rejected(self):
        with pytest.raises(ValueError, match="hash_pattern_target_size"):
            CalendarConfig(hash_pattern_target_size=-1)

    def test_non_positive_scale_is_rejected(self):
        with pytest.raises(ValueError, match="hash_pattern_scale"):
            CalendarConfig(hash_pattern_scale=0)

    @staticmethod
    def _apply_theme_data(theme_data: dict) -> CalendarConfig:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(theme_data, f)
            f.flush()
            engine = ThemeEngine()
            engine.load(f.name)
            config = create_calendar_config()
            engine.apply(config)
        return config

    def test_theme_sets_target_size(self):
        config = self._apply_theme_data(
            {
                "theme": {"name": "Pat"},
                "weekly": {"day_box": {"hash_pattern_target_size": 12}},
            }
        )
        assert config.hash_pattern_target_size == 12

    def test_theme_sets_scale(self):
        config = self._apply_theme_data(
            {
                "theme": {"name": "Pat"},
                "weekly": {"day_box": {"hash_pattern_scale": 0.5}},
            }
        )
        assert config.hash_pattern_scale == 0.5
