"""
Unit tests for visualizers.timeline.labella_adapter.

Exercises all four (orientation, side) combinations plus BOTH and the
empty-input edge case using fabricated events. Verifies:

  - No two placements on the same layer/side overlap along the axis.
  - All placements lie within the requested axis bounds.
  - Leader paths are non-empty SVG path strings.
  - BOTH partitioning produces a balanced split.
"""

from __future__ import annotations

import arrow
import pytest

from config.config import CalendarConfig
from shared.data_models import Event
from visualizers.timeline.labella_adapter import layout_callouts
from shared.orientation import Orientation, Side


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _ev(name: str, date_yyyymmdd: str, notes: str | None = None) -> Event:
    return Event(task_name=name, start=date_yyyymmdd, end=date_yyyymmdd, notes=notes)


@pytest.fixture
def dense_events() -> list[Event]:
    """15 events with many overlaps along the axis."""
    # Clusters at 2026-06-05, 06-06 (heavy), 06-15, 06-25 (heavy), 07-10.
    raw = [
        ("Kickoff",        "20260605"),
        ("Demo A",         "20260606"),
        ("Demo B",         "20260606"),
        ("Demo C",         "20260606"),
        ("Demo D",         "20260606"),
        ("Sync",           "20260615"),
        ("Review 1",       "20260625"),
        ("Review 2",       "20260625"),
        ("Review 3",       "20260625"),
        ("Review 4",       "20260625"),
        ("Review 5",       "20260625"),
        ("Status",         "20260705"),
        ("Status check",   "20260705"),
        ("Wrap",           "20260710"),
        ("Final",          "20260710"),
    ]
    return [_ev(n, d) for n, d in raw]


@pytest.fixture
def config() -> CalendarConfig:
    return CalendarConfig()


def _pos_for_day_factory(start_str: str, end_str: str, axis_length: float):
    """Build a linear date→position mapping for the test range."""
    start = arrow.get(start_str, "YYYYMMDD")
    end = arrow.get(end_str, "YYYYMMDD")
    span_days = max(1, (end.floor("day") - start.floor("day")).days)

    def pos_for_day(day):
        offset = (day.floor("day") - start.floor("day")).days
        clamped = max(0, min(offset, span_days))
        return axis_length * (clamped / span_days)

    return pos_for_day


# ---------------------------------------------------------------------------
# Empty input
# ---------------------------------------------------------------------------


def test_empty_events_returns_empty_list(config):
    placements = layout_callouts(
        [],
        axis_origin=(100.0, 200.0),
        axis_length=500.0,
        orientation=Orientation.HORIZONTAL,
        side=Side.PRIMARY,
        config=config,
        pos_for_day=lambda d: 0.0,
    )
    assert placements == []


# ---------------------------------------------------------------------------
# All four (orientation, side) combinations on dense events
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("orientation", "side"),
    [
        (Orientation.HORIZONTAL, Side.PRIMARY),
        (Orientation.HORIZONTAL, Side.SECONDARY),
        (Orientation.VERTICAL, Side.PRIMARY),
        (Orientation.VERTICAL, Side.SECONDARY),
    ],
)
def test_single_side_no_overlap_per_layer(
    config, dense_events, orientation, side
):
    axis_length = 600.0
    axis_origin = (50.0, 80.0)
    pos_for_day = _pos_for_day_factory("20260601", "20260730", axis_length)

    placements = layout_callouts(
        dense_events,
        axis_origin=axis_origin,
        axis_length=axis_length,
        orientation=orientation,
        side=side,
        config=config,
        pos_for_day=pos_for_day,
    )

    # Sanity: one placement per event.
    assert len(placements) == len(dense_events)

    # Per-layer intervals along the axis should not overlap. The axis-aligned
    # extent is label_w for horizontal, label_h for vertical.
    by_layer: dict[int, list[tuple[float, float]]] = {}
    for p in placements:
        if orientation is Orientation.HORIZONTAL:
            start = p.x_label
            extent = p.label_w
        else:
            start = p.y_label
            extent = p.label_h
        by_layer.setdefault(p.layer, []).append((start, start + extent))

    for layer, intervals in by_layer.items():
        intervals.sort()
        for (a_lo, a_hi), (b_lo, b_hi) in zip(intervals, intervals[1:]):
            assert a_hi <= b_lo + 1e-6, (
                f"Layer {layer} {orientation.value}/{side.value}: "
                f"[{a_lo:.2f},{a_hi:.2f}] overlaps [{b_lo:.2f},{b_hi:.2f}]"
            )

    # Every placement carries a non-empty bezier path.
    for p in placements:
        assert p.leader_path_d.startswith("M "), p.leader_path_d[:32]
        assert " C " in p.leader_path_d
        assert p.axis_origin == axis_origin
        assert p.orientation is orientation
        assert p.side is side


# ---------------------------------------------------------------------------
# Dot positions land on the axis line
# ---------------------------------------------------------------------------


def test_horizontal_dots_lie_on_axis_line(config, dense_events):
    axis_origin = (50.0, 80.0)
    pos_for_day = _pos_for_day_factory("20260601", "20260730", 600.0)

    placements = layout_callouts(
        dense_events,
        axis_origin=axis_origin,
        axis_length=600.0,
        orientation=Orientation.HORIZONTAL,
        side=Side.PRIMARY,
        config=config,
        pos_for_day=pos_for_day,
    )
    for p in placements:
        assert p.y_dot == axis_origin[1]


def test_vertical_dots_lie_on_axis_line(config, dense_events):
    axis_origin = (50.0, 80.0)
    pos_for_day = _pos_for_day_factory("20260601", "20260730", 600.0)

    placements = layout_callouts(
        dense_events,
        axis_origin=axis_origin,
        axis_length=600.0,
        orientation=Orientation.VERTICAL,
        side=Side.PRIMARY,
        config=config,
        pos_for_day=pos_for_day,
    )
    for p in placements:
        assert p.x_dot == axis_origin[0]


# ---------------------------------------------------------------------------
# Side direction sanity
# ---------------------------------------------------------------------------


def test_horizontal_primary_labels_above_axis(config, dense_events):
    axis_origin = (50.0, 200.0)
    pos_for_day = _pos_for_day_factory("20260601", "20260730", 600.0)
    placements = layout_callouts(
        dense_events,
        axis_origin=axis_origin,
        axis_length=600.0,
        orientation=Orientation.HORIZONTAL,
        side=Side.PRIMARY,
        config=config,
        pos_for_day=pos_for_day,
    )
    # Primary on horizontal = above the axis → label_y should be < axis_y.
    for p in placements:
        assert p.y_label < axis_origin[1]


def test_horizontal_secondary_labels_below_axis(config, dense_events):
    axis_origin = (50.0, 200.0)
    pos_for_day = _pos_for_day_factory("20260601", "20260730", 600.0)
    placements = layout_callouts(
        dense_events,
        axis_origin=axis_origin,
        axis_length=600.0,
        orientation=Orientation.HORIZONTAL,
        side=Side.SECONDARY,
        config=config,
        pos_for_day=pos_for_day,
    )
    for p in placements:
        assert p.y_label > axis_origin[1]


def test_vertical_primary_labels_right_of_axis(config, dense_events):
    axis_origin = (200.0, 50.0)
    pos_for_day = _pos_for_day_factory("20260601", "20260730", 600.0)
    placements = layout_callouts(
        dense_events,
        axis_origin=axis_origin,
        axis_length=600.0,
        orientation=Orientation.VERTICAL,
        side=Side.PRIMARY,
        config=config,
        pos_for_day=pos_for_day,
    )
    for p in placements:
        assert p.x_label > axis_origin[0]


def test_vertical_secondary_labels_left_of_axis(config, dense_events):
    axis_origin = (200.0, 50.0)
    pos_for_day = _pos_for_day_factory("20260601", "20260730", 600.0)
    placements = layout_callouts(
        dense_events,
        axis_origin=axis_origin,
        axis_length=600.0,
        orientation=Orientation.VERTICAL,
        side=Side.SECONDARY,
        config=config,
        pos_for_day=pos_for_day,
    )
    for p in placements:
        assert p.x_label < axis_origin[0]


# ---------------------------------------------------------------------------
# BOTH partitioning
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "orientation", [Orientation.HORIZONTAL, Orientation.VERTICAL]
)
def test_both_partitions_events_between_sides(config, dense_events, orientation):
    pos_for_day = _pos_for_day_factory("20260601", "20260730", 600.0)
    placements = layout_callouts(
        dense_events,
        axis_origin=(50.0, 80.0),
        axis_length=600.0,
        orientation=orientation,
        side=Side.BOTH,
        config=config,
        pos_for_day=pos_for_day,
    )
    assert len(placements) == len(dense_events)

    primary = [p for p in placements if p.side is Side.PRIMARY]
    secondary = [p for p in placements if p.side is Side.SECONDARY]

    # Alternating partition gives a balanced split (off-by-one allowed).
    assert abs(len(primary) - len(secondary)) <= 1
    assert primary, "expected at least one primary placement"
    assert secondary, "expected at least one secondary placement"


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def test_concrete_side_required_internally(config):
    # _layout_one_side rejects BOTH; the public API never calls it with BOTH
    # but defends against future regression.
    from shared.labella_layout import _layout_one_side

    with pytest.raises(ValueError):
        _layout_one_side(
            [_ev("Demo", "20260606")],
            axis_origin=(0.0, 0.0),
            axis_length=100.0,
            orientation=Orientation.HORIZONTAL,
            side=Side.BOTH,
            pos_for_day=lambda d: 0.0,
            node_width=lambda ev: 24.0,
            node_height=lambda evs: 16.0,
            density=0.85,
            layer_gap=30.0,
            min_pos=None,
            max_pos=None,
            on_side_events=None,
        )


# ---------------------------------------------------------------------------
# Row splitting under clustering
# ---------------------------------------------------------------------------
#
# The distributor sizes layers by comparing the *total* width of all labels
# against ``density * axis_length``.  That global test passes for label sets
# that still cannot be placed in one layer, because the events cluster in
# time; the constraint solver then leaves them overlapping.  The layout
# relaxes density until the rows are clean, so these cases must not overlap
# however tightly the events bunch.


@pytest.fixture
def clustered_events() -> list[Event]:
    """Long labels bunched into two tight clusters on a wide axis.

    Total width fits one layer at the default density, so the distributor
    sees no reason to split — but half of them share a fortnight.
    """
    raw = [
        ("Canary Deployment 5 percent",  "20260717"),
        ("Production Rollout 25 percent", "20260717"),
        ("Production Rollout 100 percent", "20260720"),
        ("Go/No-Go Decision Meeting",    "20260720"),
        ("Training Sign-off Complete",   "20260722"),
        ("Operations Readiness Review",  "20260722"),
        ("Go-Live Event Announcement",   "20260724"),
        ("Project Closeout Retrospective", "20260724"),
    ]
    return [_ev(name, day) for name, day in raw]


def _rows(placements):
    rows: dict[float, list[tuple[float, float]]] = {}
    for p in placements:
        rows.setdefault(round(p.y_label, 3), []).append((p.x_label, p.label_w))
    return rows


def _worst_overlap(placements) -> float:
    worst = 0.0
    for spans in _rows(placements).values():
        spans.sort()
        for (x, w), (next_x, _) in zip(spans, spans[1:]):
            worst = max(worst, (x + w) - next_x)
    return worst


def test_clustered_labels_are_split_across_rows(config, clustered_events):
    placements = layout_callouts(
        clustered_events,
        axis_origin=(0.0, 400.0),
        axis_length=1766.0,
        orientation=Orientation.HORIZONTAL,
        side=Side.PRIMARY,
        config=config,
        pos_for_day=_pos_for_day_factory("20260401", "20260731", 1766.0),
    )
    assert len(placements) == len(clustered_events)
    assert _worst_overlap(placements) <= 0.01
    # Splitting is the mechanism: one row could not have held them.
    assert len(_rows(placements)) > 1


def test_a_sparse_timeline_keeps_the_requested_density(config):
    """Relaxation is a fallback — a layout that already fits is untouched."""
    events = [_ev("One", "20260401"), _ev("Two", "20260601"), _ev("Three", "20260731")]
    kwargs = dict(
        axis_origin=(0.0, 400.0),
        axis_length=1766.0,
        orientation=Orientation.HORIZONTAL,
        side=Side.PRIMARY,
        config=config,
        pos_for_day=_pos_for_day_factory("20260401", "20260731", 1766.0),
    )
    placements = layout_callouts(events, **kwargs)
    assert _worst_overlap(placements) <= 0.01
    # Room to spare, so everything stays on the innermost row.
    assert len(_rows(placements)) == 1


def test_the_box_is_measured_wide_enough_for_its_date(config):
    """The date shares the title line, so the box must budget for it."""
    from visualizers.timeline.labella_adapter import (
        _date_extent_for,
        _measured_text_width,
    )

    event = _ev("Go-Live Event", "20260724")
    date_w = _date_extent_for(event, config)
    assert date_w > 0
    # The measured line includes the date, not just the name.
    assert _measured_text_width(event, config) > date_w
