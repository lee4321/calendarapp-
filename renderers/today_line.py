"""The "today" mark, drawn the same way in every view.

The line is a perpendicular stroke across the content area at today's cell,
styled by ``lines.today``; its label by ``text.today_label``.  Whether and how
it shows comes from the theme's ``today`` block, and which day it is comes from
:mod:`shared.today`, so a pinned ``today.date`` moves it in every view at once.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from typing import Any

from config.config import get_font_path
from config.theme_schema import Theme, Today
from renderers.lines import draw_line
from renderers.text_utils import text_center_baseline
from shared.orientation import Side
from shared.span import Frame
from shared.today import resolve_today, today_position

#: Clear space between the line and its label, in points.
_LABEL_GAP = 3.0


def draw_today(
    renderer: Any,
    theme: Theme,
    frame: Frame,
    cross_lo: float,
    cross_hi: float,
    *,
    clock: Callable[[], date] = date.today,
) -> date | None:
    """Draw the today line between *cross_lo* and *cross_hi*; return the day drawn, or ``None``.

    Nothing is drawn when ``today.show`` is false or today falls outside the
    span.  A hidden day (a weekend in a weekdays-only chart) is marked on the
    next visible day.
    """
    spec = theme.today
    if not spec.show:
        return None
    today = resolve_today(spec.date, clock)
    along = today_position(today, frame.span)
    if along is None:
        return None

    lo, hi = _extent(spec, frame, cross_lo, cross_hi)
    draw_line(renderer, theme.lines.today, frame.xy(along, lo), frame.xy(along, hi), css_class="ec-today-line")
    if spec.label:
        _draw_label(renderer, theme, frame, along, lo, hi)
    return today


def _extent(spec: Today, frame: Frame, cross_lo: float, cross_hi: float) -> tuple[float, float]:
    """The run of the line across the axis, clamped to the content area.

    ``today.length`` 0 means the whole content area, otherwise that many points
    centred on the axis (``both``) or reaching out from it to one side.
    ``today.direction`` names a side of the axis, so it means the same thing
    beside a horizontal and a vertical axis.
    """
    axis = frame.cross
    primary_high = frame.sign(Side.PRIMARY) > 0
    toward_primary = (axis, cross_hi) if primary_high else (cross_lo, axis)
    toward_secondary = (cross_lo, axis) if primary_high else (axis, cross_hi)
    if spec.length == 0:
        lo, hi = {"primary": toward_primary, "secondary": toward_secondary}.get(spec.direction, (cross_lo, cross_hi))
    elif spec.direction == "primary":
        lo, hi = (axis, axis + spec.length) if primary_high else (axis - spec.length, axis)
    elif spec.direction == "secondary":
        lo, hi = (axis - spec.length, axis) if primary_high else (axis, axis + spec.length)
    else:
        lo, hi = axis - spec.length / 2.0, axis + spec.length / 2.0
    return max(lo, cross_lo), min(hi, cross_hi)


def _draw_label(renderer: Any, theme: Theme, frame: Frame, along: float, cross_lo: float, cross_hi: float) -> None:
    """The label sits just right of the line, at the start, middle or end of its run."""
    role = theme.text.today_label
    spec = theme.today
    font = role.font or theme.fonts.family
    if spec.label_position == "start":
        across = cross_lo + spec.label_offset + role.size / 2
    elif spec.label_position == "middle":
        across = (cross_lo + cross_hi) / 2
    else:
        across = cross_hi - spec.label_offset - role.size / 2
    x, y = frame.xy(along, across)
    renderer._draw_text(
        x + _LABEL_GAP,
        text_center_baseline(y, get_font_path(font), role.size),
        spec.label,
        font,
        role.size,
        fill=role.color,
        fill_opacity=role.opacity,
        anchor="start",
        css_class="ec-today-label",
    )
