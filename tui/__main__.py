"""Entry point: ``uv run python -m tui``."""

from __future__ import annotations

import argparse
from pathlib import Path

from tui.app import CalendarTUI


def main() -> None:
    parser = argparse.ArgumentParser(prog="tui", description="EventCalendar Textual UI")
    parser.add_argument("--database", "-db", default="calendar.db",
                        help="SQLite database file (default: calendar.db)")
    parser.add_argument("--project-root", default=str(Path.cwd()),
                        help="Project root used as cwd for `uv run` calls")
    args = parser.parse_args()
    CalendarTUI(project_root=args.project_root, db_path=args.database).run()


if __name__ == "__main__":
    main()
