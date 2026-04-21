"""Shared day classifier.

Returns the set of non-workday classes that apply to a date:

    "federal_holiday" — government (python-holidays) entry with ``nonworkday=1``
    "company_holiday" — company-specific ``companyspecialdays`` row with
                        ``nonworkday=1``
    "weekend"         — weekday is in ``config.get_weekend_days()``

A date can belong to multiple classes; callers pick how to rank them.

This module is the single source of truth used by blockplan, excelheader,
and (optionally) other visualizers so non-workday styling stays consistent.
"""
from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from config.config import CalendarConfig
    from shared.db_access import CalendarDB


def classify_day(d: date, db: "CalendarDB | None", config: "CalendarConfig") -> frozenset[str]:
    """Return the subset of non-workday classes that apply to *d*.

    Returned elements are drawn from ``{"federal_holiday", "company_holiday",
    "weekend"}``.  ``db`` may be ``None`` (tests) — in that case only the
    ``weekend`` check runs.
    """
    classes: set[str] = set()
    weekend_days = config.get_weekend_days()
    if d.weekday() in weekend_days:
        classes.add("weekend")
    if db is not None:
        daykey = d.strftime("%Y%m%d")
        country = getattr(config, "country", None)
        is_gov = getattr(db, "is_government_nonworkday", None)
        if is_gov is not None and is_gov(daykey, country):
            classes.add("federal_holiday")
        is_company = _is_company_nonworkday(db, daykey)
        if is_company:
            classes.add("company_holiday")
    return frozenset(classes)


def _is_company_nonworkday(db: "CalendarDB", daykey: str) -> bool:
    """Check ``companyspecialdays`` for a nonworkday entry on *daykey*.

    Unlike :meth:`CalendarDB.is_nonworkday`, this intentionally excludes
    government holidays — callers want the two signals separated.
    """
    getter = getattr(db, "get_special_days_for_date", None)
    if getter is None:
        return False
    try:
        rows = getter(daykey) or []
    except Exception:
        return False
    return any(r.get("nonworkday") for r in rows)


def classify_days(
    visible_days: list[date],
    db: "CalendarDB | None",
    config: "CalendarConfig",
) -> dict[date, frozenset[str]]:
    """Classify every day in *visible_days* in one pass; returns a cache dict."""
    return {d: classify_day(d, db, config) for d in visible_days}


def day_rule_matches(classes: frozenset[str], rule: dict[str, Any]) -> bool:
    """Check whether *classes* satisfies a day-based match rule.

    Supported keys (all optional):

    * ``federal_holiday: bool``
    * ``company_holiday: bool``
    * ``weekend: bool``
    * ``nonworkday: bool``  — matches if any of the three classes is present

    Any ``True`` value requires the class to be present; ``False`` requires
    it to be absent.  A rule with none of these keys returns ``False`` so
    event-based rules are never accidentally matched as day rules.
    """
    has_day_key = False
    if "federal_holiday" in rule:
        has_day_key = True
        if bool(rule["federal_holiday"]) != ("federal_holiday" in classes):
            return False
    if "company_holiday" in rule:
        has_day_key = True
        if bool(rule["company_holiday"]) != ("company_holiday" in classes):
            return False
    if "weekend" in rule:
        has_day_key = True
        if bool(rule["weekend"]) != ("weekend" in classes):
            return False
    if "nonworkday" in rule:
        has_day_key = True
        is_nwd = bool(classes)
        if bool(rule["nonworkday"]) != is_nwd:
            return False
    return has_day_key


def rule_has_day_keys(rule: dict[str, Any]) -> bool:
    """Return True if *rule* uses any day-based match key."""
    return any(
        k in rule for k in ("federal_holiday", "company_holiday", "weekend", "nonworkday")
    )
