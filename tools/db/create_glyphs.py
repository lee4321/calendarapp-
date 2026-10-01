#!/usr/bin/env python3
"""Create and seed the ``glyphs`` table.

The program never creates this table itself: when it is missing, a run that
needs glyphs stops with a message naming this script.  Run it once per
database, and again whenever ``glyphs_seed.json`` changes (it replaces the
seeded groups; groups you added under other names are left alone).

A glyph group is an ordered list of glyphs.  Themes name a group per role
(``text_mini.glyphs.event: text-mini-event``); the renderer cycles through the
group in ``seq`` order.  Group names are free-form text.

Usage:
    uv run python tools/db/create_glyphs.py                      # ./calendar.db
    uv run python tools/db/create_glyphs.py --database PATH
    uv run python tools/db/create_glyphs.py --seed my_glyphs.json   # add or replace your own groups
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

DEFAULT_SEED = Path(__file__).with_name("glyphs_seed.json")

SCHEMA = """
CREATE TABLE IF NOT EXISTS glyphs (
    glyph_group TEXT    NOT NULL,
    seq         INTEGER NOT NULL,
    glyph       TEXT    NOT NULL,
    PRIMARY KEY (glyph_group, seq)
)
"""


def load_seed(path: Path) -> dict[str, list[str]]:
    """Read ``{group: [glyph, ...]}`` from *path*, checking its shape."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path}: expected an object mapping group names to lists of glyphs")
    for group, glyphs in data.items():
        if not isinstance(glyphs, list) or not glyphs or not all(isinstance(g, str) and g for g in glyphs):
            raise ValueError(f"{path}: group '{group}' must be a non-empty list of non-empty strings")
    return data


def create_glyphs(database: Path, seed: dict[str, list[str]]) -> tuple[int, int]:
    """Create the table if needed and (re)write *seed*'s groups.  Returns (groups, glyphs)."""
    with sqlite3.connect(database) as conn:
        conn.execute(SCHEMA)
        for group, glyphs in seed.items():
            conn.execute("DELETE FROM glyphs WHERE glyph_group = ?", (group,))
            conn.executemany(
                "INSERT INTO glyphs (glyph_group, seq, glyph) VALUES (?, ?, ?)",
                [(group, i, glyph) for i, glyph in enumerate(glyphs)],
            )
    return len(seed), sum(len(g) for g in seed.values())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create and seed the glyphs table.")
    parser.add_argument(
        "--database", "-db", default="calendar.db", type=Path, help="SQLite database (default: calendar.db)"
    )
    parser.add_argument(
        "--seed", type=Path, default=DEFAULT_SEED, help="JSON file of glyph groups (default: glyphs_seed.json)"
    )
    args = parser.parse_args(argv)

    if not args.database.is_file():
        print(f"error: database '{args.database}' does not exist", file=sys.stderr)
        return 2
    try:
        groups, glyphs = create_glyphs(args.database, load_seed(args.seed))
    except (OSError, ValueError, sqlite3.Error) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(f"glyphs table in {args.database}: {groups} groups, {glyphs} glyphs")
    return 0


if __name__ == "__main__":
    sys.exit(main())
