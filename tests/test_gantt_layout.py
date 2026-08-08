"""Gantt page geometry: the table/chart split and the vertical band stack."""

from __future__ import annotations

import pytest

from config.config import CalendarConfig
from visualizers.gantt.layout import GanttLayout

#: Letter landscape in points; a bare CalendarConfig has a zero-sized page.
_PAGE = (792.0, 612.0)


@pytest.fixture
def config() -> CalendarConfig:
    config = CalendarConfig()
    config.pageX, config.pageY = _PAGE
    return config


def regions(config: CalendarConfig) -> dict:
    return GanttLayout().calculate(config)


# ── Horizontal split ──────────────────────────────────────────────────────


def test_table_and_chart_tile_the_content_width(config):
    coords = regions(config)
    area_x, _ay, area_w, _ah = coords["GanttArea"]
    table_x, _ty, table_w, _th = coords["GanttTableArea"]
    chart_x, _cy, chart_w, _ch = coords["GanttChartArea"]

    assert table_x == area_x
    assert chart_x == pytest.approx(area_x + table_w, abs=0.01)
    assert table_w + chart_w == pytest.approx(area_w, abs=0.01)


def test_bodies_inherit_their_columns_horizontal_extent(config):
    coords = regions(config)
    assert coords["GanttTableBody"][0] == coords["GanttTableArea"][0]
    assert coords["GanttTableBody"][2] == coords["GanttTableArea"][2]
    assert coords["GanttChartBody"][0] == coords["GanttChartArea"][0]
    assert coords["GanttChartBody"][2] == coords["GanttChartArea"][2]


# ── Vertical split (SVG space: y is the top edge, growing downward) ────────


def test_bands_headers_and_body_stack_without_overlap(config):
    coords = regions(config)
    top_y, top_h = coords["GanttTopBands"][1], coords["GanttTopBands"][3]
    head_y, head_h = coords["GanttColumnHeader"][1], coords["GanttColumnHeader"][3]
    body_y, body_h = coords["GanttChartBody"][1], coords["GanttChartBody"][3]
    bottom_y = coords["GanttBottomBands"][1]

    assert top_y + top_h == pytest.approx(head_y, abs=0.01)
    assert head_y + head_h == pytest.approx(body_y, abs=0.01)
    assert body_y + body_h == pytest.approx(bottom_y, abs=0.01)


def test_band_heights_come_from_the_band_definitions(config):
    config.gantt_top_time_bands = [
        {"label": "Month", "unit": "month", "row_height": 20},
        {"label": "Week", "unit": "week", "row_height": 10},
    ]
    assert regions(config)["GanttTopBands"][3] == pytest.approx(30.0, abs=0.01)


def test_a_band_without_a_row_height_uses_the_config_default(config):
    config.gantt_band_row_height = 12.0
    config.gantt_top_time_bands = [{"label": "Month", "unit": "month"}]
    assert regions(config)["GanttTopBands"][3] == pytest.approx(12.0, abs=0.01)


def test_the_bottom_stack_mirrors_the_top_when_unset(config):
    config.gantt_top_time_bands = [
        {"label": "Month", "unit": "month", "row_height": 20},
    ]
    coords = regions(config)
    assert coords["GanttBottomBands"][3] == pytest.approx(
        coords["GanttTopBands"][3], abs=0.01
    )


def test_explicit_bottom_bands_size_independently(config):
    config.gantt_top_time_bands = [{"label": "Month", "unit": "month", "row_height": 20}]
    config.gantt_bottom_time_bands = [{"label": "Week", "unit": "week", "row_height": 6}]
    coords = regions(config)
    assert coords["GanttTopBands"][3] == pytest.approx(20.0, abs=0.01)
    assert coords["GanttBottomBands"][3] == pytest.approx(6.0, abs=0.01)


def test_column_header_height_comes_from_config(config):
    config.gantt_header_row_height = 24.0
    assert regions(config)["GanttColumnHeader"][3] == pytest.approx(24.0, abs=0.01)


# ── Degenerate configurations ─────────────────────────────────────────────


def test_oversized_chrome_is_capped_so_the_body_survives(config):
    """A theme asking for more chrome than the page has must still leave rows."""
    config.gantt_header_row_height = 400.0
    config.gantt_top_time_bands = [{"label": "A", "unit": "month", "row_height": 400}]
    config.gantt_bottom_time_bands = [{"label": "B", "unit": "week", "row_height": 400}]

    coords = regions(config)
    assert coords["GanttChartBody"][3] > 0
    assert coords["GanttTableBody"][3] > 0


def test_no_bands_leaves_the_body_the_whole_height(config):
    config.gantt_top_time_bands = []
    config.gantt_bottom_time_bands = []
    config.gantt_header_row_height = 0.0
    coords = regions(config)
    assert coords["GanttChartBody"][3] == pytest.approx(coords["GanttArea"][3], abs=0.01)


def test_header_and_footer_shrink_the_gantt_area(config):
    config.include_header = False
    config.include_footer = False
    bare = regions(config)["GanttArea"][3]

    config.include_header = True
    config.include_footer = True
    assert regions(config)["GanttArea"][3] < bare
