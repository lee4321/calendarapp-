"""
Visualizer factory: maps each view name to the visualizer that draws it.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import ClassVar

from visualizers.base import BaseVisualizer


def _registry() -> dict[str, Callable[[], BaseVisualizer]]:
    """Build the view-name → constructor table (imports deferred to first use)."""
    from visualizers.blockplan.layout import BlockPlanLayout
    from visualizers.blockplan.renderer import BlockPlanRenderer
    from visualizers.candybar.visualizer import CandybarVisualizer
    from visualizers.compactplan.layout import CompactPlanLayout
    from visualizers.compactplan.renderer import CompactPlanRenderer
    from visualizers.gantt.layout import GanttLayout
    from visualizers.gantt.renderer import GanttRenderer
    from visualizers.mini.visualizer import MiniCalendarVisualizer
    from visualizers.mini_icon.renderer import MiniIconRenderer
    from visualizers.pit.layout import PITLayout
    from visualizers.pit.renderer import PITRenderer
    from visualizers.text_mini.visualizer import TextMiniCalendarVisualizer
    from visualizers.timeline.layout import TimelineLayout
    from visualizers.timeline.renderer import TimelineRenderer
    from visualizers.weekly.layout import WeeklyCalendarLayout
    from visualizers.weekly.renderer import WeeklyCalendarRenderer

    # Views that are just "layout class + renderer class".
    simple = {
        "weekly": (WeeklyCalendarLayout, WeeklyCalendarRenderer),
        "timeline": (TimelineLayout, TimelineRenderer),
        "blockplan": (BlockPlanLayout, BlockPlanRenderer),
        "gantt": (GanttLayout, GanttRenderer),
        "compactplan": (CompactPlanLayout, CompactPlanRenderer),
        "pit": (PITLayout, PITRenderer),
    }
    table: dict[str, Callable[[], BaseVisualizer]] = {
        name: (lambda name=name, lr=lr: BaseVisualizer(name, *lr)) for name, lr in simple.items()
    }
    # Views with their own workflow (date expansion, week numbers, text output).
    table["mini"] = MiniCalendarVisualizer
    table["mini-icon"] = lambda: MiniCalendarVisualizer("mini-icon", renderer_cls=MiniIconRenderer)
    table["candybar"] = CandybarVisualizer
    table["text-mini"] = TextMiniCalendarVisualizer
    return table


class VisualizerFactory:
    """Create visualizer instances by view name."""

    _visualizers: ClassVar[dict[str, Callable[[], BaseVisualizer]]] = {}

    @classmethod
    def _ensure_registered(cls) -> None:
        if not cls._visualizers:
            cls._visualizers = _registry()

    @classmethod
    def create(cls, view_type: str) -> BaseVisualizer:
        """Return a new visualizer for ``view_type``; ValueError if unknown."""
        cls._ensure_registered()
        if view_type not in cls._visualizers:
            available = ", ".join(sorted(cls._visualizers.keys()))
            raise ValueError(f"Unknown view type '{view_type}'. Available: {available}")
        return cls._visualizers[view_type]()

    @classmethod
    def available_types(cls) -> list[str]:
        """Registered view names."""
        cls._ensure_registered()
        return list(cls._visualizers.keys())
