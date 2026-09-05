"""
Adapter: events → labella-placed callouts for the timeline visualizer.

The layout skeleton (Force/Renderer invocation, Side.BOTH partitioning,
placement records) lives in `shared/labella_layout.py`. This module
supplies only the timeline-specific part: measuring label extents from
`timeline_*` config fields and forwarding labella tuning values.

Text measurement uses the project's PIL-based `string_width` — no LaTeX
dependency.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Callable, Sequence

import arrow

from config.config import CalendarConfig
from renderers.glyph_cache import get_font_metrics
from renderers.text_utils import string_width
from shared.data_models import Event
from shared.date_utils import format_arrow_date
from shared.labella_layout import (
    CalloutPlacement,
    append_perp_stub,
    layout_callouts as _layout_callouts_shared,
    prepend_perp_stub,
    resolve_font_path as _resolve_font_path,
)
from shared.orientation import Orientation, Side

__all__ = ["CalloutPlacement", "callout_date_extent", "layout_callouts"]

# Horizontal padding added on each side of the measured text inside the
# label box. The default mirrors the visual feel of the legacy renderer
# without bloating dense layouts.
_LABEL_PAD_X: float = 6.0

#: Gap between the title and the date that shares its line inside the box.
_DATE_GAP_X: float = 8.0


def callout_date_extent(
    date_label: str, font_name: str | None, font_size: float
) -> float:
    """Width the in-box date claims on the title line, gap included.

    The renderer reserves exactly this much when it fits the title, so the
    box measured here is the box drawn there.
    """
    if not date_label:
        return 0.0
    font_path = _resolve_font_path(font_name)
    width = (
        string_width(date_label, font_path, font_size)
        if font_path
        else len(date_label) * font_size * 0.5
    )
    return width + _DATE_GAP_X


def _measured_text_width(event: Event, config: CalendarConfig) -> float:
    """Horizontal extent the label's two columns need.

    The box is a narrow left column — the icon above the date — beside a
    text column holding the name above the notes.  Both text lines share one
    left edge, so the box needs the wider of them plus the left column; the
    date is what sizes that column, being wider than any icon.
    """
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
    return max(name_w, notes_w) + _date_extent_for(event, config)


def _date_extent_for(event: Event, config: CalendarConfig) -> float:
    """Width the event's in-box date adds to the title line."""
    try:
        day = arrow.get(str(event.start)[:8], "YYYYMMDD")
    except (arrow.ParserError, ValueError, TypeError):
        return 0.0
    label = format_arrow_date(day, config.timeline_date_format)
    # Mirrors TimelineRenderer._callout_metrics()'s date fallback.  A theme
    # that sets a larger text:event_date size is only visible to the renderer,
    # which then fits the title into whatever room is left — the title shrinks
    # slightly rather than the date colliding with it.
    # weekly_name_text_font_size is None until setfontsizes() runs, and the
    # layout is exercised without it in tests.
    base = (
        config.weekly_name_text_font_size
        or config.timeline_name_text_font_size
        or 12.0
    )
    size = max(8.0, float(base) * 0.95)
    return callout_date_extent(label, config.timeline_date_font, size)


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


def layout_callouts(
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
) -> list[CalloutPlacement]:
    """Return labella-placed callouts for the given events.

    Thin wrapper over `shared.labella_layout.layout_callouts` that wires
    the timeline's config fields into the shared engine. See the shared
    module for full argument semantics.

    ``min_layer_gap`` is a floor on the theme's layer gap. The innermost row
    of boxes sits exactly one layer gap off the axis, so the renderer uses
    this to keep that row clear of the axis tick labels drawn in the same
    band.

    ``max_extent`` is how far from the axis one side may reach — the room
    the page actually has. It caps how many rows the overlap search will
    open, which is what keeps leaders from growing past the paper.

    ``label_bounds`` are the page edges along the axis; no box is placed
    with any part of itself outside them.

    Each finished leader gets a straight perpendicular stub at both ends,
    the same post-pass PIT applies to its callout leaders — see
    :func:`shared.labella_layout.append_perp_stub`.
    """
    placements = _layout_callouts_shared(
        events,
        axis_origin=axis_origin,
        axis_length=axis_length,
        orientation=orientation,
        side=side,
        pos_for_day=pos_for_day,
        node_width=lambda ev: _node_along_axis_extent(ev, config, orientation),
        node_height=lambda evs: _renderer_node_height(evs, config, orientation),
        density=float(config.timeline_labella_density),
        # The theme's gap is the row stride; the axis-label clearance is a
        # one-off offset of the whole stack. Folding the clearance into the
        # gap, as this used to, charged it again for every row — a 24-row
        # stack paid ~26pt of tick-label clearance 24 times over.
        layer_gap=float(config.timeline_labella_layer_gap),
        stack_offset=max(
            0.0,
            float(min_layer_gap) - float(config.timeline_labella_layer_gap),
        ),
        min_pos=config.timeline_labella_min_pos,
        max_pos=config.timeline_labella_max_pos,
        max_extent=max_extent,
        label_bounds=label_bounds,
    )
    return _add_leader_stubs(placements, config, orientation)


def _add_leader_stubs(
    placements: list[CalloutPlacement],
    config: CalendarConfig,
    orientation: Orientation,
) -> list[CalloutPlacement]:
    """Straighten both ends of every leader with a perpendicular stub.

    labella's bezier leaves the axis dot and meets the box at a shallow
    angle, so a leader reads as grazing its anchors rather than arriving at
    them.  The stubs pull each end back along the perpendicular and finish
    the run with a straight segment, which is what makes the join look
    deliberate — and, where a theme turns markers on, gives an
    ``orient="auto"`` arrowhead a segment to sit flush on.
    """
    start_stub = float(config.timeline_leader_start_stub)
    end_stub = float(config.timeline_leader_end_stub)
    if start_stub <= 0 and end_stub <= 0:
        return placements

    out: list[CalloutPlacement] = []
    for p in placements:
        leader = append_perp_stub(p.leader_path_d, orientation, end_stub)
        leader = prepend_perp_stub(leader, orientation, start_stub)
        out.append(replace(p, leader_path_d=leader))
    return out
