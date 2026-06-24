"""CalendarTUI — the Textual application shell."""

from __future__ import annotations

from pathlib import Path

from textual.app import App

from tui.screens.home import HomeScreen


class CalendarTUI(App):
    """A terminal front-end over the ecalendar.py CLI."""

    CSS_PATH = "app.tcss"
    TITLE = "EventCalendar"
    SUB_TITLE = "Textual UI"

    BINDINGS = [
        ("ctrl+q", "quit", "Quit"),
        ("d", "toggle_dark", "Dark/light"),
    ]

    def __init__(self, *, project_root: str | None = None,
                 db_path: str = "calendar.db") -> None:
        super().__init__()
        self.project_root = Path(project_root or Path.cwd()).resolve()
        self.db_path = str(self.project_root / db_path)

    def on_mount(self) -> None:
        self.push_screen(HomeScreen())

    def action_toggle_dark(self) -> None:
        self.theme = (
            "textual-light" if self.theme == "textual-dark" else "textual-dark"
        )
