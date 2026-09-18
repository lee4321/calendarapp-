# Retired front-ends: the Textual TUI and the Slint UI

**Retired:** 2026-09-18 · **Last commit carrying them:** tag `pre-ui-retirement`

EventCalendar once shipped two alternative front-ends beside the CLI. Both were
removed so the project carries one interface, and so `textual` and `slint` (plus
six transitive packages) leave the dependency set. Neither front-end held any
rendering logic, so their removal changed no output — the refcorpus was
byte-identical across the retirement commit.

This file is the record a rebuild would need. The code itself is preserved by
the tag; what rots is everything *around* it, so the contracts each front-end
leaned on are written down below with the place they lived.

## Restoring

```bash
git checkout pre-ui-retirement -- tui slint_ui
```

Then re-add the dependency the package needs (`textual` for `tui/`, `slint` for
`slint_ui/`) with `uv add`, and re-read §"Contracts a rebuild depends on" —
several of these have moved before and will move again.

## What they were

### `tui/` — Textual terminal UI (17 files, 1,422 lines)

Entry point `uv run python -m tui`, optionally `-db other.db`.

A thin terminal front end over the argparse layer: introspect the parser, build
an argv, shell out via `uv run`. Three screens.

| Module | Responsibility |
|---|---|
| `spec.py` | Introspected `_create_argument_parser()` into `CommandSpec`/`ArgSpec` — the single source of truth, so new CLI flags appeared automatically |
| `registry.py` | Populated pickers (`--theme`, `--papersize`, fonts, icons, colors) from the same DB/registry the engine uses |
| `runner.py` | Built the argv from form values and ran it |
| `importers_spec.py` | Adapters for `import_events.py` (including generator mode), `import_specialdays.py` and the content importers |
| `widgets/argfield.py` | Mapped one `ArgSpec` → a Textual control (`store_true`→Switch, `choices=`→Select, numeric→Input, listing-backed→registry Select) |
| `widgets/daterange.py` | `begin`/`end` inputs with presets |
| `screens/` | `home`, `builder`, `import_hub`, `result` |

Home offered three columns (calendar views / reference sheets / the Import Hub);
the Builder's tabs mirrored the argparse argument groups with a live command bar;
the Import Hub ran one shared wizard per data type, dry-run by default.

### `slint_ui/` — native desktop UI (7 files, 2,163 lines)

Entry point `uv run python slint_ui/ecalendar_app.py`, plus a separate throwaway
spike `import_app.py` over `importers/import_events.py`.

One window drove every render/export subcommand: pick a visualizer, fill the
form, Generate, and see the SVG rendered natively (Slint renders SVG through
resvg), text/CSV in a console pane, or a path for `.xlsx`. The pure listing
commands (`themes`, `papersizes`, …) were out of scope.

| Piece | Role |
|---|---|
| `ecalendar_window.slint` | Declarative UI. Form fields as `in-out` properties; preview/console/status/visibility as `in` properties; `generate()` and `command-changed(int)` callbacks |
| `ecalendar_app.py` | Loaded the `.slint`, introspected the parser into `FLAGS`/`POSITIONALS`, mapped fields → flags via a `FIELDS` table and `build_argv`, gated per-subcommand visibility in `_apply_command`, ran the CLI, routed output to the right pane |
| `verify_argv.py` | Headless coverage check — built argv for every subcommand and asserted exit 0 plus an output file, with no display needed |

Two design decisions worth carrying forward:

- **`build_argv(command, values, output_name)` was pure and window-free**, which
  is what made `verify_argv.py` possible. Keep that split in any rebuild.
- **Subprocess, not in-process.** Each run invoked `ecalendar.py` in a fresh
  process via `sys.executable`, isolating argparse's `SystemExit`, global logging
  config and module-level font/size state from the GUI process. Slint owned the
  event loop on the main thread; generation ran on a daemon worker and a
  repeating `slint.Timer` (which fires *on* the loop thread) polled for the
  result, so UI state was never touched from the worker.

## Contracts a rebuild depends on

These are the load-bearing assumptions. Each is given with where it lived at
retirement — verify every one before trusting old code.

1. **The parser factory.** `_create_argument_parser(default_output)` is defined
   in `cli/args.py:348` and re-exported from `ecalendar.py`. Both front-ends
   walked its subparsers to learn each subcommand's long-option and positional
   set. `ecalendar.py` once held it directly; the `cli/` split moved it.
2. **Registration order is the contract.** The parser keeps registration order;
   `_SortedSubcommandsHelpFormatter` (`cli/args.py:190`) sorts only the *printed*
   help. Anything walking the parser sees registration order.
3. **`import ecalendar` is side-effect free** — execution is guarded by
   `if __name__ == "__main__"`. This is what makes startup introspection safe;
   if that ever stops being true, the introspection approach breaks.
4. **Picker sources** (`tui/registry.py`): `ThemeEngine.list_available_themes()`,
   `config.config.FONT_REGISTRY`, and `shared.db_access.CalendarDB` for paper
   sizes, patterns, icons, colors and palettes. Every lookup degraded to a plain
   text input on failure, which is why a missing DB never broke the UI.
5. **Importer flag surfaces** — `tui/importers_spec.py` shelled out to
   `importers/import_events.py`, `import_specialdays.py` and the content
   importers. `docs/architecture/importers.md` describes the framework those
   share.
6. **Output paths.** The Slint preview resolved `output/<stem>/<stem>.svg`. This
   already changed once — the run-folder commit `d02e6b92` gave every run its own
   folder, and `1bd9a4dd` retired the companion `_details`/`_key`/`_overflow`
   pages the UI knew about. Re-derive the layout; do not trust the old code.

**The best live reference** for a rebuild is
`tools/generate_option_catalog.py`: it walks the same parser, it is covered by
`tests/test_option_catalog.py`, and it is kept current because the docs depend
on it. Start from how it reads the parser, not from the retired code.

## Constraints to revisit before rebuilding

- **Slint licensing.** Slint is tri-licensed (GPLv3 / royalty-free / commercial).
  GPLv3 likely does not fit a MobileLeverage LLC product; the royalty-free terms
  or a commercial license would need review before shipping a Slint front end.
- **Beta bindings.** The retired UI pinned `slint==1.17.0b2`, whose PyPI
  classifier was "3 - Alpha". Check API stability against whatever is current.
- **resvg fidelity.** Slint renders SVG via resvg/usvg. ecalendar emits text as
  `<path>` outlines plus `<pattern>` fills — the most compatible case — but
  `colorsheet` / `patternsheet` are worth spot-checking. A browser renders the
  same SVG exactly.
- **Introspection covers flags, not widgets.** Walking the parser auto-tracks
  which *existing* fields apply to each subcommand, but a brand-new option still
  needs a matching form control before it is settable.

## Related records

- `docs/archive/textualUI.html` — the original TUI design write-up.
- `docs/archive/CONSOLIDATION_PLAN.md` — lists both packages in the 2026-07
  inventory as "alternative front-ends".
- `.claude/plans/retire-ui-frontends.md` — the retirement plan this file came from.
