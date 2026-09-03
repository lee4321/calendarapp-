"""
Shared labella layout engine — events → placed callouts.

Both callout visualizers (timeline, PIT) place event labels along a date
axis using the vendored labella primitives (`Force`, `Node`, `Renderer`).
This module owns everything that is identical between them:

* the `CalloutPlacement` result record,
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
    min_pos: float | None,
    max_pos: float | None,
    on_side_events: Callable[[Sequence[Event], Side], None] | None,
) -> list[CalloutPlacement]:
    """One labella pass for a concrete side, at exactly the density given."""
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

    placements: list[CalloutPlacement] = []
    ox, oy = axis_origin
    for n in nodes:
        # node.x/y are top-left of the label rect in axis-local coords.
        # node.dx/dy are extents in (x, y). Convert to absolute SVG.
        x_dot, y_dot = axis_to_xy(n.idealPos, orientation, axis_origin)
        placements.append(
            CalloutPlacement(
                event=n.data,
                x_dot=x_dot,
                y_dot=y_dot,
                x_label=ox + n.x,
                y_label=oy + n.y,
                label_w=n.dx,
                label_h=n.dy,
                layer=n.getLayerIndex(),
                leader_path_d=renderer.generatePath(n),
                axis_origin=axis_origin,
                side=side,
                orientation=orientation,
            )
        )
    return placements


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
    rows: dict[tuple[float, float], list[tuple[float, float]]] = {}
    for p in placements:
        # Group by the coordinate perpendicular to the axis.
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

    for spans in rows.values():
        spans.sort()
        for (start, extent), (next_start, _) in pairwise(spans):
            if next_start < start + extent - _OVERLAP_TOLERANCE:
                return True
    return False


def _layout_one_side(
    events: Sequence[Event],
    **kwargs,
) -> list[CalloutPlacement]:
    """Lay out one side, opening more rows until no two labels collide.

    The requested density is honoured whenever it produces a clean layout —
    the common case, where this costs one pass and changes nothing.  When it
    does not, the density is relaxed step by step, which is what makes the
    distributor open another layer, until the labels are clear or the floor
    is reached.  Falling back to the last attempt keeps a too-dense timeline
    rendering rather than failing.
    """
    density = float(kwargs.pop("density"))
    placements = _run_labella(events, density=density, **kwargs)
    if not placements or not _same_row_overlap(placements):
        return placements

    # The hook (PIT's density warning) fires on the first pass only.
    kwargs["on_side_events"] = None
    for _ in range(_MAX_DENSITY_RELAXATIONS):
        density *= _DENSITY_RELAX_STEP
        if density < _MIN_DENSITY:
            break
        attempt = _run_labella(events, density=density, **kwargs)
        if not _same_row_overlap(attempt):
            return attempt
        placements = attempt
    return placements


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
    min_pos: float | None = None,
    max_pos: float | None = None,
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
        min_pos=min_pos,
        max_pos=max_pos,
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
