"""Shared table column model: every `events` column is nameable."""

from __future__ import annotations

import re
from dataclasses import fields
from pathlib import Path

from config.config import CalendarConfig
from renderers.table_columns import TableColumn, cell_value, resolve_field, resolve_table_columns
from shared.data_models import Event
from shared.events_schema import EVENTS_SCHEMA_ADDITIONS
from visualizers.gantt.columns import GanttColumn, resolve_columns

ROOT = Path(__file__).resolve().parent.parent


def _ddl_columns() -> list[str]:
    ddl = (ROOT / "tools" / "db" / "events.sql").read_text()
    body = ddl.split('CREATE TABLE IF NOT EXISTS "events"', 1)[1].split(");", 1)[0]
    return re.findall(r'^\s*"(\w+)"\s+\w+', body, flags=re.MULTILINE)


def test_every_events_column_resolves_to_an_event_attribute():
    """A new `events` column fails here until a table column can name it."""
    attrs = {f.name for f in fields(Event)}
    columns = set(_ddl_columns()) | {name for name, _decl in EVENTS_SCHEMA_ADDITIONS}
    assert len(columns) > 40
    missing = sorted(c for c in columns if resolve_field(c) not in attrs)
    assert missing == []


def test_bookkeeping_columns_come_through_from_dict():
    event = Event.from_dict({"Task_Name": "t", "Start": "20260101", "ID": 7, "User_ID": 2, "Import_ID": 3})
    assert (event.db_id, event.user_id, event.import_id) == (7, 2, 3)
    column = resolve_table_columns([{"field": "id"}], CalendarConfig())[0]
    assert cell_value(column, event) == "7"


def test_gantt_column_is_the_shared_column():
    assert GanttColumn is TableColumn
    config = CalendarConfig()
    assert resolve_columns(config) == resolve_table_columns(config.gantt_columns, config)


def test_max_chars_is_parsed_and_non_positive_ignored():
    config = CalendarConfig()
    cols = resolve_table_columns([{"field": "notes", "max_chars": 12}, {"field": "wbs", "max_chars": 0}], config)
    assert [c.max_chars for c in cols] == [12, None]


def test_date_format_accepts_timestamps():
    column = resolve_table_columns([{"field": "start_date", "date_format": "YYYY-MM-DD"}], CalendarConfig())[0]
    assert cell_value(column, Event(task_name="t", start="20260403T0900", end="20260403")) == "2026-04-03"
