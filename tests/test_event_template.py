"""The shipped Excel template must stay importable.

templates/event_template.xlsx is what new users start from, so a header
the importer no longer recognizes is a silent data-loss bug.  These
tests read the committed file and push it through the real importer.
"""

import sqlite3
from pathlib import Path

import pandas
import pytest

from importers.common import read_file
from importers.import_events import ImportDatabase, import_file, lookup_column

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = ROOT / "templates" / "event_template.xlsx"

MANDATORY_COLUMNS = {"Name", "Start", "Finish"}


@pytest.fixture(scope="module")
def headers() -> list[str]:
    return list(pandas.read_excel(TEMPLATE, sheet_name="Events").columns)


def test_template_exists():
    assert TEMPLATE.is_file(), f"missing template: {TEMPLATE}"


def test_every_header_is_recognized(headers):
    unmapped = [h for h in headers if lookup_column(h) is None]
    assert not unmapped, f"template headers the importer ignores: {unmapped}"


def test_no_two_headers_target_the_same_column(headers):
    """Two columns mapping to one DB field means one is silently dropped."""
    seen: dict[str, str] = {}
    collisions = []
    for header in headers:
        db_col = lookup_column(header)
        if db_col in seen:
            collisions.append((seen[db_col], header, db_col))
        seen[db_col] = header
    assert not collisions, f"colliding template headers: {collisions}"


def test_mandatory_columns_present(headers):
    assert MANDATORY_COLUMNS <= set(headers)


def test_has_a_data_dictionary_sheet():
    sheets = pandas.ExcelFile(TEMPLATE).sheet_names
    assert "Events" in sheets
    assert "Data Dictionary" in sheets


def test_events_sheet_is_selected_not_the_dictionary():
    """read_file must prefer the Events sheet regardless of sheet order."""
    df = read_file(str(TEMPLATE))
    assert "Name" in df.columns
    assert "Column Name" not in df.columns  # that is the dictionary's header


def test_example_rows_import_cleanly(tmp_path):
    db_path = str(tmp_path / "calendar.sqlite")
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript((ROOT / "events.sql").read_text())
        conn.execute(
            "CREATE TABLE import_history (id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "userid TEXT, filename TEXT, date TEXT, filehash TEXT, command TEXT)"
        )
        conn.commit()
    finally:
        conn.close()

    db = ImportDatabase(db_path)
    result = import_file(db, str(TEMPLATE), user_id=1)

    assert result.errors == []
    assert result.failed_rows == 0
    assert result.imported_rows == result.total_rows > 0


def test_first_example_row_lands_in_the_right_columns(tmp_path):
    """The worked example from the spec, end to end."""
    db_path = str(tmp_path / "calendar.sqlite")
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript((ROOT / "events.sql").read_text())
        conn.execute(
            "CREATE TABLE import_history (id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "userid TEXT, filename TEXT, date TEXT, filehash TEXT, command TEXT)"
        )
        conn.commit()
    finally:
        conn.close()

    import_file(ImportDatabase(db_path), str(TEMPLATE), user_id=1)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute("SELECT * FROM events WHERE name = 'Ditch'").fetchone()
    finally:
        conn.close()

    assert row is not None, "the 'Ditch' example row did not import"
    assert row["source_id"] == "143"
    assert row["wbs"] == "PROJ1.Act1.Task.143"
    assert row["priority"] == 77
    assert (row["start_date"], row["start_time"]) == ("20260602", "1230")
    assert (row["end_date"], row["end_time"]) == ("20260602", "1630")
    assert (row["duration_text"], row["duration"]) == ("4hr", 0.5)
    assert (row["effort_text"], row["effort"]) == ("0.5d", 0.5)
    assert row["earliest_start_date"] == "20260523"
    assert row["latest_end_date"] == "20260603"
    assert (row["actual_start_date"], row["actual_start_time"]) == ("20260602", "0800")
    assert row["deadline"] == "20260630"
    assert row["start_variance"] == "-4h"
    assert row["fixed_cost"] == 250.0
    assert row["cost"] == 200.0
    assert row["percent_complete"] == 1.0
    assert row["percent_work_complete"] == 1.0
    assert row["resource_names"] == "Pete, Garcia"
    assert row["resource_group"] == "Facilities"
    assert row["predecessors"] == "123"
    assert row["successors"] == "258"
    assert row["icon"] == "shovel"
    assert row["color"] == "Green"
    assert row["tags"] == "Construction, Grounds"
    assert row["custom3"] == "CoA: 99345B2026"
    assert row["milestone"] == 0
    assert row["rollup"] == 0
    assert row["critical"] == 0
