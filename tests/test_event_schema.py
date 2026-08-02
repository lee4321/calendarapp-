"""Schema migration for the schedule data elements.

The importer brings an older `events` table up to the current column set
with lazy ALTER TABLEs.  These tests pin that it is complete, additive,
idempotent, and consistent with the canonical DDL in events.sql.
"""

import re
import sqlite3
from pathlib import Path

import pytest

from importers.import_events import ImportDatabase
from shared.db_access import CalendarDB
from shared.events_schema import EVENTS_SCHEMA_ADDITIONS, migrate_events_table

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


def test_calendar_db_migrates_on_connect(legacy_db):
    """The read layer migrates too -- a stale database must not fail on
    the first query, since reads name every column explicitly."""
    db = CalendarDB(legacy_db)
    try:
        db.get_all_events_in_range("20260101", "20261231")
    finally:
        db.close()

    for column, _decl in EVENTS_SCHEMA_ADDITIONS:
        assert column in _columns(legacy_db)


def test_reading_a_stale_database_returns_the_new_fields(legacy_db):
    conn = sqlite3.connect(legacy_db)
    conn.execute(
        "INSERT INTO events (user_id, import_id, name, start_date, end_date) "
        "VALUES (1, 1, 'Legacy task', '20260115', '20260116')"
    )
    conn.commit()
    conn.close()

    db = CalendarDB(legacy_db)
    try:
        events = db.get_all_events_in_range("20260101", "20260131")
    finally:
        db.close()

    assert len(events) == 1
    assert events[0]["Task_Name"] == "Legacy task"
    assert events[0]["Cost"] is None
    assert events[0]["Custom1"] is None


def test_migration_reports_only_what_it_added(legacy_db):
    conn = sqlite3.connect(legacy_db)
    try:
        added = migrate_events_table(conn)
        assert added == [c for c, _d in EVENTS_SCHEMA_ADDITIONS]
        # Second pass has nothing left to do.
        assert migrate_events_table(conn) == []
    finally:
        conn.close()


def test_migration_skips_a_database_without_an_events_table(tmp_path):
    """Some other SQLite file must not gain an events table by accident."""
    path = str(tmp_path / "unrelated.sqlite")
    conn = sqlite3.connect(path)
    try:
        conn.execute("CREATE TABLE notes (id INTEGER PRIMARY KEY, body TEXT)")
        conn.commit()
        assert migrate_events_table(conn) == []
        tables = {
            r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        assert tables == {"notes"}
    finally:
        conn.close()


def test_migration_of_a_read_only_database_warns_instead_of_raising(legacy_db):
    """Opening a read-only file for reading must still work."""
    conn = sqlite3.connect(f"file:{legacy_db}?mode=ro", uri=True)
    try:
        assert migrate_events_table(conn) == []
    finally:
        conn.close()


def test_additions_are_declared_in_events_sql():
    """Every migrated column is also in the checked-in DDL."""
    ddl = (ROOT / "events.sql").read_text()
    declared = set(re.findall(r'"(\w+)"\s+(?:TEXT|INTEGER|REAL|NUMERIC)', ddl))
    for column, _decl in EVENTS_SCHEMA_ADDITIONS:
        assert column in declared, f"{column} missing from events.sql"
