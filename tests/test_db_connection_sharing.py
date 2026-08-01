"""Regression guard: CalendarDB holds one long-lived connection.

A render issues thousands of small queries.  Re-opening a connection per query
cost roughly a third of total runtime, so `_get_connection()` yields a shared
connection that outlives the `with` block.  These tests pin that contract so a
future refactor cannot quietly reintroduce per-query connect/close.
"""

import sqlite3

from shared.db_access import CalendarDB


def _make_db(path: str) -> None:
    conn = sqlite3.connect(path)
    conn.commit()
    conn.close()


def test_get_connection_reuses_a_single_connection(tmp_path):
    db = CalendarDB(str(tmp_path / "shared.sqlite"))
    _make_db(db.db_path)

    with db._get_connection() as first:
        pass
    with db._get_connection() as second:
        pass

    assert first is second


def test_public_wrapper_yields_the_same_shared_connection(tmp_path):
    db = CalendarDB(str(tmp_path / "wrapper.sqlite"))
    _make_db(db.db_path)

    with db.get_connection() as public:
        with db._get_connection() as private:
            assert public is private


def test_connection_stays_open_after_the_block_exits(tmp_path):
    db = CalendarDB(str(tmp_path / "stays_open.sqlite"))
    _make_db(db.db_path)

    with db._get_connection() as conn:
        pass

    # Would raise ProgrammingError if the context manager had closed it.
    assert conn.execute("SELECT 1").fetchone()[0] == 1


def test_connection_is_opened_lazily(tmp_path):
    db = CalendarDB(str(tmp_path / "lazy.sqlite"))
    _make_db(db.db_path)

    assert db._conn is None

    with db._get_connection():
        pass

    assert db._conn is not None


def test_row_factory_is_set_on_the_shared_connection(tmp_path):
    db = CalendarDB(str(tmp_path / "rowfactory.sqlite"))
    _make_db(db.db_path)

    with db._get_connection() as conn:
        row = conn.execute("SELECT 1 AS answer").fetchone()

    # sqlite3.Row supports name-based access; a plain tuple does not.
    assert row["answer"] == 1


def test_close_is_idempotent_and_connection_reopens_on_demand(tmp_path):
    db = CalendarDB(str(tmp_path / "close.sqlite"))
    _make_db(db.db_path)

    with db._get_connection() as first:
        pass

    db.close()
    db.close()  # second call must not raise
    assert db._conn is None

    with db._get_connection() as reopened:
        assert reopened.execute("SELECT 1").fetchone()[0] == 1

    assert reopened is not first
