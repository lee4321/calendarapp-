# Slint UI — unified ecalendar front-end

A native desktop front-end over `ecalendar.py`. A single window drives **every
render/export subcommand** of the CLI: pick a visualizer, fill in options, click
**Generate preview**, and see the result natively (Slint renders SVG via resvg;
text/CSV appears in a console; Excel output shows its path).

> **Companion POC:** [README_import.md](README_import.md) covers a separate spike
> over `importers/import_events.py` (`import_app.py` + `import_window.slint`) —
> the same architecture applied to a side-effecting DB importer.

## Run

From the project root:

```bash
uv run python slint_ui/ecalendar_app.py
```

## What it covers

All 17 render/export subcommands, grouped by preview type:

| Preview | Subcommands |
|---------|-------------|
| **SVG image** | `weekly`, `mini`, `mini-icon`, `candybar`, `timeline`, `pit`, `blockplan`, `compactplan`, `palettesheet`, `iconsheet`, `patternsheet`, `colorsheet`, `fontsheet` |
| **Text console** | `text-mini` (plain-text calendar), `exportdata` (CSV) |
| **Status only** | `excelheader`, `excelblockplan` (binary `.xlsx` — path shown, no inline preview) |

The pure listing commands (`themes`, `papersizes`, `patterns`, `icons`,
`colors`, `palettes`, `fonts`) are out of scope — they print reference tables
rather than produce a visualization.

Each Generate writes a deterministic file under `output/`
(`<subcommand>_preview.<ext>`) so the app always knows where the result lands.

### How the form stays in sync with the CLI

The window declares a **superset** of every subcommand's options once (~90% are
shared). Which groups/fields are shown, and which flags are emitted, are both
gated on the **live argparse parser**: at startup the app imports `ecalendar`
(side-effect free — execution is guarded by `if __name__ == "__main__"`) and
walks `ecalendar._create_argument_parser(...)` to learn the exact long-option
set and positional list for each subcommand (`FLAGS` / `POSITIONALS` in
`ecalendar_app.py`). Add a flag to a subcommand in `ecalendar.py` and — as long
as a matching form field exists — the GUI picks it up automatically.

### Conventions for "leave at the app default"

- ComboBoxes whose flag defaults to `None` carry a leading `(default)` / `(none)`
  entry — selecting it omits the flag.
- Text/number fields omit their flag when left blank (placeholder shows the
  effective default).
- The PIT today-line is a 3-way ComboBox — `(default)` omits it, `on` / `off`
  emit `--today-line` / `--no-today-line`.

## How it works

| Piece | Role |
|-------|------|
| `ecalendar_window.slint` | Declarative UI. Form fields are `in-out` properties (read by Python); `preview_image` / `console_text` / `status_text` / `generating` / `preview_mode` and all `show_*` visibility flags are `in` properties (driven by Python). Callbacks: `generate()`, `command-changed(int)`. |
| `ecalendar_app.py` | Loads the `.slint`, introspects the parser (`FLAGS`/`POSITIONALS`), maps form fields → CLI flags (`FIELDS` spec table + `build_argv`), toggles field visibility per subcommand (`_apply_command`), runs `ecalendar.py`, and routes the result into the right preview pane. |
| `verify_argv.py` | Headless coverage check — builds argv for all 17 subcommands via `build_argv` and asserts each runs (exit 0) and produces its output file. Needs no display. |

**`build_argv` is pure and window-free** (`build_argv(command, values, output_name)`),
so `verify_argv.py` and unit tests can exercise the whole emit table without a
live window.

**Subprocess, not in-process:** each Generate runs `ecalendar.py` in a fresh
process (via `sys.executable`, the uv venv interpreter — no `uv run`
re-resolution). This isolates argparse `SystemExit`, global logging config, and
module-level font/size state from the GUI process.

**Threading:** Slint owns the asyncio-integrated event loop on the main thread.
Generation runs on a daemon worker thread; a repeating `slint.Timer` (which
fires *on* the loop thread) polls for the result and updates the preview — so UI
state is never touched from the worker.

## Verify

```bash
uv run python slint_ui/verify_argv.py     # all 17 subcommands -> exit 0 + output file
```

## Known limitations / things to evaluate next

- **SVG fidelity:** Slint uses resvg/usvg. ecalendar emits text as `<path>`
  outlines plus `<pattern>` fills — the most compatible case — but spot-check
  `colorsheet`/`patternsheet` if fidelity matters. A browser renders the same SVG
  perfectly; resvg is very good but not 100% complete.
- **Beta bindings:** `slint==1.17.0b2` (PyPI classifier "3 - Alpha"). APIs are
  mostly stable but may shift.
- **Licensing:** Slint is tri-licensed (GPLv3 / royalty-free / commercial).
  Since this is a MobileLeverage LLC product, GPLv3 likely doesn't fit; the
  royalty-free terms or a commercial license would need review before shipping.
- **New CLI *fields* still need a widget:** introspection auto-tracks which
  *existing* fields apply to each subcommand, but a brand-new option also needs a
  matching form control + a `FIELDS` entry to be settable in the GUI.

## Dependency

`slint` is in `pyproject.toml`. To remove it:

```bash
uv remove slint
```
