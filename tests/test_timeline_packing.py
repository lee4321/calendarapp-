"""Deterministic packing of timeline point-event callouts.

The rules under test, in the order the packer applies them: a box's leading
edge sits on its own start date; a box that would run off the end of the
timeline is pushed back to finish flush with it; rows fill from the axis
outward so the earliest event in a stack is nearest the axis; a box with no
free row on its date slides along the axis instead; and a box with nowhere
left to go is not drawn at all.
"""

from __future__ import annotations

import logging
import re

import arrow
import pytest

from config.config import create_calendar_config, setfontsizes
from shared.data_models import Event
from shared.orientation import Orientation, Side
from visualizers.timeline.packing import pack_callouts, resolve_box_size

AXIS_ORIGIN = (100.0, 400.0)
AXIS_LENGTH = 600.0
START = arrow.get("20260101", "YYYYMMDD")
END = arrow.get("20260301", "YYYYMMDD")

BOX_W = 100.0
BOX_H = 20.0


def _config(**overrides):
    config = create_calendar_config()
    config.pageX, config.pageY = 792.0, 1224.0
    config = setfontsizes(config)
    config.timeline_event_box_width = BOX_W
    config.timeline_event_box_height = BOX_H
    config.timeline_event_row_gap = 4.0
    config.timeline_event_box_gap = 0.0
    for key, value in overrides.items():
        setattr(config, key, value)
    return config


def _pos_for_day(day: arrow.Arrow) -> float:
    span = max(1, (END.floor("day") - START.floor("day")).days)
    offset = (day.floor("day") - START.floor("day")).days
    return AXIS_LENGTH * (max(0, min(offset, span)) / span)


def _pack(events, *, config=None, orientation=Orientation.HORIZONTAL,
          side=Side.PRIMARY, **kwargs):
    return pack_callouts(
        events,
        axis_origin=AXIS_ORIGIN,
        axis_length=AXIS_LENGTH,
        orientation=orientation,
        side=side,
        config=config or _config(),
        pos_for_day=_pos_for_day,
        **kwargs,
    )


def _event(day: str, name: str = "E", **kwargs) -> Event:
    return Event(task_name=name, start=day, end=day, **kwargs)


def _leader_points(path_d: str) -> tuple[tuple[float, float], tuple[float, float]]:
    nums = [float(n) for n in re.findall(r"-?\d+(?:\.\d+)?", path_d)]
    assert len(nums) == 4, path_d
    return (nums[0], nums[1]), (nums[2], nums[3])


# ── Alignment with the start date ──────────────────────────────────────────


def test_a_box_starts_on_its_own_date():
    placed = _pack([_event("20260115")])[0]
    expected = AXIS_ORIGIN[0] + _pos_for_day(arrow.get("20260115", "YYYYMMDD"))
    assert placed.x_label == pytest.approx(expected)
    assert placed.x_dot == pytest.approx(expected)


def test_boxes_sharing_a_date_share_a_column():
    placed = _pack([_event("20260115", f"E{i}") for i in range(4)])
    assert len({round(p.x_label, 6) for p in placed} ) == 1
    assert sorted(p.layer for p in placed) == [0, 1, 2, 3]


def test_the_earliest_event_in_a_stack_sits_closest_to_the_axis():
    """Row 0 is nearest the axis, and it goes to the earliest start."""
    events = [_event("20260115", "later"), _event("20260114", "earlier")]
    by_name = {p.event.task_name: p for p in _pack(events)}
    assert by_name["earlier"].layer == 0
    # Above the axis, nearer means a larger SVG y.
    assert by_name["earlier"].y_label > by_name["later"].y_label


def test_a_row_is_reused_once_the_boxes_no_longer_collide():
    """Density is the point: a later date drops back to row 0."""
    events = [_event("20260105", "a"), _event("20260106", "b"),
              _event("20260220", "c")]
    by_name = {p.event.task_name: p for p in _pack(events)}
    assert by_name["a"].layer == 0
    assert by_name["b"].layer == 1     # overlaps a
    assert by_name["c"].layer == 0     # clear of both


# ── The leader ─────────────────────────────────────────────────────────────


def test_the_leader_is_a_straight_perpendicular_run_to_the_near_corner():
    placed = _pack([_event("20260115")])[0]
    (x0, y0), (x1, y1) = _leader_points(placed.leader_path_d)
    assert y0 == pytest.approx(0.0)          # starts on the axis
    assert x0 == pytest.approx(x1)           # perpendicular
    assert y1 < 0                            # runs up, on the primary side
    # It lands on the box's axis-facing edge, at the leading corner.
    assert AXIS_ORIGIN[1] + y1 == pytest.approx(
        placed.y_label + placed.label_h
    )
    assert AXIS_ORIGIN[0] + x1 == pytest.approx(placed.x_label)


def test_a_leader_below_the_axis_mirrors_the_one_above():
    above = _pack([_event("20260115")], side=Side.PRIMARY)[0]
    below = _pack([_event("20260115")], side=Side.SECONDARY)[0]
    (_s, (_x_a, y_a)) = _leader_points(above.leader_path_d)
    (_s2, (_x_b, y_b)) = _leader_points(below.leader_path_d)
    assert y_a == pytest.approx(-y_b)
    assert below.y_label > above.y_label
    # The near edge below the axis is the box's top.
    assert AXIS_ORIGIN[1] + y_b == pytest.approx(below.y_label)


# ── The end of the timeline ────────────────────────────────────────────────


def test_a_box_near_the_end_is_pushed_back_to_finish_flush_with_it():
    """It cannot be drawn on its date without leaving the timeline."""
    placed = _pack([_event("20260301")])[0]
    assert placed.x_label + placed.label_w == pytest.approx(
        AXIS_ORIGIN[0] + AXIS_LENGTH
    )
    assert placed.x_label < placed.x_dot


def test_a_pushed_back_box_keeps_a_perpendicular_leader():
    """The date still falls inside the box, so the leader stays straight up."""
    placed = _pack([_event("20260301")])[0]
    (x0, _y0), (x1, y1) = _leader_points(placed.leader_path_d)
    assert x0 == pytest.approx(x1)
    landing = AXIS_ORIGIN[0] + x1
    assert placed.x_label <= landing <= placed.x_label + placed.label_w
    assert AXIS_ORIGIN[1] + y1 == pytest.approx(placed.y_label + placed.label_h)


# ── Running out of room ────────────────────────────────────────────────────


def test_a_full_column_slides_the_box_along_the_axis():
    """Two rows, three same-dated events: the third gives up its column."""
    config = _config()
    events = [_event("20260115", f"E{i}") for i in range(3)]
    placed = _pack(events, config=config, max_extent=2 * (BOX_H + 4.0) + 4.0)

    assert all(p.placed for p in placed)
    rows = sorted(p.layer for p in placed)
    assert rows == [0, 0, 1]
    nudged = [p for p in placed if p.x_label != placed[0].x_label]
    assert len(nudged) == 1
    # It slid right, onto the row closest to the axis, and its leader still
    # points at the correct day — slanted, but straight.
    assert nudged[0].layer == 0
    assert nudged[0].x_label > placed[0].x_label
    (x0, _y0), (x1, _y1) = _leader_points(nudged[0].leader_path_d)
    assert x0 != pytest.approx(x1)


def test_an_event_with_nowhere_to_go_is_marked_unplaced(caplog):
    config = _config()
    events = [_event("20260220", f"E{i}", notes="detail", wbs="NP.3")
              for i in range(3)]
    # Room for a single row, and the axis ends too soon to slide sideways.
    with caplog.at_level(logging.WARNING):
        placed = _pack(events, config=config, max_extent=BOX_H + 4.0)

    unplaced = [p for p in placed if not p.placed]
    assert len(placed) == len(events)
    assert len(unplaced) == 2
    for p in unplaced:
        assert p.label_w == 0.0 and p.label_h == 0.0
        assert p.leader_path_d.startswith("M ")

    # The warning has to name the event well enough to find it in the data.
    messages = " ".join(r.getMessage() for r in caplog.records)
    assert "E1" in messages and "NP.3" in messages and "20260220" in messages


def test_no_room_at_all_places_nothing():
    placed = _pack([_event("20260115")], max_extent=1.0)
    assert placed and not placed[0].placed


def test_no_limit_keeps_stacking():
    """--shrink grows the viewBox instead, so rows are never rationed."""
    events = [_event("20260115", f"E{i}") for i in range(30)]
    placed = _pack(events, max_extent=None)
    assert all(p.placed for p in placed)
    assert max(p.layer for p in placed) == 29


# ── Both sides, and the vertical axis ──────────────────────────────────────


def test_both_sides_split_the_events_and_pack_each_side():
    events = [_event(f"202601{d:02d}", f"E{d}") for d in range(1, 9)]
    placed = _pack(events, side=Side.BOTH)
    assert len(placed) == len(events)
    assert {p.side for p in placed} == {Side.PRIMARY, Side.SECONDARY}
    for p in placed:
        assert p.placed


@pytest.mark.parametrize("side", [Side.PRIMARY, Side.SECONDARY])
def test_a_vertical_axis_packs_along_y_and_stacks_along_x(side):
    """Along-axis is the box's height; away-from-axis is its width."""
    # Far enough apart that a box-height of axis separates them.
    events = [_event("20260115", "a"), _event("20260201", "b")]
    placed = _pack(events, orientation=Orientation.VERTICAL, side=side)

    for p in placed:
        assert p.label_w == pytest.approx(BOX_W)
        assert p.label_h == pytest.approx(BOX_H)
        # The dot rides the axis line, whatever the date.
        assert p.x_dot == pytest.approx(AXIS_ORIGIN[0])
    # Their spans along the axis are clear of each other, so both take
    # the row nearest the axis.
    assert {p.layer for p in placed} == {0}
    assert placed[0].y_label < placed[1].y_label

    (x0, _y0), (x1, y1) = _leader_points(placed[0].leader_path_d)
    assert x0 == pytest.approx(0.0)          # starts on the axis
    assert y1 == pytest.approx(_y0)          # perpendicular is horizontal now
    assert (x1 > 0) is (side is Side.PRIMARY)


def test_a_vertical_box_starts_on_its_own_date():
    placed = _pack(
        [_event("20260115")], orientation=Orientation.VERTICAL
    )[0]
    expected = AXIS_ORIGIN[1] + _pos_for_day(arrow.get("20260115", "YYYYMMDD"))
    assert placed.y_label == pytest.approx(expected)


# ── Box sizing ─────────────────────────────────────────────────────────────


def test_the_theme_width_and_height_are_used_verbatim():
    config = _config()
    assert resolve_box_size([_event("20260115", "x" * 200)], config) == (
        BOX_W, BOX_H
    )


def test_an_unset_width_derives_one_width_for_the_whole_chart():
    config = _config(timeline_event_box_width=None)
    events = [_event("20260115", "short"),
              _event("20260116", "a considerably longer event name")]
    width, _height = resolve_box_size(events, config)

    # One width, sized to the widest event — every box still gets it.
    placed = _pack(events, config=config)
    assert {round(p.label_w, 6) for p in placed} == {round(width, 6)}
    assert width > resolve_box_size([events[0]], config)[0]


def test_no_two_boxes_on_a_row_ever_overlap():
    """The invariant the whole packer exists to hold."""
    events = [
        _event(f"202601{d:02d}", f"E{d}-{i}")
        for d in range(1, 29)
        for i in range(3)
    ]
    placed = [p for p in _pack(events, max_extent=None) if p.placed]
    by_row: dict[int, list[tuple[float, float]]] = {}
    for p in placed:
        by_row.setdefault(p.layer, []).append((p.x_label, p.x_label + p.label_w))
    for row, spans in by_row.items():
        spans.sort()
        for (_a_lo, a_hi), (b_lo, _b_hi) in zip(spans, spans[1:]):
            assert a_hi <= b_lo + 1e-6, f"row {row} overlaps"


def test_a_stopped_leader_leaves_room_for_the_missing_icon():
    """The glyph is centred on the leader's end, so the end must not be
    the very edge of the drawable area — half the icon would fall outside."""
    config = _config(default_missing_icon_size=12.0)
    events = [_event("20260220", f"E{i}") for i in range(3)]
    placed = _pack(events, config=config, max_extent=BOX_H + 4.0)

    unplaced = [p for p in placed if not p.placed]
    assert unplaced
    for p in unplaced:
        # Primary side: away from the axis is upward, so a smaller y.
        reach = AXIS_ORIGIN[1] - p.y_label
        assert reach == pytest.approx(BOX_H + 4.0 - 6.0)


def test_shrink_bounds_contain_every_callout_box():
    """--shrink refits the viewBox, and a packed box reaches the axis end.

    Callouts used to contribute only their top edge to the tight bounds, so
    the last box on the axis lost half its border to the new viewBox.
    """
    from visualizers.timeline.renderer import TimelineCallout, TimelineRenderer

    config = _config()
    renderer = TimelineRenderer()
    callouts = [
        TimelineCallout(
            event=p.event, color="grey", x_dot=p.x_dot, y_dot=p.y_dot,
            lane=p.layer, box_x=p.x_label, box_y=p.y_label,
            box_width=p.label_w, box_height=p.label_h,
        )
        for p in _pack(
            [_event("20260105", "a"), _event("20260301", "z")], config=config
        )
    ]
    x, y, w, h = renderer._actual_content_bounds(
        config, callouts, [],
        axis_left=AXIS_ORIGIN[0],
        axis_right=AXIS_ORIGIN[0] + AXIS_LENGTH,
        axis_y=AXIS_ORIGIN[1],
        area_x=0.0, area_y=0.0, area_w=792.0, area_h=612.0,
    )
    stroke = config.get_box_style("ec-callout-box").stroke_width
    for c in callouts:
        assert x <= c.box_x - stroke / 2.0 + 0.01
        assert c.box_x + c.box_width + stroke / 2.0 <= x + w + 0.01
        assert y <= c.box_y + 0.01
        assert c.box_y + c.box_height <= y + h + 0.01
