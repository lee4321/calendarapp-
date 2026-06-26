# Slint UI — proof of concept (PIT only)

A minimal native desktop front-end over `ecalendar.py`, scoped to the **`pit`
(Points-in-Time)** visualizer. It demonstrates the full round-trip: collect
options in a [Slint](https://slint.dev) form → run the existing CLI → preview the
resulting SVG natively (Slint renders SVG via resvg).

> Status: throwaway spike to validate feasibility. Not wired into the main app.

## Run

From the project root:

```bash
uv run python slint_ui/app.py
```

Set a date range (defaults to `20260101`–`20260630`), pick options, and click
**Generate preview**. The SVG is written to `output/pit_preview.svg` and shown
in the right-hand pane.

## What it covers

The **full `pit` parameter set** (everything in `ecalendar.py pit --help`),
grouped in the form:

- **Data** — start/end dates, database, country
- **Page & output** — theme, paper size, orientation, weekend style, weekend
  days, margins, month names, shrink-to-bbox, embed data, overflow page
- **Header / footer** — toggles plus all six text slots
- **Watermark** — text, rotation, image
- **Content filters** — empty, shade, no-events, no-durations,
  ignore-complete, milestones-only, rollups-only, include-notes, status,
  WBS
- **PIT axis & ticks** — direction, label side, tick unit/interval/format/
  length, hide ticks, hide tick labels, date placement
- **PIT today line** — tri-state on/off, today-date override, today label
- **PIT markers & icons** — event/milestone icon, marker size, label icon
  size/gap
- **PIT leaders** — dash array, label anchor, length, stub
- **Fiscal** — overlay type, fiscal-year offset
- **Logging** — verbosity level, quiet

The form maps 1:1 to CLI flags in `app.py::_build_argv`.

### Conventions for "leave at the app default"

- ComboBoxes whose flag defaults to `None` carry a leading `(default)` /
  `(none)` entry — selecting it omits the flag entirely.
- Text/number fields omit their flag when left blank (placeholder text shows
  the effective default).
- The today line is a 3-way ComboBox — `(default)` omits it, `on`/`off` emit
  `--today-line` / `--no-today-line`.

> Note: a few shared flags — `--monthnames` and `--overflow` — are accepted by
> the `pit` parser but ignored by the PIT visualizer (it warns on stderr). They
> are included here for parity with `pit --help`.

## How it works

| Piece | Role |
|-------|------|
| `pit_window.slint` | Declarative UI. Form fields are `in-out` properties (read by Python); `preview_image` / `status_text` / `generating` are `in` properties (driven by Python). |
| `app.py` | Loads the `.slint`, binds the `generate()` callback, assembles the `ecalendar.py pit …` argv, runs it, and loads the SVG into the preview. |

**Subprocess, not in-process:** each Generate runs `ecalendar.py` in a fresh
process (via `sys.executable`, the uv venv interpreter — no `uv run`
re-resolution). This isolates argparse `SystemExit`, global logging config, and
any module-level font/size state from the GUI process.

**Threading:** Slint owns the asyncio-integrated event loop on the main thread.
Generation runs on a daemon worker thread; a repeating `slint.Timer` (which
fires *on* the loop thread) polls for the result and updates the preview — so UI
state is never touched from the worker.

## Known limitations / things to evaluate next

- **SVG fidelity:** Slint uses resvg/usvg. ecalendar emits text as `<path>`
  outlines plus `<pattern>` fills — the most compatible case — but spot-check
  `colorsheet`/`patternsheet` output if fidelity matters. A browser renders the
  same SVG perfectly; resvg is very good but not 100% complete.
- **Beta bindings:** `slint==1.17.0b2` (PyPI classifier "3 - Alpha"). APIs are
  mostly stable but may shift.
- **Licensing:** Slint is tri-licensed (GPLv3 / royalty-free / commercial).
  Since this is a MobileLeverage LLC product, GPLv3 likely doesn't fit; the
  royalty-free terms or a commercial license would need review before shipping.
- **Form is hand-maintained:** for a real UI, consider introspecting the
  argparse parser to auto-generate fields so the GUI tracks new CLI flags.

## Dependency

`slint` was added to `pyproject.toml` for this spike. To remove it:

```bash
uv remove slint
```
