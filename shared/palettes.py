"""Resolve a theme palette (a database palette name or an inline colour list) to colours."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def resolve_palette(palette: str | list[str] | None, db: Any) -> list[str]:
    """The colours of *palette*; ``[]`` for ``None``.  An unknown name raises ``ValueError``."""
    if palette is None:
        return []
    if isinstance(palette, list):
        return list(palette)
    found = db.get_palette(palette) if db is not None else None
    if not found:
        raise ValueError(f"palette '{palette}' not found")
    return list(found)


def event_colors(theme: Any, db: Any, fallback: str) -> list[str]:
    """``palettes.event`` resolved, or ``[fallback]`` when the palette is empty."""
    return resolve_palette(theme.palettes.event, db) or [fallback]


def resolve_event_palette(config: Any, db: Any) -> list[str]:
    """Replace ``config.theme_v3.palettes.event`` with its colours, so code without a database reads a list."""
    import dataclasses

    theme = config.theme_v3
    colors = resolve_palette(theme.palettes.event, db)
    config.theme_v3 = dataclasses.replace(theme, palettes=dataclasses.replace(theme.palettes, event=colors))
    return colors


def _numbered(colors: list[str], count: int) -> dict[str, str]:
    """``{"01": colour, ...}`` for *count* entries, cycling a shorter list."""
    return {f"{i + 1:02d}": colors[i % len(colors)] for i in range(count)} if colors else {}


def _try(palette: str | list[str] | None, db: Any, what: str) -> list[str]:
    """``resolve_palette`` that warns and returns ``[]`` when the palette cannot be found."""
    try:
        return resolve_palette(palette, db)
    except (ValueError, AttributeError):
        logger.warning("palettes.%s: palette %r not found; using the built-in colours", what, palette)
        return []


def resolve_theme_palettes(config: Any, db: Any) -> None:
    """Resolve the theme's named palettes to the colours the grid views read.

    ``palettes.month`` and ``palettes.fiscal`` become the month and fiscal-period
    colour maps; colours the theme lists itself (``month_colors``, ``fiscal_period_colors``) win, ``palettes.group``
    the group colours and ``palettes.event`` a colour list.  A palette the
    database lacks falls back to the built-in colours.  The result replaces
    ``config.theme_v3`` so code without a database reads plain values.
    """
    import dataclasses

    from config.config import fiscalperiodcolors, monthcolors

    theme = config.theme_v3
    p = theme.palettes
    month = {**(_numbered(_try(p.month, db, "month"), 12) or monthcolors), **p.month_colors}
    fiscal = {**(_numbered(_try(p.fiscal, db, "fiscal"), 13) or fiscalperiodcolors), **p.fiscal_period_colors}
    group = p.group_colors or _try(p.group, db, "group")
    event = _try(p.event, db, "event")
    resolved = dataclasses.replace(p, month_colors=month, fiscal_period_colors=fiscal, group_colors=group, event=event)
    config.theme_v3 = dataclasses.replace(theme, palettes=resolved)
