"""
Deterministic packing for timeline point-event callouts.

The alternative to :mod:`visualizers.timeline.labella_adapter`, selected by
``timeline_events.placement: packed``.  Where labella solves for positions
with a force simulation and centres each box on the result, this module
lays boxes on a fixed grid of rows and aligns each one's leading edge with
its own start date, so a box says exactly which day it belongs to.

Everything is computed in **axis-local ``(u, v)``**: ``u`` runs along the
axis from its origin, ``v`` is distance *away* from the axis and is always
positive.  One formulation therefore serves all four orientation × side
combinations, and the spec's "lower left corner" generalises to *the corner
on the axis-facing edge at the start-date end* — ``(u_left, v_near)``.

The rules, in the order they are applied to each event:

1. The box's leading edge sits on the event's start date.
2. A box whose start date is within one box-length of the axis end cannot
   be drawn on its date without leaving the timeline, so it is pushed back
   to end flush with the axis end.  Its leader still leaves the axis
   perpendicular and lands somewhere along the box's axis-facing edge.
3. Rows are searched from the axis outward, so the earliest event in any
   collision stack ends up closest to the axis.
4. When every row is blocked at the date's own ``u``, the box is nudged
   along the axis to the first free slot on the row closest to the axis.
   Its leader is then straight but slanted — it still points at the right
   day.
5. When even that fails, the box is not drawn.  The placement comes back
   with ``placed=False``, carrying a leader that stops at the edge of the
   available room for the renderer to cap with the theme's missing icon,
   and the event is named in a warning.
"""

from __future__ import annotations

import logging
from bisect import insort
from dataclasses import dataclass
from typing import Callable, Sequence

import arrow

from config.config import CalendarConfig
from renderers.text_utils import string_width
from shared.data_models import Event
from shared.labella_layout import partition_for_both, resolve_font_path
from shared.orientation import Orientation, Side, axis_to_xy, perp_offset

logger = logging.getLogger(__name__)

__all__ = ["PackedPlacement", "pack_callouts", "resolve_box_size"]

#: Rows opened when the caller imposes no limit (``--shrink``).  High enough
#: that no realistic schedule reaches it, low enough to bound the search.
_UNBOUNDED_ROW_CAP = 512

#: Floor on a derived box width, for a chart whose events are all untitled.
_MIN_DERIVED_WIDTH = 24.0

#: Horizontal air added either side of the measured text when the theme
#: leaves ``box_width`` unset.  Mirrors the labella adapter's padding so the
#: two strategies derive comparable widths from the same events.
_DERIVED_PAD_X = 6.0


@dataclass(frozen=True)
class PackedPlacement:
    """One packed callout, ready for the renderer to draw.

    Field-compatible with :class:`shared.labella_layout.CalloutPlacement`
    so both strategies feed one conversion loop in the renderer, plus
    ``placed`` — false when the box did not fit anywhere and only its
    leader and the missing-box icon should be drawn.

    All coordinates are absolute SVG (Y-down) except ``leader_path_d``,
    which is axis-local and pairs with ``axis_origin`` via a
    ``<g transform="translate(ox,oy)">`` wrapper.
    """

    event: Event
    x_dot: float
    y_dot: float
    x_label: float
    y_label: float
    label_w: float
    label_h: float
    layer: int
    leader_path_d: str
    axis_origin: tuple[float, float]
    side: Side
    orientation: Orientation
    placed: bool = True


def resolve_box_size(
    events: Sequence[Event], config: CalendarConfig
) -> tuple[float, float]:
    """``(box_width, box_height)`` in SVG units, one size for every box.

    The theme's ``timeline_events.box_width`` / ``box_height`` win outright
    — the spec is that a box is never stretched to its contents, only its
    text is compressed to the box.  When a theme leaves the width unset one
    width is derived for the whole chart from the widest event, so the
    fixed-width invariant still holds.
    """
    height = float(
        config.timeline_event_box_height
        or config.timeline_labella_node_height
        or 24.0
    )

    configured = config.timeline_event_box_width
    if configured is not None and configured > 0:
        return float(configured), height

    name_path = resolve_font_path(config.timeline_name_text_font_name)
    notes_path = resolve_font_path(config.timeline_notes_text_font_name)
    name_size = float(config.timeline_name_text_font_size or 12.0)
    notes_size = float(config.timeline_notes_text_font_size or name_size * 0.85)

    def measure(text: str, path: str, size: float) -> float:
        if not text:
            return 0.0
        return (
            string_width(text, path, size)
            if path
            else len(text) * size * 0.5
        )

    # The text column is what has to hold the name and the notes; the icon
    # column is a fraction of the whole box, so the box is the text column
    # scaled back up by that fraction.
    text_ratio = max(0.05, 1.0 - _icon_column_ratio(config))
    widest = max(
        (
            max(
                measure(ev.task_name, name_path, name_size),
                measure(ev.notes or "", notes_path, notes_size),
            )
            for ev in events
        ),
        default=0.0,
    )
    return (
        max(widest / text_ratio + 2.0 * _DERIVED_PAD_X, _MIN_DERIVED_WIDTH),
        height,
    )


def _icon_column_ratio(config: CalendarConfig) -> float:
    """Share of the box's inner width given to the icon / date column."""
    ratio = getattr(config, "timeline_event_icon_column_ratio", 0.15)
    try:
        ratio = float(ratio)
    except (TypeError, ValueError):
        return 0.15
    # A column outside this band leaves one of the two with nothing to
    # draw in, which reads as a layout bug rather than a theme choice.
    return min(0.9, max(0.02, ratio))


def _row_gap(config: CalendarConfig) -> float:
    """Clear space between two adjacent rows of boxes."""
    configured = getattr(config, "timeline_event_row_gap", None)
    if configured is not None and float(configured) >= 0:
        return float(configured)
    return float(config.timeline_labella_layer_gap)


def _box_gap(config: CalendarConfig) -> float:
    """Clear space between two boxes sharing a row."""
    return max(0.0, float(getattr(config, "timeline_event_box_gap", 2.0) or 0.0))


def _marker_allowance(config: CalendarConfig) -> float:
    """Room the missing-box icon needs at the far end of a stopped leader.

    The leader for an unplaced box stops short by this much so the glyph the
    renderer centres there lands inside the drawable area instead of half
    over its edge.  The packer is what decides where a leader stops, so it
    is what has to know something sits at the end of it — the same reason
    ``_duration_row_extent`` lives beside the bar layout.
    """
    size = (
        getattr(config, "default_missing_icon_size", None)
        or getattr(config, "timeline_icon_size", None)
        or 8.0
    )
    return max(8.0, float(size)) / 2.0


def _conflicts(
    intervals: Sequence[tuple[float, float]],
    lo: float,
    hi: float,
    gap: float,
) -> bool:
    """True when ``[lo, hi]`` cannot join ``intervals`` at ``gap`` spacing."""
    return any(lo < b + gap and a < hi + gap for a, b in intervals)


def _first_free_u(
    intervals: Sequence[tuple[float, float]],
    u_from: float,
    width: float,
    gap: float,
    u_limit: float,
) -> float | None:
    """Smallest ``u >= u_from`` where a box of ``width`` fits this row.

    ``intervals`` is kept sorted by the caller, so one forward walk suffices:
    each interval the candidate still collides with pushes it past that
    interval's far edge.  Returns ``None`` when the row runs out of axis
    before a gap appears.
    """
    candidate = u_from
    for a, b in intervals:
        if b + gap <= candidate:
            continue
        if a >= candidate + width + gap:
            break
        candidate = b + gap
    if candidate + width > u_limit:
        return None
    return candidate


def _to_svg(
    u: float,
    v: float,
    orientation: Orientation,
    side: Side,
    axis_origin: tuple[float, float],
) -> tuple[float, float]:
    """Absolute SVG point for an axis-local ``(u, v)``."""
    x, y = axis_to_xy(u, orientation, axis_origin)
    dx, dy = perp_offset(orientation, side, v)
    return (x + dx, y + dy)


def _describe(event: Event) -> str:
    """Enough of an event to find it in the source data."""
    parts = [event.task_name or "(untitled)"]
    if event.wbs:
        parts.append(f"WBS {event.wbs}")
    parts.append(f"start {event.start}")
    if event.notes:
        notes = event.notes.strip()
        parts.append(f"notes {notes[:40]}{'…' if len(notes) > 40 else ''}")
    return ", ".join(parts)


def pack_callouts(
    events: Sequence[Event],
    *,
    axis_origin: tuple[float, float],
    axis_length: float,
    orientation: Orientation,
    side: Side,
    config: CalendarConfig,
    pos_for_day: Callable[[arrow.Arrow], float],
    min_layer_gap: float = 0.0,
    max_extent: float | None = None,
    label_bounds: tuple[float, float] | None = None,
) -> list[PackedPlacement]:
    """Place point-event callouts on a fixed grid of rows.

    Signature mirrors :func:`visualizers.timeline.labella_adapter.layout_callouts`
    so the renderer can pick a strategy without reshaping its call.

    ``min_layer_gap`` is the clearance the innermost row owes the axis tick
    labels drawn in the same band; ``max_extent`` is how far from the axis
    this side may reach (``None`` under ``--shrink``, where the viewBox
    grows to whatever the layout needs); ``label_bounds`` are the page edges
    along the axis, in absolute SVG.
    """
    if not events:
        return []

    if side is Side.BOTH:
        primary, secondary = partition_for_both(events)
        out: list[PackedPlacement] = []
        for concrete, group in ((Side.PRIMARY, primary), (Side.SECONDARY, secondary)):
            out.extend(
                pack_callouts(
                    group,
                    axis_origin=axis_origin,
                    axis_length=axis_length,
                    orientation=orientation,
                    side=concrete,
                    config=config,
                    pos_for_day=pos_for_day,
                    min_layer_gap=min_layer_gap,
                    max_extent=max_extent,
                    label_bounds=label_bounds,
                )
            )
        return out

    box_w, box_h = resolve_box_size(events, config)
    # A box's extents in axis-local terms: along the axis, and away from it.
    horizontal = orientation is Orientation.HORIZONTAL
    extent_u = box_w if horizontal else box_h
    extent_v = box_h if horizontal else box_w

    row_gap = _row_gap(config)
    box_gap = _box_gap(config)
    row_stride = extent_v + row_gap
    # The innermost row clears whichever is larger: the theme's row gap, or
    # the furniture the axis already draws in that band.
    v0 = max(row_gap, float(min_layer_gap))

    if max_extent is None:
        max_rows = _UNBOUNDED_ROW_CAP
    elif max_extent < v0 + extent_v:
        max_rows = 0
    else:
        max_rows = int((max_extent - v0 - extent_v) // row_stride) + 1

    # Axis-local bounds along the axis. Boxes stay inside the page; the
    # end-of-range clamp is measured against the axis end, which is where
    # the timeline's last date lives.
    origin_along = axis_origin[0] if horizontal else axis_origin[1]
    if label_bounds is not None:
        u_min = label_bounds[0] - origin_along
        u_max = label_bounds[1] - origin_along
    else:
        u_min, u_max = 0.0, axis_length
    clamp_edge = min(axis_length, u_max)

    ordered = sorted(
        events,
        key=lambda e: (
            e.start,
            e.priority,
            e.task_name.lower() if e.task_name else "",
        ),
    )

    rows: list[list[tuple[float, float]]] = [[] for _ in range(max(0, max_rows))]
    placements: list[PackedPlacement] = []

    for event in ordered:
        u_date = pos_for_day(_safe_day(event.start))
        # Rule 2: a box that would run off the end of the timeline is pushed
        # back to finish flush with it, rather than drawn where it cannot be
        # read.  Its date still falls within the box, so the leader stays
        # perpendicular.
        u_left = min(u_date, clamp_edge - extent_u)
        u_left = max(u_left, u_min)

        row, u_final = _find_slot(
            rows, u_left, extent_u, box_gap, min(clamp_edge, u_max)
        )

        if row is None:
            logger.warning(
                "timeline: no room for event box (%s); drawing the missing-box "
                "icon instead. Widen the page, shrink "
                "timeline_events.box_height, or reduce the events in range.",
                _describe(event),
            )
            placements.append(
                _unplaced(
                    event,
                    u_date=u_date,
                    v_edge=max(
                        v0,
                        float(max_extent or v0) - _marker_allowance(config),
                    ),
                    orientation=orientation,
                    side=side,
                    axis_origin=axis_origin,
                )
            )
            continue

        insort(rows[row], (u_final, u_final + extent_u))
        v_near = v0 + row * row_stride
        placements.append(
            _placed(
                event,
                u_date=u_date,
                u_left=u_final,
                v_near=v_near,
                extent_u=extent_u,
                extent_v=extent_v,
                row=row,
                orientation=orientation,
                side=side,
                axis_origin=axis_origin,
            )
        )

    return placements


def _find_slot(
    rows: list[list[tuple[float, float]]],
    u_left: float,
    extent_u: float,
    box_gap: float,
    u_limit: float,
) -> tuple[int | None, float]:
    """``(row, u)`` for a box, or ``(None, u_left)`` when nothing fits.

    Two passes, in the spec's order of preference.  The first keeps the box
    on its own date and climbs away from the axis looking for a free row —
    which is what puts same-dated events in one column and the earliest of
    them nearest the axis.  Only when the whole column is blocked does the
    second pass give up on the date alignment, sliding the box along the
    axis to the first free slot on the row *closest* to the axis.
    """
    if u_left + extent_u > u_limit:
        # Even alone the box will not fit between here and the end of the
        # axis, so no row can take it.
        return None, u_left

    for row, intervals in enumerate(rows):
        if not _conflicts(intervals, u_left, u_left + extent_u, box_gap):
            return row, u_left

    for row, intervals in enumerate(rows):
        nudged = _first_free_u(intervals, u_left, extent_u, box_gap, u_limit)
        if nudged is not None:
            return row, nudged

    return None, u_left


def _placed(
    event: Event,
    *,
    u_date: float,
    u_left: float,
    v_near: float,
    extent_u: float,
    extent_v: float,
    row: int,
    orientation: Orientation,
    side: Side,
    axis_origin: tuple[float, float],
) -> PackedPlacement:
    """Build the placement for a box that found a slot."""
    near_corner = _to_svg(u_left, v_near, orientation, side, axis_origin)
    far_corner = _to_svg(
        u_left + extent_u, v_near + extent_v, orientation, side, axis_origin
    )
    x_label = min(near_corner[0], far_corner[0])
    y_label = min(near_corner[1], far_corner[1])

    # One expression for all three leader cases.  When the date falls inside
    # the box's span — the aligned case and the end-of-range case alike —
    # the clamp is a no-op and the leader is perpendicular; only a nudged
    # box pulls the anchor to its corner and slants the line.
    u_anchor = min(max(u_date, u_left), u_left + extent_u)
    p0 = axis_to_xy(u_date, orientation, (0.0, 0.0))
    p1 = _to_svg(u_anchor, v_near, orientation, side, (0.0, 0.0))

    return PackedPlacement(
        event=event,
        x_dot=axis_to_xy(u_date, orientation, axis_origin)[0],
        y_dot=axis_to_xy(u_date, orientation, axis_origin)[1],
        x_label=x_label,
        y_label=y_label,
        label_w=abs(far_corner[0] - near_corner[0]),
        label_h=abs(far_corner[1] - near_corner[1]),
        layer=row,
        leader_path_d=f"M {p0[0]:.4f} {p0[1]:.4f} L {p1[0]:.4f} {p1[1]:.4f}",
        axis_origin=axis_origin,
        side=side,
        orientation=orientation,
        placed=True,
    )


def _unplaced(
    event: Event,
    *,
    u_date: float,
    v_edge: float,
    orientation: Orientation,
    side: Side,
    axis_origin: tuple[float, float],
) -> PackedPlacement:
    """Build the placement for a box that found no slot.

    The leader still leaves the axis on the event's date and runs out to the
    edge of the room this side had; the renderer caps it with the theme's
    missing-box icon, the same treatment a duration bar past its limit gets.
    """
    end = _to_svg(u_date, v_edge, orientation, side, axis_origin)
    p0 = axis_to_xy(u_date, orientation, (0.0, 0.0))
    p1 = _to_svg(u_date, v_edge, orientation, side, (0.0, 0.0))
    dot = axis_to_xy(u_date, orientation, axis_origin)

    return PackedPlacement(
        event=event,
        x_dot=dot[0],
        y_dot=dot[1],
        x_label=end[0],
        y_label=end[1],
        label_w=0.0,
        label_h=0.0,
        layer=-1,
        leader_path_d=f"M {p0[0]:.4f} {p0[1]:.4f} L {p1[0]:.4f} {p1[1]:.4f}",
        axis_origin=axis_origin,
        side=side,
        orientation=orientation,
        placed=False,
    )


def _safe_day(date_str: str) -> arrow.Arrow:
    try:
        return arrow.get(str(date_str)[:8], "YYYYMMDD")
    except (arrow.ParserError, ValueError, TypeError):
        return arrow.now().floor("day")
