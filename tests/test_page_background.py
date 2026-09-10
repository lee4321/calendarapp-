"""
Every SVG page lays the theme's ground down first.

A dark theme paints light ink, which needs a dark page under it; an SVG
with no background of its own takes the viewer's, which is white
everywhere it matters.  ``weekly``, ``mini`` and ``gantt`` used to draw
no background at all, so under a dark theme their output was pale text
on white.
"""

from __future__ import annotations

import pytest

from config.config import create_calendar_config, setfontsizes
from config.styles import BoxStyle
from shared.date_utils import calc_calendar_range
from visualizers.factory import VisualizerFactory

#: Every visualizer whose renderer opens an SVG page.
_SVG_VIEWS = (
    "weekly", "mini", "mini-icon", "candybar",
    "gantt", "timeline", "blockplan", "compactplan", "pit",
)


def _config(ground: str | None = "black"):
    cfg = create_calendar_config()
    cfg.pageX = 792.0
    cfg.pageY = 612.0
    calc_calendar_range(cfg, "20260401", "20260630")
    setfontsizes(cfg)
    style = BoxStyle(fill=ground) if ground is not None else BoxStyle(fill="none")
    cfg.get_box_style = lambda ec: style if ec == "ec-background" else BoxStyle()
    return cfg


def _page_svg(view: str, cfg) -> str:
    renderer = VisualizerFactory.create(view)._create_renderer()
    return renderer._create_drawing(cfg).as_svg()


@pytest.mark.parametrize("view", _SVG_VIEWS)
def test_every_svg_page_carries_the_theme_ground(view):
    svg = _page_svg(view, _config("black"))

    assert 'class="ec-background"' in svg
    assert 'fill="black"' in svg


@pytest.mark.parametrize("view", _SVG_VIEWS)
def test_a_transparent_ground_paints_nothing(view):
    """A theme that wants the page left alone says so, and nothing is
    drawn -- not a white rectangle standing in for one."""
    svg = _page_svg(view, _config(None))

    assert "ec-background" not in svg


def test_the_ground_covers_the_whole_page():
    svg = _page_svg("weekly", _config("navy"))

    assert 'x="0" y="0" width="792.0" height="612.0"' in svg


def test_the_ground_is_drawn_before_the_content():
    """It is a ground, not an overlay: everything else lands on top."""
    cfg = _config("navy")
    renderer = VisualizerFactory.create("weekly")._create_renderer()
    drawing = renderer._create_drawing(cfg)
    renderer._drawing = drawing
    renderer._draw_rect(10, 10, 20, 20, fill="red")

    svg = drawing.as_svg()
    assert svg.index("ec-background") < svg.index('fill="red"')
