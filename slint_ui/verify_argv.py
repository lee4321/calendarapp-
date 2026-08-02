#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Headless coverage check for the unified Slint front-end's argv builder.

For every subcommand the GUI drives, this builds the CLI argv with
``ecalendar_app.build_argv`` (the exact code path the window uses), runs
``ecalendar.py`` in a subprocess, and asserts it exits 0 and produces the
expected output file. It exercises the whole emit table without a display, so it
can run in CI / headless environments where the Slint window cannot open.

Run from the project root:
    uv run python slint_ui/verify_argv.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from ecalendar_app import (  # noqa: E402  (import after sys.path fix in the module)
    COMMANDS,
    OUTPUT,
    ROOT,
    build_argv,
    representative_values,
)


def _resolve(output_name: str, paginate: bool) -> Path | None:
    candidates: list[Path] = []
    # colorsheet / iconsheet / palettesheet all write <stem>_pNN.svg when the
    # run produces more than one page.
    if paginate:
        stem = output_name[:-4] if output_name.endswith(".svg") else output_name
        candidates += [ROOT / "output" / f"{stem}_p01.svg"]
    candidates += [ROOT / "output" / output_name, ROOT / output_name]
    for c in candidates:
        if c.exists():
            return c
    return None


def main() -> int:
    failures: list[str] = []
    for command, _hint in COMMANDS:
        output_name, mode = OUTPUT[command]
        values = representative_values(command)
        argv = build_argv(command, values, output_name)

        # Clean any stale output so "exists" means "this run produced it".
        stale = _resolve(output_name, paginate=False)
        if stale is not None:
            stale.unlink()

        proc = subprocess.run(
            argv, cwd=str(ROOT), capture_output=True, text=True, timeout=180
        )
        out_path = _resolve(output_name, paginate=False)
        ok = proc.returncode == 0 and out_path is not None

        status = "PASS" if ok else "FAIL"
        detail = ""
        if not ok:
            if proc.returncode != 0:
                tail = (proc.stderr.strip() or proc.stdout.strip()).splitlines()
                detail = "  exit=%d  %s" % (
                    proc.returncode,
                    tail[-1] if tail else "(no output)",
                )
            else:
                detail = "  ran OK but no output file (%s)" % output_name
            failures.append(command)
        loc = out_path.relative_to(ROOT) if out_path else "-"
        print(f"[{status}] {command:<14} {mode:<6} -> {loc}{detail}")

    print()
    if failures:
        print(f"{len(failures)} FAILED: {', '.join(failures)}")
        return 1
    print(f"All {len(COMMANDS)} subcommands OK.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
