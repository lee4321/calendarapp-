#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
EventCalendar v9 - SVG Calendar Generator

Creates customizable SVG calendars with events from a SQLite database.
Supports multiple visualization formats including weekly, mini, text-mini,
and timeline views.

(c) 2026 A. Lee Ingram
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

import arrow

from config.config import (
    CalendarConfig,
    create_calendar_config,
    setfontsizes,
)
from shared.db_access import CalendarDB
from shared.date_utils import InvalidDateError, calc_calendar_range
from visualizers.factory import VisualizerFactory
from visualizers.weekly.layout import WeeklyCalendarLayout

if TYPE_CHECKING:
    from argparse import Namespace

# Module logger
logger = logging.getLogger(__name__)


# =============================================================================
# Exceptions
# =============================================================================


class CalendarError(Exception):
    """Base exception for calendar errors."""

    pass


class DatabaseError(CalendarError):
    """Raised when there's a database access error."""

    pass


class ConfigError(CalendarError):
    """Raised when configuration is invalid."""

    pass


# =============================================================================
# Template Variable Replacement
# =============================================================================


def replace_template_vars(config: CalendarConfig, text: str) -> str:
    """
    Replace bracket-style template variables in header/footer/watermark text.

    This is the single expansion point for all user-supplied text fields so
    that every slot (headerleft, headercenter, footerright, watermark, …)
    behaves identically.  It must be called *after* ``calc_calendar_range()``
    has populated ``config.adjustedstart`` and ``config.adjustedend``.

    Supported variables:
        [now]       — current datetime (YYYY-MM-DD HH:mm)
        [date]      — current date (YYYY-MM-DD)
        [startdate] — config.adjustedstart (first rendered calendar day)
        [enddate]   — config.adjustedend   (last rendered calendar day)
        [events]    — config.events        (database path description)

    Called by:
        _apply_text_options() — which is itself called from run() after
        calc_calendar_range() has resolved the adjusted date boundaries.

    Args:
        config: Calendar configuration (must have adjustedstart/adjustedend set)
        text: Text containing bracket-delimited template variables

    Returns:
        Text with all recognised variables substituted; unrecognised tokens
        are left intact.
    """
    now = arrow.now()
    replacements = {
        "[now]": now.format("YYYY-MM-DD HH:mm"),
        "[date]": now.format("YYYY-MM-DD"),
        "[startdate]": str(config.adjustedstart),
        "[enddate]": str(config.adjustedend),
        "[events]": str(config.events),
    }

    for var, value in replacements.items():
        text = text.replace(var, value)

    return text


# =============================================================================
# CLI Argument Parsing
# =============================================================================


def _parse_atfile_lines(path: str) -> list[str]:
    """
    Read an ``@file`` argument file and return sanitised argument tokens.

    argparse's built-in ``fromfile_prefix_chars`` does not strip comments;
    this function provides a sanitised alternative that supports human-readable
    argument presets with explanatory comments.

    Sanitisation rules (applied in order):
    - Blank lines are dropped.
    - Lines whose first two characters are ``# `` are dropped entirely
      (full-line comments).
    - The portion of a line after the first ``# `` occurrence is dropped
      (trailing comments).
    - A bare ``#`` *not* followed by a space is preserved, so hex colour
      values like ``#FF0000`` and tags like ``#1`` survive intact.

    Called by:
        _expand_sanitized_atfiles() — which recursively resolves all @file
        tokens in the raw CLI token list before argparse sees them.

    Args:
        path: Filesystem path to the argument file.

    Returns:
        List of non-empty, comment-stripped argument tokens.
    """
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    out: list[str] = []
    for line in lines:
        if not line.strip():
            continue
        if line.startswith("# "):
            continue
        if "# " in line:
            line = line.split("# ", 1)[0]
        line = line.strip()
        if line:
            out.append(line)
    return out


def _expand_sanitized_atfiles(tokens: list[str], *, depth: int = 0) -> list[str]:
    """
    Recursively expand ``@filename`` tokens in a CLI token list.

    Each token starting with ``@`` is treated as a reference to an argument
    file.  The file is read and parsed via ``_parse_atfile_lines()``, and the
    resulting tokens replace the original ``@file`` token.  Files may reference
    other ``@file`` tokens (nesting), allowing argument presets to be composed
    from smaller reusable fragments.

    Recursion guard: raises ``ConfigError`` when nesting depth exceeds 10,
    preventing infinite loops from circular ``@file`` chains.

    Called by:
        run() — immediately after sys.argv is read, before argparse.parse_args().

    Calls:
        _parse_atfile_lines() for every @file token encountered.
        Itself recursively for tokens read from those files.

    Args:
        tokens: Raw CLI tokens, possibly containing ``@filepath`` entries.
        depth:  Current recursion depth (callers should omit this).

    Returns:
        Flat list of expanded tokens with all ``@file`` references resolved.

    Raises:
        ConfigError: If an @file cannot be read or nesting depth exceeds 10.
    """
    if depth > 10:
        raise ConfigError("Too many nested @files while expanding --sanitize-atfiles")

    expanded: list[str] = []
    for tok in tokens:
        if tok.startswith("@") and len(tok) > 1:
            path = tok[1:]
            try:
                parsed = _parse_atfile_lines(path)
            except OSError as e:
                raise ConfigError(f"Failed to read @file '{path}': {e}") from e
            expanded.extend(_expand_sanitized_atfiles(parsed, depth=depth + 1))
        else:
            expanded.append(tok)
    return expanded


def _to_output_dir_path(filename: str) -> str:
    """
    Strip any directory prefix from *filename* and place it under ``output/``.

    This is a path-traversal guard: no matter what the user passes to
    ``--outputfile``, all generated SVG/Excel files land in the local
    ``output/`` subdirectory.  Directory components are discarded silently
    rather than raising an error so that users who copy paths from other
    contexts are not penalised.

    Example:
        ``_to_output_dir_path("../secret/cal.svg")`` → ``"output/cal.svg"``

    Called by:
        run() when setting config.outputfile for calendar-visualizer commands.
    """
    return str(Path("output") / Path(filename).name)


def _create_argument_parser(default_output: str) -> argparse.ArgumentParser:
    """
    Build the full argparse.ArgumentParser for the ecalendar CLI.

    Centralising parser construction here keeps run() focused on dispatch
    logic and makes the entire argument surface easy to survey and extend in
    one place.

    Subcommands registered
    ──────────────────────
    Calendar visualizers : weekly, mini, mini-icon, text-mini, timeline, blockplan
    Output utilities     : excelheader
    Inspection / listing : themes, fonts, fontsheet, papersizes, patterns,
                           icons, iconsheet, colors, colorsheet, palettes, palette
    Help                 : help <subcommand>

    Argument groups (per visualizer subcommand)
    ───────────────────────────────────────────
    - Database Options        --database, --country
    - Output Options          --outputfile, --papersize, --orientation, --shrink
    - Layout Options          --weekends, --header, --footer, --margin, --overflow
    - Header/Footer text      --headerleft, --headercenter, --headerright, …
    - Watermark Options       --watermark, --watermark-rotation-angle, --imagemark
    - Content Filtering       --noevents, --nodurations, --ignorecomplete,
                              --milestones, --rollups, --WBS, --empty
    - Mini Calendar Options   --mini-columns, --mini-rows, --mini-no-adjacent, …
    - Timeline Options        --today-line-length, --today-line-direction, …
    - Fiscal Options          --fiscal, --fiscal-colors, --fiscal-year-offset,
                              --fiscal-show-periods, --fiscal-show-quarters (timeline)
    - Week Number Options     --weeknumbers, --week-number-mode, --week1-start
    - Theme                   --theme
    - Logging                 --verbose, --quiet

    Called by:
        run() at startup, before any argument parsing occurs.

    Args:
        default_output: Timestamped default SVG filename (e.g. ``ecalendar202601011200.svg``).

    Returns:
        Fully configured ArgumentParser ready for parse_args().
    """
    parser = argparse.ArgumentParser(
        prog="EventCalendar v9",
        fromfile_prefix_chars="@",
        description="Create SVG calendars with events from SQLite database",
        epilog=(
            "EventCalendar v, Copyright (C) 2026 A. Lee Ingram, MobileLeverage LLC\n"
            "Change calendar configuration by modifying config/config.py\n"
            "Command line parameters can be read from a file using @filename"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    sub = parser.add_subparsers(dest="command", required=True)

    weekly = sub.add_parser("weekly", help="Generate a weekly calendar")
    mini = sub.add_parser("mini", help="Generate a mini calendar")
    mini_icon = sub.add_parser("mini-icon", help="Generate a mini calendar with icons for day numbers")
    text_mini = sub.add_parser("text-mini", help="Generate a text only mini calendar")
    timeline = sub.add_parser("timeline", help="Generate a timeline")
    blockplan = sub.add_parser("blockplan", help="Generate a blockplan")
    compactplan = sub.add_parser(
        "compactplan",
        help="Generate a compressed activities timeline (duration lines above/below a central axis)",
    )
    excelheader = sub.add_parser(
        "excelheader",
        help="Generate an Excel workbook with blockplan-style timeband header rows",
    )
    themes = sub.add_parser("themes", help="List available themes")
    papers = sub.add_parser("papersizes", help="List available paper sizes")
    patterns = sub.add_parser("patterns", help="List available day-box patterns")
    icons = sub.add_parser("icons", help="List available icons from database")
    colors = sub.add_parser("colors", help="List available colors from database")
    palettes = sub.add_parser(
        "palettes", help="List available color palettes from database"
    )
    palette = sub.add_parser("palette", help="Generate a preview of a named palette")
    iconsheet = sub.add_parser(
        "iconsheet", help="Generate a grid preview of icons from database"
    )
    colorsheet = sub.add_parser(
        "colorsheet", help="Generate a grid preview of named colors from database"
    )
    fonts = sub.add_parser("fonts", help="List available registered fonts")
    fontsheet = sub.add_parser(
        "fontsheet", help="Generate a SVG sample sheet for all registered fonts"
    )
    help_cmd = sub.add_parser(
        "help", help="Show valid configurable values for a subcommand"
    )
    help_cmd.add_argument(
        "subcommand",
        type=str,
        choices=[
            "weekly",
            "mini",
            "mini-icon",
            "text-mini",
            "timeline",
            "blockplan",
            "compactplan",
            "themes",
            "papersizes",
            "patterns",
            "icons",
            "colors",
            "palettes",
            "fonts",
        ],
        help="Subcommand to show help for",
    )

    # Shared argument groups are defined once and applied to all calendar-view
    # parsers to keep option semantics aligned across views.
    # If a flag belongs to every view, add it in these loops rather than
    # copy-pasting per-subcommand definitions.
    # Positional arguments for calendar views
    for view_parser in (weekly, mini, mini_icon, text_mini, timeline, blockplan, compactplan, excelheader):
        view_parser.add_argument(
            "begin",
            type=str,
            nargs="?",
            default=None,
            metavar="START_DATE",
            help="Start date in YYYYMMDD format (will be adjusted to full week)",
        )
        view_parser.add_argument(
            "end",
            type=str,
            nargs="?",
            default=None,
            metavar="END_DATE",
            help="End date in YYYYMMDD format (will be adjusted to full week)",
        )

    # palette subcommand arguments
    palette.add_argument(
        "palette_name",
        type=str,
        metavar="NAME",
        help="Name of the palette to preview (case-sensitive, from DB palettes table)",
    )
    palette.add_argument(
        "--outputfile",
        "-of",
        type=str,
        default=None,
        metavar="PATH",
        help="Output file path (default: output/pallet.svg)",
    )

    # iconsheet subcommand arguments
    iconsheet.add_argument(
        "--filter",
        "-f",
        type=str,
        default=None,
        metavar="TEXT",
        help="Filter icons by name substring (case-insensitive)",
    )
    iconsheet.add_argument(
        "--color",
        "-c",
        type=str,
        default="#333333",
        metavar="COLOR",
        help="Stroke color for icons (default: #333333)",
    )
    iconsheet.add_argument(
        "--outputfile",
        "-of",
        type=str,
        default=None,
        metavar="PATH",
        help="Output file name and path (default: output/iconsheet.svg)",
    )

    # colorsheet subcommand arguments
    colorsheet.add_argument(
        "--filter",
        "-f",
        type=str,
        default=None,
        metavar="TEXT",
        help="Filter colors by name substring (case-insensitive)",
    )
    colorsheet.add_argument(
        "--outputfile",
        "-of",
        type=str,
        default=None,
        metavar="PATH",
        help="Output SVG path (default: output/colorsheet.svg)",
    )

    # excelheader subcommand arguments
    excelheader.add_argument(
        "--outputfile",
        "-of",
        type=str,
        default=None,
        metavar="PATH",
        help="Output .xlsx path (default: output/excelheader.xlsx)",
    )
    excelheader.add_argument(
        "--theme",
        "-th",
        type=str,
        default=None,
        metavar="THEME",
        help="Theme name or path to .yaml theme file",
    )
    excelheader.add_argument(
        "--weekends",
        "-we",
        type=int,
        default=0,
        choices=[0, 1, 2, 3, 4],
        help=(
            "Weekend style: "
            "0=work week only (default), "
            "1=full week Sunday start, "
            "2=half weekends Sunday start, "
            "3=full week Monday start, "
            "4=half weekends Monday start"
        ),
    )
    excelheader.add_argument(
        "--country",
        "-cc",
        type=str,
        default=None,
        metavar="CODE",
        help=(
            "ISO 3166-1 alpha-2 country code(s) for holidays. "
            "Accepts a single code (e.g. US) or a comma-separated list "
            "(e.g. US,CA,GB) to include holidays from multiple countries."
        ),
    )

    # fontsheet subcommand arguments
    fontsheet.add_argument(
        "--filter",
        "-f",
        type=str,
        default=None,
        metavar="TEXT",
        help="Filter fonts by name substring (case-insensitive)",
    )
    fontsheet.add_argument(
        "--color",
        "-c",
        type=str,
        default="#222222",
        metavar="COLOR",
        help="Glyph color (default: #222222)",
    )
    fontsheet.add_argument(
        "--outputfile",
        "-of",
        type=str,
        default=None,
        metavar="PATH",
        help="Output file name and path (default: output/fontsheet.svg)",
    )
    fontsheet.add_argument(
        "--fullset",
        action="store_true",
        default=False,
        help="Show every glyph in the font instead of the three fixed sample rows",
    )

    # Database options
    for view_parser in (
        weekly,
        mini,
        mini_icon,
        text_mini,
        timeline,
        blockplan,
        compactplan,
        excelheader,
        papers,
        patterns,
        icons,
        colors,
        palettes,
        palette,
        iconsheet,
        colorsheet,
    ):
        db_group = view_parser.add_argument_group("Database Options")
        db_group.add_argument(
            "--database",
            "-db",
            type=str,
            default="calendar.db",
            metavar="PATH",
            help="Path to SQLite database file (default: calendar.db)",
        )

    # SVG-producing views (text-mini is excluded — it produces plain text, not SVG)
    _svg_views = (weekly, mini, mini_icon, timeline, blockplan, compactplan)

    # Output options (SVG views: all options; text-mini: outputfile only)
    for view_parser in _svg_views:
        output_group = view_parser.add_argument_group("Output Options")
        output_group.add_argument(
            "--outputfile",
            "-of",
            type=str,
            default=default_output,
            metavar="PATH",
            help="Output filename (always written under output/)",
        )
        output_group.add_argument(
            "--theme",
            "-th",
            type=str,
            default=None,
            metavar="THEME",
            help="Theme name or path to .yaml theme file (e.g., 'corporate', 'dark')",
        )
        output_group.add_argument(
            "--papersize",
            "-ps",
            type=str,
            default="Widescreen",
            metavar="SIZE",
            help="Paper size (default: Widescreen).",
        )
        output_group.add_argument(
            "--orientation",
            "-o",
            type=str,
            default="landscape",
            choices=["portrait", "landscape"],
            help="Page orientation (default: landscape)",
        )
        output_group.add_argument(
            "--shrink",
            action="store_true",
            help=(
                "Shrink SVG width/height/viewBox to the bounding box of "
                "rendered content, removing blank page whitespace."
            ),
        )
    # text-mini: output file path only (no SVG layout args)
    _tm_output = text_mini.add_argument_group("Output Options")
    _tm_output.add_argument(
        "--outputfile",
        "-of",
        type=str,
        default=default_output,
        metavar="PATH",
        help="Output filename (always written under output/)",
    )

    for view_parser in _svg_views:
        # Layout options (SVG-specific: margin, header, footer, monthnames)
        layout_group = view_parser.add_argument_group("Layout Options")
        layout_group.add_argument(
            "--weekends",
            "-we",
            type=int,
            default=0,
            choices=[0, 1, 2, 3, 4],
            help=(
                "Weekend style: "
                "0=work week only, "
                "1=full week Sunday start, "
                "2=half weekends Sunday start, "
                "3=full week Monday start, "
                "4=half weekends Monday start"
            ),
        )
        layout_group.add_argument(
            "--margin",
            "-m",
            action="store_true",
            help="Add page margins",
        )
        layout_group.add_argument(
            "--header",
            "-ht",
            action="store_true",
            help="Include page header",
        )
        layout_group.add_argument(
            "--footer",
            "-ft",
            action="store_true",
            help="Include page footer",
        )
        layout_group.add_argument(
            "--monthnames",
            "-mn",
            action="store_true",
            help="Show month names on calendar",
        )
        # Header/Footer text
        text_group = view_parser.add_argument_group("Header/Footer Text")
        text_group.add_argument(
            "--headerleft", "-hl", type=str, default="", help="Left header text"
        )
        text_group.add_argument(
            "--headercenter", "-hc", type=str, default="", help="Center header text"
        )
        text_group.add_argument(
            "--headerright", "-hr", type=str, default="", help="Right header text"
        )
        text_group.add_argument(
            "--footerleft", "-fl", type=str, default="", help="Left footer text"
        )
        text_group.add_argument(
            "--footercenter", "-fc", type=str, default="", help="Center footer text"
        )
        text_group.add_argument(
            "--footerright", "-fr", type=str, default="", help="Right footer text"
        )

        # Watermark options
        watermark_group = view_parser.add_argument_group("Watermark Options")
        watermark_group.add_argument(
            "--watermark", "-wt", type=str, default="", help="Watermark text"
        )
        watermark_group.add_argument(
            "--watermark-rotation-angle",
            type=float,
            default=None,
            metavar="DEGREES",
            help="Rotate text watermark by degrees (clockwise coordinates)",
        )
        watermark_group.add_argument(
            "--imagemark", "-wi", type=str, default="", help="Watermark image file"
        )

        # Content filtering (SVG views include --shade and --overflow)
        content_group = view_parser.add_argument_group("Content Filtering")
        content_group.add_argument(
            "--empty",
            "-e",
            action="store_true",
            help="Create blank calendar (no events)",
        )
        content_group.add_argument(
            "--shade",
            "-sh",
            action="store_true",
            help="Shade current date",
        )
        content_group.add_argument(
            "--noevents",
            "-ne",
            action="store_true",
            help="Exclude single-day events",
        )
        content_group.add_argument(
            "--nodurations",
            "-nd",
            action="store_true",
            help="Exclude multi-day durations",
        )
        content_group.add_argument(
            "--ignorecomplete",
            "-ic",
            action="store_true",
            help="Exclude 100%% complete items",
        )
        content_group.add_argument(
            "--milestones",
            "-mo",
            action="store_true",
            help="Show only milestones",
        )
        content_group.add_argument(
            "--rollups",
            "-ro",
            action="store_true",
            help="Show only rollup entries",
        )
        content_group.add_argument(
            "--includenotes",
            "-notes",
            action="store_true",
            help="Show notes with event names",
        )
        content_group.add_argument(
            "--WBS",
            type=str,
            default="",
            help=(
                "WBS filter expression. Comma-separated tokens; '!' excludes. "
                "Segments are dot-separated. '*' matches a segment, '**' matches "
                "any remaining segments (implicit if omitted)."
            ),
        )
        content_group.add_argument(
            "--overflow",
            "-x",
            action="store_true",
            help="Create overflow page showing items",
        )
        content_group.add_argument(
            "--country",
            "-cc",
            type=str,
            default=None,
            metavar="CODE",
            help=(
                "ISO 3166-1 alpha-2 country code(s) for government holidays. "
                "Accepts a single code (e.g. US) or a comma-separated list "
                "(e.g. US,CA,GB) to include holidays from multiple countries. "
                "If omitted, US and CA holidays are loaded by default."
            ),
        )

    # text-mini: weekends + content filtering only (no SVG layout, header/footer, watermark, shade, overflow)
    _tm_layout = text_mini.add_argument_group("Layout Options")
    _tm_layout.add_argument(
        "--weekends",
        "-we",
        type=int,
        default=0,
        choices=[0, 1, 2, 3, 4],
        help=(
            "Weekend style: "
            "0=work week only, "
            "1=full week Sunday start, "
            "2=half weekends Sunday start, "
            "3=full week Monday start, "
            "4=half weekends Monday start"
        ),
    )
    _tm_content = text_mini.add_argument_group("Content Filtering")
    _tm_content.add_argument(
        "--empty",
        "-e",
        action="store_true",
        help="Create blank calendar (no events)",
    )
    _tm_content.add_argument(
        "--noevents",
        "-ne",
        action="store_true",
        help="Exclude single-day events",
    )
    _tm_content.add_argument(
        "--nodurations",
        "-nd",
        action="store_true",
        help="Exclude multi-day durations",
    )
    _tm_content.add_argument(
        "--ignorecomplete",
        "-ic",
        action="store_true",
        help="Exclude 100%% complete items",
    )
    _tm_content.add_argument(
        "--milestones",
        "-mo",
        action="store_true",
        help="Show only milestones",
    )
    _tm_content.add_argument(
        "--rollups",
        "-ro",
        action="store_true",
        help="Show only rollup entries",
    )
    _tm_content.add_argument(
        "--includenotes",
        "-notes",
        action="store_true",
        help="Show notes with event names",
    )
    _tm_content.add_argument(
        "--WBS",
        type=str,
        default="",
        help=(
            "WBS filter expression. Comma-separated tokens; '!' excludes. "
            "Segments are dot-separated. '*' matches a segment, '**' matches "
            "any remaining segments (implicit if omitted)."
        ),
    )
    _tm_content.add_argument(
        "--country",
        "-cc",
        type=str,
        default=None,
        metavar="CODE",
        help=(
            "ISO 3166-1 alpha-2 country code(s) for government holidays. "
            "Accepts a single code (e.g. US) or a comma-separated list "
            "(e.g. US,CA,GB) to include holidays from multiple countries. "
            "If omitted, US and CA holidays are loaded by default."
        ),
    )

    # Mini calendar options (SVG mini + mini-icon + text-mini)
    mini_group = mini.add_argument_group("Mini Calendar Options")
    mini_icon_group = mini_icon.add_argument_group("Mini Calendar Options")
    text_mini_group = text_mini.add_argument_group("Mini Calendar Options")
    for g in (mini_group, mini_icon_group, text_mini_group):
        g.add_argument(
            "--mini-columns",
            "-mc",
            type=int,
            default=None,
            metavar="N",
            help="Number of months per row in mini calendar (default: 3)",
        )
        g.add_argument(
            "--mini-rows",
            "-mr",
            type=int,
            default=None,
            metavar="N",
            help="Number of rows of months (0 = auto from date range)",
        )
        g.add_argument(
            "--mini-title-format",
            type=str,
            default=None,
            metavar="FMT",
            help="Format string for month title (default: MMM YY)",
        )
        g.add_argument(
            "--mini-no-adjacent",
            "-mna",
            action="store_true",
            help="Hide leading/trailing days from adjacent months",
        )
    mini_group.add_argument(
        "--mini-grid-lines",
        action="store_true",
        help="Draw grid lines between day cells",
    )
    mini_group.add_argument(
        "--mini-details",
        action="store_true",
        help="Generate a second SVG with mini calendar event details",
    )

    # Mini-icon-specific options
    mini_icon_group.add_argument(
        "--mini-grid-lines",
        action="store_true",
        help="Draw grid lines between day cells",
    )
    mini_icon_group.add_argument(
        "--mini-details",
        action="store_true",
        help="Generate a second SVG with mini calendar event details",
    )
    mini_icon_group.add_argument(
        "--mini-icon-set",
        "-mis",
        type=str,
        default=None,
        metavar="SET",
        choices=["squares", "darksquare", "darkcircles", "circles", "squircles", "darksquircles"],
        help=(
            "Icon set to use for day numbers "
            "(choices: squares, darksquare, darkcircles, circles, squircles, darksquircles; "
            "default: squares)"
        ),
    )

    # Week number options (weekly, mini, mini-icon, text-mini)
    for view_parser in (weekly, mini, mini_icon, text_mini):
        wn_group = view_parser.add_argument_group("Week Number Options")
        wn_group.add_argument(
            "--weeknumbers",
            "-wn",
            action="store_true",
            help="Show week numbers",
        )
        wn_group.add_argument(
            "--week-number-mode",
            "-wnm",
            type=str,
            default="iso",
            choices=["iso", "custom"],
            help="Week number mode (iso or custom)",
        )
        wn_group.add_argument(
            "--week1-start",
            type=str,
            default="",
            metavar="YYYYMMDD",
            help="Anchor date for week 1 (YYYYMMDD). Implies --weeknumbers and custom mode.",
        )

    # Timeline-specific options
    timeline_group = timeline.add_argument_group("Timeline Options")
    timeline_group.add_argument(
        "--today-line-length",
        "-tll",
        type=float,
        default=None,
        metavar="POINTS",
        help=(
            "Length of the today line in points (default: 0 = full available area). "
            "When direction is 'both', length is split equally above and below the axis."
        ),
    )
    timeline_group.add_argument(
        "--today-line-direction",
        "-tld",
        type=str,
        default=None,
        choices=["above", "below", "both"],
        help=(
            "Which side of the timeline axis the today line extends to: "
            "'above' (upward only), 'below' (downward only), or 'both' (default)."
        ),
    )
    timeline_group.add_argument(
        "--label-fill-opacity",
        "-lfo",
        type=float,
        default=None,
        metavar="0.0-1.0",
        help="Fill opacity for callout label boxes (default: 0.25).",
    )
    timeline_group.add_argument(
        "--duration-fill-opacity",
        "-dfo",
        type=float,
        default=None,
        metavar="0.0-1.0",
        help="Fill opacity for duration bar rectangles (default: 0.25).",
    )

    # Fiscal calendar options — all calendar views
    _fiscal_views = (weekly, mini, mini_icon, text_mini, timeline, blockplan, compactplan)
    for _vp in _fiscal_views:
        _fg = _vp.add_argument_group("Fiscal Calendar Options")
        _fg.add_argument(
            "--fiscal",
            type=str,
            default=None,
            choices=["nrf-454", "nrf-445", "nrf-544", "13-period"],
            metavar="TYPE",
            help=(
                "Enable fiscal calendar overlay (nrf-454, nrf-445, nrf-544, 13-period). "
                "weekly/mini: period labels and day-box colors. "
                "text-mini: period start markers. "
                "timeline: fiscal period/quarter bands (see --fiscal-show-periods/quarters). "
                "blockplan/compactplan: NRF-aware fiscal_quarter bands."
            ),
        )
        _fg.add_argument(
            "--fiscal-year-offset",
            type=int,
            default=None,
            metavar="N",
            help=(
                "Offset added to the fiscal period start year to produce the displayed fiscal year "
                "number. 0 = start year (e.g. FY starting Feb 2026 → FY2026), "
                "1 = start year + 1 (e.g. FY starting Oct 2025 → FY2026, US federal default), "
                "-1 = start year − 1. Default: auto (0 for NRF)."
            ),
        )

    # --fiscal-colors: day-box period fill (weekly and mini)
    for _vp in (weekly, mini, mini_icon):
        _vp._option_string_actions.get("--fiscal") and None  # guard: group already added above
        _fiscal_color_group = next(
            g for g in _vp._action_groups if g.title == "Fiscal Calendar Options"
        )
        _fiscal_color_group.add_argument(
            "--fiscal-colors",
            action="store_true",
            help="Use fiscal period colors instead of Gregorian month colors for day box backgrounds",
        )

    # --fiscal-show-periods / --fiscal-show-quarters: timeline band rows
    _timeline_fiscal_group = next(
        g for g in timeline._action_groups if g.title == "Fiscal Calendar Options"
    )
    _timeline_fiscal_group.add_argument(
        "--fiscal-show-periods",
        action="store_true",
        help="Show a fiscal period band row above the timeline axis (requires --fiscal)",
    )
    _timeline_fiscal_group.add_argument(
        "--fiscal-show-quarters",
        action="store_true",
        help="Show a fiscal quarter band row above the timeline axis (requires --fiscal)",
    )

    # Logging options
    for view_parser in (
        weekly,
        mini,
        mini_icon,
        text_mini,
        timeline,
        blockplan,
        compactplan,
        excelheader,
        themes,
        papers,
        patterns,
        icons,
        colors,
        palettes,
        palette,
        iconsheet,
        colorsheet,
        fontsheet,
        fonts,
        help_cmd,
    ):
        logging_group = view_parser.add_argument_group("Logging Options")
        logging_group.add_argument(
            "--verbose",
            "-v",
            action="count",
            default=0,
            help="Increase verbosity (-v, -vv, -vvv)",
        )
        logging_group.add_argument(
            "--quiet",
            "-q",
            action="store_true",
            help="Suppress all output except errors",
        )

    return parser


def _configure_logging(verbose: int, quiet: bool) -> None:
    """
    Set the root logging level and format for the entire run.

    Calling this once immediately after argument parsing ensures that every
    module-level logger (renderers, layout engine, db_access, …) inherits
    the correct level without each module needing its own configuration.

    Level mapping:
        --quiet          → ERROR   (only fatal messages)
        default (0 -v)   → WARNING
        -v  (verbose=1)  → INFO
        -vv (verbose=2)  → INFO    (extended format: LEVEL: module: message)
        -vvv(verbose≥3)  → DEBUG   (extended format)

    Called by:
        run() immediately after argparse.parse_args().

    Args:
        verbose: Verbosity count from --verbose / -v flags (0 = default).
        quiet:   True when --quiet is set; forces ERROR level regardless of verbose.
    """
    if quiet:
        level = logging.ERROR
    elif verbose >= 3:
        level = logging.DEBUG
    elif verbose >= 2:
        level = logging.INFO
    elif verbose >= 1:
        level = logging.INFO
    else:
        level = logging.WARNING

    logging.basicConfig(
        level=level,
        format="%(levelname)s: %(message)s"
        if verbose < 2
        else "%(levelname)s: %(name)s: %(message)s",
    )


def _apply_args_to_config(
    args: Namespace,
    config: CalendarConfig,
    paper_sizes: dict[str, tuple[float, float]],
) -> None:
    """
    Transfer parsed CLI argument values into the CalendarConfig dataclass.

    Separating this mapping from run() keeps the entry-point readable and
    makes it straightforward to unit-test config wiring in isolation.  Each
    section below handles a logical group of related settings:

    Sections handled
    ────────────────
    1. Database source       → config.events  (description string for SVG metadata)
    2. Weekend style         → config.weekend_style
    3. Month display         → config.include_month_name / include_month_number
    4. Week numbers          → config.include_week_numbers
    5. Layout toggles        → header, footer, margin, overflow, shrink flags
    6. Paper size/orientation→ case-insensitive lookup; sets config.pageX/pageY;
                               raises ConfigError on unknown size
    7. Display options       → events, durations, milestones, rollups, WBS,
                               complete-filtering, today-shading, country
    8. Mini calendar options → guarded with ``is not None`` so omitting a flag
                               never overwrites a theme-set default
    9. Timeline options      → today-line geometry, opacity overrides
    10. Fiscal calendar      → type string, per-period colour flag, year offset
    11. Week number mode     → ISO vs. custom-anchor

    Called by:
        run() for all calendar-visualizer subcommands, after the database and
        paper-size list have been loaded but before calc_calendar_range().

    Args:
        args:        Namespace from argparse.parse_args().
        config:      CalendarConfig instance to populate (mutated in-place).
        paper_sizes: Dict of ``{name: (width_pts, height_pts)}`` from the DB.

    Raises:
        ConfigError: If the requested paper size is not found in paper_sizes.
    """
    # Data source description
    config.events = f"(database: {args.database})"

    # Weekend style
    config.weekend_style = getattr(args, "weekends", config.weekend_style)

    # Month display
    if getattr(args, "monthnames", False):
        config.include_month_name = True
        config.include_month_number = False
    # Week numbers (weekly, mini, mini-icon, text-mini)
    if getattr(args, "weeknumbers", False):
        config.include_week_numbers = True
        config.mini_show_week_numbers = True
    if getattr(args, "week_number_mode", None):
        config.week_number_mode = args.week_number_mode
        config.mini_week_number_mode = args.week_number_mode
    if getattr(args, "week1_start", ""):
        config.week1_start = args.week1_start
        config.mini_week1_start = args.week1_start
        config.week_number_mode = "custom"
        config.mini_week_number_mode = "custom"
        config.include_week_numbers = True
        config.mini_show_week_numbers = True

    # Layout options
    config.include_header = getattr(args, "header", False)
    config.include_footer = getattr(args, "footer", False)
    config.include_margin = getattr(args, "margin", False)

    # Overflow page
    config.include_overflow = getattr(args, "overflow", False)

    # Shrink SVG to content bounding box.
    # compactplan always shrinks by default; other views require --shrink.
    shrink_default = getattr(args, "command", None) == "compactplan"
    config.shrink_to_content = getattr(args, "shrink", False) or shrink_default

    # Paper size and orientation
    paper_name = getattr(args, "papersize", config.papersize)
    if paper_name not in paper_sizes:
        # Try case-insensitive lookup for backward compatibility
        name_map = {k.lower(): k for k in paper_sizes}
        lower_name = paper_name.lower()
        if lower_name in name_map:
            paper_name = name_map[lower_name]
        else:
            available = ", ".join(sorted(paper_sizes.keys()))
            raise ConfigError(
                f"Unknown paper size: '{args.papersize}'. Available sizes: {available}"
            )

    dims = paper_sizes[paper_name]
    if getattr(args, "orientation", "portrait") == "portrait":
        config.pageX, config.pageY = dims
    else:
        config.pageY, config.pageX = dims
    config.papersize = paper_name
    config.orientation = getattr(args, "orientation", config.orientation)

    # Display options.
    # Kept as explicit one-to-one assignments so CLI/config wiring is easy to
    # audit during reviews; migrate to a mapping table if this list expands.
    config.shade_current_day = getattr(args, "shade", False)
    config.includeevents = not getattr(args, "noevents", False)
    config.includedurations = not getattr(args, "nodurations", False)
    config.ignorecomplete = getattr(args, "ignorecomplete", False)
    config.milestones = getattr(args, "milestones", False)
    config.rollups = getattr(args, "rollups", False)
    config.include_notes = getattr(args, "includenotes", False)
    config.WBS = getattr(args, "WBS", config.WBS)
    config.country = getattr(args, "country", None)

    # Mini calendar options — only override config defaults when explicitly set
    if getattr(args, "mini_columns", None) is not None:
        config.mini_columns = args.mini_columns
    if getattr(args, "mini_rows", None) is not None:
        config.mini_rows = args.mini_rows
    if getattr(args, "mini_title_format", None) is not None:
        config.mini_title_format = args.mini_title_format
    if getattr(args, "mini_no_adjacent", False):
        config.mini_show_adjacent = False
    if getattr(args, "mini_grid_lines", False):
        config.mini_grid_lines = True
    if getattr(args, "mini_details", False):
        config.include_mini_details = True
    if getattr(args, "mini_icon_set", None) is not None:
        config.mini_icon_set = args.mini_icon_set

    # Timeline today-line options
    if getattr(args, "today_line_length", None) is not None:
        config.timeline_today_line_length = args.today_line_length
    if getattr(args, "today_line_direction", None) is not None:
        config.timeline_today_line_direction = args.today_line_direction
    if getattr(args, "label_fill_opacity", None) is not None:
        config.timeline_label_fill_opacity = args.label_fill_opacity
    if getattr(args, "duration_fill_opacity", None) is not None:
        config.timeline_duration_bar_fill_opacity = args.duration_fill_opacity

    # Fiscal calendar
    if getattr(args, "fiscal", None):
        config.fiscal_calendar_type = args.fiscal
        config.fiscal_use_period_colors = getattr(args, "fiscal_colors", False)
    if getattr(args, "fiscal_year_offset", None) is not None:
        config.fiscal_year_offset = args.fiscal_year_offset
    if getattr(args, "fiscal_show_periods", False):
        config.timeline_show_fiscal_periods = True
    if getattr(args, "fiscal_show_quarters", False):
        config.timeline_show_fiscal_quarters = True



def _apply_text_options(args: Namespace, config: CalendarConfig) -> None:
    """
    Map CLI header/footer/watermark text arguments into CalendarConfig.

    Each non-empty text field is passed through replace_template_vars() so
    that tokens like ``[startdate]`` and ``[enddate]`` are expanded using the
    date boundaries that calc_calendar_range() has already written into config.
    This function must therefore be called *after* calc_calendar_range().

    Fields mapped (CLI arg → config attribute):
        --headerleft            → config.header_left_text
        --headercenter          → config.header_center_text
        --headerright           → config.header_right_text
        --footerleft            → config.footer_left_text
        --footercenter          → config.footer_center_text
        --footerright           → config.footer_right_text
        --watermark             → config.watermark
        --watermark-rotation-angle → config.watermark_rotation_angle
        --imagemark             → config.imagemark

    Called by:
        run() after calc_calendar_range() has populated adjustedstart/adjustedend.

    Calls:
        replace_template_vars() for every non-empty text field.

    Args:
        args:   Namespace from argparse.parse_args().
        config: CalendarConfig instance to populate (mutated in-place).
    """
    # Keep text-option mapping centralized to avoid drift between argument names
    # and CalendarConfig attribute names as options evolve.
    template_text_fields = (
        ("headerleft", "header_left_text"),
        ("headercenter", "header_center_text"),
        ("headerright", "header_right_text"),
        ("footerleft", "footer_left_text"),
        ("footercenter", "footer_center_text"),
        ("footerright", "footer_right_text"),
        ("watermark", "watermark"),
    )
    for arg_name, config_attr in template_text_fields:
        value = getattr(args, arg_name, "")
        if value:
            setattr(config, config_attr, replace_template_vars(config, value))

    if getattr(args, "watermark_rotation_angle", None) is not None:
        config.watermark_rotation_angle = float(args.watermark_rotation_angle)
    if getattr(args, "imagemark", ""):
        config.imagemark = replace_template_vars(config, args.imagemark)


def _reapply_post_theme_cli_overrides(args: Namespace, config: CalendarConfig) -> None:
    """
    Re-assert explicit CLI negation flags that the theme may have overwritten.

    The theme engine is applied *twice* in run():
      1. Before setfontsizes() — so base.size_rule can influence auto-scaling.
      2. After setfontsizes()  — so explicit theme font sizes take precedence.

    This double-apply means that CLI flags whose intent is to *disable* a
    theme-enabled feature can be silently undone on the second apply.  This
    function re-asserts those flags after the final theme.apply() call.

    Currently guarded flags:
        --mini-no-adjacent → forces config.mini_show_adjacent = False

    Called by:
        run() immediately after the second theme_engine.apply(config) call.

    Args:
        args:   Namespace from argparse.parse_args() (checked for explicit flags).
        config: CalendarConfig instance to correct (mutated in-place).
    """
    if getattr(args, "mini_no_adjacent", False):
        config.mini_show_adjacent = False


# =============================================================================
# Input Validation
# =============================================================================


def _validate_database(db_path: str) -> None:
    """
    Confirm that *db_path* refers to an existing regular file.

    Provides a clear, early error message rather than letting sqlite3 raise a
    cryptic OperationalError when the database is missing or mis-specified.

    Called by:
        _open_calendar_db() — which is the single factory for CalendarDB
        instances throughout the entire dispatch chain in run().

    Args:
        db_path: Filesystem path to the SQLite database file.

    Raises:
        DatabaseError: If the path does not exist or is not a regular file.
    """
    path = Path(db_path)
    if not path.exists():
        raise DatabaseError(f"Database file not found: {db_path}")
    if not path.is_file():
        raise DatabaseError(f"Database path is not a file: {db_path}")


def _open_calendar_db(db_path: str) -> CalendarDB:
    """
    Validate *db_path* and return an open CalendarDB instance.

    Acts as the single factory for all CalendarDB instances in run(),
    eliminating the repeated ``_validate_database() + CalendarDB()`` two-step
    that would otherwise appear in every database-using dispatch branch.

    Called by:
        run() for every subcommand that needs database access: papersizes,
        patterns, icons, iconsheet, colors, colorsheet, palettes, palette,
        excelheader, and all calendar-visualizer commands.

    Calls:
        _validate_database() → CalendarDB()

    Args:
        db_path: Filesystem path to the SQLite database file.

    Returns:
        An open CalendarDB instance ready for querying.

    Raises:
        DatabaseError: Propagated from _validate_database() if the file is
                       missing or not a regular file.
    """
    _validate_database(db_path)
    return CalendarDB(db_path)


# =============================================================================
# Subcommand Help
# =============================================================================


def _print_subcommand_help(subcommand: str, parser: argparse.ArgumentParser) -> None:
    """
    Print argparse ``--help`` for a subcommand plus supplementary value lists.

    argparse's static help strings cannot enumerate values that come from
    the database or theme registry at runtime (themes, paper sizes, patterns,
    icons, …).  This function appends a "VALID CONFIGURABLE VALUES" section
    with that dynamic information after the standard help block.

    Sections printed (conditionally by subcommand)
    ───────────────────────────────────────────────
    All calendar views (weekly/mini/mini-icon/text-mini/timeline/blockplan):
        Weekend styles, paper sizes, orientation, themes, icons, template vars

    weekly only:
        SVG day-box patterns, week number modes

    all calendar views:
        fiscal calendar types and per-visualizer fiscal features

    mini / mini-icon / text-mini:
        Mini calendar column/row option guidance

    timeline only:
        Today-line direction values

    All subcommands:
        Available fonts, available colors (with guidance to list commands)

    Called by:
        run() when args.command == "help".

    Calls:
        ThemeEngine.list_available_themes(), WEEKEND_STYLES from config.config.

    Args:
        subcommand: The subcommand name whose help should be printed.
        parser:     The top-level ArgumentParser (used to locate the sub-parser).
    """
    # Find the subparser for this subcommand
    subparsers_action = next(
        (a for a in parser._actions if isinstance(a, argparse._SubParsersAction)),
        None,
    )
    if subparsers_action and subcommand in subparsers_action.choices:
        subparsers_action.choices[subcommand].print_help()
    else:
        print(f"No help available for subcommand: {subcommand}")
        return

    # Sections that apply to specific subcommands
    calendar_subcommands = {"weekly", "mini", "mini-icon", "text-mini", "timeline", "blockplan", "compactplan"}
    # SVG-producing views only (text-mini produces plain text, not SVG)
    svg_calendar_subcommands = {"weekly", "mini", "mini-icon", "timeline", "blockplan", "compactplan"}
    weekly_only = {"weekly"}
    mini_subcommands = {"mini", "mini-icon", "text-mini"}
    timeline_only = {"timeline"}
    blockplan_only = {"blockplan"}
    week_number_views = {"weekly", "mini", "mini-icon", "text-mini"}

    print("\n" + "=" * 60)
    print("VALID CONFIGURABLE VALUES")
    print("=" * 60)

    # --- Weekend styles (all calendar views — text-mini uses weekends for column layout) ---
    if subcommand in calendar_subcommands:
        print("\nWeekend styles (--weekends):")
        from config.config import WEEKEND_STYLES

        for num, info in sorted(WEEKEND_STYLES.items()):
            day_list = ", ".join(d[:3] for d in info["day_order"])
            print(f"  {num}  {info['name']:<25}  ({day_list})")

    # --- Paper sizes (SVG views only) ---
    if subcommand in svg_calendar_subcommands:
        print("\nPaper sizes (--papersize):")
        print("  (Use 'ecalendar.py papersizes' for a full list with dimensions.)")
        print("  Common sizes: Letter, Tabloid, A4, A3, Legal, Executive")

    # --- Orientation (SVG views only) ---
    if subcommand in svg_calendar_subcommands:
        print("\nOrientation (--orientation):")
        print("  portrait")
        print("  landscape")

    # --- Themes (SVG views only) ---
    if subcommand in svg_calendar_subcommands:
        print("\nThemes (--theme):")
        try:
            from config.theme_engine import ThemeEngine

            available = ThemeEngine.list_available_themes()
            for t in available:
                print(f"  {t}")
            print("  <path/to/custom.yaml>  (custom theme file)")
        except Exception:
            print("  (Unable to load theme list)")

    # --- SVG patterns (weekly only — used in day_box.hash_rules / hash_pattern) ---
    if subcommand in weekly_only:
        print("\nSVG day-box patterns (day_box.hash_pattern / hash_rules[].pattern):")
        print("  (Use 'ecalendar.py patterns' for a full list from the database.)")
        print(
            "  Example names: diagonal-stripes, polka-dots, brick-wall, circuit-board"
        )

    # --- Fiscal calendar types (all views) ---
    if subcommand in calendar_subcommands:
        print("\nFiscal calendar types (--fiscal):")
        print("  nrf-454    NRF 4-5-4 retail calendar")
        print("  nrf-445    NRF 4-4-5 retail calendar")
        print("  nrf-544    NRF 5-4-4 retail calendar")
        print("  13-period  13 equal 4-week periods")
        print("\nFiscal features by visualizer:")
        print("  weekly      Period labels on day boxes; --fiscal-colors for period-shaded backgrounds")
        print("  mini        Period labels at bottom of day cells; --fiscal-colors for backgrounds")
        print("  text-mini   Period short name (e.g. P1) as day symbol on period-start days")
        print("  timeline    --fiscal-show-periods: period band row above axis")
        print("              --fiscal-show-quarters: quarter band row above axis")
        print("  blockplan   fiscal_quarter bands use NRF-aware boundaries when --fiscal is set")
        print("  compactplan fiscal_quarter bands use NRF-aware boundaries; fiscal_period band unit available")

    # --- Week number modes (weekly, mini, mini-icon, text-mini) ---
    if subcommand in week_number_views:
        print("\nWeek number modes (--week-number-mode):")
        print("  iso     ISO 8601 week numbers (default)")
        print("  custom  Custom week 1 anchor date (requires --week1-start YYYYMMDD)")

    # --- Mini columns/rows (mini views) ---
    if subcommand in mini_subcommands:
        print("\nMini calendar options:")
        print("  --mini-columns N   Months per row (default: 3, minimum: 1)")
        print("  --mini-rows N      Rows of months (0 = auto from date range)")

    # --- Timeline today-line direction (timeline only) ---
    if subcommand in timeline_only:
        print("\nToday-line direction (--today-line-direction):")
        print("  above  Extend today line above the axis only")
        print("  below  Extend today line below the axis only")
        print("  both   Extend today line above and below the axis (default)")

    # --- Icons (SVG views only — icons are SVG elements) ---
    if subcommand in svg_calendar_subcommands:
        print("\nAvailable icons (for event icon fields):")
        print("  (Use 'ecalendar.py icons --database <PATH>' for a full list.)")
        print("  Example names: rocket, calendar, star")

    # --- Template variables (SVG header/footer text — not applicable to text-mini) ---
    if subcommand in svg_calendar_subcommands:
        print("\nTemplate variables (for --headerleft, --headercenter, etc.):")
        print("  [now]        Current date and time")
        print("  [date]       Current date")
        print("  [startdate]  First date on the calendar")
        print("  [enddate]    Last date on the calendar")
        print("  [events]     Data source description")

    # --- Fonts and colors guidance (SVG views only — not applicable to plain-text output) ---
    if subcommand in svg_calendar_subcommands:
        print("\nAvailable fonts (for theme/config font fields):")
        print("  (Use 'ecalendar.py fonts' for a full list.)")
        print("  Example names: Roboto-Regular, NotoSans-Condensed, JuliaMono-Regular")

        print("\nAvailable colors (for theme/config color fields):")
        print("  (Use 'ecalendar.py colors' for a full list.)")
        print("  Example names: DarkSlateGrey, Tomato, LightSteelBlue")


# =============================================================================
# Palette Resolution
# =============================================================================


def _resolve_single_palette_ref(value: str, db: "CalendarDB") -> str:
    """
    Resolve a ``"palette:NAME:INDEX"`` colour reference to a concrete hex value.

    Theme YAML files can reference database palettes for individual colour
    fields (e.g., ``accent_color: "palette:Blues:3"``) without hard-coding
    hex values.  This function performs that resolution at render time.

    INDEX formats
    ─────────────
    integer  — zero-based; wraps modulo palette length (cycling out-of-bounds).
    float    — proportional position in [0.0, 1.0]; 0.0 = first, 1.0 = last.

    On any error (palette not found, invalid index) the original *value*
    string is returned unchanged and a warning is logged so the render can
    still proceed with a visible but unresolved colour token.

    Called by:
        _resolve_palette_overrides() — iterates all string fields in config
        and calls this function for any that begin with ``"palette:"``.

    Args:
        value: A ``"palette:NAME:INDEX"`` string to resolve.
        db:    Open CalendarDB for palette lookups.

    Returns:
        Resolved hex colour string, or *value* unchanged on failure.
    """
    parts = value.split(":", 2)
    if len(parts) != 3:
        return value
    _, name, idx_str = parts
    colors = db.get_palette(name)
    if not colors:
        logger.warning(f"Palette not found: {name!r}")
        return value
    try:
        if "." in idx_str:
            pos = max(0.0, min(1.0, float(idx_str)))
            idx = int(pos * (len(colors) - 1))
        else:
            idx = int(idx_str) % len(colors)
    except ValueError:
        logger.warning(f"Invalid palette index: {idx_str!r}")
        return value
    return colors[idx]


def _resolve_palette_overrides(config: "CalendarConfig", db: "CalendarDB") -> None:
    """
    Bulk-resolve all palette name references in CalendarConfig to hex colours.

    Decouples palette name resolution from theme loading: the theme engine
    writes sentinel palette-name strings into config, and this function
    fetches the actual colours from the database at render time so themes
    remain database-independent.

    This function must be called *after* the theme has been fully applied
    (both passes in run()) so that all sentinel fields have been populated.

    Phase 1 — Named bulk palettes
    ──────────────────────────────
    Five sentinel fields are checked and expanded into colour dicts/lists:

      Sentinel field                  → Target field              Size
      config.theme_month_palette      → config.theme_monthcolors  12 (one/month)
      config.theme_fiscal_palette     → config.theme_fiscalperiodcolors 13 (one/period)
      config.theme_group_palette      → config.group_colors       full palette
      config.theme_timeline_palette   → config.timeline_top/bottom_colors full palette
      config.theme_blockplan_palette_name → config.blockplan_palette full palette

    Phase 2 — Inline ``palette:NAME:INDEX`` references
    ────────────────────────────────────────────────────
    Every string field in config that starts with ``"palette:"`` is passed to
    _resolve_single_palette_ref() and replaced with the resolved hex colour.

    Called by:
        run() for both the excelheader path and all calendar-visualizer paths,
        after theme application is complete.

    Calls:
        db.sample_palette_n(), db.get_palette(),
        _resolve_single_palette_ref(), dataclasses.fields().
    """
    import dataclasses

    if config.theme_month_palette:
        colors = db.sample_palette_n(config.theme_month_palette, 12)
        if colors:
            config.theme_monthcolors = {f"{i + 1:02d}": c for i, c in enumerate(colors)}
        else:
            logger.warning(f"Palette not found: {config.theme_month_palette!r}")

    if config.theme_fiscal_palette:
        colors = db.sample_palette_n(config.theme_fiscal_palette, 13)
        if colors:
            config.theme_fiscalperiodcolors = {
                f"{i + 1:02d}": c for i, c in enumerate(colors)
            }
        else:
            logger.warning(f"Palette not found: {config.theme_fiscal_palette!r}")

    if config.theme_group_palette:
        colors = db.get_palette(config.theme_group_palette)
        if colors:
            config.group_colors = colors
        else:
            logger.warning(f"Palette not found: {config.theme_group_palette!r}")

    if config.theme_timeline_palette:
        colors = db.get_palette(config.theme_timeline_palette)
        if colors:
            config.timeline_top_colors = colors
            config.timeline_bottom_colors = colors
        else:
            logger.warning(f"Palette not found: {config.theme_timeline_palette!r}")

    if config.theme_blockplan_palette_name:
        colors = db.get_palette(config.theme_blockplan_palette_name)
        if colors:
            config.blockplan_palette = colors
        else:
            logger.warning(
                f"Palette not found: {config.theme_blockplan_palette_name!r}"
            )

    if config.theme_compactplan_palette_name:
        colors = db.get_palette(config.theme_compactplan_palette_name)
        if colors:
            config.compactplan_palette = colors
        else:
            logger.warning(
                f"Palette not found: {config.theme_compactplan_palette_name!r}"
            )

    # Resolve 'palette:NAME:INDEX' references in all string config fields.
    for f in dataclasses.fields(config):
        val = getattr(config, f.name, None)
        if isinstance(val, str) and val.startswith("palette:"):
            setattr(config, f.name, _resolve_single_palette_ref(val, db))


# =============================================================================
# Palette SVG Generator
# =============================================================================


def _generate_palette_svg(name: str, colors: list[str], output_path: Path) -> None:
    """
    Write a standalone SVG file showing a colour palette as a grid of swatches.

    Each swatch displays the colour as a filled box with its hex value as a
    label below.  Up to 10 columns; additional rows are added for larger
    palettes.  The title bar shows the palette name and total colour count.

    Provides a quick visual reference so users can choose palettes for their
    themes without needing to render a full calendar.

    Called by:
        run() when args.command == "palette".

    Args:
        name:        Palette name shown in the SVG title.
        colors:      Ordered list of hex colour strings (e.g. ``["#4472C4", …]``).
        output_path: Destination path for the generated SVG file.
    """
    import math

    MARGIN = 40
    TITLE_H = 55

    n = len(colors)

    lines: list[str] = []

    BOX_W = 80
    BOX_H = 80
    LABEL_H = 26
    GAP_X = 10
    GAP_Y = 14
    MAX_COLS = 10
    CELL_W = BOX_W + GAP_X
    CELL_H = BOX_H + LABEL_H + GAP_Y

    ncols = min(n, MAX_COLS)
    nrows = math.ceil(n / ncols)
    svg_w = MARGIN * 2 + ncols * CELL_W - GAP_X
    svg_h = MARGIN + TITLE_H + nrows * CELL_H - GAP_Y + MARGIN

    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{svg_w}" height="{svg_h}" viewBox="0 0 {svg_w} {svg_h}">',
        f'  <rect width="{svg_w}" height="{svg_h}" fill="white"/>',
        f'  <text x="{MARGIN}" y="{MARGIN + 36}" font-family="Helvetica, Arial, sans-serif"'
        f' font-size="26" font-weight="bold" font-style="italic" fill="#222">'
        f'{name}  <tspan font-size="18" font-weight="normal" font-style="normal" fill="#666">({n} colors)</tspan></text>',
    ]

    for i, color in enumerate(colors):
        row = i // ncols
        col = i % ncols
        x = MARGIN + col * CELL_W
        y = MARGIN + TITLE_H + row * CELL_H

        hx = color.upper() if color.startswith("#") else f"#{color.upper()}"
        lines.append(
            f'  <rect x="{x}" y="{y}" width="{BOX_W}" height="{BOX_H}"'
            f' fill="{color}" stroke="#bbbbbb" stroke-width="0.5"/>'
        )
        lines.append(
            f'  <text x="{x + BOX_W // 2}" y="{y + BOX_H + 18}"'
            f' font-family="Helvetica, Arial, sans-serif" font-size="11"'
            f' fill="#555" text-anchor="middle">{hx}</text>'
        )

    lines.append("</svg>")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines), encoding="utf-8")


def _generate_colorsheet_svg(
    colors: list[dict], output_path: "Path", title: str = "Colors"
) -> None:
    """
    Write an SVG grid of named-colour swatches from the database ``colors`` table.

    Complements the ``colors`` listing command with a visual browseable sheet.
    The caller is responsible for ordering ``colors`` before passing them in;
    run() sorts by HSV hue via the ``_hsv_sort_key`` nested function so the
    sheet groups colours by hue rather than alphabetically.

    Each swatch shows:
    - Filled colour box (up to 8 columns; rows added as needed)
    - Hex value centred inside the box (white text on dark backgrounds,
      dark text on light backgrounds — determined by luminance threshold 128)
    - EN colour name below the box

    Called by:
        run() when args.command == "colorsheet", after HSV sorting.

    Args:
        colors:      List of colour dicts with keys: EN, red, green, blue, hex.
        output_path: Destination path for the generated SVG file.
        title:       SVG title string (includes filter text when --filter is set).
    """
    import math

    MARGIN = 40
    TITLE_H = 55
    BOX_W = 110
    BOX_H = 60
    LABEL_H = 30
    GAP_X = 12
    GAP_Y = 10
    MAX_COLS = 8
    CELL_W = BOX_W + GAP_X
    CELL_H = BOX_H + LABEL_H + GAP_Y

    n = len(colors)
    ncols = min(n, MAX_COLS)
    nrows = math.ceil(n / ncols)
    svg_w = MARGIN * 2 + ncols * CELL_W - GAP_X
    svg_h = MARGIN + TITLE_H + nrows * CELL_H - GAP_Y + MARGIN

    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{svg_w}" height="{svg_h}" viewBox="0 0 {svg_w} {svg_h}">',
        f'  <rect width="{svg_w}" height="{svg_h}" fill="white"/>',
        f'  <text x="{MARGIN}" y="{MARGIN + 36}" font-family="Helvetica, Arial, sans-serif"'
        f' font-size="26" font-weight="bold" font-style="italic" fill="#222">'
        f'{title}  <tspan font-size="18" font-weight="normal" font-style="normal" fill="#666">({n} colors)</tspan></text>',
    ]

    for i, row in enumerate(colors):
        r_idx = i // ncols
        col = i % ncols
        x = MARGIN + col * CELL_W
        y = MARGIN + TITLE_H + r_idx * CELL_H

        name = str(row.get("EN") or "").strip()
        red = int(row.get("red") or 0)
        green = int(row.get("green") or 0)
        blue = int(row.get("blue") or 0)
        hex_color = f"#{red:02x}{green:02x}{blue:02x}"

        # Determine label color: white text on dark backgrounds
        luminance = 0.2126 * red + 0.7152 * green + 0.0722 * blue
        text_on_swatch = "white" if luminance < 128 else "#222"

        lines.append(
            f'  <rect x="{x}" y="{y}" width="{BOX_W}" height="{BOX_H}"'
            f' fill="{hex_color}" stroke="#bbbbbb" stroke-width="0.5"/>'
        )
        # Hex label centered inside the swatch
        lines.append(
            f'  <text x="{x + BOX_W // 2}" y="{y + BOX_H // 2 + 5}"'
            f' font-family="Helvetica, Arial, sans-serif" font-size="11"'
            f' fill="{text_on_swatch}" text-anchor="middle">{hex_color.upper()}</text>'
        )
        # Color name below the swatch
        lines.append(
            f'  <text x="{x + BOX_W // 2}" y="{y + BOX_H + 18}"'
            f' font-family="Helvetica, Arial, sans-serif" font-size="11"'
            f' fill="#555" text-anchor="middle">{name}</text>'
        )

    lines.append("</svg>")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines), encoding="utf-8")


def _render_font_fullset(
    font_path: str,
    x_start: float,
    content_width: float,
    font_size: float,
    color: str,
) -> tuple[list[str], float]:
    """
    Render every mapped codepoint in a font as SVG ``<path>`` elements.

    Glyphs are emitted in codepoint order, placed horizontally from *x_start*
    and wrapped to a new line when the next glyph would exceed *x_start +
    content_width*.  Paths use a local coordinate space starting at (x_start, 0);
    callers must translate via ``<g transform="translate(0,{y_offset})">``.

    Extracted as a separate function so that its rendered height can be measured
    in a first pass before the enclosing SVG document dimensions are finalised
    (the two-pass approach used by _generate_fontsheet_svg with fullset=True).

    Called by:
        _generate_fontsheet_svg() when fullset=True.

    Calls:
        get_font_codepoints(), get_glyph(), get_font_metrics()
        from renderers.glyph_cache.

    Args:
        font_path:     Absolute path to the TTF/OTF font file.
        x_start:       Left margin x-coordinate in local space.
        content_width: Maximum line width before wrapping.
        font_size:     Render size in points.
        color:         SVG fill colour for all paths (e.g. ``"#222222"``).

    Returns:
        A tuple of (path_element_strings, total_rendered_height).
        Returns ([], 0.0) if the font has no mapped codepoints.
    """
    from renderers.glyph_cache import get_font_codepoints, get_glyph, get_font_metrics

    font_size_int = int(round(font_size))
    upm, _, _ = get_font_metrics(font_path)
    scale = font_size / upm
    row_h = font_size + 5

    codepoints = get_font_codepoints(font_path)
    if not codepoints:
        return [], 0.0

    x = x_start
    y = 0.0
    paths: list[str] = []

    for cp in codepoints:
        glyph = get_glyph(font_path, cp, font_size_int)
        advance = glyph.advance_width if glyph.advance_width > 0 else font_size * 0.5

        # Wrap before placing if this glyph would exceed the right margin
        if x + advance > x_start + content_width and x > x_start:
            x = x_start
            y += row_h

        if glyph.path_d:
            baseline = y + font_size
            paths.append(
                f'<path d="{glyph.path_d}" fill="{color}"'
                f' transform="translate({x:.2f},{baseline:.2f})'
                f' scale({scale:.6f},{-scale:.6f})"/>'
            )
        x += advance

    total_height = y + row_h
    return paths, total_height


def _generate_fontsheet_svg(
    font_registry: dict,
    output_path: "Path",
    color: str = "#222222",
    title: str = "Fonts",
    fullset: bool = False,
) -> None:
    """
    Write an SVG sample sheet for every font in the registry.

    Provides visual font browsing within the ecalendar ecosystem.  This is
    important because fonts are rendered as glyph-path outlines — there is no
    browser or OS font substitution to fall back on, so choosing the right
    registered font name requires seeing how each font actually looks.

    Two rendering modes
    ───────────────────
    fullset=False (default)
        Two-column grid, uniform entry height.  Each font shows three fixed
        sample rows rendered as ``<path>`` glyph outlines via text_to_svg_group():
          - abcdefghijklmnopqrstuvwxyz
          - ABCDEFGHIJKLMNOPQRSTUVWXYZ
          - 1234567890!@#$%^&*()[]{}<>/?\\|`~

    fullset=True  (--fullset flag)
        Single column, variable entry height.  Every mapped codepoint is shown
        in codepoint order, wrapping at the right margin.  Uses a two-pass
        strategy: pass 1 calls _render_font_fullset() to measure each entry's
        height; pass 2 positions and emits them once the total SVG height is known.

    Called by:
        run() when args.command == "fontsheet".

    Calls:
        text_to_svg_group()      (default mode, from renderers.glyph_cache)
        _render_font_fullset()   (fullset mode)

    Args:
        font_registry: Dict of ``{font_name: font_path}`` to render.
        output_path:   Destination path for the generated SVG.
        color:         Glyph fill colour (default ``"#222222"``).
        title:         SVG title string.
        fullset:       When True, renders every mapped codepoint per font.
    """
    from renderers.glyph_cache import text_to_svg_group

    SAMPLE_ROWS = [
        "abcdefghijklmnopqrstuvwxyz",
        "ABCDEFGHIJKLMNOPQRSTUVWXYZ",
        "1234567890!@#$%^&*()[]{}<>/?\\|`~",
    ]

    MARGIN = 40
    TITLE_H = 60
    PAGE_W = 1024
    CONTENT_W = PAGE_W - 2 * MARGIN
    SAMPLE_SIZE = 16
    LABEL_H = 20
    ROW_H = SAMPLE_SIZE + 5
    ENTRY_PAD = 16

    fonts_sorted = sorted(font_registry.items(), key=lambda x: x[0].lower())
    n = len(fonts_sorted)

    # ------------------------------------------------------------------ #
    # fullset: pre-render each font's glyphs to know the entry height     #
    # ------------------------------------------------------------------ #
    if fullset:
        # Pass 1 — render and measure
        pre: list[tuple[str, str, list[str], float]] = []  # (name, path, elems, content_h)
        for font_name, font_path in fonts_sorted:
            try:
                path_elems, content_h = _render_font_fullset(
                    font_path, MARGIN, CONTENT_W, SAMPLE_SIZE, color
                )
            except Exception:
                path_elems, content_h = [], 0.0
            pre.append((font_name, font_path, path_elems, content_h))

        # Pass 2 — compute total SVG height
        svg_h = MARGIN + TITLE_H
        for _, _, _, content_h in pre:
            svg_h += LABEL_H + max(content_h, ROW_H) + ENTRY_PAD
        svg_h += MARGIN

        lines = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{PAGE_W}" height="{svg_h}"'
            f' viewBox="0 0 {PAGE_W} {svg_h}">',
            f'  <rect width="{PAGE_W}" height="{svg_h}" fill="white"/>',
            f'  <text x="{MARGIN}" y="{MARGIN + 40}"'
            f' font-family="Helvetica, Arial, sans-serif"'
            f' font-size="26" font-weight="bold" font-style="italic" fill="#222">'
            f'{title}  <tspan font-size="18" font-weight="normal" font-style="normal"'
            f' fill="#666">({n} fonts, full glyph set)</tspan></text>',
        ]

        y = MARGIN + TITLE_H
        for font_name, font_path, path_elems, content_h in pre:
            entry_content_h = max(content_h, ROW_H)
            lines.append(
                f'  <line x1="{MARGIN}" y1="{y}" x2="{PAGE_W - MARGIN}" y2="{y}"'
                f' stroke="#ddd" stroke-width="1"/>'
            )
            lines.append(
                f'  <text x="{MARGIN}" y="{y + LABEL_H - 4}"'
                f' font-family="Helvetica, Arial, sans-serif" font-size="11"'
                f' font-weight="bold" fill="#888">{font_name}</text>'
            )
            y_content = y + LABEL_H
            if path_elems:
                lines.append(f'  <g transform="translate(0,{y_content})">')
                lines.extend(f"    {p}" for p in path_elems)
                lines.append("  </g>")
            else:
                baseline = y_content + SAMPLE_SIZE
                lines.append(
                    f'  <text x="{MARGIN}" y="{baseline}"'
                    f' font-family="Helvetica, Arial, sans-serif" font-size="10"'
                    f' fill="#ccc" font-style="italic">(no glyphs)</text>'
                )
            y += LABEL_H + entry_content_h + ENTRY_PAD

    # ------------------------------------------------------------------ #
    # default: fixed three sample rows, uniform entry height, 2 columns  #
    # ------------------------------------------------------------------ #
    else:
        COLS = 2
        COL_GAP = 32
        COL_W = (CONTENT_W - (COLS - 1) * COL_GAP) // COLS
        ENTRY_H = LABEL_H + 3 * ROW_H + ENTRY_PAD
        rows = (n + COLS - 1) // COLS
        svg_h = MARGIN + TITLE_H + rows * ENTRY_H + MARGIN

        lines = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{PAGE_W}" height="{svg_h}"'
            f' viewBox="0 0 {PAGE_W} {svg_h}">',
            f'  <rect width="{PAGE_W}" height="{svg_h}" fill="white"/>',
            f'  <text x="{MARGIN}" y="{MARGIN + 40}"'
            f' font-family="Helvetica, Arial, sans-serif"'
            f' font-size="26" font-weight="bold" font-style="italic" fill="#222">'
            f'{title}  <tspan font-size="18" font-weight="normal" font-style="normal"'
            f' fill="#666">({n} fonts)</tspan></text>',
        ]

        for idx, (font_name, font_path) in enumerate(fonts_sorted):
            col = idx % COLS
            row = idx // COLS
            x_col = MARGIN + col * (COL_W + COL_GAP)
            y = MARGIN + TITLE_H + row * ENTRY_H
            x_right = x_col + COL_W
            lines.append(
                f'  <line x1="{x_col}" y1="{y}" x2="{x_right}" y2="{y}"'
                f' stroke="#ddd" stroke-width="1"/>'
            )
            lines.append(
                f'  <text x="{x_col}" y="{y + LABEL_H - 4}"'
                f' font-family="Helvetica, Arial, sans-serif" font-size="11"'
                f' font-weight="bold" fill="#888">{font_name}</text>'
            )
            y_row = y + LABEL_H
            for sample in SAMPLE_ROWS:
                baseline = y_row + SAMPLE_SIZE
                try:
                    g = text_to_svg_group(
                        sample, font_path, SAMPLE_SIZE, x_col, baseline, fill=color
                    )
                    if g:
                        lines.append(f"  {g}")
                    else:
                        lines.append(
                            f'  <text x="{x_col}" y="{baseline}"'
                            f' font-family="Helvetica, Arial, sans-serif" font-size="10"'
                            f' fill="#ccc" font-style="italic">(no glyphs)</text>'
                        )
                except Exception:
                    lines.append(
                        f'  <text x="{x_col}" y="{baseline}"'
                        f' font-family="Helvetica, Arial, sans-serif" font-size="10"'
                        f' fill="#bbb" font-style="italic">(not renderable)</text>'
                    )
                y_row += ROW_H

    lines.append("</svg>")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines), encoding="utf-8")


def _generate_iconsheet_svg(
    icons: list[dict],
    output_path: "Path",
    color: str = "#333333",
    title: str = "Icons",
) -> None:
    """
    Write an SVG grid of icon previews from the database ``icon`` table.

    Lets users identify icon names for use in event ``Icon`` fields and
    theme hash-rules without needing to query the database directly.

    Each cell contains the icon rendered at 24×24 with its name label below.
    Labels on odd columns are offset 12 px lower than even-column labels to
    reduce visual crowding on narrow icons.

    Colour handling — two icon styles
    ───────────────────────────────────
    Lucide-style (contains ``currentColor``):
        ``currentColor`` is replaced with *color*; the root ``fill`` attribute
        from the original ``<svg>`` element is preserved so stroked paths show.

    Klee-style (fill-based, no ``currentColor``):
        ``fill="{color}"`` is added to the container ``<svg>`` so fill-based
        paths inherit the chosen colour.

    The icon's original ``viewBox`` is preserved so internal paths render in
    their own coordinate space; ``width``/``height`` are always ``ICON_SIZE``
    so the SVG scales the content to fit the cell.

    Called by:
        run() when args.command == "iconsheet".

    Args:
        icons:       List of icon dicts with keys: name, svg (raw SVG markup).
        output_path: Destination path for the generated SVG.
        color:       Stroke/fill colour applied to icons (default ``"#333333"``).
        title:       SVG title string.
    """
    import math
    import re

    MARGIN = 40
    TITLE_H = 55
    ICON_SIZE = 24  # cell size in the sheet's coordinate space
    LABEL_H = 22
    GAP_X = 22
    GAP_Y = 19
    MAX_COLS = 12
    CELL_W = ICON_SIZE + GAP_X
    CELL_H = ICON_SIZE + LABEL_H + GAP_Y

    n = len(icons)
    ncols = min(n, MAX_COLS)
    nrows = math.ceil(n / ncols)
    svg_w = MARGIN * 2 + ncols * CELL_W - GAP_X
    svg_h = MARGIN + TITLE_H + nrows * CELL_H - GAP_Y + MARGIN

    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{svg_w}" height="{svg_h}"'
        f' viewBox="0 0 {svg_w} {svg_h}">',
        f'  <rect width="{svg_w}" height="{svg_h}" fill="white"/>',
        f'  <text x="{MARGIN}" y="{MARGIN + 36}"'
        f' font-family="Helvetica, Arial, sans-serif"'
        f' font-size="26" font-weight="bold" font-style="italic" fill="#222">'
        f'{title}  <tspan font-size="18" font-weight="normal" font-style="normal"'
        f' fill="#666">({n} icons)</tspan></text>',
    ]

    _svg_open_re = re.compile(r"<svg\b[^>]*>", re.IGNORECASE | re.DOTALL)
    _viewbox_re = re.compile(
        r'viewBox=["\'][\d.]+\s+[\d.]+\s+([\d.]+)\s+([\d.]+)["\']', re.IGNORECASE
    )
    _preamble_re = re.compile(
        r"^(?:<\?xml\b[^?]*\?>|<!DOCTYPE\b[^>]*>|\s)*", re.IGNORECASE | re.DOTALL
    )

    for i, row in enumerate(icons):
        r = i // ncols
        col = i % ncols
        x = MARGIN + col * CELL_W
        y = MARGIN + TITLE_H + r * CELL_H

        name = str(row.get("name") or "").strip()
        svg_raw = _preamble_re.sub("", str(row.get("svg") or "").strip())

        # Replace currentColor with chosen stroke color (Lucide-style icons).
        uses_current_color = "currentColor" in svg_raw
        svg_colored = svg_raw.replace("currentColor", color)

        # Extract the icon's original viewBox so its internal paths render in
        # their own coordinate space.  width/height are always set to ICON_SIZE
        # so the SVG scales the content to fit the cell regardless of whether
        # the icon uses a 24- or 48-unit (or any other) coordinate system.
        vb_match = _viewbox_re.search(svg_raw)
        vb = f"0 0 {vb_match.group(1)} {vb_match.group(2)}" if vb_match else "0 0 24 24"

        # Determine how to apply color on the container SVG:
        #   - Lucide-style: uses currentColor → already replaced above; preserve
        #     the original root fill (typically "none") so stroked paths show.
        #   - Klee-style: no currentColor, fill-based paths with no explicit fill
        #     → set fill on the container so paths inherit the chosen color.
        if uses_current_color:
            orig_fill_match = re.search(
                r"<svg\b[^>]*\bfill=[\"']([^\"']*)[\"']",
                svg_raw,
                re.IGNORECASE | re.DOTALL,
            )
            color_attr = (
                f' fill="{orig_fill_match.group(1)}"' if orig_fill_match else ""
            )
        else:
            color_attr = f' fill="{color}"'

        embedded = _svg_open_re.sub(
            f'<svg x="{x}" y="{y}" width="{ICON_SIZE}" height="{ICON_SIZE}"'
            f' viewBox="{vb}"{color_attr}'
            f' xmlns="http://www.w3.org/2000/svg">',
            svg_colored,
            count=1,
        )

        lines.append(f"  {embedded}")

        # Alternate label Y by column so adjacent labels are staggered and
        # do not overlap each other.
        label_y = y + ICON_SIZE + 5 + (12 if col % 2 else 0)

        lines.append(
            f'  <text x="{x + ICON_SIZE // 2}" y="{label_y}"'
            f' font-family="Helvetica, Arial, sans-serif" font-size="9"'
            f' fill="#555" text-anchor="middle">{name}</text>'
        )

    lines.append("</svg>")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines), encoding="utf-8")


# =============================================================================
# Main Entry Point
# =============================================================================


def run(argv: list[str] | None = None) -> int:
    """
    Top-level orchestrator for the EventCalendar CLI.

    Parses arguments, dispatches to the correct subcommand handler, assembles
    CalendarConfig, and drives the visualizer system to produce SVG or Excel
    output.  All other functions in this module are helpers called from here.

    Execution flow
    ──────────────
    1.  Generate a timestamped default output filename.
    2.  Build the argument parser (_create_argument_parser).
    3.  Expand @file tokens in sys.argv (_expand_sanitized_atfiles).
    4.  Parse arguments (argparse).
    5.  Configure logging (_configure_logging).

    6.  Dispatch pure-listing / inspection commands (return 0 on success):
          help      → _print_subcommand_help
          themes    → ThemeEngine.list_available_themes() + print
          fonts     → FONT_REGISTRY + print
          fontsheet → _generate_fontsheet_svg
          papersizes, patterns, icons, colors, palettes → DB query + print
          iconsheet → _generate_iconsheet_svg
          colorsheet→ _generate_colorsheet_svg (HSV-sorted via _hsv_sort_key)
          palette   → _generate_palette_svg

    7.  Require begin/end dates; error if absent.

    8.  Dispatch excelheader (before the full config pipeline — it does not
        need paper sizes or the weekly layout engine):
          _open_calendar_db → create config → calc_calendar_range
          → load_python_holidays → apply theme → _resolve_palette_overrides
          → generate_excel_header

    9.  For calendar visualizers (weekly / mini / mini-icon / text-mini /
        timeline / blockplan):
          a. _open_calendar_db; load paper sizes
          b. _apply_args_to_config
          c. calc_calendar_range  (adjusts for complete weeks)
          d. db.load_python_holidays  (live government holidays)
          e. Build fiscal lookup if --fiscal specified
          f. Load & pre-apply theme  (pass 1: exposes size rules for setfontsizes)
          g. _apply_text_options  (template vars have resolved date boundaries now)
          h. setfontsizes  (auto-scale fonts to paper/page dimensions)
          i. Re-apply theme  (pass 2: explicit theme font sizes override auto-scaling)
          j. _reapply_post_theme_cli_overrides  (restore CLI negation flags)
          k. _resolve_palette_overrides  (palette names → hex colours)
          l. WeeklyCalendarLayout.calculate  (weekly only — pre-compute coords)
          m. _to_output_dir_path  (confine output to output/ directory)
          n. VisualizerFactory.create(view_type).generate(config, db)

    Error handling / exit codes
    ───────────────────────────
    0 — Success
    1 — Invalid date / date range (InvalidDateError)
    2 — Database or configuration error (DatabaseError, ConfigError)
    3 — Unexpected / unhandled exception (full traceback logged)

    Nested helper
    ─────────────
    _hsv_sort_key(r) — converts a colour dict's red/green/blue fields to an
    HSV tuple for sorting the colorsheet output.  Defined inside run() so the
    ``colorsys`` import is lazy and only occurs when ``colorsheet`` is invoked.

    Args:
        argv: Raw CLI token list (defaults to sys.argv when None).

    Returns:
        Integer exit code (0 = success).
    """
    # Generate default output filename
    now = datetime.now()
    default_output = f"ecalendar{now.strftime('%Y%m%d%H%M')}.svg"

    # Parse command line arguments
    parser = _create_argument_parser(default_output)
    raw_args = list(argv[1:] if argv else sys.argv[1:])
    # @file sanitization is always on.
    try:
        raw_args = _expand_sanitized_atfiles(raw_args)
    except ConfigError as e:
        parser.error(str(e))

    args = parser.parse_args(raw_args)
    # Keep this visible in parsed args for metadata/diagnostics if needed.
    setattr(args, "sanitize_atfiles", True)

    # Configure logging
    _configure_logging(args.verbose, args.quiet)

    # Default output extension for text-mini
    if (
        args.command == "text-mini"
        and getattr(args, "outputfile", default_output) == default_output
    ):
        args.outputfile = default_output.replace(".svg", ".txt")

    # Dispatch subcommands.
    # This explicit chain favors straightforward traceability while commands
    # are still evolving; a handler map would reduce branch duplication later.
    if args.command == "help":
        _print_subcommand_help(args.subcommand, parser)
        return 0

    if args.command == "themes":
        from config.theme_engine import ThemeEngine

        themes = ThemeEngine.list_available_themes()
        print("Available themes:")
        for t in themes:
            print(f"  {t}")
        return 0

    if args.command == "fonts":
        from config.config import FONT_REGISTRY

        print(f"Available fonts ({len(FONT_REGISTRY)}):")
        for name in sorted(FONT_REGISTRY.keys()):
            print(f"  {name:35s} {FONT_REGISTRY[name]}")
        return 0

    if args.command == "fontsheet":
        from config.config import FONT_REGISTRY

        registry = dict(FONT_REGISTRY)
        if args.filter:
            flt = args.filter.lower()
            registry = {k: v for k, v in registry.items() if flt in k.lower()}
        if not registry:
            print(f"Error: no fonts match filter '{args.filter}'.", file=sys.stderr)
            return 1
        out_path = Path(args.outputfile) if args.outputfile else Path("output") / "fontsheet.svg"
        sheet_title = "Fonts" if not args.filter else f"Fonts: {args.filter}"
        _generate_fontsheet_svg(registry, out_path, color=args.color, title=sheet_title, fullset=args.fullset)
        if not args.quiet:
            print(out_path)
        return 0

    if args.command == "papersizes":
        db = _open_calendar_db(args.database)
        groups = db.get_paper_sizes_grouped()
        for group_name in sorted(groups.keys()):
            print(f"\n{group_name}:")
            for name, w, h in groups[group_name]:
                print(f"  {name:20s}  {w:7.1f} x {h:7.1f} pts")
        return 0

    if args.command == "patterns":
        db = _open_calendar_db(args.database)
        all_patterns = db.get_all_patterns()
        names = sorted(all_patterns.keys())
        print(f"Available SVG patterns ({len(names)}):")
        print('  Use in themes:  day_box.hash_pattern: "<name>"')
        print('  Use in rules:   hash_rules: [{pattern: "<name>", when: {...}}]')
        print()
        from visualizers.weekly.renderer import WeeklyCalendarRenderer

        col_width = max(len(n) for n in names) + 2
        cols = 3
        for i in range(0, len(names), cols):
            row_names = names[i : i + cols]
            parts = []
            for n in row_names:
                tw, th = WeeklyCalendarRenderer._parse_svg_tile_size(all_patterns[n])
                tile = f"({int(tw)}x{int(th)})"
                parts.append(f"{n:<{col_width}}{tile:<12}")
            print("  " + "  ".join(parts))
        return 0

    if args.command == "icons":
        db = _open_calendar_db(args.database)
        all_icons = db.get_all_icons()
        print(f"Available SVG icons ({len(all_icons)}):")
        print("  Use in event Icon fields by icon name.")
        print()
        names = [str((row.get("name") or "")).strip() for row in all_icons]
        names = [n for n in names if n]
        if names:
            col_width = max(len(n) for n in names) + 2
            cols = 3
            for i in range(0, len(names), cols):
                row_names = names[i : i + cols]
                print("  " + "".join(f"{n:<{col_width}}" for n in row_names).rstrip())
        return 0

    if args.command == "iconsheet":
        db = _open_calendar_db(args.database)
        all_icons = db.get_all_icons()
        filtered = all_icons
        if args.filter:
            flt = args.filter.lower()
            filtered = [
                row for row in all_icons if flt in str(row.get("name") or "").lower()
            ]
        if not filtered:
            print(f"Error: no icons match filter '{args.filter}'.", file=sys.stderr)
            print(
                "Use 'ecalendar.py icons' to list available icon names.",
                file=sys.stderr,
            )
            return 1
        if args.outputfile:
            out_path = Path(args.outputfile)
        else:
            out_path = Path("output") / "iconsheet.svg"
        sheet_title = "Icons" if not args.filter else f"Icons: {args.filter}"
        _generate_iconsheet_svg(filtered, out_path, color=args.color, title=sheet_title)
        if not args.quiet:
            print(out_path)
        return 0

    if args.command == "colors":
        db = _open_calendar_db(args.database)
        all_colors = db.get_all_colors()
        print(f"Available colors ({len(all_colors)}):")
        print("  EN                             RGB")
        for row in all_colors:
            en = str(row.get("EN") or "").strip()
            r = row.get("red")
            g = row.get("green")
            b = row.get("blue")
            print(f"  {en:30s} ({r},{g},{b})")
        return 0

    if args.command == "colorsheet":
        db = _open_calendar_db(args.database)
        all_colors = db.get_all_colors()
        filtered = all_colors
        if args.filter:
            flt = args.filter.lower()
            filtered = [
                row for row in all_colors if flt in str(row.get("EN") or "").lower()
            ]
        import colorsys
        def _hsv_sort_key(r: dict) -> tuple:
            # Sort coloursheet swatches by perceptual hue (0–1 around the
            # colour wheel), then saturation, then value.  This groups
            # achromatic colours (blacks/greys/whites with H=0, S=0) first,
            # followed by reds, oranges, yellows, greens, blues, purples.
            # colorsys is imported lazily here so it only loads for colorsheet.
            red   = int(r.get("red")   or 0) / 255.0
            green = int(r.get("green") or 0) / 255.0
            blue  = int(r.get("blue")  or 0) / 255.0
            h, s, v = colorsys.rgb_to_hsv(red, green, blue)
            return (h, s, v)
        filtered = sorted(filtered, key=_hsv_sort_key)
        if not filtered:
            print(f"Error: no colors match filter '{args.filter}'.", file=sys.stderr)
            print(
                "Use 'ecalendar.py colors' to list available color names.",
                file=sys.stderr,
            )
            return 1
        if args.outputfile:
            out_path = Path(args.outputfile)
        else:
            out_path = Path("output") / "colorsheet.svg"
        sheet_title = "Colors" if not args.filter else f"Colors: {args.filter}"
        _generate_colorsheet_svg(filtered, out_path, title=sheet_title)
        if not args.quiet:
            print(out_path)
        return 0

    if args.command == "palettes":
        db = _open_calendar_db(args.database)
        all_palettes = db.get_all_palettes()
        names = sorted(all_palettes.keys())
        print(f"Available palettes ({len(names)}):")
        print()
        col_width = max(len(n) for n in names) + 2
        for name in names:
            count = len(all_palettes[name])
            print(f"  {name:<{col_width}}{count} colors")
        return 0

    if args.command == "palette":
        db = _open_calendar_db(args.database)
        colors = db.get_palette(args.palette_name)
        if colors is None:
            print(
                f"Error: palette '{args.palette_name}' not found in database.",
                file=sys.stderr,
            )
            print(
                "Use 'ecalendar.py palettes' to list available palettes.",
                file=sys.stderr,
            )
            return 1
        if args.outputfile:
            out_path = Path(args.outputfile)
        else:
            safe_name = args.palette_name.replace("/", "_").replace("\\", "_")
            out_path = Path("output") / f"{safe_name}.svg"
        _generate_palette_svg(args.palette_name, colors, out_path)
        if not args.quiet:
            print(out_path)
        return 0

    # Calendar views and excelheader require date args
    if not args.begin or not args.end:
        parser.error("START_DATE and END_DATE are required")

    # excelheader — Excel workbook with timeband header rows
    if args.command == "excelheader":
        from visualizers.excelheader import generate_excel_header

        _eh_db = _open_calendar_db(args.database)
        _eh_config = create_calendar_config()
        _eh_config.weekend_style = args.weekends
        _eh_config.country = args.country
        _eh_config.userstart = args.begin
        _eh_config.userend = args.end
        calc_calendar_range(_eh_config, args.begin, args.end)
        _eh_db.load_python_holidays(
            _eh_config.country, _eh_config.adjustedstart, _eh_config.adjustedend
        )
        if getattr(args, "theme", None):
            from config.theme_engine import ThemeEngine

            _eh_te = ThemeEngine()
            _eh_te.load(args.theme)
            _eh_te.apply(_eh_config)
            _resolve_palette_overrides(_eh_config, _eh_db)
        out_path = (
            Path(args.outputfile) if args.outputfile else Path("output") / "excelheader.xlsx"
        )
        out_path.parent.mkdir(parents=True, exist_ok=True)
        generate_excel_header(_eh_config, _eh_db, out_path)
        if not args.quiet:
            print(out_path)
        return 0

    # Create calendar configuration
    config = create_calendar_config()

    try:
        # Validate database and load paper sizes
        db = _open_calendar_db(args.database)
        paper_sizes = db.get_paper_sizes()
        logger.info(f"Using database: {args.database}")

        # Apply command line arguments to config
        _apply_args_to_config(args, config, paper_sizes)

        # Store raw user dates before weekly adjustments
        config.userstart = args.begin
        config.userend = args.end

        # Calculate date range (adjusts for complete weeks)
        calc_calendar_range(config, args.begin, args.end)

        # Load government holidays from the 'holidays' Python package into the DB
        # layer so all renderers transparently use live package data instead of
        # the static 'government' table in the database.
        db.load_python_holidays(
            config.country, config.adjustedstart, config.adjustedend
        )

        # Build fiscal calendar lookup if fiscal calendar is enabled
        if config.fiscal_calendar_type:
            from shared.fiscal_calendars import (
                create_fiscal_calendar,
                build_fiscal_lookup,
            )

            fiscal_cal = create_fiscal_calendar(config.fiscal_calendar_type)
            start_d = datetime.strptime(config.adjustedstart, "%Y%m%d").date()
            end_d = datetime.strptime(config.adjustedend, "%Y%m%d").date()
            config.fiscal_lookup = build_fiscal_lookup(fiscal_cal, start_d, end_d)
            logger.info(f"Fiscal calendar enabled: {fiscal_cal.name}")

        theme_engine = None
        if getattr(args, "theme", None):
            from config.theme_engine import ThemeEngine

            theme_engine = ThemeEngine()
            theme_engine.load(args.theme)
            # Pre-apply so base.size_rule can influence setfontsizes.
            theme_engine.apply(config)

        # Apply text options (after date range calculation for template vars)
        _apply_text_options(args, config)

        # Optimize font sizes
        config = setfontsizes(config)

        # Re-apply theme after setfontsizes so explicit theme font sizes
        # (e.g., mini/title/timeline) still take precedence.
        if theme_engine is not None:
            theme_engine.apply(config)
            _reapply_post_theme_cli_overrides(args, config)
            logger.info(f"Applied theme: {theme_engine.theme_name}")

        # Resolve any DB palette name references set by the theme into
        # actual color dicts/lists and single hex color values.
        _resolve_palette_overrides(config, db)

        # Generate coordinates (weekly view uses pre-computed coords;
        # other visualizers handle layout internally in generate())
        view_type = args.command
        if view_type == "weekly":
            config.CalendarCoord = WeeklyCalendarLayout().calculate(config)

        # Set output file (always under output/).
        output_name = args.outputfile or default_output
        Path("output").mkdir(parents=True, exist_ok=True)
        config.outputfile = _to_output_dir_path(output_name)

        # Handle empty calendar option
        if args.empty:
            logger.info("Creating empty calendar (no events)")
            config.includeevents = False
            config.includedurations = False
            config.ignorecomplete = True
            config.milestones = False

        # Store command line for SVG metadata
        config.command_line = " ".join(argv if argv else sys.argv)

        # Generate the SVG
        if not args.quiet:
            print(config.outputfile)

        # Use the visualizer system
        view_type = args.command
        logger.debug(f"Using visualization type: {view_type}")

        visualizer = VisualizerFactory.create(view_type)

        # Validate config for this visualizer
        warnings = visualizer.validate_config(config)
        for warning in warnings:
            logger.warning(warning)

        if config.include_overflow and "overflow" not in visualizer.supported_options:
            logger.warning(
                f"--overflow is not supported for '{view_type}' visualization and will be ignored"
            )

        # Warn about SVG layout options not applicable to text-only output
        _svg_layout_checks = [
            ("margin",                   getattr(args, "margin", False),                              "--margin"),
            ("header",                   getattr(args, "header", False),                              "--header"),
            ("footer",                   getattr(args, "footer", False),                              "--footer"),
            ("headerleft",               bool(getattr(args, "headerleft", "")),                       "--headerleft"),
            ("headercenter",             bool(getattr(args, "headercenter", "")),                     "--headercenter"),
            ("headerright",              bool(getattr(args, "headerright", "")),                      "--headerright"),
            ("footerleft",               bool(getattr(args, "footerleft", "")),                       "--footerleft"),
            ("footercenter",             bool(getattr(args, "footercenter", "")),                     "--footercenter"),
            ("footerright",              bool(getattr(args, "footerright", "")),                      "--footerright"),
            ("watermark",                bool(getattr(args, "watermark", "")),                        "--watermark"),
            ("watermark_rotation_angle", getattr(args, "watermark_rotation_angle", None) is not None, "--watermark-rotation-angle"),
            ("imagemark",                bool(getattr(args, "imagemark", "")),                        "--imagemark"),
            ("shrink",                   getattr(args, "shrink", False),                              "--shrink"),
            ("shade",                    getattr(args, "shade", False),                               "--shade"),
            ("monthnames",               getattr(args, "monthnames", False),                          "--monthnames"),
        ]
        for opt_name, was_set, flag in _svg_layout_checks:
            if was_set and opt_name not in visualizer.supported_options:
                logger.warning(
                    f"{flag} is not supported for '{view_type}' visualization and will be ignored"
                )

        # Generate the visualization
        result = visualizer.generate(config, db)

        logger.info(
            f"Calendar generated: {result.output_path} "
            f"({result.event_count} events, {result.overflow_count} overflow)"
        )
        return 0

    except InvalidDateError as e:
        logger.error(str(e))
        return 1
    except (DatabaseError, ConfigError) as e:
        logger.error(str(e))
        return 2
    except Exception as e:
        logger.exception(f"Unexpected error: {e}")
        return 3


# =============================================================================
# Script Entry Point
# =============================================================================

if __name__ == "__main__":
    sys.exit(run(sys.argv))
