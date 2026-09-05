"""``mini_calendar.icon_set`` picks the mini-icon glyph set from a theme.

mini-icon has no theme section of its own: MiniIconRenderer subclasses the
mini renderer and swaps day numbers for glyphs, so it reads ``mini_*`` like
the rest of that family. The one thing only it uses — which of the six
31-glyph sets to draw from — was reachable from ``--mini-icon-set`` alone.
"""

from __future__ import annotations

from argparse import Namespace

import pytest

from cli.config_assembly import _reapply_post_theme_cli_overrides
from config.config import CalendarConfig
from config.theme_engine import ThemeEngine
from visualizers.mini_icon.renderer import ICON_SETS


def _themed(icon_set: str | None) -> CalendarConfig:
    config = CalendarConfig()
    engine = ThemeEngine()
    engine._theme_data = (
        {"mini_calendar": {"icon_set": icon_set}} if icon_set else {}
    )
    engine.apply(config)
    return config


def test_the_default_is_unchanged():
    assert CalendarConfig().mini_icon_set == "squares"
    assert _themed(None).mini_icon_set == "squares"


@pytest.mark.parametrize("name", sorted(ICON_SETS))
def test_a_theme_can_choose_any_of_the_shipped_sets(name):
    assert _themed(name).mini_icon_set == name


def test_the_renderer_resolves_what_the_theme_asked_for():
    """The mapping is only useful if the drawn glyphs actually change."""
    squares = ICON_SETS[_themed("squares").mini_icon_set]
    circles = ICON_SETS[_themed("darkcircles").mini_icon_set]
    assert len(squares) == len(circles) == 31
    assert squares != circles


def test_an_explicit_flag_still_beats_the_theme():
    """CLI precedence is the engine's contract; the theme is the default."""
    config = _themed("squircles")
    _reapply_post_theme_cli_overrides(
        Namespace(mini_icon_set="darksquare"), config
    )
    assert config.mini_icon_set == "darksquare"


def test_the_theme_survives_when_no_flag_is_given():
    """The re-apply pass must not overwrite a theme with an unset flag."""
    config = _themed("squircles")
    _reapply_post_theme_cli_overrides(Namespace(mini_icon_set=None), config)
    assert config.mini_icon_set == "squircles"
