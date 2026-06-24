"""Populate pickers from the listing subcommands / registries.

Best-effort: values come from the same sources the engine uses, so dropdowns
never drift from the database/font registry.  Any failure degrades to a plain
text input (the caller treats ``None`` as "no options available").
"""

from __future__ import annotations

from functools import lru_cache


@lru_cache(maxsize=8)
def list_values(kind: str, db_path: str = "calendar.db") -> tuple[str, ...] | None:
    try:
        if kind == "themes":
            from config.theme_engine import ThemeEngine

            names = ThemeEngine.list_available_themes()
            return tuple(str(n) for n in names)
        if kind == "fonts":
            from config.config import FONT_REGISTRY

            return tuple(sorted(FONT_REGISTRY.keys()))
        if kind in ("papersizes", "patterns", "icons", "colors", "palettes"):
            from shared.db_access import CalendarDB

            db = CalendarDB(db_path)
            if kind == "papersizes":
                grouped = db.get_paper_sizes_grouped()
                names = [n for rows in grouped.values() for n, _w, _h in rows]
                return tuple(sorted(names))
            if kind == "patterns":
                return tuple(sorted(db.get_all_patterns().keys()))
            if kind == "palettes":
                return tuple(sorted(db.get_all_palettes().keys()))
            if kind == "icons":
                return tuple(sorted(db.get_icon_svg_map().keys()))
            if kind == "colors":
                rows = db.get_all_colors()
                return tuple(str(r.get("EN") or r.get("name") or "") for r in rows)
    except Exception:
        return None
    return None
