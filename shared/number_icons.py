"""Numbered duration icons, shared by every view.

With ``durations.replace_icons_with_numbers`` on, every view gives each duration
one icon from ``durations.number_duration_icons`` (a key into ``ICON_SETS``) in place of the
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


def numbering_enabled(config: CalendarConfig) -> bool:
    """Whether durations get numbered icons instead of the icons their events name."""
    return bool(config.theme_v3.durations.replace_icons_with_numbers)


def number_duration_icons(events: list[Any], config: CalendarConfig, view: str) -> list[Any]:
    """Return *events* with each duration's icon replaced by its number.

    Durations (multi-day, non-milestone) are numbered in
    ``events.item_placement_order``, cycling through the icon list, so a
    duration keeps its number wherever the view draws it.  Other events are
    returned untouched, as is the whole list when the view has numbering off.
    Dicts and ``Event`` objects are both accepted; inputs are never mutated.
    """
    from config.config import ICON_SETS

    if not numbering_enabled(config):
        return events
    icons = ICON_SETS.get(str(config.theme_v3.durations.number_duration_icons or ""), [])
    if not icons:
        return events

    parsed = [Event.from_dict(e) if isinstance(e, dict) else e for e in events]
    numbered = [i for i, ev in enumerate(parsed) if ev.is_duration and not ev.milestone]
    by_position = {id(parsed[i]): i for i in numbered}
    order = sort_events([parsed[i] for i in numbered], config.theme_v3.events.item_placement_order)

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
