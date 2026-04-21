"""
Unified rule engine for style_rules and swimlane_rules.

Provides:
- DayContext: per-day state for evaluating rules
- TextStyle: per-text-element font overrides (None = use renderer default)
- StyleResult: accumulated style fields from matched rules (None = not set)
- StyleEngine: evaluates style_rules; results layer additively in order
- LaneEngine: evaluates swimlane_rules; first-match wins
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from shared.data_models import Event

logger = logging.getLogger(__name__)


# ── Context and result types ─────────────────────────────────────────────────


@dataclass(frozen=True)
class DayContext:
    """Per-day attributes for evaluating style and swimlane rules."""

    date: str = ""              # YYYYMMDD — the calendar day being rendered
    federal_holiday: bool = False
    company_holiday: bool = False
    nonworkday: bool = False    # True if any of: federal_holiday, company_holiday, weekend
    workday: bool = True
    weekend: bool = False


@dataclass
class TextStyle:
    """Font overrides for one named text element. None = inherit renderer default."""

    font: str | None = None
    font_size: float | None = None
    font_color: str | None = None
    font_opacity: float | None = None

    def merge(self, other: "TextStyle") -> None:
        """Apply non-None fields from other onto self."""
        if other.font is not None:
            self.font = other.font
        if other.font_size is not None:
            self.font_size = other.font_size
        if other.font_color is not None:
            self.font_color = other.font_color
        if other.font_opacity is not None:
            self.font_opacity = other.font_opacity


@dataclass
class StyleResult:
    """
    Accumulated style overrides from matched style_rules.
    None means "not overridden — use the renderer or theme default."
    """

    # Fill
    fill_color: str | None = None
    fill_opacity: float | None = None
    # Pattern (day_box)
    pattern: str | None = None
    pattern_color: str | None = None
    pattern_opacity: float | None = None
    # Stroke
    stroke_color: str | None = None
    stroke_width: float | None = None
    stroke_opacity: float | None = None
    stroke_dasharray: str | None = None
    # Text — keyed by text-element name (e.g. "day_number", "event_name")
    text: dict[str, TextStyle] = field(default_factory=dict)
    # Icon (event)
    icon: str | None = None
    icon_color: str | None = None

    def is_empty(self) -> bool:
        return all(
            v is None
            for v in (
                self.fill_color, self.fill_opacity,
                self.pattern, self.pattern_color, self.pattern_opacity,
                self.stroke_color, self.stroke_width, self.stroke_opacity,
                self.stroke_dasharray, self.icon, self.icon_color,
            )
        ) and not self.text

    def merge(self, other: "StyleResult") -> None:
        """Layer non-None fields from other on top of self (later rules win)."""
        if other.fill_color is not None:
            self.fill_color = other.fill_color
        if other.fill_opacity is not None:
            self.fill_opacity = other.fill_opacity
        if other.pattern is not None:
            self.pattern = other.pattern
        if other.pattern_color is not None:
            self.pattern_color = other.pattern_color
        if other.pattern_opacity is not None:
            self.pattern_opacity = other.pattern_opacity
        if other.stroke_color is not None:
            self.stroke_color = other.stroke_color
        if other.stroke_width is not None:
            self.stroke_width = other.stroke_width
        if other.stroke_opacity is not None:
            self.stroke_opacity = other.stroke_opacity
        if other.stroke_dasharray is not None:
            self.stroke_dasharray = other.stroke_dasharray
        if other.icon is not None:
            self.icon = other.icon
        if other.icon_color is not None:
            self.icon_color = other.icon_color
        for key, ts in other.text.items():
            if key in self.text:
                self.text[key].merge(ts)
            else:
                self.text[key] = TextStyle(
                    font=ts.font,
                    font_size=ts.font_size,
                    font_color=ts.font_color,
                    font_opacity=ts.font_opacity,
                )


# ── Known text-element keys ───────────────────────────────────────────────────

_ALL_TEXT_KEYS: frozenset[str] = frozenset({
    "event_name", "event_notes", "event_date",
    "duration_name", "duration_notes", "duration_start_date", "duration_end_date",
    "day_number", "week_number", "month_indicator", "holiday_title",
})


# ── Shared criterion matchers ─────────────────────────────────────────────────


def _lc(v: Any) -> str:
    return str(v or "").lower().strip()


def _to_list(v: Any) -> list[str]:
    if isinstance(v, str):
        return [v.lower().strip()]
    if isinstance(v, list):
        return [str(x).lower().strip() for x in v]
    return []


def _substr_match(patterns: list[str], value: str) -> bool:
    lv = value.lower()
    return any(p in lv for p in patterns if p)


def _matches_day_context(select: dict, ctx: DayContext) -> bool | None:
    """
    Check day-level criteria in select against ctx.
    Returns None when no day criteria are present.
    Returns False on first failing criterion; True if all pass.
    """
    day_keys = {"federal_holiday", "company_holiday", "nonworkday", "workday", "weekend", "date"}
    if not any(k in select for k in day_keys):
        return None

    if "federal_holiday" in select:
        if bool(select["federal_holiday"]) != ctx.federal_holiday:
            return False
    if "company_holiday" in select:
        if bool(select["company_holiday"]) != ctx.company_holiday:
            return False
    if "nonworkday" in select:
        if bool(select["nonworkday"]) != ctx.nonworkday:
            return False
    if "workday" in select:
        if bool(select["workday"]) != ctx.workday:
            return False
    if "weekend" in select:
        if bool(select["weekend"]) != ctx.weekend:
            return False
    if "date" in select:
        if not _matches_date(select["date"], ctx.date):
            return False
    return True


def _matches_date(criterion: Any, datekey: str) -> bool:
    """Check a date or date-range criterion against a YYYYMMDD string."""
    if not datekey:
        return False
    if isinstance(criterion, list):
        return datekey in [str(d).strip() for d in criterion]
    s = str(criterion).strip()
    if len(s) == 17 and s[8] == "-":
        return s[:8] <= datekey <= s[9:]
    if len(s) == 8:
        return datekey == s
    return False


_EVENT_CRITERIA_KEYS: frozenset[str] = frozenset({
    "task_name", "notes", "resource_group", "resource_names",
    "wbs", "priority", "priority_min", "priority_max",
    "percent_complete", "milestone", "rollup", "event_type",
    "color", "icon",
})


def _matches_event_fields(select: dict, event: "Event") -> bool | None:
    """
    Check event-level criteria in select against an Event.
    Returns None when no event criteria present.
    Returns False on first failing criterion; True if all pass.
    """
    if not any(k in select for k in _EVENT_CRITERIA_KEYS):
        return None

    if "event_type" in select:
        etype = _lc(select["event_type"])
        if etype == "duration" and not event.is_duration:
            return False
        if etype == "event" and event.is_duration:
            return False

    if "milestone" in select:
        if bool(select["milestone"]) != bool(event.milestone):
            return False

    if "rollup" in select:
        if bool(select["rollup"]) != bool(event.rollup):
            return False

    if "task_name" in select:
        if not _substr_match(_to_list(select["task_name"]), event.task_name or ""):
            return False

    if "notes" in select:
        if not _substr_match(_to_list(select["notes"]), event.notes or ""):
            return False

    if "resource_group" in select:
        allowed = _to_list(select["resource_group"])
        if _lc(event.resource_group) not in allowed:
            return False

    if "resource_names" in select:
        pats = _to_list(select["resource_names"])
        names = [n.strip().lower() for n in (event.resource_names or "").split(",") if n.strip()]
        if not any(_substr_match(pats, n) for n in names):
            return False

    if "wbs" in select:
        from shared.wbs_filter import WBSFilter
        flt = WBSFilter.parse(str(select["wbs"]))
        if flt and not flt.matches(event.wbs):
            return False

    if "priority" in select:
        pv = select["priority"]
        allowed_p = [int(p) for p in pv] if isinstance(pv, list) else [int(pv)]
        if event.priority not in allowed_p:
            return False

    if "priority_min" in select:
        if event.priority < int(select["priority_min"]):
            return False

    if "priority_max" in select:
        if event.priority > int(select["priority_max"]):
            return False

    if "percent_complete" in select:
        pc = select["percent_complete"]
        if isinstance(pc, dict):
            mn = pc.get("min")
            mx = pc.get("max")
            if mn is not None and event.percent_complete < float(mn):
                return False
            if mx is not None and event.percent_complete > float(mx):
                return False
        else:
            if event.percent_complete != float(pc):
                return False

    if "color" in select:
        if _lc(event.color) != _lc(select["color"]):
            return False

    if "icon" in select:
        if _lc(event.icon) != _lc(select["icon"]):
            return False

    return True


def _build_style_result(rule_style: dict) -> StyleResult:
    """Build a StyleResult from a rule's style: mapping."""
    sr = StyleResult()

    def _str_or_none(v: Any) -> str | None:
        return str(v) if v is not None else None

    if "fill_color" in rule_style:
        sr.fill_color = _str_or_none(rule_style["fill_color"])
    if "fill_opacity" in rule_style:
        sr.fill_opacity = float(rule_style["fill_opacity"])
    if "pattern" in rule_style:
        raw = rule_style["pattern"]
        sr.pattern = str(raw).strip() if raw else None
    if "pattern_color" in rule_style:
        raw = rule_style["pattern_color"]
        sr.pattern_color = str(raw).strip() if raw else None
    if "pattern_opacity" in rule_style:
        sr.pattern_opacity = float(rule_style["pattern_opacity"])
    if "stroke_color" in rule_style:
        sr.stroke_color = _str_or_none(rule_style["stroke_color"])
    if "stroke_width" in rule_style:
        sr.stroke_width = float(rule_style["stroke_width"])
    if "stroke_opacity" in rule_style:
        sr.stroke_opacity = float(rule_style["stroke_opacity"])
    if "stroke_dasharray" in rule_style:
        v = rule_style["stroke_dasharray"]
        sr.stroke_dasharray = str(v) if v is not None else None

    # Text shorthand — applies to all text sub-elements as a baseline
    font = rule_style.get("font")
    font_size = rule_style.get("font_size")
    font_color = rule_style.get("font_color")
    font_opacity = rule_style.get("font_opacity")
    if font or font_size is not None or font_color or font_opacity is not None:
        for key in _ALL_TEXT_KEYS:
            ts = TextStyle(
                font=str(font) if font else None,
                font_size=float(font_size) if font_size is not None else None,
                font_color=str(font_color) if font_color else None,
                font_opacity=float(font_opacity) if font_opacity is not None else None,
            )
            if key in sr.text:
                sr.text[key].merge(ts)
            else:
                sr.text[key] = ts

    # Text per-element block — overrides the shorthand per element
    text_block = rule_style.get("text") or {}
    for key, ts_dict in text_block.items():
        if not isinstance(ts_dict, dict):
            continue
        ts = TextStyle(
            font=str(ts_dict["font"]) if ts_dict.get("font") else None,
            font_size=float(ts_dict["font_size"]) if ts_dict.get("font_size") is not None else None,
            font_color=str(ts_dict["font_color"]) if ts_dict.get("font_color") else None,
            font_opacity=float(ts_dict["font_opacity"]) if ts_dict.get("font_opacity") is not None else None,
        )
        if key in sr.text:
            sr.text[key].merge(ts)
        else:
            sr.text[key] = ts

    if "icon" in rule_style:
        raw = rule_style["icon"]
        sr.icon = str(raw) if raw else None
    if "icon_color" in rule_style:
        raw = rule_style["icon_color"]
        sr.icon_color = str(raw) if raw else None

    return sr


# ── StyleEngine ───────────────────────────────────────────────────────────────


class StyleEngine:
    """
    Evaluates style_rules for day boxes and events.
    Results layer additively in declaration order — None fields are not overwritten.
    """

    def __init__(self, rules: list[dict]):
        self._rules = [r for r in (rules or []) if isinstance(r, dict)]

    def _applicable_rules(self, apply_to_filter: str) -> list[dict]:
        """Yield rules whose apply_to includes apply_to_filter or 'all'."""
        out = []
        for rule in self._rules:
            raw = rule.get("apply_to", [])
            if isinstance(raw, str):
                targets = {raw.lower()}
            elif isinstance(raw, list):
                targets = {str(x).lower() for x in raw}
            else:
                continue
            if apply_to_filter in targets or "all" in targets:
                out.append(rule)
        return out

    def evaluate_day(
        self,
        ctx: DayContext,
        events: "list[Event] | None" = None,
    ) -> StyleResult:
        """
        Layer all day_box rules that match ctx and the day's events.
        Returns a StyleResult accumulating every matching rule's style.
        """
        result = StyleResult()
        events = events or []

        for rule in self._applicable_rules("day_box"):
            select = rule.get("select", {})
            if not isinstance(select, dict):
                continue

            day_match = _matches_day_context(select, ctx)
            if day_match is False:
                continue

            event_ok = self._eval_event_criteria_for_day(select, events, rule)
            if event_ok is False:
                continue

            result.merge(_build_style_result(rule.get("style") or {}))

        return result

    def _eval_event_criteria_for_day(
        self,
        select: dict,
        events: "list[Event]",
        rule: dict,
    ) -> bool | None:
        """
        Check event-level criteria against the events on a day.
        None = no event criteria present.
        True = criteria satisfied (any_event or all_events as configured).
        False = criteria not satisfied.
        """
        if not any(k in select for k in _EVENT_CRITERIA_KEYS):
            return None
        if not events:
            return False

        if bool(rule.get("all_events", False)):
            return all(_matches_event_fields(select, ev) is not False for ev in events)

        min_match = max(1, int(rule.get("min_match", 1)))
        matched = sum(1 for ev in events if _matches_event_fields(select, ev) is True)
        return matched >= min_match

    def evaluate_event(
        self,
        event: "Event",
        ctx: DayContext | None = None,
    ) -> StyleResult:
        """
        Layer all event/duration rules that match the given event.
        Returns a StyleResult with accumulated overrides.
        """
        result = StyleResult()
        target = "duration" if event.is_duration else "event"

        for rule in self._applicable_rules(target):
            select = rule.get("select", {})
            if not isinstance(select, dict):
                continue

            if ctx is not None:
                day_match = _matches_day_context(select, ctx)
                if day_match is False:
                    continue

            event_match = _matches_event_fields(select, event)
            if event_match is False:
                continue

            if bool(rule.get("date_overlap", False)) and "date" in (select or {}):
                if not _matches_date_overlap(select["date"], event):
                    continue

            result.merge(_build_style_result(rule.get("style") or {}))

        return result


def _matches_date_overlap(criterion: Any, event: "Event") -> bool:
    """Check if an event's date span overlaps the criterion date/range."""
    if isinstance(criterion, list):
        return any(event.start <= str(d).strip() <= event.end for d in criterion)
    s = str(criterion).strip()
    if len(s) == 17 and s[8] == "-":
        crit_start, crit_end = s[:8], s[9:]
        return event.start <= crit_end and event.end >= crit_start
    if len(s) == 8:
        return event.start <= s <= event.end
    return False


# ── LaneEngine ────────────────────────────────────────────────────────────────


class LaneEngine:
    """
    Evaluates swimlane_rules for blockplan lane routing.
    First-match wins. apply_to is the lane name string.
    """

    def __init__(self, rules: list[dict]):
        self._rules = [r for r in (rules or []) if isinstance(r, dict)]

    def assign(
        self,
        event: "Event",
        ctx: DayContext | None = None,
    ) -> str | None:
        """Return the lane name for the first matching rule, or None if unmatched."""
        for rule in self._rules:
            select = rule.get("select", {})
            if not isinstance(select, dict):
                continue

            # Empty select: catch-all
            if not select:
                lane = rule.get("apply_to")
                return str(lane) if lane is not None else None

            if ctx is not None:
                day_match = _matches_day_context(select, ctx)
                if day_match is False:
                    continue

            event_match = _matches_event_fields(select, event)
            if event_match is False:
                continue

            lane = rule.get("apply_to")
            return str(lane) if lane is not None else None

        return None
