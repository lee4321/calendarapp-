"""
CSS generator for EventCalendar SVG output.

Produces a <style> block from ThemeStyles element bindings. Each CSS element
class maps to resolved style properties (fill, stroke, opacity, etc.).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from config.styles import ElementBinding, ThemeStyles


def generate_css(theme_styles: "ThemeStyles") -> str:
    """
    Generate CSS rules from theme element bindings.

    Returns a string suitable for injection via drawing.append_css().
    Each element class (ec-heading, ec-cell, etc.) gets its resolved
    style properties as CSS rules.
    """
    rules: list[str] = []

    for class_name, binding in sorted(theme_styles.element_bindings.items()):
        props = _binding_to_css_properties(binding)
        if props:
            rule_body = "; ".join(f"{k}: {v}" for k, v in props)
            rules.append(f".{class_name} {{ {rule_body}; }}")

    return "\n".join(rules)


def _binding_to_css_properties(binding: "ElementBinding") -> list[tuple[str, str]]:
    """Convert an ElementBinding to a list of (property, value) CSS pairs."""
    props: list[tuple[str, str]] = []

    if binding.text_style is not None:
        ts = binding.text_style
        color = binding.color if binding.color is not None else ts.color
        props.append(("fill", color))
        if ts.opacity < 1.0:
            props.append(("fill-opacity", _fmt(ts.opacity)))

    elif binding.box_style is not None:
        bs = binding.box_style
        if bs.fill.strip().lower() not in ("none", "transparent", ""):
            props.append(("fill", bs.fill))
        if bs.fill_opacity < 1.0:
            props.append(("fill-opacity", _fmt(bs.fill_opacity)))
        if bs.stroke is not None:
            props.append(("stroke", bs.stroke))
            props.append(("stroke-width", _fmt(bs.stroke_width)))
            if bs.stroke_opacity < 1.0:
                props.append(("stroke-opacity", _fmt(bs.stroke_opacity)))
        else:
            props.append(("stroke", "none"))
        if bs.stroke_dasharray is not None:
            props.append(("stroke-dasharray", bs.stroke_dasharray))

    elif binding.line_style is not None:
        ls = binding.line_style
        props.append(("stroke", ls.color))
        props.append(("stroke-width", _fmt(ls.width)))
        if ls.opacity < 1.0:
            props.append(("stroke-opacity", _fmt(ls.opacity)))
        if ls.dasharray is not None:
            props.append(("stroke-dasharray", ls.dasharray))

    elif binding.icon_style is not None:
        icon = binding.icon_style
        props.append(("fill", icon.color))

    return props


def _fmt(v: float) -> str:
    """Format a float, stripping trailing zeros."""
    return f"{v:g}"
