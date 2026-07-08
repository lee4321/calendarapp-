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

from typing import Callable, Sequence

import arrow

from config.config import CalendarConfig
from renderers.glyph_cache import get_font_metrics
from renderers.text_utils import string_width
from shared.data_models import Event
from shared.labella_layout import (
    CalloutPlacement,
    layout_callouts as _layout_callouts_shared,
    resolve_font_path as _resolve_font_path,
)
from shared.orientation import Orientation, Side

__all__ = ["CalloutPlacement", "layout_callouts"]

# Horizontal padding added on each side of the measured text inside the
# label box. The default mirrors the visual feel of the legacy renderer
# without bloating dense layouts.
_LABEL_PAD_X: float = 6.0


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

    Thin wrapper over `shared.labella_layout.layout_callouts` that wires
    the timeline's config fields into the shared engine. See the shared
    module for full argument semantics.
    """
    return _layout_callouts_shared(
        events,
        axis_origin=axis_origin,
        axis_length=axis_length,
        orientation=orientation,
        side=side,
        pos_for_day=pos_for_day,
        node_width=lambda ev: _node_along_axis_extent(ev, config, orientation),
        node_height=lambda evs: _renderer_node_height(evs, config, orientation),
        density=float(config.timeline_labella_density),
        layer_gap=float(config.timeline_labella_layer_gap),
        min_pos=config.timeline_labella_min_pos,
        max_pos=config.timeline_labella_max_pos,
    )
