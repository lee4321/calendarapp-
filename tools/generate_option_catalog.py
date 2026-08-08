#!/usr/bin/env python
"""
Regenerate the CLI tables in USER_GUIDE.md from the argument parser, so they
cannot drift from the CLI they document:

* the "Command-Line Option Catalog" section, which is entirely generated;
* the per-command tables under "Positional Arguments by Command".

The positional section is **not** wholly generated: each ``### <command>``
block carries hand-written prose (the excelheader column layout, the
freeze-pane rationale, per-view flag notes) that no parser knows about.  Only
the markdown table inside each block is replaced; the prose around it is left
exactly as written.

Usage:
    uv run python tools/generate_option_catalog.py           # rewrite the section
    uv run python tools/generate_option_catalog.py --print   # write to stdout
    uv run python tools/generate_option_catalog.py --check   # exit 1 when stale

The hand-maintained table this replaces had drifted: newer subcommands were
missing from most rows, and per-command defaults were quoted for one command
when every command shared them.  ``tests/test_option_catalog.py`` runs
``--check`` so the next drift fails the build instead of the reader.

Column rules
------------
Option(s)         Long option(s), plus short flags.  When the short flag
                  differs by subcommand it is annotated per command.
Metavar           Only an explicitly declared metavar; argparse's implicit
                  DEST-derived one is noise.
Commands          Every subcommand that accepts the option.
Description       The help text.  Where subcommands word it differently the
                  majority text leads and the exceptions follow, tagged.
Defaults/Choices  A default shared by every subcommand is stated once;
                  otherwise each distinct value is tagged with its commands.
                  ``choices`` follow.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

GUIDE = ROOT / "USER_GUIDE.md"
HEADING = "## Command-Line Option Catalog (All Options)"
POSITIONAL_HEADING = "## Positional Arguments by Command"

POSITIONAL_HEADER = (
    "| Name | Required | Description | Choices |\n|---|---|---|---|"
)

PREAMBLE = (
    "Generated from the argument parser by `tools/generate_option_catalog.py`.\n"
    "Run that script after changing `cli/args.py` rather than editing this\n"
    "table by hand.\n"
)


def _subcommand_parsers() -> dict[str, argparse.ArgumentParser]:
    """Every registered subcommand, name → parser."""
    from cli.args import _create_argument_parser

    parser = _create_argument_parser("ecalendar.svg")
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return dict(action.choices)
    return {}


def _collect() -> dict[tuple[str, ...], dict[str, argparse.Action]]:
    """Map long-option signature → {subcommand: the action it registered}.

    Grouping on the long options keeps an option one row even where a
    subcommand gives it a different short flag (``exportdata`` uses ``-o``
    for ``--outputfile``).
    """
    collected: dict[tuple[str, ...], dict[str, argparse.Action]] = defaultdict(dict)
    for name, sub in sorted(_subcommand_parsers().items()):
        for action in sub._actions:
            if not action.option_strings or "--help" in action.option_strings:
                continue
            longs = tuple(o for o in action.option_strings if o.startswith("--"))
            key = longs or tuple(action.option_strings)
            collected[key][name] = action
    return collected


def _md(value: object) -> str:
    """A value as inline code, with table pipes escaped."""
    return f"`{str(value).replace('|', chr(92) + '|')}`"


def _options_cell(key: tuple[str, ...], actions: dict[str, argparse.Action]) -> str:
    """Long options plus short flags, annotating per-command differences."""
    longs = ", ".join(_md(opt) for opt in key)

    shorts_by_command: dict[str, tuple[str, ...]] = {
        command: tuple(
            o for o in action.option_strings if not o.startswith("--")
        )
        for command, action in actions.items()
    }
    distinct = set(shorts_by_command.values())
    if not distinct or distinct == {()}:
        return longs

    common, _count = Counter(shorts_by_command.values()).most_common(1)[0]
    cell = longs
    if common:
        cell += ", " + ", ".join(_md(s) for s in common)

    exceptions = sorted(
        command
        for command, shorts in shorts_by_command.items()
        if shorts != common and shorts
    )
    if exceptions:
        notes = "; ".join(
            f"{', '.join(_md(s) for s in shorts_by_command[command])} for {_md(command)}"
            for command in exceptions
        )
        cell += f" ({notes})"
    return cell


def _metavar_cell(actions: dict[str, argparse.Action]) -> str:
    """The declared metavar, when the subcommands agree on one."""
    metavars = {a.metavar for a in actions.values() if a.metavar}
    if len(metavars) == 1:
        return _md(metavars.pop())
    return ", ".join(_md(m) for m in sorted(metavars))


def _description_cell(actions: dict[str, argparse.Action]) -> str:
    """Help text: the majority wording, then any subcommand that differs."""
    helps = {command: (action.help or "").strip() for command, action in actions.items()}
    counts = Counter(helps.values())
    majority, _n = counts.most_common(1)[0]

    cell = majority
    others: dict[str, list[str]] = defaultdict(list)
    for command, text in helps.items():
        if text != majority:
            others[text].append(command)

    for text, commands in sorted(others.items(), key=lambda kv: sorted(kv[1])):
        tags = ", ".join(_md(c) for c in sorted(commands))
        cell += f" ({tags}: {text})"
    return cell.replace("|", r"\|")


def _defaults_cell(actions: dict[str, argparse.Action]) -> str:
    """Defaults (shared or per-command) followed by any choices."""
    parts: list[str] = []

    # Keyed by repr so unhashable defaults (lists) still group; the value
    # carries the default itself for rendering.
    defaults: dict[str, tuple[object, list[str]]] = {}
    for command, action in actions.items():
        # None and "" both mean "unset"; rendering them as an empty code
        # span would be noise.  False/0 are real, documented defaults.
        if action.default is None or action.default is argparse.SUPPRESS:
            continue
        if isinstance(action.default, str) and not action.default:
            continue
        _value, commands = defaults.setdefault(repr(action.default), (action.default, []))
        commands.append(command)

    if defaults:
        only = len(defaults) == 1
        shared = only and len(next(iter(defaults.values()))[1]) == len(actions)
        if shared:
            value, _commands = next(iter(defaults.values()))
            parts.append(f"default {_md(value)}")
        else:
            for value, commands in sorted(
                defaults.values(), key=lambda pair: sorted(pair[1])
            ):
                tags = ", ".join(_md(c) for c in sorted(commands))
                parts.append(f"{tags}: default {_md(value)}")

    choices = {
        tuple(str(c) for c in a.choices)
        for a in actions.values()
        if a.choices is not None
    }
    for choice_set in sorted(choices):
        parts.append("choices " + _md(", ".join(choice_set)))

    return "; ".join(parts)


def build_table() -> str:
    """The full section body: preamble, header row, and one row per option."""
    rows = ["| Option(s) | Metavar | Commands | Description | Defaults/Choices |",
            "|---|---|---|---|---|"]

    collected = _collect()
    for key in sorted(collected, key=lambda k: k[0]):
        actions = collected[key]
        commands = ", ".join(_md(c) for c in sorted(actions))
        rows.append(
            "| "
            + " | ".join(
                (
                    _options_cell(key, actions),
                    _metavar_cell(actions),
                    commands,
                    _description_cell(actions),
                    _defaults_cell(actions),
                )
            )
            + " |"
        )

    return f"{HEADING}\n\n{PREAMBLE}\n" + "\n".join(rows) + "\n"


# ── Positional arguments ──────────────────────────────────────────────────


def _positionals(sub: argparse.ArgumentParser) -> list[argparse.Action]:
    """The subcommand's positional actions, in declaration order."""
    return [a for a in sub._actions if not a.option_strings]


def positional_table(sub: argparse.ArgumentParser) -> str:
    """The markdown table for one subcommand's positionals, or ``""``."""
    actions = _positionals(sub)
    if not actions:
        return ""

    rows = [POSITIONAL_HEADER]
    for action in actions:
        name = _md(action.metavar or action.dest)
        # nargs "?" and "*" both mean the user may leave it out.
        required = "no" if action.nargs in ("?", "*") else "yes"
        description = (action.help or "").strip().replace("|", r"\|")
        choices = ", ".join(str(c) for c in action.choices) if action.choices else ""
        rows.append(f"| {name} | {required} | {description} | {choices} |")
    return "\n".join(rows)


def _replace_table(block: str, table: str) -> str:
    """Swap the first markdown table in *block*, leaving prose untouched.

    When the block has no table yet, the new one is inserted directly after
    its heading -- which is where every existing block keeps it.
    """
    lines = block.splitlines()
    start = next(
        (i for i, line in enumerate(lines) if line.startswith("|")), None
    )
    if start is None:
        if not table:
            return block
        heading, rest = lines[0], lines[1:]
        while rest and not rest[0].strip():
            rest.pop(0)
        return "\n".join([heading, "", *table.splitlines(), "", *rest]) + "\n"

    end = start
    while end < len(lines) and lines[end].startswith("|"):
        end += 1
    if not table:
        return block
    return "\n".join([*lines[:start], *table.splitlines(), *lines[end:]]) + "\n"


def sync_positionals(section: str) -> str:
    """Refresh every positional table in the section; keep all prose.

    Subcommands with positionals but no block of their own are appended, so
    a newly added view shows up rather than being silently absent.
    """
    subcommands = _subcommand_parsers()
    blocks = re.split(r"(?m)^(?=### )", section)
    seen: set[str] = set()

    out = [blocks[0]]
    for block in blocks[1:]:
        match = re.match(r"### `([^`]+)`", block)
        if match is None:
            out.append(block)
            continue
        name = match.group(1)
        seen.add(name)
        sub = subcommands.get(name)
        out.append(block if sub is None else _replace_table(block, positional_table(sub)))

    missing = [
        name for name, sub in subcommands.items()
        if name not in seen and _positionals(sub)
    ]
    for name in missing:
        table = positional_table(subcommands[name])
        out.append(f"### `{name}`\n\n{table}\n\n")

    return "".join(out)


def _split_guide(text: str, heading: str = HEADING) -> tuple[str, str, str]:
    """Guide text as ``(before, that section, after)``."""
    start = text.index(heading)
    match = re.search(r"^## ", text[start + len(heading):], re.M)
    end = start + len(heading) + match.start() if match else len(text)
    return text[:start], text[start:end], text[end:]


def regenerate(text: str) -> str:
    """Both sections refreshed, everything else byte-identical."""
    before, _current, after = _split_guide(text)
    text = before + build_table() + "\n" + after

    before, section, after = _split_guide(text, POSITIONAL_HEADING)
    return before + sync_positionals(section) + after


def main() -> int:
    text = GUIDE.read_text()
    updated = regenerate(text)

    if "--print" in sys.argv:
        print(build_table(), end="")
        return 0

    if "--check" in sys.argv:
        if text == updated:
            print("CLI tables are up to date.")
            return 0
        print(
            "CLI tables are stale — regenerate with:\n"
            "  uv run python tools/generate_option_catalog.py",
            file=sys.stderr,
        )
        return 1

    GUIDE.write_text(updated)
    options = len(build_table().splitlines()) - 6
    commands = sum(1 for s in _subcommand_parsers().values() if _positionals(s))
    print(
        f"Rewrote the CLI tables: {options} options, "
        f"positionals for {commands} commands."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
