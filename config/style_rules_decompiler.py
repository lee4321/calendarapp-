"""
Style-rules decompiler — runtime bridge from unified ``style_rules`` back to
the legacy section shape that ``config/theme_engine.py`` still consumes.

Per design §7.1 the long-term plan is to retire the legacy theme_engine
entirely and have the renderer query ``UnifiedTheme`` directly via
``resolve_token`` and ``find_rules``.  Until that renderer migration
lands, this decompiler keeps visual styling working end-to-end: it walks
the ``style_rules`` definitions in a theme dict and synthesizes the
legacy ``text_styles`` / ``box_styles`` / ``line_styles`` /
``icon_styles`` / ``element_styles`` sections in place, with the
property-name flips reversed (``fill`` → ``fill_color`` etc.).

Scope and limitations
---------------------
* Only ``define:`` rules contribute to the synthesized legacy sections.
  Conditional override rules (e.g. papersize-scoped text-size tweaks)
  are not decompiled — they require the layered resolution that the
  legacy parser doesn't support.  Those overrides remain visible to
  the new resolver path and will take effect once the renderer
  migrates to use it.
* Content rules (``apply_to: box:day`` with selectors like
  ``federal_holiday: true``) stay in ``style_rules`` and are read
  directly by the existing rule engine — no decompilation needed for
  those.
* The decompiler is a DEVELOPMENT BRIDGE; it goes away when the
  renderer is migrated.  The design's "clean break" principle (§7.1)
  applies to the *file format* — themes are unified-only.  This
  decompiler is an internal runtime detail, not a user-facing legacy
  surface.
"""

from __future__ import annotations

from typing import Any

# Reverse of the converter's property renames.
_BOX_PROP_REVERSE: dict[str, str] = {
    "fill": "fill_color",
    "stroke": "stroke_color",
    "dasharray": "stroke_dasharray",
}

# Element-binding ``style.use`` values map to the legacy element_styles key.
# The legacy shape is ``{<kind>_style: <name>}``.
_USE_KIND_TO_KEY: dict[str, str] = {
    "text": "text_style",
    "box": "box_style",
    "line": "line_style",
    "icon": "icon_style",
}


def decompile_style_rules(theme: dict[str, Any]) -> None:
    """Mutate ``theme`` in place: synthesize legacy sections from ``style_rules``.

    Safe to call on a theme that already contains legacy sections —
    the decompiler does not overwrite existing keys, only fills in
    missing ones.  Safe to call repeatedly (idempotent on its outputs).

    Returns ``None`` — the theme dict is updated in place.
    """
    rules = theme.get("style_rules")
    if not isinstance(rules, list):
        return

    text_styles: dict[str, dict[str, Any]] = dict(theme.get("text_styles") or {})
    box_styles:  dict[str, dict[str, Any]] = dict(theme.get("box_styles")  or {})
    line_styles: dict[str, dict[str, Any]] = dict(theme.get("line_styles") or {})
    icon_styles: dict[str, dict[str, Any]] = dict(theme.get("icon_styles") or {})
    element_styles: dict[str, dict[str, Any]] = dict(theme.get("element_styles") or {})

    for rule in rules:
        if not isinstance(rule, dict):
            continue
        kind = rule.get("define")
        if kind:
            _decompile_define(
                rule, kind,
                text_styles=text_styles,
                box_styles=box_styles,
                line_styles=line_styles,
                icon_styles=icon_styles,
            )
            continue
        # Element bindings: apply_to: element, select.element, style.use
        if rule.get("apply_to") == "element":
            _decompile_element_binding(rule, element_styles=element_styles)

    if text_styles:
        theme["text_styles"] = text_styles
    if box_styles:
        theme["box_styles"] = box_styles
    if line_styles:
        theme["line_styles"] = line_styles
    if icon_styles:
        theme["icon_styles"] = icon_styles
    if element_styles:
        theme["element_styles"] = element_styles


def _decompile_define(
    rule: dict[str, Any],
    kind: str,
    *,
    text_styles: dict[str, dict[str, Any]],
    box_styles: dict[str, dict[str, Any]],
    line_styles: dict[str, dict[str, Any]],
    icon_styles: dict[str, dict[str, Any]],
) -> None:
    name = rule.get("as")
    style = rule.get("style") or {}
    if not isinstance(name, str) or not isinstance(style, dict):
        return

    if kind == "text":
        # text token shape: {font, size, color}; legacy text_styles preserves the same keys
        if name not in text_styles:
            text_styles[name] = dict(style)
    elif kind == "box":
        # box token shape: {fill, fill_opacity, stroke, stroke_width, stroke_opacity,
        # dasharray, pattern, pattern_color, pattern_opacity, fill_palette, fill_colors}
        # legacy box_styles uses fill_color / stroke_color / stroke_dasharray.
        if name not in box_styles:
            converted: dict[str, Any] = {}
            for k, v in style.items():
                converted[_BOX_PROP_REVERSE.get(k, k)] = v
            box_styles[name] = converted
    elif kind == "line":
        # line token shape: {color, width, opacity, dasharray}; legacy matches.
        if name not in line_styles:
            line_styles[name] = dict(style)
    elif kind == "icon":
        # icon token shape: {icon, color, size}; legacy matches.
        if name not in icon_styles:
            icon_styles[name] = dict(style)


def _decompile_element_binding(
    rule: dict[str, Any],
    *,
    element_styles: dict[str, dict[str, Any]],
) -> None:
    select = rule.get("select") or {}
    if not isinstance(select, dict):
        return
    element = select.get("element")
    style = rule.get("style") or {}
    if not isinstance(style, dict):
        return
    use = style.get("use")
    if not isinstance(use, str) or ":" not in use:
        return
    kind, _, token_name = use.partition(":")
    legacy_key = _USE_KIND_TO_KEY.get(kind)
    if legacy_key is None:
        return

    # Element may be a string or a list of element class names.
    targets: list[str] = []
    if isinstance(element, str):
        targets = [element]
    elif isinstance(element, list):
        targets = [e for e in element if isinstance(e, str)]
    else:
        return

    # Other style keys beyond `use` become per-element overrides on the binding.
    extra: dict[str, Any] = {}
    for k, v in style.items():
        if k == "use":
            continue
        extra[_BOX_PROP_REVERSE.get(k, k)] = v

    for ec in targets:
        if ec in element_styles:
            continue  # do not overwrite a user-supplied binding
        binding: dict[str, Any] = {legacy_key: token_name}
        binding.update(extra)
        element_styles[ec] = binding


__all__ = ["decompile_style_rules"]
