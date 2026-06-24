"""Textual TUI front-end for the EventCalendar CLI.

A thin GUI over the existing ``ecalendar.py`` argparse layer: it introspects the
parser to generate parameter forms, builds an argv, and shells out via ``uv run``.
No calendar-rendering logic is reimplemented here.
"""

__all__ = ["main"]


def main() -> None:
    from tui.app import CalendarTUI

    CalendarTUI().run()
