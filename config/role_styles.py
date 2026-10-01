"""The theme's role tables (``text``, ``boxes``, ``icons``, ``lines``) as element styles.

A role is defined once, in the theme.  This module turns the roles into what
the renderers read: a ``ThemeStyles`` binding every ``ec-*`` element to its
role through the element catalog, and the per-token style dictionaries the
renderers' ``_tk()`` returns.  Conditional ``style_rules`` pass through as the
plain dictionaries the rule engine takes.
"""

from __future__ import annotations

import dataclasses
from typing import Any

from config.styles import BoxStyle, IconStyle, LineStyle, TextStyle, ThemeStyles
from config.theme_schema import BoxRole, IconRole, LineSpec, TextRole, Theme

#: Role-table attribute of the theme for each token kind.
_TABLES = {"text": "text", "box": "boxes", "icon": "icons", "line": "lines"}


def _text_size(role: TextRole, papersize: str) -> float:
    return float(role.size_by_paper.get(papersize, role.size))


def text_style(theme: Theme, role: TextRole, papersize: str = "") -> TextStyle:
    return TextStyle(
        font=role.font or theme.fonts.family,
        size=_text_size(role, papersize),
        color=role.color,
        opacity=role.opacity,
        alignment=role.align,
    )


def role_text(config: Any, name: str) -> TextStyle:
    """The resolved text role *name* of ``config.theme_v3`` (font, size for the paper, colour ...)."""
    theme = config.theme_v3
    return text_style(theme, getattr(theme.text, name), config.papersize)


def box_style(role: BoxRole) -> BoxStyle:
    palette = role.fill_palette
    return BoxStyle(
        fill=role.fill,
        fill_opacity=role.fill_opacity,
        stroke=role.stroke,
        stroke_width=role.stroke_width,
        stroke_opacity=role.stroke_opacity,
        stroke_dasharray=role.stroke_dasharray,
        fill_palette=palette if isinstance(palette, str) else None,
        fill_colors=tuple(palette) if isinstance(palette, list) else None,
    )


def line_style(spec: LineSpec) -> LineStyle:
    return LineStyle(color=spec.color, width=spec.width, opacity=spec.opacity, dasharray=spec.dasharray)


def icon_style(role: IconRole) -> IconStyle:
    return IconStyle(color=role.color, size=role.size, icon=role.name)


def _roles(theme: Theme, kind: str) -> dict[str, Any]:
    """The role objects of one kind, by name (``{}`` for a kind the theme has none of)."""
    table = getattr(theme, _TABLES[kind])
    return {f.name: getattr(table, f.name) for f in dataclasses.fields(table) if not f.name.startswith("_")}


def theme_styles(theme: Theme, papersize: str = "") -> ThemeStyles:
    """Element styles for *theme*: its roles, bound to ``ec-*`` elements by the element catalog."""
    from config.element_catalog import load_catalog
    from config.styles import ElementBinding

    text = {n: text_style(theme, r, papersize) for n, r in _roles(theme, "text").items()}
    box = {n: box_style(r) for n, r in _roles(theme, "box").items()}
    line = {n: line_style(r) for n, r in _roles(theme, "line").items() if isinstance(r, LineSpec)}
    icon = {n: icon_style(r) for n, r in _roles(theme, "icon").items()}
    by_kind = {"text": text, "box": box, "line": line, "icon": icon}
    field = {"text": "text_style", "box": "box_style", "line": "line_style", "icon": "icon_style"}
    bindings = {}
    for name, entry in load_catalog().items():
        bindings[name] = ElementBinding()
        setattr(bindings[name], field[entry.kind], by_kind[entry.kind][entry.token])
    styles = ThemeStyles(
        text_styles=text, box_styles=box, line_styles=line, icon_styles=icon, element_bindings=bindings
    )

    from renderers.css_generator import generate_css

    styles.css = generate_css(styles)
    return styles


def token(theme: Theme, name: str, papersize: str = "") -> dict[str, Any]:
    """The style dictionary of a ``kind:role`` token, ``{}`` when the theme has no such role."""
    kind, _, role_name = name.partition(":")
    if kind not in _TABLES:
        return {}
    role = _roles(theme, kind).get(role_name)
    if role is None:
        return {}
    if kind == "text":
        return {
            "font": role.font or theme.fonts.family,
            "size": _text_size(role, papersize),
            "color": role.color,
            "opacity": role.opacity,
            "alignment": role.align,
        }
    if kind == "box":
        return {
            "fill": role.fill,
            "fill_opacity": role.fill_opacity,
            "stroke": role.stroke,
            "stroke_width": role.stroke_width,
            "stroke_opacity": role.stroke_opacity,
            "dasharray": role.stroke_dasharray,
            "fill_palette": role.fill_palette if isinstance(role.fill_palette, str) else None,
            "fill_colors": role.fill_palette if isinstance(role.fill_palette, list) else None,
            "pattern": role.pattern,
            "pattern_color": role.pattern_color,
            "pattern_opacity": role.pattern_opacity,
        }
    if kind == "line":
        return {"color": role.color, "width": role.width, "opacity": role.opacity, "dasharray": role.dasharray}
    out: dict[str, Any] = {"color": role.color}
    if role.size is not None:
        out["size"] = role.size
    if role.name is not None:
        out["icon"] = role.name
    if role.stroke_width is not None:
        out["stroke_width"] = role.stroke_width
    if role.stroke_opacity is not None:
        out["stroke_opacity"] = role.stroke_opacity
    return out


_TEXT_KEYS = {"size": "font_size", "color": "font_color", "opacity": "font_opacity"}
_LINE_KEYS = {"color": "stroke", "width": "stroke_width", "opacity": "stroke_opacity"}
_LINE_LEADER_KEYS = ("marker_end", "marker_end_size", "linecap", "linejoin")
_ICON_KEYS = {"color": "icon_color", "name": "icon"}


#: The engine's text-element keys each text role restyles.
_TEXT_ROLE_KEYS = {
    "event_name": ("event_name", "duration_name"),
    "event_notes": ("event_notes", "duration_notes"),
    "event_date": ("event_date",),
    "duration_date": ("duration_start_date", "duration_end_date"),
    "day_number": ("day_number",),
    "week_number": ("week_number",),
    "holiday_title": ("holiday_title",),
}


def _engine_style(kind: str, style: dict[str, Any], role: str = "") -> dict[str, Any]:
    """A rule's role attributes spelled the way the rule engine reads them."""
    if kind == "text":
        text = {_TEXT_KEYS.get(k, k): v for k, v in style.items()}
        keys = _TEXT_ROLE_KEYS.get(role)
        return {"text": {key: dict(text) for key in keys}} if keys else text
    if kind == "line":
        out = {_LINE_KEYS.get(k, k): v for k, v in style.items() if k not in _LINE_LEADER_KEYS}
        leader = {k: style[k] for k in _LINE_LEADER_KEYS if k in style}
        return {**out, "leader": leader} if leader else out
    if kind == "icon":
        return {_ICON_KEYS.get(k, k): v for k, v in style.items()}
    return dict(style)


def style_rules(theme: Theme) -> list[dict[str, Any]]:
    """The theme's conditional rules as the dictionaries the rule engine reads."""
    out = []
    for rule in theme.style_rules:
        first = rule.apply_to if isinstance(rule.apply_to, str) else rule.apply_to[0]
        kind, _, role = first.partition(":")
        out.append({**dataclasses.asdict(rule), "style": _engine_style(kind, rule.style, role)})
    return out
