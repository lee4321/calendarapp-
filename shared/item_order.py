"""
Unified item-placement ordering, shared by every visualizer.

``item_placement_order`` (theme key ``events.item_placement_order``) is the
single setting that decides how event data sorts for placement across all
views: which item type gets the limited rows in a weekly day box, which
content occupies a blockplan swimlane's upper half, row order within a
gantt/timeline/blockplan/compactplan layout, and symbol-assignment order in
text-mini. A visualizer's own placement mechanics (blockplan's lane/WBS-family
assignment, timeline's WBS-group color banding) sit above this as an
orthogonal layer; this module only builds the comparison key.

Token vocabulary, consumed left-to-right, each contributing one component to
a composite sort-key tuple:

  * ``"milestones"`` / ``"events"`` / ``"durations"`` -- type tokens. All type
    tokens in one order collapse into a single leading ``type_rank``
    component (an event is in exactly one type bucket), taken at the
    position of the first type token seen. A type not listed sorts after
    every listed type.
  * ``"wbs"`` -- WBS-having rows always precede WBS-less rows, regardless of
    where the token sits in the list; ties break by :func:`wbs_sort_key`'s
    numeric-aware comparison.
  * ``"priority"`` -- ``Event.priority`` (int, defaults to 0, never None).
  * ``"alphabetical"`` -- lowercased ``task_name``.
  * any other string -- a field token, resolved via
    :func:`renderers.table_columns.resolve_field` onto an ``Event``
    attribute and wrapped in a null-safe scalar key. An unresolvable or
    always-missing field degrades to a no-op component rather than raising.
  * a ``dict`` -- a criteria token: arbitrary event-selection criteria using
    the same vocabulary and matching semantics as ``style_rules``/
    ``swimlane_rules`` (:func:`shared.rule_engine.matches_event_fields`).
    Matching events sort ahead of non-matching ones.

``sort_events`` always appends an implicit final tiebreak of
``(task_name, start, end)`` after the token-driven key, so equal-key events
sort deterministically regardless of input order.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

from renderers.table_columns import resolve_field
from shared.rule_engine import matches_event_fields
from shared.wbs_filter import wbs_sort_key

if TYPE_CHECKING:
    from shared.data_models import Event

#: Tokens that classify an event by shape rather than by a field value.
TYPE_TOKENS: frozenset[str] = frozenset({"milestones", "events", "durations"})

PlacementToken = str | dict[str, Any]


def _event_type(event: Event) -> str:
    if event.milestone:
        return "milestones"
    if event.is_duration:
        return "durations"
    return "events"


def _type_rank(event: Event, type_tokens_in_order: list[str]) -> int:
    etype = _event_type(event)
    return type_tokens_in_order.index(etype) if etype in type_tokens_in_order else len(type_tokens_in_order)


def _wbs_key(event: Event) -> tuple:
    has_wbs = 0 if (event.wbs or "").strip() else 1
    return (has_wbs, wbs_sort_key(event.wbs))


def scalar_key(value: Any) -> tuple[int, Any]:
    """Comparable key for one field, keeping mixed types sortable.

    Every key is a ``(rank, value)`` pair so ``None``, numbers and strings
    never compare against each other directly; ``None``/``""`` sorts last.
    """
    if value is None or value == "":
        return (2, "")
    if isinstance(value, bool):
        return (0, float(value))
    if isinstance(value, (int, float)):
        return (0, float(value))
    return (1, str(value).lower())


def sort_key_for(event: Event, order: Sequence[PlacementToken]) -> tuple:
    """Build the composite item_placement_order sort key for one event."""
    type_tokens_in_order = [t for t in order if isinstance(t, str) and t in TYPE_TOKENS]

    key: list[Any] = []
    emitted_type_rank = False
    for token in order:
        if isinstance(token, dict):
            key.append((0,) if matches_event_fields(token, event) else (1,))
        elif token in TYPE_TOKENS:
            if emitted_type_rank:
                continue
            key.append((_type_rank(event, type_tokens_in_order),))
            emitted_type_rank = True
        elif token == "wbs":
            key.append(_wbs_key(event))
        elif token == "priority":
            # priority is NUMERIC in SQLite, so a column can hold ints and
            # text -- route through scalar_key like any other field so mixed
            # types stay comparable instead of raising.
            key.append((scalar_key(event.priority),))
        elif token == "alphabetical":
            key.append(((event.task_name or "").lower(),))
        else:
            key.append((scalar_key(getattr(event, resolve_field(str(token)), None)),))

    return tuple(key)


def sort_key_for_stable(event: Event, order: Sequence[PlacementToken]) -> tuple:
    """``sort_key_for`` plus the implicit ``(task_name, start, end)`` tiebreak.

    For callers that compose the item_placement_order key with their own
    outer criteria (e.g. blockplan's WBS-family grouping, timeline's WBS
    color banding) rather than calling :func:`sort_events` directly.
    """
    return (sort_key_for(event, order), (event.task_name or "").lower(), event.start, event.end)


def sort_events(events: list[Event], order: Sequence[PlacementToken]) -> list[Event]:
    """Stable sort of *events* by the composite item_placement_order key.

    Appends an implicit ``(task_name, start, end)`` tiebreak so events with
    an identical token-driven key still sort deterministically.
    """
    return sorted(events, key=lambda e: sort_key_for_stable(e, order))
