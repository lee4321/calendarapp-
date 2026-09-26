"""Section style keys retired in favour of ``style_rules`` tokens.

Each of these used to be read as a fallback beside a token: the renderer took
the token's attribute when the theme's rules set it and the section key (or its
built-in default) otherwise, so one style had two sources.  The keys are gone;
``tools/convert_style_keys.py`` moves a theme's values into token rules so the
theme renders as it did, and the theme loader rejects a theme that still carries
one of them.
"""

from __future__ import annotations

from typing import Any, NamedTuple


class Retired(NamedTuple):
    """One retired section key and where its value now lives."""

    section: str  # dotted section path, e.g. "weekly.day_box"
    key: str  # key within it, e.g. "stroke_color"
    token: str  # "<kind>:<name>", e.g. "box:cell"
    attr: str  # style attribute on the token, e.g. "stroke"
    visualizer: str  # visualizer the old code read it for
    default: Any  # the old built-in value when the theme did not set the key


RETIRED: tuple[Retired, ...] = (
    # weekly day boxes: box:cell, then weekly.day_box.stroke_*
    Retired("weekly.day_box", "stroke_color", "box:cell", "stroke", "weekly", "grey"),
    Retired("weekly.day_box", "stroke_opacity", "box:cell", "stroke_opacity", "weekly", 0.25),
    Retired("weekly.day_box", "stroke_width", "box:cell", "stroke_width", "weekly", 2),
    Retired("weekly.day_box", "stroke_dasharray", "box:cell", "dasharray", "weekly", None),
    # mini family (mini, mini-icon, candybar all resolve tokens as "mini"):
    # the day-cell grid, the milestone circle and the day-number font.
    Retired("mini_calendar", "grid_line_color", "line:grid", "color", "mini", "lightgrey"),
    Retired("mini_calendar", "grid_line_width", "line:grid", "width", "mini", 0.25),
    Retired("mini_calendar", "grid_line_opacity", "line:grid", "opacity", "mini", 0.5),
    Retired("mini_calendar", "grid_line_dasharray", "line:grid", "dasharray", "mini", None),
    Retired("mini_calendar", "milestone_stroke_width", "icon:milestone", "stroke_width", "mini", 1.0),
    Retired("mini_calendar", "milestone_stroke_opacity", "icon:milestone", "stroke_opacity", "mini", 1.0),
    Retired("mini_calendar", "cell_font", "text:day_number", "font", "mini", "JuliaMono-Regular"),
)

#: Dotted theme paths that are rejected on load.
RETIRED_PATHS = frozenset(f"{r.section}.{r.key}" for r in RETIRED)
