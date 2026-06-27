#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Slint UI proof-of-concept for ``importers/import_events.py``.

This is a *thin* front-end: it collects options from a Slint form, shells out to
``importers/import_events.py …`` in a fresh process, and streams the combined
stdout/stderr into a native read-only console pane.

Why a console instead of an SVG preview (cf. the sibling ``app.py`` PIT POC)?
    import_events.py doesn't render anything — it *writes to calendar.db* and
    emits plain-text logs (import summaries, history listings, validation
    warnings). The natural "output surface" is therefore the captured text, not
    an image.

Why subprocess instead of importing the module in-process?
    - Clean isolation: argparse ``SystemExit``, ``sys.exit()`` calls, global
      logging config, and the module's ``input()`` prompts are confined to a
      fresh process per run.
    - It exercises the exact CLI surface a user already knows.
    - ``sys.executable`` is the uv-managed venv interpreter, so there is no
      ``uv run`` re-resolution cost — the subprocess starts immediately.

Safety notes specific to this tool:
    - ``--remove`` and the GUI never share a terminal, so we run with
      ``stdin=DEVNULL`` and always pass ``--force`` (the in-app confirmation
      checkbox stands in for the CLI's ``[y/N]`` prompt). With DEVNULL any stray
      ``input()`` would EOF rather than hang.
    - "Dry run" defaults ON for the two writing modes, so an accidental Run
      validates rather than mutates the database.

Threading model (identical to the PIT POC):
    Slint owns the event loop on the main thread. Each Run launches a daemon
    worker thread for the subprocess; a repeating ``slint.Timer`` (which fires
    *on* the loop thread) polls for the result and updates the console/status,
    so UI state is never touched from the worker.

Run from the project root:
    uv run python slint_ui/import_app.py
"""

from __future__ import annotations

import datetime
import shlex
import subprocess
import sys
import threading
from pathlib import Path

import slint

# Resolve project paths relative to this file so the app works regardless of cwd.
HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
UI_FILE = HERE / "import_window.slint"
IMPORTER = "importers/import_events.py"  # relative to ROOT (the subprocess cwd)

POLL_INTERVAL = datetime.timedelta(milliseconds=150)
SUBPROCESS_TIMEOUT_S = 300

# Mode indices — must match the ComboBox order in import_window.slint.
MODE_IMPORT, MODE_GENERATE, MODE_LIST, MODE_REMOVE = range(4)


class ImportEventsApp:
    """Wires the Slint MainWindow to the import_events.py CLI."""

    def __init__(self) -> None:
        ui = slint.load_file(str(UI_FILE))
        self.window = ui.MainWindow()
        # NB: the Slint callback is `run_import`, not `run` — binding to `run`
        # would shadow the component's built-in `.run()` event-loop method.
        self.window.run_import = self._on_run
        self.window.clear_console = self._on_clear

        # Cross-thread handoff: worker writes _result, the poll Timer reads it.
        self._result: tuple[int, str] | None = None
        self._poll_timer: slint.Timer | None = None

    # ----- UI event handlers (run on the Slint event-loop thread) -----

    def _on_clear(self) -> None:
        self.window.console_text = ""
        self.window.status_text = "Cleared."

    def _on_run(self) -> None:
        try:
            argv = self._build_argv()
        except ValueError as exc:
            # A missing required field — report without launching anything.
            self.window.console_text = f"⚠ {exc}\n"
            self.window.status_text = str(exc)
            return

        pretty = " ".join(shlex.quote(a) for a in argv[1:])
        self.window.running = True
        self.window.console_text = f"$ python {pretty}\n\n(running…)\n"
        self.window.status_text = "Running…"
        self._result = None

        threading.Thread(target=self._worker, args=(argv,), daemon=True).start()

        # Poll for completion on the loop thread (Timers fire there, so it is
        # safe to update window properties from inside _poll).
        self._poll_timer = slint.Timer()
        self._poll_timer.start(slint.TimerMode.Repeated, POLL_INTERVAL, self._poll)

    def _poll(self) -> None:
        if self._result is None:
            return  # worker still running
        code, output = self._result
        self._result = None
        if self._poll_timer is not None:
            self._poll_timer.stop()
        self.window.running = False

        header = f"$ python {self._last_pretty}\n\n"
        self.window.console_text = header + (output or "(no output)\n")
        if code == 0:
            self.window.status_text = "Done — exit 0"
        else:
            self.window.status_text = f"Finished with exit code {code}"

    # ----- worker thread -----

    def _worker(self, argv: list[str]) -> None:
        try:
            proc = subprocess.run(
                argv,
                cwd=str(ROOT),
                capture_output=False,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,  # merge so log order is preserved
                text=True,
                timeout=SUBPROCESS_TIMEOUT_S,
            )
            self._result = (proc.returncode, proc.stdout)
        except subprocess.TimeoutExpired:
            self._result = (-1, f"Timed out after {SUBPROCESS_TIMEOUT_S}s\n")
        except Exception as exc:  # noqa: BLE001 - surface any failure in the UI
            self._result = (-1, f"{type(exc).__name__}: {exc}\n")

    # ----- argv assembly -----

    def _build_argv(self) -> list[str]:
        """Assemble the import_events.py argv for the active mode.

        Raises ValueError for a missing required field so the caller can report
        it in the console without spawning a process.
        """
        w = self.window
        mode = int(w.mode_index)

        argv: list[str] = [sys.executable, IMPORTER]

        # --- Common options (apply to every mode) ---
        argv += ["--database", (w.database.strip() or "calendar.db")]
        uid = w.user_id.strip()
        if uid:
            argv += ["--user-id", uid]
        argv += ["--log-level", w.log_level]
        if w.verbose:
            argv.append("--verbose")

        if mode == MODE_IMPORT:
            paths = shlex.split(w.files_path.strip())
            if not paths:
                raise ValueError("Enter at least one file or directory to import.")
            if w.replace:
                argv.append("--replace")
            if w.dry_run:
                argv.append("--dry-run")
            if w.skip_errors:
                argv.append("--skip-errors")
            argv += paths  # positional files last

        elif mode == MODE_GENERATE:
            script = w.generate_script.strip()
            if not script:
                raise ValueError("Enter the path to a generator script (.py).")
            argv += ["--generate", script]
            sd, ed = w.start_date.strip(), w.end_date.strip()
            # The CLI requires start/end as a pair; surface it early.
            if bool(sd) != bool(ed):
                raise ValueError("Start date and end date must be set together.")
            if sd:
                argv += ["--start-date", sd, "--end-date", ed]
            for line in w.params_text.splitlines():
                line = line.strip()
                if line:
                    argv += ["--param", line]
            if w.replace:
                argv.append("--replace")
            if w.dry_run:
                argv.append("--dry-run")
            if w.skip_errors:
                argv.append("--skip-errors")

        elif mode == MODE_LIST:
            argv.append("--list")

        elif mode == MODE_REMOVE:
            pattern = w.remove_pattern.strip()
            if not pattern:
                raise ValueError("Enter an import-ID pattern to remove.")
            # No shared terminal → always --force (UI checkbox is the gate).
            argv += ["--remove", pattern, "--force"]

        # Remember the pretty form so _poll can rebuild the header verbatim.
        self._last_pretty = " ".join(shlex.quote(a) for a in argv[1:])
        return argv

    def run(self) -> None:
        self.window.run()


def main() -> int:
    if not UI_FILE.exists():
        print(f"UI file not found: {UI_FILE}", file=sys.stderr)
        return 1
    ImportEventsApp().run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
