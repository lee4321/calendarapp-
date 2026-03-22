#!/usr/bin/env python3
"""Load SVG files from a folder into the calendar.db patterns table."""

import argparse
import sqlite3
from pathlib import Path


def create_patterns_table(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS patterns (
            id    INTEGER PRIMARY KEY AUTOINCREMENT,
            name  TEXT    NOT NULL UNIQUE,
            svg   TEXT    NOT NULL
        )
    """)
    conn.commit()


def load_svgs(folder: Path, db_path: Path, replace: bool) -> None:
    svg_files = sorted(folder.glob("*.svg"))
    if not svg_files:
        print(f"No SVG files found in {folder}")
        return

    conn = sqlite3.connect(db_path)
    create_patterns_table(conn)

    inserted = updated = skipped = 0
    for svg_path in svg_files:
        name = svg_path.stem
        svg_content = svg_path.read_text(encoding="utf-8")

        if replace:
            conn.execute(
                "INSERT OR REPLACE INTO patterns (name, svg) VALUES (?, ?)",
                (name, svg_content),
            )
            updated += 1
        else:
            try:
                conn.execute(
                    "INSERT INTO patterns (name, svg) VALUES (?, ?)",
                    (name, svg_content),
                )
                inserted += 1
            except sqlite3.IntegrityError:
                print(f"  Skipped (already exists): {name}")
                skipped += 1

    conn.commit()
    conn.close()

    if replace:
        print(f"Upserted {updated} pattern(s) from {folder}")
    else:
        print(f"Inserted {inserted} pattern(s), skipped {skipped} from {folder}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Import SVG files into the calendar.db patterns table."
    )
    parser.add_argument("folder", help="Folder containing .svg files")
    parser.add_argument(
        "--db",
        default="calendar.db",
        help="Path to SQLite database (default: calendar.db)",
    )
    parser.add_argument(
        "--replace",
        action="store_true",
        help="Replace existing rows with the same name (default: skip)",
    )
    args = parser.parse_args()

    folder = Path(args.folder)
    if not folder.is_dir():
        parser.error(f"Not a directory: {folder}")

    load_svgs(folder, Path(args.db), args.replace)


if __name__ == "__main__":
    main()
