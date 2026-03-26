"""
Unified style primitives for the EventCalendar theme system.

Defines reusable style tokens (TextStyle, BoxStyle, LineStyle, IconStyle, AxisStyle)
and a ThemeStyles container that binds CSS element classes to resolved style objects.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class TextStyle:
    """Named text style token defining font, size, color, and alignment."""

    font: str = "RobotoCondensed-Light"
    size: float = 8.0
    color: str = "#333333"
    opacity: float = 1.0
    alignment: str = "start"  # SVG anchor: start, middle, end

    # Optional paper-size scaling rules: list of {min_size, max_size, size}
    size_rules: tuple[dict, ...] = ()


@dataclass(frozen=True)
class BoxStyle:
    """Named box/rectangle style token with optional palette cycling."""

    fill: str = "white"
    fill_opacity: float = 1.0
    stroke: str | None = None
    stroke_width: float = 0.5
    stroke_opacity: float = 1.0
    stroke_dasharray: str | None = None

    # Palette cycling for repeating box instances (e.g., month cells, timeband segments).
    # Priority: fill_colors > fill_palette > fill (static fallback).
    fill_palette: str | None = None  # Named palette from DB (e.g., "Greys", "Pastel1")
    fill_colors: tuple[str, ...] | None = None  # Inline color list


@dataclass(frozen=True)
class LineStyle:
    """Named line style token with full stroke properties."""

    color: str = "#CCCCCC"
    width: float = 0.5
    opacity: float = 1.0
    dasharray: str | None = None


@dataclass(frozen=True)
class IconStyle:
    """Named icon style token."""

    color: str = "#333333"
    size: float = 10.0
    icon: str | None = None  # Default icon name (e.g., for overflow)


@dataclass(frozen=True)
class AxisStyle:
    """Shared axis definition for timeline/blockplan/compact plan."""

    line_style: str = "axis"  # Reference to a LineStyle name
    tick_color: str = "#666666"
    tick_label_style: str = "caption"  # Reference to a TextStyle name
    tick_date_format: str = "MMM D"
    today_line_style: str = "today"  # Reference to a LineStyle name
    today_label_color: str = "red"
    today_label_text: str = "Today"


@dataclass
class ElementBinding:
    """Binding of a CSS element class to its resolved style."""

    text_style: TextStyle | None = None
    box_style: BoxStyle | None = None
    line_style: LineStyle | None = None
    icon_style: IconStyle | None = None
    # Per-element color override (e.g., ec-today-label uses red regardless of text_style)
    color: str | None = None


@dataclass
class ThemeStyles:
    """
    Container for all resolved theme styles and element-to-style bindings.

    This is the single source of truth for styling. Each named CSS element
    maps to a resolved ElementBinding containing its style objects.
    """

    # Named style token dictionaries
    text_styles: dict[str, TextStyle] = field(default_factory=dict)
    box_styles: dict[str, BoxStyle] = field(default_factory=dict)
    line_styles: dict[str, LineStyle] = field(default_factory=dict)
    icon_styles: dict[str, IconStyle] = field(default_factory=dict)

    # Shared axis definition
    axis: AxisStyle = field(default_factory=AxisStyle)

    # Flat element-to-style binding map: CSS class name → ElementBinding
    element_bindings: dict[str, ElementBinding] = field(default_factory=dict)

    # Pre-generated CSS string for injection into SVG <style> blocks
    css: str = ""

    def get_text_style(self, element_class: str) -> TextStyle | None:
        """Look up the TextStyle bound to a CSS element class."""
        binding = self.element_bindings.get(element_class)
        if binding is None:
            return None
        return binding.text_style

    def get_box_style(self, element_class: str) -> BoxStyle | None:
        """Look up the BoxStyle bound to a CSS element class."""
        binding = self.element_bindings.get(element_class)
        if binding is None:
            return None
        return binding.box_style

    def get_line_style(self, element_class: str) -> LineStyle | None:
        """Look up the LineStyle bound to a CSS element class."""
        binding = self.element_bindings.get(element_class)
        if binding is None:
            return None
        return binding.line_style

    def get_icon_style(self, element_class: str) -> IconStyle | None:
        """Look up the IconStyle bound to a CSS element class."""
        binding = self.element_bindings.get(element_class)
        if binding is None:
            return None
        return binding.icon_style

    def get_element_color(self, element_class: str) -> str | None:
        """Get the effective color for a text element (per-element override or text_style color)."""
        binding = self.element_bindings.get(element_class)
        if binding is None:
            return None
        if binding.color is not None:
            return binding.color
        if binding.text_style is not None:
            return binding.text_style.color
        return None
