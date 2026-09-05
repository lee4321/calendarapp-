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


# ── Leader length ─────────────────────────────────────────────────────────
#
# Two things used to make leaders far longer than the layout needed.
#
# 1. The retry loop relaxed density until *no* pair of labels overlapped.
#    Labels are separated by sliding them along the axis, so two events on
#    the same day overlap at every density until each owns a row — and
#    chasing that one pair opened rows for every other label too, pushing
#    the stack off the page.
# 2. The axis-label clearance was folded into labella's layerGap, which is
#    both the axis-to-first-row gap *and* part of the row stride, so a deep
#    stack paid the clearance once per row.


def _same_day_events():
    """Four pairs that share a date: unseparable along the axis."""
    raw = [
        ("Canary Deployment 5 percent", "20260717"),
        ("Production Rollout 25 percent", "20260717"),
        ("Production Rollout 100 percent", "20260720"),
        ("Go/No-Go Decision Meeting", "20260720"),
        ("Training Sign-off Complete", "20260722"),
        ("Operations Readiness Review", "20260722"),
        ("Go-Live Event Announcement", "20260724"),
        ("Project Closeout Retrospective", "20260724"),
    ]
    return [_ev(name, day) for name, day in raw]


def _stack_depth(placements) -> float:
    return max(abs(p.y_label - p.axis_origin[1]) for p in placements)


def test_the_row_search_stops_at_the_room_available(config):
    """A stack that would run off the page is not worth the rows."""
    kwargs = dict(
        axis_origin=(0.0, 400.0),
        axis_length=1766.0,
        orientation=Orientation.HORIZONTAL,
        side=Side.PRIMARY,
        config=config,
        pos_for_day=_pos_for_day_factory("20260401", "20260731", 1766.0),
    )
    events = _same_day_events()

    uncapped = layout_callouts(events, **kwargs)
    capped = layout_callouts(events, max_extent=100.0, **kwargs)

    assert _stack_depth(capped) <= 100.0
    assert _stack_depth(capped) < _stack_depth(uncapped)
    # Nothing is dropped to achieve it.
    assert len(capped) == len(events)


def test_a_generous_bound_still_reaches_a_clean_layout(config):
    """The cap is a ceiling, not a target: given room, overlap still wins."""
    from shared.labella_layout import _row_overlap_count

    kwargs = dict(
        axis_origin=(0.0, 400.0),
        axis_length=1766.0,
        orientation=Orientation.HORIZONTAL,
        side=Side.PRIMARY,
        config=config,
        pos_for_day=_pos_for_day_factory("20260401", "20260731", 1766.0),
    )
    events = _same_day_events()
    assert _row_overlap_count(layout_callouts(events, max_extent=10_000.0, **kwargs)) == 0


def test_the_first_row_gap_does_not_inflate_the_row_stride(config):
    """stack_offset buys clearance once; layer_gap sets the stride."""
    kwargs = dict(
        axis_origin=(0.0, 400.0),
        axis_length=1766.0,
        orientation=Orientation.HORIZONTAL,
        side=Side.PRIMARY,
        config=config,
        pos_for_day=_pos_for_day_factory("20260401", "20260731", 1766.0),
    )
    events = _same_day_events()

    plain = layout_callouts(events, **kwargs)
    offset = layout_callouts(events, min_layer_gap=60.0, **kwargs)

    rows_plain = sorted({round(p.y_label, 2) for p in plain})
    rows_offset = sorted({round(p.y_label, 2) for p in offset})
    assert len(rows_plain) == len(rows_offset) > 1

    # Every row moved by the same amount — the stride is untouched.
    shifts = {
        round(b - a, 2) for a, b in zip(sorted(rows_plain), sorted(rows_offset))
    }
    assert len(shifts) == 1
    assert next(iter(shifts)) != 0.0


def test_the_leader_path_moves_with_its_label_but_keeps_its_dot(config):
    """The offset must not drag the axis end of the leader off the axis."""
    from shared.labella_layout import _offset_leader_path

    path = "M 10.00000000 0.00000000 C 10.00000000 -5.00000000 20.00000000 -5.00000000 20.00000000 -10.00000000"
    moved = _offset_leader_path(path, "up", 7.0)

    numbers = [float(t) for t in moved.split() if not t.isalpha()]
    # The dot is untouched...
    assert numbers[0] == pytest.approx(10.0)
    assert numbers[1] == pytest.approx(0.0)
    # ...and every later point moved away from the axis by exactly 7.
    assert numbers[3] == pytest.approx(-12.0)
    assert numbers[7] == pytest.approx(-17.0)
    # X is never touched on a horizontal axis.
    assert [numbers[i] for i in (2, 4, 6)] == [10.0, 20.0, 20.0]


def test_an_unparseable_leader_path_is_left_alone():
    from shared.labella_layout import _offset_leader_path

    assert _offset_leader_path("M oops", "up", 5.0) == "M oops"
    assert _offset_leader_path("", "up", 5.0) == ""
    assert _offset_leader_path("M 1 2", "sideways", 5.0) == "M 1 2"


# ── Page containment ──────────────────────────────────────────────────────
#
# Labella's walls constrain a label's position, but its model treats that
# position as the label's centre while this codebase draws the box from it
# as the leading edge. A label solved against the wall therefore still put
# most of a box-width past it: a year on A4 lost 41.7pt off the right-hand
# box, cutting the text and the border.


def _box_spans(placements):
    return [(p.x_label, p.x_label + p.label_w) for p in placements]


def _late_events():
    """Events bunched at the very end of the range, where boxes run out."""
    return [
        _ev("Production Rollout 25 percent", "20260722"),
        _ev("Go-Live Event Announcement", "20260728"),
        _ev("Project Closeout Retrospective", "20260731"),
    ]


def test_no_callout_box_is_placed_past_the_bounds(config):
    bounds = (0.0, 500.0)
    placements = layout_callouts(
        _late_events(),
        axis_origin=(0.0, 400.0),
        axis_length=480.0,
        orientation=Orientation.HORIZONTAL,
        side=Side.PRIMARY,
        config=config,
        pos_for_day=_pos_for_day_factory("20260401", "20260731", 480.0),
        label_bounds=bounds,
    )
    assert placements
    for left, right in _box_spans(placements):
        assert left >= bounds[0] - 0.01
        assert right <= bounds[1] + 0.01


def test_without_bounds_a_late_box_still_overhangs(config):
    """Guards the test above: the input really does overhang unclamped."""
    placements = layout_callouts(
        _late_events(),
        axis_origin=(0.0, 400.0),
        axis_length=480.0,
        orientation=Orientation.HORIZONTAL,
        side=Side.PRIMARY,
        config=config,
        pos_for_day=_pos_for_day_factory("20260401", "20260731", 480.0),
    )
    assert max(right for _left, right in _box_spans(placements)) > 500.0


def test_a_clamped_label_keeps_its_leader_attached(config):
    """Clamping currentPos, not the placement, moves the leader with it."""
    bounds = (0.0, 500.0)
    placements = layout_callouts(
        _late_events(),
        axis_origin=(0.0, 400.0),
        axis_length=480.0,
        orientation=Orientation.HORIZONTAL,
        side=Side.PRIMARY,
        config=config,
        pos_for_day=_pos_for_day_factory("20260401", "20260731", 480.0),
        label_bounds=bounds,
    )
    for p in placements:
        tokens = p.leader_path_d.split()
        numbers = [float(t) for t in tokens if not t.isalpha()]
        # The path's last point is where the leader meets its label.
        assert numbers[-2] == pytest.approx(p.x_label - p.axis_origin[0], abs=0.51)


def test_bounds_are_honoured_on_a_vertical_axis(config):
    bounds = (0.0, 320.0)
    placements = layout_callouts(
        _late_events(),
        axis_origin=(200.0, 0.0),
        axis_length=300.0,
        orientation=Orientation.VERTICAL,
        side=Side.PRIMARY,
        config=config,
        pos_for_day=_pos_for_day_factory("20260401", "20260731", 300.0),
        label_bounds=bounds,
    )
    assert placements
    for p in placements:
        assert p.y_label >= bounds[0] - 0.01
        assert p.y_label + p.label_h <= bounds[1] + 0.01


def test_a_box_wider_than_the_page_hugs_the_leading_edge(config):
    """Nothing fits, so keep the corner the text starts from on the page."""
    from shared.labella_layout import _clamp_labels_to_bounds
    from vendor.labella import Node

    node = Node(idealPos=200.0, width=400.0)
    node.currentPos = 200.0
    node.x = 200.0
    _clamp_labels_to_bounds(
        [node], Orientation.HORIZONTAL, (0.0, 0.0), (10.0, 110.0)
    )
    assert node.currentPos == pytest.approx(10.0)
    assert node.x == pytest.approx(10.0)


def test_a_label_already_inside_the_bounds_is_left_alone(config):
    from shared.labella_layout import _clamp_labels_to_bounds
    from vendor.labella import Node

    node = Node(idealPos=50.0, width=40.0)
    node.currentPos = 50.0
    node.x = 50.0
    _clamp_labels_to_bounds(
        [node], Orientation.HORIZONTAL, (0.0, 0.0), (0.0, 500.0)
    )
    assert node.currentPos == pytest.approx(50.0)


# ── Leader stubs ──────────────────────────────────────────────────────────
#
# labella's bezier leaves the axis dot and meets the box at a shallow angle,
# so a leader reads as grazing its anchors rather than arriving at them. PIT
# has always rewritten both ends into straight perpendicular stubs; the
# timeline now shares that post-pass.


def _leaders(config, **overrides):
    for key, value in overrides.items():
        setattr(config, key, value)
    return [
        p.leader_path_d
        for p in layout_callouts(
            [_ev("Alpha", "20260405"), _ev("Beta", "20260620")],
            axis_origin=(0.0, 400.0),
            axis_length=670.0,
            orientation=Orientation.HORIZONTAL,
            side=Side.PRIMARY,
            config=config,
            pos_for_day=_pos_for_day_factory("20260401", "20260731", 670.0),
        )
    ]


def test_timeline_leaders_start_with_a_perpendicular_stub(config):
    paths = _leaders(config, timeline_leader_start_stub=4.0)
    assert paths
    for d in paths:
        tokens = d.split()
        # M x y L x y … — and the L shares the M's x, so the stub is
        # perpendicular to a horizontal axis.
        assert tokens[3] == "L"
        assert float(tokens[4]) == pytest.approx(float(tokens[1]))
        assert float(tokens[5]) != pytest.approx(float(tokens[2]))


def test_timeline_leaders_end_with_a_perpendicular_stub(config):
    paths = _leaders(config, timeline_leader_end_stub=4.0)
    assert paths
    for d in paths:
        tokens = d.strip().split()
        assert tokens[-3] == "L"
        # The cubic's endpoint before it shares the same x.
        assert float(tokens[-2]) == pytest.approx(float(tokens[-5]))


def test_zero_stubs_leave_the_bezier_untouched(config):
    paths = _leaders(
        config, timeline_leader_start_stub=0.0, timeline_leader_end_stub=0.0
    )
    assert paths
    for d in paths:
        tokens = d.strip().split()
        assert tokens[3] != "L"
        assert tokens[-3] != "L"


def test_a_stub_never_swallows_the_whole_segment(config):
    """Capped at 85% of the segment, so the curve is never inverted."""
    from shared.labella_layout import append_perp_stub

    # Final cubic spans only 2pt perpendicular; ask for a 50pt stub.
    path = "M 0 0 C 0 -1 10 -1 10 -3"
    out = append_perp_stub(path, Orientation.HORIZONTAL, 50.0)
    tokens = out.split()
    trimmed_y = float(tokens[-4])
    # Pulled back at most 85% of the 2pt span, so it stays past the control
    # point rather than doubling back over it.
    assert -3.0 < trimmed_y <= -1.3 + 1e-6


@pytest.mark.parametrize(
    "path", ["", "M 10 0", "not a path", "M 10 0 L 10 -4"]
)
def test_stub_rewrites_leave_odd_paths_alone(path):
    from shared.labella_layout import append_perp_stub, prepend_perp_stub

    assert append_perp_stub(path, Orientation.HORIZONTAL, 4.0) == path
    assert prepend_perp_stub(path, Orientation.HORIZONTAL, 4.0) == path


# ── Leader routing ────────────────────────────────────────────────────────
#
# labella threads a leader through the solved position of every ancestor
# stub, emitting a curve-and-line pair per row, so a label eight rows up
# arrived with fifteen segments — and those chains all ran through one
# channel, crossing the boxes between. Direct routing draws one curve from
# the dot to the label's own edge instead.


def _segment_count(path_d: str) -> int:
    return path_d.count("C") + path_d.count("L")


def _deep_stack(config, **kwargs):
    """Events clustered tightly enough that labella opens several rows."""
    events = [_ev(f"Event number {i}", f"202607{10 + i:02d}") for i in range(12)]
    return layout_callouts(
        events,
        axis_origin=(0.0, 400.0),
        axis_length=600.0,
        orientation=Orientation.HORIZONTAL,
        side=Side.PRIMARY,
        config=config,
        pos_for_day=_pos_for_day_factory("20260701", "20260731", 600.0),
        **kwargs,
    )


def test_direct_routing_gives_every_leader_the_same_few_segments(config):
    config.timeline_leader_direct = True
    placements = _deep_stack(config)
    assert len({p.layer for p in placements}) > 2, "the fixture should stack up"

    counts = {_segment_count(p.leader_path_d) for p in placements}
    # One curve plus the two perpendicular stubs, whatever the depth.
    assert counts == {3}


def test_layered_routing_costs_a_segment_pair_per_row(config):
    """The behaviour direct routing replaces, kept reachable by a theme."""
    config.timeline_leader_direct = False
    placements = _deep_stack(config)

    by_layer = {}
    for p in placements:
        by_layer.setdefault(p.layer, _segment_count(p.leader_path_d))
    deepest = max(by_layer)
    assert deepest >= 2
    # Segments grow with depth: each extra row adds a curve and a line.
    assert by_layer[deepest] > by_layer[min(by_layer)]
    assert by_layer[deepest] > 3


def test_a_direct_leader_still_starts_on_its_own_dot(config):
    config.timeline_leader_direct = True
    for p in _deep_stack(config):
        tokens = p.leader_path_d.split()
        start_x = float(tokens[1])
        assert start_x == pytest.approx(p.x_dot - p.axis_origin[0], abs=0.01)


def test_a_direct_leader_ends_on_its_own_label(config):
    config.timeline_leader_direct = True
    for p in _deep_stack(config):
        tokens = p.leader_path_d.strip().split()
        end_x = float(tokens[-2])
        # The leader meets the box at the same x the box is drawn from.
        assert end_x == pytest.approx(p.x_label - p.axis_origin[0], abs=0.51)


def test_direct_routing_is_used_for_a_vertical_axis_too(config):
    config.timeline_leader_direct = True
    placements = layout_callouts(
        [_ev(f"Event {i}", f"202607{10 + i:02d}") for i in range(12)],
        axis_origin=(300.0, 0.0),
        axis_length=600.0,
        orientation=Orientation.VERTICAL,
        side=Side.PRIMARY,
        config=config,
        pos_for_day=_pos_for_day_factory("20260701", "20260731", 600.0),
    )
    assert {_segment_count(p.leader_path_d) for p in placements} == {3}
