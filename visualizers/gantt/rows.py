"""
Gantt row model: ordering and indentation.

One row per imported task -- no parent rows are synthesized, so a WBS
level only appears when the schedule actually contains that task
(answer 6).  Ordering is WBS-first, and WBS segments compare
*numerically* so ``1.9`` precedes ``1.10``; tasks with no WBS form a
second block ordered by start date (answer 7).  Indentation depth is the
WBS segment count, and a task without a WBS sits flush left (answer 8).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from shared.data_models import Event
# Re-exported: WBS ordering is shared with the timeline's duration
# grouping, but callers and tests still reach it through this module.
from shared.wbs_filter import wbs_depth, wbs_sort_key  # noqa: F401
from visualizers.gantt.columns import resolve_field

if TYPE_CHECKING:
    from config.config import CalendarConfig

#: Sort-key rank for the two row blocks: WBS rows first, then the rest.
_HAS_WBS = 0
_NO_WBS = 1


@dataclass(frozen=True)
class GanttRow:
    """One task line: the event plus where it sits in the table."""

    event: Event
    depth: int      # indentation level; 0 for top level and for no WBS
    index: int      # final row order, 0-based


def build_rows(events: list[Any], config: "CalendarConfig") -> list[GanttRow]:
    """Order *events* into task rows.

    Args:
        events: Already-filtered event dicts (from
            :func:`visualizers.base.filter_events`) or ``Event`` objects.
        config: Supplies ``gantt_sort``; unknown sort fields are ignored
            rather than raising, so a theme typo degrades to the default
            ordering.

    Returns:
        Rows in draw order, each carrying its indentation depth.
    """
    parsed = [ev if isinstance(ev, Event) else Event.from_dict(ev) for ev in events]
    sort_fields = list(getattr(config, "gantt_sort", None) or ["wbs", "start_date"])

    ordered = sorted(parsed, key=lambda ev: _sort_key(ev, sort_fields))

    return [
        GanttRow(event=event, depth=wbs_depth(event.wbs), index=index)
        for index, event in enumerate(ordered)
    ]


def _sort_key(event: Event, sort_fields: list[str]) -> tuple:
    """Build the composite sort key for one event.

    The WBS block split leads regardless of where ``wbs`` appears in the
    field list: rows without a WBS always follow rows with one, because
    interleaving them by date would scatter unnumbered tasks through the
    hierarchy.
    """
    key: list[Any] = [_HAS_WBS if (event.wbs or "").strip() else _NO_WBS]

    for field in sort_fields:
        if field == "wbs":
            key.append(wbs_sort_key(event.wbs))
        else:
            # Sort fields use the same events-table vocabulary as columns,
            # so "start_date" has to reach Event.start.
            key.append(_scalar_key(getattr(event, resolve_field(field), None)))

    return tuple(key)


def _scalar_key(value: Any) -> tuple[int, Any]:
    """Comparable key for one field, keeping mixed types sortable.

    Every key is a ``(rank, value)`` pair so ``None``, numbers and
    strings never compare against each other directly.
    """
    if value is None or value == "":
        return (2, "")
    if isinstance(value, bool):
        return (0, float(value))
    if isinstance(value, (int, float)):
        return (0, float(value))
    return (1, str(value).lower())
