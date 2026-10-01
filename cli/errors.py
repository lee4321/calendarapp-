"""Exception hierarchy for the EventCalendar CLI."""


class CalendarError(Exception):
    """Base exception for calendar errors."""

    pass


class DatabaseError(CalendarError):
    """Raised when there's a database access error."""

    pass


class ConfigError(CalendarError):
    """Raised when configuration is invalid."""

    pass


class GlyphsTableMissingError(DatabaseError):
    """Raised when a run needs glyphs and the database has no ``glyphs`` table."""

    def __init__(self, database: str) -> None:
        super().__init__(
            f"database '{database}' has no glyphs table; create and seed it with: "
            f"uv run python tools/db/create_glyphs.py --database {database}"
        )
