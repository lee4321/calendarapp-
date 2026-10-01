"""Test doubles shared across the suite."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from shared.db_access import CalendarDB

    class FakeCalendarDB(CalendarDB):
        """Base for partial CalendarDB stand-ins (see the runtime class)."""

else:

    class FakeCalendarDB:
        """Base for test doubles that implement only the CalendarDB methods a
        test needs.

        To the type checker this is CalendarDB, so a fake can be passed
        wherever the real database is expected.  At runtime it is a plain
        object, so a method the fake leaves out still raises AttributeError
        instead of reaching a real database.
        """


def seeded_glyphs(group: str) -> list[str]:
    """The glyphs of *group* as ``tools/db/glyphs_seed.json`` seeds them."""
    import json
    from pathlib import Path

    seed = json.loads((Path(__file__).parent.parent / "tools" / "db" / "glyphs_seed.json").read_text(encoding="utf-8"))
    try:
        return list(seed[group])
    except KeyError:
        raise KeyError(f"glyph group '{group}' not found; groups in the database: {', '.join(seed)}") from None


class GlyphsFromSeed:
    """Mixin for fake databases: ``get_glyphs`` answers from the seed file."""

    def get_glyphs(self, group: str) -> list[str]:
        return seeded_glyphs(group)
