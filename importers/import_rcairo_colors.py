#!/usr/bin/env python3
"""Import Rcairocolors.csv into the calendar.db colors table.

Maps CSV columns (name, hex, r, g, b) to DB columns (EN, hex, red, green, blue).
ES, DE, and FR columns are left empty.

Usage:
    uv run python importers/import_rcairo_colors.py [--db calendar.db] [--csv Rcairocolors.csv] [--replace]
"""

import argparse
import csv
import sqlite3
import sys
from pathlib import Path


def parse_args():
    parser = argparse.ArgumentParser(description="Import Rcairocolors.csv into calendar.db colors table")
    parser.add_argument("--db", default="calendar.db", help="Path to SQLite database (default: calendar.db)")
    parser.add_argument("--csv", default="Rcairocolors.csv", help="Path to CSV file (default: Rcairocolors.csv)")
    parser.add_argument(
        "--replace",
        action="store_true",
        help="Replace existing rows with matching EN name (default: skip duplicates)",
    )
    return parser.parse_args()


def import_colors(db_path: Path, csv_path: Path, replace: bool) -> None:
    rows = []
    with csv_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f, skipinitialspace=True)
        for i, row in enumerate(reader, start=2):  # line 2 = first data row
            name = row.get("name", "").strip()
            hex_val = row.get("hex", "").strip()
            try:
                r = int(row["r"])
                g = int(row["g"])
                b = int(row["b"])
            except (KeyError, ValueError) as e:
                print(f"  WARNING line {i}: skipping {name!r} — {e}", file=sys.stderr)
                continue
            rows.append((name, "", "", "", hex_val, r, g, b))

    print(f"Parsed {len(rows)} color rows from {csv_path}")

    con = sqlite3.connect(db_path)
    try:
        if replace:
            sql = (
                "INSERT OR REPLACE INTO colors (EN, ES, DE, FR, hex, red, green, blue) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
            )
        else:
            sql = (
                "INSERT OR IGNORE INTO colors (EN, ES, DE, FR, hex, red, green, blue) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
            )

        cur = con.executemany(sql, rows)
        con.commit()
        affected = cur.rowcount
        skipped = len(rows) - affected
        print(f"Inserted {affected} rows" + (f", skipped {skipped} duplicates" if skipped else ""))
    finally:
        con.close()


def main():
    args = parse_args()
    db_path = Path(args.db)
    csv_path = Path(args.csv)

    if not db_path.exists():
        print(f"ERROR: database not found: {db_path}", file=sys.stderr)
        sys.exit(1)
    if not csv_path.exists():
        print(f"ERROR: CSV not found: {csv_path}", file=sys.stderr)
        sys.exit(1)

    import_colors(db_path, csv_path, replace=args.replace)


if __name__ == "__main__":
    main()
