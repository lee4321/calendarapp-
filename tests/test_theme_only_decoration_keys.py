"""Decoration that used to be reachable only from the CLI now has theme keys."""

from __future__ import annotations

import pytest

from config.config import CalendarConfig
from config.theme_engine import ThemeEngine, find_unconsumed_keys


def _apply(theme: dict) -> CalendarConfig:
    config = CalendarConfig()
    engine = ThemeEngine()
    engine._theme_data = theme
    engine.apply(config)
    return config


@pytest.mark.parametrize(
    "theme,field,value",
    [
        ({"base": {"shade_current_day": True}}, "shade_current_day", True),
        ({"fiscal": {"use_period_colors": True}}, "fiscal_use_period_colors", True),
        ({"watermark": {"image": "logo.png"}}, "watermark_image", "logo.png"),
        ({"timeline": {"today_line_length": 40.0}}, "timeline_today_line_length", 40.0),
        ({"timeline": {"today_line_direction": "above"}}, "timeline_today_line_direction", "above"),
        ({"pit": {"today_line": {"date": 20260901}}}, "pit_today_date", "20260901"),
    ],
)
def test_theme_sets_formerly_cli_only_decoration(theme, field, value):
    assert getattr(_apply(theme), field) == value
    assert find_unconsumed_keys(theme) == []


def test_defaults_match_the_old_cli_off_state():
    config = CalendarConfig()
    assert config.shade_current_day is False
    assert config.fiscal_use_period_colors is False
    assert config.watermark_image == ""
