"""Gantt configuration and theme wiring (phase 2).

Covers the parts that must be right before any drawing happens: the
config defaults, the `gantt:` theme section reaching those fields, the
bottom-band mirror, CLI registration, and the page frame the layout
produces.
"""

from __future__ import annotations

import pytest

from config.config import CalendarConfig
from config.theme_engine import ThemeEngine
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
    engine = ThemeEngine()
    engine.load("default")
    engine.apply(config)
    return config


# ── Defaults ──────────────────────────────────────────────────────────────


def test_default_columns_match_the_documented_set():
    fields = [col["field"] for col in CalendarConfig().gantt_columns]
    assert fields == [
        "link_ref", "source_id", "name", "status", "priority", "wbs", "rollup",
        "milestone",
        "percent_complete", "effort_text", "duration_text", "start_date",
        "end_date", "resource_names", "resource_group", "notes", "deadline",
    ]


def test_the_reference_column_leads_the_table():
    """Cross-page dependency numbers sit before the ID column."""
    first = CalendarConfig().gantt_columns[0]
    assert first["field"] == "link_ref"
    assert first["render"] == "icon"


def test_text_variants_are_used_for_duration_and_effort():
    """The REAL columns are for arithmetic; the table shows what was imported."""
    fields = {col["field"] for col in CalendarConfig().gantt_columns}
    assert "duration_text" in fields and "duration" not in fields
    assert "effort_text" in fields and "effort" not in fields


def test_icon_defaults():
    config = CalendarConfig()
    assert config.gantt_milestone_icon == "diamond-fill"
    assert config.gantt_deadline_icon == "square-fill"
    assert config.gantt_rollup_icon == "check"
    assert config.gantt_milestone_flag_icon == "check"
    assert config.gantt_snapped_event_icon == "arrow-left-circle"
    assert config.gantt_offchart_dep_icon == "crosssquare"


def test_today_line_mirrors_pit_semantics():
    config = CalendarConfig()
    assert config.gantt_show_today_line is True
    assert config.gantt_today_date is None


# ── Bottom-band mirror ────────────────────────────────────────────────────


def test_bottom_bands_mirror_the_top_when_unset():
    config = CalendarConfig()
    assert config.gantt_bottom_time_bands is None
    mirrored = config.get_gantt_bottom_bands()
    assert mirrored == config.gantt_top_time_bands
    assert mirrored is not config.gantt_top_time_bands


def test_mirror_follows_the_theme_not_the_dataclass_default(themed_config):
    """The mirror has to be resolved after the theme applies, not at __init__."""
    top = themed_config.gantt_top_time_bands
    # default.yaml declares month / week / holiday, with these row heights —
    # the dataclass default carries no row_height at all, so matching these
    # proves the theme won.
    assert [band.get("row_height") for band in top] == [12, 10, 10]
    assert [band.get("unit") for band in top] == ["month", "week", "holiday"]
    assert themed_config.get_gantt_bottom_bands() == top


def test_explicit_bottom_bands_win_over_the_mirror():
    config = CalendarConfig()
    config.gantt_bottom_time_bands = [{"label": "Quarter", "unit": "fiscal_quarter"}]
    assert config.get_gantt_bottom_bands() == [
        {"label": "Quarter", "unit": "fiscal_quarter"}
    ]


def test_mirror_edits_cannot_leak_between_axes():
    config = CalendarConfig()
    config.get_gantt_bottom_bands()[0]["row_height"] = 99
    assert "row_height" not in config.gantt_top_time_bands[0]


# ── Theme section ─────────────────────────────────────────────────────────


def test_theme_gantt_section_reaches_config(themed_config):
    assert themed_config.gantt_table_width_ratio == 0.38
    assert themed_config.gantt_row_height == 14.0
    assert themed_config.gantt_indent_per_level == 8.0
    assert themed_config.gantt_sort == ["wbs", "start_date"]
    assert themed_config.gantt_progress_color == "black"


def test_theme_columns_carry_their_layout_keys(themed_config):
    by_field = {col["field"]: col for col in themed_config.gantt_columns}
    assert by_field["name"]["indent"] is True
    assert by_field["name"]["max_lines"] == 2
    assert by_field["rollup"]["render"] == "icon"
    assert by_field["start_date"]["date_format"] == "dd MM/DD/YY"
    assert by_field["percent_complete"]["align"] == "right"


def test_gantt_is_a_known_theme_section():
    """Both section registries must accept `gantt:` or every load warns."""
    from config.theme_engine import VALID_SECTIONS
    from config.unified_theme import VALID_SECTIONS as UNIFIED_SECTIONS

    assert "gantt" in VALID_SECTIONS
    assert "gantt" in UNIFIED_SECTIONS


def test_default_theme_parses_as_a_unified_theme(themed_config):
    """A theme carrying `gantt:` still builds a UnifiedTheme (not None)."""
    assert themed_config.theme is not None


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
        ["gantt", "20260907", "20261231", "--milestones", "--ignorecomplete",
         "--status", "all", "--weekends", "1", "--includenotes"]
    )
    assert args.milestones is True
    assert args.ignorecomplete is True
    assert args.weekends == 1


# ── Layout frame ──────────────────────────────────────────────────────────


def test_layout_splits_table_and_chart_by_ratio(themed_config):
    coords = GanttLayout().calculate(themed_config)
    _ax, _ay, area_w, _ah = coords["GanttArea"]
    assert area_w > 0  # guards against a zero-page false pass
    _tx, _ty, table_w, _th = coords["GanttTableArea"]
    chart_x, _cy, chart_w, _ch = coords["GanttChartArea"]

    assert table_w == pytest.approx(area_w * themed_config.gantt_table_width_ratio, abs=0.01)
    assert table_w + chart_w == pytest.approx(area_w, abs=0.01)
    assert chart_x == pytest.approx(coords["GanttArea"][0] + table_w, abs=0.01)


@pytest.mark.parametrize("ratio", [-1.0, 0.0, 1.0, 5.0])
def test_layout_clamps_an_out_of_range_ratio(ratio):
    """Both areas must keep positive width whatever the theme asks for."""
    config = CalendarConfig()
    config.pageX, config.pageY = _PAGE
    config.gantt_table_width_ratio = ratio
    coords = GanttLayout().calculate(config)
    assert coords["GanttTableArea"][2] > 0
    assert coords["GanttChartArea"][2] > 0
