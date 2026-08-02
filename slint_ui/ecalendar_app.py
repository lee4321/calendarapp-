#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Unified Slint UI front-end for ecalendar.py.

A single native window drives every render/export subcommand of the CLI:
the 9 SVG visualizers (weekly, mini, mini-icon, candybar, text-mini, timeline,
pit, blockplan, compactplan), the 5 SVG "sheets" (palettesheet, iconsheet,
patternsheet, colorsheet, fontsheet), and the 3 exporters (excelheader,
excelblockplan, exportdata).

Design
------
* Single source of truth for *which flags a subcommand accepts* is the live
  argparse parser. ``import ecalendar`` is side-effect free (execution is guarded
  by ``if __name__ == "__main__"``), so at startup we call
  ``ecalendar._create_argument_parser`` and walk its subparsers to build
  ``FLAGS[cmd]`` (valid long options) and ``POSITIONALS[cmd]`` (positional dests).
  Both form-field *visibility* and CLI-argv *emission* are gated on membership in
  those sets, so the GUI tracks new CLI flags automatically.

* ``build_argv`` is a pure, window-free function (``dict`` of field values in,
  argv list out) so it can be exercised headlessly for every subcommand without
  a live window — see ``verify_argv.py``/the tests.

* Generation runs ``ecalendar.py`` in a fresh subprocess (``sys.executable`` is
  the uv venv interpreter). Slint owns the event loop on the main thread; a
  daemon worker runs the subprocess and a repeating ``slint.Timer`` polls for the
  result and updates the preview — UI state is never touched from the worker.

Run from the project root:
    uv run python slint_ui/ecalendar_app.py
"""

from __future__ import annotations

import argparse
import datetime
import subprocess
import sys
import threading
from pathlib import Path

# Resolve project paths relative to this file so the app works regardless of cwd.
HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
UI_FILE = HERE / "ecalendar_window.slint"

# Ensure the project root is importable so we can introspect the CLI parser.
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

POLL_INTERVAL = datetime.timedelta(milliseconds=150)
SUBPROCESS_TIMEOUT_S = 180
TEXT_PREVIEW_MAX_CHARS = 200_000

# Default date range — a Monday..Tuesday span of weekdays so it renders cleanly
# even with the default weekend_style=0 (work-week-only) layout.
DEFAULT_BEGIN = "20260105"
DEFAULT_END = "20260630"

# Visualizer order — MUST match the ComboBox model order in ecalendar_window.slint.
# (subcommand, one-line hint shown under the picker)
COMMANDS: list[tuple[str, str]] = [
    ("weekly", "Weekly grid calendar with events, one page per span."),
    ("mini", "Compact month-grid mini calendars."),
    ("mini-icon", "Mini calendar using icon glyphs for day numbers."),
    ("candybar", "Vertical year strip — one row per ISO week."),
    ("text-mini", "Plain-text mini calendar (no SVG)."),
    ("timeline", "Horizontal timeline of events and durations."),
    ("pit", "Points-in-Time timeline: single-day events + milestones."),
    ("blockplan", "Swimlane block plan of activities."),
    ("compactplan", "Compressed activities timeline."),
    ("palettesheet", "Preview a named color palette (or all palettes)."),
    ("iconsheet", "Grid preview of DB icons."),
    ("patternsheet", "Grid preview of day-box patterns."),
    ("colorsheet", "Grid preview of named colors."),
    ("fontsheet", "Sample sheet of registered fonts."),
    ("excelheader", "Excel workbook: blockplan-style timeband header."),
    ("excelblockplan", "Excel workbook: timeband header + one row per item."),
    ("exportdata", "Export filtered events/durations as CSV."),
]

# Per-command deterministic output filename + preview mode.
# Modes: "image" (SVG in the Image pane), "text" (file contents in a console),
# "status" (binary output — show the path only).
OUTPUT: dict[str, tuple[str, str]] = {
    "weekly": ("weekly_preview.svg", "image"),
    "mini": ("mini_preview.svg", "image"),
    "mini-icon": ("mini-icon_preview.svg", "image"),
    "candybar": ("candybar_preview.svg", "image"),
    "text-mini": ("text-mini_preview.txt", "text"),
    "timeline": ("timeline_preview.svg", "image"),
    "pit": ("pit_preview.svg", "image"),
    "blockplan": ("blockplan_preview.svg", "image"),
    "compactplan": ("compactplan_preview.svg", "image"),
    "palettesheet": ("palettesheet_preview.svg", "image"),
    "iconsheet": ("iconsheet_preview.svg", "image"),
    "patternsheet": ("patternsheet_preview.svg", "image"),
    "colorsheet": ("colorsheet_preview.svg", "image"),
    "fontsheet": ("fontsheet_preview.svg", "image"),
    "excelheader": ("excelheader_preview.xlsx", "status"),
    "excelblockplan": ("excelblockplan_preview.xlsx", "status"),
    "exportdata": ("exportdata_preview.csv", "text"),
}

# ---- Field spec table: Slint property -> (CLI long flag, emission kind) --------
# kinds:
#   "value"  : text/combo — emit [flag, value] unless value is blank/sentinel
#   "always" : combo that always carries a real value — emit [flag, value]
#   "flag"   : bare store_true — emit [flag] when the bool is set
# Specials handled outside this table: positional dates + palette_name,
# --weekends (index), --database, --today-line tri-state, and -v verbosity.
FIELDS: list[tuple[str, str, str]] = [
    ("country", "--country", "value"),
    # Page & output
    ("theme", "--theme", "value"),
    ("papersize", "--papersize", "always"),
    ("orientation", "--orientation", "always"),
    ("shrink", "--shrink", "flag"),
    ("embed_data", "--embed-data", "flag"),
    # Layout
    ("weekend_days", "--weekend-days", "value"),
    ("margin", "--margin", "flag"),
    ("show_header", "--header", "flag"),
    ("show_footer", "--footer", "flag"),
    ("monthnames", "--monthnames", "flag"),
    # Header / footer text
    ("header_left", "--headerleft", "value"),
    ("header_center", "--headercenter", "value"),
    ("header_right", "--headerright", "value"),
    ("footer_left", "--footerleft", "value"),
    ("footer_center", "--footercenter", "value"),
    ("footer_right", "--footerright", "value"),
    # Watermark
    ("watermark_text", "--watermark-text", "value"),
    ("watermark_rotation", "--watermark-rotation-angle", "value"),
    ("watermark_image", "--watermark-image", "value"),
    # Content filters
    ("empty", "--empty", "flag"),
    ("shade", "--shade", "flag"),
    ("no_events", "--noevents", "flag"),
    ("no_durations", "--nodurations", "flag"),
    ("ignore_complete", "--ignorecomplete", "flag"),
    ("milestones_only", "--milestones", "flag"),
    ("rollups_only", "--rollups", "flag"),
    ("include_notes", "--includenotes", "flag"),
    ("overflow", "--overflow", "flag"),
    ("status", "--status", "value"),
    ("wbs", "--WBS", "value"),
    # Week numbers
    ("weeknumbers", "--weeknumbers", "flag"),
    ("week_number_mode", "--week-number-mode", "value"),
    ("week1_start", "--week1-start", "value"),
    # Mini
    ("mini_columns", "--mini-columns", "value"),
    ("mini_rows", "--mini-rows", "value"),
    ("mini_title_format", "--mini-title-format", "value"),
    ("mini_no_adjacent", "--mini-no-adjacent", "flag"),
    ("mini_grid_lines", "--mini-grid-lines", "flag"),
    ("mini_details", "--mini-details", "flag"),
    ("mini_icon_set", "--mini-icon-set", "value"),
    # Candybar
    ("candybar_row_height", "--candybar-row-height", "value"),
    ("candybar_cell_width", "--candybar-cell-width", "value"),
    ("candybar_max_rows", "--candybar-max-rows-per-page", "value"),
    ("candybar_suppress_weekends", "--candybar-suppress-weekends", "flag"),
    ("candybar_no_week_numbers", "--candybar-no-week-numbers", "flag"),
    ("candybar_month_side", "--candybar-month-side", "value"),
    ("candybar_month_rotation", "--candybar-month-rotation", "value"),
    ("candybar_weekend_fill", "--candybar-weekend-fill", "value"),
    ("candybar_month_shading", "--candybar-month-shading", "flag"),
    # Timeline
    ("today_line_length", "--today-line-length", "value"),
    ("today_line_direction", "--today-line-direction", "value"),
    ("label_fill_opacity", "--label-fill-opacity", "value"),
    # PIT — axis & ticks
    ("direction", "--direction", "value"),
    ("label_side", "--label-side", "value"),
    ("tick_unit", "--tick-unit", "value"),
    ("tick_interval", "--tick-interval", "value"),
    ("tick_label_format", "--tick-label-format", "value"),
    ("tick_length", "--tick-length", "value"),
    ("hide_ticks", "--no-ticks", "flag"),
    ("hide_tick_labels", "--no-tick-labels", "flag"),
    ("date_placement", "--date-placement", "value"),
    # PIT — today line (today_line tri-state handled specially)
    ("today_date", "--today-date", "value"),
    ("today_label", "--today-label", "value"),
    # PIT — markers & icons
    ("event_icon", "--event-icon", "value"),
    ("milestone_icon", "--milestone-icon", "value"),
    ("marker_size", "--marker-size", "value"),
    ("label_icon_size", "--label-icon-size", "value"),
    ("label_icon_gap", "--label-icon-gap", "value"),
    # PIT — leaders
    ("leader_dash", "--leader-dash", "value"),
    ("leader_label_anchor", "--leader-label-anchor", "value"),
    ("leader_length", "--leader-length", "value"),
    ("leader_stub", "--leader-stub", "value"),
    # Fiscal
    ("fiscal", "--fiscal", "value"),
    ("fiscal_year_offset", "--fiscal-year-offset", "value"),
    ("fiscal_colors", "--fiscal-colors", "flag"),
    ("fiscal_show_periods", "--fiscal-show-periods", "flag"),
    ("fiscal_show_quarters", "--fiscal-show-quarters", "flag"),
    # Sheets
    ("sheet_filter", "--filter", "value"),
    ("sheet_color", "--color", "value"),
    ("sheet_paginate", "--paginate", "flag"),
    ("sheet_columns", "--columns", "value"),
    ("sheet_rows", "--rows", "value"),
    ("sheet_sized", "--sized", "value"),
    ("sheet_fullset", "--fullset", "flag"),
    # Logging
    ("quiet", "--quiet", "flag"),
]

# Values that mean "leave at the app default" for text/combo fields.
SENTINELS = {"", "(default)", "(none)"}

# The calendar visualizers force their --outputfile under output/ automatically;
# the sheets/exporters treat --outputfile as a literal path (relative to cwd), so
# we prefix "output/" ourselves to keep every preview file inside output/.
AUTOPREFIX_COMMANDS = {
    "weekly", "mini", "mini-icon", "candybar", "text-mini",
    "timeline", "pit", "blockplan", "compactplan",
}

# All property names we read back from the window (spec fields + specials).
VALUE_PROPS = {p for p, _, _ in FIELDS} | {
    "begin_date", "end_date", "database", "weekends_index",
    "verbose_index", "today_line", "palette_name",
}


def _introspect() -> tuple[dict[str, set[str]], dict[str, list[str]]]:
    """Walk the live argparse parser → per-subcommand long-flag & positional sets."""
    import ecalendar

    parser = ecalendar._create_argument_parser("ecalendar_preview.svg")
    sub_action = next(
        a for a in parser._actions if isinstance(a, argparse._SubParsersAction)
    )
    flags: dict[str, set[str]] = {}
    positionals: dict[str, list[str]] = {}
    for name, subparser in sub_action.choices.items():
        opts: set[str] = set()
        pos: list[str] = []
        for action in subparser._actions:
            if action.option_strings:
                opts.update(s for s in action.option_strings if s.startswith("--"))
            elif action.dest not in ("help",):
                pos.append(action.dest)
        flags[name] = opts
        positionals[name] = pos
    return flags, positionals


FLAGS, POSITIONALS = _introspect()


def build_argv(command: str, values: dict, output_name: str) -> list[str]:
    """Assemble the full ecalendar argv for ``command`` from ``values``.

    Pure and window-free so it can be exercised headlessly. A flag is emitted
    only when it is valid for ``command`` (``flag in FLAGS[command]``) *and* the
    corresponding value is set / non-default. Positionals come first, then
    ``--outputfile``, then the remaining options.
    """
    cmd_flags = FLAGS.get(command, set())
    cmd_pos = POSITIONALS.get(command, [])
    argv: list[str] = [sys.executable, "ecalendar.py", command]

    def get(prop: str, default: str = "") -> str:
        return str(values.get(prop, default))

    # --- positionals -------------------------------------------------------
    if "begin" in cmd_pos:
        argv.append(get("begin_date").strip() or DEFAULT_BEGIN)
        if "end" in cmd_pos:
            argv.append(get("end_date").strip() or DEFAULT_END)
    if "palette_name" in cmd_pos:
        name = get("palette_name").strip()
        if name:
            argv.append(name)

    # --- output file (every subcommand supports --outputfile) --------------
    if "--outputfile" in cmd_flags:
        out_arg = (
            output_name if command in AUTOPREFIX_COMMANDS else f"output/{output_name}"
        )
        argv += ["--outputfile", out_arg]

    # --- database (all except fontsheet) -----------------------------------
    if "--database" in cmd_flags:
        argv += ["--database", get("database").strip() or "calendar.db"]

    # --- weekend style (int index) -----------------------------------------
    if "--weekends" in cmd_flags:
        argv += ["--weekends", str(int(values.get("weekends_index") or 0))]

    # --- generic spec-table fields -----------------------------------------
    for prop, flag, kind in FIELDS:
        if flag not in cmd_flags:
            continue
        val = values.get(prop)
        if kind == "flag":
            if val:
                argv.append(flag)
            continue
        text = "" if val is None else str(val).strip()
        if kind == "always":
            if text:
                argv += [flag, text]
        else:  # "value"
            if text and text not in SENTINELS:
                argv += [flag, text]

    # --- PIT today-line tri-state ------------------------------------------
    if "--today-line" in cmd_flags:
        tl = str(values.get("today_line") or "(default)")
        if tl == "on":
            argv.append("--today-line")
        elif tl == "off":
            argv.append("--no-today-line")

    # --- verbosity ---------------------------------------------------------
    if "--verbose" in cmd_flags:
        n = int(values.get("verbose_index") or 0)
        if n > 0:
            argv.append("-" + "v" * n)

    return argv


def preset_date_range(
    preset: str, today: datetime.date | None = None
) -> tuple[str, str] | None:
    """Resolve a quick-range preset to ``(begin, end)`` YYYYMMDD strings.

    Pure and window-free so it can be exercised headlessly. Returns ``None`` for
    an unknown preset. Presets:
      * ``"year"``    — Jan 1 .. Dec 31 of the current calendar year.
      * ``"quarter"`` — first .. last day of the current calendar quarter.
      * ``"90days"``  — today .. today + 90 days.
    """
    today = today or datetime.date.today()
    if preset == "year":
        begin = datetime.date(today.year, 1, 1)
        end = datetime.date(today.year, 12, 31)
    elif preset == "quarter":
        start_month = ((today.month - 1) // 3) * 3 + 1  # 1, 4, 7, or 10
        begin = datetime.date(today.year, start_month, 1)
        end_month = start_month + 2  # 3, 6, 9, or 12 — always ends the quarter
        # Quarter ends are Mar/Jun/Sep/Dec, so the last day is 31 or 30 (never Feb).
        last_day = 31 if end_month in (3, 12) else 30
        end = datetime.date(today.year, end_month, last_day)
    elif preset == "90days":
        begin = today
        end = today + datetime.timedelta(days=90)
    else:
        return None
    return begin.strftime("%Y%m%d"), end.strftime("%Y%m%d")


def representative_values(command: str) -> dict:
    """Minimal, valid field values for headless coverage of ``command``.

    Mirrors the window's property defaults closely enough to produce a real
    render for each subcommand.
    """
    vals = {
        "begin_date": DEFAULT_BEGIN,
        "end_date": DEFAULT_END,
        "database": "calendar.db",
        "papersize": "Widescreen",
        "orientation": "landscape",
        "weekends_index": 0,
        "verbose_index": 0,
        "theme": "(none)",
        "fiscal": "(none)",
        "today_line": "(default)",
        "palette_name": "",
    }
    return vals


class EcalendarApp:
    """Wires the unified Slint MainWindow to the ecalendar CLI."""

    def __init__(self) -> None:
        import slint

        self._slint = slint
        ui = slint.load_file(str(UI_FILE))
        self.window = ui.MainWindow()
        self.window.generate = self._on_generate
        self.window.command_changed = self._on_command_changed
        self.window.date_preset = self._on_date_preset

        # Cross-thread handoff: worker writes _result as one atomic tuple, the
        # poll Timer (on the loop thread) reads it. Everything the poller needs
        # is bundled in the tuple so there is no second field to race on.
        self._result: tuple | None = None
        self._poll_timer = None

        self._apply_command(0)

    # ----- command selection -------------------------------------------------

    def _on_command_changed(self, index: int) -> None:
        self._apply_command(int(index))

    # ----- quick-range date presets ------------------------------------------

    def _on_date_preset(self, preset: str) -> None:
        result = preset_date_range(str(preset))
        if result is None:
            return
        begin, end = result
        self.window.begin_date = begin
        self.window.end_date = end
        self.window.status_text = f"Set date range: {begin} – {end}"

    def _apply_command(self, index: int) -> None:
        index = max(0, min(index, len(COMMANDS) - 1))
        command, hint = COMMANDS[index]
        flags = FLAGS.get(command, set())
        pos = POSITIONALS.get(command, [])
        w = self.window

        def has(flag: str) -> bool:
            return flag in flags

        content_flags = {
            "--noevents", "--nodurations", "--ignorecomplete", "--milestones",
            "--rollups", "--WBS", "--status", "--empty", "--shade",
            "--includenotes", "--overflow",
        }

        w.command_hint = hint
        w.show_dates = "begin" in pos
        w.show_database = has("--database")
        w.show_theme = has("--theme")
        w.show_page = has("--papersize")
        w.page_has_shrink = has("--shrink")
        w.show_weekends = has("--weekends")
        w.weekends_has_days = has("--weekend-days")
        w.show_layout_page = has("--margin")
        w.layout_has_monthnames = has("--monthnames")
        w.show_headerfooter = has("--headerleft")
        w.show_watermark = has("--watermark-text")
        w.show_country = has("--country")
        w.show_content = bool(flags & content_flags)
        w.cf_empty = has("--empty")
        w.cf_shade = has("--shade")
        w.cf_nodurations = has("--nodurations")
        w.cf_overflow = has("--overflow")
        w.cf_includenotes = has("--includenotes")
        w.show_weeknum = has("--weeknumbers")
        w.show_mini = has("--mini-columns")
        w.mini_has_title_format = has("--mini-title-format")
        w.show_mini_extra = has("--mini-grid-lines")
        w.show_miniicon = has("--mini-icon-set")
        w.show_candybar = has("--candybar-row-height")
        w.show_timeline = has("--today-line-length")
        w.show_pit = has("--direction")
        w.show_fiscal = has("--fiscal")
        w.show_fiscalcolors = has("--fiscal-colors")
        w.show_fiscalbands = has("--fiscal-show-periods")
        w.sheet_has_name = "palette_name" in pos
        w.sheet_has_filter = has("--filter")
        w.sheet_has_color = has("--color")
        w.sheet_has_paginate = has("--paginate")
        w.sheet_has_fullset = has("--fullset")
        w.show_sheet = (
            w.sheet_has_name or w.sheet_has_filter or w.sheet_has_fullset
        )
        w.show_logging = has("--verbose")

        w.preview_mode = OUTPUT[command][1]
        w.status_text = f"Ready — {command}. Set options and click Generate."

    # ----- generate ----------------------------------------------------------

    def _read_values(self) -> dict:
        return {p: getattr(self.window, p) for p in VALUE_PROPS}

    def _on_generate(self) -> None:
        index = int(self.window.command_index)
        command = COMMANDS[index][0]
        output_name, mode = OUTPUT[command]
        values = self._read_values()
        argv = build_argv(command, values, output_name)

        self.window.generating = True
        self.window.status_text = "Generating…  " + " ".join(argv[2:])
        self._result = None

        threading.Thread(
            target=self._worker,
            args=(argv, command, output_name, mode, bool(values.get("sheet_paginate"))),
            daemon=True,
        ).start()

        self._poll_timer = self._slint.Timer()
        self._poll_timer.start(
            self._slint.TimerMode.Repeated, POLL_INTERVAL, self._poll
        )

    def _worker(
        self, argv: list[str], command: str, output_name: str, mode: str, paginate: bool
    ) -> None:
        meta = (command, output_name, mode, paginate)
        try:
            proc = subprocess.run(
                argv,
                cwd=str(ROOT),
                capture_output=True,
                text=True,
                timeout=SUBPROCESS_TIMEOUT_S,
            )
            self._result = (proc.returncode, proc.stdout, proc.stderr, *meta)
        except subprocess.TimeoutExpired:
            self._result = (-1, "", f"timed out after {SUBPROCESS_TIMEOUT_S}s", *meta)
        except Exception as exc:  # noqa: BLE001 - surface any failure in the UI
            self._result = (-1, "", str(exc), *meta)

    def _poll(self) -> None:
        if self._result is None:
            return
        code, out, err, command, output_name, mode, paginate = self._result
        self._result = None
        if self._poll_timer is not None:
            self._poll_timer.stop()
        self.window.generating = False

        if code != 0:
            detail = (err.strip() or out.strip() or f"exit code {code}")
            last_line = detail.splitlines()[-1] if detail else f"exit code {code}"
            self.window.status_text = f"Error: {last_line}"
            return

        path = self._resolve_output(command, output_name, paginate)
        if path is None:
            self.window.status_text = (
                f"Ran OK but no output file found for {command} ({output_name})."
            )
            return

        self._show_preview(command, path, mode)

    # ----- preview routing ---------------------------------------------------

    def _resolve_output(
        self, command: str, output_name: str, paginate: bool
    ) -> Path | None:
        candidates: list[Path] = []
        # The paginating sheets (colorsheet / iconsheet / palettesheet) write
        # <stem>_pNN.svg whenever a run produces more than one page, so preview
        # the first page when the un-suffixed file is absent.
        if paginate:
            stem = output_name[:-4] if output_name.endswith(".svg") else output_name
            candidates += [ROOT / "output" / f"{stem}_p01.svg", ROOT / f"{stem}_p01.svg"]
        candidates += [ROOT / "output" / output_name, ROOT / output_name]
        for c in candidates:
            if c.exists():
                return c
        return None

    def _show_preview(self, command: str, path: Path, mode: str) -> None:
        rel = path.relative_to(ROOT) if path.is_relative_to(ROOT) else path
        if mode == "image":
            self.window.preview_image = self._slint.Image.load_from_path(str(path))
            self.window.preview_mode = "image"
            self.window.status_text = f"OK — rendered {rel}"
        elif mode == "text":
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError as exc:
                text = f"(could not read {rel}: {exc})"
            if len(text) > TEXT_PREVIEW_MAX_CHARS:
                text = text[:TEXT_PREVIEW_MAX_CHARS] + "\n… (truncated)"
            self.window.console_text = text
            self.window.preview_mode = "text"
            self.window.status_text = f"OK — wrote {rel}"
        else:  # status (binary output, e.g. .xlsx)
            self.window.console_text = (
                f"Wrote {rel}\n\n"
                "This is a binary workbook — open it in a spreadsheet application "
                "to view. (No inline preview.)"
            )
            self.window.preview_mode = "status"
            self.window.status_text = f"OK — wrote {rel}"

    def run(self) -> None:
        self.window.run()


def main() -> int:
    if not UI_FILE.exists():
        print(f"UI file not found: {UI_FILE}", file=sys.stderr)
        return 1
    EcalendarApp().run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
