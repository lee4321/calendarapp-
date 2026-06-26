#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Slint UI proof-of-concept for the ecalendar `pit` (Points-in-Time) visualizer.

This is a *thin* front-end: it collects PIT options from a Slint form, shells
out to ``ecalendar.py pit ...`` to render an SVG into ``output/``, and displays
that SVG in a native preview pane via Slint's resvg-backed Image element.

Why subprocess instead of importing ecalendar.run() in-process?
    - Clean isolation: argparse errors (SystemExit), global logging config, and
      any module-level font/size state are confined to a fresh process per run.
    - It exercises the exact CLI surface a user already knows.
    ``sys.executable`` is the uv-managed venv interpreter, so there is no
    ``uv run`` re-resolution cost — the subprocess starts immediately.

Threading model:
    Slint owns the (asyncio-integrated) event loop on the main thread. Each
    Generate click launches a daemon worker thread that runs the subprocess,
    while a repeating ``slint.Timer`` (which fires *on* the loop thread) polls
    for the result and safely updates the Image/status properties. This avoids
    touching UI state from the worker thread.

Run from the project root:
    uv run python slint_ui/app.py
"""

from __future__ import annotations

import datetime
import subprocess
import sys
import threading
from pathlib import Path

import slint

# Resolve project paths relative to this file so the app works regardless of cwd.
HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
UI_FILE = HERE / "pit_window.slint"
OUTPUT_FILENAME = "pit_preview.svg"  # deterministic so we always know where it lands
OUTPUT_PATH = ROOT / "output" / OUTPUT_FILENAME

POLL_INTERVAL = datetime.timedelta(milliseconds=150)
SUBPROCESS_TIMEOUT_S = 120


class PitPreviewApp:
    """Wires the Slint MainWindow to the ecalendar `pit` subcommand."""

    def __init__(self) -> None:
        ui = slint.load_file(str(UI_FILE))
        self.window = ui.MainWindow()
        # Bind the Slint `generate()` callback to our handler.
        self.window.generate = self._on_generate

        # Cross-thread handoff: worker writes _result, the poll Timer reads it.
        self._result: tuple[int, str, str] | None = None
        self._poll_timer: slint.Timer | None = None

    # ----- UI event handlers (run on the Slint event-loop thread) -----

    def _on_generate(self) -> None:
        argv = self._build_argv()
        self.window.generating = True
        self.window.status_text = "Generating…  " + " ".join(argv[1:])
        self._result = None

        threading.Thread(target=self._worker, args=(argv,), daemon=True).start()

        # Poll for completion on the loop thread (Timers fire there, so it is
        # safe to update window properties from inside _poll).
        self._poll_timer = slint.Timer()
        self._poll_timer.start(slint.TimerMode.Repeated, POLL_INTERVAL, self._poll)

    def _poll(self) -> None:
        if self._result is None:
            return  # worker still running
        code, out, err = self._result
        self._result = None
        if self._poll_timer is not None:
            self._poll_timer.stop()
        self.window.generating = False

        if code == 0 and OUTPUT_PATH.exists():
            # load_from_path re-reads the file; assigning a fresh Image triggers
            # a redraw of the preview pane.
            self.window.preview_image = slint.Image.load_from_path(str(OUTPUT_PATH))
            self.window.status_text = f"OK — rendered output/{OUTPUT_FILENAME}"
        else:
            detail = (err.strip() or out.strip() or f"exit code {code}")
            last_line = detail.splitlines()[-1] if detail else f"exit code {code}"
            self.window.status_text = f"Error: {last_line}"

    # ----- worker thread -----

    def _worker(self, argv: list[str]) -> None:
        try:
            proc = subprocess.run(
                argv,
                cwd=str(ROOT),
                capture_output=True,
                text=True,
                timeout=SUBPROCESS_TIMEOUT_S,
            )
            self._result = (proc.returncode, proc.stdout, proc.stderr)
        except subprocess.TimeoutExpired:
            self._result = (-1, "", f"timed out after {SUBPROCESS_TIMEOUT_S}s")
        except Exception as exc:  # noqa: BLE001 - surface any failure in the UI
            self._result = (-1, "", str(exc))

    # ----- argv assembly -----

    def _build_argv(self) -> list[str]:
        w = self.window
        argv: list[str] = [
            sys.executable,
            "ecalendar.py",
            "pit",
            w.begin_date.strip(),
            w.end_date.strip(),
            "--outputfile",
            OUTPUT_FILENAME,
        ]

        def opt(flag: str, value: str) -> None:
            """Append ``flag value`` when the text value is non-blank."""
            v = value.strip()
            if v:
                argv.extend([flag, v])

        def choice(flag: str, value: str, sentinel: str) -> None:
            """Append a ComboBox choice unless it is the 'leave at default' sentinel."""
            if value and value != sentinel:
                argv.extend([flag, value])

        def flag_if(flag: str, value: bool) -> None:
            """Append a bare store_true/store_false flag when checked."""
            if value:
                argv.append(flag)

        # --- Database ---
        argv.extend(["--database", (w.database.strip() or "calendar.db")])

        # --- Output / page ---
        choice("--theme", w.theme, "(none)")
        argv.extend(["--papersize", w.papersize])
        argv.extend(["--orientation", w.orientation])
        argv.extend(["--weekends", str(w.weekends_index)])
        opt("--weekend-days", w.weekend_days)
        flag_if("--margin", w.margin)
        flag_if("--monthnames", w.monthnames)
        flag_if("--shrink", w.shrink)
        flag_if("--embed-data", w.embed_data)

        # --- Header / footer ---
        flag_if("--header", w.show_header)
        flag_if("--footer", w.show_footer)
        opt("--headerleft", w.header_left)
        opt("--headercenter", w.header_center)
        opt("--headerright", w.header_right)
        opt("--footerleft", w.footer_left)
        opt("--footercenter", w.footer_center)
        opt("--footerright", w.footer_right)

        # --- Watermark ---
        opt("--watermark-text", w.watermark_text)
        opt("--watermark-rotation-angle", w.watermark_rotation)
        opt("--watermark-image", w.watermark_image)

        # --- Content filters ---
        flag_if("--empty", w.empty)
        flag_if("--shade", w.shade)
        flag_if("--noevents", w.no_events)
        flag_if("--nodurations", w.no_durations)
        flag_if("--ignorecomplete", w.ignore_complete)
        flag_if("--milestones", w.milestones_only)
        flag_if("--rollups", w.rollups_only)
        flag_if("--includenotes", w.include_notes)
        flag_if("--overflow", w.overflow)
        opt("--WBS", w.wbs)
        opt("--status", w.status)
        opt("--country", w.country)

        # --- PIT: axis & ticks ---
        choice("--direction", w.direction, "(default)")
        choice("--label-side", w.label_side, "(default)")
        choice("--tick-unit", w.tick_unit, "(default)")
        opt("--tick-interval", w.tick_interval)
        opt("--tick-label-format", w.tick_label_format)
        opt("--tick-length", w.tick_length)
        flag_if("--no-ticks", w.hide_ticks)
        flag_if("--no-tick-labels", w.hide_tick_labels)
        choice("--date-placement", w.date_placement, "(default)")

        # --- PIT: today line (tri-state: (default) / on / off) ---
        if w.today_line == "on":
            argv.append("--today-line")
        elif w.today_line == "off":
            argv.append("--no-today-line")
        opt("--today-date", w.today_date)
        opt("--today-label", w.today_label)

        # --- PIT: markers & icons ---
        opt("--event-icon", w.event_icon)
        opt("--milestone-icon", w.milestone_icon)
        opt("--marker-size", w.marker_size)
        opt("--label-icon-size", w.label_icon_size)
        opt("--label-icon-gap", w.label_icon_gap)

        # --- PIT: leaders ---
        opt("--leader-dash", w.leader_dash)
        choice("--leader-label-anchor", w.leader_label_anchor, "(default)")
        opt("--leader-length", w.leader_length)
        opt("--leader-stub", w.leader_stub)

        # --- Fiscal ---
        choice("--fiscal", w.fiscal, "(none)")
        opt("--fiscal-year-offset", w.fiscal_year_offset)

        # --- Logging ---
        if w.verbose_index > 0:
            argv.append("-" + "v" * w.verbose_index)
        flag_if("--quiet", w.quiet)

        return argv

    def run(self) -> None:
        self.window.run()


def main() -> int:
    if not UI_FILE.exists():
        print(f"UI file not found: {UI_FILE}", file=sys.stderr)
        return 1
    PitPreviewApp().run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
