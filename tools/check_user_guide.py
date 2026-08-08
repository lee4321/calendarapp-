#!/usr/bin/env python
"""
Run every ecalendar.py example command in USER_GUIDE.md.

Keeps the guide honest: extracts fenced ``` code blocks, picks the lines
that invoke ``ecalendar.py``, and executes each one, failing on non-zero
exit. Interactive tools (the TUI) and importer examples are skipped —
they either need a terminal or would write to the real database.

Usage:
    uv run python tools/check_user_guide.py            # run everything
    uv run python tools/check_user_guide.py --list     # just show commands

Exit status: number of failing commands (0 = guide is honest).
"""

from __future__ import annotations

import re
import shlex
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GUIDE = ROOT / "USER_GUIDE.md"

# Any language tag, not just the shell ones: a ```yaml block that the
# pattern failed to recognize as an *opening* fence used to shift the
# scanner's parity, so every example after the first YAML sample fell
# outside any matched block and was silently skipped.
FENCE_RE = re.compile(r"```[A-Za-z0-9_+-]*\n(.*?)```", re.DOTALL)


def extract_commands(text: str) -> list[str]:
    """ecalendar.py invocations from fenced code blocks, one per line."""
    commands: list[str] = []
    for block in FENCE_RE.findall(text):
        for line in block.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "ecalendar.py" not in line:
                continue  # TUI, importers, shell prose
            # Only lines shaped like commands — not table rows / prose that
            # merely mention ecalendar.py inside a code block.
            if not line.startswith(("PYTHONPATH=", "uv run", "python ")):
                continue
            commands.append(line)
    return commands


def main() -> int:
    commands = extract_commands(GUIDE.read_text())
    if "--list" in sys.argv:
        print("\n".join(commands))
        return 0

    failures: list[tuple[str, str]] = []
    for i, cmd in enumerate(commands, 1):
        # Examples are written with a PYTHONPATH=. prefix; run via shell so
        # the env assignment works exactly as a user would type it.
        print(f"[{i}/{len(commands)}] {cmd}")
        proc = subprocess.run(
            cmd,
            shell=True,
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=300,
        )
        if proc.returncode != 0:
            tail = (proc.stderr or proc.stdout).strip().splitlines()[-3:]
            failures.append((cmd, " | ".join(tail)))
            print(f"    FAILED (exit {proc.returncode}): {' | '.join(tail)}")

    print()
    if failures:
        print(f"{len(failures)} of {len(commands)} guide commands FAILED:")
        for cmd, err in failures:
            print(f"  {cmd}\n      {err}")
    else:
        print(f"All {len(commands)} guide commands succeeded.")
    return len(failures)


if __name__ == "__main__":
    sys.exit(main())
