"""
Tests for the weekly overflow companion page (``--overflow`` / ``-x``).

The page is written next to the calendar as ``<output>_overflow.svg`` and
lists the events and durations that could not fit in their day boxes.
"""

from __future__ import annotations

from config.config import create_calendar_config, setfontsizes
from shared.date_utils import calc_calendar_range
from visualizers.weekly.layout import WeeklyCalendarLayout
from visualizers.weekly.renderer import OverflowEntry, WeeklyCalendarRenderer


def _config(tmp_path) -> "object":
    cfg = create_calendar_config()
    cfg.pageX = 792.0
    cfg.pageY = 612.0
    calc_calendar_range(cfg, "20260401", "20260630")
    cfg.outputfile = str(tmp_path / "weekly.svg")
    setfontsizes(cfg)
    return cfg


def test_overflow_page_renders_without_a_visualizer_token_ctx(tmp_path):
    """The page resolves its table font size even though it asks for
    ``text:event_name`` with no ``visualizer`` in the token ctx.

    The heuristic size rules are injected scoped to ``weekly``, so an
    unscoped lookup returns no ``size:`` and the renderer must fall back
    to the legacy field rather than adding to ``None``.
    """
    cfg = _config(tmp_path)
    coords = WeeklyCalendarLayout().calculate(cfg)

    renderer = WeeklyCalendarRenderer()
    renderer._drawing = renderer._create_drawing(cfg)
    renderer._render_overflow_svg(
        cfg,
        coords,
        [
            OverflowEntry("20260401", "20260401", "Kickoff", "20260401"),
            OverflowEntry("20260406", "20260410", "Design review", "20260406"),
        ],
    )

    assert (tmp_path / "weekly_overflow.svg").exists()
