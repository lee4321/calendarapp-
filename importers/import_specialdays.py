#!/usr/bin/env python
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
import os
import sqlite3
import sys

# Ensure project root is on sys.path when run as a script
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import contextlib

import pandas

from importers.common import (
    ImportDatabase as _ImportDatabaseBase,
)
from importers.common import (
    ImportLog,
    ImportResult,
    add_history_and_log_arguments,
    add_import_arguments,
    collect_import_files,
    compute_file_hash,
    finish_import_run,
    handle_history_commands,
    log_import_result,
    log_import_totals,
    process_dates,
    read_file,
    start_import_run,
)

# ============================================================================
# Logging
# ============================================================================

log = ImportLog()


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
        with contextlib.suppress(sqlite3.OperationalError):
            conn.execute("ALTER TABLE specialdays ADD COLUMN import_id INTEGER")


# ============================================================================
# Row Transformation
# ============================================================================


def transform_row(row, user_id, import_id, sd_id, default_country, default_language):
    """Transform a DataFrame row to a specialdays record."""
    norm = normalize_row(row)

    start_date, end_date, dates_valid = process_dates(norm.get("startdate"), norm.get("enddate"))
    if not dates_valid:
        return None, "Invalid or missing dates"

    name = norm.get("name")
    if name is None or pandas.isnull(name) or not str(name).strip():
        return None, "name is required"

    def _str(v):
        return str(v).strip() if v is not None and pandas.notna(v) and str(v).strip() else None

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
            msg = f"File already imported (id={existing[0]}, filename={existing[1]}). Use --replace to re-import."
            result.errors.append(msg)
            if verbose:
                log(f"  SKIPPED: {msg}", "warning")
            return result

        if existing and replace:
            deleted = db.delete_by_import_id(cursor, existing[0])
            db.delete_import_record(cursor, existing[0])
            if verbose:
                log(f"  Deleted {deleted} existing special days from previous import")

        import_id = db.create_import_record(cursor, user_id, filepath, file_hash, command=command)
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
    add_import_arguments(parser, "special days")
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
    add_history_and_log_arguments(parser, "import_specialdays.log")
    args = parser.parse_args()

    command_line = start_import_run(args, log, "import_specialdays")
    db = SpecialDaysDatabase(args.database)
    handle_history_commands(args, db, log, "import_specialdays")

    if not args.files:
        parser.error("Files are required for import. Use --list to view imports or --remove ID to delete.")

    all_files = collect_import_files(args.files, log)
    log(f"Default country: {args.country}")
    log(f"Default language: {args.language}")

    if args.dry_run:
        log("\n=== DRY RUN - No changes will be made ===\n")
        for filepath in all_files:
            try:
                df = read_file(filepath)
                log(f"  {os.path.basename(filepath)}: {len(df)} rows")
                log(f"    Columns: {', '.join(df.columns)}")

                norm_cols = {COLUMN_MAPPING.get(c.strip().lower()) for c in df.columns}
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
        finish_import_run(log, "import_specialdays", 0)

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
        log_import_result(result, args.verbose, log)
        total_imported += result.imported_rows
        total_failed += result.failed_rows

    log_import_totals("Import", total_imported, total_failed, log)
    finish_import_run(log, "import_specialdays", 0 if total_failed == 0 else 1)


if __name__ == "__main__":
    main()
