"""Schema migration for the schedule data elements.

The importer brings an older `events` table up to the current column set
with lazy ALTER TABLEs.  These tests pin that it is complete, additive,
idempotent, and consistent with the canonical DDL in events.sql.
"""

import re
import sqlite3
from pathlib import Path

import pytest

from importers.import_events import EVENTS_SCHEMA_ADDITIONS, ImportDatabase

ROOT = Path(__file__).resolve().parent.parent

_IMPORT_HISTORY_DDL = """
CREATE TABLE import_history (
    id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
    userid TEXT,
    filename TEXT,
    date TEXT,
    filehash TEXT,
    command TEXT
)
"""

#: The `events` table as it stood before the schedule data elements landed.
_LEGACY_EVENTS_DDL = """
CREATE TABLE events (
    id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    import_id INTEGER NOT NULL,
    status TEXT,
    priority NUMERIC,
    wbs TEXT,
    rollup INTEGER,
    milestone INTEGER,
    percent_complete REAL,
    name TEXT,
    effort REAL,
    duration REAL,
    start_date TEXT,
    end_date TEXT,
    earliest_start_date TEXT,
    latest_start_date TEXT,
    earliest_end_date TEXT,
    latest_end_date TEXT,
    predecessors TEXT,
    resource_names TEXT,
    resource_group TEXT,
    notes TEXT,
    icon TEXT,
    color TEXT,
    tags TEXT
)
"""


def _columns(db_path: str) -> list[str]:
    conn = sqlite3.connect(db_path)
    try:
        return [r[1] for r in conn.execute("PRAGMA table_info(events)")]
    finally:
        conn.close()


@pytest.fixture
def legacy_db(tmp_path):
    """A database at the pre-migration schema."""
    path = str(tmp_path / "legacy.sqlite")
    conn = sqlite3.connect(path)
    conn.execute(_IMPORT_HISTORY_DDL)
    conn.execute(_LEGACY_EVENTS_DDL)
    conn.commit()
    conn.close()
    return path


def test_migration_adds_every_new_column(legacy_db):
    before = _columns(legacy_db)
    for column, _decl in EVENTS_SCHEMA_ADDITIONS:
        assert column not in before

    ImportDatabase(legacy_db)

    after = _columns(legacy_db)
    for column, _decl in EVENTS_SCHEMA_ADDITIONS:
        assert column in after, f"migration did not add {column}"


def test_migration_is_idempotent(legacy_db):
    ImportDatabase(legacy_db)
    first = _columns(legacy_db)
    ImportDatabase(legacy_db)
    assert _columns(legacy_db) == first


def test_migration_preserves_existing_rows(legacy_db):
    conn = sqlite3.connect(legacy_db)
    conn.execute(
        "INSERT INTO events (user_id, import_id, name, start_date, end_date) "
        "VALUES (1, 1, 'Existing task', '20260101', '20260102')"
    )
    conn.commit()
    conn.close()

    ImportDatabase(legacy_db)

    conn = sqlite3.connect(legacy_db)
    try:
        row = conn.execute(
            "SELECT name, start_date, end_date, source_id, cost FROM events"
        ).fetchone()
    finally:
        conn.close()

    # Original values intact; new columns default to NULL.
    assert row == ("Existing task", "20260101", "20260102", None, None)


def test_migrated_schema_matches_canonical_ddl(legacy_db):
    """A migrated database and a fresh events.sql database agree."""
    ImportDatabase(legacy_db)
    migrated = _columns(legacy_db)

    fresh_path = str(Path(legacy_db).parent / "fresh.sqlite")
    conn = sqlite3.connect(fresh_path)
    try:
        conn.executescript((ROOT / "events.sql").read_text())
    finally:
        conn.close()

    assert migrated == _columns(fresh_path)


def test_additions_are_declared_in_events_sql():
    """Every migrated column is also in the checked-in DDL."""
    ddl = (ROOT / "events.sql").read_text()
    declared = set(re.findall(r'"(\w+)"\s+(?:TEXT|INTEGER|REAL|NUMERIC)', ddl))
    for column, _decl in EVENTS_SCHEMA_ADDITIONS:
        assert column in declared, f"{column} missing from events.sql"
