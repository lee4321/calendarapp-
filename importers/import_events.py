#!/usr/bin/env python
"""
import_events.py - Import XLSX/CSV event files into calendar.db

Usage:
    python import_events.py <file_or_directory> [options]
    python import_events.py --generate <script.py> [options]
    python import_events.py --generate <script.py> --start-date DATE --end-date DATE [options]

Examples:
    python import_events.py Events/PI7.xlsx
    python import_events.py Events/ --verbose
    python import_events.py Events/PI7.csv --replace
    python import_events.py Events/ --dry-run
    python import_events.py --generate my_generator.py --verbose
    python import_events.py -g my_generator.py --replace --dry-run
    python import_events.py -g my_generator.py --start-date 1/1/2026 --end-date 12/31/2026
    python import_events.py -g my_generator.py --param Priority=1 --param Icon=rocket
    python import_events.py -g my_generator.py --start-date 2026-06-01 --end-date 2026-06-30 --param Tags=Sprint
"""

import argparse
import importlib.util
import inspect
import os
import re
import sqlite3
import sys

# Ensure project root is on sys.path when run as a script
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas

from importers.common import (
    ImportDatabase as _ImportDatabaseBase,
)
from importers.common import (
    ImportLog,
    ImportResult,
    add_history_and_log_arguments,
    add_import_arguments,
    coerce_source_text,
    collect_import_files,
    compute_file_hash,
    convert_date,
    convert_datetime,
    finish_import_run,
    handle_history_commands,
    log_import_result,
    log_import_totals,
    process_datetimes,
    read_file,
    start_import_run,
)
from shared.duration_parser import normalize_decimal_separators, parse_duration

# ============================================================================
# Logging
# ============================================================================

log = ImportLog()


# ============================================================================
# Constants
# ============================================================================

SUPPORTED_EXTENSIONS = {".xlsx", ".xls", ".csv", ".txt"}

# Mapping: Source Column Name -> Database Column Name.
#
# Keys are written here in readable snake_case but matched through
# _canon() below, which strips case, spaces, underscores, hyphens, dots
# and percent signs.  One entry therefore covers every spelling of a
# name: "early_start", "EarlyStart", "Early Start" and "earlystart" all
# resolve together.  First match per DB column wins.
COLUMN_MAPPING = {
    # Task name.  NOTE: "summary" is deliberately absent here -- in the
    # schedule data-element vocabulary Summary is the rollup flag, not
    # the task name.  It is mapped to "rollup" further down.
    "task_name": "name",
    "name": "name",
    "title": "name",
    "task": "name",
    # Source-system identifier (GUID or integer from the scheduling
    # tool).  Distinct from events.id, which is our own autoincrement
    # key; predecessors/successors reference these values.
    "id": "source_id",
    "guid": "source_id",
    "task_id": "source_id",
    "uid": "source_id",
    "unique_id": "source_id",
    "source_id": "source_id",
    # Start date
    "start_date": "start_date",
    "start": "start_date",
    "begin": "start_date",
    "begin_date": "start_date",
    "date": "start_date",
    # End / finish date
    "finish_date": "end_date",
    "finish": "end_date",
    "end_date": "end_date",
    "end": "end_date",
    "due": "end_date",
    "due_date": "end_date",
    # Earliest / latest start date (schedule windows)
    "earliest_start_date": "earliest_start_date",
    "earliest_start": "earliest_start_date",
    "early_start": "earliest_start_date",
    "es_date": "earliest_start_date",
    "latest_start_date": "latest_start_date",
    "latest_start": "latest_start_date",
    "late_start": "latest_start_date",
    "ls_date": "latest_start_date",
    # Earliest / latest end (finish) date
    "earliest_end_date": "earliest_end_date",
    "earliest_end": "earliest_end_date",
    "earliest_finish_date": "earliest_end_date",
    "earliest_finish": "earliest_end_date",
    "early_finish": "earliest_end_date",
    "ef_date": "earliest_end_date",
    "latest_end_date": "latest_end_date",
    "latest_end": "latest_end_date",
    "latest_finish_date": "latest_end_date",
    "latest_finish": "latest_end_date",
    "late_finish": "latest_end_date",
    "lf_date": "latest_end_date",
    # Status
    "status": "status",
    "state": "status",
    # Priority
    "priority": "priority",
    # WBS
    "wbs": "wbs",
    # Rollup (a.k.a. Summary task)
    "rollup": "rollup",
    "summary": "rollup",
    # Milestone
    "milestone": "milestone",
    # Critical path
    "critical": "critical",
    # Percent complete
    "percent_complete": "percent_complete",
    "complete": "percent_complete",
    "% complete": "percent_complete",
    # Percent work (effort) complete
    "percent_work_complete": "percent_work_complete",
    "% work complete": "percent_work_complete",
    # Effort
    "effort": "effort",
    "work": "effort",
    # Duration
    "duration": "duration",
    # Actual start / finish
    "actual_start": "actual_start_date",
    "actual_start_date": "actual_start_date",
    "actual_finish": "actual_end_date",
    "actual_end": "actual_end_date",
    "actual_finish_date": "actual_end_date",
    "actual_end_date": "actual_end_date",
    # Deadline
    "deadline": "deadline",
    # Schedule variances (signed duration strings, e.g. "-4h")
    "start_variance": "start_variance",
    "finish_variance": "finish_variance",
    "end_variance": "finish_variance",
    # Costs
    "cost": "cost",
    "fixed_cost": "fixed_cost",
    # Predecessors / successors
    "predecessors": "predecessors",
    "predecessor": "predecessors",
    "successors": "successors",
    "successor": "successors",
    # Resource names
    "resource_names": "resource_names",
    "resource_name": "resource_names",
    "resources": "resource_names",
    "resource": "resource_names",
    "assigned_to": "resource_names",
    # Resource group
    "resource_group": "resource_group",
    "resource_groups": "resource_group",
    "group": "resource_group",
    "team": "resource_group",
    "department": "resource_group",
    # Notes
    "notes": "notes",
    "description": "notes",
    "note": "notes",
    # Icon
    "icon": "icon",
    # Color
    "highlight_color": "color",
    "color": "color",
    "colour": "color",
    # Tags
    "tags": "tags",
    "tag": "tags",
    "marks": "tags",
    "mark": "tags",
    # Free-form custom fields.  No length limit -- concatenate any extra
    # source-system fields into these to drive selection and styling.
    "custom1": "custom1",
    "custom2": "custom2",
    "custom3": "custom3",
    "custom4": "custom4",
    "custom5": "custom5",
}


# ============================================================================
# Row Normalization
# ============================================================================

#: Punctuation and whitespace removed before alias lookup.
_CANON_STRIP_RE = re.compile(r"[\s_\-.%]+")


def _canon(name) -> str:
    """Reduce a column name to its comparison form (see COLUMN_MAPPING)."""
    return _CANON_STRIP_RE.sub("", str(name).strip().lower())


def _build_canonical_mapping() -> dict:
    """Canonicalize COLUMN_MAPPING keys, rejecting genuine conflicts.

    Two spellings of the same name collapsing to one key is expected and
    harmless.  Two *different* names collapsing onto conflicting DB
    columns is a bug in the table above, so it fails loudly at import.
    """
    canonical: dict = {}
    for source_name, db_col in COLUMN_MAPPING.items():
        key = _canon(source_name)
        existing = canonical.get(key)
        if existing is not None and existing != db_col:
            raise ValueError(
                f"COLUMN_MAPPING conflict: '{source_name}' canonicalizes to "
                f"'{key}', which already maps to '{existing}' (not '{db_col}')"
            )
        canonical[key] = db_col
    return canonical


#: COLUMN_MAPPING keyed by _canon() form -- the dict actually consulted.
CANONICAL_COLUMN_MAPPING = _build_canonical_mapping()


def lookup_column(source_name) -> str | None:
    """Resolve a source column name to its DB column, or None."""
    return CANONICAL_COLUMN_MAPPING.get(_canon(source_name))


def normalize_row(row: dict) -> dict:
    """Map source column names to DB column names using COLUMN_MAPPING.

    Column names are matched ignoring case, spaces, underscores, hyphens,
    dots and percent signs.  When multiple source columns resolve to the
    same DB column the first one encountered wins.

    Args:
        row: Dict of raw column_name → value from a DataFrame row.

    Returns:
        Dict of db_column_name → value for all recognized columns.
    """
    normalized: dict = {}
    for src_col, value in row.items():
        db_col = lookup_column(src_col)
        if db_col is not None:
            normalized.setdefault(db_col, value)
    return normalized


# ============================================================================
# Database Operations
# ============================================================================


class ImportDatabase(_ImportDatabaseBase):
    """Events importer database (rows land in the ``events`` table).

    All bookkeeping (import_history, id sequence, dedup, removal) comes
    from importers.common.ImportDatabase.

    The `events` schema migration is not applied here: this class holds a
    CalendarDB, and CalendarDB migrates on connect -- so opening the
    database for writing and for reading go through the same code.  See
    :mod:`shared.events_schema`.
    """

    ROW_TABLE = "events"
    UNIT_LABEL = "events"


# ============================================================================
# Generator Script Loading
# ============================================================================


def load_generator_script(script_path):
    """
    Dynamically load a Python script and return its generate_events function.

    The script must define a generate_events() function that returns a
    pandas DataFrame with Title_Case column names matching the CSV import
    contract (e.g., Task_Name, Start_Date, Finish_Date, Priority, etc.).

    Args:
        script_path: Path to the Python script

    Returns:
        callable: The generate_events function from the script

    Raises:
        FileNotFoundError: If script doesn't exist
        ValueError: If script doesn't define generate_events()
    """
    script_path = os.path.abspath(script_path)

    if not os.path.isfile(script_path):
        raise FileNotFoundError(f"Generator script not found: {script_path}")

    if not script_path.endswith(".py"):
        raise ValueError(f"Generator script must be a .py file: {script_path}")

    module_name = os.path.splitext(os.path.basename(script_path))[0]
    spec = importlib.util.spec_from_file_location(module_name, script_path)
    if spec is None or spec.loader is None:
        raise ValueError(f"Cannot load generator script: {script_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    if not hasattr(module, "generate_events"):
        raise ValueError(f"Generator script must define a generate_events() function: {script_path}")

    if not callable(module.generate_events):
        raise ValueError(f"generate_events must be callable in: {script_path}")

    return module.generate_events


def call_generate_fn(generate_fn, **kwargs):
    """
    Call a generate_events function, optionally passing keyword arguments.

    Uses inspect to determine whether the function accepts parameters.
    If kwargs are provided but the function doesn't accept them, raises ValueError.
    If kwargs are not provided, calls with no arguments (backward compatible).

    Args:
        generate_fn: The generate_events callable loaded from a script
        **kwargs: Keyword arguments to pass (e.g., start_date, end_date, Priority, Icon)

    Returns:
        pandas.DataFrame: The generated events

    Raises:
        ValueError: If kwargs are provided but function can't accept them,
                    or if function requires parameters but none were provided
    """
    sig = inspect.signature(generate_fn)
    params = sig.parameters

    # Check if function accepts **kwargs (VAR_KEYWORD)
    has_var_keyword = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values())

    if kwargs:
        if len(params) == 0:
            raise ValueError(
                "Generator's generate_events() accepts no parameters, "
                f"but these were provided: {', '.join(kwargs.keys())}. "
                "Update the generator to accept keyword arguments."
            )
        return generate_fn(**kwargs)
    else:
        # No kwargs provided - check if function has required parameters
        if len(params) > 0 and not has_var_keyword:
            required_params = [
                name
                for name, p in params.items()
                if p.default is inspect.Parameter.empty
                and p.kind not in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD)
            ]
            if required_params:
                raise ValueError(
                    f"Generator's generate_events() requires parameters "
                    f"({', '.join(required_params)}), but none were provided. "
                    f"Use --start-date/--end-date or --param to pass values."
                )
        return generate_fn()


def import_generated_events(
    db,
    script_path,
    user_id,
    replace=False,
    verbose=False,
    skip_errors=False,
    generator_kwargs=None,
    command=None,
):
    """
    Import events from a generator script into database.

    Loads the script, calls its generate_events() function, and processes
    the returned DataFrame through the same transform_row() pipeline as
    file imports.

    Args:
        db: ImportDatabase instance
        script_path: Path to Python script with generate_events() function
        user_id: User ID for the import
        replace: If True, replace existing events from same script
        verbose: If True, print detailed progress
        skip_errors: If True, continue importing when individual rows fail
        generator_kwargs: Optional dict of keyword arguments to pass to generate_events()
        command: Command line string used to invoke the import

    Returns:
        ImportResult: Summary of import operation
    """
    if generator_kwargs is None:
        generator_kwargs = {}
    result = ImportResult(filename=script_path)

    # Compute script hash for duplicate detection
    script_hash = compute_file_hash(script_path)

    # Load the generator script
    try:
        generate_fn = load_generator_script(script_path)
    except (FileNotFoundError, ValueError) as e:
        result.errors.append(str(e))
        log(f"  {e}", "error")
        return result

    # Call the generator function to get a DataFrame
    try:
        df = call_generate_fn(generate_fn, **generator_kwargs)
    except Exception as e:
        result.errors.append(f"Generator script failed: {e}")
        log(f"  Generator script failed: {e}", "error")
        return result

    # Validate the returned value is a DataFrame
    if not isinstance(df, pandas.DataFrame):
        msg = f"generate_events() must return a pandas DataFrame, got {type(df).__name__}"
        result.errors.append(msg)
        log(f"  {msg}", "error")
        return result

    if df.empty:
        msg = "generate_events() returned an empty DataFrame"
        result.errors.append(msg)
        log(f"  {msg}", "warning")
        return result

    # Strip whitespace from column names (matching read_file behavior)
    df.columns = df.columns.str.strip()

    result.total_rows = len(df)

    if verbose:
        log(f"  Generated {result.total_rows} rows from {os.path.basename(script_path)}")
        log(f"  Columns: {', '.join(df.columns)}")

    # Import with transaction (same pattern as import_file)
    with db.transaction() as cursor:
        # Check for duplicate import
        existing = db.check_duplicate(cursor, script_hash)
        if existing and not replace:
            msg = f"Script already imported (id={existing[0]}, filename={existing[1]}). Use --replace to re-import."
            result.errors.append(msg)
            if verbose:
                log(f"  SKIPPED: {msg}", "warning")
            return result

        if existing and replace:
            deleted = db.delete_by_import_id(cursor, existing[0])
            db.delete_import_record(cursor, existing[0])
            if verbose:
                log(f"  Deleted {deleted} existing events from previous import")

        # Create import history record
        import_id = db.create_import_record(cursor, user_id, script_path, script_hash, command=command)
        result.import_id = import_id

        if verbose:
            log(f"  Created import record (id={import_id})")

        # Get starting event ID
        next_event_id = db.get_next_row_id(cursor)

        # Process each row through the same transform_row pipeline
        for idx, row in df.iterrows():
            event, error = transform_row(row.to_dict(), user_id, import_id, next_event_id)

            if error:
                result.failed_rows += 1
                if verbose:
                    log(f"  Row {idx + 1}: {error}", "error")
                if not skip_errors:
                    result.errors.append(f"Row {idx + 1}: {error}")
                continue

            try:
                db.insert_row(cursor, event)
                result.imported_rows += 1
                next_event_id += 1
            except sqlite3.Error as e:
                result.failed_rows += 1
                if verbose:
                    log(f"  Row {idx + 1}: Database error: {e}", "error")
                if not skip_errors:
                    result.errors.append(f"Row {idx + 1}: {e}")

    return result


# ============================================================================
# Row Processing
# ============================================================================


#: Schedule-window columns stored as a bare YYYYMMDD date.  The source
#: may carry a time; nothing reads these at sub-day resolution, so it is
#: dropped rather than spend a column per field on it.
_DATE_ONLY_COLS = frozenset(
    {
        "earliest_start_date",
        "latest_start_date",
        "earliest_end_date",
        "latest_end_date",
        "deadline",
    }
)

#: Date columns that keep their time component in a companion column.
_DATETIME_COLS = {
    "actual_start_date": "actual_start_time",
    "actual_end_date": "actual_end_time",
}

#: Text durations parsed into decimal days, keeping the source string.
_DURATION_COLS = {"duration": "duration_text", "effort": "effort_text"}

_BOOLEAN_COLS = frozenset({"rollup", "milestone", "critical"})
_CURRENCY_COLS = frozenset({"cost", "fixed_cost"})
_FRACTION_COLS = frozenset({"percent_complete", "percent_work_complete"})

_TRUE_VALUES = frozenset({"TRUE", "T", "1", "YES", "Y"})

#: Stripped from currency values once separators are resolved.  Commas
#: are handled by normalize_decimal_separators, not removed blindly --
#: "1,5" is one and a half, not fifteen.
_CURRENCY_NOISE_RE = re.compile(r"[$£€¥,\s]")


def _is_blank(value) -> bool:
    """True for None, NaN/NaT, and whitespace-only values."""
    return not (pandas.notna(value) and str(value).strip())


def _to_currency(value) -> float | None:
    """Parse a currency cell ('$250.00', '(1,200)') to a float."""
    if _is_blank(value):
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)

    text = _CURRENCY_NOISE_RE.sub("", normalize_decimal_separators(str(value).strip()))
    negative = text.startswith("(") and text.endswith(")")
    if negative:
        text = text[1:-1]
    try:
        amount = float(text)
    except ValueError:
        return None
    return -amount if negative else amount


def _to_fraction(value) -> float:
    """Parse a completion cell to a 0.0-1.0 fraction.

    Both conventions appear in the wild, so accept either: values above 1
    are read as percentages ('85' -> 0.85), values at or below 1 are
    already fractions ('0.85', '1.0').
    """
    if _is_blank(value):
        return 0.0
    try:
        number = float(str(value).strip().rstrip("%"))
    except (ValueError, TypeError):
        return 0.0
    return number / 100.0 if number > 1.0 else number


def transform_row(row, user_id, import_id, event_id):
    """
    Transform DataFrame row to database record.

    Args:
        row: Dict of row data from DataFrame
        user_id: User ID for the import
        import_id: Import history ID
        event_id: ID for this event

    Returns:
        tuple: (event_dict, error_message) - error_message is None if successful
    """
    # Normalize column names (case-insensitive, alias-aware)
    norm = normalize_row(row)

    # Process dates first, keeping any YYYYMMDDTHHMM time component
    start_date, start_time, end_date, end_time, dates_valid = process_datetimes(
        norm.get("start_date"), norm.get("end_date")
    )

    if not dates_valid:
        return None, "Invalid or missing dates"

    # Build event record with required fields
    event = {
        "id": event_id,
        "user_id": user_id,
        "import_id": import_id,
        "status": "active",
        "start_date": start_date,
        "start_time": start_time,
        "end_date": end_date,
        "end_time": end_time,
    }

    # Map remaining normalized columns with type coercions
    for db_col, value in norm.items():
        if db_col in ("start_date", "end_date"):
            continue  # Already handled

        if db_col == "priority":
            try:
                value = int(value) if not _is_blank(value) else 0
            except (ValueError, TypeError):
                value = 0
        elif db_col in _BOOLEAN_COLS:
            value = 1 if str(value).strip().upper() in _TRUE_VALUES else 0
        elif db_col in _FRACTION_COLS:
            value = _to_fraction(value)
        elif db_col in _CURRENCY_COLS:
            value = _to_currency(value)
        elif db_col in _DURATION_COLS:
            # Keep the source string verbatim; store decimal days alongside.
            raw = coerce_source_text(value)
            event[_DURATION_COLS[db_col]] = raw
            value = parse_duration(raw)
        elif db_col in _DATETIME_COLS:
            value, time_part = convert_datetime(value)
            event[_DATETIME_COLS[db_col]] = time_part
        elif db_col in _DATE_ONLY_COLS:
            value = convert_date(value)
        else:
            # String fields - handle NaN and pandas' numeric coercion
            value = coerce_source_text(value)

        event[db_col] = value

    # status falls back to "active" when source value is missing/blank
    if event.get("status") is None:
        event["status"] = "active"

    # Validate required fields
    if not event.get("name") or not str(event["name"]).strip():
        return None, "Task_Name is required"

    return event, None


# ============================================================================
# Import History Management
# ============================================================================


# ============================================================================
# Import Logic
# ============================================================================


def import_file(db, filepath, user_id, replace=False, verbose=False, skip_errors=False, command=None):
    """
    Import a single file into database.

    Args:
        db: ImportDatabase instance
        filepath: Path to file to import
        user_id: User ID for the import
        replace: If True, replace existing events from same file
        verbose: If True, print detailed progress
        skip_errors: If True, continue importing when individual rows fail
        command: Command line string used to invoke the import

    Returns:
        ImportResult: Summary of import operation
    """
    result = ImportResult(filename=filepath)

    # Compute file hash for duplicate detection
    file_hash = compute_file_hash(filepath)

    # Read file into DataFrame
    try:
        df = read_file(filepath)
        result.total_rows = len(df)
    except Exception as e:
        result.errors.append(f"Failed to read file: {e}")
        log(f"  Failed to read file: {e}", "error")
        return result

    if verbose:
        log(f"  Read {result.total_rows} rows from {os.path.basename(filepath)}")

    # Import with transaction
    with db.transaction() as cursor:
        # Check for duplicate import
        existing = db.check_duplicate(cursor, file_hash)
        if existing and not replace:
            msg = f"File already imported (id={existing[0]}, filename={existing[1]}). Use --replace to re-import."
            result.errors.append(msg)
            if verbose:
                log(f"  SKIPPED: {msg}", "warning")
            return result

        if existing and replace:
            deleted = db.delete_by_import_id(cursor, existing[0])
            db.delete_import_record(cursor, existing[0])
            if verbose:
                log(f"  Deleted {deleted} existing events from previous import")

        # Create import history record
        import_id = db.create_import_record(cursor, user_id, filepath, file_hash, command=command)
        result.import_id = import_id

        if verbose:
            log(f"  Created import record (id={import_id})")

        # Get starting event ID
        next_event_id = db.get_next_row_id(cursor)

        # Process each row
        for idx, row in df.iterrows():
            event, error = transform_row(row.to_dict(), user_id, import_id, next_event_id)

            if error:
                result.failed_rows += 1
                if verbose:
                    log(f"  Row {idx + 1}: {error}", "error")
                if not skip_errors:
                    result.errors.append(f"Row {idx + 1}: {error}")
                continue

            try:
                db.insert_row(cursor, event)
                result.imported_rows += 1
                next_event_id += 1
            except sqlite3.Error as e:
                result.failed_rows += 1
                if verbose:
                    log(f"  Row {idx + 1}: Database error: {e}", "error")
                if not skip_errors:
                    result.errors.append(f"Row {idx + 1}: {e}")

    return result


# ============================================================================
# Main
# ============================================================================


def main():
    parser = argparse.ArgumentParser(prog="import_events", description="Import XLSX/CSV event files into calendar.db")
    add_import_arguments(parser, "events")

    # Generator option
    parser.add_argument(
        "--generate",
        "-g",
        type=str,
        metavar="SCRIPT",
        help="Path to Python script with generate_events() function that returns a DataFrame",
    )

    # Generator parameter options
    parser.add_argument(
        "--start-date",
        type=str,
        metavar="DATE",
        help="Start date for generator scripts (any parseable format, e.g., 2026-01-01, 1/1/2026)",
    )
    parser.add_argument(
        "--end-date",
        type=str,
        metavar="DATE",
        help="End date for generator scripts (any parseable format, e.g., 2026-12-31, 12/31/2026)",
    )
    parser.add_argument(
        "--param",
        "-p",
        action="append",
        metavar="KEY=VALUE",
        help="Pass parameter to generator script (repeatable, e.g., --param Priority=1 --param Icon=rocket)",
    )
    add_history_and_log_arguments(parser, "import_events.log")

    args = parser.parse_args()

    # Validate generator-related options (--start-date, --end-date, --param)
    generator_kwargs = {}

    if (args.start_date or args.end_date or args.param) and not args.generate:
        parser.error("--start-date, --end-date, and --param can only be used with --generate")

    if args.start_date or args.end_date:
        if bool(args.start_date) != bool(args.end_date):
            parser.error("--start-date and --end-date must be used together")

        start_date_yyyymmdd = convert_date(args.start_date)
        if start_date_yyyymmdd is None:
            parser.error(f"Invalid --start-date: {args.start_date}")

        end_date_yyyymmdd = convert_date(args.end_date)
        if end_date_yyyymmdd is None:
            parser.error(f"Invalid --end-date: {args.end_date}")

        if start_date_yyyymmdd > end_date_yyyymmdd:
            parser.error(
                f"--start-date ({args.start_date} -> {start_date_yyyymmdd}) must be "
                f"before --end-date ({args.end_date} -> {end_date_yyyymmdd})"
            )

        generator_kwargs["start_date"] = start_date_yyyymmdd
        generator_kwargs["end_date"] = end_date_yyyymmdd

    if args.param:
        for param_str in args.param:
            if "=" not in param_str:
                parser.error(f"Invalid --param format: '{param_str}'. Expected KEY=VALUE")
            key, value = param_str.split("=", 1)
            key = key.strip()
            if not key:
                parser.error(f"Invalid --param: empty key in '{param_str}'")
            generator_kwargs[key] = value.strip()

    command_line = start_import_run(args, log, "import_events")
    db = ImportDatabase(args.database)
    handle_history_commands(args, db, log, "import_events")

    # Handle --generate
    if args.generate:
        script_path = args.generate

        if args.dry_run:
            log("\n=== DRY RUN (Generator) - No changes will be made ===\n")
            if generator_kwargs:
                log(f"  Parameters: {generator_kwargs}")
            try:
                generate_fn = load_generator_script(script_path)
                df = call_generate_fn(generate_fn, **generator_kwargs)
                if isinstance(df, pandas.DataFrame):
                    log(f"  Script: {os.path.basename(script_path)}")
                    log(f"  Generated: {len(df)} rows")
                    log(f"  Columns: {', '.join(df.columns)}")

                    # Check for required columns (case-insensitive via COLUMN_MAPPING)
                    norm_cols = {lookup_column(c) for c in df.columns}
                    missing = []
                    if "name" not in norm_cols:
                        missing.append("Task_Name (or equivalent)")
                    if "start_date" not in norm_cols and "end_date" not in norm_cols:
                        missing.append("Start_Date or Finish_Date (or equivalent)")
                    if missing:
                        log(
                            f"  WARNING: Missing required columns: {', '.join(missing)}",
                            "warning",
                        )

                    # Show sample rows
                    if len(df) > 0 and args.verbose:
                        log(f"  Sample row: {df.iloc[0].to_dict()}")
                else:
                    log(
                        f"  ERROR: generate_events() returned {type(df).__name__}, expected DataFrame",
                        "error",
                    )
            except Exception as e:
                log(f"  ERROR: {e}", "error")

            finish_import_run(log, "import_events", 0)

        # Perform the actual import
        log(f"\nGenerating events from: {os.path.basename(script_path)}")
        if generator_kwargs:
            log(f"  Parameters: {generator_kwargs}")
        result = import_generated_events(
            db,
            script_path,
            args.user_id,
            replace=args.replace,
            verbose=args.verbose,
            skip_errors=args.skip_errors,
            generator_kwargs=generator_kwargs,
            command=command_line,
        )
        log_import_result(result, args.verbose, log)
        log_import_totals("Generate", result.imported_rows, result.failed_rows, log)
        finish_import_run(log, "import_events", 0 if result.failed_rows == 0 else 1)

    # Require files for import operation
    if not args.files:
        parser.error(
            "Files are required for import. Use --list to view imports, --remove ID to delete, "
            "or --generate SCRIPT to generate events."
        )

    all_files = collect_import_files(args.files, log)

    # Handle dry-run mode
    if args.dry_run:
        log("\n=== DRY RUN - No changes will be made ===\n")
        for filepath in all_files:
            try:
                df = read_file(filepath)
                log(f"  {os.path.basename(filepath)}: {len(df)} rows")
                log(f"    Columns: {', '.join(df.columns[:5])}...")

                # Check for required columns (case-insensitive via COLUMN_MAPPING)
                norm_cols = {lookup_column(c) for c in df.columns}
                missing = []
                if "name" not in norm_cols:
                    missing.append("Task_Name (or equivalent)")
                if "start_date" not in norm_cols and "end_date" not in norm_cols:
                    missing.append("Start_Date or Finish_Date (or equivalent)")

                if missing:
                    log(
                        f"    WARNING: Missing required columns: {', '.join(missing)}",
                        "warning",
                    )

            except Exception as e:
                log(f"  {os.path.basename(filepath)}: ERROR - {e}", "error")
        finish_import_run(log, "import_events", 0)

    # Import files
    total_imported = 0
    total_failed = 0

    for filepath in all_files:
        log(f"\nImporting: {os.path.basename(filepath)}")
        result = import_file(
            db,
            filepath,
            args.user_id,
            replace=args.replace,
            verbose=args.verbose,
            skip_errors=args.skip_errors,
            command=command_line,
        )
        log_import_result(result, args.verbose, log)
        total_imported += result.imported_rows
        total_failed += result.failed_rows

    log_import_totals("Import", total_imported, total_failed, log)
    finish_import_run(log, "import_events", 0 if total_failed == 0 else 1)


if __name__ == "__main__":
    main()
