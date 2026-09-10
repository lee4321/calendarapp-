"""
Tests for the weekly overflow companion page (``--overflow`` / ``-x``).

The report is written beside the calendar as ``<output>_overflow.svg``
and lists the events and durations that could not fit in their day
boxes.  It is built through the shared details-page writer, so it takes
that page's format: page chrome, a title, a section heading, a column
header row, and as many pages as the entries need.
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


def _render(cfg, entries) -> int:
    coords = WeeklyCalendarLayout().calculate(cfg)
    renderer = WeeklyCalendarRenderer()
    renderer._drawing = renderer._create_drawing(cfg)
    return renderer._render_overflow_svg(cfg, coords, entries)


def _entries(count: int) -> list[OverflowEntry]:
    return [
        OverflowEntry("20260401", "20260403", f"Task {n}", "20260401")
        for n in range(count)
    ]


def test_overflow_page_renders_without_a_visualizer_token_ctx(tmp_path):
    """The page resolves its own typography from the theme's text tokens.

    The heuristic size rules are injected scoped to a visualizer, so a
    details page asking for a size with no visualizer in the ctx used to
    get ``None`` back and add to it.
    """
    cfg = _config(tmp_path)
    pages = _render(cfg, _entries(2))

    assert pages == 1
    assert (tmp_path / "weekly_overflow.svg").exists()


def test_long_report_continues_on_a_second_page(tmp_path):
    """Entries past the bottom continue rather than being dropped.

    The page exists to say what the calendar could not show, so
    truncating it would lose exactly the thing it is there to report.
    """
    cfg = _config(tmp_path)
    pages = _render(cfg, _entries(120))

    assert pages > 1
    assert (tmp_path / "weekly_overflow.svg").exists()
    assert (tmp_path / "weekly_overflow_p2.svg").exists()


def test_page_count_covers_every_page_written(tmp_path):
    """``_render_overflow_svg`` reports what it wrote, so ``render()``
    can add it to the calendar's own page."""
    cfg = _config(tmp_path)
    pages = _render(cfg, _entries(120))

    written = sorted(p.name for p in tmp_path.glob("weekly_overflow*.svg"))
    assert len(written) == pages


def test_report_carries_no_weekday_header(tmp_path):
    """The report borrows the calendar's coordinates for its header and
    footer, but it is not a grid -- the weekday labels stay behind."""
    cfg = _config(tmp_path)
    coords = WeeklyCalendarLayout().calculate(cfg)

    drawn: list[str] = []

    class _Recording(WeeklyCalendarRenderer):
        def _draw_text(self, x, y, text, *args, **kwargs):
            drawn.append(text)
            return super()._draw_text(x, y, text, *args, **kwargs)

    renderer = _Recording()
    renderer._drawing = renderer._create_drawing(cfg)
    renderer._render_overflow_svg(cfg, coords, _entries(2))

    assert "Overflow" in drawn          # the section heading is drawn
    assert not WeeklyCalendarRenderer._DAY_NAME_KEYS & set(drawn)


def test_output_suffix_is_configurable(tmp_path):
    """The filename suffix is a config field, as the gantt page's is."""
    cfg = _config(tmp_path)
    cfg.overflow_output_suffix = "_didnt_fit"
    _render(cfg, _entries(2))

    assert (tmp_path / "weekly_didnt_fit.svg").exists()
