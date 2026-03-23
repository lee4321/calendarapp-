#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Event Calendar configuration file
Sets default values that will be used unless overridden
"""

from __future__ import annotations

import arrow
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


def get_creation_date() -> str:
    """Format the creation date for use in the calendar."""
    return arrow.now().format("YYYY-MM-DD")


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
    R_BLACK = "Roboto-Black"
    R_BLACK_ITALIC = "Roboto-BlackItalic"
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
    doc_title: str = field(
        default_factory=lambda: f"Calendar created {get_creation_date()}"
    )
    doc_author: str = "A. Lee Ingram"
    doc_subject: str = "Calendar"
    doc_keywords: str = ""
    command_line: str = ""

    # Data source description (for header/footer expansion)
    events: str = ""

    # Page dimensions (set from papersize lookup)
    pageX: float = 0.0
    pageY: float = 0.0
    papersize: str = "Widescreen"
    orientation: str = "landscape"
    desired_font_size: float | None = None  # Theme-selected target base size

    # Output file
    outputfile: str = ""

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

    # ISO 3166-1 alpha-2 country code(s) for government holiday loading.
    # Accepts a single code ("US"), a comma-separated list ("US,CA,GB"), or
    # None (loads the default set — US and CA — via load_python_holidays).
    # Parsed into individual codes at use-time by _parse_country_codes() in db_access.py.
    country: str | None = None

    # Fiscal calendar settings
    fiscal_calendar_type: str | None = (
        None  # "nrf-454", "nrf-445", "nrf-544", "13-period"
    )
    fiscal_show_period_labels: bool = True
    fiscal_show_quarter_labels: bool = True
    fiscal_use_period_colors: bool = False
    fiscal_period_label_font: str = Fonts.RC_BOLD
    fiscal_period_label_color: str = "darkblue"
    fiscal_period_label_font_size: float | None = None  # Set in setfontsizes()
    fiscal_period_label_format: str = "{prefix}{period_short}"
    fiscal_period_end_label_format: str = "{period_short} End"
    # How the displayed fiscal year number relates to the calendar year in which
    # the fiscal period *starts*.  None = auto (blockplan: +1 for non-Jan starts,
    # 0 for Jan; weekly/NRF: 0).  Set to an integer to override globally:
    #   0  → fiscal year name == start calendar year  (e.g. FY starting Feb 2026 → "FY2026")
    #   1  → fiscal year name == start calendar year + 1  (e.g. FY starting Oct 2025 → "FY2026")
    #  -1  → fiscal year name == start calendar year − 1  (unusual)
    fiscal_year_offset: int | None = None
    fiscal_lookup: dict | None = None  # Runtime: populated by build_fiscal_lookup()

    # Mini calendar settings
    mini_columns: int = 3  # Months per row
    mini_rows: int = 0  # 0 = auto from date range
    mini_month_gap: float = 18.0  # Points between month grids
    mini_cell_font: str = Fonts.J_REGULAR  # Monospace day number font
    mini_cell_bold_font: str = Fonts.R_BOLD  # Bold variant
    mini_title_font: str = Fonts.RC_BOLD  # Month title font
    mini_title_font_size: float | None = None
    mini_title_format: str = "MMMM YYYY"  # Arrow format string for title
    mini_title_color: str = "navy"
    mini_header_font: str = Fonts.J_REGULAR  # Day-of-week header font
    mini_header_font_size: float | None = None
    mini_header_color: str = "grey"
    mini_day_color: str = "black"  # Default day number color
    mini_adjacent_month_color: str = "lightgrey"  # Leading/trailing days
    mini_holiday_color: str = "red"  # Holiday day number color
    mini_nonworkday_shade: str = "lightblue"  # Non-work day background
    mini_milestone_color: str = "navy"  # Milestone circle color
    mini_milestone_stroke_color: str = "navy"  # Milestone circle stroke color
    mini_milestone_stroke_width: float = 1.0
    mini_milestone_stroke_opacity: float = 1.0
    mini_day_number_glyphs: list[str] | None = None
    mini_day_number_digits: list[str] | None = None
    mini_cell_font_size: float | None = None
    mini_show_adjacent: bool = True  # Show leading/trailing days
    mini_circle_milestones: bool = True
    mini_week_start: int = -1  # -1=inherit weekend_style, 0=Sunday, 1=Monday
    mini_duration_bar_height: float = 3.0  # Stroke width of duration bar lines
    mini_duration_bar_stroke_opacity: float = 0.7
    mini_grid_lines: bool = False  # Draw grid lines between cells
    mini_grid_line_stroke_color: str = "lightgrey"
    mini_grid_line_stroke_width: float = 0.25
    mini_grid_line_stroke_opacity: float = 0.5
    mini_grid_line_stroke_dasharray: str | None = None
    mini_cell_box_stroke_dasharray: str | None = None
    mini_strikethrough_stroke_dasharray: str | None = None
    mini_hash_line_stroke_dasharray: str | None = None
    mini_duration_bar_stroke_dasharray: str | None = None
    mini_details_separator_stroke_dasharray: str | None = None
    mini_show_week_numbers: bool = False  # Show W# column on left
    mini_week_number_mode: str = "iso"  # "iso" or "custom"
    mini_week1_start: str = ""  # YYYYMMDD anchor for custom week 1
    mini_week_number_font: str = Fonts.J_REGULAR  # Font for week numbers
    mini_week_number_color: str = "black"  # Color for week numbers
    mini_week_number_font_size: float | None = None  # Week number font size
    mini_week_number_label_format: str = "W{num}"
    mini_icon_set: str = "squares"  # Icon set for mini-icon view

    # Text mini calendar settings
    text_mini_cell_width: int = 2
    text_mini_month_gap: int = 4
    text_mini_week_number_digits: list[str] = field(
        default_factory=lambda: ["⁰", "¹", "²", "³", "⁴", "⁵", "⁶", "⁷", "⁸", "⁹"]
    )
    text_mini_day_number_digits: list[str] = field(
        # default_factory=lambda: list("0123456789")
        default_factory=lambda: ["𜳰", "𜳱", "𜳲", "𜳳", "𜳴", "𜳵", "𜳶", "𜳷", "𜳸", "𜳹"]
    )
    text_mini_event_symbols: list[str] = field(
        # default_factory=lambda: ["⚐", "⚑", "⛿", "⛳"]
        default_factory=lambda: [
            "⯍",
            "⯏",
            "🟈",
            "🟃",
            "🟎",
            "🟉",
            "⯌",
            "🟒",
            "🟋",
            "🞻",
            "🞯",
            "🟂",
            "🟐",
            "🞿",
            "🞭",
            "🞹",
            "⭐",
            "🃟",
            "⊛",
            "⋇",
            "⊗",
            "⨳",
            "⧾",
            "⟡",
            "⟐",
            "❖",
            "◊",
            "⯪",
            "⯫",
            "꥟",
            "𜱃",
            "𜱪",
            "𜱩",
            "𜸂",
            "𜻏",
            "🟙",
            "🝴",
            "🩔",
            "🮻",
            "🯀",
            "🮽",
            "",
            "",
            "",
            "",
            "󰘳",
            "⟠",
            "⨷",
            "✢",
            "✨",
            "❂",
        ]
    )
    text_mini_milestone_symbols: list[str] = field(
        # default_factory=lambda: ["⸸","⹋","«","¤","‼","ʬ","ʭ","ᖚ","䷀","𝚵","ᛝ","ⵙ","꩜","ᕲ","ᛃ","߷","⁌","֎","𜰕","𜱊","𜲉","𜲌","𜳺","𜳻","🮽","","","","","󰘳","⟠","⨷","✢","✨","❂","Ꝏ","Ꙫ","ꙮ",]
        # default_factory=lambda: ["Ⅰ","Ⅱ","Ⅲ","Ⅳ","Ⅴ","Ⅵ","Ⅶ","Ⅷ","Ⅸ","Ⅹ","Ⅺ","Ⅻ",]
        default_factory=lambda: [
            "🄰",
            "🄱",
            "🄲",
            "🄳",
            "🄴",
            "🄵",
            "🄶",
            "🄷",
            "🄸",
            "🄹",
            "🄺",
            "🄻",
            "🄼",
            "🄽",
            "🄾",
            "🄿",
            "🅀",
            "🅁",
            "🅂",
            "🅃",
            "🅄",
            "🅅",
            "🅆",
            "🅇",
            "🅈",
            "🅉",
        ]
    )
    text_mini_holiday_symbols: list[str] = field(
        default_factory=lambda: [
            "🅰",
            "🅱",
            "🅲",
            "🅳",
            "🅴",
            "🅵",
            "🅶",
            "🅷",
            "🅸",
            "🅹",
            "🅺",
            "🅻",
            "🅼",
            "🅽",
            "🅾",
            "🅿",
            "🆀",
            "🆁",
            "🆂",
            "🆃",
            "🆄",
            "🆅",
            "🆆",
            "🆇",
            "🆈",
            "🆉",
        ]
    )
    text_mini_nonworkday_symbols: list[str] = field(
        default_factory=lambda: [
            "𝒂",
            "𝒃",
            "𝒄",
            "𝒅",
            "𝒆",
            "𝒇",
            "𝒈",
            "𝒉",
            "𝒊",
            "𝒋",
            "𝒌",
            "𝒍",
            "𝒎",
            "𝒏",
            "𝒐",
            "𝒑",
            "𝒒",
            "𝒓",
            "𝒔",
            "𝒕",
            "𝒖",
            "𝒗",
            "𝒘",
            "𝒙",
            "𝒚",
            "𝒛",
        ]
    )
    text_mini_duration_symbols: list[str] = field(
        default_factory=lambda: ["❶", "❷", "❸", "❹", "❺", "❻", "❼", "❽", "❾", "❿"]
    )
    text_mini_duration_fill: str = "⸬"

    # Mini calendar details page
    include_mini_details: bool = True
    mini_details_output_suffix: str = "_details"
    mini_details_title_text: str = "Event Details"
    mini_details_title_font: str = Fonts.RC_BOLD
    mini_details_title_color: str = "navy"
    mini_details_title_font_size: float | None = None
    mini_details_header_font: str = Fonts.RC_BOLD
    mini_details_header_color: str = "grey"
    mini_details_header_font_size: float | None = None
    # ── Mini details text styling (uniform) ──────────────────────────────────
    mini_details_text_font_name: str = Fonts.RC_LIGHT
    mini_details_text_font_color: str = "black"
    mini_details_text_font_size: float | None = None
    mini_details_text_font_opacity: float = 1.0
    mini_details_text_alignment: str = "left"
    mini_details_name_text_font_name: str = Fonts.RC_LIGHT
    mini_details_name_text_font_color: str = "black"
    mini_details_name_text_font_size: float | None = None
    mini_details_name_text_font_opacity: float = 1.0
    mini_details_name_text_alignment: str = "left"
    mini_details_notes_text_font_name: str = Fonts.RC_LIGHT_ITALIC
    mini_details_notes_text_font_color: str = "darkgrey"
    mini_details_notes_text_font_size: float | None = None
    mini_details_notes_text_font_opacity: float = 1.0
    mini_details_notes_text_alignment: str = "left"
    mini_details_headers: list[str] = field(
        default_factory=lambda: [
            "Start Date",
            "Name / Description",
            "Milestone",
            "Priority",
            "Group",
        ]
    )
    mini_details_column_widths: list[float] = field(
        default_factory=lambda: [0.16, 0.52, 0.10, 0.10, 0.12]
    )

    # Weekly week number settings
    week_number_mode: str = "iso"  # "iso" or "custom"
    week1_start: str = ""  # YYYYMMDD anchor for custom week 1
    mini_current_day_color: str = "lightblue"  # Current day shade color

    # Theme-overridable mini calendar fields (None = use mini_* defaults above)
    theme_mini_title_color: str | None = None
    theme_mini_header_color: str | None = None
    theme_mini_day_color: str | None = None
    theme_mini_adjacent_month_color: str | None = None
    theme_mini_holiday_color: str | None = None
    theme_mini_nonworkday_shade: str | None = None
    theme_mini_milestone_color: str | None = None
    theme_mini_week_number_color: str | None = None
    theme_mini_current_day_color: str | None = None

    # Content filtering options
    includeevents: bool = True
    includedurations: bool = True
    milestones: bool = False
    rollups: bool = True
    ignorecomplete: bool = False
    WBS: str = ""
    _wbs_filter: Any = field(default=None, repr=False)
    _wbs_filter_raw: str = field(default="", repr=False)

    # Display options
    shade_current_day: bool = True
    include_month_name: bool = True
    include_margin: bool = True
    include_overflow: bool = False
    include_color_key: bool = False
    include_notes: bool = False
    include_week_numbers: bool = False
    include_day_names: bool = True
    include_header: bool = True
    include_footer: bool = True
    shrink_to_content: bool = False

    # Layout percentages (set by setfontsizes)
    week_number_percent: float = 0.015
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
    month_percent: float = 0.03

    # Font sizes (set by setfontsizes)
    week_number_font_size: float | None = None
    day_name_font_size: float | None = None
    color_key_font_size: float | None = None
    header_left_font_size: float | None = None
    header_center_font_size: float | None = None
    header_right_font_size: float | None = None
    footer_left_font_size: float | None = None
    footer_center_font_size: float | None = None
    footer_right_font_size: float | None = None
    day_box_number_font_size: float | None = None
    day_box_icon_font_size: float | None = None
    event_icon_font_size: float | None = None

    # Week number styling
    week_number_font: str = Fonts.RC_BOLD
    week_number_font_color: str = "grey"
    week_number_label_format: str = "W{num:02d}"

    # Header text and styling
    header_left_text: str = ""
    header_left_font: str = Fonts.R_BLACK_ITALIC
    header_left_font_color: str = "grey"
    header_center_text: str = ""
    header_center_font: str = Fonts.R_BLACK_ITALIC
    header_center_font_color: str = "grey"
    header_right_text: str = field(
        default_factory=lambda: f"as of {get_creation_date()}"
    )
    header_right_font: str = Fonts.R_BLACK_ITALIC
    header_right_font_color: str = "grey"

    # Footer text and styling
    footer_left_text: str = ""
    footer_left_font: str = Fonts.RC_LIGHT
    footer_left_font_color: str = "grey"
    footer_center_text: str = ""
    footer_center_font: str = Fonts.RC_LIGHT
    footer_center_font_color: str = "grey"
    footer_right_text: str = ""
    footer_right_font: str = Fonts.RC_LIGHT
    footer_right_font_color: str = "grey"

    # Day name styling
    day_name_font: str = Fonts.RC_LIGHT_ITALIC
    day_name_font_color: str = "grey"

    # Day box styling
    day_box_stroke_color: str = "grey"
    day_box_stroke_opacity: float = 0.25
    day_box_stroke_width: int = 2
    day_box_stroke_dasharray: str | None = None
    day_box_fill_color: str = "grey"
    day_box_fill_opacity: float = 0.25
    day_box_number_font: str = "CascadiaCode"
    day_box_number_color: str = "white"
    day_box_icon_color: str = "red"
    day_box_font_color: str = "navy"

    # Event/Duration icon styling (not renamed — icon fields are out of scope)
    event_icon_color: str = "navy"
    duration_icon_color: str = "navy"
    duration_stroke_dasharray: str | None = None

    # ── Weekly text styling (uniform) ──────────────────────────────────────────
    weekly_text_font_name: str = Fonts.RC_LIGHT
    weekly_text_font_color: str = "navy"
    weekly_text_font_size: float | None = None
    weekly_text_font_opacity: float = 1.0
    weekly_text_alignment: str = "left"
    weekly_name_text_font_name: str = Fonts.RC_LIGHT
    weekly_name_text_font_color: str = "navy"
    weekly_name_text_font_size: float | None = None
    weekly_name_text_font_opacity: float = 1.0
    weekly_name_text_alignment: str = "left"
    weekly_notes_text_font_name: str = Fonts.RC_LIGHT_ITALIC
    weekly_notes_text_font_color: str = "darkgrey"
    weekly_notes_text_font_size: float | None = None
    weekly_notes_text_font_opacity: float = 1.0
    weekly_notes_text_alignment: str = "left"
    hash_pattern_opacity: float = 0.15

    # Timeline styling
    timeline_background_color: str = "none"
    timeline_axis_color: str = "lightgrey"
    timeline_axis_opacity: float = 0.85
    timeline_axis_width: float = 2.0
    timeline_tick_color: str = "grey"
    timeline_date_format: str = "MMM D"
    timeline_tick_label_format: str = "MMM D"
    timeline_today_date: str = ""
    timeline_today_label_text: str = "Today"
    timeline_today_label_offset_y: float = 10.0
    timeline_today_line_color: str = "grey"
    timeline_today_label_color: str = "grey"
    # Length of the today line in points (0 = full available area height).
    timeline_today_line_length: float = 0.0
    # Which side of the timeline axis the today line extends to.
    # "above" = from axis upward, "below" = from axis downward, "both" = both directions.
    timeline_today_line_direction: str = "both"
    timeline_marker_stroke_color: str = "black"
    timeline_marker_stroke_width: float = 1.0
    timeline_marker_radius: float = 6
    timeline_icon_size: float = 8.0
    timeline_callout_offset_y: float = 96.0
    timeline_duration_offset_y: float = 44.0
    timeline_duration_lane_gap_y: float = 8.0
    # ── Timeline text styling (uniform) ──────────────────────────────────────
    timeline_text_font_name: str = Fonts.R_BOLD
    timeline_text_font_color: str = "deepskyblue"
    timeline_text_font_size: float | None = None
    timeline_text_font_opacity: float = 1.0
    timeline_text_alignment: str = "left"
    timeline_name_text_font_name: str = Fonts.R_BOLD
    timeline_name_text_font_color: str = "deepskyblue"
    timeline_name_text_font_size: float | None = None
    timeline_name_text_font_opacity: float = 1.0
    timeline_name_text_alignment: str = "left"
    timeline_notes_text_font_name: str = Fonts.RC_BOLD
    timeline_notes_text_font_color: str = "deepskyblue"
    timeline_notes_text_font_size: float | None = None
    timeline_notes_text_font_opacity: float = 1.0
    timeline_notes_text_alignment: str = "left"
    # Timeline box/date fields (not renamed — not event name/notes text)
    timeline_event_box_width: float | None = None
    timeline_event_box_height: float | None = None
    timeline_duration_box_width: float | None = None
    timeline_duration_box_height: float | None = None
    timeline_duration_date_font: str | None = None
    timeline_duration_date_font_size: float | None = None
    timeline_duration_date_color: str | None = None
    timeline_date_font: str = Fonts.R_BOLD
    timeline_date_color: str = "deepskyblue"
    timeline_label_stroke_width: float = 1.0
    timeline_label_fill_opacity: float = 0.25
    timeline_duration_bar_fill_opacity: float = 0.25
    # stroke-dasharray for timeline elements
    timeline_axis_stroke_dasharray: str | None = None
    timeline_tick_stroke_dasharray: str | None = None
    timeline_today_line_stroke_dasharray: str | None = None
    timeline_label_stroke_dasharray: str | None = None
    timeline_duration_bar_stroke_dasharray: str | None = None
    timeline_connector_stroke_dasharray: str | None = None
    timeline_duration_bracket_stroke_dasharray: str | None = None
    timeline_top_colors: list[str] = field(
        default_factory=lambda: [
            "deepskyblue",
            "gold",
            "tomato",
            "springgreen",
            "lightskyblue",
        ]
    )
    timeline_bottom_colors: list[str] = field(
        default_factory=lambda: [
            "midnightblue",
            "springgreen",
            "deepskyblue",
            "gold",
            "tomato",
        ]
    )
    # Fiscal period/quarter bands in timeline header (requires --fiscal)
    timeline_show_fiscal_periods: bool = False
    timeline_show_fiscal_quarters: bool = False

    # Blockplan styling and behavior
    blockplan_background_color: str = "none"
    blockplan_grid_color: str = "grey"
    blockplan_grid_opacity: float = 0.6
    blockplan_grid_line_width: float = 1.0
    blockplan_grid_dasharray: str | None = None
    blockplan_timeband_line_color: str | None = None
    blockplan_timeband_line_width: float | None = None
    blockplan_timeband_line_opacity: float | None = None
    blockplan_timeband_line_dasharray: str | None = None
    blockplan_label_column_ratio: float = 0.16
    blockplan_band_row_height: float = 10.0
    blockplan_fiscal_year_start_month: int = 10
    blockplan_week_start: int = 0  # 0=Monday
    blockplan_show_unmatched_lane: bool = True
    blockplan_unmatched_lane_name: str = "Unmatched"
    blockplan_lane_match_mode: str = "first"  # "first" or "all"
    blockplan_palette: list[str] = field(
        default_factory=lambda: [
            "lightskyblue",
            "gold",
            "tomato",
            "springgreen",
            "plum",
            "khaki",
        ]
    )
    blockplan_top_time_bands: list[dict[str, Any]] = field(
        default_factory=lambda: [
            {
                "label": "Fiscal Quarter",
                "unit": "fiscal_quarter",
                "label_format": "FY{fy} Q{q}",
                "fill_color": "none",
                "show_every": 1,
            },
            {
                "label": "PI",
                "unit": "interval",
                "interval_days": 70,
                "prefix": "PI ",
                "start_index": 1,
                "fill_color": "none",
                "show_every": 1,
            },
            {
                "label": "Sprint",
                "unit": "interval",
                "interval_days": 14,
                "prefix": "Sprint ",
                "start_index": 1,
                "fill_color": "none",
                "show_every": 1,
            },
            {
                "label": "Month",
                "unit": "month",
                "date_format": "MMM YYYY",
                "fill_color": "none",
                "show_every": 1,
            },
            {
                "label": "Week Number",
                "unit": "week",
                "label_format": "Week {week}",
                "fill_color": "none",
                "show_every": 1,
            },
            {
                "label": "Date",
                "unit": "date",
                "date_format": "D",
                "fill_color": "none",
                "show_every": 1,
            },
            {
                "label": "DoW",
                "unit": "dow",
                "date_format": "ddd",
                "fill_color": "none",
                "show_every": 1,
            },
        ]
    )
    blockplan_bottom_time_bands: list[dict[str, Any]] = field(default_factory=list)
    blockplan_swimlanes: list[dict[str, Any]] = field(
        default_factory=lambda: [
            {
                "name": "Engineering",
                "match": {"resource_groups": ["engineering", "dev"]},
            },
            {"name": "Operations", "match": {"resource_groups": ["operations", "ops"]}},
            {"name": "Quality", "match": {"resource_groups": ["quality", "qa"]}},
        ]
    )
    blockplan_header_font: str = Fonts.RC_BOLD
    blockplan_header_font_size: float | None = None
    blockplan_header_label_color: str = "black"
    blockplan_header_label_opacity: float = 1.0
    blockplan_header_label_align_h: str = "left"  # left | center | right
    blockplan_header_heading_fill_color: str = "none"
    blockplan_band_font: str = Fonts.RC_BOLD
    blockplan_band_font_size: float | None = None
    blockplan_timeband_label_color: str = "black"
    blockplan_timeband_label_opacity: float = 1.0
    blockplan_timeband_fill_color: str = "none"
    blockplan_timeband_fill_palette: list[str] = field(default_factory=list)
    blockplan_timeband_fill_opacity: float = 1.0
    blockplan_lane_heading_fill_color: str = "none"
    blockplan_lane_label_font: str = Fonts.RC_BOLD
    blockplan_lane_label_font_size: float | None = None
    blockplan_lane_label_color: str = "black"
    blockplan_lane_label_align_h: str = "left"  # left | center | right
    blockplan_lane_label_align_v: str = "middle"  # top | middle | bottom
    blockplan_lane_label_rotation: float = (
        0.0  # clockwise degrees; -90 → bottom-to-top, +90 → top-to-bottom
    )
    blockplan_lane_split_ratio: float = 0.5  # divider position within the lane (0.0–1.0); 0.0 or 1.0 = no divider, both types share the full lane
    # ── Blockplan text styling (uniform) ─────────────────────────────────────
    blockplan_text_font_name: str = Fonts.RC_LIGHT
    blockplan_text_font_color: str = "navy"
    blockplan_text_font_size: float | None = None
    blockplan_text_font_opacity: float = 1.0
    blockplan_text_alignment: str = "left"
    blockplan_name_text_font_name: str = Fonts.RC_LIGHT
    blockplan_name_text_font_color: str = "navy"
    blockplan_name_text_font_size: float | None = None
    blockplan_name_text_font_opacity: float = 1.0
    blockplan_name_text_alignment: str = "left"
    blockplan_notes_text_font_name: str | None = None
    blockplan_notes_text_font_color: str | None = None
    blockplan_notes_text_font_size: float | None = None
    blockplan_notes_text_font_opacity: float = 1.0
    blockplan_notes_text_alignment: str = "left"
    # Blockplan event/duration date & marker fields (not renamed)
    blockplan_event_show_date: bool = False
    blockplan_event_date_font: str = Fonts.RC_LIGHT
    blockplan_event_date_font_size: float | None = None
    blockplan_event_date_color: str = "grey"
    blockplan_event_date_format: str = "YYYY-MM-DD"
    blockplan_marker_radius: float = 2.0
    blockplan_duration_fill_opacity: float = 0.35
    blockplan_duration_stroke_color: str | None = None
    blockplan_duration_stroke_width: float = 1.0
    blockplan_duration_stroke_opacity: float = 0.9
    blockplan_duration_stroke_dasharray: str | None = None
    blockplan_duration_bar_height: float = 8.0
    blockplan_duration_icon_visible: bool = False
    blockplan_duration_show_start_date: bool = False
    blockplan_duration_show_end_date: bool = False
    blockplan_duration_date_format: str = "MMM D"
    blockplan_duration_date_font: str = Fonts.RC_LIGHT
    blockplan_duration_date_font_size: float | None = None
    blockplan_duration_date_color: str | None = None
    blockplan_vertical_lines: list[dict[str, Any]] = field(default_factory=list)
    blockplan_vertical_line_color: str = "red"
    blockplan_vertical_line_width: float = 1.5
    blockplan_vertical_line_dasharray: str | None = None
    blockplan_vertical_line_opacity: float = 0.9
    blockplan_vertical_line_fill_color: str = (
        "none"  # default no fill; set to color, list, or palette
    )
    blockplan_vertical_line_fill_opacity: float = 0.2

    # ── Compact Activities Plan ───────────────────────────────────────────────
    compactplan_background_color: str = "none"
    compactplan_time_bands: list[dict[str, Any]] = field(
        default_factory=lambda: [
            {
                "label": "Week",
                "unit": "week",
                "label_format": "Week {n}",
                "fill_color": "none",
                "alt_fill_color": "#f2f2f2",
                "show_every": 1,
            }
        ]
    )
    compactplan_band_row_height: float = 22.0
    # ── Compact plan text styling (uniform) ──────────────────────────────────
    compactplan_text_font_name: str | None = None
    compactplan_text_font_color: str = "black"
    compactplan_text_font_size: float | None = None
    compactplan_text_font_opacity: float = 1.0
    compactplan_text_alignment: str = "left"
    compactplan_name_text_font_name: str | None = None
    compactplan_name_text_font_color: str = "#595959"
    compactplan_name_text_font_size: float | None = None
    compactplan_name_text_font_opacity: float = 1.0
    compactplan_name_text_alignment: str = "left"
    compactplan_notes_text_font_name: str | None = None
    compactplan_notes_text_font_color: str = "#595959"
    compactplan_notes_text_font_size: float | None = None
    compactplan_notes_text_font_opacity: float = 1.0
    compactplan_notes_text_alignment: str = "left"
    compactplan_show_axis: bool = True
    compactplan_axis_color: str = "#7f7f7f"
    compactplan_axis_width: float = 1.75
    compactplan_axis_dasharray: str = "1.75,7.0"
    compactplan_axis_opacity: float = 1.0
    compactplan_axis_padding: float = 4.0
    compactplan_duration_line_width: float = 5.0
    compactplan_duration_stroke_dasharray: str | None = None
    compactplan_duration_opacity: float = 1.0
    compactplan_lane_spacing: float = 6.0
    compactplan_show_duration_icons: bool = True
    compactplan_duration_icon_list: str = "darksquare"  # key into ICON_SETS
    compactplan_duration_icon_height: float = 8.0
    compactplan_duration_icon_color: str | None = None  # None = use line color
    compactplan_palette: list[str] = field(
        default_factory=lambda: [
            "#92d050",
            "#6b9bc7",
            "gold",
            "tomato",
            "plum",
            "khaki",
            "deepskyblue",
            "coral",
            "mediumseagreen",
            "mediumpurple",
        ]
    )
    compactplan_milestone_color: str = "black"
    compactplan_milestone_icon: str | None = None
    compactplan_milestone_flag_width: float = 7.0
    compactplan_milestone_flag_height: float = 9.0
    compactplan_show_milestone_labels: bool = True
    compactplan_show_legend: bool = True
    compactplan_legend_swatch_width: float = 18.0
    compactplan_legend_row_height: float = 10.0
    compactplan_legend_area_ratio: float = 0.28
    compactplan_legend_column_split: float = 0.5  # fraction of area_w given to the left (group) column
    compactplan_legend_team_columns: int = 2  # sub-columns within the left legend area
    compactplan_header_bottom_y: float | None = None
    compactplan_key_top_y: float | None = None
    compactplan_show_milestone_list: bool = False
    compactplan_milestone_list_date_format: str = "M/D"
    compactplan_milestone_list_date_color: str = "#595959"
    compactplan_milestone_list_row_height: float = 10.0
    compactplan_milestone_list_date_col_width: float = 32.0
    compactplan_milestone_list_section_gap: float = 6.0

    # ── Continuation icon ─────────────────────────────────────────────────────
    # When a duration line extends beyond the specified end date it is clamped
    # to the timeline edge and, when show_continuation_icon is True, a small
    # icon is drawn at that edge to signal that the activity continues.
    compactplan_show_continuation_icon: bool = True
    compactplan_continuation_icon: str = "arrow-right"
    compactplan_continuation_icon_height: float = 8.0
    compactplan_continuation_icon_color: str | None = None  # None = use line color
    compactplan_continuation_legend_text: str = "activity continues"
    compactplan_continuation_section_gap: float = 4.0
    compactplan_show_axis_legend: bool = True  # show axis sample + label in the legend
    compactplan_legend_axis_text: str = "timeline"  # label beside the axis sample

    # ── ExcelHeader ───────────────────────────────────────────────────────────
    # Settings for the excelheader subcommand (Excel workbook output).
    excelheader_font_name: str = "Calibri"  # System-installed Excel font for all cells
    excelheader_font_size: int = 9  # Font size in points
    excelheader_top_time_bands: list[dict[str, Any]] = field(
        default_factory=lambda: [
            {
                "label": "Fiscal Quarter",
                "unit": "fiscal_quarter",
                "label_format": "FY{fy} Q{q}",
                "fill_color": "none",
                "show_every": 1,
            },
            {
                "label": "PI",
                "unit": "interval",
                "interval_days": 70,
                "prefix": "PI ",
                "start_index": 1,
                "fill_color": "none",
                "show_every": 1,
            },
            {
                "label": "Sprint",
                "unit": "interval",
                "interval_days": 14,
                "prefix": "Sprint ",
                "start_index": 1,
                "fill_color": "none",
                "show_every": 1,
            },
            {
                "label": "Month",
                "unit": "month",
                "date_format": "MMM YYYY",
                "fill_color": "none",
                "show_every": 1,
            },
            {
                "label": "Week Number",
                "unit": "week",
                "label_format": "Week {week}",
                "fill_color": "none",
                "show_every": 1,
            },
            {
                "label": "Date",
                "unit": "date",
                "date_format": "D",
                "fill_color": "none",
                "show_every": 1,
            },
            {
                "label": "DoW",
                "unit": "dow",
                "date_format": "ddd",
                "fill_color": "none",
                "show_every": 1,
            },
        ]
    )
    excelheader_vertical_lines: list[dict[str, Any]] = field(default_factory=list)
    excelheader_vertical_line_color: str = "red"
    excelheader_vertical_line_width: float = 1.5
    excelheader_vertical_line_dasharray: str | None = None
    excelheader_vertical_line_opacity: float = 0.9
    excelheader_vertical_line_fill_color: str = "none"
    excelheader_vertical_line_fill_opacity: float = 0.2
    excelheader_band_row_height: float = 18.0
    excelheader_header_heading_fill_color: str = "none"
    excelheader_header_label_color: str = "black"
    excelheader_header_label_align_h: str = "left"  # left | center | right
    excelheader_timeband_fill_color: str = "none"
    excelheader_timeband_fill_palette: list[str] = field(default_factory=list)
    excelheader_timeband_label_color: str = "black"

    # Overflow indicator
    overflow_indicator_icon: str = "overflow"
    overflow_indicator_color: str = "red"

    # Default icon shown when an event's icon name cannot be found in the icons table
    default_missing_icon: str | None = None

    # Watermark text
    watermark: str = ""
    watermark_color: str = "white"
    watermark_font: str = "CascadiaCode"
    watermark_size: int | None = None
    watermark_resize_mode: str = "fit"  # "fit" (default) or "stretch"
    watermark_alpha: float = 0.3
    watermark_rotation_angle: float = 0.0

    # Watermark image
    imagemark: str = ""
    imagemark_width: int = 300
    imagemark_height: int = 300
    imagemark_rotation_angle: float = 0.0

    # Theme-overridable color maps (None = use module-level defaults)
    theme_fiscalperiodcolors: dict[str, str] | None = None
    theme_monthcolors: dict[str, str] | None = None
    theme_specialdaycolor: str | None = None
    theme_hashlinecolor: str | None = None
    theme_weekly_hash_rules: list[dict[str, Any]] | None = None
    theme_weekly_hash_pattern: str | None = None
    theme_mini_day_box_hash_rules: list[dict[str, Any]] | None = None

    # Item placement order in day boxes (determines which type gets top rows).
    # A list of tokens; the first token's item type is placed first, etc.
    # Type tokens: "milestones", "events", "durations"
    # Special tokens: "priority" (sort by priority field, no type grouping),
    #                 "alphabetical" (sort by name)
    # Example: ["milestones", "events", "durations"]
    item_placement_order: list[str] = field(default_factory=lambda: ["priority"])
    theme_resource_group_colors: dict[str, str] | None = None
    theme_special_day_type_colors: dict[str, str] | None = None
    theme_federal_holiday_color: str | None = None
    theme_federal_holiday_alpha: float | None = None
    theme_company_holiday_color: str | None = None
    theme_company_holiday_alpha: float | None = None

    # DB palette names — resolved at render time from calendar.db palettes table
    theme_month_palette: str | None = None
    theme_fiscal_palette: str | None = None
    theme_group_palette: str | None = None
    theme_timeline_palette: str | None = None
    theme_blockplan_palette_name: str | None = None
    theme_compactplan_palette_name: str | None = None

    # Group colors for event categorization
    group_colors: list = field(
        default_factory=lambda: [
            "bisque",
            "skyblue",
            "lawngreen",
            "cyan",
            "purple",
            "silver",
            "burlywood",
            "cornsilk",
            "goldenrod",
            "plum",
            "slategrey",
            "yellowgreen",
            "linen",
            "gold",
            "plum",
            "orchid",
            "chocolate",
            "brown",
            "maroon",
            "indigo",
            "lime",
            "forestgreen",
        ]
    )

    def __post_init__(self) -> None:
        """Validate configuration invariants after construction."""
        if self.weekend_style not in range(5):
            raise ValueError(f"weekend_style must be 0–4, got {self.weekend_style}")
        if self.mini_columns < 1:
            raise ValueError(f"mini_columns must be >= 1, got {self.mini_columns}")
        _valid_placement_tokens = frozenset(
            {"priority", "milestones", "events", "durations", "alphabetical"}
        )
        if (
            not isinstance(self.item_placement_order, list)
            or not self.item_placement_order
        ):
            raise ValueError(
                "item_placement_order must be a non-empty list of placement tokens, "
                f"got {self.item_placement_order!r}"
            )
        _invalid_tokens = [
            t for t in self.item_placement_order if t not in _valid_placement_tokens
        ]
        if _invalid_tokens:
            raise ValueError(
                f"item_placement_order contains invalid tokens {_invalid_tokens!r}; "
                f"valid tokens are {sorted(_valid_placement_tokens)}"
            )
        if self.blockplan_lane_match_mode not in {"first", "all"}:
            raise ValueError(
                "blockplan_lane_match_mode must be 'first' or 'all', "
                f"got {self.blockplan_lane_match_mode!r}"
            )
        if self.blockplan_lane_label_align_h not in {"left", "center", "right"}:
            raise ValueError(
                "blockplan_lane_label_align_h must be 'left', 'center', or 'right', "
                f"got {self.blockplan_lane_label_align_h!r}"
            )
        if self.blockplan_lane_label_align_v not in {"top", "middle", "bottom"}:
            raise ValueError(
                "blockplan_lane_label_align_v must be 'top', 'middle', or 'bottom', "
                f"got {self.blockplan_lane_label_align_v!r}"
            )
        if self.blockplan_header_label_align_h not in {"left", "center", "right"}:
            raise ValueError(
                "blockplan_header_label_align_h must be 'left', 'center', or 'right', "
                f"got {self.blockplan_header_label_align_h!r}"
            )


def create_calendar_config() -> CalendarConfig:
    """Factory function to create a new CalendarConfig instance."""
    return CalendarConfig()


def create_sample_blockplan_swimlanes_from_wbs(
    wbs_values: list[str] | tuple[str, ...],
    *,
    lane_name_format: str = "WBS {wbs}",
    sort_values: bool = True,
    include_unmatched_lane: bool = True,
    unmatched_lane_name: str = "Unmatched",
) -> list[dict[str, Any]]:
    """
    Build a sample blockplan swimlane list from WBS values/prefixes.

    Each unique non-empty WBS token becomes a lane that matches event WBS values
    by prefix using blockplan's ``wbs_prefixes`` matcher.

    Example:
        create_sample_blockplan_swimlanes_from_wbs(["1", "2.1", "3."])
        -> [
             {"name": "WBS 1",   "match": {"wbs_prefixes": ["1"]}},
             {"name": "WBS 2.1", "match": {"wbs_prefixes": ["2.1"]}},
             {"name": "WBS 3.",  "match": {"wbs_prefixes": ["3."]}},
             {"name": "Unmatched", "match": {}},
           ]

    Args:
        wbs_values: WBS values/prefixes to convert into lanes.
        lane_name_format: Format for each lane name; receives ``{wbs}``.
        sort_values: Sort unique WBS values for deterministic output.
        include_unmatched_lane: Append a final catch-all lane with empty match.
        unmatched_lane_name: Lane name for the catch-all lane.

    Returns:
        List of blockplan swimlane dictionaries suitable for
        ``CalendarConfig.blockplan_swimlanes``.
    """
    cleaned: list[str] = []
    seen: set[str] = set()
    for raw in wbs_values:
        token = str(raw or "").strip()
        if not token:
            continue
        if token in seen:
            continue
        seen.add(token)
        cleaned.append(token)

    if sort_values:
        cleaned.sort()

    lanes: list[dict[str, Any]] = []
    for token in cleaned:
        try:
            lane_name = lane_name_format.format(wbs=token)
        except Exception:
            lane_name = f"WBS {token}"
        lanes.append(
            {
                "name": lane_name,
                "match": {"wbs_prefixes": [token]},
            }
        )

    if include_unmatched_lane:
        lanes.append({"name": unmatched_lane_name, "match": {}})

    return lanes


# =============================================================================
# Unit Conversions
# =============================================================================

INCH_TO_CM = 2.54
CM_TO_INCH = 0.3937
MM_TO_INCH = 0.039
INCH_TO_PT = 72
CM_TO_PT = 28.34
MM_TO_PT = 2.834


# =============================================================================
# Calendar Labels
# =============================================================================

month_names = [
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
]

month_short = [
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
]

day_names = [
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
]

day_short = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

squares = [
    "square-01",
    "square-02",
    "square-03",
    "square-04",
    "square-05",
    "square-06",
    "square-07",
    "square-08",
    "square-09",
    "square-10",
    "square-11",
    "square-12",
    "square-13",
    "square-14",
    "square-15",
    "square-16",
    "square-17",
    "square-18",
    "square-19",
    "square-20",
    "square-21",
    "square-22",
    "square-23",
    "square-24",
    "square-25",
    "square-26",
    "square-27",
    "square-28",
    "square-29",
    "square-30",
    "square-31",
]

darksquare = [
    "darksquare-01",
    "darksquare-02",
    "darksquare-03",
    "darksquare-04",
    "darksquare-05",
    "darksquare-06",
    "darksquare-07",
    "darksquare-08",
    "darksquare-09",
    "darksquare-10",
    "darksquare-11",
    "darksquare-12",
    "darksquare-13",
    "darksquare-14",
    "darksquare-15",
    "darksquare-16",
    "darksquare-17",
    "darksquare-18",
    "darksquare-19",
    "darksquare-20",
    "darksquare-21",
    "darksquare-22",
    "darksquare-23",
    "darksquare-24",
    "darksquare-25",
    "darksquare-26",
    "darksquare-27",
    "darksquare-28",
    "darksquare-29",
    "darksquare-30",
    "darksquare-31",
    "darksquare-32",
    "darksquare-33",
    "darksquare-34",
    "darksquare-35",
    "darksquare-36",
    "darksquare-37",
    "darksquare-38",
    "darksquare-39",
    "darksquare-40",
    "darksquare-41",
    "darksquare-42",
    "darksquare-43",
    "darksquare-44",
    "darksquare-45",
    "darksquare-46",
    "darksquare-47",
    "darksquare-48",
    "darksquare-49",
    "darksquare-50",
]

darkcircles = [
    "darkcircle-01",
    "darkcircle-02",
    "darkcircle-03",
    "darkcircle-04",
    "darkcircle-05",
    "darkcircle-06",
    "darkcircle-07",
    "darkcircle-08",
    "darkcircle-09",
    "darkcircle-10",
    "darkcircle-11",
    "darkcircle-12",
    "darkcircle-13",
    "darkcircle-14",
    "darkcircle-15",
    "darkcircle-16",
    "darkcircle-17",
    "darkcircle-18",
    "darkcircle-19",
    "darkcircle-20",
    "darkcircle-21",
    "darkcircle-22",
    "darkcircle-23",
    "darkcircle-24",
    "darkcircle-25",
    "darkcircle-26",
    "darkcircle-27",
    "darkcircle-28",
    "darkcircle-29",
    "darkcircle-30",
    "darkcircle-31",
]

circles = [
    "circle-1",
    "circle-2",
    "circle-3",
    "circle-4",
    "circle-5",
    "circle-6",
    "circle-7",
    "circle-8",
    "circle-9",
    "circle-10",
    "circle-11",
    "circle-12",
    "circle-13",
    "circle-14",
    "circle-15",
    "circle-16",
    "circle-17",
    "circle-18",
    "circle-19",
    "circle-20",
    "circle-21",
    "circle-22",
    "circle-23",
    "circle-24",
    "circle-25",
    "circle-26",
    "circle-27",
    "circle-28",
    "circle-29",
    "circle-30",
    "circle-31",
]

squircles = [
    "squircle-01",
    "squircle-02",
    "squircle-03",
    "squircle-04",
    "squircle-05",
    "squircle-06",
    "squircle-07",
    "squircle-08",
    "squircle-09",
    "squircle-10",
    "squircle-11",
    "squircle-12",
    "squircle-13",
    "squircle-14",
    "squircle-15",
    "squircle-16",
    "squircle-17",
    "squircle-18",
    "squircle-19",
    "squircle-20",
    "squircle-21",
    "squircle-22",
    "squircle-23",
    "squircle-24",
    "squircle-25",
    "squircle-26",
    "squircle-27",
    "squircle-28",
    "squircle-29",
    "squircle-30",
    "squircle-31",
]

darksquircles = [
    "darksquircle-01",
    "darksquircle-02",
    "darksquircle-03",
    "darksquircle-04",
    "darksquircle-05",
    "darksquircle-06",
    "darksquircle-07",
    "darksquircle-08",
    "darksquircle-09",
    "darksquircle-10",
    "darksquircle-11",
    "darksquircle-12",
    "darksquircle-13",
    "darksquircle-14",
    "darksquircle-15",
    "darksquircle-16",
    "darksquircle-17",
    "darksquircle-18",
    "darksquircle-19",
    "darksquircle-20",
    "darksquircle-21",
    "darksquircle-22",
    "darksquircle-23",
    "darksquircle-24",
    "darksquircle-25",
    "darksquircle-26",
    "darksquircle-27",
    "darksquircle-28",
    "darksquircle-29",
    "darksquircle-30",
    "darksquircle-31",
]

# Canonical mapping of icon-list names to their icon-name sequences.
# Used by the compactplan duration-start icons and the mini-icon view.
ICON_SETS: dict[str, list[str]] = {
    "squares": squares,
    "darksquare": darksquare,
    "darkcircles": darkcircles,
    "circles": circles,
    "squircles": squircles,
    "darksquircles": darksquircles,
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

specialdaycolor = "lightblue"

specialdaycolors: dict[str, str] = {
    "federal": "blue",
    "company": "red",
    "nonworkday": "pink",
    "furlough": "lightsteelblue",
    "special": "yellow",
}

hashlinecolor = "white"

Resource_Group_colors: dict[str, str] = {
    "A": "black",
    "B": "yellow",
    "C": "red",
    "D": "grey",
}


# =============================================================================
# Font Registry
# =============================================================================


def _build_font_registry() -> dict[str, str]:
    """Build the font registry by scanning fonts/*.ttf and fonts/*.otf at import time.

    Each font file contributes an entry keyed by its stem (e.g. "Roboto-Bold").
    TTF entries take precedence over OTF when both share the same stem.
    Compatibility aliases that differ from the stem are added afterwards.
    """
    fonts_dir = Path(__file__).parent.parent / "fonts"
    registry: dict[str, str] = {}
    if fonts_dir.is_dir():
        for font in sorted(fonts_dir.glob("*.otf")):
            registry[font.stem] = f"fonts/{font.name}"
        for font in sorted(fonts_dir.glob("*.ttf")):
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
        raise KeyError(
            f"Font '{font_name}' not found in FONT_REGISTRY. "
            f"Available fonts: {sorted(FONT_REGISTRY)}"
        )
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
# Weekend Style Predicate Helpers
# =============================================================================


def weekend_style_is_workweek(style: int) -> bool:
    """True for style 0 (Mon–Fri only, no weekend days shown)."""
    return style == 0


def weekend_style_starts_sunday(style: int) -> bool:
    """True for styles 1 and 2 (week starts on Sunday)."""
    return style in (1, 2)


def weekend_style_starts_monday(style: int) -> bool:
    """True for styles 3 and 4 (week starts on Monday)."""
    return style in (3, 4)


def weekend_style_has_half_weekends(style: int) -> bool:
    """True for styles 2 and 4 (weekends rendered at half column width)."""
    return style in (2, 4)


def weekend_style_includes_weekends(style: int) -> bool:
    """True for styles 1–4 (any weekend days are shown)."""
    return style != 0


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
    base_margin = (
        round(config.pageX * config.margin_percent, 2) if config.include_margin else 0.0
    )
    left = float(config.margin_left) if config.margin_left is not None else base_margin
    right = (
        float(config.margin_right) if config.margin_right is not None else base_margin
    )
    top = float(config.margin_top) if config.margin_top is not None else base_margin
    bottom = (
        float(config.margin_bottom) if config.margin_bottom is not None else base_margin
    )

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
    """
    Set font sizes using page-dimension-derived formulas.

    All font sizes scale proportionally to pageY (the taller dimension
    in the current orientation). Layout percentages use fixed ratios
    that work across all paper sizes. Min/max clamps prevent illegibly
    small or absurdly large text on extreme paper sizes.

    Args:
        config: Calendar configuration to update

    Returns:
        The same config instance with font sizes set
    """
    h = config.pageY

    # Layout percentages (fixed ratios, work for all sizes)
    config.week_number_percent = 0.02
    config.margin_percent = 0.05
    config.color_key_percent = 0.15
    config.header_percent = 0.020
    config.footer_percent = 0.018
    config.day_name_percent = 0.02
    config.month_percent = 0.03

    # Font sizes — proportional to page height, with optional theme-selected
    # desired base size (event text) that scales all related sizes.
    base_event_size = _clamp(h * 0.009, 6.0, 32.0)
    scale = 1.0
    if config.desired_font_size is not None:
        desired = float(config.desired_font_size)
        # Reference desired size on Letter-height pages and scale with page height.
        target_event_size = _clamp(desired * (h / 792.0), 6.0, 32.0)
        if base_event_size > 0:
            scale = target_event_size / base_event_size

    config.week_number_font_size = _clamp(
        _clamp(h * 0.01, 6.0, 32.0) * scale, 6.0, 32.0
    )
    config.day_name_font_size = _clamp(_clamp(h * 0.012, 6.0, 32.0) * scale, 6.0, 32.0)
    config.color_key_font_size = _clamp(_clamp(h * 0.010, 6.0, 32.0) * scale, 6.0, 32.0)

    config.header_left_font_size = _clamp(
        _clamp(h * 0.013, 6.0, 32.0) * scale, 6.0, 32.0
    )
    config.header_center_font_size = config.header_left_font_size
    config.header_right_font_size = config.header_left_font_size

    config.footer_left_font_size = _clamp(
        _clamp(h * 0.010, 6.0, 32.0) * scale, 6.0, 32.0
    )
    config.footer_center_font_size = config.footer_left_font_size
    config.footer_right_font_size = config.footer_left_font_size

    config.day_box_number_font_size = _clamp(
        _clamp(h * 0.013, 8.0, 32.0) * scale, 8.0, 32.0
    )
    config.day_box_icon_font_size = config.day_box_number_font_size

    config.fiscal_period_label_font_size = config.day_box_number_font_size * 0.7

    # Weekly text sizes
    config.weekly_name_text_font_size = _clamp(base_event_size * scale, 6.0, 32.0)
    config.weekly_notes_text_font_size = config.weekly_name_text_font_size * 0.9
    config.weekly_text_font_size = config.weekly_name_text_font_size
    config.event_icon_font_size = config.weekly_name_text_font_size

    # Mini calendar font sizes
    config.mini_cell_font_size = _clamp(_clamp(h * 0.012, 6.0, 20.0) * scale, 6.0, 20.0)
    config.mini_title_font_size = _clamp(
        _clamp(h * 0.014, 6.0, 24.0) * scale, 6.0, 24.0
    )
    config.mini_header_font_size = _clamp(
        _clamp(h * 0.009, 6.0, 24.0) * scale, 6.0, 24.0
    )
    config.mini_week_number_font_size = _clamp(
        _clamp(h * 0.012, 6.0, 24.0) * scale, 6.0, 24.0
    )

    # Mini details page font sizes
    config.mini_details_title_font_size = _clamp(
        _clamp(h * 0.014, 6.0, 24.0) * scale, 6.0, 24.0
    )
    config.mini_details_header_font_size = _clamp(
        _clamp(h * 0.010, 6.0, 24.0) * scale, 6.0, 24.0
    )
    config.mini_details_name_text_font_size = _clamp(
        _clamp(h * 0.010, 6.0, 24.0) * scale, 6.0, 24.0
    )
    config.mini_details_text_font_size = config.mini_details_name_text_font_size
    config.mini_details_notes_text_font_size = _clamp(
        _clamp(h * 0.009, 6.0, 24.0) * scale, 6.0, 24.0
    )

    # Timeline text sizes
    base_event = config.weekly_name_text_font_size
    config.timeline_name_text_font_size = max(10.0, base_event + 2.0)
    config.timeline_notes_text_font_size = max(8.0, base_event * 0.9)
    config.timeline_text_font_size = config.timeline_name_text_font_size

    # Blockplan font sizes
    config.blockplan_header_font_size = _clamp(
        _clamp(h * 0.010, 6.0, 24.0) * scale, 6.0, 24.0
    )
    config.blockplan_band_font_size = _clamp(
        _clamp(h * 0.010, 6.0, 24.0) * scale, 6.0, 24.0
    )
    config.blockplan_lane_label_font_size = _clamp(
        _clamp(h * 0.011, 6.0, 24.0) * scale, 6.0, 24.0
    )
    config.blockplan_name_text_font_size = _clamp(
        _clamp(h * 0.009, 6.0, 24.0) * scale, 6.0, 24.0
    )
    config.blockplan_text_font_size = config.blockplan_name_text_font_size
    config.blockplan_notes_text_font_size = config.blockplan_name_text_font_size * 0.85
    config.blockplan_event_date_font_size = _clamp(
        _clamp(h * 0.008, 6.0, 20.0) * scale, 6.0, 20.0
    )
    config.blockplan_duration_date_font_size = _clamp(
        _clamp(h * 0.008, 6.0, 20.0) * scale, 6.0, 20.0
    )

    # Watermark base font size (paper-size aware, theme-overridable)
    config.watermark_size = int(round(_clamp(h * 0.10, 24.0, 256.0)))

    return config
