"""Parameter form for one calendar view / sheet command.

Tabs mirror the argparse argument groups; every field is generated from the
introspected spec, so new CLI flags appear here automatically.
"""

from __future__ import annotations

from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.screen import Screen
from textual.widgets import (
    Button,
    Footer,
    Header,
    Static,
    TabbedContent,
    TabPane,
)

from tui.runner import build_view_argv, preview_string
from tui.screens.result import ResultScreen
from tui.spec import CommandSpec, command
from tui.widgets import ArgField, DateRange


class BuilderScreen(Screen):
    BINDINGS = [
        ("escape", "app.pop_screen", "Home"),
        ("ctrl+r", "run", "Run"),
        ("ctrl+y", "copy", "Copy command"),
    ]

    def __init__(self, command_name: str, *, db_path: str = "calendar.db") -> None:
        super().__init__()
        self.cmd: CommandSpec = command(command_name)
        self._db_path = db_path
        self._daterange: DateRange | None = None

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(f"Builder · {self.cmd.name}", id="builder-title")
        with TabbedContent(id="builder-tabs"):
            has_dates = any(p.kind == "date" for p in self.cmd.positionals)
            if has_dates:
                with TabPane("Dates", id="tab-dates"):
                    self._daterange = DateRange()
                    yield self._daterange
                    for p in self.cmd.positionals:
                        if p.kind != "date":
                            yield ArgField(p, db_path=self._db_path)
            elif self.cmd.positionals:
                with TabPane("Arguments", id="tab-args"):
                    for p in self.cmd.positionals:
                        yield ArgField(p, db_path=self._db_path)

            for group in self.cmd.groups:
                slug = "tab-" + group.lower().replace(" ", "-").replace("/", "-")
                with TabPane(group, id=slug):
                    with VerticalScroll():
                        for spec in self.cmd.options_in(group):
                            yield ArgField(spec, db_path=self._db_path)

        yield Static("", id="builder-cmd")
        with Horizontal(id="builder-actions"):
            yield Button("Run  (Ctrl+R)", id="btn-run", variant="success")
            yield Button("Refresh command", id="btn-refresh")
            yield Button("Home", id="btn-home")
        yield Footer()

    def on_mount(self) -> None:
        self._refresh_command()

    # ----- value collection -------------------------------------------- #

    def _collect(self) -> dict[str, object]:
        values: dict[str, object] = {}
        if self._daterange is not None:
            values["begin"] = self._daterange.begin
            values["end"] = self._daterange.end
        for field in self.query(ArgField):
            values[field.spec.dest] = field.get_value()
        return values

    def _argv(self) -> list[str]:
        return build_view_argv(self.cmd, self._collect())

    def _refresh_command(self) -> None:
        self.query_one("#builder-cmd", Static).update(
            preview_string(self._argv()))

    # ----- actions ------------------------------------------------------ #

    @on(Button.Pressed, "#btn-refresh")
    def _on_refresh(self) -> None:
        self._refresh_command()

    @on(Button.Pressed, "#btn-home")
    def _on_home(self) -> None:
        self.app.pop_screen()

    @on(Button.Pressed, "#btn-run")
    def action_run(self) -> None:
        argv = self._argv()
        self.app.push_screen(
            ResultScreen(argv, cwd=str(self.app.project_root),
                         entry="ecalendar.py",
                         title=f"Run · ecalendar {self.cmd.name}")
        )

    def action_copy(self) -> None:
        try:
            self.app.copy_to_clipboard(preview_string(self._argv()))
            self.notify("Command copied.")
        except Exception:
            self.notify("Copy unavailable.", severity="warning")
