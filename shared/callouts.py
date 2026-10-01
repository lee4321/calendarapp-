"""Where a callout's leader starts and ends, and how it is styled, for every callout view.

A leader runs from the event's dot on the axis to the near edge of its label
box.  It meets the box at the dot's own position along the axis when that falls
within the box, and at the nearest end of the box when it does not, so an
aligned box gets a perpendicular leader and a nudged box a slanted one.  It
leaves the axis heading away from it and arrives heading back toward it, which
is what lets the line engine put square stubs at both ends.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass

from config.theme_schema import LineSpec, Theme
from shared.orientation import Orientation, Side

Point = tuple[float, float]


@dataclass(frozen=True)
class LeaderEnds:
    start: Point
    end: Point
    start_heading: Point
    end_heading: Point


def leader_ends(
    dot: Point,
    box: tuple[float, float, float, float],
    side: Side,
    orientation: Orientation,
) -> LeaderEnds:
    """The leader of the label *box* ``(x, y, w, h)`` for the dot on the axis at *dot*."""
    x, y, w, h = box
    primary = side is Side.PRIMARY
    if orientation is Orientation.HORIZONTAL:
        # Primary is above the axis, so the box's near edge is its bottom.
        near = y + h if primary else y
        end = (min(max(dot[0], x), x + w), near)
        away = (0.0, -1.0) if primary else (0.0, 1.0)
    else:
        # Primary is right of the axis, so the box's near edge is its left.
        near = x if primary else x + w
        end = (near, min(max(dot[1], y), y + h))
        away = (1.0, 0.0) if primary else (-1.0, 0.0)
    return LeaderEnds(dot, end, away, (-away[0], -away[1]))


def leader_style(theme: Theme, side: Side, override: dict | None = None) -> LineSpec:
    """``lines.leader``, recoloured for *side*, then adjusted by a style rule's ``leader_override``."""
    spec = theme.lines.leader
    side_spec = theme.lines.leader_primary if side is Side.PRIMARY else theme.lines.leader_secondary
    if side_spec.color:
        spec = dataclasses.replace(spec, color=side_spec.color)
    if override:
        fields = {f.name: f for f in dataclasses.fields(LineSpec)}
        changes = {}
        for key, value in override.items():
            if key in fields and value is not None:
                # Rule styles arrive as written in YAML, where a number may be a string.
                changes[key] = float(value) if str(fields[key].type).startswith("float") else value
        spec = dataclasses.replace(spec, **changes)
    return spec


def evaluate_callout_style(engine, event):
    """The event's style result, with the rules for its leader and its box folded in.

    Rules aimed at ``box:event`` / ``box:duration`` colour the marker; a rule
    aimed at ``line:leader`` restyles this event's leader and one aimed at
    ``box:callout`` restyles its label box.  Both are carried as the
    ``leader_override`` and ``label_override`` the drawing code reads.
    """
    result = engine.evaluate_event(event)
    leader = engine.evaluate_target("line:leader", event)
    changes = {
        "color": leader.stroke_color,
        "width": leader.stroke_width,
        "opacity": leader.stroke_opacity,
        "dasharray": leader.stroke_dasharray,
        **(leader.leader_override or {}),
    }
    changes = {k: v for k, v in changes.items() if v is not None}
    if changes:
        result.leader_override = {**(result.leader_override or {}), **changes}
    box = engine.evaluate_target("box:callout", event)
    label = {
        "fill_color": box.fill_color,
        "fill_opacity": box.fill_opacity,
        "stroke_color": box.stroke_color,
        "stroke_width": box.stroke_width,
        "pattern": box.pattern,
        "pattern_opacity": box.pattern_opacity,
    }
    label = {k: v for k, v in label.items() if v is not None}
    if label:
        result.label_override = {**(result.label_override or {}), **label}
    return result
