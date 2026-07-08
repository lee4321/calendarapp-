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

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from config.config import CalendarConfig
    from shared.db_access import CalendarDB

logger = logging.getLogger(__name__)


def _resolve_single_palette_ref(value: str, db: "CalendarDB") -> str:
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


def _resolve_palette_overrides(config: "CalendarConfig", db: "CalendarDB") -> None:
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

    Called by:
        run() for both the excelheader path and all calendar-visualizer paths,
        after theme application is complete.

    Calls:
        db.sample_palette_n(), db.get_palette(),
        _resolve_single_palette_ref(), dataclasses.fields().
    """
    import dataclasses

    if config.theme_month_palette:
        colors = db.sample_palette_n(config.theme_month_palette, 12)
        if colors:
            config.theme_month_colors = {
                f"{i + 1:02d}": c for i, c in enumerate(colors)
            }
        else:
            logger.warning(f"Palette not found: {config.theme_month_palette!r}")

    if config.theme_fiscal_palette:
        colors = db.sample_palette_n(config.theme_fiscal_palette, 13)
        if colors:
            config.theme_fiscal_period_colors = {
                f"{i + 1:02d}": c for i, c in enumerate(colors)
            }
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
            logger.warning(
                f"Palette not found: {config.theme_blockplan_palette_name!r}"
            )

    if config.theme_compactplan_palette_name:
        colors = db.get_palette(config.theme_compactplan_palette_name)
        if colors:
            config.compactplan_palette = colors
        else:
            logger.warning(
                f"Palette not found: {config.theme_compactplan_palette_name!r}"
            )

    # Resolve 'palette:NAME:INDEX' references in all string config fields.
    for f in dataclasses.fields(config):
        val = getattr(config, f.name, None)
        if isinstance(val, str) and val.startswith("palette:"):
            setattr(config, f.name, _resolve_single_palette_ref(val, db))

