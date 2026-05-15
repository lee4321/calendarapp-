"""Tests that ThemeEngine populates config.theme with a UnifiedTheme."""

from __future__ import annotations

from pathlib import Path

import pytest

from config.config import CalendarConfig
from config.theme_engine import ThemeEngine
from config.unified_theme import UnifiedTheme


THEMES = ("basic", "SAMPLE", "default", "TJX", "minimal")


@pytest.mark.parametrize("theme_name", THEMES)
def test_theme_engine_load_apply_populates_config_theme(theme_name: str) -> None:
    """After ThemeEngine.load() + apply(), config.theme is a UnifiedTheme."""
    engine = ThemeEngine()
    engine.load(theme_name)
    config = CalendarConfig()
    engine.apply(config)
    assert isinstance(config.theme, UnifiedTheme), (
        f"theme {theme_name!r}: config.theme should be a UnifiedTheme, "
        f"got {type(config.theme).__name__}"
    )


def test_resolve_token_returns_style_bag() -> None:
    engine = ThemeEngine()
    engine.load("default")
    config = CalendarConfig()
    engine.apply(config)
    assert config.theme is not None
    # text:heading should resolve to something containing font/size/color.
    style = config.theme.resolve_token("text:heading")
    assert "font" in style or "color" in style or "size" in style


def test_papersize_override_layers_on_top_of_definition() -> None:
    """SAMPLE.yaml defines text:heading and overrides size on small papers."""
    engine = ThemeEngine()
    engine.load("SAMPLE")
    config = CalendarConfig()
    engine.apply(config)
    assert config.theme is not None

    default = config.theme.resolve_token("text:heading", {"papersize": "letter"})
    small = config.theme.resolve_token("text:heading", {"papersize": "3x5"})
    # SAMPLE has: define text:heading style.size: 11; small-paper override sets size: 8
    assert default.get("size") == 11
    assert small.get("size") == 8


def test_legacy_theme_styles_field_remains_populated() -> None:
    """The legacy theme_styles field still gets populated by ThemeEngine.apply()."""
    engine = ThemeEngine()
    engine.load("default")
    config = CalendarConfig()
    engine.apply(config)
    # Both old and new APIs available — neither has retired the other yet.
    assert config.theme_styles is not None
    assert config.theme is not None
