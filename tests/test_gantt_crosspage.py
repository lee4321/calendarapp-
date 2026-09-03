"""Cross-page dependency references: numbering, the stub, and the Ref column.

When pagination separates a link's two ends, the link is numbered and the
number is drawn twice — at a stub leaving the source event, and in the
reference column of every successor it could not reach, on whichever page
that row lands.
"""

from __future__ import annotations

import pytest

from shared.data_models import Event
from test_gantt_marks import render, task
from visualizers.gantt.dependencies import (
    Dependency,
    assign_cross_page_references,
    icon_for_number,
)
from visualizers.gantt.details import KIND_OFFCHART_DEPENDENCY
from visualizers.gantt.rows import GanttRow

FAMILIES = ["circle-", "darkcircle-", "square-"]

#: The spellings the shipped icon table actually uses — `circle`/`square`
#: leave single digits bare, `darkcircle` zero-pads them.
AVAILABLE = (
    {f"circle-{n}" for n in range(1, 101)}
    | {f"darkcircle-{n:02d}" for n in range(1, 100)}
    | {"darkcircle-100"}
    | {f"square-{n}" for n in range(1, 101)}
)


# ── Icon numbering ────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "number,expected",
    [
        (1, "circle-1"),
        (100, "circle-100"),
        (101, "darkcircle-01"),   # second family, zero-padded spelling
        (109, "darkcircle-09"),
        (110, "darkcircle-10"),
        (200, "darkcircle-100"),
        (201, "square-1"),
        (300, "square-100"),
    ],
)
def test_families_are_consumed_in_order(number, expected):
    assert icon_for_number(number, FAMILIES, 100, AVAILABLE) == expected


def test_numbering_runs_out_after_the_last_family():
    assert icon_for_number(301, FAMILIES, 100, AVAILABLE) is None


def test_padding_is_only_used_when_the_bare_name_is_absent():
    """`circle-1` exists, so it is preferred over `circle-01`."""
    assert icon_for_number(1, ["circle-"], 100, AVAILABLE) == "circle-1"
    assert icon_for_number(1, ["darkcircle-"], 100, AVAILABLE) == "darkcircle-01"


def test_without_an_icon_inventory_the_bare_spelling_is_assumed():
    assert icon_for_number(7, FAMILIES, 100, None) == "circle-7"


@pytest.mark.parametrize("number", [0, -1])
def test_numbers_below_one_have_no_icon(number):
    assert icon_for_number(number, FAMILIES, 100, AVAILABLE) is None


# ── Assigning references ──────────────────────────────────────────────────


def link(successor: int, predecessor: int | None, link_type: str = "FS") -> Dependency:
    return Dependency(successor, predecessor, link_type, ref=str(predecessor))


def assign(dependencies, blocks: dict[int, int], **kwargs):
    """Assign references where *blocks* maps a row index to its page block."""
    return assign_cross_page_references(
        dependencies,
        lambda a, b: blocks.get(a) == blocks.get(b),
        kwargs.get("families", FAMILIES),
        kwargs.get("family_size", 100),
        AVAILABLE,
    )


def test_a_link_within_one_page_is_not_numbered():
    references, unnumbered = assign([link(1, 0)], {0: 0, 1: 0})
    assert references == {}
    assert unnumbered == []


def test_a_link_across_pages_is_numbered_on_its_source_event():
    references, _unnumbered = assign([link(9, 0)], {0: 0, 9: 9})
    assert list(references) == [0]
    reference = references[0]
    assert reference.number == 1
    assert reference.icon == "circle-1"
    assert reference.source_index == 0
    assert reference.target_indexes == (9,)


def test_one_number_covers_every_successor_an_event_cannot_reach():
    """Answer 3: one stub, one icon, stamped on each far row."""
    references, _unnumbered = assign(
        [link(9, 0), link(10, 0), link(11, 0)], {0: 0, 9: 9, 10: 9, 11: 9}
    )
    assert list(references) == [0]
    assert references[0].target_indexes == (9, 10, 11)
    assert references[0].number == 1


def test_a_repeated_pair_does_not_duplicate_a_target():
    references, _unnumbered = assign(
        [link(9, 0, "FS"), link(9, 0, "SS")], {0: 0, 9: 9}
    )
    assert references[0].target_indexes == (9,)


def test_separate_source_events_get_separate_numbers_in_row_order():
    references, _unnumbered = assign(
        [link(9, 3), link(9, 1)], {1: 0, 3: 0, 9: 9}
    )
    assert [(index, ref.number) for index, ref in sorted(references.items())] == [
        (1, 1), (3, 2),
    ]


def test_links_with_no_far_end_are_returned_unnumbered():
    references, unnumbered = assign([link(4, None)], {4: 0})
    assert references == {}
    assert [d.successor_index for d in unnumbered] == [4]


def test_numbering_stops_when_the_icons_run_out():
    """Exhaustion degrades quietly; it never wraps onto a used number."""
    dependencies = [link(100 + n, n) for n in range(4)]
    blocks = {n: 0 for n in range(4)} | {100 + n: 100 for n in range(4)}
    references, _unnumbered = assign(
        dependencies, blocks, families=["circle-"], family_size=2
    )
    assert sorted(ref.number for ref in references.values()) == [1, 2]


# ── Rendering ─────────────────────────────────────────────────────────────


def paged_tasks(count: int = 12) -> list[dict]:
    return [
        task(Task_Name=f"t{n}", Source_ID=str(n), WBS=f"1.{n}") for n in range(count)
    ]


def render_paged(tasks, tmp_path, **overrides):
    """Render tall rows so the chart needs several vertical pages."""
    return render(
        tasks,
        outputfile=str(tmp_path / "chart.svg"),
        gantt_row_height=40.0,
        **overrides,
    )


def test_a_cross_page_link_is_numbered_at_both_ends(tmp_path):
    tasks = paged_tasks()
    tasks[11]["Predecessors"] = "0"           # first row feeds the last
    renderer = render_paged(tasks, tmp_path)

    assert len(renderer._references) == 1
    reference = next(iter(renderer._references.values()))
    assert reference.icon == "circle-1"

    drawn = [icon for icon in renderer.icons if icon["icon"] == reference.icon]
    assert len(drawn) == 2, "one at the stub, one in the reference column"

    # The stub sits in the chart; the column icon sits in the task table.
    table_x, chart_x = renderer.table_x, renderer.chart_x
    assert min(i["x"] for i in drawn) < chart_x
    assert max(i["x"] for i in drawn) > chart_x
    assert min(i["x"] for i in drawn) >= table_x


def test_the_reference_is_reported_with_its_icon(tmp_path):
    tasks = paged_tasks()
    tasks[11]["Predecessors"] = "0"
    renderer = render_paged(tasks, tmp_path)

    entries = [e for e in renderer.exceptions if e.kind == KIND_OFFCHART_DEPENDENCY]
    assert len(entries) == 1
    assert entries[0].detail.startswith("circle-1: ")
    assert "t0" in entries[0].detail          # names the far end
    assert entries[0].task == "t11"


def test_one_event_feeding_several_off_page_rows_draws_one_stub(tmp_path):
    tasks = paged_tasks()
    for successor in (9, 10, 11):
        tasks[successor]["Predecessors"] = "0"
    renderer = render_paged(tasks, tmp_path)

    reference = next(iter(renderer._references.values()))
    assert reference.target_indexes == (9, 10, 11)

    drawn = [i for i in renderer.icons if i["icon"] == reference.icon]
    chart_x = renderer.chart_x
    stubs = [i for i in drawn if i["x"] > chart_x]
    column = [i for i in drawn if i["x"] < chart_x]
    assert len(stubs) == 1, "one stub however many successors"
    assert len(column) == 3, "every far row carries the number"


def test_a_same_page_link_still_draws_a_real_arrow(tmp_path):
    tasks = paged_tasks()
    tasks[1]["Predecessors"] = "0"            # adjacent rows, same page
    renderer = render_paged(tasks, tmp_path)

    assert renderer._references == {}
    assert renderer.of_class(renderer.paths, "ec-dependency-arrow")
    assert not [i for i in renderer.icons if i["icon"].startswith("circle-")]


def test_an_unresolvable_reference_stays_unnumbered(tmp_path):
    tasks = paged_tasks()
    tasks[11]["Predecessors"] = "999"
    renderer = render_paged(tasks, tmp_path)

    assert renderer._references == {}
    assert any(i["icon"] == "crosssquare" for i in renderer.icons)
    assert not [i for i in renderer.icons if i["icon"].startswith("circle-")]


def test_a_row_referenced_by_several_events_caps_its_icons(tmp_path):
    tasks = paged_tasks()
    tasks[11]["Predecessors"] = "0,1,2"       # three off-page sources
    renderer = render_paged(tasks, tmp_path, gantt_link_ref_max_icons=2)

    assert len(renderer._references) == 3
    assert renderer._reference_marks[11] == ["circle-1", "circle-2", "circle-3"]

    chart_x = renderer.chart_x
    in_column = [
        i for i in renderer.icons
        if i["x"] < chart_x and i["icon"].startswith("circle-")
    ]
    assert len(in_column) == 2, "capped by gantt_link_ref_max_icons"
