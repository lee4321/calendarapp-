"""Session setup shared by every test.

``calendar.db`` is gitignored, so a fresh clone has none and every test
that renders through the CLI would fail on "Database file not found".  When
it is missing, one is built from the repo's SQL scripts and sample events
(``tools/db/build_db.py``) before the first test runs.  An existing database
is never touched.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_DB = Path(__file__).resolve().parent.parent / "calendar.db"


@pytest.fixture(scope="session", autouse=True)
def calendar_db() -> Path:
    if not REPO_DB.exists():
        from tools.db.build_db import build

        build(REPO_DB)
    return REPO_DB
