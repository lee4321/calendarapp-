"""
Shared helpers for *icon-type* timebands.

An icon band (``unit: "icon"``) places one or more SVG icons into each day
cell based on a theme-configured list of rules.  Each rule specifies match
criteria for events/milestones and the icon name + colour to display when an
event falls on a given day.

Rule dict keys (all optional except ``icon``):
    icon           : str  — icon name from the icons table (required)
    color          : str  — fill colour for the icon (default "#333333")
    milestone      : bool — match milestone flag exactly
    event_type     : str  — "milestone" or "duration"
    task_contains  : str  — case-insensitive substring of task_name
    resource_group : str  — exact match on resource_group
    notes_contains : str  — case-insensitive substring of notes
    rollup         : bool — exact match on rollup flag
    priority       : int  — exact match (ignored when min/max present)
    priority_min   : int  — inclusive lower bound on priority
    priority_max   : int  — inclusive upper bound on priority
    wbs_prefixes   : list[str] — event.wbs must start with one of these
"""
from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from shared.data_models import Event


def icon_rule_matches(event: "Event", rule: dict[str, Any]) -> bool:
    """Return True if *event* satisfies every criterion in *rule*."""
    # milestone: bool — exact match
    if "milestone" in rule:
        if bool(event.milestone) != bool(rule["milestone"]):
            return False
    # event_type: "milestone" | "duration"
    if "event_type" in rule:
        et = str(rule["event_type"]).strip().lower()
        if et == "milestone" and not event.milestone:
            return False
        if et in {"duration", "task"} and event.milestone:
            return False
    # task_contains: str — case-insensitive substring
    if "task_contains" in rule:
        if str(rule["task_contains"]).lower() not in (event.task_name or "").lower():
            return False
    # resource_group: str — exact match
    if "resource_group" in rule:
        if (event.resource_group or "") != str(rule["resource_group"]):
            return False
    # notes_contains: str — case-insensitive substring
    if "notes_contains" in rule:
        if str(rule["notes_contains"]).lower() not in (event.notes or "").lower():
            return False
    # rollup: bool — exact match
    if "rollup" in rule:
        if bool(event.rollup) != bool(rule["rollup"]):
            return False
    # priority: int — exact match (superseded by min/max if both present)
    if "priority" in rule and "priority_min" not in rule and "priority_max" not in rule:
        if event.priority != int(rule["priority"]):
            return False
    # priority_min / priority_max — inclusive range
    if "priority_min" in rule:
        if event.priority < int(rule["priority_min"]):
            return False
    if "priority_max" in rule:
        if event.priority > int(rule["priority_max"]):
            return False
    # wbs_prefixes: list[str] — at least one prefix must match
    if "wbs_prefixes" in rule:
        wbs = event.wbs or ""
        if not any(wbs.startswith(str(p)) for p in rule["wbs_prefixes"]):
            return False
    return True


def compute_icon_band_days(
    events: "list[Event]",
    rules: list[dict[str, Any]],
    visible_days: list[date],
) -> dict[date, list[tuple[str, str]]]:
    """
    Return ``{day: [(icon_name, color), ...]}`` for every day in
    *visible_days*.

    * Milestones are placed on ``event.datekey or event.start``.
    * Duration events are placed on ``event.start``.
    * All matching rules for a given event are applied.
    * Icons are deduplicated by name — the same icon appears at most once per
      day regardless of how many events or rules trigger it.

    Parameters
    ----------
    events:
        Full event list (milestones + durations).
    rules:
        List of rule dicts from the band's ``icon_rules`` key.
    visible_days:
        Ordered list of visible calendar dates.
    """
    if not rules:
        return {d: [] for d in visible_days}

    visible_set: set[date] = set(visible_days)
    day_icons: dict[date, list[tuple[str, str]]] = {d: [] for d in visible_days}
    day_seen: dict[date, set[str]] = {d: set() for d in visible_days}

    for event in events:
        date_str = (
            (event.datekey or event.start) if event.milestone else event.start
        )
        try:
            evt_date = date(int(date_str[:4]), int(date_str[4:6]), int(date_str[6:8]))
        except (ValueError, TypeError, IndexError, AttributeError):
            continue

        if evt_date not in visible_set:
            continue

        for rule in rules:
            icon_name = str(rule.get("icon") or "").strip()
            if not icon_name:
                continue
            if not icon_rule_matches(event, rule):
                continue
            if icon_name not in day_seen[evt_date]:
                color = str(rule.get("color") or "#333333")
                day_icons[evt_date].append((icon_name, color))
                day_seen[evt_date].add(icon_name)

    return day_icons
