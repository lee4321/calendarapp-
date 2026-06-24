"""One form field for an ArgSpec — driven entirely by the introspected kind."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Input, Label, Select, Static, Switch

from tui.registry import list_values
from tui.spec import ArgSpec


class ArgField(Vertical):
    """Label + control + help text for a single CLI argument.

    ``get_value()`` returns the current value normalised for the argv builder.
    """

    def __init__(self, spec: ArgSpec, *, db_path: str = "calendar.db") -> None:
        super().__init__(classes="argfield")
        self.spec = spec
        self._db_path = db_path
        self._control_id = f"ctl-{spec.dest}"

    def compose(self) -> ComposeResult:
        spec = self.spec
        yield Label(spec.label, classes="arglabel")

        if spec.kind == "flag":
            yield Switch(value=bool(spec.default), id=self._control_id)

        elif spec.kind == "count":
            yield Input(value="0", type="integer", id=self._control_id,
                        classes="narrow")

        elif spec.kind in ("choice", "picker"):
            options = self._select_options()
            if options is None:
                # Picker source unavailable -> degrade to a free text input.
                yield Input(value=self._default_str(), id=self._control_id)
            else:
                # Textual's blank sentinel must not be passed explicitly; omit
                # `value` to leave the Select blank, and only set it when the
                # default is a real option.
                kwargs = dict(
                    allow_blank=True,
                    prompt=f"(default: {self._default_str() or 'none'})",
                    id=self._control_id,
                )
                default = str(spec.default) if spec.default is not None else None
                if default is not None and any(default == v for _, v in options):
                    kwargs["value"] = default
                yield Select(options, **kwargs)

        elif spec.kind in ("int", "float"):
            yield Input(value=self._default_str(),
                        type="integer" if spec.kind == "int" else "number",
                        id=self._control_id, classes="narrow")

        elif spec.kind == "append":
            yield Input(value="", placeholder="KEY=VALUE (one per line via re-add)",
                        id=self._control_id)

        else:  # text / date positional
            yield Input(value=self._default_str(),
                        placeholder=spec.metavar or "", id=self._control_id)

        if spec.help:
            yield Static(spec.help, classes="arghelp")

    # ----- value access ------------------------------------------------- #

    def _default_str(self) -> str:
        d = self.spec.default
        return "" if d is None else str(d)

    def _select_options(self) -> list[tuple[str, str]] | None:
        spec = self.spec
        if spec.kind == "choice":
            return [(c, c) for c in (spec.choices or [])]
        # picker
        values = list_values(spec.picker_source, self._db_path)
        if not values:
            return None
        # Cap very large lists so the dropdown stays usable.
        capped = list(values)[:500]
        return [(v, v) for v in capped]

    def get_value(self):
        ctl = self.query_one(f"#{self._control_id}")
        if isinstance(ctl, Switch):
            return ctl.value
        if isinstance(ctl, Select):
            return None if ctl.is_blank() else ctl.value
        # Input
        return ctl.value
