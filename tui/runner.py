"""Build an argv from collected form values and run it via ``uv run``.

The TUI never imports the calendar engine's render path; it shells out so each
run is isolated and the live command bar shows exactly what would be typed.
"""

from __future__ import annotations

import shlex
import subprocess
from dataclasses import dataclass

from tui.spec import ArgSpec, CommandSpec


def _emit_value(spec: ArgSpec, value) -> list[str]:
    """Tokens for one option given its current widget value (or [] to omit)."""
    if spec.kind == "flag":
        return [spec.option] if value else []
    if spec.kind == "count":
        n = int(value or 0)
        return [spec.option] * n
    if spec.kind == "append":
        # value is a list of "KEY=VALUE" lines.
        out: list[str] = []
        for item in value or []:
            item = item.strip()
            if item:
                out += [spec.option, item]
        return out
    # text / int / float / choice / picker
    if value is None:
        return []
    text = str(value).strip()
    if text == "" or text == str(spec.default):
        return []
    return [spec.option, text]


def build_view_argv(cmd: CommandSpec, values: dict[str, object]) -> list[str]:
    """Assemble ['weekly', '20260101', '20260331', '--theme', 'corporate', ...]."""
    argv: list[str] = [cmd.name]

    # Positionals in declared order; only emit trailing ones if earlier set.
    pos_tokens: list[str] = []
    for p in cmd.positionals:
        v = values.get(p.dest)
        text = "" if v is None else str(v).strip()
        if text == "":
            break
        pos_tokens.append(text)
    argv += pos_tokens

    for opt in cmd.options:
        argv += _emit_value(opt, values.get(opt.dest))
    return argv


def full_command(argv: list[str], *, python_entry: str = "ecalendar.py") -> list[str]:
    return ["uv", "run", python_entry, *argv]


def preview_string(argv: list[str], *, python_entry: str = "ecalendar.py") -> str:
    return " ".join(shlex.quote(t) for t in full_command(argv, python_entry=python_entry))


@dataclass
class RunResult:
    returncode: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0


def run_blocking(
    argv: list[str], *, cwd: str, python_entry: str = "ecalendar.py"
) -> RunResult:
    """Run synchronously (call from a worker thread). Captures combined output."""
    cmd = full_command(argv, python_entry=python_entry)
    proc = subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
    )
    return RunResult(proc.returncode, proc.stdout, proc.stderr)
