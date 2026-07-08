# EventCalendar Textual UI

A terminal front-end (built on [Textual](https://textual.textualize.io)) for the
`ecalendar.py` CLI and the importer family. It is a thin GUI over the existing
argparse layer — it introspects the parser, builds an argv, and shells out via
`uv run`. **No calendar-rendering logic is reimplemented here.**

## Run

```bash
uv run python -m tui                 # uses calendar.db in the project root
uv run python -m tui -db other.db    # point at a different database
```

Then:

- **Home** — three columns: calendar views, reference sheets/listings, and the Import Hub.
- **Enter** a view → the **Builder**: tabs mirror the argparse argument groups
  (Output, Layout, Content Filtering, Fiscal, …). The live command bar shows the
  exact `uv run ecalendar.py …` that will run; **Ctrl+R** runs it and streams output.
- **i** (or the DATA column) → the **Import Hub**: events, special days,
  and content importers, driven by one shared wizard. **Ctrl+D** dry-runs, **Ctrl+R** imports.

## How it works

| Module | Responsibility |
|---|---|
| `spec.py` | Introspects `ecalendar._create_argument_parser()` into `CommandSpec`/`ArgSpec`. **Single source of truth** — new CLI flags appear in the UI automatically. |
| `registry.py` | Populates pickers (`--theme`, `--papersize`, fonts, icons, colors, …) from the same DB/registry the engine uses, so dropdowns never drift. |
| `runner.py` | Builds the argv from collected form values and runs it (`uv run ecalendar.py …`). |
| `importers_spec.py` | Adapters for `import_events.py` (full functionality incl. generator mode), `import_specialdays.py`, and content importers. |
| `widgets/argfield.py` | Maps one `ArgSpec` → the right Textual control (Switch / Select / Input / picker). |
| `widgets/daterange.py` | `begin`/`end` inputs with presets (this year/quarter/month, next 90 days). |
| `screens/` | `home`, `builder`, `import_hub` (+ shared wizard), `result` (worker-threaded runner). |

### Widget mapping

| argparse signature | widget |
|---|---|
| `store_true` | `Switch` |
| `choices=[…]` | `Select` |
| `type=int/float` | numeric `Input` |
| listing-backed (`--theme`, `--papersize`, …) | `Select` from `registry.py` |
| `begin`/`end` | `DateRange` |
| free `str` | `Input` |

## Notes

- Runs are isolated subprocesses via `uv run`, matching how the project runs Python.
- Pickers degrade gracefully to a free-text input if their source is unavailable.
- The UI is non-invasive: it adds the `tui/` package and `textual` as a dependency,
  with no changes to `ecalendar.py` or the importers.
