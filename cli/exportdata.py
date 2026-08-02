"""
CSV export for the ``exportdata`` subcommand.

Converts filtered Event dicts into the canonical import-compatible CSV
column set, so an exportdata round-trip can be re-imported by
``importers/import_events.py``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

#: Column headers written to the export CSV.  These match the primary alias
#: keys in importers/import_events.py COLUMN_MAPPING so the file can be
#: re-imported without relying on fallback aliases.
_EXPORTDATA_COLUMNS: list[str] = [
    "task_name",
    "status",
    "start_date",
    "finish_date",
    "earliest_start_date",
    "latest_start_date",
    "earliest_end_date",
    "latest_end_date",
    "priority",
    "wbs",
    "rollup",
    "milestone",
    "percent_complete",
    "effort",
    "duration",
    "predecessors",
    "resource_names",
    "resource_group",
    "notes",
    "icon",
    "color",
    "tags",
    # Schedule data elements.  Times ride along inside the date columns
    # as an ISO "T" suffix, which the importer re-splits on read, so the
    # round trip stays lossless without separate time columns.
    "id",
    "critical",
    "actual_start_date",
    "actual_end_date",
    "deadline",
    "start_variance",
    "finish_variance",
    "cost",
    "fixed_cost",
    "percent_work_complete",
    "successors",
    "custom1",
    "custom2",
    "custom3",
    "custom4",
    "custom5",
]


def _fmt_date(d: str | None, time: str | None = None) -> str:
    """Convert YYYYMMDD → YYYY-MM-DD, appending an HHMM time as "THH:MM".

    Other strings are left untouched.  The importer accepts both the
    plain-date and the date-with-time forms.
    """
    if d and len(d) == 8 and d.isdigit():
        d = f"{d[:4]}-{d[4:6]}-{d[6:]}"
    elif not d:
        return ""
    if time and len(str(time)) == 4 and str(time).isdigit():
        return f"{d}T{str(time)[:2]}:{str(time)[2:]}"
    return d


def _fmt_duration(ev: dict, text_key: str, numeric_key: str) -> str:
    """Prefer the verbatim source duration; fall back to decimal days."""
    text = ev.get(text_key)
    if text:
        return text
    value = ev.get(numeric_key)
    return "" if value is None else value


def _event_to_row(ev: dict) -> dict:
    """Map a raw database event dict to an exportdata CSV row dict."""
    return {
        "task_name": ev.get("Task_Name", ""),
        "status": ev.get("Status", ""),
        "start_date": _fmt_date(
            ev.get("Start") or ev.get("Start_Date"), ev.get("Start_Time")
        ),
        "finish_date": _fmt_date(
            ev.get("End") or ev.get("Finish_Date"), ev.get("End_Time")
        ),
        "earliest_start_date": _fmt_date(ev.get("Earliest_Start_Date")),
        "latest_start_date": _fmt_date(ev.get("Latest_Start_Date")),
        "earliest_end_date": _fmt_date(ev.get("Earliest_End_Date")),
        "latest_end_date": _fmt_date(ev.get("Latest_End_Date")),
        "priority": ev.get("Priority", ""),
        "wbs": ev.get("WBS", ""),
        "rollup": ev.get("Rollup", ""),
        "milestone": ev.get("Milestone", ""),
        "percent_complete": ev.get("Percent_Complete", ""),
        "effort": _fmt_duration(ev, "Effort_Text", "Effort"),
        "duration": _fmt_duration(ev, "Duration_Text", "Duration"),
        "predecessors": ev.get("Predecessors", ""),
        "resource_names": ev.get("Resource_Names", ""),
        "resource_group": ev.get("Resource_Group", ""),
        "notes": ev.get("Notes", ""),
        "icon": ev.get("Icon", ""),
        "color": ev.get("Color", ""),
        "tags": ev.get("Tags", ""),
        "id": ev.get("Source_ID", ""),
        "critical": ev.get("Critical", ""),
        "actual_start_date": _fmt_date(
            ev.get("Actual_Start_Date"), ev.get("Actual_Start_Time")
        ),
        "actual_end_date": _fmt_date(
            ev.get("Actual_End_Date"), ev.get("Actual_End_Time")
        ),
        "deadline": _fmt_date(ev.get("Deadline")),
        "start_variance": ev.get("Start_Variance", ""),
        "finish_variance": ev.get("Finish_Variance", ""),
        "cost": ev.get("Cost", ""),
        "fixed_cost": ev.get("Fixed_Cost", ""),
        "percent_work_complete": ev.get("Percent_Work_Complete", ""),
        "successors": ev.get("Successors", ""),
        "custom1": ev.get("Custom1", ""),
        "custom2": ev.get("Custom2", ""),
        "custom3": ev.get("Custom3", ""),
        "custom4": ev.get("Custom4", ""),
        "custom5": ev.get("Custom5", ""),
    }


def _events_to_csv_string(events: list[dict]) -> str:
    """Convert raw event dicts to a CSV string using the exportdata format."""
    import csv
    import io

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=_EXPORTDATA_COLUMNS, extrasaction="ignore")
    writer.writeheader()
    for ev in events:
        writer.writerow(_event_to_row(ev))
    return buf.getvalue()


def _write_exportdata_csv(events: list[dict], out_path: "Path") -> None:
    """
    Write filtered events to a CSV file compatible with importers/import_events.py.

    Dates are converted from YYYYMMDD compact strings to YYYY-MM-DD ISO format
    (the importer accepts both).  All other fields are written as-is from the
    raw database dictionaries returned by CalendarDB.get_all_events_in_range().

    Called by:
        run() when args.command == "exportdata".
    """
    csv_text = _events_to_csv_string(events)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", newline="", encoding="utf-8") as fh:
        fh.write(csv_text)

