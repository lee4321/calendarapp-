"""Import Hub + shared import wizard (events / special days / holidays / content)."""

from __future__ import annotations

from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import (
    Button,
    Footer,
    Header,
    Input,
    Label,
    ListItem,
    ListView,
    Select,
    Static,
    Switch,
)

from tui.importers_spec import ImporterSpec, all_importers, build_import_argv
from tui.screens.result import ResultScreen


class ImportHubScreen(Screen):
    """Pick a data type to import."""

    BINDINGS = [("escape", "app.pop_screen", "Home")]

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static("Import Hub — pick a data type", id="hub-title")
        items = []
        self._keys: list[str] = []
        for key, spec in all_importers().items():
            self._keys.append(key)
            items.append(
                ListItem(
                    Vertical(
                        Label(spec.title, classes="hub-name"),
                        Static(spec.summary, classes="hub-sub"),
                    )
                )
            )
        yield ListView(*items, id="hub-list")
        yield Static("[b]Enter[/b] open wizard   ·   [b]Esc[/b] home", classes="arghelp")
        yield Footer()

    @on(ListView.Selected, "#hub-list")
    def _open(self, event: ListView.Selected) -> None:
        idx = event.list_view.index or 0
        key = self._keys[idx]
        self.app.push_screen(ImportWizardScreen(key))


class ImportWizardScreen(Screen):
    """Shared field-driven wizard for one importer."""

    BINDINGS = [
        ("escape", "app.pop_screen", "Back"),
        ("ctrl+d", "dry_run", "Dry run"),
        ("ctrl+r", "do_import", "Import"),
    ]

    def __init__(self, importer_key: str) -> None:
        super().__init__()
        self.spec: ImporterSpec = all_importers()[importer_key]
        self._controls: dict[str, object] = {}

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(f"Import · {self.spec.title}", id="wizard-title")
        yield Static(self.spec.summary, classes="arghelp")
        with VerticalScroll(id="wizard-fields"):
            for f in self.spec.fields:
                with Vertical(classes="argfield"):
                    yield Label(f.label + ("  (generator only)" if f.generator_only
                                           else ""), classes="arglabel")
                    cid = f"imp-{f.dest}"
                    if f.kind == "flag":
                        yield Switch(value=bool(f.default), id=cid)
                    elif f.kind == "choice":
                        opts = [(c, c) for c in (f.choices or [])]
                        yield Select(opts, value=str(f.default), id=cid,
                                     allow_blank=False)
                    elif f.kind == "int":
                        yield Input(value=str(f.default or ""), type="integer",
                                    id=cid, classes="narrow")
                    else:
                        yield Input(value=str(f.default or ""),
                                    placeholder=("path/to/file or folder"
                                                 if f.kind in ("path", "dir") else ""),
                                    id=cid)
                    if f.help:
                        yield Static(f.help, classes="arghelp")
        with Horizontal(id="wizard-actions"):
            yield Button("Dry run  (Ctrl+D)", id="btn-dry", variant="primary")
            yield Button("Import  (Ctrl+R)", id="btn-import", variant="warning")
            yield Button("Back", id="btn-back")
        yield Footer()

    def _collect(self) -> dict[str, object]:
        values: dict[str, object] = {}
        for f in self.spec.fields:
            ctl = self.query_one(f"#imp-{f.dest}")
            if isinstance(ctl, Switch):
                values[f.dest] = ctl.value
            elif isinstance(ctl, Select):
                values[f.dest] = None if ctl.is_blank() else ctl.value
            else:
                values[f.dest] = ctl.value
        return values

    def _launch(self, *, force_dry: bool) -> None:
        values = self._collect()
        if force_dry and "dry_run" in {f.dest for f in self.spec.fields}:
            values["dry_run"] = True
        argv = build_import_argv(self.spec, values)
        verb = "Dry run" if force_dry else "Import"
        self.app.push_screen(
            ResultScreen(argv, cwd=str(self.app.project_root),
                         entry=self.spec.script,
                         title=f"{verb} · {self.spec.title}")
        )

    def action_dry_run(self) -> None:
        self._launch(force_dry=True)

    def action_do_import(self) -> None:
        self._launch(force_dry=False)

    @on(Button.Pressed, "#btn-dry")
    def _dry(self) -> None:
        self.action_dry_run()

    @on(Button.Pressed, "#btn-import")
    def _imp(self) -> None:
        self.action_do_import()

    @on(Button.Pressed, "#btn-back")
    def _back(self) -> None:
        self.app.pop_screen()
