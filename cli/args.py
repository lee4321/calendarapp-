"""
Command-line argument layer for the EventCalendar CLI.

Owns @file (atfile) expansion, the output-path traversal guard, the
argparse builder covering every subcommand, and the per-subcommand help
printer.  ``ecalendar.run()`` is the production caller; tests exercise
the parser directly.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from cli.errors import ConfigError


def _prog_version() -> str:
    """Version string, deferred to avoid a circular import at load time."""
    from ecalendar import __version__

    return __version__


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
                           patternsheet, icons, iconsheet, colors, colorsheet,
                           palettes, palettesheet
    Help                 : help <subcommand>

    Argument groups (per visualizer subcommand)
    ───────────────────────────────────────────
    - Database Options        --database, --country
    - Output Options          --outputfile, --papersize, --orientation, --shrink
    - Layout Options          --weekends, --header, --footer, --margin

    Options that a view's renderer never reads are not registered on that
    view's parser (per-view audit: docs/cli_theme_overrides.html, Appendix A).
    E.g. --monthnames and --overflow are weekly-only, --shade exists only on
    the day-grid views, and pit has no --nodurations (it always drops
    multi-day durations).
    - Header/Footer text      --headerleft, --headercenter, --headerright, …
    - Watermark Options       --watermark-text, --watermark-rotation-angle, --watermark-image
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
        prog="EventCalendar",
        fromfile_prefix_chars="@",
        description="Create calendars with events from a SQLite database",
        epilog=(
            f"EventCalendar ({_prog_version()}), Copyright (C) 2026 A. Lee Ingram, MobileLeverage LLC\n"
            "Change calendar configuration by customizing and specifying a theme file\n"
            "\n"
            "Command line parameters can be read from a file using @filename"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    sub = parser.add_subparsers(dest="command", required=True)

    weekly = sub.add_parser("weekly", help="Generate a SVG containing weekly calendar")
    mini = sub.add_parser("mini", help="Generate a SVG mini calendar")
    mini_icon = sub.add_parser(
        "mini-icon", help="Generate a mini calendar with icons for day numbers"
    )
    candybar = sub.add_parser(
        "candybar", help="Generate a SVG vertical year-strip (one row per ISO week)"
    )
    text_mini = sub.add_parser("text-mini", help="Generate a text only mini calendar")
    timeline = sub.add_parser("timeline", help="Generate a SVG timeline")
    pit = sub.add_parser(
        "pit",
        help="Generate a SVG Points-in-Time timeline (single-day events + milestones)",
    )
    blockplan = sub.add_parser("blockplan", help="Generate a SVG blockplan")
    compactplan = sub.add_parser(
        "compactplan",
        help="Generate a SVG compressed activities timeline",
    )
    excelheader = sub.add_parser(
        "excelheader",
        help="Generate an Excel workbook with blockplan-style timeband header rows",
    )
    excelblockplan = sub.add_parser(
        "excelblockplan",
        help=(
            "Generate an Excel workbook with blockplan-style timeband header "
            "rows plus one row per event/duration in the date range"
        ),
    )
    themes = sub.add_parser("themes", help="List available themes")
    papers = sub.add_parser("papersizes", help="List available paper sizes")
    patterns = sub.add_parser("patterns", help="List available day-box patterns")
    icons = sub.add_parser("icons", help="List available icons from database")
    colors = sub.add_parser("colors", help="List available colors from database")
    palettes = sub.add_parser(
        "palettes", help="List available color palettes from database"
    )
    palettesheet = sub.add_parser(
        "palettesheet", help="Generate a SVG preview of a named palette"
    )
    iconsheet = sub.add_parser(
        "iconsheet", help="Generate a SVG grid preview of icons from database"
    )
    patternsheet = sub.add_parser(
        "patternsheet",
        help="Generate a SVG grid preview of day-box patterns from database",
    )
    colorsheet = sub.add_parser(
        "colorsheet", help="Generate a SVG grid preview of named colors from database"
    )
    fonts = sub.add_parser("fonts", help="List available registered fonts")
    fontsheet = sub.add_parser(
        "fontsheet", help="Generate a SVG sample sheet for all registered fonts"
    )
    exportdata = sub.add_parser(
        "exportdata",
        help=(
            "Export filtered event/duration data as a CSV file "
            "compatible with importers/import_events.py"
        ),
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
            "candybar",
            "text-mini",
            "timeline",
            "pit",
            "blockplan",
            "compactplan",
            "excelheader",
            "excelblockplan",
            "themes",
            "papersizes",
            "patterns",
            "patternsheet",
            "icons",
            "iconsheet",
            "colors",
            "colorsheet",
            "palettes",
            "palettesheet",
            "fonts",
            "fontsheet",
            "exportdata",
        ],
        help="Subcommand to show help for",
    )

    # Shared argument groups are defined once and applied to all calendar-view
    # parsers to keep option semantics aligned across views.
    # If a flag belongs to every view, add it in these loops rather than
    # copy-pasting per-subcommand definitions.
    # Positional arguments for calendar views
    for view_parser in (
        weekly,
        mini,
        mini_icon,
        candybar,
        text_mini,
        timeline,
        pit,
        blockplan,
        compactplan,
        excelheader,
        excelblockplan,
        exportdata,
    ):
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

    # palettesheet subcommand arguments
    palettesheet.add_argument(
        "palette_name",
        type=str,
        nargs="?",
        default=None,
        metavar="NAME",
        help=(
            "Name of the palette to preview (case-sensitive, from DB palettes "
            "table). If omitted, every palette is rendered into a single SVG."
        ),
    )
    palettesheet.add_argument(
        "--outputfile",
        "-of",
        type=str,
        default=None,
        metavar="PATH",
        help="Output file path (default: output/palettesheet.svg, or output/<NAME>.svg when a palette is named)",
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
        "--paginate",
        action="store_true",
        help=(
            "Split the icons across multiple printable SVG pages instead of one "
            "large sheet. Enables --columns/--rows; without it a single SVG "
            "containing every icon is produced (the default)."
        ),
    )
    iconsheet.add_argument(
        "--columns",
        "-cols",
        type=int,
        default=None,
        metavar="N",
        help="Icon columns per page (requires --paginate; default: 8)",
    )
    iconsheet.add_argument(
        "--rows",
        "-rows",
        type=int,
        default=None,
        metavar="N",
        help="Icon rows per page (requires --paginate; default: 10)",
    )
    iconsheet.add_argument(
        "--sized",
        type=int,
        default=None,
        metavar="N",
        help=(
            "Icon cell size in points (one integer sets both width and height; "
            "the label/spacing gaps are unchanged). Requires --paginate; "
            "default: 24."
        ),
    )
    iconsheet.add_argument(
        "--outputfile",
        "-of",
        type=str,
        default=None,
        metavar="PATH",
        help=(
            "Output file name and path (default: output/iconsheet.svg). "
            "With --paginate, a '_pNN' suffix is appended per page "
            "(e.g. iconsheet_p01.svg)."
        ),
    )

    # patternsheet subcommand arguments
    patternsheet.add_argument(
        "--filter",
        "-f",
        type=str,
        default=None,
        metavar="TEXT",
        help="Filter patterns by name substring (case-insensitive)",
    )
    patternsheet.add_argument(
        "--color",
        "-c",
        type=str,
        default="#333333",
        metavar="COLOR",
        help="Fill color for pattern tiles (default: #333333)",
    )
    patternsheet.add_argument(
        "--outputfile",
        "-of",
        type=str,
        default=None,
        metavar="PATH",
        help="Output file name and path (default: output/patternsheet.svg)",
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
        "--weekend-days",
        type=str,
        default=None,
        metavar="DAYS",
        help=(
            "Comma-separated ISO weekday list (0=Mon..6=Sun) marking "
            "non-working days for holiday/weekend classification."
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

    # excelblockplan subcommand arguments — mirror excelheader plus blockplan
    # content filters so users get parity with the SVG blockplan view.
    excelblockplan.add_argument(
        "--outputfile",
        "-of",
        type=str,
        default=None,
        metavar="PATH",
        help="Output .xlsx path (default: output/ExcelBlockplan.xlsx)",
    )
    excelblockplan.add_argument(
        "--theme",
        "-th",
        type=str,
        default=None,
        metavar="THEME",
        help="Theme name or path to .yaml theme file",
    )
    excelblockplan.add_argument(
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
    excelblockplan.add_argument(
        "--weekend-days",
        type=str,
        default=None,
        metavar="DAYS",
        help=(
            "Comma-separated ISO weekday list (0=Mon..6=Sun) marking "
            "non-working days for holiday/weekend classification."
        ),
    )
    excelblockplan.add_argument(
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
    _ebp_content = excelblockplan.add_argument_group("Content Filtering")
    _ebp_content.add_argument(
        "--noevents",
        "-ne",
        action="store_true",
        help="Exclude single-day events",
    )
    _ebp_content.add_argument(
        "--nodurations",
        "-nd",
        action="store_true",
        help="Exclude multi-day durations",
    )
    _ebp_content.add_argument(
        "--ignorecomplete",
        "-ic",
        action="store_true",
        help="Exclude 100%% complete items",
    )
    _ebp_content.add_argument(
        "--milestones",
        "-mo",
        action="store_true",
        help="Show only milestones",
    )
    _ebp_content.add_argument(
        "--rollups",
        "-ro",
        action="store_true",
        help="Show only rollup entries",
    )
    _ebp_content.add_argument(
        "--WBS",
        type=str,
        default="",
        help=(
            "WBS filter expression. Comma-separated tokens; '!' excludes. "
            "Segments are dot-separated. '*' matches a segment, '**' matches "
            "any remaining segments (implicit if omitted)."
        ),
    )
    _ebp_content.add_argument(
        "--status",
        type=str,
        default=None,
        metavar="LIST",
        help=(
            "Comma-separated event statuses to include "
            "(active, draft, cancelled, archived, on-hold). "
            "Use 'all' for no filter. Default: active."
        ),
    )
    _ebp_content.add_argument(
        "--empty",
        "-e",
        action="store_true",
        help="Create blank workbook (no events)",
    )

    # exportdata subcommand arguments
    exportdata.add_argument(
        "--outputfile",
        "-o",
        type=str,
        default=None,
        metavar="PATH",
        help="Output CSV file path (default: output/exportdata_YYYYMMDD.csv)",
    )
    _ed_content = exportdata.add_argument_group("Content Filtering")
    _ed_content.add_argument(
        "--noevents",
        "-ne",
        action="store_true",
        help="Exclude single-day events",
    )
    _ed_content.add_argument(
        "--nodurations",
        "-nd",
        action="store_true",
        help="Exclude multi-day durations",
    )
    _ed_content.add_argument(
        "--ignorecomplete",
        "-ic",
        action="store_true",
        help="Exclude 100%% complete items",
    )
    _ed_content.add_argument(
        "--milestones",
        "-mo",
        action="store_true",
        help="Show only milestones",
    )
    _ed_content.add_argument(
        "--rollups",
        "-ro",
        action="store_true",
        help="Show only rollup entries",
    )
    _ed_content.add_argument(
        "--WBS",
        type=str,
        default="",
        help=(
            "WBS filter expression. Comma-separated tokens; '!' excludes. "
            "Segments are dot-separated. '*' matches a segment, '**' matches "
            "any remaining segments (implicit if omitted)."
        ),
    )
    _ed_content.add_argument(
        "--status",
        type=str,
        default=None,
        metavar="LIST",
        help=(
            "Comma-separated event statuses to include "
            "(active, draft, cancelled, archived, on-hold). "
            "Use 'all' for no filter. Default: active."
        ),
    )
    _ed_content.add_argument(
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
        candybar,
        text_mini,
        timeline,
        pit,
        blockplan,
        compactplan,
        excelheader,
        excelblockplan,
        papers,
        patterns,
        icons,
        colors,
        palettes,
        palettesheet,
        iconsheet,
        patternsheet,
        colorsheet,
        exportdata,
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
    _svg_views = (
        weekly,
        mini,
        mini_icon,
        candybar,
        timeline,
        pit,
        blockplan,
        compactplan,
    )

    # Per-view option gating.  A flag whose value a view's renderer never
    # reads is not registered on that view's parser at all
    # (docs/cli_theme_overrides.html, Appendix A):
    #   --shade         day-grid views only (shared day-style resolver)
    #   --weekend-days  views that classify days via config.get_weekend_days()
    #   --includenotes  views that render a notes line with event names
    _shade_views = (weekly, mini, mini_icon, candybar)
    _weekend_days_views = (weekly, timeline, blockplan, compactplan)
    _includenotes_views = (weekly, timeline, pit, blockplan, compactplan)

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
        if view_parser is not compactplan:
            # compactplan always shrinks to content; the flag adds nothing there.
            output_group.add_argument(
                "--shrink",
                action="store_true",
                help=(
                    "Shrink SVG width/height/viewBox to the bounding box of "
                    "rendered content, removing blank page whitespace."
                ),
            )
        output_group.add_argument(
            "--embed-data",
            action="store_true",
            help="Embed source event data (CSV) inside SVG metadata",
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
        if view_parser in _weekend_days_views:
            layout_group.add_argument(
                "--weekend-days",
                type=str,
                default=None,
                metavar="DAYS",
                help=(
                    "Comma-separated ISO weekday list (0=Mon..6=Sun) marking "
                    "non-working days for holiday/weekend classification. "
                    "Defaults to Sat/Sun when weekends are shown."
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
        if view_parser is weekly:
            # include_month_name is read only by the weekly renderer.
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
            "--watermark-text", "-wt", type=str, default="", help="Watermark text"
        )
        watermark_group.add_argument(
            "--watermark-rotation-angle",
            type=float,
            default=None,
            metavar="DEGREES",
            help="Rotate text watermark by degrees (clockwise coordinates)",
        )
        watermark_group.add_argument(
            "--watermark-image",
            "-wi",
            type=str,
            default="",
            help="Watermark image file",
        )

        # Content filtering (day-grid views additionally get --shade; weekly
        # alone gets --overflow)
        content_group = view_parser.add_argument_group("Content Filtering")
        content_group.add_argument(
            "--empty",
            "-e",
            action="store_true",
            help="Create blank calendar (no events)",
        )
        if view_parser in _shade_views:
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
        if view_parser is not pit:
            # PIT drops multi-day durations unconditionally.
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
        if view_parser in _includenotes_views:
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
            "--status",
            type=str,
            default=None,
            metavar="LIST",
            help=(
                "Comma-separated event statuses to include "
                "(active, draft, cancelled, archived, on-hold). "
                "Use 'all' for no filter. Default: active."
            ),
        )
        if view_parser is weekly:
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

    # text-mini: weekends + content filtering only (no SVG layout,
    # header/footer, watermark, shade, overflow; its renderer also never
    # reads weekend_days or include_notes)
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
        "--status",
        type=str,
        default=None,
        metavar="LIST",
        help=(
            "Comma-separated event statuses to include "
            "(active, draft, cancelled, archived, on-hold). "
            "Use 'all' for no filter. Default: active."
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
            "--mini-no-adjacent",
            "-mna",
            action="store_true",
            help="Hide leading/trailing days from adjacent months",
        )
    # SVG mini views only — the text-mini month title is hardcoded.
    for g in (mini_group, mini_icon_group):
        g.add_argument(
            "--mini-title-format",
            type=str,
            default=None,
            metavar="FMT",
            help="Format string for month title (default: MMM YY)",
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
        choices=[
            "squares",
            "darksquare",
            "darkcircles",
            "circles",
            "squircles",
            "darksquircles",
        ],
        help=(
            "Icon set to use for day numbers "
            "(choices: squares, darksquare, darkcircles, circles, squircles, darksquircles; "
            "default: squares)"
        ),
    )

    # Candybar-specific options (vertical year-strip)
    candybar_group = candybar.add_argument_group("Candybar Options")
    candybar_group.add_argument(
        "--candybar-row-height",
        type=float,
        default=None,
        metavar="POINTS",
        help="Fixed week-row height in points (default: 0 = auto-fit to page)",
    )
    candybar_group.add_argument(
        "--candybar-cell-width",
        type=float,
        default=None,
        metavar="POINTS",
        help="Fixed day-cell width in points (default: 0 = square, width == row height)",
    )
    candybar_group.add_argument(
        "--candybar-max-rows-per-page",
        type=int,
        default=None,
        metavar="N",
        help="Split into side-by-side strips after N week rows (0 = single strip)",
    )
    candybar_group.add_argument(
        "--candybar-suppress-weekends",
        action="store_true",
        default=None,
        help="Drop Sat/Sun columns (default: weekends are shown)",
    )
    candybar_group.add_argument(
        "--candybar-no-week-numbers",
        action="store_true",
        help="Hide the week-number column (shown by default)",
    )
    candybar_group.add_argument(
        "--candybar-month-side",
        type=str,
        default=None,
        choices=["left", "right"],
        help="Side for the merged month-name box (default: right)",
    )
    candybar_group.add_argument(
        "--candybar-month-rotation",
        type=float,
        default=None,
        metavar="DEGREES",
        help="Rotate the month-name label (e.g. -90 for vertical, reading up)",
    )
    candybar_group.add_argument(
        "--candybar-weekend-fill",
        type=str,
        default=None,
        metavar="COLOR",
        help="Shade Sat/Sun day cells with this color (default: no weekend shading)",
    )
    candybar_group.add_argument(
        "--candybar-month-shading",
        action="store_true",
        default=None,
        help="Tint day cells per month (alternating bands; theme can set colors)",
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

    # =====================================================================
    # PIT (Points in Time) options
    # =====================================================================
    pit_group = pit.add_argument_group("PIT Options")
    pit_group.add_argument(
        "--direction",
        type=str,
        default=None,
        choices=["horizontal", "vertical"],
        help=(
            "Axis direction (default: horizontal). Note: --orientation "
            "remains the page-orientation flag (portrait/landscape)."
        ),
    )
    pit_group.add_argument(
        "--label-side",
        type=str,
        default=None,
        choices=["primary", "secondary", "both"],
        help=(
            "Which side(s) of the axis the labels occupy. primary = above "
            "(horizontal) / right (vertical); secondary = below / left; "
            "both = chronologically alternating. Default: both."
        ),
    )
    pit_group.add_argument(
        "--tick-unit",
        type=str,
        default=None,
        choices=[
            "month",
            "week",
            "fiscal_quarter",
            "fiscal_period",
            "interval",
            "date",
            "year",
        ],
        help="Axis tick granularity (timeband unit). Default: month.",
    )
    pit_group.add_argument(
        "--tick-interval",
        type=int,
        default=None,
        metavar="DAYS",
        help="For --tick-unit interval, days between ticks (default: 1).",
    )
    pit_group.add_argument(
        "--tick-label-format",
        type=str,
        default=None,
        metavar="FMT",
        help=(
            "Arrow date format for tick labels (e.g. 'MMM D'). For week/"
            "interval units the timeband label is used when omitted."
        ),
    )
    pit_group.add_argument(
        "--tick-length",
        type=float,
        default=None,
        metavar="POINTS",
        help="Half-length of each axis tick mark, per side (default: 5.0).",
    )
    pit_group.add_argument(
        "--no-ticks",
        dest="pit_show_ticks",
        action="store_false",
        default=None,
        help="Suppress axis tick marks and labels.",
    )
    pit_group.add_argument(
        "--no-tick-labels",
        dest="pit_show_tick_labels",
        action="store_false",
        default=None,
        help="Draw tick marks but no tick labels.",
    )
    pit_group.add_argument(
        "--date-placement",
        type=str,
        default=None,
        choices=["inline", "axis", "none"],
        help=(
            "Where each event date is drawn: inline (a line inside the "
            "label box, with the name/notes — never collides; default), "
            "axis (opposite the axis at the marker — the ruler look, but "
            "dates collide when events cluster), or none."
        ),
    )
    pit_group.add_argument(
        "--today-line",
        dest="pit_today_line",
        action="store_true",
        default=None,
        help="Draw the today line (default: on).",
    )
    pit_group.add_argument(
        "--no-today-line",
        dest="pit_today_line",
        action="store_false",
        help="Suppress the today line.",
    )
    pit_group.add_argument(
        "--today-date",
        type=str,
        default=None,
        metavar="YYYYMMDD",
        help=(
            "Override the today-line position. Lets a forward-dated "
            "presentation be prepared with the 'correct' today indicator."
        ),
    )
    pit_group.add_argument(
        "--today-label",
        type=str,
        default=None,
        metavar="TEXT",
        help='Today-line label text (default: "today"; "" suppresses).',
    )
    pit_group.add_argument(
        "--event-icon",
        type=str,
        default=None,
        metavar="NAME",
        help=(
            "DB icon name drawn inside each event's label box, on the "
            "name line and to the left of the name. Does NOT change the "
            "axis marker (always a built-in circle)."
        ),
    )
    pit_group.add_argument(
        "--milestone-icon",
        type=str,
        default=None,
        metavar="NAME",
        help=(
            "DB icon name drawn inside each milestone's label box, on "
            "the name line and to the left of the name. Does NOT change "
            "the axis marker (always a built-in diamond)."
        ),
    )
    pit_group.add_argument(
        "--marker-size",
        type=float,
        default=None,
        metavar="POINTS",
        help=(
            "Bounding-box size of the axis marker (built-in circle / "
            "diamond) in points (default: 7.0)."
        ),
    )
    pit_group.add_argument(
        "--label-icon-size",
        type=float,
        default=None,
        metavar="POINTS",
        help=(
            "Longest viewBox side of the label-box icon, in points. "
            "Defaults to the event-name font size so the glyph fits "
            "cleanly on the name baseline."
        ),
    )
    pit_group.add_argument(
        "--label-icon-gap",
        type=float,
        default=None,
        metavar="POINTS",
        help=(
            "Horizontal gap (points) between the label-box icon and the "
            "start of the event name (default: 4.0)."
        ),
    )
    pit_group.add_argument(
        "--leader-dash",
        type=str,
        default=None,
        metavar="DASHARRAY",
        help='SVG stroke-dasharray for leaders, e.g. "4,2".',
    )
    pit_group.add_argument(
        "--leader-label-anchor",
        type=str,
        default=None,
        choices=["start", "center", "end"],
        help=(
            "Where the leader meets the label box along the axis. "
            "center (default) joins the box middle and never collides; "
            "start/end join the leading/trailing edge and may overlap on "
            "dense timelines."
        ),
    )
    pit_group.add_argument(
        "--leader-length",
        type=float,
        default=None,
        metavar="POINTS",
        help=(
            "Distance from the axis to the first row of labels, i.e. the "
            "leader length (default: 8.0). Larger values lengthen leaders "
            "and widen row-to-row spacing."
        ),
    )
    pit_group.add_argument(
        "--leader-stub",
        type=float,
        default=None,
        metavar="POINTS",
        help=(
            "Length of the straight perpendicular segment where each leader "
            "meets its label box (default: 6.0). Keeps the arrowhead flush "
            "with the line; 0 disables. Equivalent to pit.leader.end_stub."
        ),
    )

    # Fiscal calendar options — all calendar views
    _fiscal_views = (
        weekly,
        mini,
        mini_icon,
        candybar,
        text_mini,
        timeline,
        pit,
        blockplan,
        compactplan,
    )
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
    for _vp in (weekly, mini, mini_icon, candybar):
        _vp._option_string_actions.get(
            "--fiscal"
        ) and None  # guard: group already added above
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
        candybar,
        text_mini,
        timeline,
        pit,
        blockplan,
        compactplan,
        excelheader,
        excelblockplan,
        themes,
        papers,
        patterns,
        icons,
        colors,
        palettes,
        palettesheet,
        iconsheet,
        patternsheet,
        colorsheet,
        fontsheet,
        fonts,
        exportdata,
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
    calendar_subcommands = {
        "weekly",
        "mini",
        "mini-icon",
        "candybar",
        "text-mini",
        "timeline",
        "blockplan",
        "compactplan",
    }
    # SVG-producing views only (text-mini produces plain text, not SVG)
    svg_calendar_subcommands = {
        "weekly",
        "mini",
        "mini-icon",
        "candybar",
        "timeline",
        "blockplan",
        "compactplan",
    }
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
        print(
            "  weekly      Period labels on day boxes; --fiscal-colors for period-shaded backgrounds"
        )
        print(
            "  mini        Period labels at bottom of day cells; --fiscal-colors for backgrounds"
        )
        print(
            "  text-mini   Period short name (e.g. P1) as day symbol on period-start days"
        )
        print("  timeline    --fiscal-show-periods: period band row above axis")
        print("              --fiscal-show-quarters: quarter band row above axis")
        print(
            "  blockplan   fiscal_quarter bands use NRF-aware boundaries when --fiscal is set"
        )
        print(
            "  compactplan fiscal_quarter bands use NRF-aware boundaries; fiscal_period band unit available"
        )

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

