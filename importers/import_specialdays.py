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
import shlex

# Ensure project root is on sys.path when run as a script
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas

from importers.common import (
    ImportDatabase as _ImportDatabaseBase,
    ImportResult,
    compute_file_hash,
    convert_date,
    determine_file_type,
    find_files,
    list_import_history,
    parse_import_pattern,
    process_dates,
    read_file,
    remove_import,
    setup_logging as _setup_logging_common,
)


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
# Value Parsing
# ============================================================================


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


class SpecialDaysDatabase(_ImportDatabaseBase):
    """Special-days importer database (rows land in the ``specialdays`` table).

    All bookkeeping (import_history, id sequence, dedup, removal) comes
    from importers.common.ImportDatabase.
    """

    ROW_TABLE = "specialdays"
    UNIT_LABEL = "special days"

    def extra_migrations(self, conn) -> None:
        # Tag specialdays rows with the import they came from
        try:
            conn.execute("ALTER TABLE specialdays ADD COLUMN import_id INTEGER")
        except sqlite3.OperationalError:
            pass


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

        next_sd_id = db.get_next_row_id(cursor)

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
                db.insert_row(cursor, sd)
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
        list_import_history(db, log)
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
            if remove_import(db, import_id, log, force=True, verbose=args.verbose):
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
