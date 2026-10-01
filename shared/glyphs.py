"""Glyph groups from the database ``glyphs`` table, as the grid views use them.

A theme names a group per role (``text_mini.glyphs.event``, ``mini_calendar.glyphs.day_number``
...).  An unset role means "use the font's own digits" for the digit roles and "no
symbol" for the symbol roles; a group the table does not hold stops the run with a
message naming the groups it does.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from cli.errors import ConfigError

#: Glyph a duration's middle days show when ``text_mini.glyphs.duration_fill`` is unset.
DEFAULT_DURATION_FILL = "·"


def resolve_group(group: str | None, db: Any, role: str) -> list[str] | None:
    """The glyphs of *group* (``None`` when unset); *role* names the theme key in the error."""
    if group is None:
        return None
    try:
        return db.get_glyphs(group)
    except KeyError as exc:
        raise ConfigError(f"{role}: {exc.args[0]}") from exc


@dataclass(frozen=True)
class MiniGlyphSets:
    """The mini view's day-number glyphs: one per day of the month, or ten digits."""

    day_number: list[str] | None = None
    day_number_digits: list[str] | None = None


def mini_glyph_sets(config: Any, db: Any) -> MiniGlyphSets:
    glyphs = config.theme_v3.mini_calendar.glyphs
    return MiniGlyphSets(
        resolve_group(glyphs.day_number, db, "mini_calendar.glyphs.day_number"),
        resolve_group(glyphs.day_number_digits, db, "mini_calendar.glyphs.day_number_digits"),
    )


@dataclass(frozen=True)
class TextMiniGlyphSets:
    event: list[str]
    milestone: list[str]
    duration: list[str]
    holiday: list[str]
    nonworkday: list[str]
    duration_fill: str
    day_number_digits: list[str] | None
    week_number_digits: list[str] | None


def text_mini_glyph_sets(config: Any, db: Any) -> TextMiniGlyphSets:
    g = config.theme_v3.text_mini.glyphs

    def symbols(name: str) -> list[str]:
        return resolve_group(getattr(g, name), db, f"text_mini.glyphs.{name}") or []

    fill = resolve_group(g.duration_fill, db, "text_mini.glyphs.duration_fill")
    return TextMiniGlyphSets(
        event=symbols("event"),
        milestone=symbols("milestone"),
        duration=symbols("duration"),
        holiday=symbols("holiday"),
        nonworkday=symbols("nonworkday"),
        duration_fill=fill[0] if fill else DEFAULT_DURATION_FILL,
        day_number_digits=resolve_group(g.day_number_digits, db, "text_mini.glyphs.day_number_digits"),
        week_number_digits=resolve_group(g.week_number_digits, db, "text_mini.glyphs.week_number_digits"),
    )
