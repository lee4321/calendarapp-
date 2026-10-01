#!/usr/bin/env python3
"""Build a working calendar.db from the SQL scripts and sample data in the repo.

A fresh clone has no database (``calendar.db`` is gitignored).  This builds
one with the schema, the named colors, the paper sizes, the icon set and the glyph groups,
and imports the sample events.  Pattern tiles and palettes are not in the
repo; load your own with ``importers/import_patterns.py`` and the palette
commands.

Usage:
    uv run python tools/db/build_db.py                 # ./calendar.db (refuses to overwrite)
    uv run python tools/db/build_db.py PATH --force    # replace PATH
    uv run python tools/db/build_db.py PATH --no-events
"""

from __future__ import annotations

import argparse
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

SQL_DIR = ROOT / "tools" / "db"
#: Run in this order: schema first, then the data that needs it.
SQL_SCRIPTS = ("create.calendar.db.sql", "load.colors.sql", "load.papersizes.sql", "create_load_icon.sql")
SAMPLE_EVENTS = (ROOT / "importers" / "sample_data.csv", ROOT / "importers" / "nimbuspay_modernization.csv")


#: SVG tiles used to fill the ``patterns`` table of test databases.
TEST_PATTERNS_DIR = ROOT / "testdb" / "patterns"


def load_patterns(path: Path, folder: Path = TEST_PATTERNS_DIR) -> int:
    """Insert every ``*.svg`` in ``folder`` into ``path``'s patterns table (name = file stem)."""
    rows = [(f.stem, f.read_text(encoding="utf-8")) for f in sorted(folder.glob("*.svg"))]
    with sqlite3.connect(path) as conn:
        conn.executemany("INSERT INTO patterns (name, svg) VALUES (?, ?)", rows)
    return len(rows)


def build(path: Path, *, events: bool = True, patterns: Path | None = None) -> Path:
    """Create the database at ``path`` (which must not exist).

    ``patterns`` is a folder of ``.svg`` tiles to load into the patterns table.
    """
    with sqlite3.connect(path) as conn:
        for script in SQL_SCRIPTS:
            conn.executescript((SQL_DIR / script).read_text(encoding="utf-8"))
    from tools.db.create_glyphs import DEFAULT_SEED, create_glyphs, load_seed

    create_glyphs(path, load_seed(DEFAULT_SEED))
    if patterns is not None:
        load_patterns(path, patterns)
    if events:
        for csv in SAMPLE_EVENTS:
            subprocess.run(
                [sys.executable, str(ROOT / "importers" / "import_events.py"), "--database", str(path), str(csv)],
                check=True,
                capture_output=True,
                cwd=ROOT,
            )
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("path", nargs="?", default="calendar.db", type=Path)
    parser.add_argument("--force", action="store_true", help="replace an existing database")
    parser.add_argument("--no-events", action="store_true", help="schema and reference data only")
    args = parser.parse_args(argv)
    if args.path.exists():
        if not args.force:
            print(f"{args.path} exists; pass --force to replace it", file=sys.stderr)
            return 1
        args.path.unlink()
    build(args.path, events=not args.no_events)
    print(f"built {args.path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
