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


def apply_style_rules(config, rules: list[dict]) -> None:
    """Apply a theme holding only ``rules`` as its ``style_rules`` to ``config``.

    Element styles come from tokens, so tests that need a particular font,
    color or line define the token the way a theme would.
    """
    from config.theme_engine import ThemeEngine

    engine = ThemeEngine()
    engine._theme_data = {"style_rules": rules}
    engine.apply(config)


def define(kind: str, name: str, **style) -> dict:
    """One ``define <kind>:<name>`` rule for :func:`apply_style_rules`."""
    return {"name": f"define {kind}:{name}", "define": kind, "as": name, "style": style}
