"""Run a command in a worker thread and stream its output."""

from __future__ import annotations

import subprocess

from textual import work
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, RichLog, Static

from tui.runner import full_command, preview_string


class ResultScreen(Screen):
    """Generic runner: takes an argv tail + entry script, shows live output."""

    BINDINGS = [
        ("escape", "app.pop_screen", "Back"),
        ("c", "copy", "Copy command"),
        ("r", "rerun", "Re-run"),
    ]

    def __init__(self, argv: list[str], *, cwd: str, entry: str, title: str) -> None:
        super().__init__()
        self._argv = argv
        self._cwd = cwd
        self._entry = entry
        self._title = title

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="result-body"):
            yield Static(self._title, id="result-title")
            yield Static(preview_string(self._argv, python_entry=self._entry),
                         id="result-cmd")
            yield Static("◐ running…", id="result-status")
            yield RichLog(id="result-log", highlight=True, markup=True, wrap=True)
            with Horizontal(id="result-actions"):
                yield Button("Re-run", id="btn-rerun", variant="primary")
                yield Button("Copy command", id="btn-copy")
                yield Button("Back", id="btn-back")
        yield Footer()

    def on_mount(self) -> None:
        self._run()

    @work(exclusive=True, thread=True)
    def _run(self) -> None:
        log = self.query_one("#result-log", RichLog)
        status = self.query_one("#result-status", Static)
        cmd = full_command(self._argv, python_entry=self._entry)
        self.app.call_from_thread(log.write, f"[dim]$ {' '.join(cmd)}[/dim]")
        try:
            proc = subprocess.Popen(
                cmd, cwd=self._cwd, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, text=True, bufsize=1,
            )
        except Exception as exc:  # pragma: no cover - launch failure
            self.app.call_from_thread(log.write, f"[red]Failed to launch: {exc}[/red]")
            self.app.call_from_thread(status.update, "✗ launch error")
            return

        assert proc.stdout is not None
        for line in proc.stdout:
            self.app.call_from_thread(log.write, line.rstrip("\n"))
        code = proc.wait()
        if code == 0:
            self.app.call_from_thread(status.update, "[green]✓ done[/green]")
        else:
            self.app.call_from_thread(
                status.update, f"[red]✗ exit {code}[/red]")

    def action_rerun(self) -> None:
        self.query_one("#result-log", RichLog).clear()
        self.query_one("#result-status", Static).update("◐ running…")
        self._run()

    def action_copy(self) -> None:
        cmd = preview_string(self._argv, python_entry=self._entry)
        try:
            self.app.copy_to_clipboard(cmd)
            self.notify("Command copied to clipboard.")
        except Exception:
            self.notify("Copy unavailable in this terminal.", severity="warning")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-rerun":
            self.action_rerun()
        elif event.button.id == "btn-copy":
            self.action_copy()
        elif event.button.id == "btn-back":
            self.app.pop_screen()
