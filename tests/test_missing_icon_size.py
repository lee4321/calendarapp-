"""The stand-in glyph's size is the theme's to choose.

``base.default_missing_icon`` names the icon drawn when a requested one is
not in the icons table.  It was always drawn at the size of the glyph it
replaced, which is right when the substitute should sit in the same hole and
wrong when it should be conspicuous — a 6pt question mark in a mini-calendar
day cell is easy to miss.  ``base.default_missing_icon_size`` overrides it;
``None`` keeps the old behaviour.
"""

from __future__ import annotations

import re

import drawsvg
import pytest

from config.config import CalendarConfig
from config.theme_engine import ThemeEngine
from renderers.svg_base import BaseSVGRenderer

_ICON = '<svg viewBox="0 0 24 24"><path d="M0 0h24v24H0z"/></svg>'


class _Probe(BaseSVGRenderer):
    """Bare renderer that draws into a scratch drawing."""

    def __init__(self):
        self._icon_svg_map = {"real": _ICON, "stand-in": _ICON}
        self._drawing = drawsvg.Drawing(200, 200)

    def _layout(self, *args, **kwargs):
        return {}

    def _render_content(self, *args, **kwargs):
        return 0, []

    def last_icon_size(self) -> float | None:
        markup = "".join(str(getattr(e, "content", "")) for e in self._drawing.elements)
        sizes = re.findall(r'<svg x="[\d.-]+" y="[\d.-]+" width="([\d.]+)"', markup)
        return float(sizes[-1]) if sizes else None


def test_a_resolvable_icon_ignores_the_fallback_size():
    probe = _Probe()
    probe._draw_icon_svg(
        "real", 10.0, 20.0, size=6.0,
        fallback_name="stand-in", fallback_size=18.0,
    )
    assert probe.last_icon_size() == pytest.approx(6.0)


def test_the_fallback_keeps_the_requested_size_when_none_is_configured():
    probe = _Probe()
    probe._draw_icon_svg(
        "no-such-icon", 10.0, 20.0, size=6.0, fallback_name="stand-in",
    )
    assert probe.last_icon_size() == pytest.approx(6.0)


def test_a_configured_size_wins_for_the_fallback():
    probe = _Probe()
    probe._draw_icon_svg(
        "no-such-icon", 10.0, 20.0, size=6.0,
        fallback_name="stand-in", fallback_size=18.0,
    )
    assert probe.last_icon_size() == pytest.approx(18.0)


@pytest.mark.parametrize("bad", [0.0, -4.0])
def test_a_nonpositive_configured_size_is_ignored(bad):
    """A theme typo costs the override, not the glyph."""
    probe = _Probe()
    probe._draw_icon_svg(
        "no-such-icon", 10.0, 20.0, size=6.0,
        fallback_name="stand-in", fallback_size=bad,
    )
    assert probe.last_icon_size() == pytest.approx(6.0)


def test_the_theme_key_reaches_config():
    config = CalendarConfig()
    assert config.default_missing_icon_size is None

    engine = ThemeEngine()
    engine._theme_data = {"base": {"default_missing_icon_size": 14.0}}
    engine.apply(config)
    assert config.default_missing_icon_size == pytest.approx(14.0)
