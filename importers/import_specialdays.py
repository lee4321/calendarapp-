#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
import_specialdays.py - Import XLSX/CSV company special-day files into calendar.db

Usage:
    python import_specialdays.py <file_or_directory> [options]

Examples:
    python import_specialdays.py SpecialDays/company.xlsx
    python import_specialdays.py SpecialDays/ --verbose
    python import_specialdays.py SpecialDays/company.csv --replace
    python import_specialdays.py SpecialDays/ --dry-run
    python import_specialdays.py --list
    python import_specialdays.py --remove 5

Expected columns (case-insensitive, many aliases accepted):
    Required: name, start_date (or end_date)
    Optional: end_date, company, user, country, language, notes, icon,
              nonworkday, fullday, starthour, endhour, tags, daycolor,
              visible, pattern, patterncolor

Date formats supported: YYYY-MM-DD, MM/DD/YYYY, M/D/YYYY, M/D/YY
"""

import argparse
import sys
import os
import sqlite3
import hashlib
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


def setup_logging(log_file="import_specialdays.log", level="info"):
    """Configure logging to file and console."""
    return _setup_logging_common("import_specialdays", log_file, level)


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
# Import-ID Pattern Parsing (mirrors import_events.py)
# ============================================================================


def parse_import_pattern(pattern, max_id):
    """Parse import ID pattern (single, list, range, open range, "all")."""
    pattern = pattern.strip().lower()

    if pattern == "all":
        return list(range(1, max_id + 1))

    if "," in pattern:
        try:
            ids = [int(x.strip()) for x in pattern.split(",")]
            return sorted(set(ids))
        except ValueError:
            raise ValueError(f"Invalid ID list: {pattern}")

    if "-" in pattern:
        parts = pattern.split("-", 1)
        if parts[1] == "":
            try:
                return list(range(int(parts[0]), max_id + 1))
            except ValueError:
                raise ValueError(f"Invalid range start: {pattern}")
        if parts[0] == "":
            try:
                return list(range(1, int(parts[1]) + 1))
            except ValueError:
                raise ValueError(f"Invalid range end: {pattern}")
        try:
            start, end = int(parts[0]), int(parts[1])
            if start > end:
                start, end = end, start
            return list(range(start, end + 1))
        except ValueError:
            raise ValueError(f"Invalid range: {pattern}")

    try:
        return [int(pattern)]
    except ValueError:
        raise ValueError(f"Invalid import ID pattern: {pattern}")


# ============================================================================
# Constants
# ============================================================================

SUPPORTED_EXTENSIONS = {".xlsx", ".xls", ".csv", ".txt"}

# Mapping: Source Column Name (lowercase) -> Database Column Name
COLUMN_MAPPING = {
    # Name
    "name": "name",
    "title": "name",
    "special_day": "name",
    "specialday": "name",
    "holiday": "name",
    "event": "name",
    # Company / user
    "company": "company",
    "org": "company",
    "organization": "company",
    "user": "user",
    "userid": "user",
    "user_id": "user",
    "owner": "user",
    # Country / language
    "country": "country",
    "country_code": "country",
    "language": "language",
    "lang": "language",
    # Start date
    "start_date": "startdate",
    "startdate": "startdate",
    "start": "startdate",
    "begin": "startdate",
    "begin_date": "startdate",
    "date": "startdate",
    # End date
    "end_date": "enddate",
    "enddate": "enddate",
    "end": "enddate",
    "finish": "enddate",
    "finish_date": "enddate",
    "due": "enddate",
    "due_date": "enddate",
    # Notes
    "notes": "notes",
    "note": "notes",
    "description": "notes",
    # Icon
    "icon": "icon",
    "icon_name": "icon",
    # Nonworkday flag
    "nonworkday": "nonworkday",
    "non_work_day": "nonworkday",
    "is_nonworkday": "nonworkday",
    "day_off": "nonworkday",
    # Fullday flag
    "fullday": "fullday",
    "full_day": "fullday",
    "all_day": "fullday",
    # Hours
    "starthour": "starthour",
    "start_hour": "starthour",
    "start_time": "starthour",
    "endhour": "endhour",
    "end_hour": "endhour",
    "end_time": "endhour",
    # Tags
    "tags": "tags",
    "tag": "tags",
    "marks": "tags",
    "mark": "tags",
    # Day color
    "daycolor": "daycolor",
    "day_color": "daycolor",
    "color": "daycolor",
    "colour": "daycolor",
    "highlight_color": "daycolor",
    # Visible flag
    "visible": "visible",
    "is_visible": "visible",
    "show": "visible",
    # Pattern
    "pattern": "pattern",
    "pattern_id": "pattern",
    "patterncolor": "patterncolor",
    "pattern_color": "patterncolor",
}


# ============================================================================
# Row Normalization
# ============================================================================


def normalize_row(row: dict) -> dict:
    """Map source column names to DB column names (case-insensitive, first wins)."""
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
# Date Conversion
# ============================================================================


def convert_date(date_value, target_format="YYYYMMDD"):
    """Convert date from various formats to YYYYMMDD."""
    if pandas.isnull(date_value) or not str(date_value).strip():
        return None

    date_str = str(date_value).strip()
    try:
        parsed_date = dateutil_parse(date_str)
        if parsed_date.year < 1950:
            return None
        return arrow.Arrow.fromdatetime(parsed_date).format(target_format)
    except (ValueError, TypeError):
        return None


def process_dates(start_raw, end_raw):
    """Convert start and end dates, filling missing side from the other."""
    start_date = convert_date(start_raw)
    end_date = convert_date(end_raw)

    if start_date is None and end_date is None:
        return None, None, False
    if start_date is None:
        return end_date, end_date, True
    if end_date is None:
        return start_date, start_date, True
    if start_date > end_date:
        start_date, end_date = end_date, start_date
    return start_date, end_date, True


def parse_bool(value, default=0):
    """Parse a boolean-ish value into 0/1."""
    if value is None or (not isinstance(value, bool) and pandas.isnull(value)):
        return default
    if isinstance(value, bool):
        return 1 if value else 0
    s = str(value).strip().lower()
    if s == "":
        return default
    if s in ("true", "yes", "y", "1", "t"):
        return 1
    if s in ("false", "no", "n", "0", "f"):
        return 0
    try:
        return 1 if int(float(s)) != 0 else 0
    except (ValueError, TypeError):
        return default


# ============================================================================
# Database Operations
# ============================================================================


class SpecialDaysDatabase:
    """Database manager for special-day imports."""

    def __init__(self, db_path):
        self.db_path = db_path
        self._db = CalendarDB(db_path)
        self._migrate_schema()

    def _migrate_schema(self):
        """Add any missing columns/tables to existing databases."""
        with self._db.get_connection() as conn:
            # Ensure import_history.command exists (events importer also does this)
            try:
                conn.execute("ALTER TABLE import_history ADD COLUMN command TEXT")
            except sqlite3.OperationalError:
                pass

            # Tag specialdays rows with the import they came from
            try:
                conn.execute("ALTER TABLE specialdays ADD COLUMN import_id INTEGER")
            except sqlite3.OperationalError:
                pass

            # Shared import-id sequence
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
        with self._db.get_connection() as conn:
            cursor = conn.cursor()
            try:
                yield cursor
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    def get_next_import_id(self, cursor):
        cursor.execute("SELECT next_id FROM import_sequence")
        next_id = cursor.fetchone()[0]
        cursor.execute("UPDATE import_sequence SET next_id = ?", (next_id + 1,))
        return next_id

    def create_import_record(self, cursor, user_id, filename, file_hash, command=None):
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
        cursor.execute(
            "SELECT id, filename FROM import_history WHERE filehash = ?", (file_hash,)
        )
        return cursor.fetchone()

    def delete_by_import_id(self, cursor, import_id):
        cursor.execute(
            "DELETE FROM specialdays WHERE import_id = ?", (import_id,)
        )
        return cursor.rowcount

    def delete_import_record(self, cursor, import_id):
        cursor.execute("DELETE FROM import_history WHERE id = ?", (import_id,))

    def get_max_import_id(self, cursor):
        cursor.execute("SELECT COALESCE(MAX(id), 0) FROM import_history")
        return cursor.fetchone()[0]

    def get_next_specialday_id(self, cursor):
        """Get next available specialdays id (TEXT column holding integer strings)."""
        cursor.execute(
            "SELECT COALESCE(MAX(CAST(id AS INTEGER)), 0) + 1 "
            "FROM specialdays WHERE id IS NOT NULL AND id != ''"
        )
        return cursor.fetchone()[0]

    def insert_specialday(self, cursor, sd_data):
        columns = ", ".join(sd_data.keys())
        placeholders = ", ".join(["?" for _ in sd_data])
        sql = f"INSERT INTO specialdays ({columns}) VALUES ({placeholders})"
        cursor.execute(sql, list(sd_data.values()))
        return cursor.lastrowid

    def list_imports(self, cursor):
        """Get import history records with special-day counts (this importer's rows only)."""
        cursor.execute("""
            SELECT
                ih.id,
                ih.userid,
                ih.filename,
                ih.date,
                ih.filehash,
                COUNT(s.id) as sd_count,
                ih.command
            FROM import_history ih
            LEFT JOIN specialdays s ON s.import_id = ih.id
            GROUP BY ih.id
            ORDER BY ih.id
        """)
        return cursor.fetchall()

    def get_import_by_id(self, cursor, import_id):
        cursor.execute(
            """
            SELECT
                ih.id,
                ih.userid,
                ih.filename,
                ih.date,
                ih.filehash,
                COUNT(s.id) as sd_count,
                ih.command
            FROM import_history ih
            LEFT JOIN specialdays s ON s.import_id = ih.id
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
    sha256 = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def determine_file_type(filename):
    ext = os.path.splitext(filename)[1].lower()
    if ext in {".xlsx", ".xls"}:
        return "excel"
    if ext in {".csv", ".txt"}:
        return "csv"
    return None


def read_file(filepath):
    file_type = determine_file_type(filepath)
    if file_type == "excel":
        df = pandas.read_excel(filepath)
    elif file_type == "csv":
        df = pandas.read_csv(filepath)
    else:
        raise ValueError(f"Unsupported file type: {filepath}")
    df.columns = df.columns.str.strip()
    return df


def find_files(path):
    if os.path.isfile(path):
        return [path] if determine_file_type(path) else []
    if os.path.isdir(path):
        files = []
        for f in os.listdir(path):
            full_path = os.path.join(path, f)
            if os.path.isfile(full_path) and determine_file_type(full_path):
                files.append(full_path)
        return sorted(files)
    return []


# ============================================================================
# Row Transformation
# ============================================================================


def transform_row(row, user_id, import_id, sd_id, default_country, default_language):
    """Transform a DataFrame row to a specialdays record."""
    norm = normalize_row(row)

    start_date, end_date, dates_valid = process_dates(
        norm.get("startdate"), norm.get("enddate")
    )
    if not dates_valid:
        return None, "Invalid or missing dates"

    name = norm.get("name")
    if name is None or pandas.isnull(name) or not str(name).strip():
        return None, "name is required"

    def _str(v):
        return (
            str(v).strip()
            if v is not None and pandas.notna(v) and str(v).strip()
            else None
        )

    country = _str(norm.get("country")) or default_country
    language = _str(norm.get("language")) or default_language

    sd = {
        "id": str(sd_id),
        "import_id": import_id,
        "company": _str(norm.get("company")) or "",
        "user": _str(norm.get("user")) or str(user_id),
        "country": country.upper(),
        "language": language.lower(),
        "startdate": start_date,
        "enddate": end_date,
        "name": str(name).strip(),
        "notes": _str(norm.get("notes")) or "",
        "icon": _str(norm.get("icon")) or "",
        "nonworkday": parse_bool(norm.get("nonworkday"), default=0),
        "fullday": parse_bool(norm.get("fullday"), default=1),
        "starthour": _str(norm.get("starthour")) or "",
        "endhour": _str(norm.get("endhour")) or "",
        "tags": _str(norm.get("tags")) or "",
        "daycolor": _str(norm.get("daycolor")) or "",
        "visible": parse_bool(norm.get("visible"), default=1),
    }

    # pattern is NUMERIC in the schema; accept numeric or string and store as-is
    pattern_val = norm.get("pattern")
    if pattern_val is not None and pandas.notna(pattern_val) and str(pattern_val).strip():
        try:
            sd["pattern"] = float(pattern_val)
        except (ValueError, TypeError):
            sd["pattern"] = str(pattern_val).strip()

    patterncolor = _str(norm.get("patterncolor"))
    if patterncolor:
        sd["patterncolor"] = patterncolor

    return sd, None


# ============================================================================
# Import History Management
# ============================================================================


def list_import_history(db):
    with db.transaction() as cursor:
        imports = db.list_imports(cursor)

        if not imports:
            log("No imports found.")
            return

        log("\nImport History:")
        log(
            f"  {'ID':>4}  {'Filename':<20}  {'Date':<19}  {'Days':>5}  {'Hash':<10}  {'Command'}"
        )
        log(
            f"  {'--':>4}  {'-' * 20}  {'-' * 19}  {'-' * 5}  {'-' * 10}  {'-' * 50}"
        )

        total = 0
        for row in imports:
            import_id, userid, filename, date, filehash, sd_count, command = row
            display_name = (
                filename[:20] if filename and len(filename) <= 20
                else (filename[:17] + "..." if filename else "")
            )
            display_date = date[:19] if date else ""
            short_hash = filehash[:8] if filehash else ""
            display_command = ""
            if command:
                display_command = (
                    command if len(command) <= 50 else command[:47] + "..."
                )

            log(
                f"  {import_id:>4}  {display_name:<20}  {display_date:<19}  {sd_count:>5}  {short_hash:<10}  {display_command}"
            )
            total += sd_count

        log(f"\nTotal: {len(imports)} imports, {total} special days")


def remove_import(db, import_id, force=False, verbose=False):
    """Remove an import and all its associated special days."""
    with db.transaction() as cursor:
        import_record = db.get_import_by_id(cursor, import_id)

    if not import_record:
        log(f"Error: Import ID {import_id} not found.", "error")
        return False

    _, userid, filename, date, _, sd_count, _ = import_record

    if not force:
        display_date = date[:19] if date else ""
        log(
            f"Import ID {import_id}: {filename} ({sd_count} special days, imported {display_date})"
        )
        response = input(
            "Are you sure you want to delete this import and all its special days? [y/N]: "
        )
        if response.lower() != "y":
            log("Cancelled.")
            return False

    with db.transaction() as cursor:
        if verbose:
            log(f"Removing import ID {import_id} ({filename})...")
        deleted = db.delete_by_import_id(cursor, import_id)
        if verbose:
            log(f"  Deleted {deleted} special days")
        db.delete_import_record(cursor, import_id)
        if verbose:
            log(f"  Deleted import history record")

    log(f"Removed import {import_id}: {filename} ({deleted} special days deleted)")
    return True


# ============================================================================
# Import Logic
# ============================================================================


def import_file(
    db,
    filepath,
    user_id,
    default_country,
    default_language,
    replace=False,
    verbose=False,
    skip_errors=False,
    command=None,
):
    """Import a single file into the specialdays table."""
    result = ImportResult(filename=filepath)

    file_hash = compute_file_hash(filepath)

    try:
        df = read_file(filepath)
        result.total_rows = len(df)
    except Exception as e:
        result.errors.append(f"Failed to read file: {e}")
        log(f"  Failed to read file: {e}", "error")
        return result

    if verbose:
        log(f"  Read {result.total_rows} rows from {os.path.basename(filepath)}")
        log(f"  Columns: {', '.join(df.columns)}")

    with db.transaction() as cursor:
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
                log(f"  Deleted {deleted} existing special days from previous import")

        import_id = db.create_import_record(
            cursor, user_id, filepath, file_hash, command=command
        )
        result.import_id = import_id

        if verbose:
            log(f"  Created import record (id={import_id})")

        next_sd_id = db.get_next_specialday_id(cursor)

        for idx, row in df.iterrows():
            sd, error = transform_row(
                row.to_dict(),
                user_id,
                import_id,
                next_sd_id,
                default_country,
                default_language,
            )

            if error:
                result.failed_rows += 1
                if verbose:
                    log(f"  Row {idx + 1}: {error}", "warning")
                if not skip_errors:
                    result.errors.append(f"Row {idx + 1}: {error}")
                continue

            try:
                db.insert_specialday(cursor, sd)
                result.imported_rows += 1
                next_sd_id += 1
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
        prog="import_specialdays",
        description="Import XLSX/CSV company special-day files into calendar.db",
    )

    parser.add_argument(
        "files", nargs="*", help="Files or directories to import"
    )
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
        help="User ID for imported special days (default: 1)",
    )
    parser.add_argument(
        "--country",
        "-c",
        default="US",
        help="Default country code when not present in row (default: US)",
    )
    parser.add_argument(
        "--language",
        "-lang",
        default="en",
        help="Default language code when not present in row (default: en)",
    )
    parser.add_argument(
        "--replace",
        "-r",
        action="store_true",
        help="Replace special days from previously imported file",
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

    parser.add_argument(
        "--log-file",
        default="import_specialdays.log",
        help="Path to log file (default: import_specialdays.log)",
    )
    parser.add_argument(
        "--log-level",
        choices=["debug", "info", "warning", "error"],
        default="info",
        help="Set logging level (default: info)",
    )

    args = parser.parse_args()

    global logger
    log_level = "debug" if args.verbose else args.log_level
    logger = setup_logging(args.log_file, log_level)

    command_line = shlex.join(sys.argv)
    log("=== import_specialdays.py started ===")
    log(f"Command: {command_line}")
    log(f"Database: {args.database}")

    if not os.path.exists(args.database):
        log(f"Error: Database not found: {args.database}", "error")
        sys.exit(1)

    db = SpecialDaysDatabase(args.database)

    if args.list:
        list_import_history(db)
        log("=== import_specialdays.py completed ===")
        sys.exit(0)

    if args.remove is not None:
        with db.transaction() as cursor:
            max_id = db.get_max_import_id(cursor)

        if max_id == 0:
            log("No imports found to remove.", "warning")
            log("=== import_specialdays.py completed ===")
            sys.exit(0)

        try:
            import_ids = parse_import_pattern(args.remove, max_id)
        except ValueError as e:
            log(f"Error: {e}", "error")
            log("=== import_specialdays.py completed ===")
            sys.exit(1)

        with db.transaction() as cursor:
            existing_ids = [
                i for i in import_ids if db.get_import_by_id(cursor, i)
            ]

        if not existing_ids:
            log(f"No matching imports found for pattern: {args.remove}", "warning")
            log("=== import_specialdays.py completed ===")
            sys.exit(0)

        log(f"Found {len(existing_ids)} import(s) to remove: {existing_ids}")

        if not args.force:
            with db.transaction() as cursor:
                total = 0
                for import_id in existing_ids:
                    record = db.get_import_by_id(cursor, import_id)
                    if record:
                        _, _, filename, date, _, sd_count, _ = record
                        display_date = date[:19] if date else ""
                        log(
                            f"  ID {import_id}: {filename} ({sd_count} special days, {display_date})"
                        )
                        total += sd_count
                log(f"  Total: {total} special days will be deleted")

            response = input(
                "Are you sure you want to delete these imports and all their special days? [y/N]: "
            )
            if response.lower() != "y":
                log("Cancelled.")
                log("=== import_specialdays.py completed ===")
                sys.exit(0)

        success_count = 0
        fail_count = 0
        for import_id in existing_ids:
            if remove_import(db, import_id, force=True, verbose=args.verbose):
                success_count += 1
            else:
                fail_count += 1

        log(f"\nRemoved {success_count} import(s), {fail_count} failed")
        log("=== import_specialdays.py completed ===")
        sys.exit(0 if fail_count == 0 else 1)

    if not args.files:
        parser.error(
            "Files are required for import. Use --list to view imports or --remove ID to delete."
        )

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

    if args.dry_run:
        log("\n=== DRY RUN - No changes will be made ===\n")
        for filepath in all_files:
            try:
                df = read_file(filepath)
                log(f"  {os.path.basename(filepath)}: {len(df)} rows")
                log(f"    Columns: {', '.join(df.columns)}")

                norm_cols = {
                    COLUMN_MAPPING.get(c.strip().lower()) for c in df.columns
                }
                missing = []
                if "name" not in norm_cols:
                    missing.append("name (or title, special_day, holiday)")
                if "startdate" not in norm_cols and "enddate" not in norm_cols:
                    missing.append("start_date or end_date")
                if missing:
                    log(
                        f"    WARNING: Missing required columns: {', '.join(missing)}",
                        "warning",
                    )

                if len(df) > 0 and args.verbose:
                    log(f"    Sample row: {df.iloc[0].to_dict()}")
            except Exception as e:
                log(f"  {os.path.basename(filepath)}: ERROR - {e}", "error")
        log("=== import_specialdays.py completed ===")
        sys.exit(0)

    total_imported = 0
    total_failed = 0

    for filepath in all_files:
        log(f"\nImporting: {os.path.basename(filepath)}")
        result = import_file(
            db,
            filepath,
            args.user_id,
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
    log("=== import_specialdays.py completed ===")

    sys.exit(0 if total_failed == 0 else 1)


if __name__ == "__main__":
    main()
