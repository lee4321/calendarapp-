"""Gantt dependency arrows: resolution, per-type anchoring, routing, drawing."""

from __future__ import annotations

import pytest

from shared.data_models import Event
from test_gantt_marks import render, task
from visualizers.gantt.dependencies import (
    ARROW_STYLE_TARGET,
    DEFAULT_STUB,
    RowAnchor,
    arrow_head,
    resolve_dependencies,
    route_arrow,
    stub_route,
)
from visualizers.gantt.details import (
    KIND_OFFCHART_DEPENDENCY,
    KIND_UNPARSEABLE_PREDECESSOR,
    KIND_UNRESOLVED_PREDECESSOR,
)
from visualizers.gantt.rows import GanttRow


def row(index: int, source_id: str, predecessors: str = "") -> GanttRow:
    return GanttRow(
        event=Event(
            task_name=f"task {source_id}",
            start="20260202",
            end="20260204",
            source_id=source_id,
            predecessors=predecessors,
        ),
        depth=0,
        index=index,
    )


# ── Resolution ────────────────────────────────────────────────────────────


def test_a_link_between_drawn_rows_resolves_to_a_dependency():
    rows = [row(0, "1"), row(1, "2", "1")]
    dependencies, exceptions = resolve_dependencies(rows, {0, 1})

    assert exceptions == []
    assert len(dependencies) == 1
    assert (dependencies[0].successor_index, dependencies[0].predecessor_index) == (1, 0)
    assert dependencies[0].link_type == "FS"


def test_links_resolve_by_source_id_not_row_order():
    rows = [row(0, "77"), row(1, "12", "77")]
    dependencies, _exceptions = resolve_dependencies(rows, {0, 1})
    assert dependencies[0].predecessor_index == 0


def test_the_link_type_is_carried_through():
    rows = [row(0, "1"), row(1, "2", "1SS+3d")]
    dependencies, _exceptions = resolve_dependencies(rows, {0, 1})
    assert dependencies[0].link_type == "SS"


def test_a_predecessor_that_is_not_drawn_becomes_a_stub():
    """It exists in the schedule but not on this page (answer 27)."""
    rows = [row(0, "1"), row(1, "2", "1")]
    dependencies, exceptions = resolve_dependencies(rows, {1})

    assert dependencies[0].predecessor_index is None
    assert [e.kind for e in exceptions] == [KIND_OFFCHART_DEPENDENCY]


def test_a_reference_matching_no_task_is_reported_as_unresolved():
    rows = [row(0, "1", "999")]
    dependencies, exceptions = resolve_dependencies(rows, {0})

    assert dependencies[0].predecessor_index is None
    assert [e.kind for e in exceptions] == [KIND_UNRESOLVED_PREDECESSOR]
    assert "999" in exceptions[0].detail


def test_an_unparseable_token_is_reported_and_draws_nothing():
    rows = [row(0, "1", "FS+3d")]
    dependencies, exceptions = resolve_dependencies(rows, {0})

    assert dependencies == []
    assert [e.kind for e in exceptions] == [KIND_UNPARSEABLE_PREDECESSOR]


def test_a_successor_that_is_not_drawn_contributes_nothing():
    rows = [row(0, "1"), row(1, "2", "1")]
    dependencies, exceptions = resolve_dependencies(rows, {0})
    assert (dependencies, exceptions) == ([], [])


def test_multiple_predecessors_all_resolve():
    rows = [row(0, "1"), row(1, "2"), row(2, "3", "1,2FF")]
    dependencies, _exceptions = resolve_dependencies(rows, {0, 1, 2})
    assert [(d.predecessor_index, d.link_type) for d in dependencies] == [
        (0, "FS"), (1, "FF"),
    ]


def test_rows_without_a_source_id_are_never_link_targets():
    rows = [row(0, ""), row(1, "2", "1")]
    dependencies, exceptions = resolve_dependencies(rows, {0, 1})
    assert dependencies[0].predecessor_index is None
    assert exceptions[0].kind == KIND_UNRESOLVED_PREDECESSOR


# ── Per-type anchoring ────────────────────────────────────────────────────

PREDECESSOR = RowAnchor(left=100.0, right=200.0, y=10.0)
SUCCESSOR = RowAnchor(left=300.0, right=400.0, y=30.0)


@pytest.mark.parametrize(
    "link_type,expected_exit,expected_entry,expected_head",
    [
        ("FS", 200.0, 300.0, +1),   # right edge  → left edge, head right
        ("SS", 100.0, 300.0, +1),   # left edge   → left edge, head right
        ("FF", 200.0, 400.0, -1),   # right edge  → right edge, head left
        ("SF", 200.0, 300.0, -1),   # right edge  → left edge from the right
    ],
)
def test_each_link_type_leaves_and_enters_its_own_edges(
    link_type, expected_exit, expected_entry, expected_head
):
    route = route_arrow(PREDECESSOR, SUCCESSOR, link_type)
    assert route.points[0] == (expected_exit, PREDECESSOR.y)
    assert route.tip == (expected_entry, SUCCESSOR.y)
    assert route.head_dir == expected_head


def test_an_unknown_type_falls_back_to_finish_to_start():
    route = route_arrow(PREDECESSOR, SUCCESSOR, "XX")
    assert route.points[0] == (PREDECESSOR.right, PREDECESSOR.y)
    assert route.tip == (SUCCESSOR.left, SUCCESSOR.y)


# ── Routing ───────────────────────────────────────────────────────────────


def test_a_route_is_always_three_orthogonal_segments():
    route = route_arrow(PREDECESSOR, SUCCESSOR, "FS")
    assert len(route.segments) == 3
    for x1, y1, x2, y2 in route.segments:
        assert x1 == x2 or y1 == y2, "segments must be axis-aligned"


def test_a_forward_route_turns_clear_of_the_entry():
    route = route_arrow(PREDECESSOR, SUCCESSOR, "FS")
    turn_x = route.points[1][0]
    assert turn_x == pytest.approx(SUCCESSOR.left - DEFAULT_STUB)
    assert PREDECESSOR.right < turn_x < SUCCESSOR.left


def test_a_backward_link_folds_into_a_dogleg_that_still_points_right():
    """The successor starts before the predecessor ends (answer 26)."""
    earlier = RowAnchor(left=100.0, right=150.0, y=30.0)
    route = route_arrow(PREDECESSOR, earlier, "FS")

    assert len(route.segments) == 3
    assert route.head_dir == +1
    turn_x = route.points[1][0]
    assert turn_x == pytest.approx(earlier.left - DEFAULT_STUB)
    assert turn_x < PREDECESSOR.right, "the first segment doubles back"


def test_a_start_to_start_route_turns_left_of_both_bars():
    route = route_arrow(PREDECESSOR, SUCCESSOR, "SS")
    turn_x = route.points[1][0]
    assert turn_x == pytest.approx(
        min(PREDECESSOR.left, SUCCESSOR.left) - DEFAULT_STUB
    )


def test_a_finish_to_finish_route_turns_right_of_both_bars():
    route = route_arrow(PREDECESSOR, SUCCESSOR, "FF")
    turn_x = route.points[1][0]
    assert turn_x == pytest.approx(
        max(PREDECESSOR.right, SUCCESSOR.right) + DEFAULT_STUB
    )


def test_the_stub_route_arrives_from_the_left():
    route = stub_route(SUCCESSOR, length=12.0)
    assert route.head_dir == +1
    assert route.tip == (SUCCESSOR.left, SUCCESSOR.y)
    assert route.points[0][0] < SUCCESSOR.left


def test_the_arrow_head_is_two_segments_meeting_at_the_tip():
    segments = arrow_head((50.0, 20.0), +1, 4.0)
    assert len(segments) == 2
    assert all(seg[2:] == (50.0, 20.0) for seg in segments)
    assert all(seg[0] < 50.0 for seg in segments), "head opens to the left"


def test_a_left_pointing_head_opens_to_the_right():
    segments = arrow_head((50.0, 20.0), -1, 4.0)
    assert all(seg[0] > 50.0 for seg in segments)


# ── Drawing ───────────────────────────────────────────────────────────────


def linked_tasks() -> list[dict]:
    return [
        task(Task_Name="first", Source_ID="1", Start="20260202", End="20260204"),
        task(
            Task_Name="second", Source_ID="2", Start="20260209", End="20260211",
            Predecessors="1",
        ),
    ]


def test_a_link_draws_a_route_and_a_head():
    renderer = render(linked_tasks())
    arrows = renderer.of_class(renderer.polylines, "ec-dependency-arrow")
    assert len(arrows) == 2                      # route + head
    assert len(arrows[0]["segments"]) == 3
    assert len(arrows[1]["segments"]) == 2


def test_dependencies_can_be_switched_off():
    renderer = render(linked_tasks(), gantt_show_dependencies=False)
    assert renderer.of_class(renderer.polylines, "ec-dependency-arrow") == []


def test_no_arrows_without_predecessor_data():
    renderer = render([task(Source_ID="1"), task(Source_ID="2")])
    assert renderer.of_class(renderer.polylines, "ec-dependency-arrow") == []


def test_an_offchart_predecessor_draws_the_marker_icon():
    renderer = render([
        task(Task_Name="orphan", Source_ID="2", Predecessors="999"),
    ])
    assert any(i["icon"] == "crosssquare" for i in renderer.icons)
    assert [e.kind for e in renderer.exceptions] == [KIND_UNRESOLVED_PREDECESSOR]


def test_a_style_rule_restyles_the_arrows():
    rule = {
        "apply_to": ARROW_STYLE_TARGET,
        "select": {"resource_group": "Delivery"},
        "style": {"stroke": "crimson", "stroke_width": 2.0},
    }
    events = linked_tasks()
    events[1]["Resource_Group"] = "Delivery"
    renderer = render(events, theme_style_rules=[rule])

    arrows = renderer.of_class(renderer.polylines, "ec-dependency-arrow")
    assert arrows[0]["stroke"] == "crimson"
    assert arrows[0]["stroke_width"] == pytest.approx(2.0)


def test_the_arrow_head_is_never_dashed():
    rule = {
        "apply_to": ARROW_STYLE_TARGET,
        "style": {"stroke": "black", "stroke_dasharray": "4 2"},
    }
    renderer = render(linked_tasks(), theme_style_rules=[rule])
    route, head = renderer.of_class(renderer.polylines, "ec-dependency-arrow")
    assert route["stroke_dasharray"] == "4 2"
    assert head.get("stroke_dasharray") is None
