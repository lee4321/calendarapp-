"""Both Gantt band stacks accept any number of time bands.

`gantt.top_bands` and `gantt.bottom_bands` are plain lists, and neither
the layout nor the renderer caps their length. What is bounded is the
*height* they may take together: past `MAX_CHROME_SHARE` of the content
height every chrome row scales down proportionally, so the task body
survives rather than a band being dropped.
"""

from __future__ import annotations

from datetime import date

import pytest

from config.config import CalendarConfig
from shared.date_utils import visible_days
from test_gantt_marks import _DummyDB, render, task
from visualizers.gantt.layout import MAX_CHROME_SHARE, GanttLayout
from visualizers.gantt.renderer import GanttRenderer

_PAGE = (792.0, 612.0)


def bands(count: int, row_height: float = 10.0, unit: str = "month") -> list[dict]:
    return [
        {"label": f"B{index}", "unit": unit, "row_height": row_height}
        for index in range(count)
    ]


@pytest.fixture
def config() -> CalendarConfig:
    config = CalendarConfig()
    config.pageX, config.pageY = _PAGE
    return config


# ── Layout ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("count", [1, 2, 3, 5, 8, 12])
def test_a_stack_of_any_length_gets_its_full_height(config, count):
    config.gantt_top_time_bands = bands(count)
    config.gantt_bottom_time_bands = []
    assert GanttLayout().calculate(config)["GanttTopBands"][3] == pytest.approx(
        10.0 * count, abs=0.01
    )


@pytest.mark.parametrize("count", [1, 4, 9])
def test_the_two_stacks_size_independently(config, count):
    config.gantt_top_time_bands = bands(count)
    config.gantt_bottom_time_bands = bands(2)
    coords = GanttLayout().calculate(config)
    assert coords["GanttTopBands"][3] == pytest.approx(10.0 * count, abs=0.01)
    assert coords["GanttBottomBands"][3] == pytest.approx(20.0, abs=0.01)


def test_bands_may_each_state_their_own_height(config):
    config.gantt_top_time_bands = [
        {"label": "a", "unit": "month", "row_height": 24},
        {"label": "b", "unit": "week", "row_height": 10},
        {"label": "c", "unit": "date"},          # falls back to the config default
    ]
    config.gantt_band_row_height = 6.0
    config.gantt_bottom_time_bands = []
    assert GanttLayout().calculate(config)["GanttTopBands"][3] == pytest.approx(
        40.0, abs=0.01
    )


@pytest.mark.parametrize("count", [20, 60, 200])
def test_a_very_tall_stack_scales_instead_of_starving_the_body(config, count):
    """No band is dropped; every chrome row shrinks together."""
    config.gantt_top_time_bands = bands(count)
    config.gantt_bottom_time_bands = bands(count)
    coords = GanttLayout().calculate(config)

    content_h = coords["GanttArea"][3]
    chrome = (
        coords["GanttTopBands"][3]
        + coords["GanttBottomBands"][3]
        + coords["GanttColumnHeader"][3]
    )
    assert coords["GanttChartBody"][3] > 0
    assert coords["GanttTableBody"][3] > 0
    assert chrome <= content_h * MAX_CHROME_SHARE + 0.01


def test_the_stacks_keep_their_proportions_when_scaled(config):
    """A stack twice as tall as the other stays twice as tall."""
    config.gantt_top_time_bands = bands(40)
    config.gantt_bottom_time_bands = bands(20)
    coords = GanttLayout().calculate(config)
    assert coords["GanttTopBands"][3] == pytest.approx(
        coords["GanttBottomBands"][3] * 2, rel=0.01
    )


def test_no_bands_at_all_is_allowed(config):
    config.gantt_top_time_bands = []
    config.gantt_bottom_time_bands = []
    coords = GanttLayout().calculate(config)
    assert coords["GanttTopBands"][3] == 0
    assert coords["GanttBottomBands"][3] == 0


def test_malformed_entries_cost_one_band_not_the_page(config):
    config.gantt_top_time_bands = [
        {"label": "good", "unit": "month", "row_height": 10},
        "not a dict",
        None,
    ]
    config.gantt_bottom_time_bands = []
    assert GanttLayout().calculate(config)["GanttTopBands"][3] == pytest.approx(
        10.0, abs=0.01
    )


# ── Segments and drawing ──────────────────────────────────────────────────


def test_every_band_in_both_stacks_gets_its_own_segments():
    config = CalendarConfig()
    config.pageX, config.pageY = _PAGE
    config.gantt_top_time_bands = [
        {"label": "q", "unit": "fiscal_quarter"},
        {"label": "m", "unit": "month"},
        {"label": "w", "unit": "week"},
        {"label": "d", "unit": "date"},
    ]
    config.gantt_bottom_time_bands = [
        {"label": "m2", "unit": "month"},
        {"label": "d2", "unit": "date"},
    ]

    renderer = GanttRenderer()
    renderer._populate_tokens(config)
    start, end = date(2026, 3, 1), date(2026, 4, 30)
    days = visible_days(start, end, int(config.weekend_style))
    segments = renderer._build_all_segments(config, start, end, days, None)

    assert [key for key in segments if key[0] == "top"] == [
        ("top", 0), ("top", 1), ("top", 2), ("top", 3)
    ]
    assert [key for key in segments if key[0] == "bottom"] == [
        ("bottom", 0), ("bottom", 1)
    ]
    assert all(segments[key] for key in segments), "every band produced segments"


@pytest.mark.parametrize("count", [1, 3, 6])
def test_the_renderer_draws_a_row_for_every_band(count):
    """Band cells are drawn per segment, so more bands means more cells."""
    single = render(
        [task()],
        gantt_top_time_bands=[{"label": "m", "unit": "month", "row_height": 8}],
        gantt_bottom_time_bands=[],
    )
    many = render(
        [task()],
        gantt_top_time_bands=[
            {"label": f"m{i}", "unit": "month", "row_height": 8} for i in range(count)
        ],
        gantt_bottom_time_bands=[],
    )
    one_row = len(single.of_class(single.rects, "ec-band-cell"))
    assert len(many.of_class(many.rects, "ec-band-cell")) == one_row * count


def test_top_and_bottom_stacks_both_draw():
    renderer = render(
        [task()],
        gantt_top_time_bands=[{"label": "m", "unit": "month", "row_height": 8}],
        gantt_bottom_time_bands=[
            {"label": "w", "unit": "week", "row_height": 8},
            {"label": "d", "unit": "date", "row_height": 8},
        ],
    )
    cells = renderer.of_class(renderer.rects, "ec-band-cell")
    assert cells

    # Three distinct band rows means three distinct y positions.
    assert len({round(cell["y"], 2) for cell in cells}) == 3
