"""``mini_calendar.icon_set`` picks the mini-icon glyph set from a theme.

mini-icon has no theme section of its own: MiniIconRenderer subclasses the
mini renderer and swaps day numbers for glyphs.  The one thing only it uses --
which of the six 31-glyph sets to draw from -- is ``mini_calendar.icon_set``
(theme-only).
"""

from __future__ import annotations

import pytest
from band_helpers import update_theme

from config.config import ICON_SETS, CalendarConfig
from visualizers.mini_icon.renderer import MiniIconRenderer


def _themed(icon_set: str | None) -> CalendarConfig:
    config = CalendarConfig()
    if icon_set:
        update_theme(config, mini_calendar={"icon_set": icon_set})
    return config


def test_the_default_is_unchanged():
    assert _themed(None).theme_v3.mini_calendar.icon_set == "squares"


@pytest.mark.parametrize("name", sorted(ICON_SETS))
def test_a_theme_can_choose_any_of_the_shipped_sets(name):
    assert _themed(name).theme_v3.mini_calendar.icon_set == name


def test_the_renderer_resolves_what_the_theme_asked_for():
    """The mapping is only useful if the drawn glyphs actually change."""
    renderer = MiniIconRenderer()
    squares = renderer._get_day_icon_name(1, _themed("squares"))
    circles = renderer._get_day_icon_name(1, _themed("darkcircles"))
    assert squares == ICON_SETS["squares"][0]
    assert circles == ICON_SETS["darkcircles"][0]
    assert squares != circles
