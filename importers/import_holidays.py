#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
import_holidays.py - Import CSV government holiday files into calendar.db

Usage:
    python import_holidays.py <csv_file> [options]

Examples:
    python import_holidays.py holidays_2025.csv
    python import_holidays.py holidays_2025.csv --country US --language en
    python import_holidays.py holidays/ --verbose
    python import_holidays.py holidays_2025.csv --replace
    python import_holidays.py holidays_2025.csv --dry-run

Expected CSV columns:
    Required: name, start_date (or startdatetime)
    Optional: end_date (or enddatetime), country, subregion1, subregion2, subregion3,
              language, observed_start, observed_end, icon_id, nonworkday

Date formats supported: YYYY-MM-DD, MM/DD/YYYY, M/D/YYYY, M/D/YY
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
from typing import List, Optional
from contextlib import contextmanager

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

logger = None


def setup_logging(log_file="import_holidays.log", level="info"):
    """Configure logging to file and console."""
    return _setup_logging_common("import_holidays", log_file, level)


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
# Constants
# ============================================================================

SUPPORTED_EXTENSIONS = {".csv", ".txt"}

# Mapping: Source Column Name -> Database Column Name
# Supports multiple aliases for flexibility
COLUMN_MAPPING = {
    # Name
    "name": "displayname",
    "displayname": "displayname",
    "holiday_name": "displayname",
    "holiday": "displayname",
    # Start date
    "start_date": "startdatetime",
    "startdatetime": "startdatetime",
    "date": "startdatetime",
    "start": "startdatetime",
    # End date
    "end_date": "enddatetime",
    "enddatetime": "enddatetime",
    "end": "enddatetime",
    # Observed dates
    "observed_start": "observedstartdatetime",
    "observedstartdatetime": "observedstartdatetime",
    "observed_start_date": "observedstartdatetime",
    "observed_end": "observedenddatetime",
    "observedenddatetime": "observedenddatetime",
    "observed_end_date": "observedenddatetime",
    # Location
    "country": "country",
    "country_code": "country",
    "subregion1": "subregion1",
    "state": "subregion1",
    "province": "subregion1",
    "region": "subregion1",
    "subregion2": "subregion2",
    "county": "subregion2",
    "subregion3": "subregion3",
    "city": "subregion3",
    # Other
    "language": "language",
    "lang": "language",
    "icon_id": "displayiconid",
    "displayiconid": "displayiconid",
    "icon": "displayiconid",
    "nonworkday": "nonworkday",
    "non_work_day": "nonworkday",
    "is_nonworkday": "nonworkday",
    "day_off": "nonworkday",
}


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
    - YYYY-MM-DD (e.g., "2025-01-01")
    - M/D/YYYY (e.g., "1/1/2025")
    - M/D/YY (e.g., "1/1/25")
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


def process_dates(start_date_raw, end_date_raw):
    """
    Convert start and end dates, handling edge cases.

    - If start invalid and end valid: start = end
    - If end invalid and start valid: end = start
    - If start > end: swap them

    Returns:
        tuple: (start_date_str, end_date_str, is_valid)
    """
    start_date = convert_date(start_date_raw)
    end_date = convert_date(end_date_raw)

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


class HolidayDatabase:
    """Database manager for holiday imports."""

    def __init__(self, db_path):
        self.db_path = db_path
        self._db = CalendarDB(db_path)
        self._migrate_schema()

    def _migrate_schema(self):
        """Add any missing tables to existing databases."""
        with self._db.get_connection() as conn:
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

    def delete_holidays_by_import_id(self, cursor, import_id):
        """Delete holidays from a previous import (for --replace)."""
        # We need a way to track which holidays came from which import
        # Since government table doesn't have import_id, we'll delete by matching criteria
        # For now, we'll delete all holidays that match the file hash pattern
        # This is a limitation - consider adding import_id to government table
        cursor.execute("DELETE FROM government WHERE id IN (SELECT id FROM government)")
        return cursor.rowcount

    def delete_import_record(self, cursor, import_id):
        """Delete import_history record."""
        cursor.execute(
            """
            DELETE FROM import_history WHERE id = ?
        """,
            (import_id,),
        )

    def get_next_holiday_id(self, cursor):
        """Get next available holiday ID."""
        cursor.execute("SELECT COALESCE(MAX(id), 0) + 1 FROM government")
        return cursor.fetchone()[0]

    def insert_holiday(self, cursor, holiday_data):
        """Insert single holiday record."""
        columns = ", ".join(holiday_data.keys())
        placeholders = ", ".join(["?" for _ in holiday_data])

        sql = f"INSERT INTO government ({columns}) VALUES ({placeholders})"
        cursor.execute(sql, list(holiday_data.values()))
        return cursor.lastrowid

    def get_holiday_count(self, cursor):
        """Get total number of holidays in database."""
        cursor.execute("SELECT COUNT(*) FROM government")
        return cursor.fetchone()[0]

    def clear_all_holidays(self, cursor):
        """Delete all holidays from the government table."""
        cursor.execute("DELETE FROM government")
        return cursor.rowcount


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
    if ext in {".csv", ".txt"}:
        return "csv"
    return None


def read_file(filepath):
    """Read CSV file into DataFrame."""
    file_type = determine_file_type(filepath)
    if file_type != "csv":
        raise ValueError(f"Unsupported file type: {filepath}")

    df = pandas.read_csv(filepath)

    # Normalize column names: strip whitespace and convert to lowercase
    df.columns = df.columns.str.strip().str.lower()
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
# Row Processing
# ============================================================================


def normalize_column_name(col_name):
    """Normalize column name for matching."""
    return col_name.strip().lower().replace(" ", "_").replace("-", "_")


def get_row_value(row, possible_columns):
    """Get value from row trying multiple possible column names."""
    for col in possible_columns:
        normalized = normalize_column_name(col)
        if normalized in row:
            return row[normalized]
    return None


def transform_row(row, default_country, default_language, holiday_id):
    """
    Transform DataFrame row to database record.

    Args:
        row: Dict of row data from DataFrame
        default_country: Default country code if not in row
        default_language: Default language code if not in row
        holiday_id: ID for this holiday

    Returns:
        tuple: (holiday_dict, error_message) - error_message is None if successful
    """
    # Get display name (required)
    displayname = get_row_value(row, ["name", "displayname", "holiday_name", "holiday"])
    if not displayname or pandas.isnull(displayname) or not str(displayname).strip():
        return None, "Holiday name is required"

    # Get start date (required)
    start_raw = get_row_value(row, ["start_date", "startdatetime", "date", "start"])
    end_raw = get_row_value(row, ["end_date", "enddatetime", "end"])

    start_date, end_date, dates_valid = process_dates(start_raw, end_raw)

    if not dates_valid:
        return None, "Invalid or missing start date"

    # Get country (use default if not specified)
    country = get_row_value(row, ["country", "country_code"])
    if not country or pandas.isnull(country) or not str(country).strip():
        country = default_country

    # Get subregions
    subregion1 = get_row_value(row, ["subregion1", "state", "province", "region"])
    if subregion1 and not pandas.isnull(subregion1):
        subregion1 = str(subregion1).strip()
    else:
        subregion1 = ""  # Required field, use empty string

    subregion2 = get_row_value(row, ["subregion2", "county"])
    if subregion2 and not pandas.isnull(subregion2):
        subregion2 = str(subregion2).strip()
    else:
        subregion2 = None

    subregion3 = get_row_value(row, ["subregion3", "city"])
    if subregion3 and not pandas.isnull(subregion3):
        subregion3 = str(subregion3).strip()
    else:
        subregion3 = None

    # Get language (use default if not specified)
    language = get_row_value(row, ["language", "lang"])
    if not language or pandas.isnull(language) or not str(language).strip():
        language = default_language

    # Get observed dates (optional)
    observed_start_raw = get_row_value(
        row, ["observed_start", "observedstartdatetime", "observed_start_date"]
    )
    observed_end_raw = get_row_value(
        row, ["observed_end", "observedenddatetime", "observed_end_date"]
    )
    observed_start = convert_date(observed_start_raw) if observed_start_raw else None
    observed_end = convert_date(observed_end_raw) if observed_end_raw else None

    # Get icon ID (optional)
    icon_id = get_row_value(row, ["icon_id", "displayiconid", "icon"])
    if icon_id and not pandas.isnull(icon_id):
        try:
            icon_id = int(icon_id)
        except (ValueError, TypeError):
            icon_id = None
    else:
        icon_id = None

    # Get nonworkday flag (default to 1 for holidays)
    nonworkday = get_row_value(
        row, ["nonworkday", "non_work_day", "is_nonworkday", "day_off"]
    )
    if nonworkday is not None and not pandas.isnull(nonworkday):
        # Handle various boolean representations
        if isinstance(nonworkday, bool):
            nonworkday = 1 if nonworkday else 0
        elif str(nonworkday).strip().lower() in ("true", "yes", "1", "y"):
            nonworkday = 1
        elif str(nonworkday).strip().lower() in ("false", "no", "0", "n"):
            nonworkday = 0
        else:
            try:
                nonworkday = int(nonworkday)
            except (ValueError, TypeError):
                nonworkday = 1  # Default: holidays are non-work days
    else:
        nonworkday = 1  # Default: holidays are non-work days

    # Build holiday record
    holiday = {
        "id": holiday_id,
        "country": str(country).strip().upper(),
        "subregion1": subregion1,
        "language": str(language).strip().lower(),
        "startdatetime": start_date,
        "enddatetime": end_date,
        "displayname": str(displayname).strip(),
        "nonworkday": nonworkday,
    }

    # Add optional fields if present
    if subregion2:
        holiday["subregion2"] = subregion2
    if subregion3:
        holiday["subregion3"] = subregion3
    if observed_start:
        holiday["observedstartdatetime"] = observed_start
    if observed_end:
        holiday["observedenddatetime"] = observed_end
    if icon_id:
        holiday["displayiconid"] = icon_id

    return holiday, None


# ============================================================================
# Import Logic
# ============================================================================


def import_file(
    db,
    filepath,
    default_country,
    default_language,
    replace=False,
    verbose=False,
    skip_errors=False,
    command=None,
):
    """
    Import a single CSV file into database.

    Args:
        db: HolidayDatabase instance
        filepath: Path to file to import
        default_country: Default country code for holidays
        default_language: Default language code for holidays
        replace: If True, clear existing holidays before importing
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
        log(f"  Columns found: {', '.join(df.columns)}")

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

        if replace:
            # Clear all existing holidays when replacing
            deleted = db.clear_all_holidays(cursor)
            if verbose:
                log(f"  Cleared {deleted} existing holidays")

            # Also delete the old import record if it exists
            if existing:
                db.delete_import_record(cursor, existing[0])

        # Create import history record
        import_id = db.create_import_record(
            cursor, "system", filepath, file_hash, command=command
        )
        result.import_id = import_id

        if verbose:
            log(f"  Created import record (id={import_id})")

        # Get starting holiday ID
        next_holiday_id = db.get_next_holiday_id(cursor)

        # Process each row
        for idx, row in df.iterrows():
            holiday, error = transform_row(
                row.to_dict(), default_country, default_language, next_holiday_id
            )

            if error:
                result.failed_rows += 1
                if verbose:
                    log(f"  Row {idx + 1}: {error}", "warning")
                if not skip_errors:
                    result.errors.append(f"Row {idx + 1}: {error}")
                continue

            try:
                db.insert_holiday(cursor, holiday)
                result.imported_rows += 1
                next_holiday_id += 1

                if verbose and result.imported_rows % 50 == 0:
                    log(f"  Imported {result.imported_rows} holidays...")

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
        prog="import_holidays",
        description="Import CSV government holiday files into calendar.db",
    )

    parser.add_argument("files", nargs="*", help="CSV files or directories to import")
    parser.add_argument(
        "--database",
        "-db",
        default="calendar.db",
        help="Path to SQLite database (default: calendar.db)",
    )
    parser.add_argument(
        "--country",
        "-c",
        default="US",
        help="Default country code for holidays (default: US)",
    )
    parser.add_argument(
        "--language",
        "-lang",
        default="en",
        help="Default language code for holidays (default: en)",
    )
    parser.add_argument(
        "--replace",
        "-r",
        action="store_true",
        help="Clear existing holidays and re-import",
    )
    parser.add_argument(
        "--dry-run",
        "-n",
        action="store_true",
        help="Validate files without importing",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Show detailed progress",
    )
    parser.add_argument(
        "--skip-errors",
        action="store_true",
        help="Continue importing when individual rows fail",
    )
    parser.add_argument(
        "--list",
        "-l",
        action="store_true",
        help="List current holidays in database",
    )
    parser.add_argument(
        "--clear",
        action="store_true",
        help="Clear all holidays from database",
    )

    # Logging options
    parser.add_argument(
        "--log-file",
        default="import_holidays.log",
        help="Path to log file (default: import_holidays.log)",
    )
    parser.add_argument(
        "--log-level",
        choices=["debug", "info", "warning", "error"],
        default="info",
        help="Set logging level (default: info)",
    )

    args = parser.parse_args()

    # Setup logging
    global logger
    log_level = "debug" if args.verbose else args.log_level
    logger = setup_logging(args.log_file, log_level)

    command_line = shlex.join(sys.argv)
    log("=== import_holidays.py started ===")
    log(f"Command: {command_line}")
    log(f"Database: {args.database}")

    # Verify database exists
    if not os.path.exists(args.database):
        log(f"Error: Database not found: {args.database}", "error")
        sys.exit(1)

    db = HolidayDatabase(args.database)

    # Handle --list
    if args.list:
        with db.transaction() as cursor:
            cursor.execute("""
                SELECT country, COUNT(*) as count, MIN(startdatetime) as earliest, MAX(enddatetime) as latest
                FROM government
                GROUP BY country
                ORDER BY country
            """)
            results = cursor.fetchall()

            if not results:
                log("No holidays found in database.")
            else:
                log("\nHolidays in database:")
                log(
                    f"  {'Country':<10}  {'Count':>6}  {'Earliest':<10}  {'Latest':<10}"
                )
                log(f"  {'-' * 10}  {'-' * 6}  {'-' * 10}  {'-' * 10}")
                total = 0
                for row in results:
                    country, count, earliest, latest = row
                    log(f"  {country:<10}  {count:>6}  {earliest:<10}  {latest:<10}")
                    total += count
                log(f"\nTotal: {total} holidays")

        log("=== import_holidays.py completed ===")
        sys.exit(0)

    # Handle --clear
    if args.clear:
        response = input("Are you sure you want to delete ALL holidays? [y/N]: ")
        if response.lower() != "y":
            log("Cancelled.")
            sys.exit(0)

        with db.transaction() as cursor:
            deleted = db.clear_all_holidays(cursor)
            log(f"Deleted {deleted} holidays.")

        log("=== import_holidays.py completed ===")
        sys.exit(0)

    # Require files for import operation
    if not args.files:
        parser.error(
            "CSV files are required for import. Use --list to view holidays or --clear to delete all."
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
    log(f"Default country: {args.country}")
    log(f"Default language: {args.language}")

    # Handle dry-run mode
    if args.dry_run:
        log("\n=== DRY RUN - No changes will be made ===\n")
        for filepath in all_files:
            try:
                df = read_file(filepath)
                log(f"  {os.path.basename(filepath)}: {len(df)} rows")
                log(f"    Columns: {', '.join(df.columns)}")

                # Check for required columns
                has_name = any(
                    col in df.columns
                    for col in ["name", "displayname", "holiday_name", "holiday"]
                )
                has_date = any(
                    col in df.columns
                    for col in ["start_date", "startdatetime", "date", "start"]
                )

                if not has_name:
                    log(
                        "    WARNING: Missing required column: name (or displayname, holiday_name)",
                        "warning",
                    )
                if not has_date:
                    log(
                        "    WARNING: Missing required column: start_date (or startdatetime, date)",
                        "warning",
                    )

                # Show sample data
                if len(df) > 0:
                    log(f"    Sample: {df.iloc[0].to_dict()}")

            except Exception as e:
                log(f"  {os.path.basename(filepath)}: ERROR - {e}", "error")

        log("=== import_holidays.py completed ===")
        sys.exit(0)

    # Import files
    total_imported = 0
    total_failed = 0

    for filepath in all_files:
        log(f"\nImporting: {os.path.basename(filepath)}")
        result = import_file(
            db,
            filepath,
            args.country,
            args.language,
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
    log("=== import_holidays.py completed ===")

    sys.exit(0 if total_failed == 0 else 1)


if __name__ == "__main__":
    main()
