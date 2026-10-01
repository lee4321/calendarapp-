# EventCalendar User Guide

> **For developers:** architecture docs live in
> [ARCHITECTURE.md](ARCHITECTURE.md) (reading order, diagrams) and
> [CONTRIBUTING.md](CONTRIBUTING.md) (working practices, vocabulary).
> The examples in this guide are executable — verify them with
> `uv run python tools/check_user_guide.py`.

This guide is generated from the current codebase (`ecalendar.py`, `cli/args.py`, `config/theme_schema.py`) and reflects the exact implemented CLI/theme surface.

## Commands

| Command | What it does |
|---|---|
| `weekly` | Generate a weekly calendar SVG. |
| `mini` | Generate a mini calendar SVG. |
| `mini-icon` | Generate a mini calendar SVG using icon images for day numbers instead of numerals. |
| `candybar` | Generate a vertical year-strip calendar SVG: one row per ISO week, a week-number column, day-of-month cells, and a merged month-name box spanning each month's rows. |
| `text-mini` | Generate a text mini calendar. |
| `timeline` | Generate a timeline SVG. |
| `pit` | Generate a Points-in-Time SVG (clean axis + marker-per-event + bezier leaders). |
| `blockplan` | Generate a blockplan SVG. |
| `gantt` | Generate a Gantt chart SVG: task table on the left, timescale on the right, with duration bars, percent-complete lines, milestones, rollup brackets and dependency arrows. |
| `compactplan` | Generate a compressed activities timeline SVG showing durations as colored lines above/below a central axis, grouped by resource group. |
| `excelblockplan` | Generate an `.xlsx` workbook with blockplan-style timeband header rows plus one row per event/duration in the range (with style-rule decoration and holiday overlays). Pass `--empty` for a blank workbook with only the header rows, ready to use as a planning template. |
| `themes` | List available themes. |
| `papersizes` | List available paper sizes from DB. |
| `patterns` | List available SVG day-box patterns from DB. |
| `icons` | List available icons from DB. |
| `colors` | List available named colors from DB (includes RGB channels). |
| `palettes` | List available color palettes from DB. |
| `palettesheet` | Generate an SVG swatch preview for one named palette. |
| `iconsheet` | Generate an SVG grid preview of icons. |
| `patternsheet` | Generate an SVG grid preview of day-box patterns. |
| `colorsheet` | Generate an SVG grid preview of named colors. |
| `fonts` | List registered fonts. |
| `fontsheet` | Generate an SVG sample sheet for all registered fonts. |
| `exportdata` | Export filtered events/durations as a CSV compatible with `importers/import_events.py`. |
| `help` | Show valid configurable values for a subcommand. |

## Run Output

Every visualization run writes its own folder under `output/`, named after
the output file:

```
output/gantt202609141530/
  gantt202609141530.svg        the chart (continuation pages: _p2.svg, _p3.svg, ...)
  gantt202609141530.md         the details document
  gantt202609141530.csv        the events the run included
  icons/                       one SVG per icon or mark the chart drew
```

`--outputfile chart.svg` writes `output/chart/chart.svg` and the files beside
it; any directory in the name is discarded. Re-running into the same folder
first removes what a run writes there (the chart, its pages, the document,
the CSV and `icons/`) and leaves anything else alone. `text-mini` writes its
`.txt`, document and CSV the same way. The utilities (`excelblockplan`,
`exportdata` and the sheets) still write single files directly under
`output/`.

### The details document

`<stem>.md` is a Markdown document describing what the chart shows. It
replaced the companion SVG pages -- the gantt details page, the weekly
overflow page, the mini family's details page and the compactplan key --
and lists everything they did:

| Section | Holds |
|---|---|
| Events | Every event the run was given, one row each, in the columns `details.markdown.columns` names: any `events` table column, plus what the chart assigned it (see below) |
| Color Key | Every color the chart handed out: a swatch, the color, what it was assigned to, where it came from (a style rule, a color rule, a group palette, the event's own color ...) and how many events carry it |
| Icons & Symbols | Every file in `icons/`: the icon or mark, its name and color, the role it plays (milestone, duration start, continuation, holiday, overflow ...) and what it means |
| Exceptions | Everything the chart could not show faithfully: items that did not fit their day, bars clipped at the range edge, events moved off a hidden weekend, dependencies drawn on another page, labels with no room, lanes past the page, items no swimlane took, icons a day cell had no corner for, names shortened to fit |
| Holidays & Special Days | The holidays and company special days on the days the chart shows, one row per name, government holidays with their country code |

Icons are image links into `icons/`, so the document shows its icons in
GitHub, VS Code, Obsidian and most other Markdown viewers.

#### Render-derived event fields

Besides every `events` column (`name`, `start_date`, `end_date`, `wbs`,
`resource_group`, `notes`, `source_id`, `custom1` ...), an Events column may
name what the chart did with the event:

| Field | Value |
|---|---|
| `marker` | The event's key mark: its bar or flag in its color (or a swatch of its assigned color), then every icon drawn for it |
| `icons` | Every icon and mark drawn for the event, in draw order |
| `icon` | The first icon drawn for it |
| `event_icon` | The `events.icon` value, as text |
| `assigned_color` | The color it was drawn in, as a swatch and its name |
| `color_source` | Where that color came from |
| `category` | `event`, `milestone` or `duration` |
| `lane` | Its swimlane (blockplan) |
| `drawn` | `yes`, `partial` (clipped, or partly overflowed) or `no` |
| `page` | The chart page its row is on (gantt) |
| `ref` / `link_ref` | Cross-page dependency reference icons (gantt) |
| `exceptions` | How many exception rows concern it |
| `continues_before` / `continues_after` | Whether it was clipped at the range edge |
| `color_rank` | For `sort`: the color assignment order |

#### The event CSV

`<stem>.csv` has one row per event the run was given, in the Events table's
order. By default its columns are the `exportdata` set, so it re-imports
through `importers/import_events.py`, followed by the render columns
`assigned_color`, `color_source`, `icons` (`;`-separated names), `category`,
`lane`, `drawn`, `page` and `exceptions`; the importer ignores columns it
does not know. `details.csv.columns` may instead list columns in the same
schema as the document's.

#### Icon files

Each distinct icon and color the chart drew is written once, as
`icons/<icon>--<color>.svg`, recolored exactly as the chart painted it.
Every file is the same square size (`details.icons.size`, default 16), so
icons line up in the document's tables. Marks drawn as geometry -- a bar, a
color swatch, a milestone pennant, a rollup bracket -- get `mark-*` files.

#### Command-line switches

| Flag | Effect |
|---|---|
| `--details-md` / `--no-details-md` | Write / skip the details document |
| `--icons` / `--no-icons` | Write / skip the icon files (the document then names icons instead of showing them) |
| `--csv` / `--no-csv` | Write / skip the event CSV |

All three are on by default, and the flags beat a theme's `enable:` either
way. See [Run details](#run-details) for the theme keys.

## Common Workflows

```bash
# Weekly calendar for a date range
PYTHONPATH=. uv run python ecalendar.py weekly 20260101 20260131 -th default -of weekly.svg

# Mini calendar with week numbers (output/mini/: mini.svg, mini.md, mini.csv, icons/)
PYTHONPATH=. uv run python ecalendar.py mini 20260101 20261231 --weeknumbers -of mini.svg

# Mini-icon calendar, 4 columns, landscape (icon set comes from the theme: mini_calendar.icon_set)
PYTHONPATH=. uv run python ecalendar.py mini-icon 20260101 20261231 --mini-columns 4 -o landscape -of mini_icon.svg

# Candybar vertical year-strip for a full year
PYTHONPATH=. uv run python ecalendar.py candybar 20260101 20261231 -th default -of candybar.svg

# Candybar (the theme's candybar.suppress_weekends drops the weekend columns; the month row's text.rotation turns the month names)
PYTHONPATH=. uv run python ecalendar.py candybar 20260101 20261231 -of candybar.svg

# Timeline (the today line is styled by the theme: lines.today, today)
PYTHONPATH=. uv run python ecalendar.py timeline 20260101 20261231 -of timeline.svg

# Blockplan view
PYTHONPATH=. uv run python ecalendar.py blockplan 20260101 20261231 -th default -of blockplan.svg

# Gantt chart: task table + bars + dependency arrows, plus its details document
PYTHONPATH=. uv run python ecalendar.py gantt 20260101 20260630 -th default -of chart.svg

# Compact activities plan
PYTHONPATH=. uv run python ecalendar.py compactplan 20260309 20260424 -th default -of compact.svg

# Excel workbook with blockplan-style data rows (events + durations, sorted by start date)
PYTHONPATH=. uv run python ecalendar.py excelblockplan 20260101 20260630 -th default -of plan.xlsx

# Empty Excel planning template: the same header rows, no event rows (--empty)
PYTHONPATH=. uv run python ecalendar.py excelblockplan 20260101 20260630 -th default --empty -of template.xlsx

# Export filtered events to CSV
PYTHONPATH=. uv run python ecalendar.py exportdata 20260101 20261231 --milestones -o milestones.csv

# Weekly view including draft and on-hold events (dimmed) alongside active work
PYTHONPATH=. uv run python ecalendar.py weekly 20260101 20260131 --status active,draft,on-hold -of weekly.svg

# Inspect available theme resources
PYTHONPATH=. uv run python ecalendar.py themes
PYTHONPATH=. uv run python ecalendar.py papersizes
PYTHONPATH=. uv run python ecalendar.py palettes
PYTHONPATH=. uv run python ecalendar.py patterns
PYTHONPATH=. uv run python ecalendar.py fonts

# Generate sample-sheet previews
PYTHONPATH=. uv run python ecalendar.py palettesheet Set2 -of output/set2.svg
PYTHONPATH=. uv run python ecalendar.py patternsheet -f wiggle -of output/wiggle.svg
PYTHONPATH=. uv run python ecalendar.py iconsheet -f arrow -of output/arrows.svg
PYTHONPATH=. uv run python ecalendar.py colorsheet -of output/colors.svg
PYTHONPATH=. uv run python ecalendar.py fontsheet -f roboto -of output/roboto.svg

# Same sheets split into printable pages (output/colors_p01.svg, output/colors_p02.svg, ...)
PYTHONPATH=. uv run python ecalendar.py colorsheet -f blue --paginate -cols 6 -rows 8 -of output/colors.svg
PYTHONPATH=. uv run python ecalendar.py palettesheet Set2 --paginate -cols 4 -rows 2 -of output/set2.svg
```

## Command-Line Option Catalog (All Options)

Generated from the argument parser by `tools/generate_option_catalog.py`.
Run that script after changing `cli/args.py` rather than editing this
table by hand.

| Option(s) | Metavar | Commands | Description | Defaults/Choices |
|---|---|---|---|---|
| `--WBS` |  | `blockplan`, `candybar`, `compactplan`, `excelblockplan`, `exportdata`, `gantt`, `mini`, `mini-icon`, `pit`, `text-mini`, `timeline`, `weekly` | WBS filter expression. Comma-separated tokens; '!' excludes. Segments are dot-separated. '*' matches a segment, '**' matches any remaining segments (implicit if omitted). |  |
| `--candybar-cell-width` | `POINTS` | `candybar` | Fixed day-cell width in points (default: 0 = square, width == row height) |  |
| `--candybar-max-rows-per-page` | `N` | `candybar` | Split into side-by-side strips after N week rows (0 = single strip) |  |
| `--candybar-row-height` | `POINTS` | `candybar` | Fixed week-row height in points (default: 0 = auto-fit to page) |  |
| `--color`, `-c` | `COLOR` | `fontsheet`, `iconsheet`, `patternsheet` | Glyph color (default: #222222) (`iconsheet`: Stroke color for icons (default: #333333)) (`patternsheet`: Fill color for pattern tiles (default: #333333)) | `fontsheet`: default `#222222`; `iconsheet`, `patternsheet`: default `#333333` |
| `--columns`, `-cols` | `N` | `colorsheet`, `fontsheet`, `iconsheet`, `palettesheet` | Swatch columns per page (requires --paginate; default: 8) (`fontsheet`: Font columns per page (requires --paginate; default: 2). Ignored with --fullset, which is always a single column.) (`iconsheet`: Icon columns per page (requires --paginate; default: 8)) (`palettesheet`: Swatch columns per page (requires --paginate; default: 12)) |  |
| `--country`, `-cc` | `CODE` | `blockplan`, `candybar`, `compactplan`, `excelblockplan`, `exportdata`, `gantt`, `mini`, `mini-icon`, `pit`, `text-mini`, `timeline`, `weekly` | ISO 3166-1 alpha-2 country code(s) for government holidays. Accepts a single code (e.g. US) or a comma-separated list (e.g. US,CA,GB) to include holidays from multiple countries. If omitted, US and CA holidays are loaded by default. |  |
| `--csv` |  | `blockplan`, `candybar`, `compactplan`, `gantt`, `mini`, `mini-icon`, `pit`, `text-mini`, `timeline`, `weekly` | Write the event CSV into the run folder (on by default) | default `False` |
| `--database`, `-db` | `PATH` | `blockplan`, `candybar`, `colors`, `colorsheet`, `compactplan`, `excelblockplan`, `exportdata`, `gantt`, `glyphs`, `icons`, `iconsheet`, `mini`, `mini-icon`, `palettes`, `palettesheet`, `papersizes`, `patterns`, `patternsheet`, `pit`, `text-mini`, `timeline`, `weekly` | Path to SQLite database file (default: calendar.db) | default `calendar.db` |
| `--details-md` |  | `blockplan`, `candybar`, `compactplan`, `gantt`, `mini`, `mini-icon`, `pit`, `text-mini`, `timeline`, `weekly` | Write the Markdown details document into the run folder (on by default) | default `False` |
| `--direction` |  | `pit`, `timeline` | Axis direction (default: horizontal). Note: --orientation remains the page-orientation flag (portrait/landscape). (`timeline`: Axis direction (default: horizontal). Vertical runs the axis top-to-bottom with labels to the right (primary) / left (secondary). Note: --orientation remains the page-orientation flag (portrait/landscape).) | choices `horizontal, vertical` |
| `--durations`, `-du` |  | `candybar`, `mini`, `mini-icon`, `text-mini` | Include multi-day durations (excluded by default) | default `False` |
| `--embed-data` |  | `blockplan`, `candybar`, `compactplan`, `gantt`, `mini`, `mini-icon`, `pit`, `timeline`, `weekly` | Embed source event data (CSV) inside SVG metadata | default `False` |
| `--empty`, `-e` |  | `blockplan`, `candybar`, `compactplan`, `excelblockplan`, `gantt`, `mini`, `mini-icon`, `pit`, `text-mini`, `timeline`, `weekly` | Create blank calendar (no events) (`excelblockplan`: Create blank workbook (no events)) | default `False` |
| `--filter`, `-f` | `TEXT` | `colorsheet`, `fontsheet`, `iconsheet`, `patternsheet` | Filter colors by name substring (case-insensitive) (`fontsheet`: Filter fonts by name substring (case-insensitive)) (`iconsheet`: Filter icons by name substring (case-insensitive)) (`patternsheet`: Filter patterns by name substring (case-insensitive)) |  |
| `--fiscal` | `TYPE` | `blockplan`, `candybar`, `compactplan`, `gantt`, `mini`, `mini-icon`, `pit`, `text-mini`, `timeline`, `weekly` | Enable fiscal calendar overlay (nrf-454, nrf-445, nrf-544, 13-period). weekly/mini: period labels (period colors come from the theme). text-mini: period start markers. timeline/pit: fiscal rows of the theme's timescale. blockplan/compactplan/gantt: NRF-aware fiscal_quarter and fiscal_period rows. | choices `nrf-454, nrf-445, nrf-544, 13-period` |
| `--fiscal-year-offset` | `N` | `blockplan`, `candybar`, `compactplan`, `gantt`, `mini`, `mini-icon`, `pit`, `text-mini`, `timeline`, `weekly` | Offset added to the fiscal period start year to produce the displayed fiscal year number. 0 = start year (e.g. FY starting Feb 2026 → FY2026), 1 = start year + 1 (e.g. FY starting Oct 2025 → FY2026, US federal default), -1 = start year − 1. Default: auto (0 for NRF). |  |
| `--footer`, `-ft` |  | `blockplan`, `candybar`, `compactplan`, `gantt`, `mini`, `mini-icon`, `pit`, `timeline`, `weekly` | Include page footer | default `False` |
| `--footercenter`, `-fc` |  | `blockplan`, `candybar`, `compactplan`, `gantt`, `mini`, `mini-icon`, `pit`, `timeline`, `weekly` | Center footer text |  |
| `--footerleft`, `-fl` |  | `blockplan`, `candybar`, `compactplan`, `gantt`, `mini`, `mini-icon`, `pit`, `timeline`, `weekly` | Left footer text |  |
| `--footerright`, `-fr` |  | `blockplan`, `candybar`, `compactplan`, `gantt`, `mini`, `mini-icon`, `pit`, `timeline`, `weekly` | Right footer text |  |
| `--fullset` |  | `fontsheet` | Show every glyph in the font instead of the three fixed sample rows | default `False` |
| `--header`, `-ht` |  | `blockplan`, `candybar`, `compactplan`, `gantt`, `mini`, `mini-icon`, `pit`, `timeline`, `weekly` | Include page header | default `False` |
| `--headercenter`, `-hc` |  | `blockplan`, `candybar`, `compactplan`, `gantt`, `mini`, `mini-icon`, `pit`, `timeline`, `weekly` | Center header text |  |
| `--headerleft`, `-hl` |  | `blockplan`, `candybar`, `compactplan`, `gantt`, `mini`, `mini-icon`, `pit`, `timeline`, `weekly` | Left header text |  |
| `--headerright`, `-hr` |  | `blockplan`, `candybar`, `compactplan`, `gantt`, `mini`, `mini-icon`, `pit`, `timeline`, `weekly` | Right header text |  |
| `--icons` |  | `blockplan`, `candybar`, `compactplan`, `gantt`, `mini`, `mini-icon`, `pit`, `text-mini`, `timeline`, `weekly` | Write one SVG per icon the chart drew into the run folder (on by default) | default `False` |
| `--includenotes`, `-notes` |  | `blockplan`, `compactplan`, `gantt`, `pit`, `timeline`, `weekly` | Show notes with event names | default `False` |
| `--margin`, `-m` |  | `blockplan`, `candybar`, `compactplan`, `gantt`, `mini`, `mini-icon`, `pit`, `timeline`, `weekly` | Add page margins | default `False` |
| `--milestones`, `-mo` |  | `blockplan`, `candybar`, `compactplan`, `excelblockplan`, `exportdata`, `gantt`, `mini`, `mini-icon`, `pit`, `text-mini`, `timeline`, `weekly` | Show only milestones | default `False` |
| `--mini-columns`, `-mc` | `N` | `mini`, `mini-icon`, `text-mini` | Number of months per row in mini calendar (default: 3) |  |
| `--mini-rows`, `-mr` | `N` | `mini`, `mini-icon`, `text-mini` | Number of rows of months (0 = auto from date range) |  |
| `--monthnames`, `-mn` |  | `weekly` | Show month names on calendar | default `False` |
| `--no-csv` |  | `blockplan`, `candybar`, `compactplan`, `gantt`, `mini`, `mini-icon`, `pit`, `text-mini`, `timeline`, `weekly` | Do not write the event CSV | default `False` |
| `--no-details-md` |  | `blockplan`, `candybar`, `compactplan`, `gantt`, `mini`, `mini-icon`, `pit`, `text-mini`, `timeline`, `weekly` | Do not write the Markdown details document | default `False` |
| `--no-icons` |  | `blockplan`, `candybar`, `compactplan`, `gantt`, `mini`, `mini-icon`, `pit`, `text-mini`, `timeline`, `weekly` | Do not write one SVG per icon the chart drew | default `False` |
| `--nodurations`, `-nd` |  | `blockplan`, `compactplan`, `excelblockplan`, `exportdata`, `gantt`, `timeline`, `weekly` | Exclude multi-day durations | default `False` |
| `--noevents`, `-ne` |  | `blockplan`, `candybar`, `compactplan`, `excelblockplan`, `exportdata`, `gantt`, `mini`, `mini-icon`, `pit`, `text-mini`, `timeline`, `weekly` | Exclude single-day events | default `False` |
| `--orientation`, `-o` |  | `blockplan`, `candybar`, `compactplan`, `gantt`, `mini`, `mini-icon`, `pit`, `timeline`, `weekly` | Page orientation (default: landscape) | default `landscape`; choices `portrait, landscape` |
| `--outputfile`, `-of` (`-o` for `exportdata`) | `PATH` | `blockplan`, `candybar`, `colorsheet`, `compactplan`, `excelblockplan`, `exportdata`, `fontsheet`, `gantt`, `iconsheet`, `mini`, `mini-icon`, `palettesheet`, `patternsheet`, `pit`, `text-mini`, `timeline`, `weekly` | Output filename (always written under output/) (`colorsheet`: Output SVG path (default: output/colorsheet.svg). With --paginate, a '_pNN' suffix is appended per page (e.g. colorsheet_p01.svg).) (`excelblockplan`: Output .xlsx file name (always written under output/; default: output/ExcelBlockplan.xlsx)) (`exportdata`: Output CSV file name (always written under output/; default: output/exportdata_YYYYMMDD.csv)) (`fontsheet`: Output file name and path (default: output/fontsheet.svg). With --paginate, a '_pNN' suffix is appended per page (e.g. fontsheet_p01.svg).) (`iconsheet`: Output file name and path (default: output/iconsheet.svg). With --paginate, a '_pNN' suffix is appended per page (e.g. iconsheet_p01.svg).) (`palettesheet`: Output file path (default: output/palettesheet.svg, or output/<NAME>.svg when a palette is named). With --paginate, a '_pNN' suffix is appended per page (e.g. palettesheet_p01.svg).) (`patternsheet`: Output file name and path (default: output/patternsheet.svg)) | `blockplan`, `candybar`, `compactplan`, `gantt`, `mini`, `mini-icon`, `pit`, `text-mini`, `timeline`, `weekly`: default `ecalendar.svg` |
| `--paginate` |  | `colorsheet`, `fontsheet`, `iconsheet`, `palettesheet` | Split the colors across multiple printable SVG pages instead of one large sheet. Enables --columns/--rows/--sized; without it a single SVG containing every color is produced (the default). (`fontsheet`: Split the fonts across multiple printable SVG pages instead of one large sheet. Enables --columns/--rows/--sized; without it a single SVG containing every font is produced (the default).) (`iconsheet`: Split the icons across multiple printable SVG pages instead of one large sheet. Enables --columns/--rows; without it a single SVG containing every icon is produced (the default).) (`palettesheet`: Split the swatches across multiple printable SVG pages instead of one large sheet. Enables --columns/--rows/--sized; without it a single SVG containing every palette is produced (the default). When every palette is rendered, each page is packed with as many complete palettes as fit; a palette is never split across pages.) | default `False` |
| `--papersize`, `-ps` | `SIZE` | `blockplan`, `candybar`, `compactplan`, `gantt`, `mini`, `mini-icon`, `pit`, `timeline`, `weekly` | Paper size (default: Widescreen). | default `Widescreen` |
| `--quiet`, `-q` |  | `blockplan`, `candybar`, `colors`, `colorsheet`, `compactplan`, `excelblockplan`, `exportdata`, `fonts`, `fontsheet`, `gantt`, `glyphs`, `help`, `icons`, `iconsheet`, `mini`, `mini-icon`, `palettes`, `palettesheet`, `papersizes`, `patterns`, `patternsheet`, `pit`, `text-mini`, `themes`, `timeline`, `weekly` | Suppress all output except errors | default `False` |
| `--rows`, `-rows` | `N` | `colorsheet`, `fontsheet`, `iconsheet`, `palettesheet` | Swatch rows per page (requires --paginate; default: 10) (`fontsheet`: Font rows per page (requires --paginate; default: 10)) (`iconsheet`: Icon rows per page (requires --paginate; default: 10)) (`palettesheet`: Swatch rows per page — with no palette name this is the page's height budget for packing whole palettes (requires --paginate; default: 10)) |  |
| `--shrink` |  | `blockplan`, `candybar`, `gantt`, `mini`, `mini-icon`, `pit`, `timeline`, `weekly` | Shrink SVG width/height/viewBox to the bounding box of rendered content, removing blank page whitespace. | default `False` |
| `--sized` | `N` | `colorsheet`, `fontsheet`, `iconsheet`, `palettesheet` | Swatch box width in points (the height scales with it to keep the sheet's aspect ratio; the label/spacing gaps are unchanged). Requires --paginate; default: 110. (`fontsheet`: Sample text size in points; entry heights follow it. Requires --paginate; default: 16.) (`iconsheet`: Icon cell size in points (one integer sets both width and height; the label/spacing gaps are unchanged). Requires --paginate; default: 24.) (`palettesheet`: Swatch box size in points (one integer sets both width and height; the label/spacing gaps are unchanged). Requires --paginate; default: 80.) |  |
| `--status` | `LIST` | `blockplan`, `candybar`, `compactplan`, `excelblockplan`, `exportdata`, `gantt`, `mini`, `mini-icon`, `pit`, `text-mini`, `timeline`, `weekly` | Comma-separated event statuses to include (active, draft, cancelled, archived, on-hold). Use 'all' for no filter. Default: active. |  |
| `--theme`, `-th` | `THEME` | `blockplan`, `candybar`, `compactplan`, `excelblockplan`, `gantt`, `mini`, `mini-icon`, `pit`, `text-mini`, `timeline`, `weekly` | Theme name or path to a version-3.0 .yaml theme file (default: 'default'; see `themes`) (`excelblockplan`: Theme name or path to .yaml theme file) |  |
| `--tile-size`, `-ts` | `PTS` | `patternsheet` | Largest tile dimension after auto-normalization, in points (default: 18); 0 previews tiles at native size | default `18.0` |
| `--trace-style` |  | `blockplan`, `candybar`, `colors`, `colorsheet`, `compactplan`, `excelblockplan`, `exportdata`, `fonts`, `fontsheet`, `gantt`, `glyphs`, `help`, `icons`, `iconsheet`, `mini`, `mini-icon`, `palettes`, `palettesheet`, `papersizes`, `patterns`, `patternsheet`, `pit`, `text-mini`, `themes`, `timeline`, `weekly` | Trace how theme style_rules and decoration change each day, event and duration (which rules applied, what they overrode, which were skipped and why) to stderr | default `False` |
| `--verbose`, `-v` |  | `blockplan`, `candybar`, `colors`, `colorsheet`, `compactplan`, `excelblockplan`, `exportdata`, `fonts`, `fontsheet`, `gantt`, `glyphs`, `help`, `icons`, `iconsheet`, `mini`, `mini-icon`, `palettes`, `palettesheet`, `papersizes`, `patterns`, `patternsheet`, `pit`, `text-mini`, `themes`, `timeline`, `weekly` | Increase verbosity (-v, -vv, -vvv) | default `0` |
| `--week-number-mode`, `-wnm` |  | `mini`, `mini-icon`, `text-mini`, `weekly` | Week number mode (iso or custom) | default `iso`; choices `iso, custom` |
| `--week1-start` | `YYYYMMDD` | `mini`, `mini-icon`, `text-mini`, `weekly` | Anchor date for week 1 (YYYYMMDD). Implies --weeknumbers and custom mode. |  |
| `--weekend-days` | `DAYS` | `blockplan`, `compactplan`, `excelblockplan`, `gantt`, `timeline`, `weekly` | Comma-separated ISO weekday list (0=Mon..6=Sun) marking non-working days for holiday/weekend classification. Defaults to Sat/Sun when weekends are shown. (`excelblockplan`: Comma-separated ISO weekday list (0=Mon..6=Sun) marking non-working days for holiday/weekend classification.) |  |
| `--weekends`, `-we` |  | `blockplan`, `candybar`, `compactplan`, `excelblockplan`, `gantt`, `mini`, `mini-icon`, `pit`, `text-mini`, `timeline`, `weekly` | Weekend style: 0=work week only, 1=full week Sunday start, 2=half weekends Sunday start, 3=full week Monday start, 4=half weekends Monday start (`excelblockplan`: Weekend style: 0=work week only (default), 1=full week Sunday start, 2=half weekends Sunday start, 3=full week Monday start, 4=half weekends Monday start) | default `0`; choices `0, 1, 2, 3, 4` |
| `--weeknumbers`, `-wn` |  | `mini`, `mini-icon`, `text-mini`, `weekly` | Show week numbers | default `False` |

## Positional Arguments by Command

### `blockplan`

| Name | Required | Description | Choices |
|---|---|---|---|
| `START_DATE` | no | Start date in YYYYMMDD format (will be adjusted to full week) |  |
| `END_DATE` | no | End date in YYYYMMDD format (will be adjusted to full week) |  |

### `compactplan`

| Name | Required | Description | Choices |
|---|---|---|---|
| `START_DATE` | no | Start date in YYYYMMDD format (will be adjusted to full week) |  |
| `END_DATE` | no | End date in YYYYMMDD format (will be adjusted to full week) |  |

### `excelblockplan`

| Name | Required | Description | Choices |
|---|---|---|---|
| `START_DATE` | no | Start date in YYYYMMDD format (will be adjusted to full week) |  |
| `END_DATE` | no | End date in YYYYMMDD format (will be adjusted to full week) |  |

Generates an Excel workbook (`.xlsx`) with blockplan-style timeband header
rows, a column-header row, and one data row per event/duration sourced from
the events table. Columns A–AS carry all 45 events-table field names in
schema order (`id`, `status`, `priority`, `wbs`, `rollup`, `milestone`,
`percent_complete`, `name`, `effort`, `duration`, `start_date`, `end_date`,
`earliest_start_date`, `latest_start_date`, `earliest_end_date`,
`latest_end_date`, `predecessors`, `resource_names`, `resource_group`,
`notes`, `icon`, `color`, `tags`, then the schedule data elements:
`source_id`, `critical`, `start_time`, `end_time`, `duration_text`,
`effort_text`, `actual_start_date`, `actual_start_time`, `actual_end_date`,
`actual_end_time`, `deadline`, `start_variance`, `finish_variance`,
`fixed_cost`, `cost`, `percent_work_complete`, `successors`,
`custom1`–`custom5`), column AT holds the continuation marker, and one column
per visible day starts at column AU. Timeband rows place their heading label
in the last label column with segment values starting at the first date
column.

**Empty spreadsheet:** pass `--empty` to generate an empty spreadsheet — the
timeband and column-header rows (with holiday shading and vertical lines) but
no event or duration rows — ready to fill in as a project-planning template.

The command-line surface mirrors `blockplan` so the same filter flags work:
`--theme`, `--weekends`, `--weekend-days`, `--country`, `--noevents`,
`--nodurations`, `--milestones`, `--WBS`, `--status`, `--empty`. (There is no
`--includenotes` — the Notes column is always emitted.)

The label columns are **not** frozen, and no freeze pane is set at all — with
the full events-table column set the label block is far wider than a screen,
and the rows are independent records meant for sorting and filtering rather
than a grid you scroll within.

Data-row behavior:

- Rows are ordered by `start_date`, then by `name`.
- Each event or duration occupies its own row — cells in the label columns
  (A–AS) are written independently (never merged) so per-cell colour and font
  rules from `style_rules` can apply.
- **Single-day events**: the resolved icon glyph (theme `style_rules`'
  `icon:` → events.icon → `●`) is placed in the day column (AU+) that
  corresponds to the event's start date.
- **Multi-day durations**: every visible day column between start and end
  is filled with the style-resolved colour (or `events.color` when no rule
  matches).
- **Continuation marker**: when a duration extends past the visible range,
  column AT (the column just after the label block) carries `◀`, `▶`, or
  `◀▶` to indicate which side(s) continue.
- **Holiday overlay**: after all data rows are drawn the federal-holiday /
  company-holiday / weekend decoration is applied to the day columns. When
  a cell already holds an event icon or duration colour, the overlay uses
  an Excel `lightUp` pattern that combines the holiday colour (foreground
  stripes) with the data colour (background) so both stay visible.

Default output path: `output/ExcelBlockplan.xlsx`. The header rows are the theme's `timescale` rows (primary rows above the column headers, secondary rows appended after the last data row); fonts come from the `excelblockplan:` block, colours from `holidays` and the shared roles — see [ExcelBlockplan Subcommand](#excelblockplan-subcommand).

#### `blockplan` rendering behavior

In blockplan, items are first assigned to configured lanes, then rendered separately as events or durations:

- Lane assignment is driven by each lane's `match` rules. Supported filters include WBS prefixes, resource groups, resource name substrings, task-name substrings, notes substrings, milestone/rollup flags, event type, and priority filters/ranges.
- If `blockplan.lane_match_mode` is `first`, an item stops at the first matching lane. If it is `all`, the same item can appear in multiple lanes.
- If `blockplan.show_unmatched_lane` is enabled, unmatched items are collected into the configured unmatched lane instead of disappearing.
- Durations are drawn as horizontal bars inside the lane's duration section. Bars are packed into rows to avoid overlap. With `durations.wbs_group_depth` above 0 (default 2), bars sharing their first N WBS segments form a family: the family takes one `palettes.event` color for the whole page (families take colors in the order they first appear by date), families are packed in WBS order, and a family's rollups — or the bar whose WBS is the family code — sit in rows above its other bars. Bars without a WBS, and every bar when the depth is 0, use the event's own `Color`, else `palettes.event[event.priority % len(palettes.event)]`, packed in date order. A matching style rule's fill wins over both; durations with notes and `-notes` enabled switch to a taller weekly-style bar with the `boxes.duration` fill and separate note line.
- Events are drawn as point markers with a text label to the right. If the event has an icon and that icon resolves from the icon table, the icon is used as the marker; otherwise a filled circle is drawn.
- Event rows are assigned to avoid horizontal label collisions. If enabled, event dates render above the event name, and notes render on a separate line below the name.

#### `compactplan` rendering behavior

In compactplan, durations and milestones are rendered relative to a horizontal dashed axis spanning the full content width:

- Duration lines are placed using a greedy row assignment that alternates above and below the axis. Row 0 is immediately above the axis, row 1 is immediately below, row 2 is further above, row 3 further below, and so on. Durations are sorted by start date before placement; the first row with no x-overlap is chosen.
- **Duration line colors** come from the theme's `style_rules`, the same [event color rules](#style-rules-conditional-restyling) every view uses: a `box:duration` (or `box:event`) rule whose `style` sets `fill` colors the bars it selects, and when several match, the last one wins.
  - A bar no rule colors keeps the **default assignment, by resource group**: the event's own `Color` if it has one, else its group's color from `palettes.event`. Groups take palette slots in sorted name order, wrapping when there are more groups than colors; ungrouped bars sort first. Every group present keeps its slot even when rules color all its bars, so adding a rule never reshuffles the other groups' colors.
  - A rule's `fill` beats the event's own `Color`.
- **Duration start icons**: an icon is drawn at the start (left) end of every duration line that has one. With `durations.replace_icons_with_numbers` `true` (the default) that icon is the duration's number — see [Durations, events and numbered icons](#durations-events-and-numbered-icons). With it `false` the bar shows the icon its style rule or event data names, if any.
- Milestone markers are drawn on the axis at the milestone date: a stem standing up from the axis, topped by a pennant or an icon. Icon priority: a style rule's `icon` → `event.Icon` from the database → `icons.milestone.name` from the active theme; with none of those, or a name not in the `icons` table, the built-in pennant is drawn. An icon takes the pennant's place at the stem tip, sized to the flag height (capped at one label line), in the milestone's color — the event's `Color`, a style rule's `fill_color`, or the `ec-milestone-marker` color — unless a style rule sets `icon_color`; a theme can halo it with a `box:milestone` rule. If `show_milestone_labels` is enabled, the task name is drawn in italic to the right of the marker. In the details document, the milestone's Key cell carries the same icon or flag.
- The column header bands are the theme's `timescale` rows (primary above the chart, secondary below), the same stack every view draws; see [Timescale](#timescale-one-stack-for-every-view). Rows whose cells are too narrow to read are dropped; a label too wide for its cell is compressed.
- The layout is content-first and always shrunk: the axis is fixed at the vertical centre of the content area, duration rows are placed around it, then the header rows float `compact_plan.header_bottom_y` pts above the topmost row. The SVG viewBox is trimmed to exactly the rendered content — from the top of the header bands to the lowest ink below the axis (the bottom row's bar or the icons riding on it) — producing the smallest possible output.
- **The key is the details document.** Nothing but the chart is drawn on the chart page. What each bar, flag and symbol means is written to the run's [details document](#the-details-document), which carries everything the key page did:
  - Each activity's **Key** cell (`marker`) is its bar in miniature: a mark in the exact color it was drawn in, its start icon, and the continuation arrows if it runs off either end. A milestone's is its flag or icon in its marker color. Its **Color** cell names the color, and its **Color Key** row says where it came from: a style rule (listed by the rule's `name`), the resource group's palette slot, or the event's own `Color`.
  - Sort the Events table with `details.markdown.sort: [color_rank, start_date]` to list rows as the key did: rows of one color together, the colors in the order they are handed out (each style rule's that colored a bar, in the theme's order, then each resource group's palette color by slot, then any color only events carry), with milestones, which take no color assignment, last.
  - The **Icons & Symbols** table explains the continuation arrows (`compact_plan.continuation_before_legend_text`, default `"activity began earlier"`, and `continuation_legend_text`, default `"activity continues"`, each listed only when a bar needs it) and the axis (`compact_plan.legend_axis_text`, default `"timeline"`, listed when `show_axis` and `show_axis_legend` are on).
  - A bar name shortened to fit, or a date left out for want of room, is listed under **Exceptions**.
- **Continuation icons**: when a duration event's end date extends beyond the specified calendar end date the line is clamped to the right edge of the timeline. If `continuation.show` is `true` (the default), a small icon is drawn at the right edge of the clamped line and listed in the details document's Icons & Symbols table. The icon name (default `"arrow-right"`), display height in points (default `8.0`) and color come from `continuation.icon_after`, `continuation.icon_height` and `continuation.icon_color` (compactplan is horizontal-only and only clips on its trailing end, so it reads `icon_after`). See [Continuation icons](#continuation-icons).
- The chart's text takes its font and size from the `text` roles (`band_label`, `event_name`, `event_notes`).
- The today line and its label (`today`, `lines.today`) are drawn when today falls within the date range.
- `--weekends` controls whether weekend columns are included in the x-axis day list (same as all other commands).

### `gantt`

| Name | Required | Description | Choices |
|---|---|---|---|
| `START_DATE` | no | Start date in YYYYMMDD format (will be adjusted to full week) |  |
| `END_DATE` | no | End date in YYYYMMDD format (will be adjusted to full week) |  |

### `help`

| Name | Required | Description | Choices |
|---|---|---|---|
| `subcommand` | yes | Subcommand to show help for | blockplan, candybar, colors, colorsheet, compactplan, excelblockplan, exportdata, fonts, fontsheet, gantt, glyphs, icons, iconsheet, mini, mini-icon, palettes, palettesheet, papersizes, patterns, patternsheet, pit, text-mini, themes, timeline, weekly |

### `mini`

| Name | Required | Description | Choices |
|---|---|---|---|
| `START_DATE` | no | Start date in YYYYMMDD format (will be adjusted to full week) |  |
| `END_DATE` | no | End date in YYYYMMDD format (will be adjusted to full week) |  |

#### `mini` day styling behavior

In the SVG mini calendar, day-level styling is driven by holidays, special days, and events:

- Only single-day events and milestones are shown by default. A multi-day duration paints a bar across a run of day cells and buries the marks beneath it, so the whole mini family (`mini`, `mini-icon`, `text-mini`, and `candybar`, which draws its year strip with the same day-cell engine) leaves durations out unless `--durations` / `-du` is passed. There is no `--nodurations` on these views — it would only restate the default.
- An icon replaces the day number when the resolved day style has an icon. This can come from a holiday icon, a special-day icon, or an event `Icon` value. If both milestone and non-milestone event icons exist on the same day, the milestone icon wins.
- A day number is circled when any event on that day has `Milestone` set and `mini_calendar.circle_milestones` is enabled.
- A day number is bold when the day contains a milestone, or when any event on that day has `Priority <= 1`.
- A day number changes color when one of these applies: the day is from an adjacent month, the day is a holiday, or a `style_rules` entry colors the event (for example by resource group).
- Adjacent-month day cells can be shown or hidden with `mini_calendar.show_adjacent` (default: `true`).
- A configurable outline can be drawn around each entire month grid (title + DOW header + day cells) with the `mini_calendar.month_outline` line (`color`, `width`, `opacity`, `dasharray`); the outline is off by default (`null`).
- Day cells can also receive SVG pattern decorations from `style_rules` entries with `apply_to: box:day` (the mini renderer reads the same `style_rules` list as weekly).
- If none of those overrides apply, the day number uses the `text.day_number` role's color (shared with `mini-icon` and `candybar`).
- `today.highlight` (`show`, `color`, `opacity`) fills the current day's cell; it does not by itself make the number bold or change the number color.

#### Details

`mini`, `mini-icon` and `candybar` list the range's events, the icons each
day carries and the holidays and special days the grid shows in the run's
[details document](#the-details-document). A day cell has four corners for
icons; an icon it had no corner for is listed under **Exceptions**.

### `mini-icon`

| Name | Required | Description | Choices |
|---|---|---|---|
| `START_DATE` | no | Start date in YYYYMMDD format (will be adjusted to full week) |  |
| `END_DATE` | no | End date in YYYYMMDD format (will be adjusted to full week) |  |

#### `mini-icon` day rendering behavior

`mini-icon` is a variant of `mini` that replaces plain day-number text with SVG icon images drawn at 80 % of the cell height. Everything else — grid layout, month rows/columns, holidays, events, milestones, week numbers, adjacent-month cells, pattern decorations, and the details document — behaves identically to `mini`.

**Icon selection priority (highest → lowest):**

1. `icon_replace` from an event, holiday, or special-day rule on that date — replaces the day icon entirely.
2. `icon_append` from an event, holiday, or special-day rule — used when no `icon_replace` is present.
3. Day-number icon from the configured icon set — one of 31 per-day icons (1–31) looked up by name from the icon database.
4. Plain day-number text — rendered as a fallback if the icon name is not found in the database.

**Available icon sets** (theme key `mini_calendar.icon_set`):

| Set name | Style |
|---|---|
| `squares` | Outlined square badges with white fill (default) |
| `darksquare` | Solid dark-filled square badges |
| `circles` | Outlined circle badges with white fill |
| `darkcircles` | Solid dark-filled circle badges |
| `squircles` | Outlined squircle (rounded-square) badges with white fill |
| `darksquircles` | Solid dark-filled squircle badges |

**Layout auto-scaling:** The grid always fits all requested rows within the available content area. When the width-derived square-cell size would cause the bottom rows to overflow the page (common in landscape orientation with many rows), the cell height is reduced to fit — cells become slightly shorter than wide but remain visually compact.

**Inherited `mini` options** — all flags and config fields that apply to `mini` also apply to `mini-icon`, including:
`--mini-columns`, `--mini-rows`, `--weeknumbers`, `--week1-start`, `--week-number-mode`, `--weekends`, `--theme`, `--papersize`, `--orientation`, `--margin`, `--header`, `--footer`, `--watermark`, and all filter flags.

### `candybar`

| Name | Required | Description | Choices |
|---|---|---|---|
| `START_DATE` | no | Start date in YYYYMMDD format (will be adjusted to full week) |  |
| `END_DATE` | no | End date in YYYYMMDD format (will be adjusted to full week) |  |

#### `candybar` layout and behavior

`candybar` renders a tall, narrow vertical year-strip — modeled on the *ISO Week Numbers* spreadsheet layout. Each **row is one ISO week** (Mon–Sun across seven columns), with a week-number column on the left and the day-of-month number in each day cell. The requested date range is **expanded out to whole-week boundaries** (start snaps back to its week-start day, end snaps forward to its week-end day) so the first and last rows are always complete weeks — no blank end cells. Boundary days from the adjacent month are shown with their day numbers and pick up any events/holidays on those dates.

The number of rows is derived from the start/end dates — a full year produces ~53 rows. By default the rows are auto-scaled to fit the page height; set `--candybar-row-height` for a fixed row height, or `--candybar-max-rows-per-page` to split a long range into multiple side-by-side strips.

**Box widths.** Day cells are **square by default** — their width equals the (auto-fit or fixed) row height — and the resulting strip is centered horizontally rather than stretched to fill the page. Widths are theme-configurable under the `candybar:` section:

| Theme key | Default | Meaning |
|---|---|---|
| `cell_width` | `0` | Day-cell width in points. `0` = square (width == row height). |
| `weeknum_col_ratio` | `0.6` | Week-number column width as a multiple of the day-cell width. |
| `month_col_ratio` | `1.6` | Month-box column width as a multiple of the day-cell width. |

`cell_width` can also be set on the command line with `--candybar-cell-width POINTS`; the two column ratios are theme-only.

**Month column.** The right-hand column holds the theme's **month row** laid down the strip: the first `month` row of `timescale.primary` provides its format, text (`font`, `size`, `color`, `align`, `rotation`), fill and border, and consecutive week rows of one month merge into one cell. A week is attributed to the month of its last visible day, so a boundary week such as Jan 27–Feb 2 is labeled *Feb* (matching the spreadsheet reference). Month names read bottom to top unless the row's `text.rotation` says otherwise; a theme without a `month` row in `primary` draws no month column content.

**Decoration and icons.** Day cells use the **same rule engine as `mini`/`mini-icon`** — holidays, special days, events, and theme `style_rules` / `box:day` rules drive cell shading, SVG pattern decorations, milestone circles, and icon placement (`icon_replace` / `icon_append`). Day cells show the day number by default and swap in an icon only when a rule requests one.

**Cell shading (months & weekends).** In addition to the rule engine, candybar has two built-in base shades drawn *under* the rule/holiday shade (so holidays still win):

- **Month banding** — enable with `candybar.month_shading: true`. Day cells are tinted per calendar month with the month's colour from `palettes.month` (or `palettes.month_colors`), at `shading.month_opacity` (default 0.12).
- **Weekend tint** — `holidays.weekend` (`color`, `opacity`) shades the Sat/Sun day cells, independent of the rule engine, in every view that shows weekends. (Only visible when weekends are shown.)

**Weekend suppression.** Candybar **shows weekends by default** (7-column Mon–Sun strip), independent of the `--weekends` / `weekend_style` setting. Set `candybar.suppress_weekends: true` in a theme to drop the Sat/Sun columns for a 5-column Mon–Fri strip.

**Candybar-specific options:**

| Option | Argument | Description |
|---|---|---|
| `--candybar-row-height` | `POINTS` | Fixed week-row height (default: 0 = auto-fit to page). |
| `--candybar-cell-width` | `POINTS` | Fixed day-cell width (default: 0 = square, width == row height). |
| `--candybar-max-rows-per-page` | `N` | Split into side-by-side strips after N rows (0 = single strip). |

Candybar also accepts the shared `mini` options (`--weeknumbers` mode/anchor via `--week-number-mode` / `--week1-start`, `--theme`, `--papersize`, `--orientation`, `--margin`, `--header`, `--footer`, `--watermark`, `--fiscal`, and the event filter flags `--noevents`, `--durations`, `--milestones`, `--WBS`, `--status`, `--empty`). Like the other mini views, candybar shows single-day events and milestones only unless `--durations` is passed.

### `palettesheet`

| Name | Required | Description | Choices |
|---|---|---|---|
| `NAME` | no | Name of the palette to preview (case-sensitive, from DB palettes table). If omitted, every palette is rendered into a single SVG. |  |

Renders a single named palette as an SVG swatch sheet. Run `ecalendar.py palettes` to discover palette names. Omit `NAME` to render every palette into one sheet, each palette as its own labeled section.

Pass `--paginate` to split the sheet across multiple printable "pages" instead: `--columns`/`-cols` sets the swatches per row (default `12`), `--rows`/`-rows` the rows per page (default `10`), and `--sized N` the swatch box size in points (default `80`, width = height; the label and spacing gaps are unchanged). `--columns`/`--rows`/`--sized` are only valid together with `--paginate`. Pages get a `_pNN` suffix before the file extension (e.g. `palettesheet_p01.svg`).

The two forms paginate differently:

- **With a palette name**, that one palette's swatches are split into `columns × rows` pages, and each page's title keeps the palette name while the color count is replaced by the page's color-name range — for example `(azure to steelblue)`.
- **Without a palette name**, pages hold the same labeled palette sections as the single sheet, packed so each page carries **as many complete palettes as fit**. A page's budget is the height of `--rows` swatch rows, palettes are packed into it in alphabetical order, and a palette is never split across a page break — one that is taller than a whole page simply gets its own, taller, page. This keeps the page count low: with the defaults the ~90 palettes in the database land on roughly a dozen sheets rather than one per palette.

### `patternsheet`

No positional arguments. Use `--filter` to narrow the rendered grid by pattern name and `--color` to set the tile fill (default `#333333`). Use `--tile-size` to preview a different auto-normalized tile size (default `18` points; `0` shows tiles at their native size). Run `ecalendar.py patterns` to discover pattern names.

Pattern tiles are monochrome artwork, and `--color` — like a `style_rules` `patterncolor` — repaints all of a tile's ink, whichever form the source SVG declared it in. One pattern is the exception: `stars65` is an embedded bitmap rather than vector geometry, so it always renders in its own black. `ecalendar.py patterns` marks it `[fixed]`, and the sheet labels it `(fixed)`.

### `iconsheet`

No positional arguments. Use `--filter` to narrow the rendered grid by icon name and `--color` to set the stroke color (default `#333333`). Run `ecalendar.py icons` to discover icon names.

By default a single SVG containing every (name-sorted) icon is produced, with the sheet title as its header. Pass `--paginate` to instead split the icons across multiple printable "pages": `--columns`/`-cols` sets the icons per row (default `8`) and `--rows`/`-rows` sets the rows per page (default `10`), giving 80 icons per page by default. `--sized N` sets the icon render box to `N×N` points (default `24`); the label and spacing gaps are unchanged so larger icons simply get larger cells. `--columns`/`--rows`/`--sized` are only valid together with `--paginate`. When paginating, a `_pNN` suffix is inserted before the file extension (e.g. `iconsheet_p01.svg`, `iconsheet_p02.svg`), and each page header shows the first and last icon name on that page joined by `to` — for example `10baseT  to  C-squircle` (the icon count is omitted on paginated pages, since icon names can themselves contain dashes).

### `colorsheet`

No positional arguments. Use `--filter` to narrow the rendered grid by color name. Run `ecalendar.py colors` to discover color names.

By default a single SVG containing every (hue-sorted) color is produced. Pass `--paginate` to instead split the swatches across multiple printable "pages": `--columns`/`-cols` sets the swatches per row (default `8`) and `--rows`/`-rows` the rows per page (default `10`), giving 80 colors per page by default. `--sized N` sets the swatch box width in points (default `110`); the height scales with it to keep the sheet's aspect ratio, and the label and spacing gaps are unchanged. `--columns`/`--rows`/`--sized` are only valid together with `--paginate`. When paginating, a `_pNN` suffix is inserted before the file extension (e.g. `colorsheet_p01.svg`), and each page keeps the sheet title but shows the page's color-name range in place of the color count — for example `(Eton blue to Robin egg blue)`.

### `fontsheet`

No positional arguments. Three sample rows (uppercase, lowercase, digits/punct) are drawn for each registered font. Use `--filter` to narrow by font name, `--color` to set glyph color (default `#222222`), and `--fullset` to render every glyph in each font instead of the three fixed rows. Note that `--database` is not accepted because font files come from the `fonts/` directory rather than the DB.

By default every font goes into a single SVG. Pass `--paginate` to split them across printable pages: `--columns`/`-cols` sets the font columns per page (default `2`) and `--rows`/`-rows` the rows per page (default `10`), giving 20 fonts per page by default. `--sized N` sets the sample text size in points (default `16`); entry heights follow it. `--columns`/`--rows`/`--sized` are only valid together with `--paginate`, and `--columns` is ignored with `--fullset` (a full glyph set spans the whole content width, so it is always one column — pair it with a small `--rows`, since each entry can run to hundreds of kilobytes). Pages get a `_pNN` suffix before the file extension (e.g. `fontsheet_p01.svg`), and each page keeps the sheet title but shows the page's font-name range in place of the font count.

### `exportdata`

| Name | Required | Description | Choices |
|---|---|---|---|
| `START_DATE` | no | Start date in YYYYMMDD format (will be adjusted to full week) |  |
| `END_DATE` | no | End date in YYYYMMDD format (will be adjusted to full week) |  |

Exports filtered events and durations as a CSV file matching the schema consumed by `importers/import_events.py`. Supports the standard content filters (`--noevents`, `--nodurations`, `--milestones`, `--WBS`, `--status`) and `--country` for selecting which government holidays accompany the event rows. By default only `status='active'` events are exported — pass `--status all` or a specific list (e.g. `--status active,draft`) to widen the result. The `--outputfile` short form is `-o` (not `-of`); the default path is `output/exportdata_YYYYMMDD.csv` based on the run date.

The exported CSV includes every column of the `events` table that round-trips back through the importer: `task_name`, `status`, `start_date`, `finish_date`, `earliest_start_date`, `latest_start_date`, `earliest_end_date`, `latest_end_date`, `priority`, `wbs`, `rollup`, `milestone`, `percent_complete`, `effort`, `duration`, `predecessors`, `resource_names`, `resource_group`, `notes`, `icon`, `color`, `tags`.

### `text-mini`

| Name | Required | Description | Choices |
|---|---|---|---|
| `START_DATE` | no | Start date in YYYYMMDD format (will be adjusted to full week) |  |
| `END_DATE` | no | End date in YYYYMMDD format (will be adjusted to full week) |  |

`text-mini` takes `--theme` like the other views. The theme keys it reads are the `text_mini:` block (`cell_width`, `month_gap`, `glyphs`), `mini_calendar.show_adjacent`, and a `fiscal_period` timescale row for fiscal labels. Its remaining inputs — `--mini-columns` / `--mini-rows`, `--weeknumbers`, `--weekends` — are CLI-only and have no theme key.

#### `text-mini` symbol behavior

In the text mini calendar, each day cell shows either a formatted day number or one resolved symbol:

- Plain day numbers are shown only when no higher-priority symbol has been assigned to that day.
- Single-day events use symbols from the `text_mini.glyphs.event` group.
- Milestones use symbols from the `text_mini.glyphs.milestone` group.
- Multi-day durations are excluded by default (as in `mini` and `mini-icon`); pass `--durations` / `-du` to include them. When included, they use symbols from the `text_mini.glyphs.duration` group on the start and end dates, and use the `text_mini.glyphs.duration_fill` glyph for interior days.
- Holidays use symbols from the `text_mini.glyphs.holiday` group.
- Special days marked `nonworkday` use symbols from the `text_mini.glyphs.nonworkday` group.
- Symbol precedence is enforced by priority, highest to lowest: holidays, company nonworkdays, milestone events, duration start/end markers, duration interior fill, then regular single-day events.
- When multiple symbols compete for one day, the higher-priority symbol replaces the lower-priority one in the month grid. A details list is appended below the calendar for the assigned symbols.
- The details list opens with a `Calendar Details` heading and is grouped under one subheading per entry type, in this order: `Events`, `Milestones`, `Durations`, `Holidays`, `Non-Working Days`. A type with no entries is skipped entirely. Within each group, entries run in ascending date order, and dates are zero-padded `MM/DD` (durations show `MM/DD - MM/DD`). Government holidays are prefixed with their two-letter country code — see [Government holiday labels](#government-holiday-labels):

```
Calendar Details

  Milestones
    🄰 02/02 Project Kickoff
    🄱 02/27 Requirements Sign-off

  Holidays
    🅰 07/04 US - Independence Day
    🅲 07/15 UA - Ukrainian Statehood Day
```


### `timeline`

| Name | Required | Description | Choices |
|---|---|---|---|
| `START_DATE` | no | Start date in YYYYMMDD format (will be adjusted to full week) |  |
| `END_DATE` | no | End date in YYYYMMDD format (will be adjusted to full week) |  |

#### `timeline` rendering behavior

In timeline, single-day events and multi-day durations are rendered differently and use separate color cycles:

- Single-day events become callout boxes above the axis. Durations become bars below the axis.
- Event callouts and duration bars take their colors from `palettes.event`, cycling in sorted order when there are more items than colors; with `durations.wbs_group_depth` above 0 a WBS family shares one color across callouts and bars. A `style_rules` fill wins.
- Event markers on the main axis are always plain circles; event icons, when present and found in the icon table, appear inside the event callout box next to the title instead of on the axis marker.
- A callout box is two columns: the event's icon over its **start date** on the leading side (`timeline.events.icon_column_ratio` sets the split, 15% by default), the name over the notes on the other. Both columns are filled whichever way the axis runs.
- **A duration bar is a three-column grid**, the callout box's two columns with one more: the event's icon over its **start date** on the leading side, the **name over the notes** in the middle, and the **end date** on the trailing side. The two side columns are the same width — `timeline.durations.icon_column_ratio`, or the callout boxes' `timeline.events.icon_column_ratio` when a theme sets only that — so the dates at the two ends are laid out identically and a row of bars reads as a column of dates with the names between them. A gap either side of the middle column keeps the name and notes off those dates.
- **Duration bars span exactly their dates.** Each edge sits at the x of the day it names, so every bar starting on a given day shares a left edge and every bar ending on one shares a right edge — bars can be read against the axis and against each other. One vertical leader ties the bar back to the axis, drawn from the start date; a second at the end date would cross every bar stacked between the two edges.
- **When a bar is too narrow for its text** it is *not* widened — its edges are its dates. The grid holds, and the bar answers in two steps. First it **breaks the name across both rows of the middle column**, at the word boundary that balances the two lines, and **drops the notes** that second row would otherwise carry: two legible lines of what the activity is beat one line of it above a description neither has room for. A single-word name stays on one line. Second, whatever text still wants more than its cell is **condensed horizontally at full font size, keeping every word** — and every cell of the bar is condensed by *the same* factor, the one the tightest of them needs, so the name, both dates and the event icon narrow together rather than each being squashed to its own cell's taste. A bar too narrow to give its side columns 3pt — where every cell would be thinner than the ink it carries — draws nothing inside; the rect alone stands. `timeline.durations.box_width`, when a theme sets it, is the width the grid is considered to want: it decides which bars break and condense, and never stretches one.
- A **vertical** timeline follows the same rules along its own axis: a bar runs from its start date to its end date, carries the one start-date leader, and breaks and condenses its text rather than stretching. Its grid is the same one turned a quarter-turn — the columns run along the axis (start date at the top, name and notes between, end date at the bottom) and the rows across the bar's thickness. Text is rotated to read bottom→top with the bar; the icons stay upright, since an indicator on its side reads as a different glyph, and condense along the axis with the text rather than across it.
- **Both directions spend their two sides the same way.** `primary` is above a horizontal axis and right of a vertical one; `secondary` is below or left. Event callouts take the side `timeline.label_side` names and the duration bars take the other one, so the default (`label_side: primary`) reads callouts above, bars below. `timeline.duration_side` overrides that — `primary` / `secondary` / `both` pin the bars wherever you want them, including back onto the callouts' side. With `label_side: both` the bars split across both sides too. The tick dates and fiscal rows go opposite the bars (the secondary side when bars take both), and holiday marks go opposite the tick dates.
- Event callout boxes are lane-positioned and horizontally offset to reduce collisions. Their connector lines are routed to avoid other boxes when possible.
- **Axis ticks and their dates** come from the `timescale` rows that carry a `tick:` facet, in both directions: a row on the primary side draws its ticks and labels on the axis's primary side (above a horizontal axis, right of a vertical one), a secondary row on the other side. A tick's mark is `lines.tick` (overridden by the facet's `width`, `color`, `opacity`), its label the `text.event_date` role aligned by `tick.label_align`, set `tick.label_gap` from the mark; `tick.max_label_count` drops the labels of a row that would carry too many. Without a `tick` row no ticks are drawn. Under `--shrink` the viewBox is widened to keep a vertical axis's labels.
- **Timebands, the today marker and holiday marks are drawn in both directions**, each turned through the same quarter-turn:
  - *Rows without a `tick:` facet* (fiscal quarters, months, dates ...) become bands at the page edges — rows above and below a horizontal chart, columns left and right of a vertical one — in the order the theme lists them, with their labels rotated on a vertical chart. The axis is placed in what is left over.
  - *The today marker* crosses the axis at today's date (`today.show`, `today.date`, `lines.today`). `today.direction` names a side of the axis (`primary`, `secondary` or `both`) and `today.length` how far it reaches (`0` = all the room there is); the label (`today.label`, `text.today_label`) rides off the line's end, kept clear of the band rows.
  - *Holiday marks* come from a `unit: holiday` row: each flag sits beside the axis with its date written past it (`holidays.show_icons`, `icon_size`, `show_dates`, `date_format`), on the side the row belongs to; on a vertical axis dates that would collide step further out instead of down.
- With `--noevents` the axis moves to the edge of the area the bars leave free — the top of a horizontal chart when the bars are below, the bottom when they are above, the middle when they take both sides — kept far enough in for its own tick dates to be printed.
- The timeline does not shade the current day. Instead, it has a dedicated today marker: a vertical line and label rendered only when the resolved today date falls inside the displayed date range.

### `weekly`

| Name | Required | Description | Choices |
|---|---|---|---|
| `START_DATE` | no | Start date in YYYYMMDD format (will be adjusted to full week) |  |
| `END_DATE` | no | End date in YYYYMMDD format (will be adjusted to full week) |  |

#### `weekly` rendering behavior

In weekly, day-box cells are drawn first, events and durations are placed into the available rows inside each visible day, then the day-number row is laid out with full knowledge of which days overflowed:

- Day-box background color is chosen from month colors by default, from fiscal-period colors when `fiscal.use_period_colors` is enabled, or from the `holidays.federal` / `holidays.company` colors when the date is marked as a special day. `today.highlight` overrides that fill for the current day only.
- The number of event rows per day box is derived from the box height, day-number height, and event-row height so the bottom row never bleeds into the next week's cell.
- Day-number row layout (left → right): fiscal label, week number, overflow icon, holiday/special-day icon(s), holiday name, day number. Every element is vertically centered with the day number — text/icon baselines shift by `0.3 × (day_num_size − element_size)` so labels with smaller fonts share a midline with the day number rather than a baseline.
  - **Week numbers** appear only on week-start days when `--weeknumbers` is enabled. They sit either in the left page margin (when one is present) or inside the day box past the fiscal label.
  - **Overflow icon** is drawn only on days where at least one event or duration could not fit into the available rows. Multiple overflows on the same day produce a single icon. The icon's color is `icons.overflow`, its glyph `overflow.icon`.
  - **Holiday / special-day icons** are drawn one per marking, in sequence after the overflow icon. Federal holidays come first, then company special days. Numeric icon IDs are resolved through the `fonticon` table.
  - **Holiday name** is drawn ONLY when there is exactly one marking AND no overflow on that day; otherwise the row is icon-only so multiple markings stay visible. The name follows immediately after the icon (left-justified) and shrinks to fit the space between the icons and the day number while the icon itself stays at the unshrunk theme size.
- Fiscal period labels come from the theme's first `fiscal_period` timescale row (`format`, optional `end_format`, `text`) and appear on a period's first visible day when `--fiscal` is given.
- Day-box pattern and color decorations come from `style_rules` entries with `apply_to: box:day`. Rules can match on day context (federal/company holiday, nonworkday, weekend, date) and event criteria (task name, notes, WBS, percent complete, resource group/names, priority, milestone, rollup, event type). Rules layer additively in declaration order. If no rule supplies a pattern, `weekly.day_box.hash_pattern` is used as the fallback. See [Style rules](#style-rules-conditional-restyling) for the full syntax.
- Single-day event text and event icons use the color a `style_rules` entry gives the event (for example by resource group); otherwise the `text.event_name` and `icons.event` colors.
- Item placement order is controlled by `item_placement_order` (`events.item_placement_order`), shared by every visualizer that places or orders event data — not just weekly. Type tokens (`milestones`, `events`, `durations`) determine grouping order; `wbs` orders WBS-having rows first (numeric comparison) with WBS-less rows always last; `priority` or `alphabetical` determine ordering within a group or the whole list; any other string names an events-table field; a mapping (e.g. `{resource_group: "Executive"}`) is a criteria token using the same select vocabulary as `style_rules`, and matching events sort ahead of non-matching ones. Defaults to `[wbs, start_date]` when a theme doesn't set it.
- Events with notes need two free rows in the day box when `-notes` is enabled. Durations with notes also require two stacked rows for their double-height bar; if that space is not available, they overflow instead of being compressed into a one-row notes layout.
- Continuation dates on duration bars (drawn when a duration starts before the calendar's first visible day or ends after the last) sit **inside** the bar — the start date is drawn just right of the left continuation arrow, the end date is drawn just left of the right continuation arrow, both vertically centered with the bar's name baseline.

#### Overflow

The icon in the day-number row says *that* something was left out; the
run's [details document](#the-details-document) says *what*. Every event
and duration that could not be placed is an **Exceptions** row ("Did not
fit in its day") naming the item, its span and the day box it was pushed
out of -- the one to go and look at. The item's own Events row says whether
it was drawn at all (`drawn: no`) or only in part (`partial`).

### `pit`

| Name | Required | Description | Choices |
|---|---|---|---|
| `START_DATE` | no | Start date in YYYYMMDD format (will be adjusted to full week) |  |
| `END_DATE` | no | End date in YYYYMMDD format (will be adjusted to full week) |  |

## Event Status

Every row in the `events` table carries a `status` value. The system recognizes five values: `active`, `draft`, `cancelled`, `archived`, and `on-hold`. Other values are accepted by the importer and stored as-is, but render as if `active`.

**Filtering.** By default, all rendering and export commands include only events with `status='active'` — older statuses stay in the database but don't appear in output. Pass `--status` to widen the set:

```bash
# Default: only active events (equivalent to --status active)
PYTHONPATH=. uv run python ecalendar.py weekly 20260101 20260131

# Include drafts alongside active events
PYTHONPATH=. uv run python ecalendar.py weekly 20260101 20260131 --status active,draft

# Show every event regardless of status
PYTHONPATH=. uv run python ecalendar.py weekly 20260101 20260131 --status all

# Export only cancelled events for a clean-up review
PYTHONPATH=. uv run python ecalendar.py exportdata 20260101 20261231 --status cancelled -o cancelled.csv
```

Unknown status names are rejected at the CLI; the error message lists the allowed values.

**Visual treatment.** When non-active statuses are surfaced via `--status`, the weekly renderer dims them via opacity so they remain visible but visually subordinate to active work:

| Status | Opacity | Use case |
|---|---|---|
| `active` | 1.00 | Default — full visibility |
| `draft` | 0.55 | Planned but not yet committed |
| `on-hold` | 0.50 | Paused; expected to resume |
| `cancelled` | 0.35 | Will not be done; kept for audit trail |
| `archived` | 0.25 | Historical record; rarely shown |

The opacity applies to the event name, event icon, duration bar fill, duration name/notes/icon, and continuation arrows/dates. It is multiplied with any theme-supplied opacity so style-rule transparency still composes correctly.

**Import.** The importer (`importers/import_events.py`) reads `Status` (or `State`) from the source file's columns. When the column is absent or blank, the row is stored with `status='active'`. CSV / XLSX files exported via `exportdata` round-trip cleanly: status is preserved column-for-column.

## Government Holiday Labels

Wherever a view lists holidays alongside their dates, the holiday name is prefixed with its ISO 3166-1 alpha-2 country code:

```
07/15 UA - Ukrainian Statehood Day
```

`--country`/`-cc` accepts several countries at once (`-cc US,CA,UA`), and countries share holiday *names* — 1 January is `New Year's Day` in both the US and Canada — so without the code a listing cannot say whose holiday a row describes. The prefix appears in:

| Listing | Where |
|---|---|
| `text-mini` details | the `Holidays` section under the calendars |
| Details document | the `Federal Holiday` rows of every visualization's Holidays & Special Days table |

The details document collapses a holiday that recurs across visible days into one row, and a holiday that several countries celebrate under the same name into one row listing every code (`CA, US - New Year's Day`).

Company special days come from the `specialdays` table rather than a government holiday calendar, carry no country code, and are never prefixed.

## Importing Events

Project and schedule data lives in the `events` table and is loaded with
`importers/import_events.py`. The importer accepts XLSX / XLS / CSV / TSV input,
matches column names loosely (see [Accepted column names](#accepted-column-names)),
hashes each file for duplicate detection, and records every run in `import_history`.

**Start from the template.** [`templates/event_template.xlsx`](templates/event_template.xlsx)
carries every supported column in order, with the description and format of each
one attached as a cell comment, dropdown validation on the True/False columns, and
three worked example rows. Delete the example rows, paste your data in, and import.
The workbook's second sheet, `Data Dictionary`, restates the full element reference
below for people filling the sheet in.

```sh
# Import the filled-in template
uv run python importers/import_events.py templates/event_template.xlsx

# Re-import after editing the source (replaces the previous batch by file hash)
uv run python importers/import_events.py MyProject.xlsx --replace

# Import every supported file in a directory
uv run python importers/import_events.py Events/ --verbose

# Validate without writing -- reports row count, columns, and missing required fields
uv run python importers/import_events.py MyProject.xlsx --dry-run

# Review what is already in import_history (with row counts per import)
uv run python importers/import_events.py --list

# Drop a previous import and all of its events
uv run python importers/import_events.py --remove 15 --force
```

Excel is the preferred format: it handles multiple comma-separated entries and
special characters (`/ ' " $`) without the quoting rules a CSV imposes. When a
workbook contains a sheet named `Events`, that sheet is read; otherwise the first
sheet is used.

### Required columns

Only three are mandatory: **`Name`**, **`Start`**, and **`Finish`**. Everything else
is optional and may be omitted entirely — absent columns are simply not set.

A blank `Start` is filled from `Finish` (and vice versa), so single-date events need
only one of the two. A reversed pair is swapped rather than rejected. A row with no
parseable date on either side, or with a blank `Name`, is reported as a failed row;
use `--skip-errors` to import the rest of the file anyway.

### Data elements

`Name`, `Start` and `Finish` are marked **\***; all others are optional.

| Column | Also accepted | Description | Format | Example |
| --- | --- | --- | --- | --- |
| `ID` | `GUID` | Unique ID for the task. | Alphanumeric string | `143` |
| `Name` **\*** | `TaskName` | Name of the task. | Alphanumeric string | `Ditch` |
| `WBS` | — | A unique code (work breakdown structure) used to represent a task's position within the hierarchical structure of tasks. | Alphanumeric string separated by periods (.) | `PROJ1.Act1.Task.143` |
| `Priority` | — | Indicates the level of importance assigned to a task. | Alphanumeric string. 1 highest, 99 lowest priority | `77` |
| `Milestone` | — | Indicates whether a task is a milestone. | True or False - can be 0 for false and 1 for true | `False` |
| `Summary` | `Rollup` | Indicates whether a task is a summary task. | True or False - can be 0 for false and 1 for true | `False` |
| `Critical` | — | Indicates whether a task has room in the schedule to slip, or if it is on the critical path. | True or False - can be 0 for false and 1 for true | `False` |
| `Start` **\*** | `StartDate` | Date and time that a task is scheduled to begin. | YYYYMMDDTHHMM | `20260602T1230` |
| `Finish` **\*** | `EndDate` | The date and time that a task is scheduled to be completed. | YYYYMMDDTHHMM | `20260602T1630` |
| `Duration` | — | Total span of active working time for a task. Not to be confused with the effort required to complete this task. | Alphanumeric string | `4hr` |
| `Work` | `Effort` | Total amount of work scheduled to be performed on a task by all assigned resources. | Alphanumeric string | `0.5d` |
| `EarlyStart` | `earliest_start_date` | The earliest date that a task can begin, based on the early start dates of predecessor and successor tasks and other constraints. | YYYYMMDDTHHMM | `20260523T0800` |
| `EarlyFinish` | `earliest_end_date` | The earliest date that a task can finish, based on early finish dates of predecessor and successor tasks, other constraints. | YYYYMMDDTHHMM | `20260523T1700` |
| `LateStart` | `latest_start_date` | The latest date that a task can start without delaying the finish of the project. | YYYYMMDDTHHMM | `20260603T0800` |
| `LateFinish` | `latest_end_date` | The latest date that a task can finish without delaying the finish of the project. | YYYYMMDDTHHMM | `20260603T1630` |
| `ActualStart` | — | Date and time that a task actually began. | YYYYMMDDTHHMM | `20260602T0800` |
| `ActualFinish` | — | Date and time that a task actually finished. | YYYYMMDDTHHMM | `20260602T1200` |
| `Deadline` | — | Date entered as a deadline for the task. | YYYYMMDDTHHMM | `20260630` |
| `StartVariance` | — | The difference between a task's baseline start date and its currently scheduled start date. | Alphanumeric string | `-4h` |
| `FinishVariance` | — | The amount of time that represents the difference between a task's baseline finish date and its current finish date. | Alphanumeric string | `-4h` |
| `FixedCost` | — | A task expense that is not associated with people performing the work - this may be the cost of a fixed price contract, capital acquisition, equipment rental or other non-labor fee. This is the summation of all costs related to this task. | Numeric | `250.00` |
| `PercentComplete` | `percent_complete` | The current status of a task, expressed as the percentage of the task's duration that has been completed. | Decimal number between 0 and 1.0 where 1 is 100% | `1.0` |
| `PercentWorkComplete` | — | The current status of a task, expressed as the percentage of the task's work / effort that has been completed. | Decimal number between 0 and 1.0 where 1 is 100% | `1.0` |
| `Cost` | — | The total scheduled, or projected, cost for the labor associated with the task. This should exclude any FixedCost items. This is the summation of all labor costs related to this task. | Numeric | `200.00` |
| `Notes` | — | Notes about the task. | Alphanumeric string | `This is the ditch that must be placed 4' from the road for drainage for the water tower.` |
| `Resources` | `resource_names` | Names of people associated to this task. | Alphanumeric string | `Pete, Garcia` |
| `ResourceGroups` | `resource_groups` | Department(s) associated to this task. | Alphanumeric string | `Facilities` |
| `Predecessors` | — | Specifies the predecessor tasks. | ID values or WBS values | `123` |
| `Successors` | — | Specifies the successor tasks. | ID values or WBS values | `258` |
| `Icon` | — | Name of icon to be used in visualizations of this task. | Alphanumeric string | `shovel` |
| `Color` | — | Name of the color to be used in visualizations for this task. | Alphanumeric string | `Green` |
| `Tags` | — | Strings associated with this task to be used for selection, filtering, and style rule definition. | Alphanumeric string | `Construction, Grounds` |
| `Custom1` | — | Custom field holding company / user specific value(s) related to this task to be used for selection, filtering, and style rule definition. | Alphanumeric string | `Equipment: $250.00` |
| `Custom2` | — | Custom field holding company / user specific value(s) related to this task to be used for selection, filtering, and style rule definition. | Alphanumeric string | `Pete: $25/hr Garcia: $25/hr` |
| `Custom3` | — | Custom field holding company / user specific value(s) related to this task to be used for selection, filtering, and style rule definition. | Alphanumeric string | `CoA: 99345B2026` |
| `Custom4` | — | Custom field holding company / user specific value(s) related to this task to be used for selection, filtering, and style rule definition. | Alphanumeric string | `Greenbriar Resorts` |
| `Custom5` | — | Custom field holding company / user specific value(s) related to this task to be used for selection, filtering, and style rule definition. | Alphanumeric string | — |

### Dates and times

The canonical format is `YYYYMMDDTHHMM` — `20260602T1230` for 2 June 2026, 12:30pm.
The importer is deliberately lenient and also accepts:

- the colon form, `20260602T12:30`
- a bare date with no time, `20260602`
- `YYYY-MM-DD`, `M/D/YYYY`, `M/D/YY`, `6/2/2026 4:30 PM`, and anything else
  `dateutil` can parse

`Start` and `Finish` keep their time-of-day in separate `start_time` / `end_time`
columns (`HHMM`), leaving `start_date` / `end_date` as plain `YYYYMMDD` day keys —
which is what every calendar view indexes on. `ActualStart` / `ActualFinish` are
stored the same way. A value with no time recorded leaves the time column `NULL`,
so midnight stays distinguishable from "not specified".

`EarlyStart`, `EarlyFinish`, `LateStart`, `LateFinish` and `Deadline` keep the date
only; a time supplied for those is accepted and discarded, since no view reads those
windows at sub-day resolution.

> **Excel tip.** Format the date columns as *Text* before typing, or Excel will
> reinterpret `20260602T1230` as its own date serial. The supplied template already
> does this.

### Durations

`Duration`, `Work`, `StartVariance` and `FinishVariance` are free text. Each is stored
twice: verbatim in a `*_text` column, and parsed into **decimal days** in the numeric
column, so nothing you typed is lost.

| Unit | Accepted spellings | In days |
| --- | --- | --- |
| Minutes | `m`, `min`, `mins`, `minute`, `minutes` | 1 / 480 |
| Hours | `h`, `hr`, `hrs`, `hour`, `hours` | 1 / 8 |
| Days | `d`, `dy`, `day`, `days` | 1 |
| Weeks | `w`, `wk`, `wks`, `week`, `weeks` | 5 |
| Months | `mo`, `mos`, `mon`, `month`, `months` | 20 |

Conversion assumes an 8-hour workday, a 5-day week and a 20-day month; those three
constants live at the top of [`shared/duration_parser.py`](shared/duration_parser.py).

**Accepted forms**

| Form | Example | Decimal days |
| --- | --- | --- |
| Single term | `4hr` | `0.5` |
| Decimal value | `0.5d`, `1.5weeks` | `0.5`, `7.5` |
| Leading decimal point | `.5` | `0.5` |
| Bare number, taken as days | `3` | `3.0` |
| Compound, spaced | `1d 4h` | `1.5` |
| Compound, unspaced | `2w3d` | `13.0` |
| Three or more terms | `1d 4h 30m` | `1.5625` |
| Negative, for the variance fields | `-4h`, `-1d 4h` | `-0.5`, `-1.5` |
| Explicit positive sign | `+1d` | `1.0` |
| Any capitalization | `4 HR`, `4Hr` | `0.5` |
| Surrounding whitespace | `  4hr  ` | `0.5` |
| Estimated-duration mark | `4h?` | `0.5` |
| Cell already typed as a number | `4`, `2.5` | `4.0`, `2.5` |

**Values that do not parse**

Blank cells, and text such as `n/a`, `TBD`, `abc`, `-`, or a partial match like
`4hr of prep`. The whole string must be accounted for — otherwise `4hr of prep`
would silently yield half a day. These leave the numeric column `NULL` while the
`*_text` column still holds the original string, so one unparseable cell costs one
field, never the whole row.

> **`m` means minutes, not months.** `1m` is one minute; use `1mo` or longer for
> months. This follows the schedule exports the importer reads, where minutes are
> common and months are always spelled out — but it is the opposite of the
> convention some scheduling tools use.

**Decimal commas and thousands separators**

Both conventions are understood; which character is the decimal point is decided by
position rather than assumed.

| Input | Reads as | Rule |
| --- | --- | --- |
| `1,5` | `1.5` | fewer than three digits after the comma — decimal comma |
| `1,50` | `1.5` | fewer than three digits after the comma — decimal comma |
| `1,200` | `1200` | exactly three digits after the comma — thousands separator |
| `1,234,567` | `1234567` | thousands separators throughout |
| `1,234.5` | `1234.5` | both present — the later `.` is the decimal |
| `1.234,5` | `1234.5` | both present — the later `,` is the decimal |

One case is genuinely ambiguous: `1,500` could mean fifteen hundred or one-and-a-half
written with three decimal places. It resolves as **1500**, the conventional reading —
three-decimal-place durations do not occur in practice. Write `1.5` if you mean one
and a half.

### Other value formats

- **True/False columns** (`Milestone`, `Summary`, `Critical`) accept `True`/`False`,
  `T`/`F`, `Yes`/`No`, `Y`/`N`, `1`/`0`. Anything unrecognized reads as false.
- **`PercentComplete` / `PercentWorkComplete`** accept either convention: `0.85` and
  `85` both store as `0.85`. Values above 1 are read as percentages.
- **`Cost` / `FixedCost`** accept currency decoration — `$250.00`, `€1.234,56`,
  `1,200`, and `(500)` for a negative — and store as a plain number. They use the
  same decimal-comma and thousands-separator rules as
  [Durations](#durations) above.
- **`Priority`** is an integer, 1 highest through 99 lowest. Blank reads as `0`.
- **`Resources`, `ResourceGroups`, `Tags`** hold comma-separated lists.
- **`Custom1`–`Custom5`, `Notes`, `Tags`** have no length limit. Concatenate any extra
  fields from your source system into them to drive selection, filtering, and
  `style_rules` matching.
- **`ID`** is the identifier from your source system, stored in `source_id`. It is
  kept separate from the `events.id` primary key, which this application assigns.
  `Predecessors` and `Successors` reference `ID` or `WBS` values.
- **`WBS`** values should be unique across all projects; include a project identifier
  in the WBS structure to guarantee it.

### Accepted column names

Column names are matched ignoring case, spaces, underscores, hyphens, dots and
percent signs — so `EarlyStart`, `early_start`, `Early Start` and `earlystart` are
all the same column. The names below are the additional aliases on top of each
element's own name and the "Also accepted" column in the table above.

| Database column | Aliases |
| --- | --- |
| `name` | `name`, `task_name`, `title`, `task` |
| `source_id` | `id`, `guid`, `task_id`, `uid`, `unique_id` |
| `start_date` | `start`, `start_date`, `begin`, `begin_date`, `date` |
| `end_date` | `finish`, `end`, `end_date`, `finish_date`, `due`, `due_date` |
| `earliest_start_date` | `early_start`, `earliest_start`, `es_date` |
| `latest_start_date` | `late_start`, `latest_start`, `ls_date` |
| `earliest_end_date` | `early_finish`, `earliest_finish`, `earliest_end`, `ef_date` |
| `latest_end_date` | `late_finish`, `latest_finish`, `latest_end`, `lf_date` |
| `actual_start_date` | `actual_start` |
| `actual_end_date` | `actual_finish`, `actual_end` |
| `status` | `status`, `state` |
| `rollup` | `rollup`, `summary` |
| `percent_complete` | `percent_complete`, `complete`, `% complete` |
| `effort` | `work`, `effort` |
| `finish_variance` | `finish_variance`, `end_variance` |
| `resource_names` | `resources`, `resource`, `resource_names`, `assigned_to` |
| `resource_group` | `resource_groups`, `resource_group`, `group`, `team`, `department` |
| `notes` | `notes`, `note`, `description` |
| `color` | `color`, `colour`, `highlight_color` |
| `tags` | `tags`, `tag`, `marks`, `mark` |

> **Behaviour change.** `Summary` now maps to the **rollup** flag, matching the
> schedule data-element vocabulary where a summary task is a rollup. It previously
> mapped to the task name. If you have existing files that used `Summary` as the
> task name, rename that column to `Name` before re-importing.

`Status` is not part of the schedule element set but is read if present; see
[Event Status](#event-status) for the allowed values and how each renders. When the
column is absent or blank the row is stored as `active`.

### Round-tripping

`exportdata` writes the same column set the importer reads, so an export can be
edited and re-imported without loss. Times ride along inside the date columns as an
ISO `T` suffix, and durations export as the original text rather than the parsed
number.

```sh
uv run python ecalendar.py exportdata 20260101 20261231 -o events.csv
uv run python importers/import_events.py events.csv
```

### Import history and schema migration

Every run inserts a row in `import_history` (id, userid, filename, date, filehash,
command), and each imported event is tagged with that `import_id` — so `--replace`
and `--remove` target one batch without touching rows from other imports or
hand-edited entries. Import IDs are never reused.

On first run the importer brings an older `events` table up to the current schema
with a lazy `ALTER TABLE ... ADD COLUMN` per missing column. It is additive only:
existing rows and their data are untouched, and re-running is a no-op.

## Importing Special Days

Company special days (founders days, all-hands picnics, hack days, locale-specific observances) live in the `specialdays` table and are loaded with `importers/import_specialdays.py`. The importer mirrors `import_events.py` in shape: XLSX / XLS / CSV / TSV input, case-insensitive column aliasing, SHA-256 hashing for duplicate detection, and full `import_history` tracking.

```sh
# Import a single file
uv run python importers/import_specialdays.py SpecialDays/company.xlsx

# Re-import after editing the source (replaces the previous batch by file hash)
uv run python importers/import_specialdays.py SpecialDays/company.xlsx --replace

# Import every supported file in a directory
uv run python importers/import_specialdays.py SpecialDays/ --verbose

# Validate without writing
uv run python importers/import_specialdays.py SpecialDays/company.csv --dry-run

# Review what is already in import_history (with row counts per import)
uv run python importers/import_specialdays.py --list

# Drop a previous import and all of its rows
uv run python importers/import_specialdays.py --remove 15 --force
```

**Required columns:** `name` and at least one of `start_date` / `end_date`. A blank end date is auto-filled from start (and vice versa); a reversed pair is swapped.

**Accepted column aliases (case-insensitive):**

| Database column | Aliases |
| --- | --- |
| `name` | `name`, `title`, `special_day`, `holiday`, `event` |
| `startdate` | `start_date`, `startdate`, `start`, `begin`, `begin_date`, `date` |
| `enddate` | `end_date`, `enddate`, `end`, `finish`, `finish_date`, `due`, `due_date` |
| `company` | `company`, `org`, `organization` |
| `user` | `user`, `userid`, `user_id`, `owner` |
| `country` | `country`, `country_code` (default `US` via `--country`) |
| `language` | `language`, `lang` (default `en` via `--language`) |
| `notes` | `notes`, `note`, `description` |
| `icon` | `icon`, `icon_name` |
| `nonworkday` | `nonworkday`, `non_work_day`, `is_nonworkday`, `day_off` (default `0`) |
| `fullday` | `fullday`, `full_day`, `all_day` (default `1`) |
| `starthour` / `endhour` | `start_hour` / `end_hour`, `start_time` / `end_time` |
| `tags` | `tags`, `tag`, `marks`, `mark` |
| `daycolor` | `daycolor`, `day_color`, `color`, `colour`, `highlight_color` |
| `visible` | `visible`, `is_visible`, `show` (default `1`) |
| `pattern` / `patterncolor` | `pattern` / `pattern_id`, `pattern_color` |

Date formats accepted: `YYYY-MM-DD`, `M/D/YYYY`, `M/D/YY`, and any other format `dateutil` can parse. Booleans accept `true`/`false`, `yes`/`no`, `y`/`n`, `1`/`0`.

**Import history.** Every run inserts a row in the shared `import_history` table (id, userid, filename, date, filehash, command). Each imported `specialdays` row is tagged with the `import_id` from that record, so `--replace` and `--remove` can target a single batch without touching rows added by other imports or hand-edited entries.

**Schema migration.** On first run the importer adds an `import_id INTEGER` column to `specialdays` via a lazy `ALTER TABLE` (no-op if the column already exists). Existing rows without an `import_id` are left intact and are not affected by `--replace` or `--remove`.

## Theme System

A theme is one YAML file that declares how every visualization looks. The guiding rule is **declare it once**: the timescale (timebands and the tick patterns of an axis), the "today" line, palettes, fonts, holiday handling, numbered duration icons, lines and leaders are each stated in one place, and every view honours that single statement. A view's own block (`timeline:`, `gantt:`, `candybar:` ...) holds only what means something to that view alone — geometry, columns, lanes, ratios.

Two themes ship with the program:

- **`default.yaml`** — the default look. A theme may omit anything; a value it leaves out is the schema default.
- **`demonstration.yaml`** — every key a theme can set, with its default and the values it accepts, each preceded by a note. It is generated from the schema (`tools/generate_demonstration_theme.py`), so it cannot drift from what the program reads. Copy it, delete what you do not change, and you have a theme.

```bash
PYTHONPATH=. uv run python ecalendar.py themes                          # the built-in themes
uv run python ecalendar.py weekly 20260101 20260131 --theme default     # by name
uv run python ecalendar.py weekly 20260101 20260131 --theme config/themes/default.yaml     # by path
```

The theme loads before any command-line option is applied, so an explicit option always wins over the theme's value for the same setting.

### Strict loading

Only version-3.0 themes are read; a theme must say `theme: { name: ..., version: '3.0' }`. There is no converter and no inheritance (`extends:` and `unset:` are gone). The loader stops the run, with the key's path in the message, for:

- a theme of another version — `theme 'X' is not supported: ...`;
- an unknown or misplaced key — `theme key 'candybar.row_hight' is not supported inside 'candybar'; valid keys here: ...`;
- a value of the wrong type or out of range, a font that is not registered, a `style_rules` entry naming a role or selector that does not exist, an unknown column in `details`, or a glyph group the database does not have.

### The shape of a theme

```yaml
theme:        # name, version ('3.0'), description
fonts:        # family: the default font; any text role may name its own
text:         # text roles: heading, body, label, day_number, event_name, ... (font, size, color, opacity, align, size_by_paper)
boxes:        # box roles: default, cell, day, header, band, callout, event, milestone, duration (fill, stroke, pattern ...)
icons:        # icon roles: event, duration, milestone, missing, overflow (color, size, name)
lines:        # line roles: axis, tick, grid, separator, border, today, leader, connector, dependency, duration_bar, progress
palettes:     # month, fiscal, group, event (names or colour lists), plus explicit colour maps
timescale:    # axis, min_segment_width, and the rows of the primary and secondary stacks
today:        # show, date, label, line extent, highlight (the current day in a day box)
holidays:     # federal / company / weekend treatment, icons and dates
shading:      # month tint strength
week_numbers: # label format
fiscal:       # year start month, week start, label format, period colours
events:       # item_placement_order, date format, marker
durations:    # numbered icons, icon size, date labels, WBS grouping
continuation: # marks on durations clipped by the range
overflow:     # glyph marking a box that could not hold its contents
watermark:    # text or image
layout:       # page margins
details:      # the run's details document, icon files and event CSV
style_rules:  # conditional restyling of content (events, days)
weekly:, mini_calendar:, text_mini:, candybar:, timeline:, pit:, compact_plan:, blockplan:, gantt:, excelblockplan:
```

### Roles: text, boxes, icons, lines

A **role** is a named style, defined once and used wherever the program draws that kind of thing. Which role styles which `ec-*` element is fixed by [`config/element_catalog.yaml`](../config/element_catalog.yaml); a theme only says what each role looks like.

| Table | Role attributes |
|---|---|
| `text.<role>` | `font` (unset: `fonts.family`), `size`, `color`, `opacity`, `align` (`start` / `middle` / `end`), `size_by_paper` (e.g. `{letter: 10, 3x5: 6}`) |
| `boxes.<role>` | `fill`, `fill_opacity`, `fill_palette`, `stroke`, `stroke_width`, `stroke_opacity`, `stroke_dasharray`, `corner_radius`, `pattern`, `pattern_color`, `pattern_opacity` |
| `icons.<role>` | `color`, `size`, `name` (the default icon), `stroke_width`, `stroke_opacity` |
| `lines.<role>` | `color`, `width`, `opacity`, `dasharray`, `linecap`, `linejoin`, `marker_start` / `marker_end` (+ `_size`), `start_stub` / `end_stub`, `route` (`straight` or `curve`) |

Every line the program draws — the axis, a tick, a callout leader, a dependency arrow, the today line, a border — is one `lines` role with these attributes. `lines.leader_primary.color` and `lines.leader_secondary.color` recolour the leaders of labels on the two sides of an axis.

### Palettes

`palettes.month`, `palettes.fiscal`, `palettes.group` and `palettes.event` are each the name of a database palette (`ecalendar.py palettes`) or an inline list of colours. `palettes.month_colors` and `palettes.fiscal_period_colors` set individual colours (`"01"` ... `"12"`, `"01"` ... `"13"`) and win over the palette. `palettes.hash_lines` is the ink of day-box patterns. Colours are CSS names (`navy`) or `#rrggbb`; `none` is transparent.

### Timescale: one stack for every view

The timescale is the theme's single declaration of timebands. `timescale.primary` and `timescale.secondary` are lists of **rows**; a row divides the distance into day segments and groups them. Table views (blockplan, compactplan, gantt, Excel) draw the primary rows above the content and the secondary rows below; the axis views (timeline, pit) draw them on the two sides of the axis (above and below a horizontal axis, right and left of a vertical one); candybar draws its month row down the right of each strip (the first `month` row of `primary`); weekly, mini and text-mini take their fiscal period labels from the first `fiscal_period` row.

```yaml
timescale:
  heading_align: end              # start | middle | end — the row headings in table views
  min_segment_width: 3            # a row whose segments are narrower than this is dropped
  axis: { show: true, orientation: horizontal, padding: 4, marker_size: 7 }
  primary:
    - { unit: fiscal_quarter, label: Fiscal Quarter, format: 'Q{q}-FY{fy2}', height: 12 }
    - { unit: month, label: Month, format: MMMM, height: 12, tick: { length: 6, label_align: start } }
    - { unit: date,  label: Date,  format: D, height: 10, vline: { color: grey, width: 0.5 } }
    - { unit: holiday, label: Holidays, height: 10 }
  secondary: []
```

A row's `unit` is one of `date`, `dow`, `week`, `month`, `quarter`, `year`, `fiscal_quarter`, `fiscal_period`, `interval`, `countdown`, `countup`, `holiday`, `icon`. Besides `label`, `format`, `height` and `every` (show every Nth segment as one cell), a row can carry:

| Facet | Meaning |
|---|---|
| `fill`, `fill_palette`, `fill_opacity`, `border`, `text` | The cell's look; unset values come from `boxes.band` and `text.band_label` |
| `tick` | Draw it on an axis as a tick and a label (timeline, pit); table views ignore it |
| `vline` | A line down the content area at every segment boundary |
| `vfill` | A fill down the content area under every segment |
| `holidays` | For `unit: holiday` rows: `nonworkdays_only` (default true) |
| `end_format` | For `unit: fiscal_period` rows in weekly / mini: a second label on the period's last day |
| unit options | `week_start`, `fiscal_year_start_month`, `interval_days`, `prefix`, `start_index`, `max_index`, `anchor_date`, `reference_date`, `skip_weekends`, `skip_nonworkdays`, `label_values`, `icon_rules` |

A label wider than its cell is compressed to fit, never dropped. A view draws the rows its geometry can express and ignores the rest; a `fiscal_period` row has nothing to show — and is dropped — unless `--fiscal` supplies a fiscal calendar.

### Today, holidays, fiscal

- **`today`**: `show`, `date` (pin "today" to `YYYYMMDD`), `label`, `label_position`, `label_offset`, `length`, `direction`; the line is `lines.today` and its label `text.today_label`. `today.highlight` (`show`, `color`, `opacity`) fills the current day's box in weekly and mini views.
- **`holidays`**: `federal`, `company` and `weekend` each take `color`, `opacity` and an optional `icon`; every view tints those days the same way. `show_icons`, `icon_size`, `icon_color`, `icon_y_offset`, `show_dates`, `date_format`, `date_font_size` and `date_color` style the holiday marks on an axis.
- **`fiscal`**: `year_start_month`, `week_start`, `year_offset`, `use_period_colors`, `period_opacity` and `label_format` (the default template of fiscal labels; a `fiscal_period` row's own `format` wins).

### Durations, events and numbered icons

Any view can give each duration a numbered icon in place of the icon its event data names. `durations.replace_icons_with_numbers` (default `true`) is the one switch for every view; `durations.number_duration_icons` names the icon set (`ecalendar.py icons`; ignored when the switch is off). Durations are numbered in `events.item_placement_order`, and the run's details document lists each number beside its event. `durations.icon_size`, `icon_background_color`, `icon_stroke_color`, `stroke_dasharray`, `show_icons`, `wbs_group_depth`, `name_color` and `dates` (`show_start`, `show_end`, `format`, `font_size`, `color`) style duration labels everywhere; `events.date` and `events.marker` do the same for point events.

`events.item_placement_order` is a list of tokens (a field name, or a criteria mapping) that orders items wherever a view places them.

### Style rules: conditional restyling

Roles define the look; `style_rules` change it for the events or days a rule selects. A rule never defines anything.

```yaml
style_rules:
  - name: engineering work
    apply_to: [box:event, box:duration]      # <kind>:<role>, or a list
    select: { resource_group: engineering }  # which events or days
    style: { fill: steelblue }               # attributes of that role

  - name: critical names
    apply_to: text:event_name
    select: { priority_max: 1 }
    style: { color: crimson, size: 11 }

  - name: federal holiday hatching
    apply_to: box:day
    select: { federal_holiday: true }
    style: { pattern: diagonal-stripes, pattern_color: tomato, pattern_opacity: 0.12 }

  - name: dashed leaders for milestones
    apply_to: line:leader
    select: { milestone: true }
    style: { dasharray: '4 2' }
```

`style` holds attributes of the role named in `apply_to` (the tables above). Rules are applied in order and the last matching rule wins. On `box:event` and `box:duration`, `fill` is the event's colour (every view paints the event in it), so only a `stroke` there outlines an icon. `box:callout` and `line:leader` rules restyle one callout's box or leader (timeline, pit); a `text:<role>` rule restyles that text for the events or days it selects.

| `select` key | Matches |
|---|---|
| `federal_holiday`, `company_holiday`, `nonworkday`, `workday`, `weekend` | The day's class (`true` / `false`) |
| `date` | `YYYYMMDD`, a closed range `YYYYMMDD-YYYYMMDD`, or a list; with `date_overlap: true` a duration matches if its span overlaps |
| `task_name`, `notes`, `resource_names` | Substring, case-insensitive |
| `resource_group` | The whole group name, ignoring case |
| `wbs` | A WBS filter: comma-separated tokens, `!` excludes, `*` one segment, `**` the rest |
| `priority`, `priority_min`, `priority_max` | Exact value, or an inclusive range |
| `percent_complete` | A number or `{min, max}` |
| `milestone`, `rollup` | Flags |
| `event_type` | `event`, `duration` or `any` |
| `color`, `icon` | The event's own colour or icon, exactly |
| `min_match`, `any_event`, `all_events` | How many event criteria a day box needs, and whether any or all of its events must match |

An empty `select` matches everything. A rule that names a role or selector that does not exist is rejected when the theme loads.

### Glyph groups

Text-mini symbols and the mini calendar's day numbers can come from the database's `glyphs` table, a group per role. `text_mini.glyphs` names a group for `event`, `milestone`, `duration`, `holiday` and `nonworkday` symbols (defaults: the seeded `text-mini-*` groups), `duration_fill` (a one-glyph group), and optional `day_number_digits` and `week_number_digits` (ten glyphs). `mini_calendar.glyphs` names `day_number` (31 glyphs, one per day) and `day_number_digits`. An unset digit group uses the font's own digits. List the groups with `ecalendar.py glyphs`; a database without the table is told to run `tools/db/create_glyphs.py`.

### View blocks

Each view block holds structure only, for example:

| Block | Keys |
|---|---|
| `weekly` | `day_box` (hash pattern name, opacity, tile size and scale) |
| `mini_calendar` | `icon_set`, `title_format`, `show_adjacent`, `adjacent_month_*`, `circle_milestones`, `event_icon_scale`, `event_icon_opacity`, `grid_lines`, `month_outline`, `glyphs` |
| `candybar` | `row_height`, `cell_width`, `weeknum_col_ratio`, `month_col_ratio`, `week_start`, `suppress_weekends`, `show_week_numbers`, `max_rows_per_page`, `grid_lines`, `month_shading` |
| `timeline` | `label_side`, `duration_side`, offsets, `labella`, `events` and `durations` box sizing |
| `pit` | `label_side`, `leader_label_anchor`, `date_offset`, `date_placement`, `labella`, `label` padding and icon |
| `compact_plan` | bar line width, date column ratio, lane spacing, milestone flag size, legend texts |
| `blockplan` | column ratios, swimlanes, unmatched lane, lane label alignment, bar height and gap |
| `gantt` | table width, row heights, indent, bar height, `min_day_width`, `marks` (icon names), `columns`, `show_dependencies` |
| `excelblockplan` | `font_name`, `font_size`, `column_width` (Excel units and installed fonts) |

[`demonstration.yaml`](../config/themes/demonstration.yaml) lists every key of every block.

### Run details

Every run writes a details document, the icon files it uses and an event CSV beside the chart (see [The details document](#the-details-document)). The `details` block controls them:

| Key | Meaning |
|---|---|
| `details.markdown` | `enable`; `title_text`; `sections` (a list of `events`, `colors`, `symbols`, `exceptions`, `holidays`) and each section's heading text; `empty_exceptions_text`, `empty_cell_text`; `icon_mode` (`file`, `inline`, `none`); `color_mode` (`swatch`, `name`, `hex`); `group_by`; `sort`; `columns`, `exception_columns`, `holiday_columns` (lists of `{field, header, align, format, date_format, max_lines, indent}`; an unknown `field` is a load error) |
| `details.icons` | `enable`; `size` of every exported icon file |
| `details.csv` | `enable`; `columns` (`exportdata` or a column list); `render_columns` |

`--details-md` / `--no-details-md`, `--icons` / `--no-icons` and `--csv` / `--no-csv` override `enable` for one run.

### Swimlanes (blockplan)

`blockplan.swimlanes` declares the lanes in order. A lane's `match` decides which items it takes (`resource_groups`, `groups`, `resource_names_contains`, `task_contains`, `notes_contains`, `wbs_prefixes`, `milestone`, `rollup`, `event_type`, `priority`, `priority_min`, `priority_max`); `blockplan.lane_match_mode` is `first` (the first matching lane takes an item) or `all`. Per-lane styling:

| Key | When omitted |
|---|---|
| `name` (required; `\n` breaks the label) | — |
| `split_ratio` | `blockplan.lane_split_ratio`; `0.0` or `1.0` removes the events / durations divider |
| `fill_color` | the heading cell's `boxes.header` fill |
| `timeline_fill_color` | `none` |
| `label_color` | `text.swimlane_label` colour |
| `label_align_h`, `label_align_v` | the block's alignment |
| `label_rotation` | `blockplan.lane_label_rotation` |

`blockplan.show_unmatched_lane` and `unmatched_lane_name` control the lane for items no lane matches.

### Creating a theme

1. Copy `config/themes/demonstration.yaml` (or start from `default.yaml`).
2. Keep only the keys you want to change — everything else is the schema default.
3. Run any view with `--theme path/to/mytheme.yaml`; a mistake names the key and what is valid there.
4. Compare with `--trace-style`, which prints for each day and event which `style_rules` applied and what each overrode.

Fonts, patterns, palettes, colours and icons are listed by the discovery commands:

| Resource | List command | Preview command |
|---|---|---|
| Fonts (~125 registered) | `ecalendar.py fonts` | `ecalendar.py fontsheet [-f NAME]` |
| Patterns (~350 in DB) | `ecalendar.py patterns` | `ecalendar.py patternsheet [-f NAME]` |
| Named colors | `ecalendar.py colors` | `ecalendar.py colorsheet [-f NAME]` |
| Palettes (~600 in DB) | `ecalendar.py palettes` | `ecalendar.py palettesheet NAME` |
| Icons | `ecalendar.py icons` | `ecalendar.py iconsheet [-f NAME]` |
| Glyph groups | `ecalendar.py glyphs` | — |

### CSS element catalog

Every SVG element carries a semantic CSS class, and the SVG embeds a stylesheet built from the theme's roles. The authoritative list — which role styles which class — is [`config/element_catalog.yaml`](../config/element_catalog.yaml); a CI test keeps it in step with the renderers. Modifier classes added beside an element class: `ec-holiday`, `ec-nonworkday`, `ec-current-day`, `ec-adjacent`.

### External CSS overrides

Because every element has a class, CSS applied when an SVG is embedded in HTML restyles it:

```css
.ec-event-name { fill: darkblue; }
.ec-grid-line { stroke: none; }
```

Classes drawn with inline styles (the PIT markers, leaders and boxes) need `!important`; see the PIT section.

### Continuation icons

When a duration runs past the start or end of the range, the view clips the bar and draws `continuation.icon_before` / `icon_after` (a name, or a list tried in order) at `continuation.icon_height` and `continuation.icon_color`, unless `continuation.show` is false.

### Notes

- Paper-size-dependent text is `size_by_paper` on a text role.
- `layout.margin.*` accepts numeric points or values with units such as `0.5in` and `10mm`. A side set in the theme applies to every render with that theme.
- Run `ecalendar.py help <subcommand>` for allowed values and focused help output.
- Run `ecalendar.py` from the project root. Font files are located relative to it, so SVG views fail with a font error when run from another directory.

---

## PIT (Points in Time) Subcommand

The `pit` subcommand generates a clean **Points-in-Time** SVG: a single axis line with one marker per event, connected by a labella-spaced bezier leader to a non-overlapping label box. It is the lightest-weight timeline style — no duration bars, no fiscal bands, no WBS hierarchy — designed for milestone charts, roadmaps, and presentation decks where clarity trumps density.

### Visual aesthetic

A single horizontal (or vertical) axis spans the project date range. Each event appears as a marker (filled circle, diamond, or DB icon glyph) on the axis, with a curved leader rising to a labeled box on the primary or secondary side. The box holds the event name, optional notes, and (by default) the date — see `pit.date_placement` to move the date onto the axis or hide it. An optional "today" line crosses the axis as a perpendicular dashed rule.

### Usage examples

```bash
# Horizontal, both-side labels, default theme (landscape page)
uv run python ecalendar.py pit 20260101 20261231 \
  --orientation landscape --direction horizontal \
  --outputfile output/pit_2026.svg

# Vertical poster, milestones only
# (the axis uses the built-in diamond for each milestone; set icons.milestone.name for an icon in the label box.)
uv run python ecalendar.py pit 20260101 20261231 \
  --orientation portrait --papersize tabloid \
  --direction vertical \
  --milestones \
  --outputfile output/pit_milestones_2026.svg

# Fiscal calendar, includes notes (add a fiscal_quarter tick row to timescale.primary and lines.leader.dasharray in the theme)
uv run python ecalendar.py pit 20260101 20271231 \
  --fiscal "4-5-4" \
  --includenotes \
  --outputfile output/pit_program.svg

# Future-dated "today" line: set today.date / today.label in the theme
uv run python ecalendar.py pit 20260101 20261231 \
  --outputfile output/pit_q3_presentation.svg

# Custom themed output, vertical direction
uv run python ecalendar.py pit 20260101 20261231 \
  --theme my_theme.yaml --direction vertical \
  --outputfile output/pit_custom.svg
```

### Inherited content-filter flags

These flags are shared with other visualizers and apply identically to `pit`:

| Flag | Short | Description |
|---|---|---|
| `--noevents` | `-ne` | Exclude regular (non-milestone) events |
| `--milestones` | `-ms` | Include milestone events |
| `--includenotes` | `-in` | Render the Notes field as a second label line |
| `--WBS` | | WBS filter expression (prefix-based, comma-separated, `!` excludes) |
| `--empty` | `-e` | Render with no events (blank axis) |
| `--status` | | Event status filter (active, draft, cancelled, on_hold, all) |

Multi-day duration events are **always dropped** — PIT renders only point-in-time events and milestones. Use the `timeline` subcommand for durations.

### PIT-specific flags

| Flag | Short | Default | Description |
|---|---|---|---|
| `--direction` | | `horizontal` | Axis direction: `horizontal` or `vertical` (the theme's `timescale.axis.orientation`; distinct from `--orientation`, which rotates the page). |

All other PIT styling is theme-only. PIT reads the shared declarations like every axis view, plus its own `pit:` block:

| Theme key | Default | Description |
|---|---|---|
| `timescale.primary` / `secondary` | | Rows with a `tick:` facet draw ticks and labels on the matching side of the axis; other rows are bands at the page edges; a `holiday` row draws flag marks with their dates |
| `timescale.axis` | | `show`, `orientation`, `padding`, `marker_size` (the built-in dot) |
| `lines.axis`, `lines.leader`, `lines.leader_primary` / `lines.leader_secondary`, `lines.today` | | Axis, leaders (with a colour per side) and the today line, including markers, dashes and stubs |
| `today` | | `show`, `date`, `label`, `label_position` |
| `boxes.callout` | | The label box: fill, stroke, corner radius, `pattern`; `fill_palette` cycles a palette through the labels |
| `text.event_name`, `event_notes`, `event_date` | | Label text |
| `icons.event`, `icons.milestone` | | Marker colours and the default icon (`name`) drawn in a label box |
| `pit.label_side` | `both` | `primary`, `secondary` or `both` |
| `pit.date_placement` / `pit.date_offset` | `inline` / `6.0` | Where each event date is drawn: `inline` (in the box), `axis`, or `none`; and its distance from the label |
| `pit.leader_label_anchor` | `center` | Where the leader meets the box: `center`, `start` or `end` |
| `pit.labella.layer_gap` / `node_height` / `density` | `50` / `24` / `0.5` | Label placement; `layer_gap` is the leader length |
| `pit.label` | | `padding_x`, `padding_y`, `icon_size`, `icon_gap` |

A rule aimed at `line:leader` or `box:callout` restyles one event's leader or label box (see [Style rules](#style-rules-conditional-restyling)).

### `ec-pit-*` CSS classes

The following CSS classes are emitted on PIT SVG elements for external stylesheet targeting:

| Class | Element |
|---|---|
| `ec-pit-axis-group` | `<g>` wrapping the axis line and ticks |
| `ec-axis-line` | The axis `<line>` element |
| `ec-pit-callout-group` | `<g>` wrapping all elements for one event |
| `ec-pit-side-primary` | Added to the callout group for primary-side events |
| `ec-pit-side-secondary` | Added to the callout group for secondary-side events |
| `ec-callout-leader` | `<g>` wrapping the leader `<path>` |
| `ec-callout-box` | The label box `<rect>` |
| `ec-pit-event-marker` | Non-milestone marker glyph or shape |
| `ec-milestone-marker` | Milestone marker glyph or shape |
| `ec-event-name` | Label name text `<g>` |
| `ec-event-notes` | Label notes text `<g>` (present only when `--includenotes`) |
| `ec-event-date` | Opposite-side date text `<g>` |
| `ec-today-line` | The today `<line>` element |
| `ec-today-label` | The today-line label text `<g>` |
| `ec-pit-marker-arrow-head` | Built-in `<marker>` elements in `<defs>` |
| `ec-pit-label-pattern` | Pattern overlay `<rect>` on a label box |

Each callout group also carries `data-*` attributes for JavaScript filtering:
- `data-event-date` — YYYYMMDD string
- `data-milestone` — `"true"` / `"false"`
- `data-priority` — integer priority value
- `data-groups` — resource group string

### External CSS styling guide

The four **inline-styled** classes — `ec-pit-event-marker`, `ec-milestone-marker`, `ec-callout-leader`, `ec-callout-box` — carry their fill/stroke as inline `style="..."` attributes so per-event theme colors are always honored. To override them from an external stylesheet you **must** use `!important`:

```css
/* Override all event markers to a flat blue */
.ec-pit-event-marker {
  fill: #2d5fae !important;
}

/* Target only primary-side leaders */
.ec-pit-side-primary .ec-callout-leader path {
  stroke: royalblue !important;
  stroke-dasharray: 4 2 !important;
}

/* Style all label boxes */
.ec-callout-box {
  fill: lavender !important;
  fill-opacity: 0.9 !important;
  stroke: steelblue !important;
}
```

All other `ec-*` classes use presentation attributes (not inline style), so a plain CSS rule (without `!important`) is sufficient to override them.

### Hard limitations

- **No multi-day events.** Duration events are silently dropped. Use the `timeline` subcommand for durations and duration bars.
- **80-events-per-side soft cap.** Above 80 events on a single axis side, labella's Force algorithm may not converge cleanly. A `WARNING` is logged and the SVG is still produced, but label spacing may be suboptimal. Split the date range or use `--WBS` / `--milestones` filtering to reduce density.
- **No fiscal bands, WBS groups, or icon bands.** These are supported by `timeline` and `blockplan`; PIT intentionally omits them for visual clarity.

---

## Gantt Subcommand

The `gantt` subcommand generates a classic **Gantt chart**: a task table on the left, a
date-scaled plotting area on the right, and one row per task running across both. It is
the densest of the plan views — where `blockplan` groups work into swimlanes and
`compactplan` packs durations around a single axis, `gantt` keeps one task per row and
adds the three things a schedule review needs: **dependencies**, **progress**, and the
**schedule window** (earliest/latest dates).

### Page anatomy

```
┌──────────────────────────────────────────────────────────────┐
│ header                                                       │
├───────────────────────┬──────────────────────────────────────┤
│                       │ top time bands (month / week / …)    │
├───────────────────────┼──────────────────────────────────────┤
│ column headers        │                                      │
├───────────────────────┼──────────────────────────────────────┤
│ task table            │ bars, milestones, arrows              │
│ (one row per task)    │ over non-working-day shading         │
├───────────────────────┼──────────────────────────────────────┤
│                       │ bottom time bands                    │
├───────────────────────┴──────────────────────────────────────┤
│ footer                                                       │
└──────────────────────────────────────────────────────────────┘
```

Every run also writes a [details document](#the-details-document) — see
[What the details document reports](#what-the-details-document-reports) below.

### Usage examples

```bash
# Six-month chart with the default theme
uv run python ecalendar.py gantt 20260202 20260731 -of gantt_h1.svg

# One programme only, using the WBS filter, with notes in the task rows
uv run python ecalendar.py gantt 20260202 20260731 --WBS NP --includenotes -of nimbuspay.svg

# Show weekends as shaded columns instead of removing them from the axis
uv run python ecalendar.py gantt 20260202 20260430 --weekends 1 -of gantt_7day.svg

# Milestones only, on a wide sheet
uv run python ecalendar.py gantt 20260101 20261231 --milestones -th default -ps Tabloid --orientation landscape -of milestones.svg

# Drop single-day events; keep the multi-day bars
uv run python ecalendar.py gantt 20260202 20260731 --noevents -of gantt_bars.svg

# Fiscal-quarter aware run against the NRF 4-5-4 retail calendar
uv run python ecalendar.py gantt 20260202 20260731 --fiscal nrf-454 -of gantt_fiscal.svg
```

### The task table

Columns are theme configuration, not styling: the `gantt.columns` list decides which
fields appear, in what order, and how each behaves. `style_rules` then decide how the
resulting cells *look*.

| Key | Meaning |
|---|---|
| `field` | Column from the `events` table — `name`, `start_date`, `end_date`, `wbs`, `notes`, `source_id`, … — or the synthetic `link_ref` (cross-page dependency numbers) |
| `header` | Heading text (defaults to `field`) |
| `width` | Share of the table width. Widths are renormalized, so any scale works |
| `align` | `left` (default), `center`, `right` |
| `max_lines` | Wrap up to this many lines, then truncate with an ellipsis |
| `truncate` | Truncate rather than overflow (default true) |
| `render` | `text` (default) or `icon` — an icon column draws a glyph when the value is truthy |
| `icon` | Icon name for an `icon` column (defaults per field, e.g. `check` for `rollup`) |
| `format` | Python format spec, e.g. `'{:.0%}'` for `percent_complete` |
| `date_format` | Arrow format string, plus the `dd` two-letter weekday token (`dd MM/DD/YY` → `Mo 02/02/26`) |
| `indent` | Shift this column's text by the row's WBS depth |

The default set leads with `link_ref` (see
[Dependencies](#dependencies)) and then the sixteen columns the requirements call for:
`source_id`, `name`,
`status`, `priority`, `wbs`, `rollup`, `milestone`, `percent_complete`, `effort`,
`duration`, `start_date`, `end_date`, `resource_names`, `resource_group`, `notes`,
`deadline`. Effort and duration render the **text** the source system exported
(`"10 days"`), not the parsed decimal — the numeric columns exist for arithmetic.

Row height is fixed and uniform: a value too long for its column loses characters, never
pushes the row taller.

**Ordering and indentation.** Rows sort by WBS then start date, comparing WBS segments
numerically — so `1.10` follows `1.9` rather than `1.1`. Tasks with no WBS form a second
block after every numbered task, ordered by start date. Indentation comes from WBS depth,
so `3.1.2` sits two levels in. No parent rows are invented: a level appears only when the
schedule actually contains that task.

### Weekends and non-working days

The `--weekends` style decides the shape of the axis, not just its shading:

| `--weekends` | Effect on the chart |
|---|---|
| `0` (default) | Saturday and Sunday are **removed from the axis entirely**. Bars span the working days they actually cover, and a five-day task is five columns wide regardless of which weekend it crosses |
| `1`–`4` | Every day gets a column; non-working days are shaded behind the bars |

Country holidays are always columns and always shaded, so adding `--country` never
changes the width of the chart. The one casualty is a holiday that falls on a hidden
weekend — it has no column to shade, so it is reported in the details document instead.

A single-day event landing on a hidden weekend is drawn on the **next working day** with a
marker icon (`arrow-left-circle` by default), and likewise reported.

### Dependencies

Arrows come from the `events.predecessors` column and resolve against `events.source_id`
— the identifier your scheduling tool assigned, not EventCalendar's own row id. The
MS Project grammar is supported:

```
12            → finish-to-start on task 12, no lag
12FS+3d       → finish-to-start, three days' lag
7SS,9FF-2d    → two predecessors: start-to-start on 7, finish-to-finish on 9 less two days
15FS+50%      → percentage lag
15FS+3ed      → elapsed (calendar) days
```

Each arrow leaves and enters the bar edges its link type implies — `FS` right-to-left,
`SS` left-to-left, `FF` right-to-right — which keeps overlapping work reading correctly
instead of as backward arrows. Lag is parsed and stored but does not currently offset the
arrow geometry.

Arrows are drawn as **curved leaders**, the same construction the `pit` view uses for its
callout leaders: a short perpendicular stub off the bar edge, a cubic bezier across the
gap, and a matching stub into the target — the stubs are what stop the curve cusping
where it meets a bar. The arrowhead is an SVG marker with `orient="auto"`, so it points
along the curve's tangent rather than being fixed horizontally. `gantt.arrow_marker_end`,
`arrow_marker_end_size`, `arrow_linecap` and `arrow_linejoin` tune it.

**Links the pagination breaks.** When a link's two ends land on different pages the arrow
cannot be drawn, so the link is *numbered* instead and the number appears at both ends:

* on the page holding the source event, one stub arrow leaves its bar and ends in a
  numbered icon — one stub however many successors it could not reach;
* on the page holding each unreachable successor, the same icon appears in the
  **reference column**, the left-most column of the task table.

So ⑦ beside a stub on page 1 is the same link as ⑦ in the reference column on page 3.
Numbers are drawn from `circle-1`…`circle-100`, then `darkcircle-`, then `square-` —
300 references before numbering degrades. All of them are listed in the details document's Exceptions table with
their icon name.

A reference matching **no** task, or a predecessor cell that cannot be parsed, has no far
end to number: it keeps an unnumbered `crosssquare` stub. The rule is
*numbered ⇒ the other end is somewhere in this document; unnumbered ⇒ it is not.*

If your export has no predecessor data, no arrows are drawn and nothing else changes.

### Bars, progress, and the schedule window

| Element | Drawn from | Notes |
|---|---|---|
| Duration bar | `start_date` → `end_date` | Single-day events are one column wide |
| Progress line | `percent_complete` | Measured against the **working-day** span, so it lines up with the drawn bar; black by default |
| Float bars | `earliest_start_date`, `latest_start_date`, `earliest_end_date`, `latest_end_date` | Same color as the bar at reduced opacity; omitted entirely when the dates are absent |
| Rollup bracket | `rollup` rows | A downward-facing bracket over the row's own dates; no progress line or float bars. Omitted when the row has no dates — children are never consulted |
| Milestone | `milestone` rows | A filled diamond anchored on `end_date` |
| Deadline | `deadline` | A themed icon in the task's row |
| Continuation icon | bars crossing `START_DATE` / `END_DATE` | Drawn inside the clipped edge, and reported in the details document |
| Today line | wall clock, or `gantt.today_date` | Same semantics as the `pit` view: suppressed when outside the range |

### Stacking the timescale

The gantt draws the theme's shared `timescale`: `timescale.primary` rows above the chart, `timescale.secondary` rows below, each at its own `height`, drawn in the order listed. A row's `label` is written in a heading cell in the task table's column, level with its row (leave it empty for no heading), and `every: N` draws every Nth segment as one cell, labelled by its first. `timescale.heading_align` (`start`, `middle` or `end`) aligns every heading.

```yaml
timescale:
  primary:
    - { unit: fiscal_quarter, label: Quarter, format: 'Q{q}-FY{fy2}', height: 12 }
    - { unit: month,          label: Month,   format: MMMM,            height: 12 }
    - { unit: week,           label: Week,    format: 'W{n}',          height: 10 }
    - { unit: dow,            label: DoW,     format: dd,              height: 9 }
  secondary:
    - { unit: date, label: Date, format: D, height: 9 }
```

Weekend and holiday columns are tinted from `holidays`; a row's `vline` and `vfill` draw lines and fills down the chart at its segment boundaries.

If the two stacks plus the column-header row together want more than 75% of the content
height, every chrome row is scaled down in proportion — no row is dropped for height, and the task
body always keeps positive height.

### Pagination

The chart splits across pages on both axes when it does not fit:

- **Vertically**, when there are more rows than the page height allows. Every page repeats
  the column headers and the full timescale.
- **Horizontally**, when a day column would fall below `gantt.min_day_width` (4 pt by
  default; set it to `0` to fit any range onto one page, however thin the columns). Every
  page repeats the task table, and the timescale *continues* rather than restarting — week
  48 is followed by week 49, not by week 1. A page ends before a segment that would fit a page is cut, so pages are a little shorter than the full width; a segment longer than a page is clipped on every page it crosses, its label repeated.

Pages run row-major, so following one task's bar across the date range means turning
consecutive pages. Continuation files are named `<output>_p2.svg`, `<output>_p3.svg`, and
so on.

### What the details document reports

The run's [details document](#the-details-document) lists every task, with the
`page` its row is on and the cross-page `ref` icons it carries, and, under
**Exceptions**, one line per item the chart could not show faithfully:

| Reported | Why |
|---|---|
| Bar begins before the start of the range | Clipped to the first column |
| Bar continues past the end of the range | Clipped to the last column |
| Moved to the next working day | Single-day event on a hidden weekend |
| Holiday hidden with its weekend | No column exists to shade |
| Not drawn — every day of the span is hidden | A multi-day task falling entirely on hidden days |
| Predecessor is not on the chart | Filtered out or on another page |
| Predecessor does not match any task | No task carries that `source_id` |
| Predecessor could not be parsed | The cell's syntax was not understood |

A cross-page dependency's numbered icon is in the Ref column. A column list written
for `gantt.columns` pastes into `details.markdown.columns` unchanged, to list the
tasks exactly as the chart's own table does.

### Inherited content-filter flags

These flags are shared with the other plan views and apply identically to `gantt`:

| Flag | Short | Description |
|---|---|---|
| `--noevents` | `-ne` | Exclude single-day events |
| `--nodurations` | `-nd` | Exclude multi-day durations |
| `--milestones` | `-mo` | Show only milestones |
| `--includenotes` | `-notes` | Show notes with event names |
| `--WBS` | | WBS filter expression (comma-separated, `!` excludes) |
| `--status` | | Event status filter (`active` by default; `all` for everything) |
| `--weekends` | `-w` | Weekend style 0-4 (see above) |
| `--country` | `-cc` | Country code(s) for government holidays |
| `--empty` | `-e` | Render the frame and timescale with no tasks |

A filtered-out task stops being a link target as well as a row: its dependents draw the
off-chart stub instead of an arrow.

### Theme reference

Gantt structure lives under `gantt:`; its decoration is the shared declarations. [`config/themes/demonstration.yaml`](../config/themes/demonstration.yaml) lists every key.

| Key | Default | Purpose |
|---|---|---|
| `gantt.table_width_ratio` | `0.38` | Task table's share of the content width |
| `gantt.row_height` | `14.0` | Fixed row height |
| `gantt.header_row_height` | `18.0` | Column-header row height |
| `gantt.indent_per_level` | `8.0` | Points of indent per WBS level |
| `gantt.bar_height` | `8.0` | Duration-bar thickness |
| `gantt.min_day_width` | `4.0` | Split the range across pages below this; `0` disables |
| `gantt.columns` | 17-column set | The task table: `field`, `header`, `width`, `align`, `max_lines`, `wrap`, `truncate`, `render` (`text` or `icon`), `icon`, `format`, `date_format`, `indent`. Unset widths take the average of the columns that set one |
| `gantt.marks` | | Icon names: `milestone`, `deadline`, `rollup`, `milestone_flag`, `snapped_event` (an event moved off a hidden weekend), `offchart_dependency` (a predecessor nowhere in the chart), `link_ref_icon_families`, `link_ref_family_size`, `link_ref_max_icons` |
| `gantt.float_opacity_scale` | `0.4` | Float-bar opacity, relative to the bar |
| `gantt.show_dependencies` | `true` | Draw dependency arrows |
| `timescale.*` | | The rows above and below the chart |
| `lines.dependency` | | Arrow color, width, `marker_end`, `marker_end_size`, `linecap`, `linejoin`, `dasharray` |
| `lines.progress` | | The percent-complete line |
| `boxes.duration` | | Bar fill and stroke when no rule or event color applies |
| `today`, `lines.today`, `text.today_label` | | The today line (pin the day with `today.date`) |
| `continuation.icon_after` / `icon_before` | | Bar clipped at a range edge |

Bars, milestones and arrows are styled through `style_rules` like every other element:

```yaml
style_rules:
  - name: critical-path bars in red
    apply_to: box:duration
    select: { priority_max: 1 }
    style: { fill: crimson, fill_opacity: 0.8 }
  - name: dependency arrows into delivery
    apply_to: line:dependency
    select: { resource_group: Delivery }
    style: { color: navy, width: 1.0, opacity: 0.85 }
```

The `ec-*` classes the Gantt emits — usable from an external stylesheet — are
`ec-column-header`, `ec-task-cell`, `ec-row-band`, `ec-duration-bar`, `ec-progress-line`,
`ec-float-bar`, `ec-rollup-bracket`, `ec-dependency-arrow`, `ec-milestone-marker`,
`ec-band-cell`, `ec-tick-label`, `ec-today-line`, and `ec-grid-line`.

## ExcelBlockplan Subcommand

The `excelblockplan` subcommand generates an Excel workbook (`.xlsx`) containing timeband rows in the top rows of a worksheet, a fixed column-header row, and one row per event or duration in the date range. The column layout and data-row behavior are described under [`excelblockplan`](#excelblockplan) in Positional Arguments.

An empty spreadsheet can be generated by using the `--empty` filter: the workbook keeps its timeband and column-header rows (with holiday shading and vertical lines) but has no event or duration rows, so it can be used as a ready-to-fill project planning template.

### Usage

```bash
ecalendar.py excelblockplan START_DATE END_DATE [options]
ecalendar.py excelblockplan 20260101 20260630 --theme default --weekends 0 --country US
ecalendar.py excelblockplan 20260101 20260630 --theme default --empty -of template.xlsx
```

### Options

| Flag | Short | Default | Description |
|---|---|---|---|
| `--outputfile` | `-of` | `output/ExcelBlockplan.xlsx` | Destination `.xlsx` path |
| `--theme` | `-th` | none | Theme name or `.yaml` path |
| `--weekends` | `-we` | `0` | Weekend style (0 = workweek only, 1–4 = include weekends) |
| `--weekend-days` |  | — | Comma-separated ISO weekday list (`0=Mon..6=Sun`) overriding the implicit Sat/Sun pair |
| `--country` | `-cc` | US, CA | ISO 3166-1 alpha-2 country code(s) for government holidays. Comma-separated (e.g. `US,CA,GB`) for multi-country merging. |
| `--empty` | `-e` | — | Empty spreadsheet: header rows only, no event or duration rows |
| `--noevents` / `--nodurations` | `-ne` / `-nd` | — | Leave out single-day events / multi-day durations |
| `--milestones` | `-mo` | — | Only milestone rows |
| `--WBS` |  | — | WBS filter expression |
| `--status` |  | `active` | Event statuses to include (`all` for no filter) |
| `--database` | `-db` | `calendar.db` | SQLite database path |
| `--verbose` | `-v` | — | Increase verbosity (`-v`, `-vv`, `-vvv`) |
| `--trace-style` | — | — | Theme trace to stderr: for each day, event and duration, which `style_rules` applied, what each overrode (`was X from rule 'name'`), which were skipped and why, and the final result |
| `--quiet` | `-q` | — | Suppress output path echo |

### Workbook Layout

```
Columns A–AS : one label column per events-table field, in schema order
Column  AT   : continuation marker for durations running past the visible range
Columns AU+  : one column per visible calendar day (width = 3 characters)
Rows 1..N    : timeband rows — one per row of timescale.primary
Row  N+1     : column-header row with the label names
Rows N+2..   : one row per event/duration, ordered by start date (none with --empty)
```


### Timeband Configuration

The workbook draws the theme's shared `timescale`, in Excel units: each row of `timescale.primary` becomes a header row above the column headers, and the `timescale.secondary` rows are appended after the last data row (after the column headers when there are no events). A row's `height` is the Excel row height in points, `label` is written in the last label column, and `every` merges every Nth segment. A row's `vline` becomes a right-hand cell border on its segment boundaries (see below).

```yaml
timescale:
  primary:
    - { unit: fiscal_quarter, label: Quarter, format: 'FY{fy2} Q{q}', height: 18, vline: { color: red, width: 1.5 } }
    - { unit: month,          label: Month,   format: MMM,            height: 18, vline: { color: navy, width: 2.0 } }
    - { unit: date,           label: Day,     format: D,              height: 18 }
```

Every `unit` is supported. Icon rows (`unit: icon`) write a colored bullet (●) in each day cell where a matching event exists, matched by the row's `icon_rules` (`milestone`, `task_contains`, `icon`, `color`):

```yaml
timescale:
  primary:
    - unit: icon
      label: Events
      height: 14
      icon_rules:
        - { milestone: true, icon: diamond, color: "#4472C4" }
        - { task_contains: Release, icon: star, color: "#E74C3C" }
```

### Excel Font Settings

The workbook's fonts are Excel's, not the ecalendar font registry's, so they have their own block (system-installed font names, sizes in points):

```yaml
excelblockplan:
  font_name: "Calibri"   # default font for all cells
  font_size: 9           # default font size in points
  column_width: 3.2      # day-column width in Excel character units (default 3)
```

### Holiday Decoration

Each visible day column is checked against government holidays (via the `holidays` Python package) and company special days in the database:

- **Federal/government holidays** — background shaded with `holidays.federal.color` from the theme; the cell displays a country flag emoji (e.g. 🇺🇸 for US).
- **Company non-workdays** — background shaded with `holidays.company.color` from the theme; the cell displays 🏢.

Holiday shading is applied in:
- **Date/dow band cells** — the individual day segment cell is shaded and its label replaced with the emoji.
- **Column-header row** — holiday columns are shaded.
- **Data rows** — holiday columns are shaded in every event/duration row; where a cell already carries an event icon or duration colour, the holiday colour is combined with it as an Excel `lightUp` pattern so both stay visible.

### Vertical Lines → Cell Right Borders

A timescale row's `vline` is written as a right-side border on the last column of each of its segments. The border is applied to the column-header row and to the data-row day cells that carry an event, a duration or holiday shading. Style: `medium` (width > 1.5 pt) or `thin` (≤ 1.5 pt); the color is the line's `color`.
