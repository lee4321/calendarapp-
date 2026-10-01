#!/usr/bin/env python
"""
Event Calendar configuration file
Sets default values that will be used unless overridden
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import arrow


def _default_theme_v3() -> Any:
    """A version-3.0 theme made only of schema defaults (what a config has before a theme is applied)."""
    from config.theme_schema import Theme, ThemeMeta

    return Theme(theme=ThemeMeta(name="default"))


def get_creation_date() -> str:
    """Format the creation date for use in the calendar."""
    return arrow.now().format("YYYY-MM-DD")


#: Default target for the largest dimension of a decoration pattern tile,
#: in document points.  Native tiles in the ``patterns`` table span 16 to
#: 1920 pt; this size makes a tile repeat several times across a weekly day
#: box (384 x 54 pt on a 1920 x 1080 page) instead of showing one crop.
#: Re-exported by renderers.svg_patterns, which owns tile geometry but
#: cannot be imported from here without a cycle.
DEFAULT_PATTERN_TARGET_SIZE = 18.0


# =============================================================================
# Font Name Constants
# =============================================================================


class Fonts:
    """Font name constants for calendar generation."""

    CLEAR_SANS = "ClearSans-Thin"
    LINEAR = "Linearicons"
    MPLUS = "mplus-1m-light"
    EMOJI = "android-emoji"

    # Roboto Condensed family
    RC_LIGHT = "RobotoCondensed-Light"
    RC_LIGHT_ITALIC = "RobotoCondensed-LightItalic"
    RC_BOLD = "RobotoCondensed-Bold"
    RC_BOLD_ITALIC = "RobotoCondensed-BoldItalic"
    RC_REGULAR = "RobotoCondensed-Regular"
    RC_ITALIC = "RobotoCondensed-Italic"

    # Roboto family
    R_REGULAR = "Roboto-Regular"
    R_ITALIC = "Roboto-Italic"
    R_BOLD = "Roboto-Bold"
    R_BOLD_ITALIC = "Roboto-BoldItalic"
    R_LIGHT = "Roboto-Light"
    R_LIGHT_ITALIC = "Roboto-LightItalic"

    # Julia
    J_REGULAR = "JuliaMono-Regular"
    J_ITALIC = "JuliaMono-RegularItalic"


# =============================================================================
# Calendar Configuration Dataclass
# =============================================================================


@dataclass
class CalendarConfig:
    """
    Configuration for calendar document generation.

    All properties have sensible defaults and can be overridden via CLI or programmatically.
    """

    # Document Metadata
    doc_title: str = field(default_factory=lambda: f"Calendar created {get_creation_date()}")
    doc_author: str = "A. Lee Ingram"
    command_line: str = ""
    embed_data: bool = False

    # Element styles bound from the theme's roles (config.role_styles), and the theme and
    # paper they were built for; rebuilt when either changes.
    theme_styles: Any = None
    theme_styles_key: Any = None

    # The theme (config/theme_schema.py): every decoration and structure value a view reads.
    theme_v3: Any = field(default_factory=lambda: _default_theme_v3())

    # Data source description (for header/footer expansion)
    events: str = ""

    # Page dimensions (set from papersize lookup)
    pageX: float = 0.0
    pageY: float = 0.0
    papersize: str = "Widescreen"
    orientation: str = "landscape"

    # Output file
    outputfile: str = ""
    # The run folder the CLI writes into (shared.run_paths.RunPaths).  None
    # when a caller renders straight to ``outputfile``, as tests do.
    run_paths: Any = None

    # Calendar date range (calculated from user input)
    adjustedstart: str = ""
    adjustedend: str = ""
    userstart: str = ""  # Raw user-provided start date (YYYYMMDD, before adjustments)
    userend: str = ""  # Raw user-provided end date (YYYYMMDD, before adjustments)
    duration: Any = 1  # Arrow timedelta
    numberofweeks: int = 0

    # Coordinate storage
    CalendarCoord: dict = field(default_factory=dict)
    maxrows: int = 0

    # Weekend style (0-4)
    weekend_style: int = 0

    # User-configurable weekend days (ISO weekday: 0=Mon .. 6=Sun).
    # When None, derived from ``weekend_style`` — style 0 → no weekends shown,
    # styles 1–4 → [5, 6] (Sat/Sun).  Explicit values override and are used by
    # the day classifier so international weekend conventions work
    # (e.g. ``[4, 5]`` for Fri/Sat).  Does not change layout geometry.
    weekend_days: list[int] | None = None

    # ISO 3166-1 alpha-2 country code(s) for government holiday loading.
    # Accepts a single code ("US"), a comma-separated list ("US,CA,GB"), or
    # None (loads the default set — US and CA — via load_python_holidays).
    # Parsed into individual codes at use-time by _parse_country_codes() in db_access.py.
    country: str | None = None

    # Fiscal calendar settings
    fiscal_calendar_type: str | None = None  # "nrf-454", "nrf-445", "nrf-544", "13-period"
    fiscal_show_period_labels: bool = True
    fiscal_show_quarter_labels: bool = True
    # How the displayed fiscal year number relates to the calendar year in which
    # the fiscal period *starts*.  None = auto (blockplan: +1 for non-Jan starts,
    # 0 for Jan; weekly/NRF: 0).  Set to an integer to override globally:
    #   0  → fiscal year name == start calendar year  (e.g. FY starting Feb 2026 → "FY2026")
    #   1  → fiscal year name == start calendar year + 1  (e.g. FY starting Oct 2025 → "FY2026")
    #  -1  → fiscal year name == start calendar year − 1  (unusual)
    fiscal_lookup: dict | None = None  # Runtime: populated by build_fiscal_lookup()

    # Mini calendar settings
    mini_columns: int = 3  # Months per row
    mini_rows: int = 0  # 0 = auto from date range
    mini_month_gap: float = 18.0  # Points between month grids
    # Event / holiday / special-day icons drawn in a day cell's corners,
    # alongside the day number (or day glyph in mini-icon) rather than in
    # place of it. Scale is a fraction of the cell's shorter side; the
    # opacity keeps the number legible where an icon overlaps it.
    mini_week_start: int = -1  # -1=inherit weekend_style, 0=Sunday, 1=Monday
    mini_duration_bar_height: float = 3.0  # Stroke width of duration bar lines
    mini_show_week_numbers: bool = False  # Show W# column on left
    mini_week_number_mode: str = "iso"  # "iso" or "custom"
    mini_week1_start: str = ""  # YYYYMMDD anchor for custom week 1

    # Candybar calendar settings (vertical year-strip: one row per ISO week)
    # Base cell shading (drawn under holiday/rule shade so those override it)
    # Month-name box (right-hand column spanning all of a month's week rows)

    # Text mini calendar settings

    # Weekly week number settings
    week_number_mode: str = "iso"  # "iso" or "custom"
    week1_start: str = ""  # YYYYMMDD anchor for custom week 1

    # Day-cell shade strengths. These were hardcoded in
    # visualizers/mini/day_styles.py until 2026-09-18; a theme sets them
    # through `colors.mini_calendar.*_opacity`. Holidays and company special
    # days share nonworkday_fill_color but have always shaded at different
    # strengths, so both values are kept rather than reconciled here.

    # Content filtering options
    includeevents: bool = True
    includedurations: bool = True
    milestones: bool = False
    WBS: str = ""
    _wbs_filter: Any = field(default=None, repr=False)
    _wbs_filter_raw: str = field(default="", repr=False)
    # Status filter: events whose status is in this set are included.
    # None means "all statuses". Default keeps the historic behaviour of
    # showing only events with status='active'.
    status_filter: frozenset[str] | None = field(default_factory=lambda: frozenset({"active"}))

    # Display options
    include_month_name: bool = True
    include_margin: bool = True
    include_color_key: bool = False

    # Run details (theme `details:` section): the details document, icon
    # files and event CSV every visualization run writes into its folder.
    # Table columns use the gantt.columns schema (renderers/table_columns).
    include_notes: bool = False
    include_week_numbers: bool = False
    include_day_names: bool = True
    include_header: bool = True
    include_footer: bool = True
    shrink_to_content: bool = False

    # Layout percentages (set by setfontsizes)
    margin_percent: float = 0.02
    # Optional explicit side margins in points (theme-overridable).
    margin_left: float | None = None
    margin_right: float | None = None
    margin_top: float | None = None
    margin_bottom: float | None = None
    color_key_percent: float = 0.15
    header_percent: float = 0.020
    footer_percent: float = 0.015
    day_name_percent: float = 0.02

    # Page-chrome font sizes (set by setfontsizes from the page height)
    header_left_font_size: float | None = None
    header_center_font_size: float | None = None
    header_right_font_size: float | None = None
    footer_left_font_size: float | None = None
    footer_center_font_size: float | None = None
    footer_right_font_size: float | None = None

    # Header text and styling
    header_left_text: str = ""
    header_center_text: str = ""
    header_right_text: str = field(default_factory=lambda: f"as of {get_creation_date()}")

    # Footer text and styling
    footer_left_text: str = ""
    footer_center_text: str = ""
    footer_right_text: str = ""

    # ── Continuation icons (global) ────────────────────────────────────────
    # When a duration event's start date precedes the visualization start
    # ("before") or its end date follows the visualization end ("after"),
    # the visualizers clamp the bar to the visible range and draw a small
    # icon at the clipped edge to signal that the activity continues. Shared
    # across timeline, blockplan, and compact_plan; configured under the
    # top-level `continuation:` section in theme YAMLs.
    #
    # icon_before / icon_after each accept either a single icon name or a
    # [horizontal, vertical] list. With a list, element [0] is used for
    # horizontally-oriented visualizers and element [1] for vertical
    # timelines — letting a theme pair, e.g., `move-left` (horizontal
    # "before") with `move-up` (vertical "before"). A bare string applies
    # to both orientations.

    # ── Overflow indicator (global) ────────────────────────────────────────
    # Drawn wherever a visualizer has more to say than the box it was given
    # can hold: the weekly day-number row when a day's events did not fit,
    # and a timeline duration bar too narrow for its name (there it precedes
    # the condensed name). Configured under the top-level `overflow:`
    # section in theme YAMLs; themes can also paint a halo behind it with a
    # `box:overflow` rule.

    # ── Weekly text styling — kept survivors only.  Phase 2 stripped
    # weekly_text_* (the full font_name/_color/_opacity/_alignment +
    # _font_size set), weekly_name_text_alignment, and
    # weekly_notes_text_alignment — none had readers post-Phase-1.
    # Day-box month shade and duration-bar base colours. Hardcoded in
    # visualizers/weekly/renderer.py until 2026-09-18; the bar colours are the
    # values a style rule starts from, so a rule still overrides them.

    # Extra padding (pts) added between the timeline axis and the bottom of
    # event callouts above the axis. Use this to push events away from tick
    # labels. Stacks on top of callout_offset_y / min-callout-offset.
    # Timeline box/date fields (not renamed — not event name/notes text)
    # Share of a duration bar's width given to each of its two side columns
    # (icon over start date, overflow mark over end date). None follows
    # timeline_event_icon_column_ratio, so the two kinds of box line up
    # without a theme saying so twice.
    # How point-event callouts are placed. "packed" lays them on a grid of
    # rows with each box's leading edge on its own start date; "labella"
    # keeps the force-solved placement that centres a box on its date.
    # Packed placement only. None follows timeline_labella_layer_gap, so a
    # theme that tuned the labella gap does not have to restate it.
    # Inner border kept clear inside a callout box, all four sides.
    # Share of a callout box's inner width given to the icon / date column;
    # the name and notes get the rest.
    # How many leading WBS segments group chart items: 2 makes NP.3.S1.4 and
    # NP.3.S2.1 both "NP.3", so a phase's events, milestones and duration
    # bars share one color and its bars sort together. 0 disables grouping —
    # each layout cycles its own palette per item, as before.

    # Which side(s) of the axis labels appear on. "primary" / "secondary" /
    # "both"; meaning depends on `timeline_orientation` (see above).
    # Which side a vertical axis's duration bars stack on. "opposite" (the
    # default) puts them across the axis from the event callouts, the way a
    # horizontal timeline reads with callouts above and bars below; the
    # concrete sides pin them regardless of where the callouts went.
    # Ignored on a horizontal axis, where bars are always below.
    # Vertical (or horizontal, for vertical orientation) gap between label
    # rows when labella stacks overlapping labels onto multiple layers.
    # Label-row thickness used by labella's Renderer.layout() to position
    # successive layers away from the axis.
    # Force density (0.0–1.0); higher → tighter packing, may oscillate at
    # extremes. Passed to labella.Force as the 'density' option.

    # Where the event date is drawn:
    #   "inline" — as a line inside the label box (with name/notes); the
    #              box grows to fit. Dates inherit the boxes' collision-free
    #              multi-row spacing, so they never overlap (default).
    #   "axis"   — on the opposite side of the axis at the marker. The
    #              "ruler tick" look, but dates collide when events cluster.
    #   "none"   — suppress the date entirely.

    # Label-box icons (DB icon names; None = no icon).
    # The PIT axis marker is ALWAYS a built-in shape (circle for events,
    # diamond for milestones) — icons are never placed on the axis.
    # These config defaults are drawn *inside the callout label box*,
    # on the same baseline as the event name and to its left. They
    # apply when the event has no per-event ``Icon`` column value and
    # no matched style rule supplied a ``marker_icon`` override.

    # Label-icon sizing. ``size`` defaults to the name font size so the
    # glyph fits cleanly on the name baseline; ``gap`` is the horizontal
    # space (points) between the icon's right edge and the start of the
    # name text.

    # Label box defaults
    # Where, along the axis, the leader meets the label box.
    #   "center" — leader joins the middle of the box (default; matches
    #              labella's centered overlap model, so boxes never collide)
    #   "start"  — leader joins the leading edge (top/left) of the box
    #   "end"    — leader joins the trailing edge (bottom/right) of the box
    # "start"/"end" can overlap on dense timelines because labella reserves
    # space centered on the marker; "center" is the collision-free choice.

    # Labella tuning (PIT-local copies so timeline and PIT can diverge)

    # Theme overrides (None → use module defaults). All color slots accept
    # CSS / hex / "palette:NAME:INDEX" via _resolve_palette_overrides.
    # PIT base colours and today-line strengths. Each theme_pit_* field below
    # overrides its partner here; until 2026-09-18 the partner was a literal
    # inlined in visualizers/pit/renderer.py, so no theme could change the
    # value a default render actually used.
    # Nonworkday tint shared by the blockplan and compactplan day axes, and
    # the gantt duration-bar fill. All three were inlined as `or "<literal>"`
    # fallbacks in their renderers until 2026-09-18.
    nonworkday_fill_color: str = "#333333"

    # Per-event font fields (mirror timeline_* equivalents)

    # Width of the time-band name cells; None = same as label_column_ratio.
    # Empty → no swimlanes: one unlabeled lane holds every item.
    # ── Blockplan text styling — kept survivors only (font_size + name fields).
    # Blockplan event/duration date & marker fields (not renamed)
    # Space (pt) between duration bars in adjacent rows; bars shrink below
    # duration_bar_height to keep it.  None = bars may fill 95% of the row.

    # ── Gantt ─────────────────────────────────────────────────────────────────
    # Task table on the left, timescale chart on the right.  Column layout is
    # configuration rather than style, so it lives here and in the theme's
    # `gantt.columns:` section; style_rules govern only the visuals.
    # Horizontal pagination: the narrowest a day column may get before the
    # date range is split across pages.  0 disables the split, fitting the
    # whole range onto one page however thin the columns become.
    # Marks.  Icon names resolve against the `icon` table.
    # Cross-page dependency references.  Families are consumed in order, so
    # numbering survives 300 breaks before falling back to the unnumbered
    # marker above.
    # Dependency arrows are curved leaders drawn the way PIT draws its
    # callout leaders, so they take the same styling vocabulary: an SVG
    # marker that orients itself along the curve, plus stroke joins.

    # ── Compact plan text styling (uniform) ──────────────────────────────────
    # Phase 2 strip — fields with no consumers post-Phase-1 dropped:
    #   text_font_color/opacity/alignment, name_text_font_color/opacity/alignment,
    #   notes_text_font_color/opacity/alignment (all subsumed by the
    #   text:event_name / text:event_notes / text:label tokens; the per-renderer
    #   YAML overrides cover any compactplan-specific deviation), plus
    #   axis_color/dasharray/opacity, duration_stroke_dasharray, duration_opacity,
    #   duration_icon_color, milestone_color, milestone_list_date_color,
    #   milestone_list_section_gap, continuation_section_gap, legend_area_ratio,
    #   background_color (compactplan inherits the page background).
    # Each bar is three columns: start date | icon + name | end date.  The
    # date columns are each duration_date_column_ratio of the bar's width and
    # the icon and name are fitted to the middle one.  A color left None
    # takes black or white, whichever reads against the bar.

    # ── Continuation icon ─────────────────────────────────────────────────────
    # The global continuation_icon_after / _color / _height fields drive the
    # compactplan continuation icon (the line only clips on its "after" end).
    # What its symbols mean -- listed in the run's details document -- is
    # compactplan-specific.

    # Default icon shown when an event's icon name cannot be found in the icons table
    # Drawn size of that stand-in glyph, in points. None keeps it the size of
    # whatever it replaces — the icon the caller asked for, or the mark the
    # visualizer would have drawn — which is right when the substitute should
    # sit in the same hole, and wrong when it should be conspicuous.
    # Ink for that stand-in. It marks a data problem — an event naming an icon
    # the icons table does not have — so it defaults to an alert colour rather
    # than inheriting the ink of whatever it replaced, which would let the
    # substitution pass unnoticed. Set `base.default_missing_icon_color` in a
    # theme to tune it.

    # Watermark text

    # Watermark image
    watermark_image_width: int = 300
    watermark_image_height: int = 300

    # Theme-overridable color maps (None = use module-level defaults)

    # Global item-placement/sort order, honored by every visualizer that
    # places or orders event data (weekly day boxes, blockplan swimlanes,
    # gantt rows, timeline callouts/bars, compactplan durations, text-mini
    # symbol assignment). A list of tokens, consumed left-to-right; see
    # shared/item_order.py for the full algorithm. Token kinds:
    #   Type tokens: "milestones", "events", "durations" -- classify by
    #     event shape; not-listed types sort after listed ones.
    #   "wbs" -- WBS-having rows before WBS-less rows, numeric WBS compare.
    #   "priority" -- sort by Event.priority.
    #   "alphabetical" -- sort by lowercased task_name.
    #   any other string -- an Event field name (via resolve_field).
    #   a dict -- arbitrary event-selection criteria (same vocabulary as
    #     style_rules' select:), matches sort first.
    # Example: [{"resource_group": "Executive"}, "milestones", "priority"]

    # DB palette names — resolved at render time from calendar.db palettes table

    # Group colors for event categorization

    def __post_init__(self) -> None:
        """Validate configuration invariants after construction."""
        if self.weekend_style not in range(5):
            raise ValueError(f"weekend_style must be 0–4, got {self.weekend_style}")
        if self.mini_columns < 1:
            raise ValueError(f"mini_columns must be >= 1, got {self.mini_columns}")
        if self.weekend_days is not None:
            if not isinstance(self.weekend_days, list) or not all(
                isinstance(d, int) and 0 <= d <= 6 for d in self.weekend_days
            ):
                raise ValueError(f"weekend_days must be a list of ints 0–6 (ISO weekday), got {self.weekend_days!r}")
            if len(set(self.weekend_days)) != len(self.weekend_days):
                raise ValueError(f"weekend_days must not contain duplicates, got {self.weekend_days!r}")

    def get_weekend_days(self) -> frozenset[int]:
        """Resolve weekend days (ISO weekday 0=Mon..6=Sun).

        If ``weekend_days`` is explicitly set, use it verbatim.  Otherwise
        derive from ``weekend_style``: style 0 yields an empty set (no
        weekends), and styles 1–4 yield {5, 6} (Saturday/Sunday).
        """
        if self.weekend_days is not None:
            return frozenset(self.weekend_days)
        if self.weekend_style == 0:
            return frozenset()
        return frozenset({5, 6})

    # ── Style accessor methods ──────────────────────────────────────────────
    # Element styles always come from tokens: the theme's, or with no
    # ``style_rules`` theme loaded, the built-in catalog defaults.

    def _styles(self) -> Any:
        key = (id(self.theme_v3), self.papersize)
        if self.theme_styles is None or self.theme_styles_key != key:
            from config import role_styles

            self.theme_styles = role_styles.theme_styles(self.theme_v3, self.papersize)
            self.theme_styles_key = key
        return self.theme_styles

    def get_text_style(self, element_class: str) -> Any:
        """Look up the TextStyle bound to a CSS element class."""
        from config.styles import TextStyle

        return self._styles().get_text_style(element_class) or TextStyle()

    def get_box_style(self, element_class: str) -> Any:
        """Look up the BoxStyle bound to a CSS element class."""
        from config.styles import BoxStyle

        return self._styles().get_box_style(element_class) or BoxStyle()

    def get_line_style(self, element_class: str) -> Any:
        """Look up the LineStyle bound to a CSS element class."""
        from config.styles import LineStyle

        return self._styles().get_line_style(element_class) or LineStyle()

    def get_icon_style(self, element_class: str) -> Any:
        """Look up the IconStyle bound to a CSS element class."""
        from config.styles import IconStyle

        return self._styles().get_icon_style(element_class) or IconStyle()

    def get_element_color(self, element_class: str, fallback: str = "#333333") -> str:
        """Get the effective color for a CSS element class."""
        return self._styles().get_element_color(element_class) or fallback


def create_calendar_config() -> CalendarConfig:
    """Factory function to create a new CalendarConfig instance."""
    return CalendarConfig()


# =============================================================================
# Calendar Labels
# =============================================================================

day_short = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _numbered_icons(prefix: str, count: int = 31, *, zero_pad: bool = True) -> list[str]:
    """Icon names ``prefix-01 … prefix-NN`` (``prefix-1 …`` when not zero-padded)."""
    return [f"{prefix}-{n:02d}" if zero_pad else f"{prefix}-{n}" for n in range(1, count + 1)]


# Canonical mapping of icon-list names to their icon-name sequences.
# Used by the compactplan duration-start icons and the mini-icon view.
ICON_SETS: dict[str, list[str]] = {
    "squares": _numbered_icons("square"),
    "darksquare": _numbered_icons("darksquare", 50),
    "darkcircles": _numbered_icons("darkcircle"),
    "circles": _numbered_icons("circle", zero_pad=False),
    "squircles": _numbered_icons("squircle"),
    "darksquircles": _numbered_icons("darksquircle"),
}


# =============================================================================
# Colors
# =============================================================================

monthcolors: dict[str, str] = {
    "01": "lightgrey",
    "02": "grey",
    "03": "lightgrey",
    "04": "grey",
    "05": "lightgrey",
    "06": "grey",
    "07": "lightgrey",
    "08": "grey",
    "09": "lightgrey",
    "10": "grey",
    "11": "lightgrey",
    "12": "grey",
}

fiscalperiodcolors: dict[str, str] = {
    "01": "lightgrey",
    "02": "grey",
    "03": "lightgrey",
    "04": "grey",
    "05": "lightgrey",
    "06": "grey",
    "07": "lightgrey",
    "08": "grey",
    "09": "lightgrey",
    "10": "grey",
    "11": "lightgrey",
    "12": "grey",
    "13": "lightgrey",
}

FederalHolidayColor = "red"
FederalHolidayAlpha = 0.25
CompanyHolidayColor = "green"
CompanyHolidayAlpha = 0.25

hashlinecolor = "white"

# =============================================================================
# Font Registry
# =============================================================================


def _build_font_registry() -> dict[str, str]:
    """Build the font registry by scanning fonts/*.ttf and fonts/*.otf at import time.

    Each font file contributes an entry keyed by its stem (e.g. "Roboto-Bold").
    TTF entries take precedence over OTF when both share the same stem.
    Compatibility aliases that differ from the stem are added afterwards.

    Extensions match case-insensitively, so a file shipped as ``.TTF``
    registers the same as a ``.ttf`` one.
    """
    fonts_dir = Path(__file__).parent.parent / "fonts"
    registry: dict[str, str] = {}
    if fonts_dir.is_dir():
        for pattern in ("*.otf", "*.ttf"):
            for font in sorted(fonts_dir.glob(pattern, case_sensitive=False)):
                registry[font.stem] = f"fonts/{font.name}"
    return registry


FONT_REGISTRY: dict[str, str] = _build_font_registry()


def get_font_path(font_name: str) -> str:
    """Return the TTF file path for a registered font name.

    Args:
        font_name: Font name as registered in FONT_REGISTRY

    Returns:
        Path string to the TTF file, or '' if font_name is empty

    Raises:
        KeyError: If font_name is non-empty but not found in FONT_REGISTRY
    """
    if not font_name:
        return ""
    path = FONT_REGISTRY.get(font_name)
    if path is None:
        raise KeyError(f"Font '{font_name}' not found in FONT_REGISTRY. Available fonts: {sorted(FONT_REGISTRY)}")
    return path


# =============================================================================
# Weekend Style Configurations
# =============================================================================

WEEKEND_STYLES: dict[int, dict[str, Any]] = {
    0: {  # Work week only - no weekends shown
        "name": "workweek",
        "days_per_week": 5,
        "day_order": [
            "Monday",
            "Tuesday",
            "Wednesday",
            "Thursday",
            "Friday",
        ],
        "weekend_width_factor": 0,
        "ptr_init": -8,
        "ptr_increment": 12,
        "divisor": 5,
    },
    1: {  # All days same size, Sunday start
        "name": "full_sunday_start",
        "days_per_week": 7,
        "day_order": [
            "Sunday",
            "Monday",
            "Tuesday",
            "Wednesday",
            "Thursday",
            "Friday",
            "Saturday",
        ],
        "weekend_width_factor": 1.0,
        "ptr_init": -8,
        "ptr_increment": 14,
        "divisor": 7,
    },
    2: {  # Half-width weekends, Sunday start
        "name": "half_sunday_start",
        "days_per_week": 7,
        "day_order": [
            "Sunday",
            "Monday",
            "Tuesday",
            "Wednesday",
            "Thursday",
            "Friday",
            "Saturday",
        ],
        "weekend_width_factor": 0.5,
        "ptr_init": 6,
        "ptr_increment": 7,
        "divisor": 6,
        "special_layout": True,
    },
    3: {  # All days same size, Monday start
        "name": "full_monday_start",
        "days_per_week": 7,
        "day_order": [
            "Monday",
            "Tuesday",
            "Wednesday",
            "Thursday",
            "Friday",
            "Saturday",
            "Sunday",
        ],
        "weekend_width_factor": 1.0,
        "ptr_init": -8,
        "ptr_increment": 14,
        "divisor": 7,
    },
    4: {  # Half-width weekends, Monday start
        "name": "half_monday_start",
        "days_per_week": 7,
        "day_order": [
            "Monday",
            "Tuesday",
            "Wednesday",
            "Thursday",
            "Friday",
            "Saturday",
            "Sunday",
        ],
        "weekend_width_factor": 0.5,
        "ptr_init": -8,
        "ptr_increment": 14,
        "divisor": 6,
    },
}


# =============================================================================
# Continuation Icon Resolution
# =============================================================================


def resolve_continuation_icon(
    value: str | list[str] | tuple[str, ...] | None,
    orientation: str,
    fallback: str,
) -> str:
    """Pick the orientation-appropriate icon name from a continuation_icon field.

    Themes may supply either a single icon name (used for any orientation)
    or a two-element list ``[horizontal, vertical]``. A single-element list
    behaves like the bare string. Empty / None values fall through to
    ``fallback``.

    ``orientation`` is matched case-insensitively against ``"vertical"``;
    anything else (including ``"horizontal"`` and Orientation enum values
    whose str() form is ``"horizontal"``) selects index 0.
    """
    if value is None or value == "":
        return fallback
    if isinstance(value, str):
        return value
    if isinstance(value, (list, tuple)):
        if not value:
            return fallback
        is_vertical = str(orientation).lower() == "vertical"
        idx = 1 if (is_vertical and len(value) >= 2) else 0
        chosen = value[idx]
        return str(chosen) if chosen else fallback
    return str(value)


# =============================================================================
# Weekend Style Predicate Helpers
# =============================================================================


def weekend_style_is_workweek(style: int) -> bool:
    """True for style 0 (Mon–Fri only, no weekend days shown)."""
    return style == 0


def weekend_style_starts_sunday(style: int) -> bool:
    """True for styles 1 and 2 (week starts on Sunday)."""
    return style in (1, 2)


# =============================================================================
# Font Size Calculation
# =============================================================================


def _clamp(value: float, minimum: float, maximum: float) -> float:
    """Clamp a value between minimum and maximum."""
    return max(minimum, min(maximum, value))


_LEN_RE = re.compile(r"^\s*([+-]?\d+(?:\.\d+)?)\s*([A-Za-z]*)\s*$")
_UNIT_TO_PT = {
    "": 1.0,
    "pt": 1.0,
    "pts": 1.0,
    "point": 1.0,
    "points": 1.0,
    "in": 72.0,
    "inch": 72.0,
    "inches": 72.0,
    "mm": 72.0 / 25.4,
    "cm": 72.0 / 2.54,
    "px": 72.0 / 96.0,
}


def parse_length_to_points(value: Any) -> float:
    """
    Parse a scalar length with optional unit and return points.

    Accepted forms:
    - numeric: treated as points
    - string: e.g. '12', '12pt', '0.5in', '10mm', '2.54cm', '24px'
    - mapping: {'value': 0.5, 'unit': 'in'}
    """
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, dict):
        if "value" not in value:
            raise ValueError(f"Missing 'value' in length mapping: {value!r}")
        v = value["value"]
        unit = str(value.get("unit", "")).strip().lower()
        if not isinstance(v, (int, float)):
            raise ValueError(f"Length mapping value must be numeric: {value!r}")
        if unit not in _UNIT_TO_PT:
            raise ValueError(f"Unsupported unit '{unit}' in length mapping: {value!r}")
        return float(v) * _UNIT_TO_PT[unit]
    if isinstance(value, str):
        m = _LEN_RE.match(value)
        if not m:
            raise ValueError(f"Invalid length string: {value!r}")
        number = float(m.group(1))
        unit = m.group(2).strip().lower()
        if unit not in _UNIT_TO_PT:
            raise ValueError(f"Unsupported unit '{unit}' in length: {value!r}")
        return number * _UNIT_TO_PT[unit]
    raise ValueError(f"Unsupported length value type: {type(value).__name__}")


def resolve_page_margins(config: CalendarConfig) -> dict[str, float]:
    """
    Resolve effective page margins in points.

    - If include_margin is True, uses symmetric margin_percent as default.
    - Explicit side margins override defaults when present.
    - If include_margin is False and no side overrides are provided, margins are 0.
    """
    base_margin = round(config.pageX * config.margin_percent, 2) if config.include_margin else 0.0
    left = float(config.margin_left) if config.margin_left is not None else base_margin
    right = float(config.margin_right) if config.margin_right is not None else base_margin
    top = float(config.margin_top) if config.margin_top is not None else base_margin
    bottom = float(config.margin_bottom) if config.margin_bottom is not None else base_margin

    left = max(0.0, left)
    right = max(0.0, right)
    top = max(0.0, top)
    bottom = max(0.0, bottom)

    usable_width = max(0.0, config.pageX - left - right)
    usable_height = max(0.0, config.pageY - top - bottom)
    return {
        "left": left,
        "right": right,
        "top": top,
        "bottom": bottom,
        "usable_width": usable_width,
        "usable_height": usable_height,
    }


def setfontsizes(config: CalendarConfig) -> CalendarConfig:
    """Set the page-layout ratios (margins, header, footer, day names, colour key) and the
    header and footer text sizes, which follow the page height.

    Every other text size is the theme's ``text`` role, scaled by paper size with
    the role's ``size_by_paper``.

    Returns:
        The same config instance.
    """
    config.margin_percent = 0.05
    config.color_key_percent = 0.15
    config.header_percent = 0.020
    config.footer_percent = 0.018
    config.day_name_percent = 0.02

    h = config.pageY
    config.header_left_font_size = _clamp(h * 0.013, 6.0, 32.0)
    config.header_center_font_size = config.header_left_font_size
    config.header_right_font_size = config.header_left_font_size
    config.footer_left_font_size = _clamp(h * 0.010, 6.0, 32.0)
    config.footer_center_font_size = config.footer_left_font_size
    config.footer_right_font_size = config.footer_left_font_size
    return config
