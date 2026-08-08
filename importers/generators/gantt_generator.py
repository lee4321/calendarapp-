#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
gantt_generator.py - Gantt test-data generator for import_events.py

Usage:
    python importers/import_events.py --generate importers/generators/gantt_generator.py
    python importers/import_events.py -g importers/generators/gantt_generator.py --start-date 2026-09-07

Produces a ~40-task programme that exercises every path the Gantt
visualization has to handle.  The schedule data most project managers
never export -- WBS, predecessors, float dates -- is fully populated here
precisely because the shipping `calendar.db` has none of it, so this is
the dataset the Gantt renderer is developed and tested against.

Deliberate edge cases, one row each unless noted:

* Three-level WBS (1 / 3.1 / 3.1.1) with real rollup rows -- no rollup is
  synthesized by the renderer, so every parent exists as a task.
* WBS 1.9 before 1.10, which only sorts correctly under segment-wise
  numeric ordering.
* All four link types, positive/negative lag, week lag, percentage lag
  ("+50%") and elapsed lag ("+3ed"), plus a multi-predecessor list.
* A backward link, where the successor starts before its predecessor
  ends, forcing the three-segment dogleg route.
* A forward reference: a predecessor defined later in the table.
* A predecessor pointing at a cancelled task, which the default
  `--status active` filter removes -- the off-chart dependency stub.
* An unparseable predecessor token ("FS+3d", no reference) and an
  unresolvable one ("TBD") -- the two distinct details-page reports.
* A task spanning far outside any sensible chart range, for the
  continuation icons at both ends.
* A single-day event on a Saturday, which snaps forward when weekends
  are hidden.
* Tasks with and without float dates, 0%/partial/100% complete, notes
  long enough to truncate, deadlines, and rows with no WBS at all.

Dates are business-day offsets from an anchor Monday, so the programme
lands on weekdays regardless of when it is generated.  The one Saturday
row is placed by calendar offset on purpose.
"""

import pandas
from datetime import date, datetime, timedelta

#: Anchor-relative float offsets, in business days, applied as
#: (earliest_start, latest_start, earliest_finish, latest_finish) around a
#: task's own start and end.
_FLOAT = (-3, 2, -2, 5)


def _monday_of(day: date) -> date:
    """The Monday of *day*'s week."""
    return day - timedelta(days=day.weekday())


def _add_workdays(start: date, count: int) -> date:
    """Shift *start* by *count* business days, forward or backward.

    Weekends are skipped, so every generated date is a weekday and the
    programme reads the same whichever day it is generated on.
    """
    step = 1 if count >= 0 else -1
    remaining = abs(count)
    current = start
    while remaining:
        current += timedelta(days=step)
        if current.weekday() < 5:
            remaining -= 1
    return current


# ── The programme ──────────────────────────────────────────────────────────
#
# Keys, all optional past `sid`/`wbs`/`name`/`start`:
#   sid    source_id -- what predecessors reference
#   start  business-day offset from the anchor Monday
#   days   business-day length; 0 means a milestone / single-day event
#   cal    calendar-day offset, used instead of `start` (the Saturday row)
#   pred   raw predecessor cell, written exactly as a scheduling tool would
#   pct    percent complete, 0.0-1.0
#   roll   rollup (summary) row
#   ms     milestone
#   flt    attach float dates using _FLOAT
#   dl     deadline, as a business-day offset from the task's end
#
_TASKS: list[dict] = [
    # ── 1 Program Management ──────────────────────────────────────────────
    dict(sid="1", wbs="1", name="Program Management", start=0, days=150,
         roll=True, grp="PMO", res="Program Director"),
    dict(sid="2", wbs="1.1", name="Program Kickoff", start=0, ms=True, pct=1.0,
         grp="PMO", res="Program Director", notes="Charter signed by steering committee"),
    dict(sid="3", wbs="1.2", name="Governance Cadence Setup", start=1, days=4,
         pred="2FS+1d", pct=1.0, grp="PMO", res="PMO Analyst"),
    dict(sid="4", wbs="1.3", name="Charter Approved", start=5, ms=True, pred="3",
         pct=1.0, grp="PMO", res="Steering Committee"),
    dict(sid="5", wbs="1.9", name="Steering Review Q2", start=40, days=1,
         grp="PMO", res="Steering Committee", pri=1),
    dict(sid="6", wbs="1.10", name="Steering Review Q3", start=80, days=1,
         grp="PMO", res="Steering Committee", pri=1),

    # ── 2 Discovery ───────────────────────────────────────────────────────
    dict(sid="10", wbs="2", name="Discovery", start=2, days=25, roll=True,
         grp="Delivery"),
    dict(sid="11", wbs="2.1", name="Stakeholder Interviews", start=2, days=10,
         pred="2", pct=1.0, flt=True, grp="Delivery", res="Business Analyst",
         notes="Thirty-two interviews across finance, operations, treasury and "
               "the regional service desks; transcripts in the programme wiki"),
    dict(sid="12", wbs="2.2", name="Current-State Assessment", start=7, days=8,
         pred="11SS+3d", pct=1.0, grp="Delivery", res="Business Analyst"),
    dict(sid="13", wbs="2.3", name="Data Inventory", start=12, days=6,
         pred="12", pct=0.75, grp="Delivery", res="Data Architect"),
    dict(sid="14", wbs="2.4", name="Requirements Workshop", start=18, days=3,
         pred="13FS-1d", pct=0.5, grp="Delivery", res="Business Analyst,Data Architect"),
    dict(sid="15", wbs="2.5", name="Gap Analysis", start=21, days=5,
         pred="14,12FF+2d", pct=0.25, grp="Delivery", res="Business Analyst"),
    dict(sid="16", wbs="2.6", name="Vendor Selection", start=15, days=6,
         pred="TBD", grp="Procurement", res="Sourcing Lead",
         notes="Predecessor never resolved -- reported on the details page"),
    dict(sid="17", wbs="2.7", name="Discovery Signoff", start=26, ms=True,
         pred="15", dl=3, grp="Delivery", res="Program Director"),

    # ── 3 Build ───────────────────────────────────────────────────────────
    dict(sid="20", wbs="3", name="Build", start=27, days=60, roll=True,
         grp="Engineering"),
    dict(sid="21", wbs="3.1", name="Platform Core", start=27, days=35, roll=True,
         grp="Engineering"),
    dict(sid="22", wbs="3.1.1", name="Environment Provisioning", start=27, days=8,
         pred="17", pct=1.0, grp="Engineering", res="Platform Engineer"),
    dict(sid="23", wbs="3.1.2", name="Identity Integration", start=33, days=10,
         pred="22SS+4d", pct=0.6, grp="Engineering", res="Security Engineer"),
    dict(sid="24", wbs="3.1.3", name="Ledger Migration", start=41, days=12,
         pred="23", pct=0.3, flt=True, grp="Engineering", res="Data Architect", pri=1),
    dict(sid="25", wbs="3.1.4", name="Core Hardening", start=51, days=6,
         pred="24FF-3d", pct=0.0, grp="Engineering", res="Security Engineer"),
    dict(sid="26", wbs="3.2", name="Payments", start=40, days=26, roll=True,
         grp="Engineering"),
    dict(sid="27", wbs="3.2.1", name="Gateway Adapter", start=40, days=14,
         pred="23FS+2d", pct=0.4, grp="Engineering", res="Payments Engineer"),
    dict(sid="28", wbs="3.2.2", name="Settlement Engine", start=50, days=12,
         pred="27SS+5d", pct=0.1, grp="Engineering", res="Payments Engineer"),
    dict(sid="29", wbs="3.2.3", name="Reconciliation Rules", start=58, days=8,
         pred="28FF,27SF", grp="Engineering", res="Payments Engineer"),
    dict(sid="30", wbs="3.3", name="Reporting", start=45, days=22, roll=True,
         grp="Engineering"),
    dict(sid="31", wbs="3.3.1", name="Warehouse Schema", start=45, days=10,
         pred="24SS", pct=0.2, grp="Engineering", res="Data Architect"),
    dict(sid="32", wbs="3.3.2", name="Dashboard Build", start=55, days=12,
         pred="31FS+1w", grp="Engineering", res="Reporting Analyst"),
    # Backward link: 33 starts before its predecessor 32 finishes.
    dict(sid="33", wbs="3.3.3", name="Report Validation", start=58, days=5,
         pred="32", grp="Engineering", res="Reporting Analyst",
         notes="Starts before its predecessor ends -- dogleg route"),
    # Forward reference: 34's predecessor 40 appears later in the table.
    dict(sid="34", wbs="3.4", name="Build Complete", start=87, ms=True,
         pred="25,29,32,40", dl=5, grp="Engineering", res="Delivery Lead"),
    dict(sid="35", wbs="3.5", name="Vendor Support Retainer", start=-20, days=200,
         grp="Procurement", res="Sourcing Lead",
         notes="Spans well outside any chart range -- continuation icons both ends"),
    dict(sid="36", wbs="3.6", name="Security Review", start=60, days=4,
         pred="FS+3d", grp="Engineering", res="Security Engineer",
         notes="Predecessor cell has no reference -- reported as unparseable"),

    # ── 4 Rollout ─────────────────────────────────────────────────────────
    dict(sid="40", wbs="4", name="Rollout", start=88, days=52, roll=True,
         grp="Operations"),
    dict(sid="41", wbs="4.1", name="Pilot Wave", start=88, days=10, pred="34",
         grp="Operations", res="Rollout Manager", pri=1),
    dict(sid="42", wbs="4.2", name="Wave 1", start=95, days=15, pred="41FS+50%",
         flt=True, grp="Operations", res="Rollout Manager"),
    dict(sid="43", wbs="4.3", name="Wave 2", start=108, days=15, pred="42SS+10d",
         grp="Operations", res="Rollout Manager"),
    dict(sid="44", wbs="4.4", name="Hypercare", start=120, days=20,
         pred="43FF+3ed", grp="Operations", res="Support Lead"),
    dict(sid="45", wbs="4.5", name="Legacy Cutover", start=130, days=3,
         pred="90FS+2d", grp="Operations", res="Platform Engineer",
         notes="Predecessor is a cancelled task -- off-chart dependency stub"),
    dict(sid="46", wbs="4.6", name="Rollout Complete", start=140, ms=True,
         pred="44,45", grp="Operations", res="Rollout Manager"),

    # ── 5 Closeout ────────────────────────────────────────────────────────
    dict(sid="50", wbs="5", name="Closeout", start=141, days=10, roll=True,
         grp="PMO"),
    dict(sid="51", wbs="5.1", name="Benefits Review", start=141, days=5,
         pred="46", grp="PMO", res="PMO Analyst"),
    dict(sid="52", wbs="5.2", name="Lessons Learned", start=144, days=3,
         pred="51SS+2d", grp="PMO", res="PMO Analyst"),
    dict(sid="53", wbs="5.3", name="Program Close", start=150, ms=True,
         pred="51,52", dl=0, grp="PMO", res="Program Director"),

    # ── Filtered out by the default --status active ────────────────────────
    dict(sid="90", wbs="6.1", name="Legacy Decommission", start=125, days=8,
         status="cancelled", grp="Operations", res="Platform Engineer"),

    # ── No WBS: sort into their own block after every WBS row ──────────────
    dict(sid="80", name="Executive Briefing", start=30, days=1, grp="PMO",
         res="Program Director"),
    dict(sid="81", name="Weekend Cutover Rehearsal", cal=26, days=0,
         grp="Operations", res="Platform Engineer",
         notes="Falls on a Saturday -- snaps forward when weekends are hidden"),
    dict(sid="82", name="Ad-hoc Risk Review", start=64, days=2, grp="PMO",
         res="Risk Manager", pri=1),
]


def _build_row(task: dict, anchor: date) -> dict:
    """Turn one table entry into an import row with real dates."""
    days = task.get("days", 0)

    if "cal" in task:
        start = anchor + timedelta(days=task["cal"])
        end = start + timedelta(days=max(days - 1, 0))
    else:
        start = _add_workdays(anchor, task["start"])
        end = _add_workdays(start, max(days - 1, 0))

    is_milestone = bool(task.get("ms"))
    row = {
        "ID": task["sid"],
        "WBS": task.get("wbs", ""),
        "Task_Name": task["name"],
        "Start_Date": start.strftime("%Y-%m-%d"),
        "Finish_Date": end.strftime("%Y-%m-%d"),
        "Duration": "0 days" if is_milestone else f"{max(days, 1)} days",
        "Effort": "0 hrs" if is_milestone else f"{max(days, 1) * 8} hrs",
        "Predecessors": task.get("pred", ""),
        "Percent_Complete": task.get("pct", 0.0),
        "Rollup": bool(task.get("roll")),
        "Milestone": is_milestone,
        "Status": task.get("status", "active"),
        "Priority": task.get("pri", 2),
        "Resource_Names": task.get("res", ""),
        "Resource_Group": task.get("grp", ""),
        "Notes": task.get("notes", ""),
        "Deadline": "",
        "Earliest_Start": "",
        "Latest_Start": "",
        "Earliest_Finish": "",
        "Latest_Finish": "",
    }

    if "dl" in task:
        row["Deadline"] = _add_workdays(end, task["dl"]).strftime("%Y-%m-%d")

    if task.get("flt"):
        early_start, late_start, early_finish, late_finish = _FLOAT
        row["Earliest_Start"] = _add_workdays(start, early_start).strftime("%Y-%m-%d")
        row["Latest_Start"] = _add_workdays(start, late_start).strftime("%Y-%m-%d")
        row["Earliest_Finish"] = _add_workdays(end, early_finish).strftime("%Y-%m-%d")
        row["Latest_Finish"] = _add_workdays(end, late_finish).strftime("%Y-%m-%d")

    return row


def generate_events(start_date=None, end_date=None, **kwargs):
    """
    Generate the Gantt test programme.

    Args:
        start_date: Optional anchor in YYYYMMDD format (from --start-date).
            Snapped back to that week's Monday.  Defaults to the current
            week's Monday.
        end_date: Accepted for contract compatibility; the programme's
            length is fixed by its own schedule.
        **kwargs: Accepted and ignored -- every field this generator sets
            is deliberate, so overriding one would defeat the fixtures.

    Returns:
        pandas.DataFrame with Title_Case column names matching the CSV
        import contract.
    """
    if start_date:
        anchor = _monday_of(datetime.strptime(start_date, "%Y%m%d").date())
    else:
        anchor = _monday_of(datetime.now().date())

    return pandas.DataFrame([_build_row(task, anchor) for task in _TASKS])


if __name__ == "__main__":
    import sys

    cli_kwargs = {}
    positional = []

    for arg in sys.argv[1:]:
        if "=" in arg:
            key, value = arg.split("=", 1)
            cli_kwargs[key] = value
        else:
            positional.append(arg)

    if positional:
        cli_kwargs["start_date"] = positional[0]

    df = generate_events(**cli_kwargs)
    print(f"Generated {len(df)} tasks")
    print(df.to_string(index=False))
