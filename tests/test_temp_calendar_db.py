"""The ``temp_calendar_db`` fixture fills patterns from ``testdb/patterns``."""

import sqlite3

from tools.db.build_db import TEST_PATTERNS_DIR


def test_temp_db_patterns_match_testdb_folder(temp_calendar_db):
    with sqlite3.connect(temp_calendar_db) as conn:
        names = {n for (n,) in conn.execute("SELECT name FROM patterns")}
    assert names == {f.stem for f in TEST_PATTERNS_DIR.glob("*.svg")}
    assert names
