"""Gantt column model: resolution, widths, value formatting, wrap/truncate."""

from __future__ import annotations

import pytest

from config.config import CalendarConfig
from shared.data_models import Event
from visualizers.gantt.columns import (
    ELLIPSIS,
    cell_icon_visible,
    cell_value,
    column_x_positions,
    fit_lines,
    resolve_columns,
)


#: One unit of width per character — keeps wrap assertions exact.
def measure(text: str) -> float:
    return float(len(text))


def column(**overrides) -> CalendarConfig:
    """A config whose gantt_columns is exactly the given entries."""
    config = CalendarConfig()
    config.gantt_columns = overrides["entries"]
    return config


# ── Resolution ────────────────────────────────────────────────────────────


def test_default_widths_sum_to_one():
    """Widths renormalize, so defaults that do not sum to 1 silently shrink."""
    total = sum(col["width"] for col in CalendarConfig().gantt_columns)
    assert total == pytest.approx(1.0)


def test_widths_are_renormalized():
    config = column(entries=[
        {"field": "name", "width": 3},
        {"field": "wbs", "width": 1},
    ])
    widths = [col.width for col in resolve_columns(config)]
    assert widths == pytest.approx([0.75, 0.25])


def test_unsized_columns_take_the_average_of_the_sized_ones():
    config = column(entries=[
        {"field": "name", "width": 2},
        {"field": "wbs", "width": 2},
        {"field": "notes"},
    ])
    widths = [col.width for col in resolve_columns(config)]
    assert widths == pytest.approx([1 / 3, 1 / 3, 1 / 3])
    assert sum(widths) == pytest.approx(1.0)


def test_columns_without_a_field_are_dropped():
    config = column(entries=[
        {"field": "name", "width": 1},
        {"header": "Oops", "width": 1},
        "not a dict",
    ])
    assert [col.field for col in resolve_columns(config)] == ["name"]


def test_header_defaults_to_the_field_name():
    config = column(entries=[{"field": "wbs", "width": 1}])
    assert resolve_columns(config)[0].header == "wbs"


@pytest.mark.parametrize(
    "field,expected_attr",
    [
        ("name", "task_name"),
        ("start_date", "start"),
        ("end_date", "end"),
        ("finish", "end"),
        ("wbs", "wbs"),               # no alias needed
        ("percent_complete", "percent_complete"),
    ],
)
def test_table_column_names_resolve_to_event_attributes(field, expected_attr):
    """Themes name columns after the events table, not the Event dataclass."""
    config = column(entries=[{"field": field, "width": 1}])
    resolved = resolve_columns(config)[0]
    assert resolved.field == field
    assert resolved.attr == expected_attr


def test_icon_columns_take_their_default_icon_from_config():
    config = column(entries=[
        {"field": "rollup", "width": 1, "render": "icon"},
        {"field": "milestone", "width": 1, "render": "icon"},
    ])
    icons = [col.icon for col in resolve_columns(config)]
    assert icons == [config.gantt_rollup_icon, config.gantt_milestone_flag_icon]


def test_explicit_icon_beats_the_default():
    config = column(entries=[
        {"field": "rollup", "width": 1, "render": "icon", "icon": "star"},
    ])
    assert resolve_columns(config)[0].icon == "star"


def test_column_x_positions_tile_the_table_width():
    config = column(entries=[
        {"field": "name", "width": 1},
        {"field": "wbs", "width": 1},
        {"field": "notes", "width": 2},
    ])
    positions = column_x_positions(resolve_columns(config), 100.0, 400.0)
    assert positions == [(100.0, 100.0), (200.0, 100.0), (300.0, 200.0)]


# ── Values ────────────────────────────────────────────────────────────────


@pytest.fixture
def event() -> Event:
    return Event(
        task_name="Ledger Migration",
        start="20260202",
        end="20260213",
        wbs="NP.1.1",
        percent_complete=0.35,
        rollup=False,
        milestone=True,
        duration_text="10 days",
    )


def test_date_columns_use_arrow_formats_including_dd(event):
    config = column(entries=[
        {"field": "start_date", "width": 1, "date_format": "dd MM/DD/YY"},
    ])
    assert cell_value(resolve_columns(config)[0], event) == "Mo 02/02/26"


def test_unparseable_date_passes_through(event):
    config = column(entries=[
        {"field": "duration_text", "width": 1, "date_format": "MM/DD/YY"},
    ])
    assert cell_value(resolve_columns(config)[0], event) == "10 days"


def test_format_spec_is_applied(event):
    config = column(entries=[
        {"field": "percent_complete", "width": 1, "format": "{:.0%}"},
    ])
    assert cell_value(resolve_columns(config)[0], event) == "35%"


def test_a_format_spec_that_does_not_fit_costs_only_the_formatting(event):
    config = column(entries=[
        {"field": "task_name", "width": 1, "format": "{:.0%}"},
    ])
    assert cell_value(resolve_columns(config)[0], event) == "Ledger Migration"


def test_missing_values_render_empty(event):
    config = column(entries=[{"field": "notes", "width": 1}])
    assert cell_value(resolve_columns(config)[0], event) == ""


def test_icon_columns_have_no_text_but_report_visibility(event):
    config = column(entries=[
        {"field": "milestone", "width": 1, "render": "icon"},
        {"field": "rollup", "width": 1, "render": "icon"},
    ])
    milestone, rollup = resolve_columns(config)
    assert cell_value(milestone, event) == ""
    assert cell_icon_visible(milestone, event) is True
    assert cell_icon_visible(rollup, event) is False


# ── Wrapping and truncation ───────────────────────────────────────────────


def test_text_that_fits_is_one_line():
    assert fit_lines("short", 10.0, 2, measure) == ["short"]


def test_text_wraps_at_word_boundaries():
    assert fit_lines("alpha beta gamma", 11.0, 2, measure) == ["alpha beta", "gamma"]


def test_overflow_past_max_lines_gets_an_ellipsis():
    """The ellipsis counts toward the width, so the last word loses a char."""
    lines = fit_lines("alpha beta gamma delta epsilon", 11.0, 2, measure)
    assert lines == ["alpha beta", "gamma delt" + ELLIPSIS]
    assert all(measure(line) <= 11.0 for line in lines)


def test_single_line_columns_truncate_rather_than_wrap():
    """One line takes as many whole words as fit, then an ellipsis."""
    assert fit_lines("alpha beta gamma", 11.0, 1, measure) == ["alpha beta" + ELLIPSIS]
    # Tighter column: the second word no longer fits at all.
    assert fit_lines("alpha beta gamma", 6.0, 1, measure) == ["alpha" + ELLIPSIS]


def test_a_word_wider_than_the_column_is_broken_not_overflowed():
    lines = fit_lines("supercalifragilistic", 5.0, 2, measure)
    assert all(measure(line) <= 5.0 for line in lines)
    assert lines[0] == "super"


def test_empty_and_degenerate_inputs():
    assert fit_lines("", 10.0, 2, measure) == []
    assert fit_lines("   ", 10.0, 2, measure) == []
    assert fit_lines("text", 0.0, 2, measure) == []
    assert fit_lines("text", 10.0, 0, measure) == []


def test_ellipsis_alone_when_nothing_fits():
    assert fit_lines("wide", 1.0, 1, measure) == [ELLIPSIS]
