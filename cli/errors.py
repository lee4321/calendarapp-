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

