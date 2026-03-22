#!/usr/bin/env python3
"""Import SVG files from a folder into the calendar.db icon table."""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path


def ensure_icon_table(conn: sqlite3.Connection) -> None:
    """Create icon table if it does not exist yet."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS icon (
            filename          TEXT NOT NULL,
            name              TEXT NOT NULL,
            alternativenames  TEXT,
            svg               TEXT NOT NULL
        )
        """
    )
    conn.commit()


def import_icons(folder: Path, db_path: Path, replace: bool) -> None:
    svg_files = sorted(folder.glob("*.svg"))
    if not svg_files:
        print(f"No SVG files found in {folder}")
        return

    conn = sqlite3.connect(db_path)
    try:
        ensure_icon_table(conn)

        inserted = 0
        replaced = 0
        skipped = 0

        for svg_file in svg_files:
            filename = svg_file.name
            name = svg_file.stem
            svg_content = svg_file.read_text(encoding="utf-8")

            existing = conn.execute(
                "SELECT 1 FROM icon WHERE filename = ? OR name = ? LIMIT 1",
                (filename, name),
            ).fetchone()

            if existing and not replace:
                skipped += 1
                continue

            if existing and replace:
                conn.execute(
                    "DELETE FROM icon WHERE filename = ? OR name = ?",
                    (filename, name),
                )
                replaced += 1

            conn.execute(
                "INSERT INTO icon (filename, name, svg) VALUES (?, ?, ?)",
                (filename, name, svg_content),
            )
            inserted += 1

        conn.commit()
    finally:
        conn.close()

    print(
        f"Processed {len(svg_files)} SVG(s): inserted={inserted}, "
        f"replaced={replaced}, skipped={skipped}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Import .svg files into the icon table in a SQLite database."
    )
    parser.add_argument("folder", help="Path to folder containing .svg files")
    parser.add_argument(
        "--db",
        default="calendar.db",
        help="Path to SQLite database (default: calendar.db)",
    )
    parser.add_argument(
        "--replace",
        action="store_true",
        help="Replace existing rows with the same filename or name",
    )
    args = parser.parse_args()

    folder = Path(args.folder)
    if not folder.is_dir():
        parser.error(f"Not a directory: {folder}")

    import_icons(folder=folder, db_path=Path(args.db), replace=args.replace)


if __name__ == "__main__":
    main()
