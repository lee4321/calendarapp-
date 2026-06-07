"""
PIT labella adapter — events → placed callouts.

Thin wrapper around the vendored labella primitives (`Force`, `Node`,
`Renderer`) that returns a list of `PITPlacement` records in absolute
SVG coordinates. The PIT renderer consumes the placements; it never
imports labella directly.

Mirrors `visualizers/timeline/labella_adapter.py` but:

* drops duration / rollup / WBS handling — PIT only renders single-day
  events and milestones,
* uses PIT-local config fields (`pit_labella_*`, `pit_name_text_*`,
  `pit_notes_text_*`) so PIT and timeline can be tuned independently,
* enforces the `PIT_MAX_EVENTS_PER_SIDE` density cap with a logged
  WARNING — over-budget layouts still render.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable, Sequence

import arrow

from config.config import CalendarConfig, get_font_path
from renderers.text_utils import string_width
from shared.data_models import Event
from vendor.labella import Force, Node, Renderer

# Reuse the timeline package's orientation primitives — they are pure and
# direction-agnostic.
from visualizers.timeline.orientation import (
    Orientation,
    Side,
    axis_to_xy,
    labella_direction,
    opposite,
)

logger = logging.getLogger(__name__)


# Density safety cap from §10 of the plan. Above this, labella's Force
# can struggle to converge; we emit a WARNING but still render so the
# user can see what they asked for.
PIT_MAX_EVENTS_PER_SIDE: int = 80


_LABEL_PAD_X: float = 6.0
_FALLBACK_FONT: str = "Roboto-Bold"


@dataclass(frozen=True)
class PITPlacement:
    """One labella-placed PIT callout, ready for the renderer to draw.

    All coordinates are absolute SVG (Y-down). The leader path is in
    labella's axis-local frame — pair it with `axis_origin` via a
    `<g transform="translate(ox,oy)">` wrapper when emitting markup.
    """

    event: Event
    # Marker (dot) on the axis where the leader originates.
    x_dot: float
    y_dot: float
    # Label box, top-left + extents.
    x_label: float
    y_label: float
    label_w: float
    label_h: float
    # Which row labella placed the label on (0 = closest to the axis).
    layer: int
    # Labella's bezier "d" string, in axis-local coords.
    leader_path_d: str
    # Origin (idealPos=0) of the axis in absolute SVG coords.
    axis_origin: tuple[float, float]
    side: Side
    direction: Orientation


def _resolve_font_path(name: str | None) -> str:
    """Resolve a font name to a TTF path, with fallback."""
    tried = name or _FALLBACK_FONT
    try:
        return get_font_path(tried)
    except KeyError:
        try:
            return get_font_path(_FALLBACK_FONT)
        except KeyError:
            return ""


def _name_size(config: CalendarConfig) -> float:
    return float(config.pit_name_text_font_size or 11.0)


def _notes_size(config: CalendarConfig) -> float:
    return float(config.pit_notes_text_font_size or _name_size(config) * 0.85)


def _measured_text_width(event: Event, config: CalendarConfig) -> float:
    """Horizontal text extent of the longest line in the label."""
    name_path = _resolve_font_path(config.pit_name_text_font_name)
    notes_path = _resolve_font_path(config.pit_notes_text_font_name)
    name_size = _name_size(config)
    notes_size = _notes_size(config)

    name_w = (
        string_width(event.task_name, name_path, name_size)
        if name_path
        else len(event.task_name or "") * name_size * 0.5
    )
    notes_w = 0.0
    if event.notes and getattr(config, "includenotes", False):
        notes_w = (
            string_width(event.notes, notes_path, notes_size)
            if notes_path
            else len(event.notes) * notes_size * 0.5
        )
    return max(name_w, notes_w)


def _line_height_extent(config: CalendarConfig) -> float:
    """Vertical extent of a single label box (one line + optional notes)."""
    name_size = _name_size(config)
    notes_size = _notes_size(config)
    has_notes = getattr(config, "includenotes", False)
    return name_size * 1.2 + (notes_size * 1.2 if has_notes else 0.0) + 4.0


def _node_along_axis_extent(
    event: Event, config: CalendarConfig, direction: Orientation
) -> float:
    """Return the value passed as `Node.width` to labella.

    Labella treats `Node.width` as the extent **along** the axis.
    Horizontal → measured text width + padding.
    Vertical   → label vertical height.
    """
    if direction is Orientation.HORIZONTAL:
        measured = _measured_text_width(event, config) + 2.0 * _LABEL_PAD_X
        return max(measured, 24.0)
    return _line_height_extent(config)


def _renderer_node_height(
    events: Sequence[Event], config: CalendarConfig, direction: Orientation
) -> float:
    """Per-layer extent perpendicular to the axis.

    Horizontal → label vertical height.
    Vertical   → widest text + padding (so all vertical labels align).
    """
    if direction is Orientation.HORIZONTAL:
        return max(_line_height_extent(config), config.pit_labella_node_height)
    widest = max(
        (_measured_text_width(e, config) for e in events),
        default=0.0,
    )
    return max(widest + 2.0 * _LABEL_PAD_X, 40.0)


def _partition_for_both(
    events: Sequence[Event],
) -> tuple[list[Event], list[Event]]:
    """Split events into (primary, secondary) by chronological alternation.

    Mirrors the timeline adapter's _partition_for_both so PIT and
    timeline produce the same balance pattern under Side.BOTH.
    """
    ordered = sorted(
        events,
        key=lambda e: (e.start, e.priority, (e.task_name or "").lower()),
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
    direction: Orientation,
    side: Side,
    config: CalendarConfig,
    pos_for_day: Callable[[arrow.Arrow], float],
) -> list[PITPlacement]:
    """Run labella for one concrete side and return placements."""
    if not events:
        return []
    if side is Side.BOTH:
        raise ValueError("_layout_one_side requires a concrete side")

    if len(events) > PIT_MAX_EVENTS_PER_SIDE:
        logger.warning(
            "PIT: %d events on %s side exceeds soft cap of %d; "
            "labella may not converge cleanly.",
            len(events), side.value, PIT_MAX_EVENTS_PER_SIDE,
        )

    direction_str = labella_direction(direction, side)
    node_height = _renderer_node_height(events, config, direction)
    layer_gap = float(config.pit_labella_layer_gap)

    # Build nodes.
    nodes: list[Node] = []
    for ev in events:
        try:
            day = arrow.get(ev.start, "YYYYMMDD")
        except (arrow.ParserError, ValueError):
            continue
        ideal = pos_for_day(day)
        width = _node_along_axis_extent(ev, config, direction)
        nodes.append(Node(idealPos=ideal, width=width, data=ev))

    if not nodes:
        return []

    force = Force(
        {
            "minPos": 0.0,
            "maxPos": axis_length,
            "density": float(config.pit_labella_density),
        }
    )
    force.nodes(nodes)
    force.compute()

    renderer = Renderer(
        {
            "layerGap": layer_gap,
            "nodeHeight": node_height,
            "direction": direction_str,
        }
    )
    renderer.layout(nodes)

    # Where the leader meets the box along the axis. labella reserves
    # space centered on each node's currentPos, but its renderer reports
    # the box origin (n.x / n.y) at currentPos itself — i.e. the leading
    # edge. Shifting the box back onto currentPos ("center") makes the
    # drawn geometry match labella's overlap model, so boxes that labella
    # placed without collision actually render without collision.
    anchor = getattr(config, "pit_leader_label_anchor", "center")

    placements: list[PITPlacement] = []
    ox, oy = axis_origin
    for n in nodes:
        x_label = ox + n.x
        y_label = oy + n.y
        label_w = n.dx
        label_h = n.dy

        # Re-anchor along the axis. Horizontal → shift x; vertical → y.
        if direction is Orientation.HORIZONTAL:
            if anchor == "center":
                x_label -= label_w / 2.0
            elif anchor == "end":
                x_label -= label_w
        else:
            if anchor == "center":
                y_label -= label_h / 2.0
            elif anchor == "end":
                y_label -= label_h

        x_dot, y_dot = axis_to_xy(n.idealPos, direction, axis_origin)
        leader = renderer.generatePath(n)

        placements.append(
            PITPlacement(
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
                direction=direction,
            )
        )
    return placements


def layout_pit_callouts(
    events: Sequence[Event],
    *,
    axis_origin: tuple[float, float],
    axis_length: float,
    direction: Orientation,
    side: Side,
    config: CalendarConfig,
    pos_for_day: Callable[[arrow.Arrow], float],
) -> list[PITPlacement]:
    """Return labella-placed PIT callouts for the given events.

    Args:
        events: Single-day events to place. Empty input → empty output.
        axis_origin: (x, y) where labella's idealPos=0 maps. For
            horizontal: left end of the axis. For vertical: top end.
        axis_length: Length of the axis in SVG units.
        direction: HORIZONTAL or VERTICAL.
        side: PRIMARY, SECONDARY, or BOTH. BOTH partitions events
            chronologically into alternating sides and runs labella
            twice with opposing directions.
        config: Supplies font names/sizes and labella tuning.
        pos_for_day: Maps an arrow Date to a 1-D axis position in
            [0, axis_length].

    Returns:
        List of PITPlacement records. For BOTH, primary placements
        first, then secondary.
    """
    if not events:
        return []

    if side is Side.BOTH:
        primary_events, secondary_events = _partition_for_both(events)
        primary = _layout_one_side(
            primary_events,
            axis_origin=axis_origin,
            axis_length=axis_length,
            direction=direction,
            side=Side.PRIMARY,
            config=config,
            pos_for_day=pos_for_day,
        )
        secondary = _layout_one_side(
            secondary_events,
            axis_origin=axis_origin,
            axis_length=axis_length,
            direction=direction,
            side=opposite(Side.PRIMARY),
            config=config,
            pos_for_day=pos_for_day,
        )
        return primary + secondary

    return _layout_one_side(
        events,
        axis_origin=axis_origin,
        axis_length=axis_length,
        direction=direction,
        side=side,
        config=config,
        pos_for_day=pos_for_day,
    )
