"""Tests for day-based icon rules in compute_icon_band_days()."""
from datetime import date

from shared.data_models import Event
from shared.icon_band import compute_icon_band_days


def _classify_weekend_only(d: date) -> frozenset[str]:
    if d.weekday() >= 5:
        return frozenset({"weekend"})
    return frozenset()


def test_day_based_icon_rule_fires_on_weekend():
    visible = [date(2026, 5, 1), date(2026, 5, 2), date(2026, 5, 3)]  # Fri, Sat, Sun
    rules = [{"icon": "beach", "color": "#ccc", "weekend": True}]
    out = compute_icon_band_days(
        events=[], rules=rules, visible_days=visible,
        classify_fn=_classify_weekend_only,
    )
    assert out[date(2026, 5, 1)] == []
    assert ("beach", "#ccc") in out[date(2026, 5, 2)]
    assert ("beach", "#ccc") in out[date(2026, 5, 3)]


def test_day_rules_require_classify_fn():
    """Day rules with no classify_fn are silently skipped (no crash)."""
    visible = [date(2026, 5, 2)]
    rules = [{"icon": "beach", "weekend": True}]
    out = compute_icon_band_days(events=[], rules=rules, visible_days=visible)
    assert out[date(2026, 5, 2)] == []


def test_event_and_day_rules_coexist():
    """Event-based and day-based rules can both populate the same map."""
    visible = [date(2026, 5, 1), date(2026, 5, 2)]
    rules = [
        {"icon": "beach", "color": "#ccc", "weekend": True},
        {"icon": "flag", "color": "#f00", "milestone": True},
    ]
    ev = Event(
        task_name="Launch", start="20260501", end="20260501",
        milestone=True, datekey="20260501",
    )
    out = compute_icon_band_days(
        events=[ev], rules=rules, visible_days=visible,
        classify_fn=_classify_weekend_only,
    )
    # Fri: milestone only
    assert out[date(2026, 5, 1)] == [("flag", "#f00")]
    # Sat: weekend only
    assert out[date(2026, 5, 2)] == [("beach", "#ccc")]


def test_nonworkday_key_matches_any_class():
    visible = [date(2026, 5, 1), date(2026, 5, 2)]  # Fri, Sat

    def classify(d):
        return frozenset({"weekend"}) if d.weekday() == 5 else frozenset()

    rules = [{"icon": "x", "nonworkday": True}]
    out = compute_icon_band_days(
        events=[], rules=rules, visible_days=visible, classify_fn=classify,
    )
    assert out[date(2026, 5, 1)] == []
    assert out[date(2026, 5, 2)] == [("x", "#333333")]
