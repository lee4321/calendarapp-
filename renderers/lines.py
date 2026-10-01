"""One way to draw a line, for every view.

A :class:`config.theme_schema.LineSpec` describes a line (colour, width, dash,
markers at either end, stub segments, straight or curved).  This module turns a
spec plus two endpoints into SVG, so the axis, a tick, a callout leader, a gantt
dependency arrow, the today line and a border all go through the same code.

Geometry is separate from drawing: :func:`line_path` returns the ``d`` string,
:func:`line_svg` wraps it in a ``<path>``, and :func:`draw_line` appends it to a
renderer's drawing, registering any ``<marker>`` definition it needs.

Stubs
-----
A stub is a short straight segment kept square to the anchor at one end, so a
routed line leaves and meets its endpoints cleanly and an end marker sits flush
on a straight stretch instead of on the tail of a curve.  Each end has a
*heading*: the unit vector pointing away from the anchor into the line (a
callout above a horizontal axis leaves the axis dot heading ``(0, -1)``).  When
no heading is given it is the direction of travel.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any

import drawsvg

from config.theme_schema import LineSpec

if TYPE_CHECKING:
    from collections.abc import Sequence

Point = tuple[float, float]

#: Markers :class:`MarkerRegistry` can build.
MARKER_KINDS: frozenset[str] = frozenset({"arrow-head", "circle", "diamond", "square"})

#: Stubs never take more than this share of the distance between the endpoints.
_STUB_LIMIT = 0.45


def _fmt(v: float) -> str:
    """Three decimals, trailing zeros dropped (``4.000`` -> ``4``)."""
    return f"{v:.3f}".rstrip("0").rstrip(".")


def _pt(p: Point) -> str:
    return f"{_fmt(p[0])} {_fmt(p[1])}"


def _unit(dx: float, dy: float) -> Point:
    n = math.hypot(dx, dy)
    return (0.0, 0.0) if n == 0 else (dx / n, dy / n)


def _along(p: Point, heading: Point, distance: float) -> Point:
    return (p[0] + heading[0] * distance, p[1] + heading[1] * distance)


def line_path(
    spec: LineSpec,
    start: Point,
    end: Point,
    *,
    start_heading: Point | None = None,
    end_heading: Point | None = None,
) -> str:
    """The SVG path data for *spec* between *start* and *end*.

    ``route: straight`` runs start, stub, stub, end as straight segments.
    ``route: curve`` replaces the middle with one cubic whose control points sit
    along the two headings, so it leaves and arrives square to each anchor.
    """
    distance = math.dist(start, end)
    if distance == 0:
        return f"M {_pt(start)}"
    travel = _unit(end[0] - start[0], end[1] - start[1])
    h_start = start_heading or travel
    h_end = end_heading or (-travel[0], -travel[1])

    limit = _STUB_LIMIT * distance
    s_stub = min(spec.start_stub, limit)
    e_stub = min(spec.end_stub, limit)
    p1 = _along(start, h_start, s_stub) if s_stub > 0 else start
    p2 = _along(end, h_end, e_stub) if e_stub > 0 else end

    parts = [f"M {_pt(start)}"]
    if s_stub > 0:
        parts.append(f"L {_pt(p1)}")
    if spec.route == "curve":
        horizontal = abs(h_start[0]) >= abs(h_start[1])
        k = 0.5 * (abs(p2[0] - p1[0]) if horizontal else abs(p2[1] - p1[1]))
        parts.append(f"C {_pt(_along(p1, h_start, k))} {_pt(_along(p2, h_end, k))} {_pt(p2)}")
    elif p2 != p1:
        parts.append(f"L {_pt(p2)}")
    if e_stub > 0:
        parts.append(f"L {_pt(end)}")
    return " ".join(parts)


class MarkerRegistry:
    """The ``<marker>`` definitions a drawing needs, one per (kind, end, colour, size)."""

    def __init__(self, prefix: str = "line-marker") -> None:
        self.prefix = prefix
        self.defs: dict[str, str] = {}

    def ensure(self, kind: str, color: str, size: float, *, at_start: bool = False) -> str | None:
        """The id for this marker, defining it if new; ``None`` when nothing should be drawn."""
        if kind not in MARKER_KINDS or size <= 0 or color in ("none", ""):
            return None
        slug = "".join(ch for ch in color if ch.isalnum()) or "c"
        marker_id = f"{self.prefix}-{kind}-{'s' if at_start else 'e'}-{slug}-{_fmt(size).replace('.', '_')}"
        if marker_id not in self.defs:
            self.defs[marker_id] = _marker_xml(marker_id, kind, color, size, at_start)
        return marker_id


def _marker_xml(marker_id: str, kind: str, color: str, size: float, at_start: bool) -> str:
    s = float(size)
    if kind == "arrow-head":
        # The tip sits on the path's endpoint.  A start marker is the mirror image, so it points
        # away from the line without needing SVG 2's auto-start-reverse.
        if at_start:
            shape, ref_x = f"M {_fmt(s)} 0 L 0 {_fmt(s / 2)} L {_fmt(s)} {_fmt(s)} Z", 0.0
        else:
            shape, ref_x = f"M 0 0 L {_fmt(s)} {_fmt(s / 2)} L 0 {_fmt(s)} Z", s
        ref_y = s / 2
    else:
        ref_x = ref_y = s / 2
        if kind == "circle":
            shape = f"M {_fmt(s / 2)} 0 A {_fmt(s / 2)} {_fmt(s / 2)} 0 1 1 {_fmt(s / 2)} {_fmt(s)} A {_fmt(s / 2)} {_fmt(s / 2)} 0 1 1 {_fmt(s / 2)} 0 Z"
        elif kind == "diamond":
            shape = f"M {_fmt(s / 2)} 0 L {_fmt(s)} {_fmt(s / 2)} L {_fmt(s / 2)} {_fmt(s)} L 0 {_fmt(s / 2)} Z"
        else:
            shape = f"M 0 0 L {_fmt(s)} 0 L {_fmt(s)} {_fmt(s)} L 0 {_fmt(s)} Z"
    return (
        f'<marker id="{marker_id}" markerUnits="userSpaceOnUse" viewBox="0 0 {_fmt(s)} {_fmt(s)}" '
        f'markerWidth="{_fmt(s)}" markerHeight="{_fmt(s)}" refX="{_fmt(ref_x)}" refY="{_fmt(ref_y)}" orient="auto">'
        f'<path d="{shape}" fill="{color}" stroke="none"/></marker>'
    )


def stroke_attrs(spec: LineSpec) -> dict[str, Any]:
    """The stroke keywords of ``BaseSVGRenderer._draw_rect`` / ``_draw_line`` for *spec* (borders, grid lines)."""
    return {
        "stroke": spec.color,
        "stroke_width": spec.width,
        "stroke_opacity": spec.opacity,
        "stroke_dasharray": spec.dasharray,
    }


def line_svg(spec: LineSpec, path_d: str, markers: MarkerRegistry, *, css_class: str | None = None) -> str:
    """A ``<path>`` element for *path_d* styled by *spec*; empty for a ``none`` line."""
    if spec.color in ("none", "") or spec.width <= 0 or not path_d:
        return ""
    attrs = [
        f'd="{path_d}"',
        'fill="none"',
        f'stroke="{spec.color}"',
        f'stroke-width="{_fmt(spec.width)}"',
        f'stroke-opacity="{_fmt(spec.opacity)}"',
        f'stroke-linecap="{spec.linecap}"',
        f'stroke-linejoin="{spec.linejoin}"',
    ]
    if spec.dasharray:
        attrs.append(f'stroke-dasharray="{spec.dasharray}"')
    start_id = markers.ensure(spec.marker_start, spec.color, spec.marker_start_size, at_start=True)
    end_id = markers.ensure(spec.marker_end, spec.color, spec.marker_end_size)
    if start_id:
        attrs.append(f'marker-start="url(#{start_id})"')
    if end_id:
        attrs.append(f'marker-end="url(#{end_id})"')
    if css_class:
        attrs.append(f'class="{css_class}"')
    return "<path " + " ".join(attrs) + "/>"


def draw_line(
    renderer: Any,
    spec: LineSpec,
    start: Point,
    end: Point,
    *,
    start_heading: Point | None = None,
    end_heading: Point | None = None,
    css_class: str | None = None,
) -> None:
    """Append the line to *renderer*'s drawing, defining its markers once per drawing."""
    markers = _registry_for(renderer)
    known = set(markers.defs)
    svg = line_svg(
        spec,
        line_path(spec, start, end, start_heading=start_heading, end_heading=end_heading),
        markers,
        css_class=css_class,
    )
    if not svg:
        return
    for marker_id, xml in markers.defs.items():
        if marker_id not in known:
            renderer.drawing.append_def(drawsvg.Raw(xml))
    renderer.drawing.append(drawsvg.Raw(svg))


def draw_segments(
    renderer: Any,
    spec: LineSpec,
    segments: Sequence[tuple[float, float, float, float]],
    *,
    css_class: str | None = None,
) -> None:
    """Draw many plain ``(x1, y1, x2, y2)`` lines in one style (ticks, grid lines)."""
    for x1, y1, x2, y2 in segments:
        draw_line(renderer, spec, (x1, y1), (x2, y2), css_class=css_class)


def _registry_for(renderer: Any) -> MarkerRegistry:
    """The marker registry of the renderer's current drawing (a new drawing starts a new one)."""
    held = getattr(renderer, "_line_markers", None)
    if held is None or held[0] is not renderer.drawing:
        held = (renderer.drawing, MarkerRegistry())
        renderer._line_markers = held
    return held[1]
