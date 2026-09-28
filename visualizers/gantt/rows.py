"""
Gantt row model: ordering and indentation.

One row per imported task -- no parent rows are synthesized, so a WBS
level only appears when the schedule actually contains that task
(answer 6).  Ordering follows ``config.item_placement_order`` (shared
across every visualizer -- see shared/item_order.py), which defaults to
WBS-first with WBS segments comparing *numerically* so ``1.9`` precedes
``1.10``; tasks with no WBS form a second block ordered by start date
(answer 7).  Indentation depth is the WBS segment count, and a task
without a WBS sits flush left (answer 8).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from shared.data_models import Event
from shared.item_order import sort_events

# Re-exported: WBS ordering is shared with the timeline's duration
# grouping, but callers and tests still reach it through this module.
from shared.wbs_filter import wbs_depth, wbs_sort_key  # noqa: F401 -- re-exported, see module docstring

if TYPE_CHECKING:
    from config.config import CalendarConfig


@dataclass(frozen=True)
class GanttRow:
    """One task line: the event plus where it sits in the table."""

    event: Event
    depth: int  # indentation level; 0 for top level and for no WBS
    index: int  # final row order, 0-based


def build_rows(events: list[Any], config: CalendarConfig) -> list[GanttRow]:
    """Order *events* into task rows.

    Args:
        events: Already-filtered event dicts (from
            :func:`visualizers.base.filter_events`) or ``Event`` objects.
        config: Supplies ``item_placement_order``; unknown sort fields are
            ignored rather than raising, so a theme typo degrades to the
            default ordering.

    Returns:
        Rows in draw order, each carrying its indentation depth.
    """
    parsed = [ev if isinstance(ev, Event) else Event.from_dict(ev) for ev in events]
    ordered = sort_events(parsed, config.item_placement_order)

    return [GanttRow(event=event, depth=wbs_depth(event.wbs), index=index) for index, event in enumerate(ordered)]
