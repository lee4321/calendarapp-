"""
Gantt dependency arrows: resolution and curved-leader routing.

Links are resolved against ``events.source_id`` -- the identifier the
source system assigned -- and each one is drawn from the edge its type
implies:

    ┌──────────────┐
    │ predecessor  │──┐
    └──────────────┘  │   ┌──────────────┐
                      └──▶│ successor    │
                          └──────────────┘

======  =================  ==============================
type    exits predecessor  enters successor
======  =================  ==============================
FS      right edge         left edge, from the left
SS      left edge          left edge, from the left
FF      right edge         right edge, from the right
SF      right edge         left edge, from the right
======  =================  ==============================

Anchoring by type matters even though v1 ignores lag: in a real
schedule most overlapping work is expressed as ``SS``/``FF``, and
forcing those to finish-to-start geometry would draw correct schedules
as backward-running arrows.

Routing follows the PIT leader algorithm rather than the orthogonal
dogleg the requirements first described: a short perpendicular stub out
of the exit edge, a cubic bezier across the gap
(:func:`vendor.labella.renderer.hCurveBetween` -- control points on the
horizontal midline, so the curve leaves and arrives tangentially), and a
matching stub into the entry edge.  The stubs are what keep the curve
from forming a cusp where it meets a bar, exactly as
``pit/labella_adapter._append_perp_stub`` does for callout leaders.

The arrowhead is an SVG ``<marker>`` with ``orient="auto"``, so it points
along the curve's tangent instead of being fixed left or right.

A backward link -- successor starting before its predecessor ends -- is
the same construction; the curve simply doubles back.  No collision
avoidance is attempted, so arrows may cross other bars.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from shared.predecessors import Link, parse_links_with_rejects
from vendor.labella.renderer import lineTo as _lineTo, moveTo as _moveTo
from visualizers.gantt.details import (
    KIND_OFFCHART_DEPENDENCY,
    KIND_UNPARSEABLE_PREDECESSOR,
    KIND_UNRESOLVED_PREDECESSOR,
    GanttException,
)

#: Distance the route stands off from a bar edge before turning, in points.
DEFAULT_STUB = 4.0

#: ``apply_to`` target a theme uses to style dependency arrows.  Spelled
#: as a ``<kind>:<name>`` token because that is the only form the unified
#: theme parser accepts alongside ``element`` and ``lane``.
ARROW_STYLE_TARGET = "line:dependency_arrow"

#: Which edge each link type leaves and enters.  ``exit_dir`` and
#: ``entry_dir`` are +1 for the right side and -1 for the left, where
#: ``entry_dir`` is the side the arrow *approaches from*.
_ANCHORS: dict[str, tuple[str, int, str, int]] = {
    "FS": ("right", +1, "left", -1),
    "SS": ("left", -1, "left", -1),
    "FF": ("right", +1, "right", +1),
    "SF": ("right", +1, "left", +1),
}


@dataclass(frozen=True)
class RowAnchor:
    """Where a drawn row's mark sits, for arrows to attach to.

    Attributes:
        left: Left edge of the bar, bracket or glyph.
        right: Right edge of the same.
        y: Vertical center to enter and leave at.
    """

    left: float
    right: float
    y: float

    def edge(self, side: str) -> float:
        return self.right if side == "right" else self.left


@dataclass(frozen=True)
class ArrowRoute:
    """A curved leader: its SVG path plus where it starts and ends.

    ``head_dir`` is retained for callers that need to know which way the
    arrow travels, but the drawn arrowhead orients itself from the path
    tangent rather than from this value.
    """

    path_d: str
    points: list[tuple[float, float]]
    head_dir: int          # +1 when the head points right, -1 when left

    @property
    def tip(self) -> tuple[float, float]:
        return self.points[-1]

    @property
    def tail(self) -> tuple[float, float]:
        return self.points[0]


@dataclass(frozen=True)
class Dependency:
    """One resolved link, ready to draw.

    ``predecessor_index`` is ``None`` when the predecessor is not on the
    chart at all; the renderer then draws an unnumbered stub (answer 27)
    rather than a full arrow.
    """

    successor_index: int
    predecessor_index: int | None
    link_type: str
    ref: str


@dataclass(frozen=True)
class CrossPageReference:
    """One numbered cross-page reference.

    A number belongs to the *source event*, not to a single link: an event
    that cannot reach three successors gets one number, one stub, and
    stamps that number on all three successor rows.

    Attributes:
        number: 1-based, unique within the chart.
        icon: Icon name for *number*, resolved against the configured
            families.
        source_index: Row of the event the stub is drawn from.
        target_indexes: Rows that carry the icon in their reference column.
    """

    number: int
    icon: str
    source_index: int
    target_indexes: tuple[int, ...]


def resolve_dependencies(
    rows: list, drawn_indices: set[int]
) -> tuple[list[Dependency], list[GanttException]]:
    """Turn every row's predecessor cell into drawable dependencies.

    Args:
        rows: All :class:`~visualizers.gantt.rows.GanttRow` values for the
            chart, drawn or not.
        drawn_indices: Row indices actually on this page.  A predecessor
            that exists but is not drawn is off-chart, not missing.

    Returns:
        ``(dependencies, exceptions)``.  Dependencies are produced for
        successors that are themselves drawn; everything that could not
        be resolved is reported for the details page.
    """
    by_source_id: dict[str, int] = {}
    for row in rows:
        source_id = str(row.event.source_id or "").strip()
        if source_id and source_id not in by_source_id:
            by_source_id[source_id] = row.index

    dependencies: list[Dependency] = []
    exceptions: list[GanttException] = []

    for row in rows:
        if row.index not in drawn_indices:
            continue

        links, rejects = parse_links_with_rejects(row.event.predecessors)

        for token in rejects:
            exceptions.append(
                GanttException(
                    kind=KIND_UNPARSEABLE_PREDECESSOR,
                    task=row.event.task_name,
                    detail=f"could not read {token!r}",
                )
            )

        for link in links:
            dependency, exception = _resolve_one(
                link, row, by_source_id, drawn_indices
            )
            if dependency is not None:
                dependencies.append(dependency)
            if exception is not None:
                exceptions.append(exception)

    return dependencies, exceptions


def _resolve_one(
    link: Link,
    row,
    by_source_id: dict[str, int],
    drawn_indices: set[int],
) -> tuple[Dependency | None, GanttException | None]:
    """Resolve one link to a dependency, an exception, or both."""
    predecessor_index = by_source_id.get(link.ref)

    if predecessor_index is not None and predecessor_index in drawn_indices:
        return (
            Dependency(row.index, predecessor_index, link.type, link.ref),
            None,
        )

    # Drawn as a stub either way; only the reason differs.
    stub = Dependency(row.index, None, link.type, link.ref)

    if predecessor_index is None:
        return stub, GanttException(
            kind=KIND_UNRESOLVED_PREDECESSOR,
            task=row.event.task_name,
            detail=f"no task carries source_id {link.ref!r}",
        )

    return stub, GanttException(
        kind=KIND_OFFCHART_DEPENDENCY,
        task=row.event.task_name,
        detail=f"predecessor {link.ref!r} is not on this page",
    )


def icon_for_number(
    number: int,
    families: list[str],
    family_size: int,
    available: set[str] | None = None,
) -> str | None:
    """Icon name for a 1-based reference *number*, or None past the end.

    Families are consumed in order -- ``circle-`` 1-100, then
    ``darkcircle-`` 1-100, then ``square-`` 1-100 -- giving 300 references
    before numbering degrades (answer 1).

    Naming is padding-tolerant because the families disagree: ``circle-7``
    and ``square-7`` exist unpadded while ``darkcircle`` zero-pads its
    single digits (``darkcircle-07``).  Pass *available* (the icon cache's
    key set) to pick whichever spelling that family actually uses.
    """
    if number < 1 or family_size < 1:
        return None
    index = number - 1
    family_number = index // family_size
    if family_number >= len(families):
        return None

    prefix = families[family_number]
    within = index % family_size + 1
    candidates = (f"{prefix}{within}", f"{prefix}{within:02d}")
    if available is None:
        return candidates[0]
    for candidate in candidates:
        if candidate in available:
            return candidate
    return None


def assign_cross_page_references(
    dependencies: list[Dependency],
    same_page: "Callable[[int, int], bool]",
    families: list[str],
    family_size: int,
    available: set[str] | None = None,
) -> tuple[dict[int, CrossPageReference], list[Dependency]]:
    """Number the links whose two ends never share a page.

    Args:
        dependencies: Every resolved link in the chart.
        same_page: ``(row_a, row_b) -> bool`` — whether two rows are ever
            drawn together.  Pagination decides this, so it is a property
            of the chart rather than of one page.
        families: Icon-family prefixes, used in order.
        family_size: Numbers available per family.
        available: Icon names that actually exist, for padding tolerance.

    Returns:
        ``(references_by_source_row, unnumbered)`` — the numbered
        references keyed by the row their stub is drawn from, and the
        links that could not be numbered because they have no far end.
    """
    unnumbered = [d for d in dependencies if d.predecessor_index is None]

    targets: dict[int, list[int]] = {}
    for dependency in dependencies:
        source = dependency.predecessor_index
        if source is None or same_page(source, dependency.successor_index):
            continue
        # One entry per source event; successors accumulate under it.
        seen = targets.setdefault(source, [])
        if dependency.successor_index not in seen:
            seen.append(dependency.successor_index)

    references: dict[int, CrossPageReference] = {}
    number = 1
    for source in sorted(targets):
        icon = icon_for_number(number, families, family_size, available)
        if icon is None:
            # Numbering exhausted: the remaining stubs stay unnumbered.
            break
        references[source] = CrossPageReference(
            number=number,
            icon=icon,
            source_index=source,
            target_indexes=tuple(targets[source]),
        )
        number += 1

    return references, unnumbered


def route_arrow(
    predecessor: RowAnchor,
    successor: RowAnchor,
    link_type: str,
    stub: float = DEFAULT_STUB,
) -> ArrowRoute:
    """Route one arrow between two anchors, per the type's edges.

    The turn line sits clear of both the exit and the entry by *stub*, so
    a forward link runs out-across-in and a backward link folds the same
    three segments into a dogleg.
    """
    exit_side, exit_dir, entry_side, entry_dir = _ANCHORS.get(
        link_type.upper(), _ANCHORS["FS"]
    )

    exit_x = predecessor.edge(exit_side)
    entry_x = successor.edge(entry_side)

    # Stubs stand the curve off each bar so it meets the edge travelling
    # perpendicular to it -- the same trick PIT uses to avoid a cusp where
    # a leader meets its axis dot.
    exit_stub = (exit_x + exit_dir * stub, predecessor.y)
    entry_stub = (entry_x + entry_dir * stub, successor.y)

    return ArrowRoute(
        path_d=curved_path(
            (exit_x, predecessor.y), exit_stub, entry_stub, (entry_x, successor.y)
        ),
        points=[
            (exit_x, predecessor.y),
            exit_stub,
            entry_stub,
            (entry_x, successor.y),
        ],
        head_dir=-entry_dir,
    )


def curved_path(
    start: tuple[float, float],
    exit_stub: tuple[float, float],
    entry_stub: tuple[float, float],
    end: tuple[float, float],
) -> str:
    """``M`` start, ``L`` out to the stub, ``C`` across, ``L`` in to the end.

    The curve is :func:`vendor.labella.renderer.hCurveBetween`, the same
    primitive the PIT callout leaders are built from: a cubic whose
    control points sit on the horizontal midline between its endpoints,
    so it leaves and arrives horizontally.
    """
    from vendor.labella.renderer import hCurveBetween, lineTo, moveTo

    return " ".join(
        [
            moveTo(list(start)),
            lineTo(list(exit_stub)),
            hCurveBetween(list(exit_stub), list(entry_stub)),
            lineTo(list(end)),
        ]
    )


def stub_route(
    successor: RowAnchor, length: float, stub: float = DEFAULT_STUB
) -> ArrowRoute:
    """A short arrow into *successor* standing in for an off-chart predecessor.

    The renderer caps the far end with the off-chart icon (answer 27).
    """
    entry_x = successor.left
    tail = (entry_x - length - stub, successor.y)
    head = (entry_x, successor.y)
    return ArrowRoute(
        path_d=" ".join(
            [
                _moveTo(list(tail)),
                _lineTo(list(head)),
            ]
        ),
        points=[tail, head],
        head_dir=+1,
    )
