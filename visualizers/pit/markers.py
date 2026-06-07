"""
PIT marker resolution + draw helpers.

There are two distinct glyphs per event in PIT:

* **Axis marker** — the glyph drawn *on the axis* where the leader
  line originates. PIT no longer supports DB icons on the axis; the
  axis marker is always a built-in shape:

    - ``circle``  for ordinary events
    - ``diamond`` for milestones (``event.milestone == True``)

  ``resolve_marker`` returns the ``MarkerSpec`` for the axis glyph and
  ``draw_marker`` paints it.

* **Label icon** — an optional DB icon drawn *inside the label box*,
  on the same baseline as the event name and to its left. This is
  where per-event / per-rule / per-theme icons now live.

  ``resolve_label_icon`` returns the raw SVG markup for the icon (or
  ``None`` when no icon applies), and ``draw_label_icon`` paints it.

Resolution precedence for the **label icon** (highest → lowest):

  1. Per-event ``event.icon`` (DB column ``Icon``)
  2. Style-rule ``marker_icon: "name"`` from a matched StyleResult
  3. Config default — ``pit_default_event_icon`` for non-milestones,
     ``pit_default_milestone_icon`` for milestones
  4. None — no icon, label name starts at the left padding edge.

This module is the single source of truth for what shape/icon to draw;
the renderer calls ``resolve_marker`` + ``draw_marker`` for the axis
and ``resolve_label_icon`` + ``draw_label_icon`` for the label box.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

import drawsvg

from shared.data_models import Event
from shared.rule_engine import StyleResult

if TYPE_CHECKING:
    from config.config import CalendarConfig


# Built-in shapes recognized by draw_marker.
BUILTIN_SHAPES: frozenset[str] = frozenset({
    "circle", "diamond", "square", "triangle", "star",
})


@dataclass(frozen=True)
class MarkerSpec:
    """Resolved axis marker for one event.

    The axis marker is always a built-in shape — DB icons are rendered
    inside the label box (see ``resolve_label_icon``), never on the
    axis. ``kind`` is retained as ``"shape"`` to keep the dataclass
    shape stable for downstream consumers.
    """

    kind: str = "shape"   # always "shape" — retained for API stability
    shape: str = ""       # one of BUILTIN_SHAPES
    css_class: str = ""   # ec-pit-event-marker / ec-milestone-marker

    @property
    def is_icon(self) -> bool:
        # Axis markers are never icons. Kept for backward compatibility
        # with callers that branch on this property.
        return False


# Pattern used to colorize a DB icon glyph. Mirrors the SVG-pattern
# colorization path used by the weekly day-box decoration code.
_FILL_REPLACE_RE = re.compile(
    r'fill\s*=\s*"(?:#000000|#000|black)"', re.IGNORECASE
)


def resolve_marker(
    event: Event,
    *,
    config: "CalendarConfig" = None,           # kept for signature stability
    icon_svg_map: dict[str, str] | None = None, # ignored — axis uses shapes
    style_result: "StyleResult | None" = None,  # ignored — axis uses shapes
) -> MarkerSpec:
    """Pick the axis marker for one event.

    PIT axis markers are always built-in shapes:

      * ``diamond`` for milestones (``event.milestone == True``)
      * ``circle`` for ordinary events

    The ``config``, ``icon_svg_map``, and ``style_result`` parameters
    are retained for signature stability — callers may still pass them
    — but they no longer influence the axis glyph. DB icons now live
    inside the label box (see ``resolve_label_icon``).
    """
    is_milestone = bool(event.milestone)
    css = "ec-milestone-marker" if is_milestone else "ec-pit-event-marker"
    shape = "diamond" if is_milestone else "circle"
    return MarkerSpec(kind="shape", shape=shape, css_class=css)


def resolve_label_icon(
    event: Event,
    *,
    config: "CalendarConfig",
    icon_svg_map: dict[str, str] | None = None,
    style_result: "StyleResult | None" = None,
) -> str | None:
    """Return raw SVG markup for the event's label icon, or ``None``.

    Precedence (highest → lowest):

      1. Per-event ``event.icon`` (DB column)
      2. Per-rule ``marker_icon`` from ``style_result``
      3. Config default (``pit_default_event_icon`` /
         ``pit_default_milestone_icon``)
      4. None — no icon should be drawn in the label box.

    The returned string is the raw glyph SVG as stored in the
    ``icons`` table; ``draw_label_icon`` strips the outer ``<svg>``
    wrapper and colorizes the fills.
    """

    def _lookup(name: str) -> str | None:
        if not name or not icon_svg_map:
            return None
        return icon_svg_map.get(str(name).strip().lower())

    # 1) Per-event icon override.
    svg = _lookup(event.icon or "")
    if svg:
        return svg

    # 2) Per-rule marker_icon from StyleResult.
    rule_icon = getattr(style_result, "marker_icon", None) if style_result else None
    svg = _lookup(rule_icon or "")
    if svg:
        return svg

    # 3) Config default for this event type.
    is_milestone = bool(event.milestone)
    default_name = (
        config.pit_default_milestone_icon if is_milestone
        else config.pit_default_event_icon
    )
    svg = _lookup(default_name or "")
    if svg:
        return svg

    # 4) No icon.
    return None


def draw_marker(
    drawing,
    spec: MarkerSpec,
    x: float,
    y: float,
    *,
    size: float,
    color: str,
    strip_svg_wrapper=None,   # kept for signature stability; unused
) -> None:
    """Draw the axis marker (always a built-in shape) centered on (x, y)."""
    _draw_shape_marker(drawing, spec.shape, x, y, size, color, spec.css_class)


def _draw_shape_marker(
    drawing,
    shape: str,
    cx: float,
    cy: float,
    size: float,
    color: str,
    css_class: str,
) -> None:
    """Draw a built-in shape centered on (cx, cy)."""
    r = size / 2.0
    if shape == "circle":
        drawing.append(drawsvg.Circle(
            round(cx, 2), round(cy, 2), round(r, 2),
            fill=color, stroke="none", class_=css_class,
        ))
        return
    if shape == "square":
        drawing.append(drawsvg.Rectangle(
            round(cx - r, 2), round(cy - r, 2), round(size, 2), round(size, 2),
            fill=color, stroke="none", class_=css_class,
        ))
        return
    if shape == "diamond":
        # Rotated square — same area as the equivalent circle.
        pts = [
            (cx,     cy - r),
            (cx + r, cy),
            (cx,     cy + r),
            (cx - r, cy),
        ]
        d = "M " + " L ".join(f"{px:.2f},{py:.2f}" for px, py in pts) + " Z"
        drawing.append(drawsvg.Raw(
            f'<path d="{d}" fill="{color}" stroke="none" class="{css_class}"/>'
        ))
        return
    if shape == "triangle":
        # Upward-pointing equilateral.
        pts = [
            (cx,           cy - r),
            (cx + r * 0.866, cy + r * 0.5),
            (cx - r * 0.866, cy + r * 0.5),
        ]
        d = "M " + " L ".join(f"{px:.2f},{py:.2f}" for px, py in pts) + " Z"
        drawing.append(drawsvg.Raw(
            f'<path d="{d}" fill="{color}" stroke="none" class="{css_class}"/>'
        ))
        return
    if shape == "star":
        # 5-point star.
        import math
        pts: list[tuple[float, float]] = []
        for i in range(10):
            angle = -math.pi / 2 + i * math.pi / 5
            radius = r if i % 2 == 0 else r * 0.4
            pts.append((cx + radius * math.cos(angle), cy + radius * math.sin(angle)))
        d = "M " + " L ".join(f"{px:.2f},{py:.2f}" for px, py in pts) + " Z"
        drawing.append(drawsvg.Raw(
            f'<path d="{d}" fill="{color}" stroke="none" class="{css_class}"/>'
        ))
        return

    # Unknown shape: degrade to circle.
    drawing.append(drawsvg.Circle(
        round(cx, 2), round(cy, 2), round(r, 2),
        fill=color, stroke="none", class_=css_class,
    ))


# Extract a viewBox attribute value (returns (w, h)) from raw SVG markup.
_VIEWBOX_RE = re.compile(
    r'viewBox\s*=\s*"\s*([\d.\-]+)\s+([\d.\-]+)\s+([\d.\-]+)\s+([\d.\-]+)\s*"',
    re.IGNORECASE,
)


def draw_label_icon(
    drawing,
    icon_svg: str,
    x_left: float,
    y_center: float,
    *,
    size: float,
    color: str,
    strip_svg_wrapper,
    css_class: str = "ec-pit-label-icon",
) -> None:
    """Draw a DB icon glyph anchored to (x_left, y_center).

    ``x_left`` is the leftmost x of the glyph's bounding box;
    ``y_center`` is the vertical center the glyph is drawn around. The
    glyph is scaled so the longest viewBox side equals ``size`` and
    its black fills are recolored to ``color`` — same colorization
    path as the (legacy) axis-icon code.
    """
    cx = x_left + size / 2.0
    cy = y_center
    _draw_icon_at_center(
        drawing, icon_svg, cx, cy, size, color, strip_svg_wrapper, css_class,
    )


def _draw_icon_at_center(
    drawing,
    icon_svg: str,
    cx: float,
    cy: float,
    size: float,
    color: str,
    strip_svg_wrapper,
    css_class: str,
) -> None:
    """Shared scale-and-translate glyph emit, centered on (cx, cy)."""
    raw = icon_svg or ""
    m = _VIEWBOX_RE.search(raw)
    if m:
        vx = float(m.group(1))
        vy = float(m.group(2))
        vw = float(m.group(3))
        vh = float(m.group(4))
    else:
        vw, vh, vx, vy = 100.0, 100.0, 0.0, 0.0

    longest = max(vw, vh) or 1.0
    scale = size / longest

    tx = cx - (vx + vw / 2.0) * scale
    ty = cy - (vy + vh / 2.0) * scale

    inner = strip_svg_wrapper(raw)
    colored = _FILL_REPLACE_RE.sub(f'fill="{color}"', inner)

    drawing.append(drawsvg.Raw(
        f'<g transform="translate({tx:.2f},{ty:.2f}) scale({scale:.4f})" '
        f'class="{css_class}">{colored}</g>'
    ))


# ---------------------------------------------------------------------------
# Back-compat shim — older tests imported ``_draw_icon_marker`` directly.
# Now that the axis no longer draws icons, the symbol is repointed at the
# label-box drawing path so callers that just want to verify sizing still
# work. The (cx, cy) signature is preserved.
# ---------------------------------------------------------------------------
def _draw_icon_marker(
    drawing,
    spec: "MarkerSpec | object",
    cx: float,
    cy: float,
    size: float,
    color: str,
    strip_svg_wrapper,
) -> None:
    """Deprecated — kept so older tests still import successfully."""
    icon_svg = getattr(spec, "icon_svg", "") or ""
    _draw_icon_at_center(
        drawing, icon_svg, cx, cy, size, color,
        strip_svg_wrapper, "ec-pit-label-icon",
    )
