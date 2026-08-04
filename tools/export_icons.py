#!/usr/bin/env python3
"""Export the SVG contents of the ``icon`` table in calendar.db to a folder.

Each row's ``svg`` column is written to a file named after its ``filename``
column. This script is standalone — it depends only on the Python standard
library and does NOT require the ecalendar package or any of its dependencies.

Usage:
    python export_icons.py exported_icons                 # export to ./exported_icons
    python export_icons.py exported_icons --db other.db   # use a different database
    python export_icons.py exported_icons --overwrite     # replace existing files
    python export_icons.py exported_icons --name-like "arrow%"   # export a subset
"""

from __future__ import annotations

import argparse
import re
import sqlite3
import sys
from pathlib import Path

DEFAULT_DB = "calendar.db"

# Characters that are unsafe in a filename on macOS/Linux/Windows.
_UNSAFE_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def safe_filename(raw: str, fallback: str) -> str:
    """Return *raw* reduced to a safe, single-segment ``.svg`` filename.

    Path separators and other unsafe characters are replaced with ``_`` so a
    malformed database value can never escape the destination directory.
    """
    name = _UNSAFE_CHARS.sub("_", (raw or "").strip())
    name = name.strip(". ")
    if not name:
        name = fallback
    if not name.lower().endswith(".svg"):
        name += ".svg"
    return name


def export_icons(
    db_path: Path,
    dest: Path,
    *,
    name_like: str | None = None,
    overwrite: bool = False,
) -> tuple[int, int]:
    """Write every icon's SVG into *dest*.

    Returns ``(written, skipped)``.
    """
    if not db_path.exists():
        raise SystemExit(f"error: database not found: {db_path}")

    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        sql = "SELECT rowid, filename, svg FROM icon"
        params: tuple[str, ...] = ()
        if name_like:
            sql += " WHERE filename LIKE ? OR name LIKE ?"
            params = (name_like, name_like)
        sql += " ORDER BY filename"
        try:
            rows = conn.execute(sql, params).fetchall()
        except sqlite3.OperationalError as exc:
            raise SystemExit(f"error: cannot read icon table: {exc}") from exc
    finally:
        conn.close()

    if not rows:
        raise SystemExit("error: no icons matched")

    dest.mkdir(parents=True, exist_ok=True)

    written = 0
    skipped = 0
    used: set[str] = set()

    for rowid, filename, svg in rows:
        if not svg or not svg.strip():
            print(f"skip: rowid {rowid} ({filename!r}) has empty svg", file=sys.stderr)
            skipped += 1
            continue

        name = safe_filename(filename, fallback=f"icon_{rowid}")

        # Disambiguate collisions from sanitizing, duplicate rows, or names that
        # differ only by case (those clash on case-insensitive filesystems such
        # as macOS). Compared casefolded so the result is identical on every
        # platform rather than silently losing rows on some of them.
        if name.casefold() in used:
            name = f"{name[:-4]}_{rowid}.svg"
        used.add(name.casefold())

        target = dest / name
        if target.exists() and not overwrite:
            print(f"skip: {target} exists (use --overwrite)", file=sys.stderr)
            skipped += 1
            continue

        target.write_text(svg, encoding="utf-8")
        written += 1

    return written, skipped


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Export SVG icons from the calendar.db icon table."
    )
    parser.add_argument("folder", help="destination folder (created if missing)")
    parser.add_argument(
        "--db",
        default=DEFAULT_DB,
        help=f"path to the SQLite database (default: {DEFAULT_DB})",
    )
    parser.add_argument(
        "--name-like",
        help="only export icons whose filename or name matches this SQL LIKE pattern",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="overwrite files that already exist in the destination",
    )
    args = parser.parse_args(argv)

    written, skipped = export_icons(
        Path(args.db),
        Path(args.folder),
        name_like=args.name_like,
        overwrite=args.overwrite,
    )
    print(f"Exported {written} icon(s) to {Path(args.folder).resolve()}", end="")
    print(f" ({skipped} skipped)" if skipped else "")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
