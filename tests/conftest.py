"""Session setup shared by every test.

``calendar.db`` is gitignored, so a fresh clone has none and every test
that renders through the CLI would fail on "Database file not found".  When
it is missing, one is built from the repo's SQL scripts and sample events
(``tools/db/build_db.py``) before the first test runs.  An existing database
is never touched.  Its patterns table is loaded from ``testdb/patterns``;
tests that build a temporary database use the ``temp_calendar_db`` fixture,
which does the same.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tools.db.build_db import TEST_PATTERNS_DIR

REPO_DB = Path(__file__).resolve().parent.parent / "calendar.db"


@pytest.fixture(scope="session", autouse=True)
def calendar_db() -> Path:
    if not REPO_DB.exists():
        from tools.db.build_db import build

        build(REPO_DB, patterns=TEST_PATTERNS_DIR)
    return REPO_DB


@pytest.fixture
def temp_calendar_db(tmp_path: Path) -> Path:
    """A throwaway database (schema, reference data, ``testdb/patterns`` tiles), no events."""
    from tools.db.build_db import build

    return build(tmp_path / "calendar.db", events=False, patterns=TEST_PATTERNS_DIR)
