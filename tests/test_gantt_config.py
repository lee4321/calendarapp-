"""Gantt configuration and theme wiring (phase 2).

Covers the parts that must be right before any drawing happens: the
config defaults, the `gantt:` theme section reaching those fields, the
bottom-band mirror, CLI registration, and the page frame the layout
produces.
"""

from __future__ import annotations

import pytest
from band_helpers import set_fields

from config.config import CalendarConfig
from config.theme_loader import load_theme
from visualizers.factory import VisualizerFactory
from visualizers.gantt.layout import GanttLayout

#: Letter landscape in points.  A bare CalendarConfig has a zero-sized page
#: (paper dimensions are loaded from the database at runtime), so any test
#: that measures geometry has to set one.
_PAGE = (792.0, 612.0)


@pytest.fixture
def themed_config() -> CalendarConfig:
    config = CalendarConfig()
    config.pageX, config.pageY = _PAGE
    config.theme_v3 = load_theme("default")
    return config


# ── Defaults ──────────────────────────────────────────────────────────────


def test_default_columns_match_the_documented_set():
    fields = [col.field for col in CalendarConfig().theme_v3.gantt.columns]
    assert fields == [
        "link_ref",
        "source_id",
        "name",
        "status",
        "priority",
        "wbs",
        "rollup",
        "milestone",
        "percent_complete",
        "effort_text",
        "duration_text",
        "start_date",
        "end_date",
        "resource_names",
        "resource_group",
        "notes",
        "deadline",
    ]


def test_the_reference_column_leads_the_table():
    """Cross-page dependency numbers sit before the ID column."""
    first = CalendarConfig().theme_v3.gantt.columns[0]
    assert first.field == "link_ref"
    assert first.render == "icon"


def test_text_variants_are_used_for_duration_and_effort():
    """The REAL columns are for arithmetic; the table shows what was imported."""
    fields = {col.field for col in CalendarConfig().theme_v3.gantt.columns}
    assert "duration_text" in fields and "duration" not in fields
    assert "effort_text" in fields and "effort" not in fields


def test_icon_defaults():
    config = CalendarConfig()
    marks = config.theme_v3.gantt.marks
    assert marks.milestone == "diamond-fill"
    assert marks.deadline == "square-fill"
    assert marks.rollup == "check"
    assert marks.milestone_flag == "check"
    assert marks.snapped_event == "arrow-left-circle"
    assert marks.offchart_dependency == "crosssquare"


def test_today_comes_from_the_shared_theme_block():
    today = CalendarConfig().theme_v3.today
    assert today.show is True
    assert today.date is None


# ── Band stacks ───────────────────────────────────────────────────────────


def test_the_default_theme_declares_both_band_stacks():
    """Both stacks come from the version-3.0 default theme: the same rows for every view."""
    scale = load_theme("default").timescale
    assert [row.unit for row in scale.primary] == ["fiscal_quarter", "fiscal_period", "month", "dow", "date", "holiday"]
    assert [row.height for row in scale.primary] == [12, 12, 12, 10, 10, 10]
    assert [row.unit for row in scale.secondary] == [
        "holiday",
        "date",
        "dow",
        "month",
        "fiscal_period",
        "fiscal_quarter",
    ]


# ── Theme section ─────────────────────────────────────────────────────────


def test_theme_gantt_section_reaches_config(themed_config):
    assert themed_config.theme_v3.gantt.table_width_ratio == 0.38
    assert themed_config.theme_v3.gantt.row_height == 14.0
    assert themed_config.theme_v3.gantt.indent_per_level == 5.0
    assert themed_config.theme_v3.events.item_placement_order == ["wbs", "start_date"]


def test_theme_columns_carry_their_layout_keys(themed_config):
    by_field = {col.field: col for col in themed_config.theme_v3.gantt.columns}
    assert by_field["name"].indent is True
    assert by_field["name"].max_lines == 2
    assert by_field["start_date"].date_format == "dd MM/DD"
    assert by_field["percent_complete"].align == "end"


# ── Registration ──────────────────────────────────────────────────────────


def test_factory_creates_the_gantt_visualizer():
    visualizer = VisualizerFactory.create("gantt")
    assert visualizer.name == "gantt"


def test_cli_registers_the_gantt_subcommand():
    from cli.args import _create_argument_parser

    parser = _create_argument_parser("out.svg")
    args = parser.parse_args(["gantt", "20260907", "20261231", "--WBS", "1"])
    assert args.command == "gantt"
    assert args.WBS == "1"


def test_gantt_accepts_the_shared_content_filters():
    from cli.args import _create_argument_parser

    parser = _create_argument_parser("out.svg")
    args = parser.parse_args(
        ["gantt", "20260907", "20261231", "--milestones", "--status", "all", "--weekends", "1", "--includenotes"]
    )
    assert args.milestones is True
    assert args.weekends == 1


# ── Layout frame ──────────────────────────────────────────────────────────


def test_layout_splits_table_and_chart_by_ratio(themed_config):
    coords = GanttLayout().calculate(themed_config)
    _ax, _ay, area_w, _ah = coords["GanttArea"]
    assert area_w > 0  # guards against a zero-page false pass
    _tx, _ty, table_w, _th = coords["GanttTableArea"]
    chart_x, _cy, chart_w, _ch = coords["GanttChartArea"]

    assert table_w == pytest.approx(area_w * themed_config.theme_v3.gantt.table_width_ratio, abs=0.01)
    assert table_w + chart_w == pytest.approx(area_w, abs=0.01)
    assert chart_x == pytest.approx(coords["GanttArea"][0] + table_w, abs=0.01)


@pytest.mark.parametrize("ratio", [-1.0, 0.0, 1.0, 5.0])
def test_layout_clamps_an_out_of_range_ratio(ratio):
    """Both areas must keep positive width whatever the theme asks for."""
    config = CalendarConfig()
    config.pageX, config.pageY = _PAGE
    set_fields(config, gantt_table_width_ratio=ratio)
    coords = GanttLayout().calculate(config)
    assert coords["GanttTableArea"][2] > 0
    assert coords["GanttChartArea"][2] > 0
