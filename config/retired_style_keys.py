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
    # True when the old code read the key *before* the token, so the value
    # always won: the converted rule is then written even if the token
    # already sets the attribute.
    override: bool = False
    # "section.key" of another retired key whose value the old code used
    # when this one resolved to None.
    fallback: str | None = None
    # "section.key" of another retired key whose value the old code used
    # when this one resolved to None.
    fallback: str | None = None


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
    # timeline event text, axis dates and callout leaders.
    Retired("timeline.name_text", "font_name", "text:event_name", "font", "timeline", "Roboto-Bold"),
    Retired("timeline.name_text", "font_color", "text:event_name", "color", "timeline", "deepskyblue"),
    Retired("timeline.notes_text", "font_name", "text:event_notes", "font", "timeline", "RobotoCondensed-Bold"),
    Retired("timeline.notes_text", "font_color", "text:event_notes", "color", "timeline", "deepskyblue"),
    Retired("timeline.date", "font_family", "text:event_date", "font", "timeline", "Roboto-Bold"),
    Retired("timeline", "connector_stroke_dasharray", "line:grid", "dasharray", "timeline", None),
    # PIT labels fell back to the timeline fonts without consulting a token.
    Retired("timeline.name_text", "font_name", "text:event_name", "font", "pit", "Roboto-Bold", override=True),
    Retired(
        "timeline.notes_text", "font_name", "text:event_notes", "font", "pit", "RobotoCondensed-Bold", override=True
    ),
    # blockplan grid lines, band-row borders (which fell back to the grid),
    # heading labels and duration bars.
    Retired("blockplan", "grid_color", "line:grid", "color", "blockplan", "grey"),
    Retired("blockplan", "grid_line_width", "line:grid", "width", "blockplan", 1.0),
    Retired("blockplan", "grid_opacity", "line:grid", "opacity", "blockplan", 0.6),
    Retired("blockplan", "grid_dasharray", "line:grid", "dasharray", "blockplan", None),
    Retired(
        "blockplan", "timeband_line_color", "box:band", "stroke", "blockplan", None, fallback="blockplan.grid_color"
    ),
    Retired(
        "blockplan",
        "timeband_line_width",
        "box:band",
        "stroke_width",
        "blockplan",
        None,
        fallback="blockplan.grid_line_width",
    ),
    Retired(
        "blockplan",
        "timeband_line_opacity",
        "box:band",
        "stroke_opacity",
        "blockplan",
        None,
        fallback="blockplan.grid_opacity",
    ),
    Retired(
        "blockplan",
        "timeband_line_dasharray",
        "box:band",
        "dasharray",
        "blockplan",
        None,
        fallback="blockplan.grid_dasharray",
    ),
    Retired("blockplan", "header_label_color", "text:heading", "color", "blockplan", "black"),
    Retired("blockplan", "header_label_opacity", "text:heading", "opacity", "blockplan", 1.0),
    Retired("blockplan", "duration_fill_opacity", "box:duration", "fill_opacity", "blockplan", 0.35),
    Retired("blockplan", "duration_stroke_opacity", "box:duration", "stroke_opacity", "blockplan", 0.9),
    Retired("blockplan", "duration_stroke_width", "box:duration", "stroke_width", "blockplan", 1.0),
    # ...and the keys blockplan read ahead of its tokens.
    Retired("blockplan", "duration_stroke_color", "box:duration", "stroke", "blockplan", None, override=True),
    Retired("blockplan", "duration_stroke_dasharray", "box:duration", "dasharray", "blockplan", None, override=True),
    Retired("blockplan", "duration_date_color", "text:duration_date", "color", "blockplan", None, override=True),
    Retired(
        "blockplan",
        "duration_date_font",
        "text:duration_date",
        "font",
        "blockplan",
        "RobotoCondensed-Light",
        override=True,
    ),
    Retired("blockplan.notes_text", "font_name", "text:event_notes", "font", "blockplan", None, override=True),
    Retired("blockplan.notes_text", "font_color", "text:event_notes", "color", "blockplan", None, override=True),
)

#: Dotted theme paths that are rejected on load.
RETIRED_PATHS = frozenset(f"{r.section}.{r.key}" for r in RETIRED)
