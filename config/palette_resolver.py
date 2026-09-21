"""
Palette reference resolution.

Themes and CLI flags may reference DB palettes instead of literal color
lists: bulk lists via ``month_palette`` / ``fiscal_palette`` /
``group_palette`` and individual colors via ``palette:NAME:INDEX``.
``_resolve_palette_overrides()`` rewrites those references into concrete
color lists on the config at render time; it runs after theme
application in ``ecalendar.run()``.
"""

from __future__ import annotations

import dataclasses
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from config.config import CalendarConfig
    from shared.db_access import CalendarDB

logger = logging.getLogger(__name__)


def _resolve_single_palette_ref(value: str, db: CalendarDB) -> str:
    """
    Resolve a ``"palette:NAME:INDEX"`` colour reference to a concrete hex value.

    Theme YAML files can reference database palettes for individual colour
    fields (e.g., ``accent_color: "palette:Blues:3"``) without hard-coding
    hex values.  This function performs that resolution at render time.

    INDEX formats
    ─────────────
    integer  — zero-based; wraps modulo palette length (cycling out-of-bounds).
    float    — proportional position in [0.0, 1.0]; 0.0 = first, 1.0 = last.

    On any error (palette not found, invalid index) the original *value*
    string is returned unchanged and a warning is logged so the render can
    still proceed with a visible but unresolved colour token.

    Called by:
        _resolve_palette_overrides() — iterates all string fields in config
        and calls this function for any that begin with ``"palette:"``.

    Args:
        value: A ``"palette:NAME:INDEX"`` string to resolve.
        db:    Open CalendarDB for palette lookups.

    Returns:
        Resolved hex colour string, or *value* unchanged on failure.
    """
    parts = value.split(":", 2)
    if len(parts) != 3:
        return value
    _, name, idx_str = parts
    colors = db.get_palette(name)
    if not colors:
        logger.warning(f"Palette not found: {name!r}")
        return value
    try:
        if "." in idx_str:
            pos = max(0.0, min(1.0, float(idx_str)))
            idx = int(pos * (len(colors) - 1))
        else:
            idx = int(idx_str) % len(colors)
    except ValueError:
        logger.warning(f"Invalid palette index: {idx_str!r}")
        return value
    return colors[idx]


def _resolve_palette_overrides(config: CalendarConfig, db: CalendarDB) -> None:
    """
    Bulk-resolve all palette name references in CalendarConfig to hex colours.

    Decouples palette name resolution from theme loading: the theme engine
    writes sentinel palette-name strings into config, and this function
    fetches the actual colours from the database at render time so themes
    remain database-independent.

    This function must be called *after* the theme has been fully applied
    (both passes in run()) so that all sentinel fields have been populated.

    Phase 1 — Named bulk palettes
    ──────────────────────────────
    Five sentinel fields are checked and expanded into colour dicts/lists:

      Sentinel field                  → Target field              Size
      config.theme_month_palette      → config.theme_month_colors  12 (one/month)
      config.theme_fiscal_palette     → config.theme_fiscal_period_colors 13 (one/period)
      config.theme_group_palette      → config.group_colors       full palette
      config.theme_timeline_palette   → config.timeline_top/bottom_colors full palette
      config.theme_blockplan_palette_name → config.blockplan_palette full palette

    Phase 2 — Inline ``palette:NAME:INDEX`` references
    ────────────────────────────────────────────────────
    Every string field in config that starts with ``"palette:"`` is passed to
    _resolve_single_palette_ref() and replaced with the resolved hex colour.

    Phase 3 — References inside the parsed theme
    ─────────────────────────────────────────────
    ``style_rules`` styles (``define:`` tokens and ``apply_to`` rules) on
    ``config.theme`` and the ThemeStyles built from them are resolved by
    _resolve_theme_palette_refs().

    Called by:
        run() for both the excelblockplan path and all calendar-visualizer paths,
        after theme application is complete.

    Calls:
        db.sample_palette_n(), db.get_palette(),
        _resolve_single_palette_ref(), _resolve_theme_palette_refs(),
        dataclasses.fields().
    """
    if config.theme_month_palette:
        colors = db.sample_palette_n(config.theme_month_palette, 12)
        if colors:
            config.theme_month_colors = {f"{i + 1:02d}": c for i, c in enumerate(colors)}
        else:
            logger.warning(f"Palette not found: {config.theme_month_palette!r}")

    if config.theme_fiscal_palette:
        colors = db.sample_palette_n(config.theme_fiscal_palette, 13)
        if colors:
            config.theme_fiscal_period_colors = {f"{i + 1:02d}": c for i, c in enumerate(colors)}
        else:
            logger.warning(f"Palette not found: {config.theme_fiscal_palette!r}")

    if config.theme_group_palette:
        colors = db.get_palette(config.theme_group_palette)
        if colors:
            config.group_colors = colors
        else:
            logger.warning(f"Palette not found: {config.theme_group_palette!r}")

    if config.theme_timeline_palette:
        colors = db.get_palette(config.theme_timeline_palette)
        if colors:
            config.timeline_top_colors = colors
            config.timeline_bottom_colors = colors
        else:
            logger.warning(f"Palette not found: {config.theme_timeline_palette!r}")

    if config.theme_blockplan_palette_name:
        colors = db.get_palette(config.theme_blockplan_palette_name)
        if colors:
            config.blockplan_palette = colors
        else:
            logger.warning(f"Palette not found: {config.theme_blockplan_palette_name!r}")

    if config.theme_compactplan_palette_name:
        colors = db.get_palette(config.theme_compactplan_palette_name)
        if colors:
            config.compactplan_palette = colors
        else:
            logger.warning(f"Palette not found: {config.theme_compactplan_palette_name!r}")

    # Resolve 'palette:NAME:INDEX' references in all string config fields.
    for f in dataclasses.fields(config):
        val = getattr(config, f.name, None)
        if isinstance(val, str) and val.startswith("palette:"):
            setattr(config, f.name, _resolve_single_palette_ref(val, db))

    _resolve_theme_palette_refs(config, db)


def _resolve_refs_in(value: Any, db: CalendarDB) -> Any:
    """
    Return *value* with every ``palette:NAME:INDEX`` string resolved.

    Walks strings, lists, tuples, dicts and dataclass instances.  Containers
    holding a reference are rebuilt, never edited in place, and anything
    without one is returned as the same object, so values shared with the
    cached theme YAML are left untouched.
    """
    if isinstance(value, str):
        return _resolve_single_palette_ref(value, db) if value.startswith("palette:") else value
    if isinstance(value, dict):
        items = {k: _resolve_refs_in(v, db) for k, v in value.items()}
        return items if any(items[k] is not value[k] for k in value) else value
    if isinstance(value, (list, tuple)):
        seq = [_resolve_refs_in(v, db) for v in value]
        if all(a is b for a, b in zip(seq, value, strict=True)):
            return value
        return seq if isinstance(value, list) else tuple(seq)
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        changes = {}
        for f in dataclasses.fields(value):
            if not f.init:
                continue
            old = getattr(value, f.name)
            new = _resolve_refs_in(old, db)
            if new is not old:
                changes[f.name] = new
        return dataclasses.replace(value, **changes) if changes else value
    return value


def _resolve_theme_palette_refs(config: CalendarConfig, db: CalendarDB) -> None:
    """
    Resolve ``palette:NAME:INDEX`` references in the parsed theme's styles.

    ``config.theme`` (UnifiedTheme) keeps the theme's ``style_rules`` as the
    YAML wrote them — both the raw list in ``sections["style_rules"]`` (what
    each visualizer feeds its StyleEngine) and the parsed ``rules`` behind
    the token resolver — so token styles such as ``color: palette:Accent:4``
    and rule styles such as ``fill: palette:Accent:0`` (or a list of them)
    would otherwise reach the SVG verbatim.  Both are replaced with resolved
    copies, as is the legacy ``config.theme_style_rules`` fallback; the cached
    YAML they came from is not modified.  ``config.theme_styles``, built from
    the same rules during theme application, is resolved likewise and its
    CSS regenerated.
    """
    from config.unified_theme import _build_token_index

    theme = getattr(config, "theme", None)
    if theme is not None:
        raw_rules = theme.sections.get("style_rules")
        resolved_raw = _resolve_refs_in(raw_rules, db)
        if resolved_raw is not raw_rules:
            # Rebind a copy: ``sections`` is the cached YAML mapping itself.
            theme.sections = {**theme.sections, "style_rules": resolved_raw}
        rules = [_resolve_refs_in(rule, db) for rule in theme.rules]
        if any(new is not old for new, old in zip(rules, theme.rules, strict=True)):
            theme.rules = rules
            theme._token_index = _build_token_index(rules)

    legacy_rules = getattr(config, "theme_style_rules", None)
    if legacy_rules:
        config.theme_style_rules = _resolve_refs_in(legacy_rules, db)

    theme_styles = getattr(config, "theme_styles", None)
    if theme_styles is not None:
        resolved = _resolve_refs_in(theme_styles, db)
        if resolved is not theme_styles:
            from renderers.css_generator import generate_css

            resolved.css = generate_css(resolved)
            config.theme_styles = resolved
