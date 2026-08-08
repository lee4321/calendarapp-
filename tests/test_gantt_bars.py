"""Gantt bar geometry: placement, clipping, snapping, progress and float."""

from __future__ import annotations

from datetime import date

import pytest

from shared.data_models import Event
from shared.date_utils import visible_days
from visualizers.gantt.bars import (
    DayAxis,
    bar_geometry,
    float_spans,
    progress_width,
)

#: Mon 2 Feb 2026 through Fri 13 Feb 2026, workweek only: 10 columns of 10pt.
WORKWEEK = DayAxis(
    days=visible_days(date(2026, 2, 2), date(2026, 2, 15), 0), x=100.0, width=100.0
)

#: The same fortnight with every day shown: 14 columns.
ALL_DAYS = DayAxis(
    days=visible_days(date(2026, 2, 2), date(2026, 2, 15), 1), x=0.0, width=140.0
)


# ── The axis ──────────────────────────────────────────────────────────────


def test_workweek_axis_has_one_column_per_working_day():
    assert len(WORKWEEK.days) == 10
    assert WORKWEEK.day_width == pytest.approx(10.0)
    assert WORKWEEK.first == date(2026, 2, 2)
    assert WORKWEEK.last == date(2026, 2, 13)


def test_column_edges_and_centers():
    assert WORKWEEK.left_of(0) == pytest.approx(100.0)
    assert WORKWEEK.center_of(0) == pytest.approx(105.0)
    assert WORKWEEK.left_of(9) == pytest.approx(190.0)


def test_hidden_days_are_not_visible_but_snap_forward():
    saturday = date(2026, 2, 7)
    assert WORKWEEK.is_visible(saturday) is False
    # Monday the 9th is column 5 (Mon-Fri, then the next Monday).
    assert WORKWEEK.snap_forward(saturday) == 5
    assert ALL_DAYS.is_visible(saturday) is True


def test_snapping_past_the_end_has_no_column():
    assert WORKWEEK.snap_forward(date(2026, 3, 1)) is None


def test_an_empty_axis_has_no_width():
    assert DayAxis(days=[], x=0.0, width=100.0).day_width == 0.0


# ── Placement ─────────────────────────────────────────────────────────────


def test_a_span_inside_the_range_covers_its_columns():
    bar = bar_geometry(WORKWEEK, date(2026, 2, 3), date(2026, 2, 5))
    assert bar.visible is True
    assert bar.x == pytest.approx(110.0)
    assert bar.width == pytest.approx(30.0)
    assert (bar.clipped_start, bar.clipped_end, bar.snapped) == (False, False, False)


def test_a_span_crossing_a_hidden_weekend_covers_only_working_columns():
    """Mon 2nd - Mon 9th is 8 calendar days but 6 working columns."""
    bar = bar_geometry(WORKWEEK, date(2026, 2, 2), date(2026, 2, 9))
    assert bar.width == pytest.approx(60.0)


def test_the_same_span_covers_every_day_when_weekends_are_shown():
    bar = bar_geometry(ALL_DAYS, date(2026, 2, 2), date(2026, 2, 9))
    assert bar.width == pytest.approx(80.0)


def test_a_single_day_is_one_column_wide():
    bar = bar_geometry(WORKWEEK, date(2026, 2, 3), date(2026, 2, 3))
    assert bar.width == pytest.approx(10.0)


def test_a_reversed_span_is_put_back_in_order():
    forward = bar_geometry(WORKWEEK, date(2026, 2, 3), date(2026, 2, 5))
    backward = bar_geometry(WORKWEEK, date(2026, 2, 5), date(2026, 2, 3))
    assert backward == forward


# ── Clipping ──────────────────────────────────────────────────────────────


def test_a_span_starting_before_the_range_is_clipped_and_flagged():
    bar = bar_geometry(WORKWEEK, date(2026, 1, 1), date(2026, 2, 4))
    assert bar.clipped_start is True
    assert bar.clipped_end is False
    assert bar.x == pytest.approx(100.0)


def test_a_span_ending_after_the_range_is_clipped_and_flagged():
    bar = bar_geometry(WORKWEEK, date(2026, 2, 11), date(2026, 6, 1))
    assert bar.clipped_end is True
    assert bar.x + bar.width == pytest.approx(200.0)


def test_a_span_covering_everything_is_clipped_at_both_ends():
    bar = bar_geometry(WORKWEEK, date(2025, 1, 1), date(2027, 1, 1))
    assert (bar.clipped_start, bar.clipped_end) == (True, True)
    assert bar.width == pytest.approx(100.0)


@pytest.mark.parametrize(
    "start,end",
    [
        (date(2025, 1, 1), date(2025, 12, 31)),   # entirely before
        (date(2026, 3, 1), date(2026, 3, 31)),    # entirely after
    ],
)
def test_a_span_outside_the_range_is_invisible(start, end):
    assert bar_geometry(WORKWEEK, start, end).visible is False


def test_a_multi_day_span_entirely_inside_hidden_days_is_invisible():
    """Sat-Sun under weekend_style 0: no column, and no sensible placement."""
    bar = bar_geometry(WORKWEEK, date(2026, 2, 7), date(2026, 2, 8))
    assert bar.visible is False
    assert bar.snapped is True


def test_a_single_day_event_on_a_hidden_day_moves_to_the_next_working_day():
    """Answer 22: it is drawn on the following column, and flagged."""
    bar = bar_geometry(WORKWEEK, date(2026, 2, 7), date(2026, 2, 7))
    assert bar.visible is True
    assert bar.snapped is True
    assert bar.x == pytest.approx(WORKWEEK.left_of(5))
    assert bar.width == pytest.approx(WORKWEEK.day_width)


def test_a_single_day_event_after_the_last_visible_day_is_invisible():
    """Sat 14 Feb has no following column inside the range."""
    assert bar_geometry(WORKWEEK, date(2026, 2, 14), date(2026, 2, 14)).visible is False


def test_a_span_starting_on_a_hidden_day_snaps_forward():
    bar = bar_geometry(WORKWEEK, date(2026, 2, 7), date(2026, 2, 10))
    assert bar.visible is True
    assert bar.snapped is True
    assert bar.x == pytest.approx(WORKWEEK.left_of(5))


def test_clipping_at_the_start_is_not_reported_as_snapping():
    """A bar clipped to the first column has not been moved off its own day."""
    bar = bar_geometry(WORKWEEK, date(2026, 1, 1), date(2026, 2, 4))
    assert bar.snapped is False


def test_nothing_is_drawn_on_an_empty_axis():
    empty = DayAxis(days=[], x=0.0, width=100.0)
    assert bar_geometry(empty, date(2026, 2, 2), date(2026, 2, 3)).visible is False


# ── Progress ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "percent,expected",
    [(None, 0.0), (0.0, 0.0), (0.25, 7.5), (0.5, 15.0), (1.0, 30.0)],
)
def test_progress_is_a_fraction_of_the_drawn_bar(percent, expected):
    """The bar spans working columns, so this is the working-day span."""
    bar = bar_geometry(WORKWEEK, date(2026, 2, 3), date(2026, 2, 5))
    assert progress_width(bar, percent) == pytest.approx(expected)


def test_progress_is_clamped_to_the_bar():
    bar = bar_geometry(WORKWEEK, date(2026, 2, 3), date(2026, 2, 5))
    assert progress_width(bar, 1.5) == pytest.approx(bar.width)
    assert progress_width(bar, -1.0) == pytest.approx(0.0)


def test_an_invisible_bar_has_no_progress():
    bar = bar_geometry(WORKWEEK, date(2026, 3, 1), date(2026, 3, 2))
    assert progress_width(bar, 1.0) == 0.0


# ── Float windows ─────────────────────────────────────────────────────────


def test_all_four_float_windows_are_emitted_when_present():
    event = Event(
        task_name="t", start="20260210", end="20260213",
        earliest_start_date="20260205", latest_start_date="20260212",
        earliest_end_date="20260211", latest_end_date="20260220",
    )
    assert float_spans(event) == [
        ("earliest_start", "20260205", "20260210"),
        ("latest_start", "20260210", "20260212"),
        ("earliest_end", "20260211", "20260213"),
        ("latest_end", "20260213", "20260220"),
    ]


def test_no_float_windows_without_the_dates():
    """The common case: a schedule with no critical-path export."""
    event = Event(task_name="t", start="20260210", end="20260213")
    assert float_spans(event) == []


def test_partial_float_data_emits_only_what_is_present():
    event = Event(
        task_name="t", start="20260210", end="20260213",
        latest_end_date="20260220",
    )
    assert [name for name, _b, _f in float_spans(event)] == ["latest_end"]
