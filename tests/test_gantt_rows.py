"""Gantt row model: WBS ordering, the no-WBS block, and indentation."""

from __future__ import annotations

import pytest

from config.config import CalendarConfig
from shared.data_models import Event
from visualizers.gantt.rows import build_rows, wbs_depth, wbs_sort_key


def event(name: str, wbs: str | None = None, start: str = "20260202") -> Event:
    return Event(task_name=name, start=start, end=start, wbs=wbs)


@pytest.fixture
def config() -> CalendarConfig:
    return CalendarConfig()


# ── WBS ordering ──────────────────────────────────────────────────────────


def test_wbs_segments_compare_numerically_not_lexically(config):
    """The ordering plain string comparison gets wrong: 1.9 before 1.10."""
    rows = build_rows(
        [event("nine", "1.9"), event("ten", "1.10"), event("two", "1.2")], config
    )
    assert [row.event.task_name for row in rows] == ["two", "nine", "ten"]


def test_deep_hierarchies_order_by_each_segment(config):
    codes = ["1.10.1", "1.2", "1.2.10", "1.2.2", "1", "2"]
    rows = build_rows([event(code, code) for code in codes], config)
    assert [row.event.task_name for row in rows] == [
        "1", "1.2", "1.2.2", "1.2.10", "1.10.1", "2",
    ]


def test_alphanumeric_segments_stay_deterministic(config):
    codes = ["NP.2", "NP.10", "NP.1", "NP"]
    rows = build_rows([event(code, code) for code in codes], config)
    assert [row.event.task_name for row in rows] == ["NP", "NP.1", "NP.2", "NP.10"]


def test_numeric_segments_sort_before_text_segments():
    assert wbs_sort_key("1.2") < wbs_sort_key("1.B")


# ── The no-WBS block ──────────────────────────────────────────────────────


def test_rows_without_wbs_follow_every_wbs_row(config):
    rows = build_rows(
        [
            event("loose early", None, "20260101"),
            event("numbered", "9.9", "20260601"),
            event("loose late", "", "20260301"),
        ],
        config,
    )
    assert [row.event.task_name for row in rows] == [
        "numbered", "loose early", "loose late",
    ]


def test_the_no_wbs_block_is_ordered_by_start_date(config):
    rows = build_rows(
        [
            event("march", None, "20260301"),
            event("january", None, "20260101"),
            event("february", None, "20260201"),
        ],
        config,
    )
    assert [row.event.task_name for row in rows] == ["january", "february", "march"]


# ── Indentation ───────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "wbs,expected",
    [(None, 0), ("", 0), ("1", 0), ("1.2", 1), ("1.2.3", 2), ("NP.3.S1", 2)],
)
def test_depth_counts_wbs_segments(wbs, expected):
    assert wbs_depth(wbs) == expected


def test_rows_carry_their_depth_and_order(config):
    rows = build_rows(
        [event("child", "1.1"), event("parent", "1"), event("loose")], config
    )
    assert [(row.event.task_name, row.depth, row.index) for row in rows] == [
        ("parent", 0, 0),
        ("child", 1, 1),
        ("loose", 0, 2),
    ]


# ── Inputs and configuration ──────────────────────────────────────────────


def test_accepts_database_dicts_as_well_as_events(config):
    rows = build_rows(
        [{"Task_Name": "from dict", "Start": "20260202", "End": "20260202",
          "WBS": "1.1"}],
        config,
    )
    assert rows[0].event.task_name == "from dict"
    assert rows[0].depth == 1


def test_an_unknown_sort_field_is_ignored(config):
    """A theme typo should degrade to a stable order, not raise."""
    config.gantt_sort = ["wbs", "not_a_field", "start_date"]
    rows = build_rows([event("b", "1.2"), event("a", "1.1")], config)
    assert [row.event.task_name for row in rows] == ["a", "b"]


def test_sorting_tolerates_mixed_types_in_one_field(config):
    """priority is NUMERIC in SQLite, so a column can hold ints and text."""
    config.gantt_sort = ["priority"]
    events = [
        Event(task_name="text", start="20260202", end="20260202", priority="high"),
        Event(task_name="number", start="20260202", end="20260202", priority=2),
    ]
    assert [row.event.task_name for row in build_rows(events, config)] == [
        "number", "text",
    ]


def test_no_rows_when_there_are_no_events(config):
    assert build_rows([], config) == []
