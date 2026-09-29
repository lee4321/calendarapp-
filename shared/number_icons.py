"""Numbered duration icons, shared by every view.

A view whose ``<view>_number_duration_icons`` flag is on gives each duration
one icon from ``duration_icon_list`` (a key into ``ICON_SETS``) in place of the
icon its event data names (kept in ``original_icon`` for the run details).  The events are rewritten once, before the view
lays anything out, so every renderer draws -- and the run details report --
the number through the ordinary icon path.
"""

from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING, Any

from shared.data_models import Event
from shared.item_order import sort_events

if TYPE_CHECKING:
    from config.config import CalendarConfig

#: View name -> the config flag that switches numbering on for it.
NUMBER_ICON_FLAGS: dict[str, str] = {
    "weekly": "weekly_number_duration_icons",
    "mini": "mini_number_duration_icons",
    "candybar": "candybar_number_duration_icons",
    "timeline": "timeline_number_duration_icons",
    "blockplan": "blockplan_number_duration_icons",
    "gantt": "gantt_number_duration_icons",
    "pit": "pit_number_duration_icons",
    "compactplan": "compactplan_number_duration_icons",
    "excelblockplan": "excelblockplan_number_duration_icons",
}


def numbering_enabled(config: CalendarConfig, view: str) -> bool:
    """Whether *view* replaces its durations' icons with numbers."""
    flag = NUMBER_ICON_FLAGS.get(view)
    return bool(flag and getattr(config, flag, False))


def number_duration_icons(events: list[Any], config: CalendarConfig, view: str) -> list[Any]:
    """Return *events* with each duration's icon replaced by its number.

    Durations (multi-day, non-milestone) are numbered in
    ``events.item_placement_order``, cycling through the icon list, so a
    duration keeps its number wherever the view draws it.  Other events are
    returned untouched, as is the whole list when the view has numbering off.
    Dicts and ``Event`` objects are both accepted; inputs are never mutated.
    """
    from config.config import ICON_SETS

    if not numbering_enabled(config, view):
        return events
    icons = ICON_SETS.get(str(config.duration_icon_list or ""), [])
    if not icons:
        return events

    parsed = [Event.from_dict(e) if isinstance(e, dict) else e for e in events]
    numbered = [i for i, ev in enumerate(parsed) if ev.is_duration and not ev.milestone]
    by_position = {id(parsed[i]): i for i in numbered}
    order = sort_events([parsed[i] for i in numbered], config.item_placement_order)

    result = list(events)
    for n, ev in enumerate(order):
        i = by_position[id(ev)]
        icon = icons[n % len(icons)]
        original = events[i]
        if isinstance(original, dict):
            result[i] = {**original, "Icon": icon, "Original_Icon": original.get("Icon") or ""}
        else:
            result[i] = dataclasses.replace(original, icon=icon, original_icon=original.icon or "")
    return result
