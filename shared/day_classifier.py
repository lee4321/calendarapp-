"""Shared day classifier.

Returns the set of non-workday classes that apply to a date:

    "federal_holiday" — government (python-holidays) entry with ``nonworkday=1``
    "company_holiday" — company-specific ``companyspecialdays`` row with
                        ``nonworkday=1``
    "weekend"         — weekday is in ``config.get_weekend_days()``

A date can belong to multiple classes; callers pick how to rank them.

This module is the single source of truth used by blockplan, excelblockplan,
and (optionally) other visualizers so non-workday styling stays consistent.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from config.config import CalendarConfig
    from shared.db_access import CalendarDB


def classify_day(d: date, db: CalendarDB | None, config: CalendarConfig) -> frozenset[str]:
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


def _is_company_nonworkday(db: CalendarDB, daykey: str) -> bool:
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
    db: CalendarDB | None,
    config: CalendarConfig,
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
    return any(k in rule for k in ("federal_holiday", "company_holiday", "weekend", "nonworkday"))


@dataclass(frozen=True)
class NonWorkdayStyle:
    """One view's styling for one non-workday class (``classify_day`` names)."""

    day_class: str  # "federal_holiday", "company_holiday" or "weekend"
    fill_color: str | None
    fill_opacity: float | None
    icon: str | None


@dataclass
class NonWorkdayOverride:
    """How a single-day band cell is restyled for a non-working day."""

    fill: str | None = None  # replaces the cell fill when set
    opacity: float | None = None  # with ``fill``; None keeps the band default
    icons: list[tuple[str, str]] = field(default_factory=list)  # (icon name, color)


def nonworkday_override(
    classes: frozenset[str],
    styles: Sequence[NonWorkdayStyle],
    default_icon_color: str,
    *,
    band_fill_rules: list[dict] | None = None,
    holiday_flags: Sequence[Any] | None = None,
) -> NonWorkdayOverride:
    """Resolve the fill, opacity and icons for one non-workday band cell.

    ``styles`` lists the view's per-class settings in priority order.

    * **fill/opacity** — the first matching band ``fill_rules`` entry with a
      ``color`` wins (its ``opacity`` or None); otherwise the first style
      whose class applies and has a fill color.
    * **icons** — the first style whose class applies and has an icon, drawn
      in that style's fill color (or ``default_icon_color``). A federal
      holiday shows ``holiday_flags`` (one mark per country closed that day)
      instead of the static icon when any are given.
    """
    result = NonWorkdayOverride()
    if not classes:
        return result

    for rule in band_fill_rules or ():
        if not isinstance(rule, dict):
            continue
        match = rule.get("match") or {}
        if isinstance(match, dict) and day_rule_matches(classes, match) and rule.get("color"):
            result.fill = str(rule["color"])
            op = rule.get("opacity")
            result.opacity = float(op) if op is not None else None
            break
    else:
        for style in styles:
            if style.day_class in classes and style.fill_color:
                result.fill = style.fill_color
                result.opacity = style.fill_opacity
                break

    for style in styles:
        if style.day_class in classes and style.icon:
            color = style.fill_color or default_icon_color
            if style.day_class == "federal_holiday" and holiday_flags:
                result.icons = [(mark.icon, color) for mark in holiday_flags]
            else:
                result.icons = [(style.icon, color)]
            break
    return result
