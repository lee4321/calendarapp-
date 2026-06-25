#!/usr/bin/env python3
"""Remove duplicate rows from the `colors` table based on hex value.

Duplicates are detected case-insensitively on the `hex` column. Within each
group of rows sharing a hex value, the most complete row is kept (one that has
Spanish/German/French translations populated, tie-broken by lowest rowid); the
rest are deleted.

Usage:
    uv run python "db utils/dedupe_colors.py"            # dry run (default)
    uv run python "db utils/dedupe_colors.py" --apply    # perform deletion
    uv run python "db utils/dedupe_colors.py" --apply --db path/to/calendar.db
"""

from __future__ import annotations

import argparse
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

# Row kept per hex group: most translations first, then lowest rowid (original).
RANK_SQL = """
WITH ranked AS (
    SELECT rowid AS rid,
        ROW_NUMBER() OVER (
            PARTITION BY lower(hex)
            ORDER BY (ES <> '') DESC, (DE <> '') DESC, (FR <> '') DESC, rowid ASC
        ) AS rn
    FROM colors
)
SELECT rid FROM ranked WHERE rn > 1
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default="calendar.db", help="Path to the SQLite database (default: calendar.db)")
    parser.add_argument("--apply", action="store_true", help="Actually delete duplicates (default is a dry run)")
    parser.add_argument("--no-backup", action="store_true", help="Skip creating a .bak copy before applying")
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"error: database not found: {db_path}", file=sys.stderr)
        return 1

    conn = sqlite3.connect(db_path)
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        total = conn.execute("SELECT COUNT(*) FROM colors").fetchone()[0]
        doomed = [r[0] for r in conn.execute(RANK_SQL).fetchall()]

        print(f"Database:        {db_path}")
        print(f"Total rows:      {total}")
        print(f"Rows to keep:    {total - len(doomed)}")
        print(f"Rows to remove:  {len(doomed)}")

        if not doomed:
            print("\nNo duplicates found. Nothing to do.")
            return 0

        if not args.apply:
            print("\nDry run — no changes made. Re-run with --apply to delete the rows above.")
            return 0

        if not args.no_backup:
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup = db_path.with_suffix(db_path.suffix + f".bak.{stamp}")
            shutil.copy2(db_path, backup)
            print(f"\nBackup created:  {backup}")

        conn.executemany("DELETE FROM colors WHERE rowid = ?", [(rid,) for rid in doomed])
        conn.commit()

        remaining = conn.execute("SELECT COUNT(*) FROM colors").fetchone()[0]
        distinct = conn.execute("SELECT COUNT(*) FROM (SELECT DISTINCT lower(hex) FROM colors)").fetchone()[0]
        print(f"Deleted {len(doomed)} rows. Remaining: {remaining} ({distinct} distinct hex values).")
        if remaining != distinct:
            print("warning: remaining row count does not match distinct hex count", file=sys.stderr)
            return 1
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
