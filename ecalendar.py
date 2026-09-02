#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
EventCalendar - SVG Calendar Generator

Creates highly customizable calendars with events from a SQLite database.

(c) 2026 A. Lee Ingram
"""

from __future__ import annotations

__version__ = "26.09.02.0"

import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING


from config.config import (
    create_calendar_config,
    setfontsizes,
)
from shared.date_utils import InvalidDateError, calc_calendar_range, parse_date
from visualizers.factory import VisualizerFactory
from visualizers.weekly.layout import WeeklyCalendarLayout

if TYPE_CHECKING:
    pass

# Module logger
logger = logging.getLogger(__name__)

# =============================================================================
# Split-module imports
# =============================================================================
# ecalendar.py holds only run(); the layers live in their own modules.
# The private names are re-exported here because tests and downstream
# tooling historically reach them via `ecalendar.<name>`.

from cli.errors import CalendarError, ConfigError, DatabaseError  # noqa: E402,F401
from cli.args import (  # noqa: E402,F401
    _create_argument_parser,
    _expand_sanitized_atfiles,
    _parse_atfile_lines,
    _print_subcommand_help,
    _to_output_dir_path,
)
from cli.config_assembly import (  # noqa: E402,F401
    _apply_args_to_config,
    _apply_text_options,
    _configure_logging,
    _open_calendar_db,
    _parse_status_filter,
    _parse_weekend_days,
    _reapply_post_theme_cli_overrides,
    _validate_database,
    replace_template_vars,
)
from cli.exportdata import (  # noqa: E402,F401
    _event_to_row,
    _events_to_csv_string,
    _fmt_date,
    _write_exportdata_csv,
)
from config.palette_resolver import (  # noqa: E402,F401
    _resolve_palette_overrides,
    _resolve_single_palette_ref,
)
from visualizers.sheets import (  # noqa: E402,F401
    _generate_all_palettes_svg,
    _generate_colorsheet_svg,
    _generate_fontsheet_svg,
    _generate_iconsheet_svg,
    _generate_palette_svg,
    _generate_patternsheet_svg,
)


# =============================================================================
# CLI Argument Parsing
# =============================================================================


# =============================================================================
# Input Validation
# =============================================================================


# =============================================================================
# Subcommand Help
# =============================================================================


# =============================================================================
# Palette Resolution
# =============================================================================


def _validate_pagination_args(args) -> int:
    """
    Validate the shared ``--paginate`` option group of the sample-sheet commands.

    ``colorsheet``, ``fontsheet``, ``iconsheet`` and ``palettesheet`` all expose
    the same pagination flags, so the same two rules apply to each of them:
    ``--columns``/``--rows``/``--sized`` are only meaningful alongside
    ``--paginate``, and ``--sized`` must be a positive number of points.

    Called by:
        run() at the start of the colorsheet / fontsheet / iconsheet /
        palettesheet branches.

    Returns:
        0 when the arguments are valid, 1 after printing an error to stderr.
    """
    if not args.paginate and (
        args.columns is not None or args.rows is not None or args.sized is not None
    ):
        print(
            "Error: --columns/--rows/--sized require --paginate.",
            file=sys.stderr,
        )
        return 1
    if args.sized is not None and args.sized < 1:
        print("Error: --sized must be a positive integer.", file=sys.stderr)
        return 1
    return 0


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
          patternsheet → _generate_patternsheet_svg
          colorsheet→ _generate_colorsheet_svg (HSV-sorted via _hsv_sort_key)
          palettesheet → _generate_palette_svg

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
          j. _reapply_post_theme_cli_overrides  (re-assert explicit CLI values
             over theme-set fields — CLI always beats the theme)
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
    # Generate default output filename. The "ecalendar" prefix acts as a
    # sentinel so we can detect when the user did not override --outputfile
    # and substitute the subcommand name (e.g. "blockplan202605251040.svg").
    now = datetime.now()
    _timestamp = now.strftime("%Y%m%d%H%M")
    default_output = f"ecalendar{_timestamp}.svg"

    print(f"EventCalendar ({__version__})")

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

    # When the user did not pass --outputfile, derive the default name from
    # the subcommand so each visualizer produces a recognizable file
    # (e.g. weekly202605251040.svg, blockplan202605251040.svg).
    _svg_visualizer_commands = {
        "weekly",
        "mini",
        "mini-icon",
        "candybar",
        "timeline",
        "pit",
        "blockplan",
        "gantt",
        "compactplan",
    }
    if (
        getattr(args, "outputfile", None) == default_output
        and args.command in _svg_visualizer_commands
    ):
        args.outputfile = f"{args.command}{_timestamp}.svg"

    # Default output extension for text-mini
    if (
        args.command == "text-mini"
        and getattr(args, "outputfile", default_output) == default_output
    ):
        args.outputfile = f"text-mini{_timestamp}.txt"

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
        rc = _validate_pagination_args(args)
        if rc:
            return rc
        out_path = (
            Path(args.outputfile)
            if args.outputfile
            else Path("output") / "fontsheet.svg"
        )
        sheet_title = "Fonts" if not args.filter else f"Fonts: {args.filter}"
        written = _generate_fontsheet_svg(
            registry,
            out_path,
            color=args.color,
            title=sheet_title,
            fullset=args.fullset,
            paginate=args.paginate,
            columns=args.columns if args.columns is not None else 2,
            rows=args.rows if args.rows is not None else 10,
            cell_size=args.sized if args.sized is not None else 16,
        )
        if not args.quiet:
            for page_path in written:
                print(page_path)
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
        from renderers.svg_patterns import parse_svg_tile_size

        col_width = max(len(n) for n in names) + 2
        cols = 3
        for i in range(0, len(names), cols):
            row_names = names[i : i + cols]
            parts = []
            for n in row_names:
                tw, th = parse_svg_tile_size(all_patterns[n])
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
        rc = _validate_pagination_args(args)
        if rc:
            return rc
        if args.outputfile:
            out_path = Path(args.outputfile)
        else:
            out_path = Path("output") / "iconsheet.svg"
        sheet_title = "Icons" if not args.filter else f"Icons: {args.filter}"
        written = _generate_iconsheet_svg(
            filtered,
            out_path,
            color=args.color,
            title=sheet_title,
            paginate=args.paginate,
            columns=args.columns if args.columns is not None else 8,
            rows=args.rows if args.rows is not None else 10,
            cell_size=args.sized if args.sized is not None else 24,
        )
        if not args.quiet:
            for page_path in written:
                print(page_path)
        return 0

    if args.command == "patternsheet":
        db = _open_calendar_db(args.database)
        all_patterns = db.get_all_patterns()
        items = sorted(all_patterns.items())
        if args.filter:
            flt = args.filter.lower()
            items = [(name, svg) for name, svg in items if flt in name.lower()]
        if not items:
            print(f"Error: no patterns match filter '{args.filter}'.", file=sys.stderr)
            print(
                "Use 'ecalendar.py patterns' to list available pattern names.",
                file=sys.stderr,
            )
            return 1
        if args.outputfile:
            out_path = Path(args.outputfile)
        else:
            out_path = Path("output") / "patternsheet.svg"
        sheet_title = "Patterns" if not args.filter else f"Patterns: {args.filter}"
        _generate_patternsheet_svg(items, out_path, color=args.color, title=sheet_title)
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
            red = int(r.get("red") or 0) / 255.0
            green = int(r.get("green") or 0) / 255.0
            blue = int(r.get("blue") or 0) / 255.0
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
        rc = _validate_pagination_args(args)
        if rc:
            return rc
        if args.outputfile:
            out_path = Path(args.outputfile)
        else:
            out_path = Path("output") / "colorsheet.svg"
        sheet_title = "Colors" if not args.filter else f"Colors: {args.filter}"
        written = _generate_colorsheet_svg(
            filtered,
            out_path,
            title=sheet_title,
            paginate=args.paginate,
            columns=args.columns if args.columns is not None else 8,
            rows=args.rows if args.rows is not None else 10,
            cell_size=args.sized if args.sized is not None else 110,
        )
        if not args.quiet:
            for page_path in written:
                print(page_path)
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

    if args.command == "palettesheet":
        rc = _validate_pagination_args(args)
        if rc:
            return rc
        db = _open_calendar_db(args.database)
        # Map uppercase hex → colour name so swatches can be labelled like the colorsheet
        name_lookup = {c["hex"].upper(): c["EN"] for c in db.get_all_colors()}
        page_opts = dict(
            paginate=args.paginate,
            columns=args.columns if args.columns is not None else 12,
            rows=args.rows if args.rows is not None else 10,
            cell_size=args.sized if args.sized is not None else 80,
        )
        if args.palette_name is None:
            all_palettes = db.get_all_palettes()
            if not all_palettes:
                print("Error: no palettes found in database.", file=sys.stderr)
                return 1
            out_path = (
                Path(args.outputfile)
                if args.outputfile
                else Path("output") / "palettesheet.svg"
            )
            written = _generate_all_palettes_svg(
                all_palettes, out_path, name_lookup, **page_opts
            )
            if not args.quiet:
                for page_path in written:
                    print(page_path)
            return 0
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
        written = _generate_palette_svg(
            args.palette_name, colors, out_path, name_lookup, **page_opts
        )
        if not args.quiet:
            for page_path in written:
                print(page_path)
        return 0

    # Calendar views and excelheader require date args
    if not args.begin or not args.end:
        parser.error("START_DATE and END_DATE are required")

    # Validate date format up front so every subcommand emits a friendly
    # message instead of leaking a traceback from deep inside calc_calendar_range.
    try:
        parse_date(args.begin, "start")
        parse_date(args.end, "end")
    except InvalidDateError as e:
        parser.error(f"{e}. Dates must be in YYYYMMDD format (e.g. 20260301).")

    # excelheader — Excel workbook with timeband header rows
    if args.command == "excelheader":
        from visualizers.excelheader import generate_excel_header

        _eh_db = _open_calendar_db(args.database)
        _eh_config = create_calendar_config()
        _eh_config.weekend_style = args.weekends
        _eh_wd = getattr(args, "weekend_days", None)
        if _eh_wd:
            _eh_config.weekend_days = _parse_weekend_days(_eh_wd)
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
            Path(_to_output_dir_path(args.outputfile))
            if args.outputfile
            else Path("output") / "excelheader.xlsx"
        )
        out_path.parent.mkdir(parents=True, exist_ok=True)
        generate_excel_header(_eh_config, _eh_db, out_path)
        if not args.quiet:
            print(out_path)
        return 0

    # excelblockplan — Excel workbook with timeband header + event/duration rows
    if args.command == "excelblockplan":
        from visualizers.excelblockplan import generate_excel_blockplan

        _ebp_db = _open_calendar_db(args.database)
        _ebp_config = create_calendar_config()
        _ebp_config.weekend_style = args.weekends
        _ebp_wd = getattr(args, "weekend_days", None)
        if _ebp_wd:
            _ebp_config.weekend_days = _parse_weekend_days(_ebp_wd)
        _ebp_config.country = args.country
        _ebp_config.userstart = args.begin
        _ebp_config.userend = args.end
        # Blockplan-equivalent content filters
        _ebp_config.includeevents = not args.noevents
        _ebp_config.includedurations = not args.nodurations
        _ebp_config.ignorecomplete = args.ignorecomplete
        _ebp_config.milestones = args.milestones
        _ebp_config.rollups = args.rollups
        _ebp_config.WBS = args.WBS
        _ebp_config.status_filter = _parse_status_filter(getattr(args, "status", None))
        if args.empty:
            _ebp_config.includeevents = False
            _ebp_config.includedurations = False
            _ebp_config.ignorecomplete = True
            _ebp_config.milestones = False
        calc_calendar_range(_ebp_config, args.begin, args.end)
        _ebp_db.load_python_holidays(
            _ebp_config.country, _ebp_config.adjustedstart, _ebp_config.adjustedend
        )
        if getattr(args, "theme", None):
            from config.theme_engine import ThemeEngine

            _ebp_te = ThemeEngine()
            _ebp_te.load(args.theme)
            _ebp_te.apply(_ebp_config)
            _resolve_palette_overrides(_ebp_config, _ebp_db)
        out_path = (
            Path(_to_output_dir_path(args.outputfile))
            if args.outputfile
            else Path("output") / "ExcelBlockplan.xlsx"
        )
        out_path.parent.mkdir(parents=True, exist_ok=True)
        generate_excel_blockplan(_ebp_config, _ebp_db, out_path)
        if not args.quiet:
            print(out_path)
        return 0

    # exportdata — export filtered events/durations as import-compatible CSV
    if args.command == "exportdata":
        _ed_db = _open_calendar_db(args.database)
        _ed_config = create_calendar_config()
        _ed_config.country = args.country
        _ed_config.includeevents = not args.noevents
        _ed_config.includedurations = not args.nodurations
        _ed_config.ignorecomplete = args.ignorecomplete
        _ed_config.milestones = args.milestones
        _ed_config.rollups = args.rollups
        _ed_config.WBS = args.WBS
        _ed_config.status_filter = _parse_status_filter(getattr(args, "status", None))
        calc_calendar_range(_ed_config, args.begin, args.end)
        _ed_db.load_python_holidays(
            _ed_config.country, _ed_config.adjustedstart, _ed_config.adjustedend
        )

        from visualizers.base import filter_events

        raw_events = _ed_db.get_all_events_in_range(
            _ed_config.adjustedstart, _ed_config.adjustedend
        )
        exported = filter_events(raw_events, _ed_config)

        out_path = (
            Path(_to_output_dir_path(args.outputfile))
            if args.outputfile
            else Path("output") / f"exportdata_{_ed_config.adjustedstart}.csv"
        )
        _write_exportdata_csv(exported, out_path)
        if not args.quiet:
            print(f"Exported {len(exported)} record(s) → {out_path}")
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

        # Load government holidays from the 'holidays' Python package so all
        # renderers transparently use live package data.
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

        # Warn about SVG layout options not applicable to text-only output.
        # Options with per-view effects (--shade, --monthnames, --overflow,
        # --shrink, --weekend-days, --includenotes, --nodurations) are gated
        # at the parser level instead — a view that never reads them does not
        # accept them (docs/cli_theme_overrides.html, Appendix A).
        _svg_layout_checks = [
            ("margin", getattr(args, "margin", False), "--margin"),
            ("header", getattr(args, "header", False), "--header"),
            ("footer", getattr(args, "footer", False), "--footer"),
            ("headerleft", bool(getattr(args, "headerleft", "")), "--headerleft"),
            ("headercenter", bool(getattr(args, "headercenter", "")), "--headercenter"),
            ("headerright", bool(getattr(args, "headerright", "")), "--headerright"),
            ("footerleft", bool(getattr(args, "footerleft", "")), "--footerleft"),
            ("footercenter", bool(getattr(args, "footercenter", "")), "--footercenter"),
            ("footerright", bool(getattr(args, "footerright", "")), "--footerright"),
            (
                "watermark_text",
                bool(getattr(args, "watermark_text", "")),
                "--watermark-text",
            ),
            (
                "watermark_rotation_angle",
                getattr(args, "watermark_rotation_angle", None) is not None,
                "--watermark-rotation-angle",
            ),
            (
                "watermark_image",
                bool(getattr(args, "watermark_image", "")),
                "--watermark-image",
            ),
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
