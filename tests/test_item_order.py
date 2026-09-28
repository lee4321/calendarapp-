"""shared/item_order.py: the unified item_placement_order sort key."""

from __future__ import annotations

from config.config import CalendarConfig
from shared.data_models import Event
from shared.item_order import sort_events


def event(
    name: str,
    start: str = "20260202",
    end: str | None = None,
    *,
    wbs: str | None = None,
    priority: int = 0,
    milestone: bool = False,
    resource_group: str | None = None,
    notes: str | None = None,
) -> Event:
    return Event(
        task_name=name,
        start=start,
        end=end if end is not None else start,
        wbs=wbs,
        priority=priority,
        milestone=milestone,
        resource_group=resource_group,
        notes=notes,
    )


# ── Type-token grouping ──────────────────────────────────────────────────


def test_type_tokens_group_in_listed_order():
    events = [
        event("a duration", "20260101", "20260105"),
        event("a milestone", "20260101", milestone=True),
        event("an event", "20260101"),
    ]
    ordered = sort_events(events, ["milestones", "events", "durations"])
    assert [e.task_name for e in ordered] == ["a milestone", "an event", "a duration"]


def test_unlisted_types_sort_after_listed_types():
    events = [
        event("a duration", "20260101", "20260105"),
        event("a milestone", "20260101", milestone=True),
    ]
    ordered = sort_events(events, ["durations"])
    assert [e.task_name for e in ordered] == ["a duration", "a milestone"]


def test_multiple_type_tokens_collapse_into_one_component():
    """Listing a type token more than once shouldn't add extra key components."""
    events = [event("m", milestone=True), event("e")]
    ordered = sort_events(events, ["milestones", "milestones", "events"])
    assert [e.task_name for e in ordered] == ["m", "e"]


# ── priority / alphabetical ──────────────────────────────────────────────


def test_priority_sorts_ascending():
    events = [event("high", priority=5), event("low", priority=1)]
    assert [e.task_name for e in sort_events(events, ["priority"])] == ["low", "high"]


def test_alphabetical_sorts_by_lowercased_name():
    events = [event("Zebra"), event("apple")]
    assert [e.task_name for e in sort_events(events, ["alphabetical"])] == ["apple", "Zebra"]


def test_priority_tolerates_mixed_types():
    """priority is NUMERIC in SQLite, so a column can hold ints and text."""
    events = [
        Event(task_name="text", start="20260202", end="20260202", priority="high"),  # ty: ignore[invalid-argument-type]
        Event(task_name="number", start="20260202", end="20260202", priority=2),
    ]
    assert [e.task_name for e in sort_events(events, ["priority"])] == ["number", "text"]


# ── wbs ───────────────────────────────────────────────────────────────────


def test_wbs_compares_numerically_not_lexically():
    events = [event("nine", wbs="1.9"), event("ten", wbs="1.10"), event("two", wbs="1.2")]
    ordered = sort_events(events, ["wbs"])
    assert [e.task_name for e in ordered] == ["two", "nine", "ten"]


def test_wbs_less_rows_always_follow_wbs_rows():
    events = [event("loose", wbs=None), event("numbered", wbs="9.9")]
    ordered = sort_events(events, ["wbs", "priority"])
    assert [e.task_name for e in ordered] == ["numbered", "loose"]


# ── arbitrary field tokens ────────────────────────────────────────────────


def test_unknown_field_token_is_a_no_op():
    """A theme typo should degrade to the implicit tiebreak, not raise."""
    events = [event("b", wbs="1.2"), event("a", wbs="1.1")]
    ordered = sort_events(events, ["not_a_field"])
    assert [e.task_name for e in ordered] == ["a", "b"]


def test_start_date_field_token_resolves_via_field_aliases():
    events = [event("second", "20260202"), event("first", "20260101")]
    ordered = sort_events(events, ["start_date"])
    assert [e.task_name for e in ordered] == ["first", "second"]


# ── criteria tokens ───────────────────────────────────────────────────────


def test_criteria_token_buckets_matches_first():
    events = [
        event("other", resource_group="Ops", priority=1),
        event("exec", resource_group="Executive", priority=9),
    ]
    ordered = sort_events(events, [{"resource_group": "Executive"}, "priority"])
    assert [e.task_name for e in ordered] == ["exec", "other"]


def test_criteria_token_uses_contains_semantics_for_task_name():
    events = [event("Quarterly Launch Review"), event("Standup")]
    ordered = sort_events(events, [{"task_name": "Launch"}])
    assert ordered[0].task_name == "Quarterly Launch Review"


def test_criteria_token_combines_with_type_token():
    events = [
        event("exec milestone", resource_group="Executive", milestone=True),
        event("exec event", resource_group="Executive"),
        event("other milestone", resource_group="Ops", milestone=True),
    ]
    ordered = sort_events(events, [{"resource_group": "Executive"}, "milestones"])
    assert [e.task_name for e in ordered] == ["exec milestone", "exec event", "other milestone"]


# ── determinism ──────────────────────────────────────────────────────────


def test_equal_keys_break_ties_deterministically_regardless_of_input_order():
    a = event("a", "20260101")
    b = event("b", "20260101")
    forward = sort_events([a, b], ["priority"])
    backward = sort_events([b, a], ["priority"])
    assert [e.task_name for e in forward] == [e.task_name for e in backward] == ["a", "b"]


# ── config validation ────────────────────────────────────────────────────


def test_config_accepts_criteria_dicts():
    config = CalendarConfig(item_placement_order=[{"resource_group": "Executive"}, "priority"])
    assert config.item_placement_order == [{"resource_group": "Executive"}, "priority"]


def test_config_rejects_unrecognized_criteria_key():
    try:
        CalendarConfig(item_placement_order=[{"not_a_criterion": "x"}])
    except ValueError as exc:
        assert "not_a_criterion" in str(exc)
    else:
        raise AssertionError("expected ValueError")
