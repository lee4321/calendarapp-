"""Gantt dependency arrows: resolution, per-type anchoring, routing, drawing."""

from __future__ import annotations

import pytest

from shared.data_models import Event
from test_gantt_marks import render, task
from visualizers.gantt.dependencies import (
    ARROW_STYLE_TARGET,
    DEFAULT_STUB,
    RowAnchor,
    curved_path,
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


# ── Routing: the PIT leader construction ──────────────────────────────────


def test_a_route_is_a_stub_then_a_curve_then_a_stub():
    """Same shape as a PIT callout leader: L … C … L."""
    route = route_arrow(PREDECESSOR, SUCCESSOR, "FS")
    assert route.path_d.startswith("M ")
    assert route.path_d.count(" C ") == 1, "exactly one cubic segment"
    assert route.path_d.count(" L ") == 2, "a stub at each end"


def test_the_path_starts_and_ends_on_the_anchors():
    route = route_arrow(PREDECESSOR, SUCCESSOR, "FS")
    assert route.tail == (PREDECESSOR.right, PREDECESSOR.y)
    assert route.tip == (SUCCESSOR.left, SUCCESSOR.y)
    assert route.path_d.startswith(f"M {PREDECESSOR.right:.8f} {PREDECESSOR.y:.8f}")
    assert route.path_d.endswith(f"L {SUCCESSOR.left:.8f} {SUCCESSOR.y:.8f}")


def test_the_stubs_leave_and_arrive_perpendicular_to_the_bars():
    """A stub on each end is what keeps the curve from cusping."""
    route = route_arrow(PREDECESSOR, SUCCESSOR, "FS")
    _start, exit_stub, entry_stub, _end = route.points

    assert exit_stub == (PREDECESSOR.right + DEFAULT_STUB, PREDECESSOR.y)
    assert entry_stub == (SUCCESSOR.left - DEFAULT_STUB, SUCCESSOR.y)


def test_the_curve_control_points_sit_on_the_horizontal_midline():
    """hCurveBetween's signature: both controls at the midpoint x."""
    route = route_arrow(PREDECESSOR, SUCCESSOR, "FS")
    _start, exit_stub, entry_stub, _end = route.points
    mid_x = (exit_stub[0] + entry_stub[0]) / 2

    curve = route.path_d.split(" C ")[1]
    numbers = [float(value) for value in curve.split(" L ")[0].split()]
    assert numbers[0] == pytest.approx(mid_x)
    assert numbers[1] == pytest.approx(exit_stub[1])
    assert numbers[2] == pytest.approx(mid_x)
    assert numbers[3] == pytest.approx(entry_stub[1])


def test_a_start_to_start_route_leaves_leftward():
    route = route_arrow(PREDECESSOR, SUCCESSOR, "SS")
    _start, exit_stub, _entry_stub, _end = route.points
    assert exit_stub[0] == pytest.approx(PREDECESSOR.left - DEFAULT_STUB)


def test_a_finish_to_finish_route_arrives_from_the_right():
    route = route_arrow(PREDECESSOR, SUCCESSOR, "FF")
    _start, _exit_stub, entry_stub, end = route.points
    assert entry_stub[0] == pytest.approx(SUCCESSOR.right + DEFAULT_STUB)
    assert end == (SUCCESSOR.right, SUCCESSOR.y)


def test_a_backward_link_is_the_same_construction():
    """The successor starts before the predecessor ends; the curve doubles back."""
    earlier = RowAnchor(left=100.0, right=150.0, y=30.0)
    route = route_arrow(PREDECESSOR, earlier, "FS")

    assert route.path_d.count(" C ") == 1
    assert route.tip == (earlier.left, earlier.y)
    _start, exit_stub, entry_stub, _end = route.points
    assert entry_stub[0] < exit_stub[0], "the curve runs back to the left"


def test_the_stub_route_is_a_straight_run_into_the_bar():
    route = stub_route(SUCCESSOR, length=12.0)
    assert route.head_dir == +1
    assert route.tip == (SUCCESSOR.left, SUCCESSOR.y)
    assert route.tail[0] < SUCCESSOR.left
    assert " C " not in route.path_d


def test_curved_path_is_built_from_the_labella_primitive():
    """The same helper the PIT leaders use, so the shapes cannot diverge."""
    from vendor.labella.renderer import hCurveBetween

    path = curved_path((0.0, 0.0), (4.0, 0.0), (16.0, 10.0), (20.0, 10.0))
    assert hCurveBetween([4.0, 0.0], [16.0, 10.0]) in path


# ── Drawing ───────────────────────────────────────────────────────────────


def linked_tasks() -> list[dict]:
    return [
        task(Task_Name="first", Source_ID="1", Start="20260202", End="20260204"),
        task(
            Task_Name="second", Source_ID="2", Start="20260209", End="20260211",
            Predecessors="1",
        ),
    ]


def test_a_link_draws_one_curved_path():
    renderer = render(linked_tasks())
    arrows = renderer.of_class(renderer.paths, "ec-dependency-arrow")
    assert len(arrows) == 1, "one path, not a route plus a drawn head"
    assert " C " in arrows[0]["path_d"]


def test_the_head_is_an_oriented_marker_not_drawn_segments():
    renderer = render(linked_tasks())
    arrow = renderer.of_class(renderer.paths, "ec-dependency-arrow")[0]
    assert arrow["marker_end"], "the arrowhead is an SVG marker"
    assert renderer.markers, "a marker def was injected"
    assert renderer.markers[0]["kind"] == "arrow-head"


def test_dependencies_can_be_switched_off():
    renderer = render(linked_tasks(), gantt_show_dependencies=False)
    assert renderer.of_class(renderer.paths, "ec-dependency-arrow") == []


def test_no_arrows_without_predecessor_data():
    renderer = render([task(Source_ID="1"), task(Source_ID="2")])
    assert renderer.of_class(renderer.paths, "ec-dependency-arrow") == []


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

    arrows = renderer.of_class(renderer.paths, "ec-dependency-arrow")
    assert arrows[0]["stroke"] == "crimson"
    assert arrows[0]["stroke_width"] == pytest.approx(2.0)


def test_a_dashed_arrow_keeps_a_solid_head():
    """The marker is a filled glyph, so the dash pattern cannot reach it."""
    rule = {
        "apply_to": ARROW_STYLE_TARGET,
        "style": {"stroke": "black", "stroke_dasharray": "4 2"},
    }
    renderer = render(linked_tasks(), theme_style_rules=[rule])
    arrow = renderer.of_class(renderer.paths, "ec-dependency-arrow")[0]
    assert arrow["stroke_dasharray"] == "4 2"
    assert arrow["marker_end"]
