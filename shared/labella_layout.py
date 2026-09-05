"""
Shared labella layout engine — events → placed callouts.

Both callout visualizers (timeline, PIT) place event labels along a date
axis using the vendored labella primitives (`Force`, `Node`, `Renderer`).
This module owns everything that is identical between them:

* the `CalloutPlacement` result record,
* the perpendicular-stub rewrites that straighten a leader's two ends,
* font-path resolution with fallback,
* chronological event partitioning for `Side.BOTH`,
* the Force/Renderer invocation skeleton and node→placement conversion.

What stays in each visualizer's adapter is the part that genuinely
differs: how a label's along-axis width and per-layer height are measured
(different config fields, PIT adds inline dates and label icons) and any
post-processing of placements (PIT re-anchors labels and rewrites leader
paths with perpendicular stubs).

The adapters inject their measurements as callables (`node_width`,
`node_height`) so this module never reads visualizer-specific config.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from itertools import pairwise
from typing import Callable, Sequence

import arrow

from config.config import get_font_path
from shared.data_models import Event
from shared.orientation import (
    Orientation,
    Side,
    axis_to_xy,
    labella_direction,
    opposite,
)
from vendor.labella import Force, Node, Renderer
from vendor.labella.renderer import hCurveBetween, moveTo, vCurveBetween

#: Overlap smaller than this is rounding, not a collision.
_OVERLAP_TOLERANCE = 0.01
#: How far the density drops per retry, how many retries, and the floor
#: below which relaxing further only adds rows without separating labels.
_DENSITY_RELAX_STEP = 0.8
_MAX_DENSITY_RELAXATIONS = 12
_MIN_DENSITY = 0.05

# Fallback font used when a configured font name is missing from the
# registry. Picked because the project's existing fallback chain ends here.
FALLBACK_FONT: str = "Roboto-Bold"


@dataclass(frozen=True)
class CalloutPlacement:
    """One labella-placed callout, ready for a renderer to draw.

    All coordinates are absolute SVG (Y-down). The leader path is in
    labella's axis-local frame; pair it with `axis_origin` via a
    `<g transform="translate(ox,oy)">` wrapper when emitting markup.
    """

    event: Event
    # Dot at the axis (where the leader originates).
    x_dot: float
    y_dot: float
    # Label box top-left.
    x_label: float
    y_label: float
    label_w: float
    label_h: float
    # Which row (away from axis) labella placed the label on.
    layer: int
    # Labella's path "d" string, in axis-local coords (axis at origin).
    leader_path_d: str
    # Origin (idealPos=0) of the axis in absolute SVG coords.
    axis_origin: tuple[float, float]
    side: Side
    orientation: Orientation


# Matches a signed int/float (incl. scientific notation) in an SVG path.
_PATH_NUM_RE = re.compile(r"-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?")


def append_perp_stub(
    path_d: str, direction: Orientation, stub: float
) -> str:
    """Make a leader's final segment a straight perpendicular stub.

    labella ends each leader with a cubic Bézier whose *endpoint tangent*
    is perpendicular to the axis, but the visible curve arrives at a
    shallow angle. An ``orient="auto"`` arrowhead orients to that exact
    endpoint tangent (perpendicular), so the head points straight at the
    box while the line comes in diagonally — they look detached.

    We pull the final cubic back by ``stub`` units along the perpendicular
    (toward the axis) and append a straight ``L`` to the original box
    endpoint. The last drawn segment is then genuinely perpendicular, so
    the arrowhead sits flush on it. labella always sets the final control
    point collinear with the endpoint on the perpendicular axis
    (``c2.x == ex`` horizontal / ``c2.y == ey`` vertical), so trimming the
    endpoint keeps the curve's exit tangent perpendicular — no cusp.

    Args:
        path_d: The leader path ``d`` string (ends with a cubic ``C``).
        direction: Axis orientation (horizontal → vary y; vertical → x).
        stub: Desired stub length in user units. ``<= 0`` is a no-op.

    Returns:
        The rewritten path, or the original if it can't be parsed or the
        final cubic has no perpendicular extent to trim.
    """
    if stub <= 0 or not path_d:
        return path_d
    i = path_d.rfind("C")
    if i < 0:
        return path_d
    head = path_d[:i]
    nums = _PATH_NUM_RE.findall(path_d[i + 1:])
    if len(nums) < 6:
        return path_d
    c1x, c1y, c2x, c2y, ex, ey = (float(v) for v in nums[-6:])

    if direction is Orientation.HORIZONTAL:
        # Perpendicular is vertical: trim along y, keep x.
        span = ey - c2y
        if span == 0:
            return path_d
        s = min(stub, 0.85 * abs(span))
        qx, qy = ex, ey - s * (1.0 if span > 0 else -1.0)
    else:
        # Perpendicular is horizontal: trim along x, keep y.
        span = ex - c2x
        if span == 0:
            return path_d
        s = min(stub, 0.85 * abs(span))
        qx, qy = ex - s * (1.0 if span > 0 else -1.0), ey

    return (
        f"{head}C {c1x:.8f} {c1y:.8f} {c2x:.8f} {c2y:.8f} "
        f"{qx:.8f} {qy:.8f} L {ex:.8f} {ey:.8f}"
    )


def prepend_perp_stub(
    path_d: str, direction: Orientation, stub: float
) -> str:
    """Make a leader's first segment a straight perpendicular stub.

    Mirror of :func:`append_perp_stub` on the axis side. labella's first
    cubic leaves the axis with a perpendicular tangent (``c1.x == sx`` for
    horizontal axes, ``c1.y == sy`` for vertical), but the visible curve
    bends away at a shallow angle. A ``marker_start`` rendered with
    ``orient="auto"`` aligns to that endpoint tangent (perpendicular) and
    appears detached from the curve.

    We insert an ``L`` from the original axis point to a point pulled
    ``stub`` units along the perpendicular (toward ``c1``), then start the
    cubic from that pulled point. Since ``c1`` is unchanged and remains
    collinear with the new start on the perpendicular axis, the curve's
    entry tangent stays perpendicular — no cusp.

    Args:
        path_d: The leader path ``d`` string (starts with ``M`` followed
            by a cubic ``C``).
        direction: Axis orientation (horizontal → vary y; vertical → x).
        stub: Desired stub length in user units. ``<= 0`` is a no-op.

    Returns:
        The rewritten path, or the original if it can't be parsed or the
        first cubic has no perpendicular extent to trim.
    """
    if stub <= 0 or not path_d:
        return path_d
    if not path_d.lstrip().startswith("M"):
        return path_d
    c_idx = path_d.find("C")
    if c_idx < 0:
        return path_d
    m_nums = _PATH_NUM_RE.findall(path_d[:c_idx])
    if len(m_nums) < 2:
        return path_d
    sx, sy = float(m_nums[-2]), float(m_nums[-1])

    # Locate the 6 numbers of the first cubic and the index just past them.
    tail_start = -1
    found = 0
    for m in _PATH_NUM_RE.finditer(path_d, c_idx + 1):
        found += 1
        if found == 6:
            tail_start = m.end()
            break
    if found < 6 or tail_start < 0:
        return path_d
    cubic_nums = _PATH_NUM_RE.findall(path_d[c_idx + 1:tail_start])
    c1x, c1y, c2x, c2y, ex, ey = (float(v) for v in cubic_nums[:6])
    tail = path_d[tail_start:]

    if direction is Orientation.HORIZONTAL:
        # Perpendicular is vertical: trim along y, keep x.
        span = c1y - sy
        if span == 0:
            return path_d
        s = min(stub, 0.85 * abs(span))
        qx, qy = sx, sy + s * (1.0 if span > 0 else -1.0)
    else:
        # Perpendicular is horizontal: trim along x, keep y.
        span = c1x - sx
        if span == 0:
            return path_d
        s = min(stub, 0.85 * abs(span))
        qx, qy = sx + s * (1.0 if span > 0 else -1.0), sy

    return (
        f"M {sx:.8f} {sy:.8f} L {qx:.8f} {qy:.8f} "
        f"C {c1x:.8f} {c1y:.8f} {c2x:.8f} {c2y:.8f} {ex:.8f} {ey:.8f}"
        f"{tail}"
    )


def resolve_font_path(font_name: str | None) -> str:
    """Resolve a config font name to a TTF path, with fallback."""
    name = font_name or FALLBACK_FONT
    try:
        return get_font_path(name)
    except KeyError:
        try:
            return get_font_path(FALLBACK_FONT)
        except KeyError:
            return ""


def partition_for_both(
    events: Sequence[Event],
) -> tuple[list[Event], list[Event]]:
    """Split events into (primary, secondary) lists for Side.BOTH.

    Chronological alternation keeps the layout balanced regardless of
    upstream sort order. Stable: equal-dated events retain their relative
    order within their side.
    """
    ordered = sorted(
        events,
        key=lambda e: (
            e.start,
            e.priority,
            (e.task_name or "").lower(),
        ),
    )
    primary, secondary = [], []
    for i, ev in enumerate(ordered):
        (primary if i % 2 == 0 else secondary).append(ev)
    return primary, secondary


#: Which coordinate of a path point runs perpendicular to the axis, and
#: which way is "away from the axis", per labella direction.
_PERPENDICULAR: dict[str, tuple[int, float]] = {
    "up": (1, -1.0),
    "down": (1, 1.0),
    "left": (0, -1.0),
    "right": (0, 1.0),
}


def _leader_path(
    renderer: Renderer, node: Node, direction: str, direct: bool
) -> str:
    """The leader for one node, routed directly or through its ancestors.

    labella threads a leader through the solved position of every ancestor
    stub, emitting a curve-and-line pair per layer, so a label eight rows up
    arrives with fifteen segments.  Worse than the count, those chains all
    run through the same congested channel and cross the boxes between —
    the ribbons of hatching over the middle rows are leaders, not borders.

    ``direct`` skips the chain and draws one curve from the axis dot to the
    label's own near edge: three segments once the perpendicular stubs are
    added, whatever the depth.  Row count is what makes a leader *long*;
    this is what stops it being *convoluted*.
    """
    if not direct:
        return renderer.generatePath(node)

    options = renderer.options
    gap = options["nodeHeight"] + options["layerGap"]
    # Matches Renderer.getWayPoints: the label's near edge sits one
    # node-height inside the layer's outer boundary.
    offset = (gap * (node.getLayerIndex() + 1)) - options["nodeHeight"]

    if direction in ("up", "down"):
        sign = -1.0 if direction == "up" else 1.0
        start = [node.idealPos, 0.0]
        end = [node.currentPos, sign * offset]
        return " ".join([moveTo(start), vCurveBetween(start, end)])

    sign = -1.0 if direction == "left" else 1.0
    start = [0.0, node.idealPos]
    end = [sign * offset, node.currentPos]
    return " ".join([moveTo(start), hCurveBetween(start, end)])


def _offset_leader_path(path_d: str, direction: str, offset: float) -> str:
    """Push every point of a leader except its axis end `offset` outward.

    Labella spends its ``layerGap`` twice: once as the gap between the axis
    and the first row, and again inside the stride between every pair of
    rows.  The timeline needs a wide first gap — the axis tick labels are
    drawn in it — but not a wide stride, and one knob sets both.  So labella
    is given the stride it should have and the extra first-row clearance is
    added here, by sliding the whole stack out and lengthening the one
    segment that reaches back to the axis.

    The path comes from ``Renderer.generatePath``, which emits
    ``CMD n n [n n n n]`` with a fixed format, so splitting on whitespace is
    exact.  Anything unparseable is returned untouched.
    """
    if not path_d or not offset:
        return path_d
    perpendicular = _PERPENDICULAR.get(direction)
    if perpendicular is None:
        return path_d
    index, sign = perpendicular
    shift = sign * offset

    tokens = path_d.split()
    out: list[str] = []
    pair = 0
    i = 0
    try:
        while i < len(tokens):
            if tokens[i].isalpha():
                out.append(tokens[i])
                i += 1
                continue
            point = [float(tokens[i]), float(tokens[i + 1])]
            # Pair 0 is the dot on the axis; it must not move.
            if pair:
                point[index] += shift
            out.extend("%.8f" % v for v in point)
            pair += 1
            i += 2
    except (IndexError, ValueError):
        return path_d
    return " ".join(out)


def _run_labella(
    events: Sequence[Event],
    *,
    axis_origin: tuple[float, float],
    axis_length: float,
    orientation: Orientation,
    side: Side,
    pos_for_day: Callable[[arrow.Arrow], float],
    node_width: Callable[[Event], float],
    node_height: Callable[[Sequence[Event]], float],
    density: float,
    layer_gap: float,
    stack_offset: float = 0.0,
    label_bounds: tuple[float, float] | None = None,
    direct_leaders: bool = False,
    min_pos: float | None = None,
    max_pos: float | None,
    on_side_events: Callable[[Sequence[Event], Side], None] | None,
) -> list[CalloutPlacement]:
    """One labella pass for a concrete side, at exactly the density given.

    ``stack_offset`` slides every row (and its leader) that much further
    from the axis, leaving the dot where it is. It buys first-row clearance
    without paying for it again in every row stride — see
    :func:`_offset_leader_path`.
    """
    if not events:
        return []
    if side is Side.BOTH:
        raise ValueError("_layout_one_side requires a concrete side")

    if on_side_events is not None:
        on_side_events(events, side)

    direction = labella_direction(orientation, side)

    # Build nodes.
    nodes: list[Node] = []
    for ev in events:
        try:
            day = arrow.get(ev.start, "YYYYMMDD")
        except (arrow.ParserError, ValueError):
            continue
        ideal = pos_for_day(day)
        nodes.append(Node(idealPos=ideal, width=node_width(ev), data=ev))

    if not nodes:
        return []

    force = Force(
        {
            "minPos": float(min_pos) if min_pos is not None else 0.0,
            "maxPos": float(max_pos) if max_pos is not None else axis_length,
            "density": float(density),
        }
    )
    force.nodes(nodes)
    force.compute()

    renderer = Renderer(
        {
            "layerGap": float(layer_gap),
            "nodeHeight": node_height(events),
            "direction": direction,
        }
    )
    renderer.layout(nodes)
    _clamp_labels_to_bounds(nodes, orientation, axis_origin, label_bounds)

    placements: list[CalloutPlacement] = []
    ox, oy = axis_origin
    index, sign = _PERPENDICULAR.get(direction, (1, 1.0))
    shift_x = sign * stack_offset if index == 0 else 0.0
    shift_y = sign * stack_offset if index == 1 else 0.0
    for n in nodes:
        # node.x/y are top-left of the label rect in axis-local coords.
        # node.dx/dy are extents in (x, y). Convert to absolute SVG.
        x_dot, y_dot = axis_to_xy(n.idealPos, orientation, axis_origin)
        placements.append(
            CalloutPlacement(
                event=n.data,
                x_dot=x_dot,
                y_dot=y_dot,
                x_label=ox + n.x + shift_x,
                y_label=oy + n.y + shift_y,
                label_w=n.dx,
                label_h=n.dy,
                layer=n.getLayerIndex(),
                leader_path_d=_offset_leader_path(
                    _leader_path(renderer, n, direction, direct_leaders),
                    direction,
                    stack_offset,
                ),
                axis_origin=axis_origin,
                side=side,
                orientation=orientation,
            )
        )
    return placements


def _clamp_labels_to_bounds(
    nodes: list[Node],
    orientation: Orientation,
    axis_origin: tuple[float, float],
    label_bounds: tuple[float, float] | None,
) -> None:
    """Pull any label whose box falls outside `label_bounds` back inside.

    ``label_bounds`` is (low, high) along the axis in absolute SVG units —
    the edges of the drawable page.

    Labella's own walls do constrain label positions, but its model treats
    ``currentPos`` as a label's *centre* while this codebase draws the box
    from that value as its leading edge.  A label solved right up against
    the wall therefore still puts most of a box-width past it, and on a page
    whose axis nearly spans the paper that is the difference between a whole
    box and a clipped one: a year on A4 lost 41.7pt off the right-hand box.

    Clamping ``currentPos`` rather than the finished placement is
    deliberate — the leader path is generated from it afterwards, so a label
    and its leader move together instead of coming apart.
    """
    if label_bounds is None:
        return
    low, high = label_bounds
    if high <= low:
        return
    # Axis-local: position p sits at origin + p along the axis.
    origin = (
        axis_origin[0] if orientation is Orientation.HORIZONTAL else axis_origin[1]
    )
    lo = low - origin
    hi = high - origin
    for node in nodes:
        room = hi - node.width
        if room < lo:
            # Wider than the page: hugging the low edge at least keeps the
            # box's leading corner and the start of its text on the paper.
            node.currentPos = lo
        else:
            node.currentPos = min(max(node.currentPos, lo), room)
        # Renderer.layout() already copied currentPos into the render
        # fields, so they have to be refreshed here.
        if orientation is Orientation.HORIZONTAL:
            node.x = node.currentPos
        else:
            node.y = node.currentPos


def _row_overlap_count(placements: Sequence[CalloutPlacement]) -> int:
    """Number of adjacent label pairs that overlap along the axis.

    A count, not a flag, because the retry loop needs to know whether
    relaxing the density is still *achieving* anything.  Two events on the
    same day can never be separated along the axis at any density, so a
    loop that only asks "is there any overlap left?" keeps opening rows for
    all the other labels in pursuit of a pair it will never fix.
    """
    total = 0
    for spans in _spans_by_row(placements).values():
        spans.sort()
        for (start, extent), (next_start, _) in pairwise(spans):
            if next_start < start + extent - _OVERLAP_TOLERANCE:
                total += 1
    return total


def _spans_by_row(
    placements: Sequence[CalloutPlacement],
) -> dict[tuple[float, float], list[tuple[float, float]]]:
    """Group label extents by the row they are drawn on."""
    rows: dict[tuple[float, float], list[tuple[float, float]]] = {}
    for p in placements:
        key = (
            (round(p.y_label, 3), 0.0)
            if p.orientation is Orientation.HORIZONTAL
            else (0.0, round(p.x_label, 3))
        )
        span = (
            (p.x_label, p.label_w)
            if p.orientation is Orientation.HORIZONTAL
            else (p.y_label, p.label_h)
        )
        rows.setdefault(key, []).append(span)
    return rows


def _same_row_overlap(placements: Sequence[CalloutPlacement]) -> bool:
    """True when two labels sharing a row overlap along the axis.

    Labella's distributor decides how many layers to use by comparing the
    *total* width of all labels against ``density * axis_length``.  That is a
    global capacity test: a set of labels whose total width fits one layer can
    still be impossible to place there when the events cluster in time, and
    the constraint solver then leaves them overlapping rather than opening
    another layer.  Rows are compared by drawn position, not by layer index,
    because a label's layer index and its final row do not always agree.
    """
    return _row_overlap_count(placements) > 0


def _stack_extent(placements: Sequence[CalloutPlacement]) -> float:
    """How far the deepest label reaches from the axis, box included."""
    worst = 0.0
    for p in placements:
        ox, oy = p.axis_origin
        if p.orientation is Orientation.HORIZONTAL:
            near, far = p.y_label - oy, p.y_label + p.label_h - oy
        else:
            near, far = p.x_label - ox, p.x_label + p.label_w - ox
        worst = max(worst, abs(near), abs(far))
    return worst


def _layout_one_side(
    events: Sequence[Event],
    **kwargs,
) -> list[CalloutPlacement]:
    """Lay out one side, opening rows only while that separates labels.

    The requested density is honoured whenever it produces a clean layout —
    the common case, where this costs one pass and changes nothing.  When it
    does not, the density is relaxed step by step, which is what makes the
    distributor open another row.

    Relaxing used to run until *no* pair overlapped, which sounds right and
    is not.  Labels are separated by sliding them along the axis, so two
    events on the same day overlap at every density until each owns a row —
    and chasing that one pair drags every other label along with it.  On a
    25-event year the stack went from 9 rows to 24 and the longest leader
    from 449pt to 1197pt, past the bottom of an 810pt page, to close a 5.6pt
    gap.  Rows bought nothing there because the labels they carried had
    already left the paper.

    So rows are spent while there is room to spend them.  ``max_extent`` is
    how far from the axis this side may reach; the search stops at the first
    attempt that would exceed it, since every later attempt is deeper still,
    and keeps the best layout that did fit — no overlap wins outright,
    otherwise fewest overlapping pairs.  With no ``max_extent`` (PIT does not
    supply one) the old unbounded search runs as before.
    """
    density = float(kwargs.pop("density"))
    max_extent = kwargs.pop("max_extent", None)
    best = _run_labella(events, density=density, **kwargs)
    if not best:
        return best
    best_overlaps = _row_overlap_count(best)
    if best_overlaps == 0:
        return best

    # The hook (PIT's density warning) fires on the first pass only.
    kwargs["on_side_events"] = None
    for _ in range(_MAX_DENSITY_RELAXATIONS):
        density *= _DENSITY_RELAX_STEP
        if density < _MIN_DENSITY:
            break
        attempt = _run_labella(events, density=density, **kwargs)
        if (
            max_extent is not None
            and max_extent > 0
            and _stack_extent(attempt) > max_extent
        ):
            break
        overlaps = _row_overlap_count(attempt)
        if overlaps == 0:
            return attempt
        if overlaps < best_overlaps:
            best, best_overlaps = attempt, overlaps
    return best


def layout_callouts(
    events: Sequence[Event],
    *,
    axis_origin: tuple[float, float],
    axis_length: float,
    orientation: Orientation,
    side: Side,
    pos_for_day: Callable[[arrow.Arrow], float],
    node_width: Callable[[Event], float],
    node_height: Callable[[Sequence[Event]], float],
    density: float,
    layer_gap: float,
    stack_offset: float = 0.0,
    label_bounds: tuple[float, float] | None = None,
    direct_leaders: bool = False,
    min_pos: float | None = None,
    max_pos: float | None = None,
    max_extent: float | None = None,
    on_side_events: Callable[[Sequence[Event], Side], None] | None = None,
) -> list[CalloutPlacement]:
    """Return labella-placed callouts for the given events.

    Args:
        events: Events to place. Empty input → empty output.
        axis_origin: (x, y) where labella's idealPos=0 maps to in SVG.
            For horizontal: the left end of the axis. For vertical: the
            top end.
        axis_length: Length of the axis in SVG units. Doubles as the
            default max_pos when `max_pos` is None.
        orientation: HORIZONTAL or VERTICAL.
        side: PRIMARY, SECONDARY, or BOTH. BOTH partitions events
            chronologically into alternating sides and runs labella twice
            with opposing directions.
        pos_for_day: Maps an arrow date to a 1-D axis position (must be in
            the [0, axis_length] range — or the [min_pos, max_pos] range
            if those are set).
        node_width: Along-axis extent of one event's label (labella
            `Node.width`). Horizontal axis → text width; vertical axis →
            line height. Supplied by the visualizer's adapter.
        node_height: Per-layer extent perpendicular to the axis for a
            side's events (labella `nodeHeight`). Supplied by the adapter.
        density / layer_gap / min_pos / max_pos: labella tuning values.
        stack_offset: Extra distance from the axis for every row, applied
            after layout so it does not inflate the row stride.
        label_bounds: (low, high) along the axis, in absolute SVG units, that
            every label box must lie within — normally the page edges. None
            leaves placement unclamped.
        direct_leaders: Draw each leader straight from its dot to its own
            label instead of threading it through the ancestor stubs — see
            `_leader_path`.
        max_extent: How far from the axis one side may reach, in SVG units.
            Caps how many rows the overlap search will open — see
            `_layout_one_side`. Applied to each side. None = uncapped.
        on_side_events: Optional hook invoked once per concrete side with
            (side_events, side) before layout — e.g. PIT's density-cap
            warning.

    Returns:
        List of CalloutPlacement in input order for single-sided runs;
        for BOTH, primary placements first, then secondary.
    """
    if not events:
        return []

    common = dict(
        axis_origin=axis_origin,
        axis_length=axis_length,
        orientation=orientation,
        pos_for_day=pos_for_day,
        node_width=node_width,
        node_height=node_height,
        density=density,
        layer_gap=layer_gap,
        stack_offset=stack_offset,
        label_bounds=label_bounds,
        direct_leaders=direct_leaders,
        min_pos=min_pos,
        max_pos=max_pos,
        max_extent=max_extent,
        on_side_events=on_side_events,
    )

    if side is Side.BOTH:
        primary_events, secondary_events = partition_for_both(events)
        primary = _layout_one_side(primary_events, side=Side.PRIMARY, **common)
        secondary = _layout_one_side(
            secondary_events, side=opposite(Side.PRIMARY), **common
        )
        return primary + secondary

    return _layout_one_side(events, side=side, **common)
