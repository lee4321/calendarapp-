"""
Data models for calendar events and special days.

Provides normalized data structures used across all visualization types.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


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
    notes: Optional[str] = None
    icon: Optional[str] = None
    resource_group: Optional[str] = None
    resource_names: Optional[str] = None  # comma-separated individual resource names
    percent_complete: float = 0.0
    milestone: bool = False
    rollup: bool = False
    datekey: Optional[str] = None
    priority: int = 0
    wbs: Optional[str] = None
    color: Optional[str] = None

    @classmethod
    def from_dict(cls, data: dict) -> "Event":
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
    icon: Optional[str] = None
    nonworkday: bool = False
    hash_pattern: int = 0
    country: Optional[str] = None

    @classmethod
    def from_dict(cls, data: dict) -> "SpecialDay":
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
            hash_pattern=data.get("hash_pattern", data.get("marks", 0)) or 0,
            country=data.get("country"),
        )
