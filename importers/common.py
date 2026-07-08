"""
Shared framework for calendar importers.

The events and special-days importers share everything except the target
table and the per-row transform: file discovery and reading, SHA-256
dedup hashing, date parsing, the import_history bookkeeping (sequence,
create/list/remove), and logging. This module owns all of that.

Each importer supplies:

* an `ImportDatabase` subclass declaring `ROW_TABLE` / `UNIT_LABEL`
  (plus any `extra_migrations`),
* its column mapping + `transform_row`,
* its CLI (`main`) and `import_file` orchestration.
"""

import hashlib
import logging
import os
import sqlite3
import sys
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional

import arrow
import pandas
from dateutil.parser import parse as dateutil_parse

from shared.db_access import CalendarDB


def setup_logging(
    module_name: str, log_file: str | None = None, level: str = "info"
) -> logging.Logger:
    """Configure logging to file and console.

    Args:
        module_name: Logger name (e.g. "import_events")
        log_file: Path to log file; defaults to "<module_name>.log"
        level: Logging level ('debug', 'info', 'warning', 'error')

    Returns:
        Configured logger instance
    """
    log = logging.getLogger(module_name)
    if log_file is None:
        log_file = f"{module_name}.log"

    level_map = {
        "debug": logging.DEBUG,
        "info": logging.INFO,
        "warning": logging.WARNING,
        "error": logging.ERROR,
    }
    log_level = level_map.get(level.lower(), logging.INFO)
    log.setLevel(log_level)
    log.handlers = []

    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(log_level)
    file_handler.setFormatter(
        logging.Formatter(
            "%(asctime)s | %(levelname)-7s | %(filename)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    log.addHandler(file_handler)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(logging.Formatter("%(message)s"))
    log.addHandler(console_handler)

    return log


def make_log_fn(logger_ref: list) -> callable:
    """Return a log() helper that dispatches to a logger stored in a mutable container.

    The container pattern allows the importer module to replace the logger after
    calling setup_logging() while keeping the log() function reference stable.

    Args:
        logger_ref: A single-element list holding the logger (or None)

    Returns:
        A log(message, level) function
    """
    level_names = ("debug", "info", "warning", "error")

    def _log(message: str, level: str = "info") -> None:
        lg = logger_ref[0]
        if lg is None:
            print(message)
            return
        if level not in level_names:
            level = "info"
        getattr(lg, level)(message)

    return _log


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

    if pattern == "all":
        return list(range(1, max_id + 1))

    # Comma-separated list: "1,3,5"
    if "," in pattern:
        try:
            ids = [int(x.strip()) for x in pattern.split(",")]
            return sorted(set(ids))
        except ValueError:
            raise ValueError(f"Invalid ID list: {pattern}")

    # Ranges: "1-5", "5-" (to max), "-3" (from 1)
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

    # Single ID: "3"
    try:
        return [int(pattern)]
    except ValueError:
        raise ValueError(f"Invalid import ID pattern: {pattern}")


# ============================================================================
# Result Record
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
    """
    Convert date from various formats to YYYYMMDD.

    Handles M/D/YYYY, M/D/YY, YYYY-MM-DD, and empty/NaN values.

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

        return arrow.Arrow.fromdatetime(parsed_date).format(target_format)

    except (ValueError, TypeError):
        return None


def process_dates(start_raw, end_raw):
    """
    Convert start and end dates, handling edge cases.

    - If only one side is valid, the other side copies it.
    - If start > end: swap them.

    Returns:
        tuple: (start_date_str, end_date_str, is_valid)
    """
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
    """Determine file type ("excel" / "csv" / None) from extension."""
    ext = os.path.splitext(filename)[1].lower()
    if ext in {".xlsx", ".xls"}:
        return "excel"
    if ext in {".csv", ".txt"}:
        return "csv"
    return None


def read_file(filepath):
    """Read an importable file into a DataFrame."""
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
# Database Operations
# ============================================================================


class ImportDatabase:
    """Import-history database manager shared by the row importers.

    Owns the `import_history` bookkeeping: the never-reused id sequence,
    record creation, hash-based duplicate detection, and removal of an
    import together with its rows.

    Subclasses declare:
        ROW_TABLE:   table their rows land in (has an `import_id` column)
        UNIT_LABEL:  human plural for messages ("events", "special days")
    and may override `extra_migrations()` for table-specific schema fixes.
    """

    ROW_TABLE: str = ""
    UNIT_LABEL: str = "rows"

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

            self.extra_migrations(conn)

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

    def extra_migrations(self, conn) -> None:
        """Hook for subclass-specific schema migrations. Default: none."""

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
            "SELECT id, filename FROM import_history WHERE filehash = ?",
            (file_hash,),
        )
        return cursor.fetchone()

    def delete_by_import_id(self, cursor, import_id):
        """Delete this importer's rows from a previous import (for --replace)."""
        cursor.execute(
            f"DELETE FROM {self.ROW_TABLE} WHERE import_id = ?", (import_id,)
        )
        return cursor.rowcount

    def delete_import_record(self, cursor, import_id):
        """Delete import_history record."""
        cursor.execute("DELETE FROM import_history WHERE id = ?", (import_id,))

    def get_max_import_id(self, cursor):
        """Get the maximum import ID."""
        cursor.execute("SELECT COALESCE(MAX(id), 0) FROM import_history")
        return cursor.fetchone()[0]

    def get_next_row_id(self, cursor):
        """Get next available row ID in this importer's table."""
        cursor.execute(f"SELECT COALESCE(MAX(id), 0) + 1 FROM {self.ROW_TABLE}")
        return cursor.fetchone()[0]

    def insert_row(self, cursor, row_data):
        """Insert a single row record into this importer's table."""
        columns = ", ".join(row_data.keys())
        placeholders = ", ".join(["?" for _ in row_data])
        sql = f"INSERT INTO {self.ROW_TABLE} ({columns}) VALUES ({placeholders})"
        cursor.execute(sql, list(row_data.values()))
        return cursor.lastrowid

    def list_imports(self, cursor):
        """Get all import history records with per-import row counts."""
        cursor.execute(f"""
            SELECT
                ih.id,
                ih.userid,
                ih.filename,
                ih.date,
                ih.filehash,
                COUNT(r.id) as row_count,
                ih.command
            FROM import_history ih
            LEFT JOIN {self.ROW_TABLE} r ON r.import_id = ih.id
            GROUP BY ih.id
            ORDER BY ih.id
        """)
        return cursor.fetchall()

    def get_import_by_id(self, cursor, import_id):
        """Get single import record with its row count."""
        cursor.execute(
            f"""
            SELECT
                ih.id,
                ih.userid,
                ih.filename,
                ih.date,
                ih.filehash,
                COUNT(r.id) as row_count,
                ih.command
            FROM import_history ih
            LEFT JOIN {self.ROW_TABLE} r ON r.import_id = ih.id
            WHERE ih.id = ?
            GROUP BY ih.id
            """,
            (import_id,),
        )
        return cursor.fetchone()


# ============================================================================
# Import-history CLI actions
# ============================================================================


def list_import_history(db: ImportDatabase, log) -> None:
    """Print the import_history table with per-import row counts."""
    with db.transaction() as cursor:
        imports = db.list_imports(cursor)

        if not imports:
            log("No imports found.")
            return

        log("\nImport History:")
        log(
            f"  {'ID':>4}  {'Filename':<20}  {'Date':<19}  {'Rows':>6}  {'Hash (first 8)':<14}  {'Command'}"
        )
        log(
            f"  {'--':>4}  {'-' * 20}  {'-' * 19}  {'------':>6}  {'-' * 14}  {'-' * 50}"
        )

        total_rows = 0
        for row in imports:
            import_id, userid, filename, date, filehash, row_count, command = row
            display_name = (
                filename[:20]
                if filename and len(filename) <= 20
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
                f"  {import_id:>4}  {display_name:<20}  {display_date:<19}  {row_count:>6}  {short_hash:<14}  {display_command}"
            )
            total_rows += row_count

        log(f"\nTotal: {len(imports)} imports, {total_rows} {db.UNIT_LABEL}")


def remove_import(db: ImportDatabase, import_id, log, force=False, verbose=False):
    """Remove an import and all its associated rows."""
    unit = db.UNIT_LABEL

    # First, get import details (outside transaction for user confirmation)
    with db.transaction() as cursor:
        import_record = db.get_import_by_id(cursor, import_id)

    if not import_record:
        log(f"Error: Import ID {import_id} not found.", "error")
        return False

    _, userid, filename, date, _, row_count, _ = import_record

    if not force:
        display_date = date[:19] if date else ""
        log(
            f"Import ID {import_id}: {filename} ({row_count} {unit}, imported {display_date})"
        )
        response = input(
            f"Are you sure you want to delete this import and all its {unit}? [y/N]: "
        )
        if response.lower() != "y":
            log("Cancelled.")
            return False

    with db.transaction() as cursor:
        if verbose:
            log(f"Removing import ID {import_id} ({filename})...")

        deleted_rows = db.delete_by_import_id(cursor, import_id)
        if verbose:
            log(f"  Deleted {deleted_rows} {unit}")

        db.delete_import_record(cursor, import_id)
        if verbose:
            log("  Deleted import history record")

    log(f"Removed import {import_id}: {filename} ({deleted_rows} {unit} deleted)")
    return True
