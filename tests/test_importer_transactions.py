"""Regression guard: importer transactions on CalendarDB's shared connection.

`ImportDatabase` does not own its connection — it holds a `CalendarDB` and runs
`transaction()` through `CalendarDB.get_connection()`, which now yields one
long-lived connection instead of a fresh one per block.  Commit durability and
rollback isolation therefore depend on `transaction()` alone, with no implicit
cleanup from a closing connection.  These tests pin that behaviour.
"""

import sqlite3

import pytest

from importers.import_events import ImportDatabase

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

_EVENTS_DDL = """
CREATE TABLE events (
    id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    import_id INTEGER NOT NULL,
    name TEXT,
    start_date TEXT,
    end_date TEXT
)
"""


@pytest.fixture
def db(tmp_path):
    """An ImportDatabase over a minimal events schema."""
    path = str(tmp_path / "imports.sqlite")
    conn = sqlite3.connect(path)
    conn.execute(_IMPORT_HISTORY_DDL)
    conn.execute(_EVENTS_DDL)
    conn.commit()
    conn.close()
    return ImportDatabase(path)


def _history_ids_from_fresh_connection(db_path: str) -> list[int]:
    """Read committed state through a connection the importer does not own."""
    conn = sqlite3.connect(db_path)
    try:
        return [r[0] for r in conn.execute("SELECT id FROM import_history")]
    finally:
        conn.close()


def test_transaction_commits_are_durable(db):
    with db.transaction() as cursor:
        db.create_import_record(cursor, user_id=1, filename="a.csv", file_hash="h1")

    # Durability must be visible outside the shared connection, not just inside it.
    assert _history_ids_from_fresh_connection(db.db_path) == [1]


def test_transaction_rolls_back_on_exception(db):
    with pytest.raises(RuntimeError):
        with db.transaction() as cursor:
            db.create_import_record(cursor, user_id=1, filename="b.csv", file_hash="h2")
            raise RuntimeError("boom")

    assert _history_ids_from_fresh_connection(db.db_path) == []


def test_shared_connection_is_usable_after_a_rollback(db):
    with pytest.raises(RuntimeError):
        with db.transaction() as cursor:
            db.create_import_record(cursor, user_id=1, filename="c.csv", file_hash="h3")
            raise RuntimeError("boom")

    # The rolled-back connection is reused, so it must be left in a clean state.
    with db.transaction() as cursor:
        import_id = db.create_import_record(
            cursor, user_id=1, filename="d.csv", file_hash="h4"
        )
        db.insert_row(
            cursor,
            {
                "user_id": 1,
                "import_id": import_id,
                "name": "Kickoff",
                "start_date": "20260105",
                "end_date": "20260105",
            },
        )

    assert _history_ids_from_fresh_connection(db.db_path) == [import_id]


def test_rollback_returns_the_claimed_id_to_the_sequence(db):
    """A failed import releases the id it claimed.

    The never-reused-id guarantee covers *deleted* imports, not aborted ones:
    the `import_sequence` bump is written inside the transaction, so a rollback
    discards it along with the rows and the next import takes that id.
    """
    with pytest.raises(RuntimeError):
        with db.transaction() as cursor:
            db.create_import_record(cursor, user_id=1, filename="e.csv", file_hash="h5")
            raise RuntimeError("boom")

    with db.transaction() as cursor:
        second_id = db.create_import_record(
            cursor, user_id=1, filename="f.csv", file_hash="h6"
        )

    # The sequence bump was rolled back with the rest of the failed transaction,
    # so the next successful import takes the id the failed one had claimed.
    assert second_id == 1
    assert _history_ids_from_fresh_connection(db.db_path) == [1]


def test_sequential_transactions_do_not_leak_state(db):
    with db.transaction() as cursor:
        first = db.create_import_record(cursor, user_id=1, filename="g.csv", file_hash="h7")
    with db.transaction() as cursor:
        second = db.create_import_record(cursor, user_id=1, filename="h.csv", file_hash="h8")

    assert second == first + 1
    assert _history_ids_from_fresh_connection(db.db_path) == [first, second]
