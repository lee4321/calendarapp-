#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
sample_generator.py - Example event generator script for import_events.py

Usage:
    python import_events.py --generate generators/sample_generator.py
    python import_events.py -g generators/sample_generator.py --start-date 6/1/2026 --end-date 6/30/2026
    python import_events.py -g generators/sample_generator.py --param Priority=1 --param Icon=rocket
    python import_events.py -g generators/sample_generator.py --start-date 2026-06-01 --end-date 2026-06-30 --param Marks=Sprint

This script demonstrates the generator contract:
- Define a generate_events() function with optional keyword arguments
- Return a pandas DataFrame with Title_Case column names
- Required columns: Task_Name, Start_Date (or Finish_Date)
- Optional columns: Priority, WBS, Notes, Icon, Duration, etc.

The function can accept these keyword arguments from the CLI:
- start_date / end_date: YYYYMMDD strings (from --start-date / --end-date)
- Any key=value pair (from --param KEY=VALUE), e.g., Priority, Icon, Marks, Notes

Date formats: Any format parseable by dateutil (M/D/YYYY, YYYY-MM-DD, etc.)
"""

import pandas
from datetime import datetime, timedelta


def generate_events(start_date=None, end_date=None, **kwargs):
    """
    Generate sample calendar events.

    Can be called three ways:
    1. generate_events() - uses current week as the date range, default values
    2. generate_events(start_date="20260601", end_date="20260630") - uses provided range
    3. generate_events(start_date="20260601", end_date="20260630", Priority="1", Icon="rocket")

    Args:
        start_date: Optional start date in YYYYMMDD format (from --start-date)
        end_date: Optional end date in YYYYMMDD format (from --end-date)
        **kwargs: Additional parameters (from --param KEY=VALUE), e.g.:
            Priority, Milestone, Task_Name, Resource_Group, Notes, Icon,
            nonworkday, Marks - all arrive as strings

    Returns:
        pandas.DataFrame with Title_Case column names matching the CSV import contract.
    """
    # Determine the anchor date range
    if start_date and end_date:
        monday = datetime.strptime(start_date, "%Y%m%d").date()
    else:
        today = datetime.now().date()
        monday = today - timedelta(days=today.weekday())  # This week's Monday

    # Extract override values from kwargs (all arrive as strings)
    default_priority = int(kwargs.get("Priority", 0)) if "Priority" in kwargs else None
    default_icon = kwargs.get("Icon")
    default_notes = kwargs.get("Notes")
    default_marks = kwargs.get("Marks")
    default_resource_group = kwargs.get("Resource_Group")

    events = [
        {
            "Task_Name": "Sprint Planning",
            "Start_Date": monday.strftime("%m/%d/%Y"),
            "Finish_Date": monday.strftime("%m/%d/%Y"),
            "Priority": default_priority if default_priority is not None else 1,
            "Notes": default_notes or "Weekly sprint planning meeting",
            "Icon": default_icon or "calendar",
            "Resource_Names": "Team",
        },
        {
            "Task_Name": "Sprint 42",
            "Start_Date": monday.strftime("%m/%d/%Y"),
            "Finish_Date": (monday + timedelta(days=13)).strftime("%m/%d/%Y"),
            "Priority": default_priority if default_priority is not None else 2,
            "Duration": 10,
            "Notes": default_notes or "Two-week sprint",
            "Resource_Group": default_resource_group or "Engineering",
            "Marks": default_marks or "Sprint",
        },
        {
            "Task_Name": "Code Review Day",
            "Start_Date": (monday + timedelta(days=4)).strftime("%m/%d/%Y"),
            "Finish_Date": (monday + timedelta(days=4)).strftime("%m/%d/%Y"),
            "Priority": default_priority if default_priority is not None else 3,
            "Notes": default_notes or "Weekly code review",
            "Icon": default_icon or "star",
        },
        {
            "Task_Name": "Release v2.1",
            "Start_Date": (monday + timedelta(days=13)).strftime("%m/%d/%Y"),
            "Finish_Date": (monday + timedelta(days=13)).strftime("%m/%d/%Y"),
            "Priority": default_priority if default_priority is not None else 1,
            "Milestone": True,
            "Notes": default_notes or "Production release",
            "Icon": default_icon or "rocket",
        },
        {
            "Task_Name": "Team Retrospective",
            "Start_Date": (monday + timedelta(days=13)).strftime("%m/%d/%Y"),
            "Finish_Date": (monday + timedelta(days=13)).strftime("%m/%d/%Y"),
            "Priority": default_priority if default_priority is not None else 2,
            "Notes": default_notes or "Sprint retrospective",
            "Resource_Names": "Team",
        },
    ]

    return pandas.DataFrame(events)


if __name__ == "__main__":
    import sys

    # Parse command-line args for standalone testing
    # Usage: python sample_generator.py [start_date end_date] [key=value ...]
    # Example: python sample_generator.py 20260601 20260630 Priority=1 Icon=rocket
    cli_kwargs = {}
    positional = []

    for arg in sys.argv[1:]:
        if "=" in arg:
            key, value = arg.split("=", 1)
            cli_kwargs[key] = value
        else:
            positional.append(arg)

    if len(positional) >= 2:
        cli_kwargs["start_date"] = positional[0]
        cli_kwargs["end_date"] = positional[1]

    df = generate_events(**cli_kwargs)
    if cli_kwargs:
        print(f"Generated {len(df)} events with params: {cli_kwargs}")
    else:
        print(f"Generated {len(df)} events (default range):")
    print(df.to_string(index=False))
