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
