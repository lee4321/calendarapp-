"""Home launcher: calendar views, reference sheets/listings, and the Import Hub."""

from __future__ import annotations

from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Footer, Header, Label, ListItem, ListView, Static

from tui.screens.builder import BuilderScreen
from tui.screens.import_hub import ImportHubScreen
from tui.spec import (
    CALENDAR_VIEWS,
    LISTING_COMMANDS,
    SHEET_COMMANDS,
    command,
)


def _items(names: list[str]) -> tuple[ListView, list[str]]:
    keys: list[str] = []
    rows: list[ListItem] = []
    for name in names:
        keys.append(name)
        try:
            help_text = command(name).help
        except KeyError:
            help_text = ""
        rows.append(
            ListItem(Vertical(Label(name, classes="hub-name"),
                              Static(help_text, classes="hub-sub")))
        )
    return ListView(*rows), keys


class HomeScreen(Screen):
    BINDINGS = [
        ("i", "import_hub", "Import"),
        ("q", "app.quit", "Quit"),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static("EventCalendar — Textual UI", id="home-title")
        with Horizontal(id="home-columns"):
            with Vertical(classes="home-col"):
                yield Label("CALENDAR VIEWS", classes="col-head")
                lv, self._view_keys = _items(CALENDAR_VIEWS)
                lv.id = "list-views"
                yield lv
            with Vertical(classes="home-col"):
                yield Label("REFERENCE SHEETS", classes="col-head")
                lv2, self._sheet_keys = _items(SHEET_COMMANDS + LISTING_COMMANDS)
                lv2.id = "list-sheets"
                yield lv2
            with Vertical(classes="home-col"):
                yield Label("DATA", classes="col-head")
                yield ListView(
                    ListItem(Vertical(
                        Label("Import Hub", classes="hub-name"),
                        Static("events · special days · holidays · content",
                               classes="hub-sub"))),
                    id="list-data",
                )
        yield Static("[b]Enter[/b] configure · [b]i[/b] import · [b]q[/b] quit",
                     classes="arghelp")
        yield Footer()

    @on(ListView.Selected, "#list-views")
    def _open_view(self, event: ListView.Selected) -> None:
        name = self._view_keys[event.list_view.index or 0]
        self.app.push_screen(BuilderScreen(name, db_path=self.app.db_path))

    @on(ListView.Selected, "#list-sheets")
    def _open_sheet(self, event: ListView.Selected) -> None:
        name = self._sheet_keys[event.list_view.index or 0]
        self.app.push_screen(BuilderScreen(name, db_path=self.app.db_path))

    @on(ListView.Selected, "#list-data")
    def _open_data(self, event: ListView.Selected) -> None:
        self.action_import_hub()

    def action_import_hub(self) -> None:
        self.app.push_screen(ImportHubScreen())
