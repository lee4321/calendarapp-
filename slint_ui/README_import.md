# Slint UI — proof of concept (import_events)

A native desktop front-end over `importers/import_events.py`. It demonstrates the
full round-trip for a *side-effecting* CLI: collect options in a
[Slint](https://slint.dev) form → run the existing importer in a subprocess →
stream its plain-text output into a console pane.

This is the companion to the `pit` POC ([README.md](README.md)). The key
difference: `import_events.py` doesn't render an image — it writes to
`calendar.db` and emits logs — so the right pane is a **read-only text console**
rather than an SVG preview.

> Status: throwaway spike to validate feasibility. Not wired into the main app.

## Run

From the project root:

```bash
uv run python slint_ui/import_app.py
```

Pick a **Mode**, fill in the fields, and click **Run**. The combined
stdout/stderr of the importer appears in the right-hand console.

## Modes

The form is organised around the importer's four mutually-exclusive operations
(everything in `import_events.py --help`):

| Mode | CLI it builds | Notes |
|------|---------------|-------|
| **Import files** | `import_events.py <paths> [--dry-run] [--replace] [--skip-errors]` | Space-separated paths; a directory imports every supported file inside it. **Dry run defaults ON.** |
| **Generate from script** | `import_events.py --generate <script.py> [--start-date/--end-date] [--param K=V …]` | One `KEY=VALUE` per line in the Parameters box. **Dry run defaults ON.** |
| **List history** | `import_events.py --list` | Read-only — safe to run anytime. The POC opens in this mode. |
| **Remove imports** | `import_events.py --remove <pattern> --force` | Pattern: `3`, `1-5`, `1,3,5`, `5-`, `-3`, or `all`. Gated behind a confirmation checkbox (see below). |

**Common options** (all modes): database path, user ID, log level, verbose.

## Safety conventions

- **Dry run defaults ON** for the two writing modes (Import, Generate), so an
  accidental Run validates rather than mutating the database. Un-check it to
  actually write.
- **Remove always passes `--force`.** The GUI and the importer don't share a
  terminal, so the CLI's interactive `[y/N]` prompt can't be answered. The
  subprocess runs with `stdin=DEVNULL` (a stray `input()` would EOF, not hang)
  and the in-app **"I understand this permanently deletes events"** checkbox
  stands in for the prompt — the Run button stays disabled until it's checked.
- Text/number fields omit their flag when left blank (placeholder text shows the
  effective default).

## How it works

| Piece | Role |
|-------|------|
| `import_window.slint` | Declarative UI. Form fields are `in-out` properties (read by Python); `console_text` / `status_text` / `running` are `in` properties (driven by Python). Mode-specific groups render with `if root.mode_index == N`. |
| `import_app.py` | Loads the `.slint`, binds the `run()` / `clear_console()` callbacks, assembles the `import_events.py …` argv for the active mode, runs it, and pipes the merged output into the console. |

**Subprocess, not in-process:** each Run executes `import_events.py` in a fresh
process (via `sys.executable`, the uv venv interpreter — no `uv run`
re-resolution). This isolates argparse `SystemExit`/`sys.exit()`, global logging
config, and the module's `input()` prompts from the GUI process.

**Threading:** identical to the PIT POC. Slint owns the event loop on the main
thread; the subprocess runs on a daemon worker thread; a repeating `slint.Timer`
(which fires *on* the loop thread) polls for the result and updates the console —
so UI state is never touched from the worker.

**Output capture:** `stdout` and `stderr` are merged (`stderr=STDOUT`) so log
lines and any traceback stay in emission order. Success is read from the exit
code (`0` = clean, non-zero = some rows failed or an error occurred).

## Known limitations / things to evaluate next

- **No live progress.** Output is captured and shown when the process exits, not
  streamed line-by-line. A real UI would read the pipe incrementally.
- **No file picker.** Paths are typed. A native open-file/-folder dialog would be
  the obvious next step.
- **Single database, single user.** Matches the CLI defaults; no profile/recents.
- **Form is hand-maintained.** As with the PIT POC, a real UI could introspect
  the argparse parser to auto-generate fields so the GUI tracks new flags.
- Same **beta-bindings** (`slint==1.17.0b2`) and **licensing** (tri-license;
  GPLv3 likely unsuitable for a MobileLeverage product) caveats as the PIT POC —
  see [README.md](README.md).

## Dependency

`slint` is already in `pyproject.toml` (added for the PIT spike). No new
dependency is introduced by this POC.
