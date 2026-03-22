"""
Visualizer factory for creating visualization instances.

Provides a registry-based factory pattern for instantiating the
appropriate visualizer based on view type.
"""

from __future__ import annotations

from typing import Type

from visualizers.base import BaseVisualizer


class VisualizerFactory:
    """
    Factory for creating visualizer instances.

    Maintains a registry of available visualizers and creates
    instances by type name.
    """

    _visualizers: dict[str, Type[BaseVisualizer]] = {}

    @classmethod
    def _ensure_registered(cls):
        """Lazily register default visualizers on first use."""
        if not cls._visualizers:
            from visualizers.weekly.visualizer import WeeklyCalendarVisualizer
            from visualizers.mini.visualizer import MiniCalendarVisualizer
            from visualizers.mini_icon.visualizer import MiniIconCalendarVisualizer
            from visualizers.text_mini.visualizer import TextMiniCalendarVisualizer
            from visualizers.timeline.visualizer import TimelineVisualizer
            from visualizers.blockplan.visualizer import BlockPlanVisualizer
            from visualizers.compactplan.visualizer import CompactPlanVisualizer

            cls._visualizers = {
                "weekly": WeeklyCalendarVisualizer,
                "mini": MiniCalendarVisualizer,
                "mini-icon": MiniIconCalendarVisualizer,
                "text-mini": TextMiniCalendarVisualizer,
                "timeline": TimelineVisualizer,
                "blockplan": BlockPlanVisualizer,
                "compactplan": CompactPlanVisualizer,
            }

    @classmethod
    def register(cls, name: str, visualizer_class: Type[BaseVisualizer]):
        """
        Register a new visualizer type.

        Args:
            name: Name to register under (e.g., "weekly", "monthly")
            visualizer_class: Class to instantiate for this type
        """
        cls._ensure_registered()
        cls._visualizers[name] = visualizer_class

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
