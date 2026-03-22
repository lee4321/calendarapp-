#!/usr/bin/env python
# -*- coding: utf-8 -*-
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
    python import_events.py -g my_generator.py --start-date 2026-06-01 --end-date 2026-06-30 --param Marks=Sprint
"""

import argparse
import sys
import os
import sqlite3
import hashlib
import logging
import shlex
from datetime import datetime
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from contextlib import contextmanager
import importlib.util
import inspect

# Ensure project root is on sys.path when run as a script
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas
from dateutil.parser import parse as dateutil_parse
import arrow

from shared.db_access import CalendarDB
from importers.common import setup_logging as _setup_logging_common


# ============================================================================
# Logging
# ============================================================================

# Global logger instance
logger = None


def setup_logging(log_file="import_events.log", level="info"):
    """Configure logging to file and console."""
    return _setup_logging_common("import_events", log_file, level)


def log(message, level="info"):
    """Log message at specified level."""
    if logger is None:
        print(message)
        return
    level_map = {
        "debug": logger.debug,
        "info": logger.info,
        "warning": logger.warning,
        "error": logger.error,
    }
    level_map.get(level, logger.info)(message)


# ============================================================================
# Pattern Parsing
# ============================================================================


def parse_import_pattern(pattern, max_id):
    """
    Parse import ID pattern and return list of IDs to remove.

    Args:
        pattern: String pattern (e.g., "3", "1-5", "1,3,5", "all", "5-", "-3")
        max_id: Maximum import ID in database

    Returns:
        list: List of import IDs to remove

    Raises:
        ValueError: If pattern is invalid
    """
    pattern = pattern.strip().lower()

    # Handle "all"
    if pattern == "all":
        return list(range(1, max_id + 1))

    # Handle comma-separated list: "1,3,5"
    if "," in pattern:
        try:
            ids = [int(x.strip()) for x in pattern.split(",")]
            return sorted(set(ids))  # Remove duplicates, sort
        except ValueError:
            raise ValueError(f"Invalid ID list: {pattern}")

    # Handle range: "1-5", "5-", "-3"
    if "-" in pattern:
        parts = pattern.split("-", 1)

        # Open-ended range: "5-" (from 5 to max)
        if parts[1] == "":
            try:
                start = int(parts[0])
                return list(range(start, max_id + 1))
            except ValueError:
                raise ValueError(f"Invalid range start: {pattern}")

        # Open-start range: "-3" (from 1 to 3)
        if parts[0] == "":
            try:
                end = int(parts[1])
                return list(range(1, end + 1))
            except ValueError:
                raise ValueError(f"Invalid range end: {pattern}")

        # Full range: "1-5"
        try:
            start = int(parts[0])
            end = int(parts[1])
            if start > end:
                start, end = end, start  # Swap if reversed
            return list(range(start, end + 1))
        except ValueError:
            raise ValueError(f"Invalid range: {pattern}")

    # Handle single ID: "3"
    try:
        return [int(pattern)]
    except ValueError:
        raise ValueError(f"Invalid import ID pattern: {pattern}")


# ============================================================================
# Constants
# ============================================================================

SUPPORTED_EXTENSIONS = {".xlsx", ".xls", ".csv", ".txt"}

# Mapping: Source Column Name (lowercase) -> Database Column Name
# Keys are matched case-insensitively; first match per DB column wins.
COLUMN_MAPPING = {
    # Task name
    "task_name": "name",
    "name": "name",
    "title": "name",
    "task": "name",
    "summary": "name",
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
    # Priority
    "priority": "priority",
    # WBS
    "wbs": "wbs",
    # Rollup
    "rollup": "rollup",
    # Milestone
    "milestone": "milestone",
    # Percent complete
    "percent_complete": "percent_complete",
    "complete": "percent_complete",
    "% complete": "percent_complete",
    # Effort
    "effort": "effort",
    # Duration
    "duration": "duration",
    # Predecessors
    "predecessors": "predecessors",
    "predecessor": "predecessors",
    # Resource names
    "resource_names": "resource_names",
    "resource_name": "resource_names",
    "resources": "resource_names",
    "resource": "resource_names",
    "assigned_to": "resource_names",
    # Resource group
    "resource_group": "resource_group",
    "group": "resource_group",
    "team": "resource_group",
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
    # Marks / tags
    "marks": "marks",
    "mark": "marks",
    "tags": "marks",
    "tag": "marks",
}


# ============================================================================
# Row Normalization
# ============================================================================


def normalize_row(row: dict) -> dict:
    """Map source column names to DB column names using COLUMN_MAPPING.

    Column names are matched case-insensitively.  When multiple source columns
    resolve to the same DB column the first one encountered wins.

    Args:
        row: Dict of raw column_name → value from a DataFrame row.

    Returns:
        Dict of db_column_name → value for all recognized columns.
    """
    normalized: dict = {}
    for src_col, value in row.items():
        db_col = COLUMN_MAPPING.get(str(src_col).strip().lower())
        if db_col is not None:
            normalized.setdefault(db_col, value)
    return normalized


# ============================================================================
# Data Classes
# ============================================================================


@dataclass
class ImportResult:
    """Result of importing a file."""

    filename: str
    total_rows: int = 0
    imported_rows: int = 0
    failed_rows: int = 0
    errors: List[str] = field(default_factory=list)
    import_id: Optional[int] = None


# ============================================================================
# Date Conversion Functions
# ============================================================================


def convert_date(date_value, target_format="YYYYMMDD"):
    """
    Convert date from various formats to YYYYMMDD.

    Handles:
    - M/D/YYYY (e.g., "7/5/2019")
    - M/D/YY (e.g., "9/4/19")
    - Empty/NaN values

    Args:
        date_value: Input date string or pandas NaT/NaN
        target_format: Arrow format string (default: YYYYMMDD)

    Returns:
        str: Formatted date string or None if invalid
    """
    if pandas.isnull(date_value) or not str(date_value).strip():
        return None

    date_str = str(date_value).strip()

    try:
        parsed_date = dateutil_parse(date_str)

        # Check for invalid dates (year 1900 indicates parsing failure)
        if parsed_date.year < 1950:
            return None

        arrow_date = arrow.Arrow.fromdatetime(parsed_date)
        return arrow_date.format(target_format)

    except (ValueError, TypeError):
        return None


def process_dates(start_date_raw, finish_date_raw):
    """
    Convert start and finish dates, handling edge cases.

    - If start invalid and end valid: start = end
    - If start > end: swap them

    Returns:
        tuple: (start_date_str, end_date_str, is_valid)
    """
    start_date = convert_date(start_date_raw)
    end_date = convert_date(finish_date_raw)

    # Both invalid
    if start_date is None and end_date is None:
        return None, None, False

    # Start invalid, end valid: use end for both
    if start_date is None and end_date is not None:
        return end_date, end_date, True

    # End invalid, start valid: use start for both
    if start_date is not None and end_date is None:
        return start_date, start_date, True

    # Both valid: ensure start <= end
    if start_date > end_date:
        start_date, end_date = end_date, start_date

    return start_date, end_date, True


# ============================================================================
# Database Operations
# ============================================================================


class ImportDatabase:
    """Database manager for event imports."""

    def __init__(self, db_path):
        self.db_path = db_path
        self._db = CalendarDB(db_path)
        self._migrate_schema()

    def _migrate_schema(self):
        """Add any missing columns/tables to existing databases."""
        with self._db.get_connection() as conn:
            try:
                conn.execute("ALTER TABLE import_history ADD COLUMN command TEXT")
                conn.commit()
            except sqlite3.OperationalError:
                pass  # Column already exists
            conn.execute(
                "CREATE TABLE IF NOT EXISTS import_sequence (next_id INTEGER NOT NULL)"
            )
            cursor = conn.execute("SELECT COUNT(*) FROM import_sequence")
            if cursor.fetchone()[0] == 0:
                cursor = conn.execute(
                    "SELECT COALESCE(MAX(id), 0) + 1 FROM import_history"
                )
                next_id = cursor.fetchone()[0]
                conn.execute(
                    "INSERT INTO import_sequence (next_id) VALUES (?)", (next_id,)
                )
            conn.commit()

    @contextmanager
    def transaction(self):
        """Context manager for transactional operations."""
        with self._db.get_connection() as conn:
            cursor = conn.cursor()
            try:
                yield cursor
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    def get_next_import_id(self, cursor):
        """Get next available import history ID (never reuses IDs)."""
        cursor.execute("SELECT next_id FROM import_sequence")
        next_id = cursor.fetchone()[0]
        cursor.execute("UPDATE import_sequence SET next_id = ?", (next_id + 1,))
        return next_id

    def create_import_record(self, cursor, user_id, filename, file_hash, command=None):
        """Create import_history record and return import_id."""
        import_id = self.get_next_import_id(cursor)
        cursor.execute(
            """
            INSERT INTO import_history (id, userid, filename, date, filehash, command)
            VALUES (?, ?, ?, ?, ?, ?)
        """,
            (
                import_id,
                str(user_id),
                os.path.basename(filename),
                datetime.now().isoformat(),
                file_hash,
                command,
            ),
        )
        return import_id

    def check_duplicate(self, cursor, file_hash):
        """Check if file has been imported before (by hash)."""
        cursor.execute(
            """
            SELECT id, filename FROM import_history
            WHERE filehash = ?
        """,
            (file_hash,),
        )
        return cursor.fetchone()

    def delete_by_import_id(self, cursor, import_id):
        """Delete events from a previous import (for --replace)."""
        cursor.execute(
            """
            DELETE FROM events WHERE import_id = ?
        """,
            (import_id,),
        )
        return cursor.rowcount

    def delete_import_record(self, cursor, import_id):
        """Delete import_history record."""
        cursor.execute(
            """
            DELETE FROM import_history WHERE id = ?
        """,
            (import_id,),
        )

    def get_max_import_id(self, cursor):
        """Get the maximum import ID."""
        cursor.execute("SELECT COALESCE(MAX(id), 0) FROM import_history")
        return cursor.fetchone()[0]

    def get_next_event_id(self, cursor):
        """Get next available event ID."""
        cursor.execute("SELECT COALESCE(MAX(id), 0) + 1 FROM events")
        return cursor.fetchone()[0]

    def insert_event(self, cursor, event_data):
        """Insert single event record."""
        columns = ", ".join(event_data.keys())
        placeholders = ", ".join(["?" for _ in event_data])

        sql = f"INSERT INTO events ({columns}) VALUES ({placeholders})"
        cursor.execute(sql, list(event_data.values()))
        return cursor.lastrowid

    def list_imports(self, cursor):
        """Get all import history records with event counts."""
        cursor.execute("""
            SELECT
                ih.id,
                ih.userid,
                ih.filename,
                ih.date,
                ih.filehash,
                COUNT(e.id) as event_count,
                ih.command
            FROM import_history ih
            LEFT JOIN events e ON e.import_id = ih.id
            GROUP BY ih.id
            ORDER BY ih.id
        """)
        return cursor.fetchall()

    def get_import_by_id(self, cursor, import_id):
        """Get single import record with event count."""
        cursor.execute(
            """
            SELECT
                ih.id,
                ih.userid,
                ih.filename,
                ih.date,
                ih.filehash,
                COUNT(e.id) as event_count,
                ih.command
            FROM import_history ih
            LEFT JOIN events e ON e.import_id = ih.id
            WHERE ih.id = ?
            GROUP BY ih.id
        """,
            (import_id,),
        )
        return cursor.fetchone()


# ============================================================================
# File Operations
# ============================================================================


def compute_file_hash(filepath):
    """Compute SHA256 hash of entire file contents."""
    sha256 = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def determine_file_type(filename):
    """Determine file type from extension."""
    ext = os.path.splitext(filename)[1].lower()
    if ext in {".xlsx", ".xls"}:
        return "excel"
    elif ext in {".csv", ".txt"}:
        return "csv"
    return None


def read_file(filepath):
    """Read file into DataFrame."""
    file_type = determine_file_type(filepath)
    if file_type == "excel":
        df = pandas.read_excel(filepath)
    elif file_type == "csv":
        df = pandas.read_csv(filepath)
    else:
        raise ValueError(f"Unsupported file type: {filepath}")

    # Strip whitespace from column names (some XLSX files have trailing spaces)
    df.columns = df.columns.str.strip()
    return df


def find_files(path):
    """Find all importable files in path (file or directory)."""
    if os.path.isfile(path):
        if determine_file_type(path):
            return [path]
        return []

    if os.path.isdir(path):
        files = []
        for f in os.listdir(path):
            full_path = os.path.join(path, f)
            if os.path.isfile(full_path) and determine_file_type(full_path):
                files.append(full_path)
        return sorted(files)

    return []


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
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    if not hasattr(module, "generate_events"):
        raise ValueError(
            f"Generator script must define a generate_events() function: {script_path}"
        )

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
    has_var_keyword = any(
        p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values()
    )

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
                and p.kind
                not in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD)
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
        msg = (
            f"generate_events() must return a pandas DataFrame, got {type(df).__name__}"
        )
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
        log(
            f"  Generated {result.total_rows} rows from {os.path.basename(script_path)}"
        )
        log(f"  Columns: {', '.join(df.columns)}")

    # Import with transaction (same pattern as import_file)
    with db.transaction() as cursor:
        # Check for duplicate import
        existing = db.check_duplicate(cursor, script_hash)
        if existing and not replace:
            msg = (
                f"Script already imported (id={existing[0]}, filename={existing[1]}). "
                "Use --replace to re-import."
            )
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
        import_id = db.create_import_record(
            cursor, user_id, script_path, script_hash, command=command
        )
        result.import_id = import_id

        if verbose:
            log(f"  Created import record (id={import_id})")

        # Get starting event ID
        next_event_id = db.get_next_event_id(cursor)

        # Process each row through the same transform_row pipeline
        for idx, row in df.iterrows():
            event, error = transform_row(
                row.to_dict(), user_id, import_id, next_event_id
            )

            if error:
                result.failed_rows += 1
                if verbose:
                    log(f"  Row {idx + 1}: {error}", "error")
                if not skip_errors:
                    result.errors.append(f"Row {idx + 1}: {error}")
                continue

            try:
                db.insert_event(cursor, event)
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

    # Process dates first
    start_date, end_date, dates_valid = process_dates(
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
        "end_date": end_date,
    }

    # Map remaining normalized columns with type coercions
    for db_col, value in norm.items():
        if db_col in ("start_date", "end_date"):
            continue  # Already handled

        if db_col == "priority":
            try:
                value = int(value) if pandas.notna(value) and str(value).strip() else 0
            except (ValueError, TypeError):
                value = 0
        elif db_col in ("rollup", "milestone"):
            value = 1 if str(value).strip().upper() in ("TRUE", "1", "YES") else 0
        elif db_col == "percent_complete":
            try:
                value = (
                    float(value) if pandas.notna(value) and str(value).strip() else 0.0
                )
            except (ValueError, TypeError):
                value = 0.0
        elif db_col in ("effort", "duration"):
            try:
                value = (
                    float(value) if pandas.notna(value) and str(value).strip() else None
                )
            except (ValueError, TypeError):
                value = None
        else:
            # String fields - handle NaN
            value = (
                str(value).strip()
                if pandas.notna(value) and str(value).strip()
                else None
            )

        event[db_col] = value

    # Validate required fields
    if not event.get("name") or not str(event["name"]).strip():
        return None, "Task_Name is required"

    return event, None


# ============================================================================
# Import History Management
# ============================================================================


def list_import_history(db):
    """List all imports from import_history table."""
    with db.transaction() as cursor:
        imports = db.list_imports(cursor)

        if not imports:
            log("No imports found.")
            return

        # Print header
        log("\nImport History:")
        log(
            f"  {'ID':>4}  {'Filename':<20}  {'Date':<19}  {'Events':>6}  {'Hash (first 8)':<14}  {'Command'}"
        )
        log(
            f"  {'--':>4}  {'-' * 20}  {'-' * 19}  {'------':>6}  {'-' * 14}  {'-' * 50}"
        )

        total_events = 0
        for row in imports:
            import_id, userid, filename, date, filehash, event_count, command = row
            # Truncate filename if too long
            display_name = (
                filename[:20] if len(filename) <= 20 else filename[:17] + "..."
            )
            # Format date (remove microseconds)
            display_date = date[:19] if date else ""
            # Show first 8 chars of hash
            short_hash = filehash[:8] if filehash else ""
            # Truncate command if too long
            display_command = ""
            if command:
                display_command = (
                    command if len(command) <= 50 else command[:47] + "..."
                )

            log(
                f"  {import_id:>4}  {display_name:<20}  {display_date:<19}  {event_count:>6}  {short_hash:<14}  {display_command}"
            )
            total_events += event_count

        log(f"\nTotal: {len(imports)} imports, {total_events} events")


def remove_import(db, import_id, force=False, verbose=False):
    """Remove an import and all its associated events."""
    # First, get import details (outside transaction for user confirmation)
    with db.transaction() as cursor:
        import_record = db.get_import_by_id(cursor, import_id)

    if not import_record:
        log(f"Error: Import ID {import_id} not found.", "error")
        return False

    _, userid, filename, date, _, event_count, _ = import_record

    # Confirm unless --force
    if not force:
        display_date = date[:19] if date else ""
        log(
            f"Import ID {import_id}: {filename} ({event_count} events, imported {display_date})"
        )
        response = input(
            "Are you sure you want to delete this import and all its events? [y/N]: "
        )
        if response.lower() != "y":
            log("Cancelled.")
            return False

    # Perform deletion in transaction
    with db.transaction() as cursor:
        if verbose:
            log(f"Removing import ID {import_id} ({filename})...")

        # Delete events
        deleted_events = db.delete_by_import_id(cursor, import_id)
        if verbose:
            log(f"  Deleted {deleted_events} events")

        # Delete import record
        db.delete_import_record(cursor, import_id)
        if verbose:
            log(f"  Deleted import history record")

    log(f"Removed import {import_id}: {filename} ({deleted_events} events deleted)")
    return True


# ============================================================================
# Import Logic
# ============================================================================


def import_file(
    db, filepath, user_id, replace=False, verbose=False, skip_errors=False, command=None
):
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
            msg = (
                f"File already imported (id={existing[0]}, filename={existing[1]}). "
                "Use --replace to re-import."
            )
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
        import_id = db.create_import_record(
            cursor, user_id, filepath, file_hash, command=command
        )
        result.import_id = import_id

        if verbose:
            log(f"  Created import record (id={import_id})")

        # Get starting event ID
        next_event_id = db.get_next_event_id(cursor)

        # Process each row
        for idx, row in df.iterrows():
            event, error = transform_row(
                row.to_dict(), user_id, import_id, next_event_id
            )

            if error:
                result.failed_rows += 1
                if verbose:
                    log(f"  Row {idx + 1}: {error}", "error")
                if not skip_errors:
                    result.errors.append(f"Row {idx + 1}: {error}")
                continue

            try:
                db.insert_event(cursor, event)
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
    parser = argparse.ArgumentParser(
        prog="import_events", description="Import XLSX/CSV event files into calendar.db"
    )

    # Make files optional (not required for --list or --remove)
    parser.add_argument("files", nargs="*", help="Files or directories to import")
    parser.add_argument(
        "--database",
        "-db",
        default="calendar.db",
        help="Path to SQLite database (default: calendar.db)",
    )
    parser.add_argument(
        "--user-id",
        "-u",
        type=int,
        default=1,
        help="User ID for imported events (default: 1)",
    )
    parser.add_argument(
        "--replace",
        "-r",
        action="store_true",
        help="Replace events from previously imported file",
    )
    parser.add_argument(
        "--dry-run", "-n", action="store_true", help="Validate files without importing"
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Show detailed progress"
    )
    parser.add_argument(
        "--skip-errors",
        action="store_true",
        help="Continue importing when individual rows fail",
    )

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

    # Import history management options
    parser.add_argument(
        "--list",
        "-l",
        action="store_true",
        help="List all previous imports from import_history",
    )
    parser.add_argument(
        "--remove",
        "-rm",
        type=str,
        metavar="PATTERN",
        help='Remove imports by ID. Supports: single (3), range (1-5), list (1,3,5), open range (5- or -3), or "all"',
    )
    parser.add_argument(
        "--force",
        "-f",
        action="store_true",
        help="Skip confirmation prompt when removing",
    )

    # Logging options
    parser.add_argument(
        "--log-file",
        default="import_events.log",
        help="Path to log file (default: import_events.log)",
    )
    parser.add_argument(
        "--log-level",
        choices=["debug", "info", "warning", "error"],
        default="info",
        help="Set logging level (default: info)",
    )

    args = parser.parse_args()

    # Validate generator-related options (--start-date, --end-date, --param)
    generator_kwargs = {}

    if (args.start_date or args.end_date or args.param) and not args.generate:
        parser.error(
            "--start-date, --end-date, and --param can only be used with --generate"
        )

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
                parser.error(
                    f"Invalid --param format: '{param_str}'. Expected KEY=VALUE"
                )
            key, value = param_str.split("=", 1)
            key = key.strip()
            if not key:
                parser.error(f"Invalid --param: empty key in '{param_str}'")
            generator_kwargs[key] = value.strip()

    # Setup logging
    # --verbose is shorthand for --log-level debug
    global logger
    log_level = "debug" if args.verbose else args.log_level
    logger = setup_logging(args.log_file, log_level)

    command_line = shlex.join(sys.argv)
    log("=== import_events.py started ===")
    log(f"Command: {command_line}")
    log(f"Database: {args.database}")

    # Verify database exists
    if not os.path.exists(args.database):
        log(f"Error: Database not found: {args.database}", "error")
        sys.exit(1)

    db = ImportDatabase(args.database)

    # Handle --list
    if args.list:
        list_import_history(db)
        log("=== import_events.py completed ===")
        sys.exit(0)

    # Handle --remove
    if args.remove is not None:
        # Get max import ID for pattern parsing
        with db.transaction() as cursor:
            max_id = db.get_max_import_id(cursor)

        if max_id == 0:
            log("No imports found to remove.", "warning")
            log("=== import_events.py completed ===")
            sys.exit(0)

        # Parse the pattern
        try:
            import_ids = parse_import_pattern(args.remove, max_id)
        except ValueError as e:
            log(f"Error: {e}", "error")
            log("=== import_events.py completed ===")
            sys.exit(1)

        # Filter to only existing IDs
        with db.transaction() as cursor:
            existing_ids = []
            for import_id in import_ids:
                if db.get_import_by_id(cursor, import_id):
                    existing_ids.append(import_id)

        if not existing_ids:
            log(f"No matching imports found for pattern: {args.remove}", "warning")
            log("=== import_events.py completed ===")
            sys.exit(0)

        # Show summary and confirm
        log(f"Found {len(existing_ids)} import(s) to remove: {existing_ids}")

        if not args.force:
            # Show details for each import
            with db.transaction() as cursor:
                total_events = 0
                for import_id in existing_ids:
                    record = db.get_import_by_id(cursor, import_id)
                    if record:
                        _, _, filename, date, _, event_count, _ = record
                        display_date = date[:19] if date else ""
                        log(
                            f"  ID {import_id}: {filename} ({event_count} events, {display_date})"
                        )
                        total_events += event_count
                log(f"  Total: {total_events} events will be deleted")

            response = input(
                "Are you sure you want to delete these imports and all their events? [y/N]: "
            )
            if response.lower() != "y":
                log("Cancelled.")
                log("=== import_events.py completed ===")
                sys.exit(0)

        # Perform deletions
        success_count = 0
        fail_count = 0
        for import_id in existing_ids:
            # Use force=True since we already confirmed
            if remove_import(db, import_id, force=True, verbose=args.verbose):
                success_count += 1
            else:
                fail_count += 1

        log(f"\nRemoved {success_count} import(s), {fail_count} failed")
        log("=== import_events.py completed ===")
        sys.exit(0 if fail_count == 0 else 1)

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
                    norm_cols = {
                        COLUMN_MAPPING.get(c.strip().lower()) for c in df.columns
                    }
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

            log("=== import_events.py completed ===")
            sys.exit(0)

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

        log(f"  Result: {result.imported_rows}/{result.total_rows} imported")
        if result.failed_rows:
            log(f"  Failed: {result.failed_rows} rows", "warning")
        if result.errors and not args.verbose:
            for err in result.errors[:3]:
                log(f"  Error: {err}", "error")
            if len(result.errors) > 3:
                log(f"  ... and {len(result.errors) - 3} more errors", "error")

        log(f"\n=== Generate Complete ===")
        log(f"Total imported: {result.imported_rows}")
        log(f"Total failed: {result.failed_rows}")
        log("=== import_events.py completed ===")

        sys.exit(0 if result.failed_rows == 0 else 1)

    # Require files for import operation
    if not args.files:
        parser.error(
            "Files are required for import. Use --list to view imports, --remove ID to delete, "
            "or --generate SCRIPT to generate events."
        )

    # Find all files to import
    all_files = []
    for path in args.files:
        files = find_files(path)
        if not files:
            log(f"Warning: No importable files found: {path}", "warning")
        all_files.extend(files)

    if not all_files:
        log("Error: No files to import", "error")
        sys.exit(1)

    log(f"Found {len(all_files)} file(s) to import")

    # Handle dry-run mode
    if args.dry_run:
        log("\n=== DRY RUN - No changes will be made ===\n")
        for filepath in all_files:
            try:
                df = read_file(filepath)
                log(f"  {os.path.basename(filepath)}: {len(df)} rows")
                log(f"    Columns: {', '.join(df.columns[:5])}...")

                # Check for required columns (case-insensitive via COLUMN_MAPPING)
                norm_cols = {COLUMN_MAPPING.get(c.strip().lower()) for c in df.columns}
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
        log("=== import_events.py completed ===")
        sys.exit(0)

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

        log(f"  Result: {result.imported_rows}/{result.total_rows} imported")
        if result.failed_rows:
            log(f"  Failed: {result.failed_rows} rows", "warning")
        if result.errors and not args.verbose:
            for err in result.errors[:3]:
                log(f"  Error: {err}", "error")
            if len(result.errors) > 3:
                log(f"  ... and {len(result.errors) - 3} more errors", "error")

        total_imported += result.imported_rows
        total_failed += result.failed_rows

    log(f"\n=== Import Complete ===")
    log(f"Total imported: {total_imported}")
    log(f"Total failed: {total_failed}")
    log("=== import_events.py completed ===")

    sys.exit(0 if total_failed == 0 else 1)


if __name__ == "__main__":
    main()
