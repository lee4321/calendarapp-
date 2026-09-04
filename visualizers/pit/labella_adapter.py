"""
PIT labella adapter — events → placed callouts.

The layout skeleton (Force/Renderer invocation, Side.BOTH partitioning,
placement records) lives in `shared/labella_layout.py`. This module
supplies the PIT-specific parts:

* label measurement from `pit_*` config fields, including the inline
  date line and the optional label icon (`extra_width_for_event`),
* the `PIT_MAX_EVENTS_PER_SIDE` density cap with a logged WARNING —
  over-budget layouts still render,
* placement post-processing: re-anchoring the label along the axis
  (`pit_leader_label_anchor`) and rewriting leader paths so they start
  and end with straight perpendicular stubs (`pit_leader_*_stub`).
"""

from __future__ import annotations

import logging
from dataclasses import replace
from typing import Callable, Sequence

import arrow

from config.config import CalendarConfig
from renderers.text_utils import string_width
from shared.data_models import Event
from shared.date_utils import format_arrow_date
from shared.labella_layout import (
    CalloutPlacement,
    append_perp_stub,
    layout_callouts as _layout_callouts_shared,
    partition_for_both as _partition_for_both,
    prepend_perp_stub,
    resolve_font_path as _resolve_font_path,
)
from shared.orientation import Orientation, Side

logger = logging.getLogger(__name__)

__all__ = [
    "PIT_MAX_EVENTS_PER_SIDE",
    "PITPlacement",
    "layout_pit_callouts",
]

# The PIT renderer consumes the shared placement record; the historical
# name is kept because the renderer and tests import it.
PITPlacement = CalloutPlacement

# Density safety cap from §10 of the plan. Above this, labella's Force
# can struggle to converge; we emit a WARNING but still render so the
# user can see what they asked for.
PIT_MAX_EVENTS_PER_SIDE: int = 80


_LABEL_PAD_X: float = 6.0

def _name_size(config: CalendarConfig) -> float:
    return float(config.pit_name_text_font_size or 11.0)


def _notes_size(config: CalendarConfig) -> float:
    return float(config.pit_notes_text_font_size or _name_size(config) * 0.85)


def _date_size(config: CalendarConfig) -> float:
    return float(
        getattr(config, "theme_pit_date_text_font_size", None)
        or _name_size(config) * 0.85
    )


def _inline_date(config: CalendarConfig) -> bool:
    """True when the event date is rendered inside the label box."""
    return getattr(config, "pit_date_placement", "inline") == "inline"


def _date_string(event: Event, config: CalendarConfig) -> str:
    """Formatted event date, or '' if it can't be parsed."""
    try:
        day = arrow.get(event.start, "YYYYMMDD")
        return format_arrow_date(day, config.pit_date_format)
    except Exception:
        return ""


def _label_icon_size(config: CalendarConfig) -> float:
    """Pixel size of the label-box icon glyph (longest viewBox side)."""
    explicit = getattr(config, "pit_label_icon_size", None)
    if explicit is not None and float(explicit) > 0:
        return float(explicit)
    return _name_size(config)


def _label_icon_gap(config: CalendarConfig) -> float:
    """Gap between the label icon's right edge and the name text."""
    return float(getattr(config, "pit_label_icon_gap", 4.0) or 0.0)


def _measured_text_width(
    event: Event,
    config: CalendarConfig,
    *,
    extra_name_width: float = 0.0,
) -> float:
    """Horizontal text extent of the longest line in the label.

    ``extra_name_width`` is appended to the *name* line only — the
    label icon (when present) is drawn left of the name on the same
    baseline, so notes and inline-date lines are unaffected.
    """
    name_path = _resolve_font_path(config.pit_name_text_font_name)
    notes_path = _resolve_font_path(config.pit_notes_text_font_name)
    name_size = _name_size(config)
    notes_size = _notes_size(config)

    name_w = (
        string_width(event.task_name, name_path, name_size)
        if name_path
        else len(event.task_name or "") * name_size * 0.5
    )
    name_w += max(0.0, float(extra_name_width))
    notes_w = 0.0
    if event.notes and config.include_notes:
        notes_w = (
            string_width(event.notes, notes_path, notes_size)
            if notes_path
            else len(event.notes) * notes_size * 0.5
        )
    date_w = 0.0
    if _inline_date(config):
        date_text = _date_string(event, config)
        date_path = _resolve_font_path(
            getattr(config, "theme_pit_date_text_font_name", None)
            or config.pit_name_text_font_name
        )
        date_size = _date_size(config)
        date_w = (
            string_width(date_text, date_path, date_size)
            if date_path
            else len(date_text) * date_size * 0.5
        )
    return max(name_w, notes_w, date_w)


def _line_height_extent(config: CalendarConfig) -> float:
    """Vertical extent of a single label box.

    One name line, plus an optional notes line, plus the date line when
    ``pit_date_placement == "inline"`` (so the box grows to fit it).
    """
    name_size = _name_size(config)
    notes_size = _notes_size(config)
    has_notes = config.include_notes
    extent = name_size * 1.2 + 4.0
    if has_notes:
        extent += notes_size * 1.2
    if _inline_date(config):
        extent += _date_size(config) * 1.2
    return extent


def _node_along_axis_extent(
    event: Event,
    config: CalendarConfig,
    direction: Orientation,
    *,
    extra_name_width: float = 0.0,
) -> float:
    """Return the value passed as `Node.width` to labella.

    Labella treats `Node.width` as the extent **along** the axis.
    Horizontal → measured text width + padding.
    Vertical   → label vertical height.
    """
    if direction is Orientation.HORIZONTAL:
        measured = (
            _measured_text_width(event, config, extra_name_width=extra_name_width)
            + 2.0 * _LABEL_PAD_X
        )
        return max(measured, 24.0)
    return _line_height_extent(config)


def _extra_width_fn(
    extra_width_for_event: Callable[[Event], float] | None,
) -> Callable[[Event], float]:
    """Wrap the optional per-event extra-width callback defensively."""

    def _extra(ev: Event) -> float:
        if extra_width_for_event is None:
            return 0.0
        try:
            return float(extra_width_for_event(ev) or 0.0)
        except Exception:
            return 0.0

    return _extra


def _renderer_node_height(
    events: Sequence[Event],
    config: CalendarConfig,
    direction: Orientation,
    *,
    extra_width_for_event: Callable[[Event], float] | None = None,
) -> float:
    """Per-layer extent perpendicular to the axis.

    Horizontal → label vertical height.
    Vertical   → widest text + padding (so all vertical labels align).
    """
    if direction is Orientation.HORIZONTAL:
        return max(_line_height_extent(config), config.pit_labella_node_height)

    extra = _extra_width_fn(extra_width_for_event)
    widest = max(
        (
            _measured_text_width(e, config, extra_name_width=extra(e))
            for e in events
        ),
        default=0.0,
    )
    return max(widest + 2.0 * _LABEL_PAD_X, 40.0)


def _re_anchor_and_stub(
    placements: list[CalloutPlacement],
    config: CalendarConfig,
    direction: Orientation,
) -> list[CalloutPlacement]:
    """PIT post-pass over shared placements: re-anchor labels, add stubs.

    Re-anchoring: labella reserves space centered on each node's
    currentPos, but its renderer reports the box origin (n.x / n.y) at
    currentPos itself — i.e. the leading edge. Shifting the box back onto
    currentPos ("center") makes the drawn geometry match labella's
    overlap model, so boxes that labella placed without collision
    actually render without collision.
    """
    anchor = getattr(config, "pit_leader_label_anchor", "center")
    end_stub = float(config.pit_leader_end_stub)
    start_stub = float(config.pit_leader_start_stub)

    out: list[CalloutPlacement] = []
    for p in placements:
        x_label, y_label = p.x_label, p.y_label
        # Re-anchor along the axis. Horizontal → shift x; vertical → y.
        if direction is Orientation.HORIZONTAL:
            if anchor == "center":
                x_label -= p.label_w / 2.0
            elif anchor == "end":
                x_label -= p.label_w
        else:
            if anchor == "center":
                y_label -= p.label_h / 2.0
            elif anchor == "end":
                y_label -= p.label_h

        leader = append_perp_stub(p.leader_path_d, direction, end_stub)
        leader = prepend_perp_stub(leader, direction, start_stub)

        out.append(
            replace(p, x_label=x_label, y_label=y_label, leader_path_d=leader)
        )
    return out


def layout_pit_callouts(
    events: Sequence[Event],
    *,
    axis_origin: tuple[float, float],
    axis_length: float,
    direction: Orientation,
    side: Side,
    config: CalendarConfig,
    pos_for_day: Callable[[arrow.Arrow], float],
    extra_width_for_event: Callable[[Event], float] | None = None,
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
        extra_width_for_event: Optional per-event extra width for the
            name line (label icon + gap).

    Returns:
        List of PITPlacement records. For BOTH, primary placements
        first, then secondary.
    """
    extra = _extra_width_fn(extra_width_for_event)

    def _warn_over_cap(side_events: Sequence[Event], concrete_side: Side) -> None:
        if len(side_events) > PIT_MAX_EVENTS_PER_SIDE:
            logger.warning(
                "PIT: %d events on %s side exceeds soft cap of %d; "
                "labella may not converge cleanly.",
                len(side_events), concrete_side.value, PIT_MAX_EVENTS_PER_SIDE,
            )

    placements = _layout_callouts_shared(
        events,
        axis_origin=axis_origin,
        axis_length=axis_length,
        orientation=direction,
        side=side,
        pos_for_day=pos_for_day,
        node_width=lambda ev: _node_along_axis_extent(
            ev, config, direction, extra_name_width=extra(ev)
        ),
        node_height=lambda evs: _renderer_node_height(
            evs, config, direction,
            extra_width_for_event=extra_width_for_event,
        ),
        density=float(config.pit_labella_density),
        layer_gap=float(config.pit_labella_layer_gap),
        on_side_events=_warn_over_cap,
    )
    return _re_anchor_and_stub(placements, config, direction)
