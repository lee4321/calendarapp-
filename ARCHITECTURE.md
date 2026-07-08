# EventCalendar architecture — start here

SVG calendar generator: SQLite events + YAML themes → drawsvg SVG (and two
XLSX exports). Python 3.13, run with `uv run python …`.

**The documentation set lives in [docs/architecture/](docs/architecture/README.md)**,
in reading order:

| Doc | What it answers |
|---|---|
| [overview](docs/architecture/overview.md) | How the pieces fit, in one diagram |
| [render-pipeline](docs/architecture/render-pipeline.md) | What happens on one `weekly` run |
| [theme-resolution](docs/architecture/theme-resolution.md) | How YAML becomes styles; the precedence chain |
| [data-model](docs/architecture/data-model.md) | calendar.db tables → `Event` → consumers |
| [visualizers](docs/architecture/visualizers.md) | One section per visualizer |
| [importers](docs/architecture/importers.md) | The CSV/XLSX import framework |
| [ARCHITECTURE_ecalendar.md](ARCHITECTURE_ecalendar.md) | CLI-layer deep dive (parser, atfiles, dispatch) |

Working practices, layering rules, commenting standards, and the
vocabulary glossary: [CONTRIBUTING.md](CONTRIBUTING.md).
User-facing documentation: [USER_GUIDE.md](USER_GUIDE.md).
Completed 2026-07 maintainability effort: [CONSOLIDATION_PLAN.md](docs/archive/CONSOLIDATION_PLAN.md).
