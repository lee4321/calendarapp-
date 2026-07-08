"""
Orientation + side primitives shared by the labella-driven callout visualizers (timeline, PIT).

The timeline supports two axis orientations and three label-side modes,
combined into four concrete labella directions:

    +------------+-----------+----------------------+-----------------+
    | orientation| side      | label position       | labella dir.    |
    +============+===========+======================+=================+
    | horizontal | primary   | above the axis       | "up"            |
    | horizontal | secondary | below the axis       | "down"          |
    | vertical   | primary   | right of the axis    | "right"         |
    | vertical   | secondary | left  of the axis    | "left"          |
    +------------+-----------+----------------------+-----------------+

`Side.BOTH` is a *render-time* mode handled by the caller: events are
partitioned and labella runs twice with opposing single-sided directions.
It is never passed to `labella_direction()` directly.
"""

from __future__ import annotations

from enum import StrEnum


class Orientation(StrEnum):
    """Axis orientation."""

    HORIZONTAL = "horizontal"
    VERTICAL = "vertical"


class Side(StrEnum):
    """Which side of the axis labels appear on.

    PRIMARY:   above (horizontal) / right (vertical)
    SECONDARY: below (horizontal) / left  (vertical)
    BOTH:      caller partitions events and runs twice with PRIMARY + SECONDARY
    """

    PRIMARY = "primary"
    SECONDARY = "secondary"
    BOTH = "both"


# Concrete labella `direction` strings — must match values accepted by
# `vendor/labella/renderer.py`. Keep in sync with that file.
_DIRECTION_MAP: dict[tuple[Orientation, Side], str] = {
    (Orientation.HORIZONTAL, Side.PRIMARY): "up",
    (Orientation.HORIZONTAL, Side.SECONDARY): "down",
    (Orientation.VERTICAL, Side.PRIMARY): "right",
    (Orientation.VERTICAL, Side.SECONDARY): "left",
}


def labella_direction(orient: Orientation, side: Side) -> str:
    """Map (orientation, side) → labella direction string.

    Raises ValueError if `side is Side.BOTH` — the caller must split first.
    """
    if side is Side.BOTH:
        raise ValueError(
            "labella_direction() requires a concrete side (PRIMARY or "
            "SECONDARY); split events before calling with BOTH."
        )
    return _DIRECTION_MAP[(orient, side)]


def axis_to_xy(
    pos: float,
    orient: Orientation,
    axis_origin: tuple[float, float],
) -> tuple[float, float]:
    """Map a 1-D axis-local position to absolute SVG (x, y).

    `axis_origin` is the (x, y) where pos == 0. For horizontal, increasing
    pos moves right; for vertical, increasing pos moves down (matches SVG
    Y-down convention).
    """
    ox, oy = axis_origin
    if orient is Orientation.HORIZONTAL:
        return (ox + pos, oy)
    return (ox, oy + pos)


def perp_offset(
    orient: Orientation,
    side: Side,
    distance: float,
) -> tuple[float, float]:
    """Vector perpendicular to the axis pointing toward the label side.

    `distance` is in SVG units. For PRIMARY: returns the offset that moves
    a point *away* from the axis on the primary side (up for horizontal,
    right for vertical). SECONDARY returns the negation.

    Raises ValueError if `side is Side.BOTH`.
    """
    if side is Side.BOTH:
        raise ValueError("perp_offset() requires a concrete side, not BOTH.")
    if orient is Orientation.HORIZONTAL:
        # Primary = above, which is -Y in SVG coordinates.
        sign = -1.0 if side is Side.PRIMARY else 1.0
        return (0.0, sign * distance)
    # Vertical: primary = right (+X).
    sign = 1.0 if side is Side.PRIMARY else -1.0
    return (sign * distance, 0.0)


def opposite(side: Side) -> Side:
    """Return the opposing single-sided value. Raises on BOTH."""
    if side is Side.PRIMARY:
        return Side.SECONDARY
    if side is Side.SECONDARY:
        return Side.PRIMARY
    raise ValueError("opposite() requires PRIMARY or SECONDARY, not BOTH.")
