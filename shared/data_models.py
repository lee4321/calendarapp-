"""
Data models for calendar events and special days.

Provides normalized data structures used across all visualization types.
"""

from __future__ import annotations

from dataclasses import dataclass

# Allowed values for events.status. Unknown values are accepted by the
# importer (stored as-is) but render as if 'active'.
ALLOWED_STATUSES: frozenset[str] = frozenset({"active", "draft", "cancelled", "archived", "on-hold"})


@dataclass(frozen=True)
class Event:
    """
    Normalized event for all visualizers.

    This dataclass provides a consistent interface for event data
    regardless of the underlying data source.
    """

    task_name: str
    start: str  # YYYYMMDD
    end: str  # YYYYMMDD
    notes: str | None = None
    icon: str | None = None
    resource_group: str | None = None
    resource_names: str | None = None  # comma-separated individual resource names
    percent_complete: float = 0.0
    milestone: bool = False
    rollup: bool = False
    datekey: str | None = None
    priority: int = 0
    wbs: str | None = None
    color: str | None = None
    status: str = "active"

    # Schedule data elements.  All optional: rows imported before these
    # columns existed, and files that omit the columns, leave them unset.
    source_id: str | None = None
    critical: bool = False
    start_time: str | None = None  # HHMM
    end_time: str | None = None  # HHMM
    duration: float | None = None  # decimal days
    duration_text: str | None = None  # source string, e.g. "4hr"
    effort: float | None = None  # decimal days
    effort_text: str | None = None  # source string, e.g. "0.5d"
    actual_start_date: str | None = None
    actual_start_time: str | None = None
    actual_end_date: str | None = None
    actual_end_time: str | None = None
    # Schedule window (float).  Populated only by tools that export a
    # critical-path analysis; the Gantt draws float bars when they are
    # present and simply omits them when they are not.
    earliest_start_date: str | None = None  # YYYYMMDD
    latest_start_date: str | None = None  # YYYYMMDD
    earliest_end_date: str | None = None  # YYYYMMDD
    latest_end_date: str | None = None  # YYYYMMDD
    deadline: str | None = None
    start_variance: str | None = None
    finish_variance: str | None = None
    cost: float | None = None
    fixed_cost: float | None = None
    percent_work_complete: float = 0.0
    predecessors: str | None = None
    successors: str | None = None
    tags: str | None = None
    custom1: str | None = None
    custom2: str | None = None
    custom3: str | None = None
    custom4: str | None = None
    custom5: str | None = None
    # Database bookkeeping: the row's primary key and provenance.  Listed
    # so every `events` column can be named in a table column; the `id`
    # column resolves to ``db_id`` (``id`` would shadow the builtin).
    db_id: int | None = None
    user_id: int | None = None
    import_id: int | None = None

    @classmethod
    def from_dict(cls, data: dict) -> Event:
        """
        Create an Event from a dictionary (e.g., database row).

        Args:
            data: Dictionary with event data

        Returns:
            Event instance
        """
        return cls(
            task_name=data.get("Task_Name", ""),
            start=str(data.get("Start", "")),
            end=str(data.get("End") or data.get("Finish") or data.get("Start", "")),
            notes=data.get("Notes"),
            icon=data.get("Icon"),
            resource_group=data.get("Resource_Group"),
            resource_names=data.get("Resource_Name") or data.get("Resource_Names"),
            percent_complete=data.get("Percent_Complete", 0.0) or 0.0,
            milestone=bool(data.get("Milestone")),
            rollup=bool(data.get("Rollup")),
            datekey=data.get("Datekey") or data.get("datekey"),
            priority=data.get("Priority", 0) or 0,
            wbs=data.get("WBS"),
            color=data.get("Color") or data.get("color") or None,
            status=(data.get("Status") or "active"),
            source_id=data.get("Source_ID"),
            critical=bool(data.get("Critical")),
            start_time=data.get("Start_Time"),
            end_time=data.get("End_Time"),
            duration=data.get("Duration"),
            duration_text=data.get("Duration_Text"),
            effort=data.get("Effort"),
            effort_text=data.get("Effort_Text"),
            actual_start_date=data.get("Actual_Start_Date"),
            actual_start_time=data.get("Actual_Start_Time"),
            actual_end_date=data.get("Actual_End_Date"),
            actual_end_time=data.get("Actual_End_Time"),
            earliest_start_date=data.get("Earliest_Start_Date"),
            latest_start_date=data.get("Latest_Start_Date"),
            earliest_end_date=data.get("Earliest_End_Date"),
            latest_end_date=data.get("Latest_End_Date"),
            deadline=data.get("Deadline"),
            start_variance=data.get("Start_Variance"),
            finish_variance=data.get("Finish_Variance"),
            cost=data.get("Cost"),
            fixed_cost=data.get("Fixed_Cost"),
            percent_work_complete=data.get("Percent_Work_Complete", 0.0) or 0.0,
            predecessors=data.get("Predecessors"),
            successors=data.get("Successors"),
            tags=data.get("Tags"),
            custom1=data.get("Custom1"),
            custom2=data.get("Custom2"),
            custom3=data.get("Custom3"),
            custom4=data.get("Custom4"),
            custom5=data.get("Custom5"),
            db_id=data.get("ID"),
            user_id=data.get("User_ID"),
            import_id=data.get("Import_ID"),
        )

    @property
    def is_duration(self) -> bool:
        """Check if this event spans multiple days."""
        return self.start != self.end


@dataclass(frozen=True)
class SpecialDay:
    """
    Holiday or company special day.

    Represents days with special meaning (holidays, company events, etc.)
    that may affect the calendar display.
    """

    title: str
    icon: str | None = None
    nonworkday: bool = False
    hash_pattern: int = 0
    country: str | None = None

    @classmethod
    def from_dict(cls, data: dict) -> SpecialDay:
        """
        Create a SpecialDay from a dictionary.

        Args:
            data: Dictionary with special day data

        Returns:
            SpecialDay instance
        """
        return cls(
            title=data.get("title", data.get("Holiday", "")),
            icon=data.get("icon", data.get("Icon")),
            nonworkday=bool(data.get("nonworkday", False)),
            hash_pattern=data.get("hash_pattern", data.get("tags", 0)) or 0,
            country=data.get("country"),
        )
