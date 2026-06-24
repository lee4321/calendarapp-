"""Introspect ecalendar.py's argparse parser into a UI-friendly spec.

This is the single source of truth for the parameter forms.  We walk the real
``_create_argument_parser()`` output once, so any flag added to the CLI shows up
in the TUI automatically and its ``help`` text becomes the field description.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from functools import lru_cache


# Subcommands that take begin/end dates and the full option set.
CALENDAR_VIEWS = [
    "weekly",
    "mini",
    "mini-icon",
    "candybar",
    "text-mini",
    "timeline",
    "pit",
    "blockplan",
    "compactplan",
    "excelheader",
    "excelblockplan",
    "exportdata",
]

# Pure listing / inspection subcommands (no args worth a form).
LISTING_COMMANDS = [
    "themes",
    "papersizes",
    "patterns",
    "icons",
    "colors",
    "palettes",
    "fonts",
]

# Subcommands that render a reference sheet (have a few options).
SHEET_COMMANDS = [
    "palettesheet",
    "iconsheet",
    "patternsheet",
    "colorsheet",
    "fontsheet",
]

# Free-string args whose value-space comes from a listing command -> picker.
PICKER_SOURCE = {
    "theme": "themes",
    "papersize": "papersizes",
}


@dataclass
class ArgSpec:
    """One argparse action, normalised for widget construction."""

    dest: str
    kind: str  # flag | count | choice | int | float | append | text | date | picker
    option: str | None  # canonical "--long" flag, or None for positionals
    help: str
    default: object = None
    choices: list[str] | None = None
    metavar: str | None = None
    group: str = "Options"
    picker_source: str | None = None

    @property
    def label(self) -> str:
        if self.option:
            return self.option.lstrip("-")
        return self.dest


@dataclass
class CommandSpec:
    """One subcommand: its ordered positionals + grouped optional args."""

    name: str
    help: str
    positionals: list[ArgSpec] = field(default_factory=list)
    options: list[ArgSpec] = field(default_factory=list)

    @property
    def groups(self) -> list[str]:
        seen: list[str] = []
        for a in self.options:
            if a.group not in seen:
                seen.append(a.group)
        return seen

    def options_in(self, group: str) -> list[ArgSpec]:
        return [a for a in self.options if a.group == group]


def _canonical_option(option_strings: list[str]) -> str:
    for o in option_strings:
        if o.startswith("--"):
            return o
    return option_strings[0]


def _classify(action: argparse.Action) -> str:
    cls = type(action).__name__
    if cls in ("_StoreTrueAction", "_StoreFalseAction"):
        return "flag"
    if cls == "_CountAction":
        return "count"
    if cls == "_AppendAction":
        return "append"
    if action.choices:
        return "choice"
    if action.type is int:
        return "int"
    if action.type is float:
        return "float"
    return "text"


def _build_arg(action: argparse.Action, group_title: str) -> ArgSpec | None:
    cls = type(action).__name__
    if cls in ("_HelpAction", "_SubParsersAction", "_VersionAction"):
        return None

    help_text = (action.help or "").replace("%%", "%")

    # Positionals (begin / end / palette_name ...).
    if not action.option_strings:
        kind = "date" if action.dest in ("begin", "end") else "text"
        return ArgSpec(
            dest=action.dest,
            kind=kind,
            option=None,
            help=help_text,
            default=action.default,
            metavar=action.metavar,
            group="Dates" if kind == "date" else "Arguments",
        )

    kind = _classify(action)
    option = _canonical_option(action.option_strings)
    choices = [str(c) for c in action.choices] if action.choices else None
    picker = PICKER_SOURCE.get(action.dest)
    if picker and kind == "text":
        kind = "picker"

    return ArgSpec(
        dest=action.dest,
        kind=kind,
        option=option,
        help=help_text,
        default=action.default,
        choices=choices,
        metavar=action.metavar,
        group=group_title or "Options",
        picker_source=picker,
    )


@lru_cache(maxsize=1)
def _parser() -> argparse.ArgumentParser:
    import ecalendar

    return ecalendar._create_argument_parser("ecalendar.svg")


@lru_cache(maxsize=1)
def all_commands() -> dict[str, CommandSpec]:
    """Return every subcommand spec keyed by name."""
    parser = _parser()
    sub_action = next(
        a for a in parser._actions if isinstance(a, argparse._SubParsersAction)
    )

    # argparse stores one (name -> subparser) entry plus aliases; dedupe by id.
    specs: dict[str, CommandSpec] = {}
    help_by_name = {
        choice.dest: choice.help for choice in sub_action._choices_actions
    }

    for name, subparser in sub_action.choices.items():
        if name in specs:
            continue
        cmd = CommandSpec(name=name, help=help_by_name.get(name, ""))
        for arg_group in subparser._action_groups:
            title = arg_group.title or "Options"
            # argparse's two default groups carry positionals/optionals.
            if title == "positional arguments":
                title = "Arguments"
            if title in ("options", "optional arguments"):
                title = "Options"
            for action in arg_group._group_actions:
                spec = _build_arg(action, title)
                if spec is None:
                    continue
                if spec.option is None:
                    cmd.positionals.append(spec)
                else:
                    cmd.options.append(spec)
        specs[name] = cmd
    return specs


def command(name: str) -> CommandSpec:
    return all_commands()[name]
