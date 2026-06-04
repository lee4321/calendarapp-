"""
Adapter: events → labella-placed callouts for the timeline visualizer.

Wraps the vendored labella primitives (`Force`, `Node`, `Renderer`) behind
a single `layout_callouts()` function that returns a list of
`CalloutPlacement` records in absolute SVG coordinates. The timeline
renderer consumes the placements; it never imports labella directly.

Text measurement uses the project's PIL-based `string_width` — no LaTeX
dependency.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Sequence

import arrow

from config.config import CalendarConfig, get_font_path
from renderers.glyph_cache import get_font_metrics
from renderers.text_utils import string_width
from shared.data_models import Event
from vendor.labella import Force, Node, Renderer

from visualizers.timeline.orientation import (
    Orientation,
    Side,
    axis_to_xy,
    labella_direction,
    opposite,
)

# Horizontal padding added on each side of the measured text inside the
# label box. The default mirrors the visual feel of the legacy renderer
# without bloating dense layouts.
_LABEL_PAD_X: float = 6.0

# Fallback font used when a configured font name is missing from the
# registry. Picked because the project's existing fallback chain ends here.
_FALLBACK_FONT: str = "Roboto-Bold"


@dataclass(frozen=True)
class CalloutPlacement:
    """One labella-placed callout, ready for the renderer to draw.

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


def _resolve_font_path(font_name: str | None) -> str:
    """Resolve a config font name to a TTF path, with fallback."""
    name = font_name or _FALLBACK_FONT
    try:
        return get_font_path(name)
    except KeyError:
        try:
            return get_font_path(_FALLBACK_FONT)
        except KeyError:
            return ""


def _measured_text_width(event: Event, config: CalendarConfig) -> float:
    """Horizontal text extent of the longest line in the label."""
    name_font_path = _resolve_font_path(config.timeline_name_text_font_name)
    notes_font_path = _resolve_font_path(config.timeline_notes_text_font_name)
    name_size = float(config.timeline_name_text_font_size or 12.0)
    notes_size = float(config.timeline_notes_text_font_size or name_size * 0.85)

    name_w = (
        string_width(event.task_name, name_font_path, name_size)
        if name_font_path else len(event.task_name or "") * name_size * 0.5
    )
    notes_w = 0.0
    if event.notes:
        notes_w = (
            string_width(event.notes, notes_font_path, notes_size)
            if notes_font_path else len(event.notes) * notes_size * 0.5
        )
    return max(name_w, notes_w)


def _line_height_extent(config: CalendarConfig) -> float:
    """Vertical extent of a single label box (name + notes lines combined).

    This is the perpendicular extent — perpendicular to the text reading
    direction. Used as the off-axis dimension for horizontal labels and
    as the along-axis dimension for vertical labels.
    """
    name_font_path = _resolve_font_path(config.timeline_name_text_font_name)
    name_size = float(config.timeline_name_text_font_size or 12.0)
    notes_size = float(config.timeline_notes_text_font_size or name_size * 0.85)
    if name_font_path:
        upm, asc, desc = get_font_metrics(name_font_path)
        line_h = (asc - desc) / upm * name_size
    else:
        line_h = name_size * 1.2
    return line_h + notes_size * 1.2 + 4.0


def _node_along_axis_extent(
    event: Event, config: CalendarConfig, orientation: Orientation
) -> float:
    """Return the size passed as `Node.width` to labella.

    Labella interprets `Node.width` as the extent **along** the axis
    direction. For a horizontal axis that's the label's horizontal text
    width; for a vertical axis it's the label's vertical (line) height.
    """
    if orientation is Orientation.HORIZONTAL:
        configured = config.timeline_event_box_width
        if configured is not None and configured > 0:
            return float(configured)
        measured = _measured_text_width(event, config) + 2.0 * _LABEL_PAD_X
        return max(measured, 24.0)
    # Vertical: along-axis extent is the box's vertical height.
    configured = config.timeline_event_box_height
    if configured is not None and configured > 0:
        return float(configured)
    return _line_height_extent(config)


def _renderer_node_height(
    events: Sequence[Event],
    config: CalendarConfig,
    orientation: Orientation,
) -> float:
    """Return the value passed to `Renderer.options["nodeHeight"]`.

    Labella interprets `nodeHeight` as the per-layer extent perpendicular
    to the axis. Horizontal axis → label vertical height; vertical axis →
    label horizontal text width (the same value for every label so that
    the column of labels lines up). For vertical we take the max measured
    text width across all events so the widest one fits.
    """
    if orientation is Orientation.HORIZONTAL:
        if config.timeline_event_box_height is not None and config.timeline_event_box_height > 0:
            return float(config.timeline_event_box_height)
        if config.timeline_labella_node_height > 0:
            return float(config.timeline_labella_node_height)
        return _line_height_extent(config)
    # Vertical: per-layer horizontal extent = widest text + padding.
    configured = config.timeline_event_box_width
    if configured is not None and configured > 0:
        return float(configured)
    widest = max(
        (_measured_text_width(e, config) for e in events),
        default=0.0,
    )
    return max(widest + 2.0 * _LABEL_PAD_X, 40.0)


def _partition_for_both(
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


def _layout_one_side(
    events: Sequence[Event],
    *,
    axis_origin: tuple[float, float],
    axis_length: float,
    orientation: Orientation,
    side: Side,
    config: CalendarConfig,
    pos_for_day: Callable[[arrow.Arrow], float],
) -> list[CalloutPlacement]:
    """Run labella for a single concrete side and return placements."""
    if not events:
        return []
    if side is Side.BOTH:
        raise ValueError("_layout_one_side requires a concrete side")

    direction = labella_direction(orientation, side)
    node_height = _renderer_node_height(events, config, orientation)
    layer_gap = float(config.timeline_labella_layer_gap)

    min_pos = (
        float(config.timeline_labella_min_pos)
        if config.timeline_labella_min_pos is not None
        else 0.0
    )
    max_pos = (
        float(config.timeline_labella_max_pos)
        if config.timeline_labella_max_pos is not None
        else axis_length
    )

    # Build nodes.
    nodes: list[Node] = []
    for ev in events:
        try:
            day = arrow.get(ev.start, "YYYYMMDD")
        except (arrow.ParserError, ValueError):
            continue
        ideal = pos_for_day(day)
        width = _node_along_axis_extent(ev, config, orientation)
        nodes.append(Node(idealPos=ideal, width=width, data=ev))

    if not nodes:
        return []

    force = Force(
        {
            "minPos": min_pos,
            "maxPos": max_pos,
            "density": float(config.timeline_labella_density),
        }
    )
    force.nodes(nodes)
    force.compute()

    renderer = Renderer(
        {
            "layerGap": layer_gap,
            "nodeHeight": node_height,
            "direction": direction,
        }
    )
    renderer.layout(nodes)

    placements: list[CalloutPlacement] = []
    ox, oy = axis_origin
    for n in nodes:
        # node.x/y are top-left of the label rect in axis-local coords.
        # node.dx/dy are extents in (x, y). Convert to absolute SVG.
        x_label = ox + n.x
        y_label = oy + n.y
        label_w = n.dx
        label_h = n.dy

        x_dot, y_dot = axis_to_xy(n.idealPos, orientation, axis_origin)
        leader = renderer.generatePath(n)

        placements.append(
            CalloutPlacement(
                event=n.data,
                x_dot=x_dot,
                y_dot=y_dot,
                x_label=x_label,
                y_label=y_label,
                label_w=label_w,
                label_h=label_h,
                layer=n.getLayerIndex(),
                leader_path_d=leader,
                axis_origin=axis_origin,
                side=side,
                orientation=orientation,
            )
        )
    return placements


def layout_callouts(
    events: Sequence[Event],
    *,
    axis_origin: tuple[float, float],
    axis_length: float,
    orientation: Orientation,
    side: Side,
    config: CalendarConfig,
    pos_for_day: Callable[[arrow.Arrow], float],
) -> list[CalloutPlacement]:
    """Return labella-placed callouts for the given events.

    Args:
        events: Events to place. Empty input → empty output.
        axis_origin: (x, y) where labella's idealPos=0 maps to in SVG.
            For horizontal: the left end of the axis. For vertical: the
            top end.
        axis_length: Length of the axis in SVG units. Doubles as the
            default max_pos when `config.timeline_labella_max_pos` is None.
        orientation: HORIZONTAL or VERTICAL.
        side: PRIMARY, SECONDARY, or BOTH. BOTH partitions events
            chronologically into alternating sides and runs labella twice
            with opposing directions.
        config: Supplies font names/sizes, labella tuning, override widths.
        pos_for_day: Maps an arrow Date to a 1-D axis position (must be in
            the [0, axis_length] range — or the configured min_pos/max_pos
            range if those are set).

    Returns:
        List of CalloutPlacement in input order for single-sided runs;
        for BOTH, primary placements first, then secondary.
    """
    if not events:
        return []

    if side is Side.BOTH:
        primary_events, secondary_events = _partition_for_both(events)
        primary = _layout_one_side(
            primary_events,
            axis_origin=axis_origin,
            axis_length=axis_length,
            orientation=orientation,
            side=Side.PRIMARY,
            config=config,
            pos_for_day=pos_for_day,
        )
        secondary = _layout_one_side(
            secondary_events,
            axis_origin=axis_origin,
            axis_length=axis_length,
            orientation=orientation,
            side=opposite(Side.PRIMARY),
            config=config,
            pos_for_day=pos_for_day,
        )
        return primary + secondary

    return _layout_one_side(
        events,
        axis_origin=axis_origin,
        axis_length=axis_length,
        orientation=orientation,
        side=side,
        config=config,
        pos_for_day=pos_for_day,
    )
