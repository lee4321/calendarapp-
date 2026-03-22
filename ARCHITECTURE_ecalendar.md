# Architecture: `ecalendar.py`

`ecalendar.py` is the single CLI entry point for the EventCalendar SVG generator.
It owns argument parsing, configuration assembly, database wiring, and dispatch to
every subcommand — both the read-only inspection commands (themes, fonts, colors, …)
and the SVG/Excel visualizer commands (weekly, mini, blockplan, excelheader, …).

---

## Module-Level Structure

```
ecalendar.py
├── Exceptions          CalendarError / DatabaseError / ConfigError
├── replace_template_vars
├── CLI argument layer
│   ├── _parse_atfile_lines
│   ├── _expand_sanitized_atfiles
│   ├── _to_output_dir_path
│   └── _create_argument_parser
├── Configuration assembly
│   ├── _configure_logging
│   ├── _apply_args_to_config
│   ├── _apply_text_options
│   └── _reapply_post_theme_cli_overrides
├── Input validation
│   ├── _validate_database
│   └── _open_calendar_db
├── Subcommand help
│   └── _print_subcommand_help
├── Palette resolution
│   ├── _resolve_single_palette_ref
│   └── _resolve_palette_overrides
├── SVG preview generators
│   ├── _generate_palette_svg
│   ├── _generate_colorsheet_svg
│   ├── _render_font_fullset            ← helper for _generate_fontsheet_svg
│   ├── _generate_fontsheet_svg
│   └── _generate_iconsheet_svg
└── run                                  ← top-level entry point
    └── _hsv_sort_key (nested)
```

---

## Call Graph

```
__main__
  └── run()
        ├── _create_argument_parser()
        ├── _expand_sanitized_atfiles()
        │     └── _parse_atfile_lines()
        ├── _configure_logging()
        │
        ├── [help]       _print_subcommand_help()
        │
        ├── [fontsheet]  _generate_fontsheet_svg()
        │                     └── _render_font_fullset()
        │
        ├── [iconsheet]  _generate_iconsheet_svg()
        ├── [colorsheet] _generate_colorsheet_svg()
        │                     └── _hsv_sort_key (nested)
        ├── [palette]    _generate_palette_svg()
        │
        ├── [papersizes/patterns/icons/colors/palettes]
        │                     └── _open_calendar_db()
        │                               └── _validate_database()
        │
        ├── [excelheader]
        │     ├── _open_calendar_db()
        │     └── _resolve_palette_overrides()
        │               └── _resolve_single_palette_ref()
        │
        └── [weekly / mini / mini-icon / text-mini / timeline / blockplan]
              ├── _open_calendar_db()
              ├── _apply_args_to_config()
              ├── _apply_text_options()
              │     └── replace_template_vars()
              ├── _resolve_palette_overrides()
              │     └── _resolve_single_palette_ref()
              ├── _reapply_post_theme_cli_overrides()
              ├── _to_output_dir_path()
              └── VisualizerFactory.create(view_type).generate(config, db)
```

---

## Exception Hierarchy

| Class | Parent | Purpose |
|---|---|---|
| `CalendarError` | `Exception` | Base for all domain exceptions; catch this to handle any ecalendar error |
| `DatabaseError` | `CalendarError` | Raised when the SQLite database cannot be opened or is missing |
| `ConfigError` | `CalendarError` | Raised for invalid CLI arguments or configuration values |

Exit-code convention in `run()`:

| Code | Meaning |
|---|---|
| `0` | Success |
| `1` | Invalid date / date range (`InvalidDateError`) |
| `2` | Database or configuration error (`DatabaseError`, `ConfigError`) |
| `3` | Unexpected / unhandled exception |

---

## Function Reference

### `replace_template_vars(config, text) → str`

**Purpose:** Expands bracket-style template variables embedded in user-supplied
header, footer, and watermark strings.

**Supported tokens:**

| Token | Expands to |
|---|---|
| `[now]` | Current datetime (`YYYY-MM-DD HH:mm`) |
| `[date]` | Current date (`YYYY-MM-DD`) |
| `[startdate]` | `config.adjustedstart` (first day of the rendered calendar) |
| `[enddate]` | `config.adjustedend` (last day of the rendered calendar) |
| `[events]` | `config.events` (database path description) |

**Called by:** `_apply_text_options()` — which is itself called from `run()` after
`calc_calendar_range()` has populated the adjusted-start/end dates.

**Why it exists:** Keeps text-substitution logic in one place so the six
header/footer slots and the watermark field all behave identically.

---

### `_parse_atfile_lines(path) → list[str]`

**Purpose:** Reads a `@file` argument file and returns clean argument tokens,
stripping blank lines and comments.

**Comment stripping rules:**
- Lines whose first two characters are `# ` are dropped entirely.
- The portion of a line after the first `# ` is dropped (trailing comment).
- A bare `#` not followed by a space is preserved (e.g., color codes like `#FF0000`).

**Called by:** `_expand_sanitized_atfiles()`.

**Why it exists:** argparse's built-in `fromfile_prefix_chars` does not strip
comments; this function provides a sanitised alternative.

---

### `_expand_sanitized_atfiles(tokens, *, depth=0) → list[str]`

**Purpose:** Recursively expands `@filename` tokens in the raw CLI token list
by reading and parsing each referenced file via `_parse_atfile_lines()`.

**Recursion guard:** Raises `ConfigError` if nesting depth exceeds 10, preventing
infinite loops from circular `@file` chains.

**Called by:** `run()` immediately after `sys.argv` is read, before `argparse.parse_args()`.

**Calls:** `_parse_atfile_lines()` (for each `@file` token), itself recursively.

**Why it exists:** Supports storing reusable argument presets in plain-text files
with comments, which the user can compose via nesting (e.g., a `base.args` file
referenced from `theme.args`).

---

### `_to_output_dir_path(filename) → str`

**Purpose:** Strips any directory component from a filename and places it under
the local `output/` directory.

**Example:** `_to_output_dir_path("../secret/calendar.svg")` → `"output/calendar.svg"`

**Called by:** `run()` when setting `config.outputfile` for calendar visualizer commands.

**Why it exists:** Prevents path-traversal: all generated output is confined to
the `output/` subdirectory regardless of what the user supplies to `--outputfile`.

---

### `_create_argument_parser(default_output) → ArgumentParser`

**Purpose:** Builds the full `argparse.ArgumentParser` for the CLI, including
all subcommands and their option groups.

**Subcommands registered:**

| Category | Subcommands |
|---|---|
| Calendar visualizers | `weekly`, `mini`, `mini-icon`, `text-mini`, `timeline`, `blockplan` |
| Inspection / listing | `themes`, `fonts`, `fontsheet`, `papersizes`, `patterns`, `icons`, `iconsheet`, `colors`, `colorsheet`, `palettes`, `palette` |
| Output utilities | `excelheader` |
| Help | `help` |

**Argument groups (per visualizer subcommand):**
- Database Options (`--database`, `--country`)
- Output Options (`--outputfile`, `--papersize`, `--orientation`, `--shrink`)
- Layout Options (`--weekends`, `--header`, `--footer`, `--margin`, `--overflow`)
- Header/Footer text (`--headerleft`, `--headercenter`, `--headerright`, …)
- Watermark Options (`--watermark`, `--watermark-rotation-angle`, `--imagemark`)
- Content Filtering (`--noevents`, `--nodurations`, `--ignorecomplete`, `--milestones`, `--rollups`, `--WBS`)
- Mini Calendar Options (`--mini-columns`, `--mini-rows`, `--mini-no-adjacent`, …)
- Timeline Options (`--today-line-length`, `--today-line-direction`, `--label-fill-opacity`, `--duration-fill-opacity`)
- Fiscal Options (`--fiscal`, `--fiscal-colors`, `--fiscal-year-offset`)
- Week Number Options (`--weeknumbers`, `--week-number-mode`, `--week1-start`)
- Theme (`--theme`)
- Logging (`--verbose`, `--quiet`)

**Called by:** `run()` at startup, before parsing.

**Why it exists:** Centralising parser construction keeps `run()` focused on
dispatch logic and makes the argument surface easy to survey and extend.

---

### `_configure_logging(verbose, quiet)`

**Purpose:** Sets the root logging level and format based on the `--verbose` /
`--quiet` flags.

| Flag / level | Effective log level | Format |
|---|---|---|
| `--quiet` | `ERROR` | `LEVEL: message` |
| default (0) | `WARNING` | `LEVEL: message` |
| `-v` (1) | `INFO` | `LEVEL: message` |
| `-vv` (2) | `INFO` | `LEVEL: module: message` |
| `-vvv` (3+) | `DEBUG` | `LEVEL: module: message` |

**Called by:** `run()` immediately after argument parsing.

**Why it exists:** A single call immediately after `parse_args()` ensures all
subsequent module-level loggers (renderers, layout engine, db_access, …) inherit
the correct level for the entire run.

---

### `_apply_args_to_config(args, config, paper_sizes)`

**Purpose:** Transfers parsed CLI argument values into the `CalendarConfig`
dataclass, performing any necessary validation or transformation along the way.

**Sections handled:**
1. **Database source** — sets `config.events` description string.
2. **Weekend style** — writes `config.weekend_style`.
3. **Month display** — resolves `--monthnames` / `--monthnumbers` mutual exclusivity.
4. **Week numbers** — sets `config.include_week_numbers`.
5. **Layout toggles** — header, footer, margin, overflow, shrink flags.
6. **Paper size & orientation** — case-insensitive lookup with clear error on unknown name; sets `config.pageX/pageY`.
7. **Display options** — events, durations, milestones, rollups, WBS, complete filtering, today-shading, country.
8. **Mini calendar options** — guarded with `is not None` so omitting a flag never clobbers a theme-set default.
9. **Timeline options** — today-line geometry, opacity overrides.
10. **Fiscal calendar** — type string and per-period colour flag.
11. **Week number mode** — ISO vs. custom-anchor.

**Called by:** `run()` for all calendar-visualizer subcommands, after the database
and paper-size list have been loaded.

**Calls:** `getattr()`, `setattr()`, raises `ConfigError` on unknown paper size.

**Why it exists:** Separating argument-to-config mapping from `run()` keeps the
entry-point readable and makes it easy to unit-test config wiring in isolation.

---

### `_apply_text_options(args, config)`

**Purpose:** Maps the six header/footer text arguments and watermark fields from
`args` into `config`, applying `replace_template_vars()` to each non-empty value.

**Fields mapped:**

| CLI arg | Config attribute |
|---|---|
| `--headerleft` | `config.header_left_text` |
| `--headercenter` | `config.header_center_text` |
| `--headerright` | `config.header_right_text` |
| `--footerleft` | `config.footer_left_text` |
| `--footercenter` | `config.footer_center_text` |
| `--footerright` | `config.footer_right_text` |
| `--watermark` | `config.watermark` |
| `--watermark-rotation-angle` | `config.watermark_rotation_angle` |
| `--imagemark` | `config.imagemark` |

**Called by:** `run()` after `calc_calendar_range()` (so `[startdate]`/`[enddate]`
tokens are already resolved in the config when template substitution runs).

**Calls:** `replace_template_vars()` for each non-empty text field.

**Why it exists:** Keeps text-option wiring together in one auditable function,
separate from the larger `_apply_args_to_config()` which handles structural options.

---

### `_reapply_post_theme_cli_overrides(args, config)`

**Purpose:** Re-asserts explicit CLI flags that the theme application may have
silently overwritten.

**Currently handles:**
- `--mini-no-adjacent` → forces `config.mini_show_adjacent = False` even if the
  theme sets it `True`.

**Called by:** `run()` immediately after the second `theme_engine.apply(config)` call
(the call that follows `setfontsizes()`).

**Why it exists:** The theme engine is applied *twice* — once before `setfontsizes()`
to expose size rules, and once after to lock in theme font sizes. This double-apply
means that explicit CLI negation flags can be clobbered the second time. This
function re-asserts them after the final apply.

---

### `_validate_database(db_path)`

**Purpose:** Confirms that the path supplied for `--database` refers to an
existing regular file before attempting to open it.

**Raises:**
- `DatabaseError("Database file not found: …")` — path does not exist.
- `DatabaseError("Database path is not a file: …")` — path exists but is a directory.

**Called by:** `_open_calendar_db()`.

**Why it exists:** Provides a clear, early error message rather than letting
`sqlite3` raise a cryptic `OperationalError`.

---

### `_open_calendar_db(db_path) → CalendarDB`

**Purpose:** Validates the database path and returns an open `CalendarDB` instance
in a single call.

**Called by:** `run()` for every subcommand that requires database access
(`papersizes`, `patterns`, `icons`, `iconsheet`, `colors`, `colorsheet`, `palettes`,
`palette`, `excelheader`, and all calendar-visualizer commands).

**Calls:** `_validate_database()`, `CalendarDB()`.

**Why it exists:** Eliminates the repeated two-step `_validate_database() + CalendarDB()`
pattern that would otherwise appear in every database-using dispatch branch.

---

### `_print_subcommand_help(subcommand, parser)`

**Purpose:** Prints the argparse `--help` text for the requested subcommand,
followed by a supplementary "VALID CONFIGURABLE VALUES" section listing the
enumerated options that are too dynamic to encode in the static help strings
(themes, paper sizes, fonts, icons, patterns, etc.).

**Sections printed (conditionally by subcommand):**
- Weekend styles — all calendar views
- Paper sizes — all calendar views
- Orientation — all calendar views
- Themes — all calendar views
- SVG day-box patterns — `weekly` only
- Fiscal calendar types — `weekly` only
- Week number modes — `weekly` only
- Mini calendar options — `mini`, `mini-icon`, `text-mini`
- Today-line direction — `timeline` only
- Icons guidance — all calendar views
- Template variables — all calendar views
- Available fonts / colors guidance — all subcommands

**Called by:** `run()` when `args.command == "help"`.

**Calls:** `ThemeEngine.list_available_themes()`, `WEEKEND_STYLES`.

**Why it exists:** Complements argparse's static help with runtime data from the
theme engine and config registries that cannot be embedded in `add_argument()` calls.

---

### `_resolve_single_palette_ref(value, db) → str`

**Purpose:** Resolves a single `"palette:NAME:INDEX"` colour reference string to
a concrete hex colour fetched from the database.

**INDEX formats supported:**
- `int` — zero-based index; wraps modulo palette length (cycling).
- `float` in `[0.0, 1.0]` — proportional position through the palette (0.0 = first
  colour, 1.0 = last colour).

**Returns:** The resolved hex string on success, or the original `value` string
unchanged on any error (palette not found, bad index), logging a warning.

**Called by:** `_resolve_palette_overrides()` for every string config field that
starts with `"palette:"`.

**Why it exists:** Allows theme YAML files to reference database palettes for
individual colour fields (e.g., `accent_color: "palette:Blues:3"`) without
requiring the theme to hard-code hex values.

---

### `_resolve_palette_overrides(config, db)`

**Purpose:** Bulk-resolves all palette name references in `CalendarConfig` to
actual colour values fetched from the database.

**Two phases:**
1. **Named bulk palettes** — five sentinel fields set by the theme engine are checked
   and populated with sampled/full palette lists:

   | Sentinel field | Target field | Sample size |
   |---|---|---|
   | `config.theme_month_palette` | `config.theme_monthcolors` | 12 (one per month) |
   | `config.theme_fiscal_palette` | `config.theme_fiscalperiodcolors` | 13 (one per period) |
   | `config.theme_group_palette` | `config.group_colors` | full palette |
   | `config.theme_timeline_palette` | `config.timeline_top_colors` / `timeline_bottom_colors` | full palette |
   | `config.theme_blockplan_palette_name` | `config.blockplan_palette` | full palette |

2. **Inline `palette:NAME:INDEX` references** — iterates all `dataclasses.fields(config)`,
   resolving any `str` value that starts with `"palette:"` via `_resolve_single_palette_ref()`.

**Called by:** `run()` for both the `excelheader` and all calendar-visualizer paths,
after the theme has been applied.

**Calls:** `db.sample_palette_n()`, `db.get_palette()`, `_resolve_single_palette_ref()`.

**Why it exists:** Decouples palette name resolution from theme loading — the theme
engine writes sentinel names, and this function fetches actual colours at render time
so themes remain database-independent.

---

### `_generate_palette_svg(name, colors, output_path)`

**Purpose:** Writes a standalone SVG file previewing a named colour palette as a
grid of colour boxes, each labelled with its hex value.

**Layout:** Up to 10 columns; rows added as needed. Title shows palette name and
colour count.

**Called by:** `run()` when `args.command == "palette"`.

**Why it exists:** Provides a quick visual reference for palette contents so users
can choose palettes for their themes without needing to render a full calendar.

---

### `_generate_colorsheet_svg(colors, output_path, title)`

**Purpose:** Writes an SVG grid of named-color swatches from the database `colors`
table, sorted by HSV hue before this function is called.

**Layout:** Up to 8 columns. Each swatch shows its hex value (white or dark text
chosen by luminance) centred on the swatch, and the EN colour name below it.

**Called by:** `run()` when `args.command == "colorsheet"`, after the caller has
already sorted `colors` by HSV via the `_hsv_sort_key` nested function.

**Why it exists:** Lets users browse the full named-colour library in a scannable
visual format grouped by hue rather than alphabetically.

---

### `_render_font_fullset(font_path, x_start, content_width, font_size, color) → (list[str], float)`

**Purpose:** Renders every codepoint mapped in a font as SVG `<path>` elements,
wrapping to a new line when the current line reaches `content_width`.

**Returns:** A list of raw SVG `<path>` element strings and the total rendered
height in user units (so the caller can size its `<svg>` container).

**Coordinate space:** Paths are in a local space starting at `(x_start, 0)`;
callers must translate via `<g transform="translate(0,{y_offset})">`.

**Called by:** `_generate_fontsheet_svg()` when `fullset=True`.

**Calls:** `get_font_codepoints()`, `get_glyph()`, `get_font_metrics()` from
`renderers.glyph_cache`.

**Why it exists:** Extracted as a standalone function so its pre-render height
can be measured in a first pass before the enclosing SVG document dimensions
are committed (the two-pass approach in `_generate_fontsheet_svg`).

---

### `_generate_fontsheet_svg(font_registry, output_path, color, title, fullset)`

**Purpose:** Writes an SVG sample sheet for every font in the registry.

**Two rendering modes:**

| Mode | Layout | Content |
|---|---|---|
| `fullset=False` (default) | Two-column grid, fixed entry height | Three fixed sample rows per font (lowercase / uppercase / digits+symbols) rendered as glyph paths |
| `fullset=True` | Single column, variable entry height | Every mapped codepoint in order, wrapping at margin |

**Two-pass strategy (fullset mode only):** First pass calls `_render_font_fullset()`
for every font to measure each entry's height; second pass positions and emits them.

**Called by:** `run()` when `args.command == "fontsheet"`.

**Calls:** `text_to_svg_group()` (default mode), `_render_font_fullset()` (fullset mode).

**Why it exists:** Provides visual font browsing within the ecalendar ecosystem,
important because fonts are rendered as glyph paths — there is no browser or OS
font substitution to fall back on.

---

### `_generate_iconsheet_svg(icons, output_path, color, title)`

**Purpose:** Writes an SVG grid of icon previews from the database `icon` table,
each rendered at 24×24 with its name label below.

**Colour handling — two icon styles:**
- **Lucide-style** (uses `currentColor`): `currentColor` is replaced with `color`;
  the root `fill` attribute from the original SVG is preserved.
- **Klee-style** (fill-based, no `currentColor`): `fill="{color}"` is added to the
  container `<svg>` so paths inherit it.

**Label staggering:** Odd-column labels are offset 12 px lower than even-column
labels to reduce visual overlap on narrow icons.

**Called by:** `run()` when `args.command == "iconsheet"`.

**Why it exists:** Lets users quickly identify icon names for use in event `Icon`
fields and theme rules, without needing to open the database directly.

---

### `run(argv) → int`  *(main entry point)*

**Purpose:** Top-level orchestrator. Parses arguments, dispatches to the correct
subcommand handler, assembles `CalendarConfig`, and drives the visualizer system
to produce SVG or Excel output.

**Execution flow:**

```
1. Generate timestamped default output filename
2. Build the argument parser (_create_argument_parser)
3. Expand @file tokens (_expand_sanitized_atfiles)
4. Parse arguments (argparse)
5. Configure logging (_configure_logging)
6. Dispatch pure-listing commands:
     help → _print_subcommand_help
     themes, fonts → direct print
     fontsheet → _generate_fontsheet_svg
     papersizes, patterns, icons, colors, palettes → DB query + print
     iconsheet → _generate_iconsheet_svg
     colorsheet → _generate_colorsheet_svg  (HSV-sorted)
     palette → _generate_palette_svg
7. Require begin/end dates for date-range commands
8. Dispatch excelheader (early, before the full config pipeline):
     open DB → create config → calc range → load holidays
     → apply theme → resolve palettes → generate_excel_header
9. For calendar visualizers (weekly / mini / mini-icon / text-mini /
   timeline / blockplan):
     a. Open DB; load paper sizes
     b. _apply_args_to_config
     c. calc_calendar_range  (adjusts for complete weeks / weekend style)
     d. db.load_python_holidays  (injects live government holidays)
     e. build fiscal lookup  (if --fiscal specified)
     f. Load & pre-apply theme  (first pass: exposes size rules)
     g. _apply_text_options  (template vars now have resolved dates)
     h. setfontsizes  (auto-scale fonts to page/paper dimensions)
     i. Re-apply theme  (second pass: theme font sizes win over auto-scaled)
     j. _reapply_post_theme_cli_overrides
     k. _resolve_palette_overrides  (DB palette names → hex colours)
     l. WeeklyCalendarLayout.calculate  (weekly only — pre-compute coords)
     m. _to_output_dir_path  (confine output to output/ directory)
     n. VisualizerFactory.create(view_type).generate(config, db)
10. Return exit code (0/1/2/3)
```

**Error handling:**

| Exception | Exit code |
|---|---|
| `InvalidDateError` | 1 |
| `DatabaseError`, `ConfigError` | 2 |
| Any other `Exception` | 3 (with full traceback logged) |

**Nested helper:** `_hsv_sort_key(r)` — converts a colour dict's `red`/`green`/`blue`
fields to an HSV tuple used as the sort key for `colorsheet` output.  Defined inside
`run()` alongside `colorsys.rgb_to_hsv` so it can be imported lazily only when the
`colorsheet` subcommand is invoked.

**Why it exists:** Concentrating all dispatch, config assembly, and error handling
here keeps each called helper focused on a single responsibility, while giving a
single place to trace the full execution path.

---

## Key External Dependencies (called from ecalendar.py)

| Symbol | Source module | Role |
|---|---|---|
| `CalendarConfig` / `create_calendar_config` | `config.config` | Configuration dataclass and factory |
| `setfontsizes` | `config.config` | Auto-scale font sizes to paper dimensions |
| `FONT_REGISTRY` | `config.config` | Mapping of font name → TTF path |
| `WEEKEND_STYLES` | `config.config` | Weekend-style integer → metadata dict |
| `CalendarDB` | `shared.db_access` | SQLite database access layer |
| `InvalidDateError` / `calc_calendar_range` | `shared.date_utils` | Date-range calculation and validation |
| `VisualizerFactory` | `visualizers.factory` | Creates the correct visualizer for each subcommand |
| `WeeklyCalendarLayout` | `visualizers.weekly.layout` | Pre-computes page coordinates for weekly view |
| `ThemeEngine` | `config.theme_engine` | Loads and applies YAML themes to config |
| `generate_excel_header` | `visualizers.excelheader` | Produces the Excel workbook for `excelheader` |
| `create_fiscal_calendar` / `build_fiscal_lookup` | `shared.fiscal_calendars` | Fiscal calendar computation |
| `text_to_svg_group` | `renderers.glyph_cache` | Converts text to SVG glyph path group |
| `get_font_codepoints` / `get_glyph` / `get_font_metrics` | `renderers.glyph_cache` | Per-glyph path extraction |
| `WeeklyCalendarRenderer._parse_svg_tile_size` | `visualizers.weekly.renderer` | Reads tile dimensions from pattern SVG (used in `patterns` listing) |

---

## Design Conventions

- **Single module, multiple subcommands.** All dispatch lives in `run()` as an
  explicit `if args.command == …` chain rather than a registry dict.  This trades
  conciseness for traceability: every code path is directly readable without
  indirection.

- **Early-exit dispatch for read-only commands.** Listing commands (`themes`,
  `fonts`, `colors`, …) return before the expensive config-assembly pipeline.
  `excelheader` also exits early because it does not need the full paper-size /
  weekly-layout machinery.

- **Config-first, render-last.** The entire `CalendarConfig` is assembled and
  validated before any rendering code is imported or called.  Lazy imports inside
  dispatch branches keep module load time low for simple listing commands.

- **Two-pass theme application.** The theme is applied once before `setfontsizes()`
  (to expose base size rules that influence scaling) and again after (so explicit
  theme font-size overrides win). `_reapply_post_theme_cli_overrides()` follows
  the second apply to restore CLI negation flags.

- **Output confinement.** `_to_output_dir_path()` strips any directory component
  from user-supplied filenames, ensuring all generated files land in `output/`.

- **Palette resolution as a post-theme step.** `_resolve_palette_overrides()` runs
  after the theme is fully applied so all sentinel palette-name fields have been
  written by the theme engine before they are fetched from the database.
