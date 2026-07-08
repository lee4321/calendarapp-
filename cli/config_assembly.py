"""
CalendarConfig assembly from parsed CLI arguments.

Bridges argparse Namespace -> CalendarConfig: logging setup, argument
application (including the post-theme override re-application pass),
header/footer template-variable expansion, status/weekend-day parsing,
and database open/validation.
"""

from __future__ import annotations

import logging
from pathlib import Path

import arrow
from typing import TYPE_CHECKING

from cli.errors import ConfigError, DatabaseError
from config.config import CalendarConfig
from shared.db_access import CalendarDB

if TYPE_CHECKING:
    from argparse import Namespace

logger = logging.getLogger(__name__)


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
    _wd = getattr(args, "weekend_days", None)
    if _wd:
        config.weekend_days = _parse_weekend_days(_wd)

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
    # compactplan and candybar always shrink by default (candybar is a narrow
    # centered strip that otherwise leaves large blank margins); other views
    # require --shrink.
    shrink_default = getattr(args, "command", None) in ("compactplan", "candybar")
    config.shrink_to_content = getattr(args, "shrink", False) or shrink_default
    config.embed_data = getattr(args, "embed_data", False)

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
    config.status_filter = _parse_status_filter(getattr(args, "status", None))

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

    # Candybar options
    if getattr(args, "candybar_row_height", None) is not None:
        config.candybar_row_height = args.candybar_row_height
    if getattr(args, "candybar_cell_width", None) is not None:
        config.candybar_cell_width = args.candybar_cell_width
    if getattr(args, "candybar_max_rows_per_page", None) is not None:
        config.candybar_max_rows_per_page = args.candybar_max_rows_per_page
    if getattr(args, "candybar_suppress_weekends", None) is not None:
        config.candybar_suppress_weekends = args.candybar_suppress_weekends
    if getattr(args, "candybar_no_week_numbers", False):
        config.candybar_show_week_numbers = False
    if getattr(args, "candybar_month_side", None) is not None:
        config.candybar_month_label_side = args.candybar_month_side
    if getattr(args, "candybar_month_rotation", None) is not None:
        config.candybar_month_rotation = args.candybar_month_rotation
    if getattr(args, "candybar_weekend_fill", None) is not None:
        config.candybar_weekend_fill = args.candybar_weekend_fill
    if getattr(args, "candybar_month_shading", None):
        config.candybar_month_shading = True

    # Timeline today-line options
    if getattr(args, "today_line_length", None) is not None:
        config.timeline_today_line_length = args.today_line_length
    if getattr(args, "today_line_direction", None) is not None:
        config.timeline_today_line_direction = args.today_line_direction
    if getattr(args, "label_fill_opacity", None) is not None:
        config.timeline_label_fill_opacity = args.label_fill_opacity

    # PIT options
    if getattr(args, "direction", None) is not None:
        config.pit_direction = args.direction
    if getattr(args, "label_side", None) is not None:
        config.pit_label_side = args.label_side
    if getattr(args, "tick_unit", None) is not None:
        config.pit_tick_unit = args.tick_unit
    if getattr(args, "date_placement", None) is not None:
        config.pit_date_placement = args.date_placement
    if getattr(args, "tick_interval", None) is not None:
        config.pit_tick_interval = args.tick_interval
    if getattr(args, "tick_label_format", None) is not None:
        config.pit_tick_label_format = args.tick_label_format
    if getattr(args, "tick_length", None) is not None:
        config.pit_tick_length = args.tick_length
    if getattr(args, "pit_show_ticks", None) is not None:
        config.pit_show_ticks = args.pit_show_ticks
    if getattr(args, "pit_show_tick_labels", None) is not None:
        config.pit_show_tick_labels = args.pit_show_tick_labels
    if getattr(args, "pit_today_line", None) is not None:
        config.pit_show_today_line = args.pit_today_line
    if getattr(args, "today_date", None) is not None:
        config.pit_today_date = args.today_date
    if getattr(args, "today_label", None) is not None:
        config.pit_today_line_label = args.today_label
    if getattr(args, "event_icon", None) is not None:
        config.pit_default_event_icon = args.event_icon
    if getattr(args, "milestone_icon", None) is not None:
        config.pit_default_milestone_icon = args.milestone_icon
    if getattr(args, "marker_size", None) is not None:
        config.pit_marker_size = args.marker_size
    if getattr(args, "label_icon_size", None) is not None:
        config.pit_label_icon_size = args.label_icon_size
    if getattr(args, "label_icon_gap", None) is not None:
        config.pit_label_icon_gap = args.label_icon_gap
    if getattr(args, "leader_dash", None) is not None:
        config.pit_leader_stroke_dasharray = args.leader_dash
    if getattr(args, "leader_label_anchor", None) is not None:
        config.pit_leader_label_anchor = args.leader_label_anchor
    if getattr(args, "leader_length", None) is not None:
        config.pit_labella_layer_gap = args.leader_length
    if getattr(args, "leader_stub", None) is not None:
        config.pit_leader_end_stub = args.leader_stub

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
        --watermark-text        → config.watermark_text
        --watermark-rotation-angle → config.watermark_rotation_angle
        --watermark-image       → config.watermark_image

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
        ("watermark_text", "watermark_text"),
    )
    for arg_name, config_attr in template_text_fields:
        value = getattr(args, arg_name, "")
        if value:
            setattr(config, config_attr, replace_template_vars(config, value))

    if getattr(args, "watermark_rotation_angle", None) is not None:
        config.watermark_rotation_angle = float(args.watermark_rotation_angle)
    if getattr(args, "watermark_image", ""):
        config.watermark_image = replace_template_vars(config, args.watermark_image)


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
        PIT --direction / --label-side / --marker-size / --label-icon-size /
        --label-icon-gap / --today-line / --no-today-line → re-asserted over
        the theme's pit.direction / label_side / axis.marker_size /
        label.icon_size / label.icon_gap / today_line.show keys.

    Called by:
        run() immediately after the second theme_engine.apply(config) call.

    Args:
        args:   Namespace from argparse.parse_args() (checked for explicit flags).
        config: CalendarConfig instance to correct (mutated in-place).
    """
    if getattr(args, "mini_no_adjacent", False):
        config.mini_show_adjacent = False

    # PIT scalars that are now theme-configurable: an explicit CLI flag must
    # still win over the theme value the second theme.apply() restores.
    if getattr(args, "direction", None) is not None:
        config.pit_direction = args.direction
    if getattr(args, "label_side", None) is not None:
        config.pit_label_side = args.label_side
    if getattr(args, "marker_size", None) is not None:
        config.pit_marker_size = args.marker_size
    if getattr(args, "label_icon_size", None) is not None:
        config.pit_label_icon_size = args.label_icon_size
    if getattr(args, "label_icon_gap", None) is not None:
        config.pit_label_icon_gap = args.label_icon_gap
    if getattr(args, "pit_today_line", None) is not None:
        config.pit_show_today_line = args.pit_today_line


def _parse_status_filter(raw: str | None) -> "frozenset[str] | None":
    """Parse ``--status`` CLI value into the set used by ``config.status_filter``.

    ``None`` / empty / ``"all"`` → ``None`` (no filter). Otherwise a
    comma-separated list of status names (case-insensitive). Unknown values
    are rejected against :data:`shared.data_models.ALLOWED_STATUSES`.
    """
    from shared.data_models import ALLOWED_STATUSES

    if raw is None:
        return frozenset({"active"})
    cleaned = raw.strip().lower()
    if not cleaned or cleaned == "all":
        return None
    parts = [p.strip().lower() for p in cleaned.split(",") if p.strip()]
    if not parts:
        return None
    bad = [p for p in parts if p not in ALLOWED_STATUSES]
    if bad:
        raise SystemExit(
            f"--status: unknown value(s) {bad!r}. "
            f"Allowed: {sorted(ALLOWED_STATUSES)} or 'all'."
        )
    return frozenset(parts)


def _parse_weekend_days(raw: str) -> list[int]:
    """Parse ``--weekend-days`` CLI value ``"5,6"`` → ``[5, 6]``.

    Raises ``SystemExit`` via argparse-style error on malformed input.
    """
    try:
        parts = [p.strip() for p in str(raw).split(",") if p.strip()]
        days = [int(p) for p in parts]
    except ValueError as exc:
        raise SystemExit(
            f"--weekend-days: expected comma-separated ints, got {raw!r}"
        ) from exc
    for d in days:
        if d < 0 or d > 6:
            raise SystemExit(
                f"--weekend-days: each value must be 0–6 (ISO weekday), got {d}"
            )
    if len(set(days)) != len(days):
        raise SystemExit(f"--weekend-days: duplicate values in {raw!r}")
    return days


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
        patterns, patternsheet, icons, iconsheet, colors, colorsheet, palettes,
        palettesheet, excelheader, and all calendar-visualizer commands.

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

