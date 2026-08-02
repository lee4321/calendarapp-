"""
Schema evolution for the `events` table.

Columns added after the original schema are declared here once and
applied by whoever opens the database first -- the importer when writing,
:class:`~shared.db_access.CalendarDB` when reading.  Keeping the list in
a module that imports nothing from either layer avoids a cycle
(`importers.common` already imports `CalendarDB`).

Migration is additive only: lazy ``ALTER TABLE ... ADD COLUMN`` per
missing column, existing rows untouched, re-running a no-op.
"""

from __future__ import annotations

import logging
import sqlite3

logger = logging.getLogger(__name__)

#: Columns added to `events` after the original schema, in the order the
#: canonical DDL (events.sql) declares them.  Keep the two in step: the
#: test suite asserts a migrated database matches a freshly created one.
EVENTS_SCHEMA_ADDITIONS: tuple[tuple[str, str], ...] = (
    ("source_id", "TEXT"),
    ("critical", "INTEGER"),
    ("start_time", "TEXT"),
    ("end_time", "TEXT"),
    ("duration_text", "TEXT"),
    ("effort_text", "TEXT"),
    ("actual_start_date", "TEXT"),
    ("actual_start_time", "TEXT"),
    ("actual_end_date", "TEXT"),
    ("actual_end_time", "TEXT"),
    ("deadline", "TEXT"),
    ("start_variance", "TEXT"),
    ("finish_variance", "TEXT"),
    ("fixed_cost", "REAL"),
    ("cost", "REAL"),
    ("percent_work_complete", "REAL"),
    ("successors", "TEXT"),
    ("custom1", "TEXT"),
    ("custom2", "TEXT"),
    ("custom3", "TEXT"),
    ("custom4", "TEXT"),
    ("custom5", "TEXT"),
)


def migrate_events_table(conn: sqlite3.Connection) -> list[str]:
    """Add any missing schedule-data-element columns to `events`.

    Safe to call on every connection: the existing columns are read once
    and only genuinely missing ones are added, so the steady-state cost
    is a single PRAGMA.

    A database that cannot be written -- opened read-only, or on a
    read-only filesystem -- is left alone with a warning rather than
    raising, so that opening such a file for *reading* still works.

    Args:
        conn: Open connection to a calendar database.

    Returns:
        Names of the columns actually added, in application order.
    """
    try:
        existing = {row[1] for row in conn.execute("PRAGMA table_info(events)")}
    except sqlite3.DatabaseError:
        logger.debug("events table not readable; skipping migration")
        return []

    if not existing:
        # No events table here (a fresh file, or some other database).
        # Creating it is the DDL's job, not ours.
        return []

    missing = [(c, d) for c, d in EVENTS_SCHEMA_ADDITIONS if c not in existing]
    if not missing:
        return []

    added: list[str] = []
    try:
        for column, decl in missing:
            conn.execute(f"ALTER TABLE events ADD COLUMN {column} {decl}")
            added.append(column)
        conn.commit()
    except sqlite3.OperationalError as exc:
        # Read-only database, or a concurrent writer got there first.
        logger.warning("could not migrate events table: %s", exc)
        return added

    logger.info("events table migrated: added %s", ", ".join(added))
    return added
