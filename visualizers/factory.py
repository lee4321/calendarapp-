"""
Visualizer factory for creating visualization instances.

Provides a registry-based factory pattern for instantiating the
appropriate visualizer based on view type.
"""

from __future__ import annotations

from typing import ClassVar

from visualizers.base import BaseVisualizer


class VisualizerFactory:
    """
    Factory for creating visualizer instances.

    Maintains a registry of available visualizers and creates
    instances by type name.
    """

    _visualizers: ClassVar[dict[str, type[BaseVisualizer]]] = {}

    @classmethod
    def _ensure_registered(cls):
        """Lazily register default visualizers on first use."""
        if not cls._visualizers:
            from visualizers.blockplan.visualizer import BlockPlanVisualizer
            from visualizers.candybar.visualizer import CandybarVisualizer
            from visualizers.compactplan.visualizer import CompactPlanVisualizer
            from visualizers.gantt.visualizer import GanttVisualizer
            from visualizers.mini.visualizer import MiniCalendarVisualizer
            from visualizers.mini_icon.visualizer import MiniIconCalendarVisualizer
            from visualizers.pit.visualizer import PITVisualizer
            from visualizers.text_mini.visualizer import TextMiniCalendarVisualizer
            from visualizers.timeline.visualizer import TimelineVisualizer
            from visualizers.weekly.visualizer import WeeklyCalendarVisualizer

            cls._visualizers = {
                "weekly": WeeklyCalendarVisualizer,
                "mini": MiniCalendarVisualizer,
                "mini-icon": MiniIconCalendarVisualizer,
                "candybar": CandybarVisualizer,
                "text-mini": TextMiniCalendarVisualizer,
                "timeline": TimelineVisualizer,
                "blockplan": BlockPlanVisualizer,
                "gantt": GanttVisualizer,
                "compactplan": CompactPlanVisualizer,
                "pit": PITVisualizer,
            }

    @classmethod
    def create(cls, view_type: str) -> BaseVisualizer:
        """
        Create a visualizer instance by type name.

        Args:
            view_type: Type of visualizer (e.g., "weekly")

        Returns:
            Instantiated visualizer

        Raises:
            ValueError: If view_type is not registered
        """
        cls._ensure_registered()

        if view_type not in cls._visualizers:
            available = ", ".join(sorted(cls._visualizers.keys()))
            raise ValueError(f"Unknown view type '{view_type}'. Available: {available}")

        return cls._visualizers[view_type]()

    @classmethod
    def available_types(cls) -> list[str]:
        """
        Return list of registered visualizer names.

        Returns:
            List of available view type names
        """
        cls._ensure_registered()
        return list(cls._visualizers.keys())
