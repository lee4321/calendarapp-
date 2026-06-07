"""
PIT marker resolution + draw helpers.

Markers are the on-axis glyphs (one per event) where leader lines
originate. PIT supports two flavors:

* **Built-in shapes** — ``circle``, ``diamond``, ``square``,
  ``triangle``, ``star``. Drawn as native SVG primitives.
* **DB icons** — any name from the ``icons`` table in ``calendar.db``.
  Loaded via ``BaseSVGRenderer._resolve_icon_svg`` (already inherited),
  scaled to fit the longest viewBox side, centered on the marker
  position, and colorized by replacing ``fill="#000"`` /
  ``fill="black"`` with the resolved marker color.

Resolution precedence (per v5 plan §2):

  1. Per-event ``event.icon`` (DB column ``Icon``)
  2. Style-rule ``marker_icon: "name"`` (Phase 7 — not yet honored)
  3. Config default — ``pit_default_event_icon`` for non-milestones,
     ``pit_default_milestone_icon`` for milestones
  4. Built-in shape — circle for events, diamond for milestones

This module is the single source of truth for what shape/icon to draw;
the renderer calls ``resolve_marker`` then ``draw_marker``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

import drawsvg

from shared.data_models import Event

if TYPE_CHECKING:
    from config.config import CalendarConfig


# Built-in shapes recognized by draw_marker.
BUILTIN_SHAPES: frozenset[str] = frozenset({
    "circle", "diamond", "square", "triangle", "star",
})


@dataclass(frozen=True)
class MarkerSpec:
    """Resolved marker for one event.

    Either ``icon_svg`` is set (a DB icon's raw SVG markup) or
    ``shape`` names a built-in. Never both.
    """

    kind: str             # "icon" | "shape"
    shape: str = ""       # one of BUILTIN_SHAPES (when kind == "shape")
    icon_svg: str = ""    # raw SVG markup (when kind == "icon")
    css_class: str = ""   # ec-pit-event-marker / ec-milestone-marker

    @property
    def is_icon(self) -> bool:
        return self.kind == "icon"


# Pattern used to colorize a DB icon glyph. Mirrors the SVG-pattern
# colorization path used by the weekly day-box decoration code.
_FILL_REPLACE_RE = re.compile(
    r'fill\s*=\s*"(?:#000000|#000|black)"', re.IGNORECASE
)


def resolve_marker(
    event: Event,
    *,
    config: "CalendarConfig",
    icon_svg_map: dict[str, str] | None = None,
) -> MarkerSpec:
    """Pick the marker for one event using the precedence chain.

    Args:
        event: The Event being drawn.
        config: For the per-visualizer defaults
            (``pit_default_event_icon`` / ``pit_default_milestone_icon``).
        icon_svg_map: Optional preloaded icon name → SVG markup map.
            When None, only built-in shapes are returned.

    Returns:
        A MarkerSpec ready to hand to ``draw_marker``.
    """
    is_milestone = bool(event.milestone)
    css = "ec-milestone-marker" if is_milestone else "ec-pit-event-marker"

    # 1) Per-event icon override.
    if event.icon and icon_svg_map:
        key = str(event.icon).strip().lower()
        svg = icon_svg_map.get(key)
        if svg:
            return MarkerSpec(kind="icon", icon_svg=svg, css_class=css)

    # 2) Per-rule (Phase 7) — not honored yet.

    # 3) Config default for this event type.
    default_name = (
        config.pit_default_milestone_icon if is_milestone
        else config.pit_default_event_icon
    )
    if default_name and icon_svg_map:
        key = str(default_name).strip().lower()
        svg = icon_svg_map.get(key)
        if svg:
            return MarkerSpec(kind="icon", icon_svg=svg, css_class=css)

    # 4) Built-in shape.
    shape = "diamond" if is_milestone else "circle"
    return MarkerSpec(kind="shape", shape=shape, css_class=css)


def draw_marker(
    drawing,
    spec: MarkerSpec,
    x: float,
    y: float,
    *,
    size: float,
    color: str,
    strip_svg_wrapper,
) -> None:
    """Draw ``spec`` centered on (x, y) in absolute SVG coords.

    For built-in shapes ``size`` is treated as a bounding-box side; for
    icons ``size`` sets the longest viewBox side after scaling.

    The ``strip_svg_wrapper`` parameter is the inherited
    ``BaseSVGRenderer._strip_svg_wrapper`` static method; passing it in
    avoids a coupling between markers.py and svg_base.
    """
    if spec.is_icon:
        _draw_icon_marker(drawing, spec, x, y, size, color, strip_svg_wrapper)
        return
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


def _draw_icon_marker(
    drawing,
    spec: MarkerSpec,
    cx: float,
    cy: float,
    size: float,
    color: str,
    strip_svg_wrapper,
) -> None:
    """Draw a DB icon glyph centered on (cx, cy), longest side = size."""
    raw = spec.icon_svg or ""
    # Find the viewBox so we know how to scale.
    m = _VIEWBOX_RE.search(raw)
    if m:
        vw = float(m.group(3))
        vh = float(m.group(4))
        vx = float(m.group(1))
        vy = float(m.group(2))
    else:
        vw, vh, vx, vy = 100.0, 100.0, 0.0, 0.0

    longest = max(vw, vh) or 1.0
    scale = size / longest

    # Translate the (vx + vw/2, vy + vh/2) viewBox center to (cx, cy).
    tx = cx - (vx + vw / 2.0) * scale
    ty = cy - (vy + vh / 2.0) * scale

    inner = strip_svg_wrapper(raw)
    # Colorize: replace black fills with the resolved color so the glyph
    # picks up the theme/rule color.
    colored = _FILL_REPLACE_RE.sub(f'fill="{color}"', inner)

    drawing.append(drawsvg.Raw(
        f'<g transform="translate({tx:.2f},{ty:.2f}) scale({scale:.4f})" '
        f'class="{spec.css_class}">{colored}</g>'
    ))
