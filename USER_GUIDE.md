# EventCalendar User Guide

> **For developers:** architecture docs live in
> [ARCHITECTURE.md](ARCHITECTURE.md) (reading order, diagrams) and
> [CONTRIBUTING.md](CONTRIBUTING.md) (working practices, vocabulary).
> The examples in this guide are executable — verify them with
> `uv run python tools/check_user_guide.py`.

This guide is generated from the current codebase (`ecalendar.py`, `config/theme_engine.py`, `config/config.py`) and reflects the exact implemented CLI/theme surface.

## Textual UI (interactive terminal app)

Prefer a guided interface over typing flags? Launch the Textual UI:

```sh
uv run python -m tui                 # uses calendar.db in the project root
uv run python -m tui -db other.db    # point at a different database
```

The UI is a thin front end over the same CLI documented below — it introspects
`ecalendar.py`'s argument parser, builds the exact `uv run ecalendar.py …`
command, and runs it for you. Nothing in the rendering pipeline is bypassed or
reimplemented, so any flag in this guide is available in the UI, and a live
command bar always shows the command being assembled (copyable, so you can
graduate to the shell at any time).

**Home** has three columns:

- **Calendar views** — `weekly`, `mini`, `mini-icon`, `candybar`, `text-mini`,
  `timeline`, `pit`, `blockplan`, `gantt`, `compactplan`, `excelheader`,
  `excelblockplan`, `exportdata`.
- **Reference sheets / listings** — the `*sheet` previews plus `themes`,
  `papersizes`, `patterns`, `icons`, `colors`, `palettes`, `fonts`.
- **Data** — the **Import Hub** (see below).

**Builder** (open a view with **Enter**): a tabbed form whose tabs mirror the
CLI argument groups — Output, Layout, Header/Footer, Watermark, **Content
Filtering**, Fiscal, Week Number, Logging. Each field is generated from the
parser, so its help text is the same as `--help`. Pickers for `--theme`,
`--papersize`, fonts, icons, colors, and patterns are populated from the same
database/registry the engine uses, so the choices never drift. The **Dates** tab
has `begin`/`end` inputs with quick presets (this year / quarter / month, next 90
days). Press **Ctrl+R** to run; output streams live and the rendered file path is
printed at the end.

**Import Hub** (press **i**, or pick the Data column): one wizard per data type —
**Events**, **Special days**, **Holidays**, and **Content** (icons / patterns /
colors). Events, special days, and holidays share one wizard since they share a
grammar; the Events wizard exposes the full `import_events.py` surface, including
generator mode (`--generate` with `--start-date` / `--end-date` / repeatable
`--param KEY=VALUE`). Every importer defaults to a **dry run** so you can validate
before writing: **Ctrl+D** dry-runs, **Ctrl+R** imports.

Global keys: **Esc** goes back, **q** / **Ctrl+Q** quits, **d** toggles
dark/light. The UI adds the `tui/` package and the `textual` dependency; it makes
no changes to `ecalendar.py` or the importers. See [tui/README.md](tui/README.md)
for the module-level architecture.

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
| `gantt` | Generate a Gantt chart SVG: task table on the left, timescale on the right, with duration bars, percent-complete lines, milestones, rollup brackets and dependency arrows. Also writes a companion `_details.svg` listing every task plus anything the chart could not show faithfully. |
| `compactplan` | Generate a compressed activities timeline SVG showing durations as colored lines above/below a central axis, grouped by resource group. |
| `excelheader` | Generate an `.xlsx` workbook with timeband header rows and a project-planning template. |
| `excelblockplan` | Generate an `.xlsx` workbook with the same timeband header rows as `excelheader` plus one row per event/duration in the range (with style-rule decoration and holiday overlays). |
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

## Common Workflows

```bash
# Weekly calendar for a date range
PYTHONPATH=. uv run python ecalendar.py weekly 20260101 20260131 -th corporate -of weekly.svg

# Mini calendar with week numbers and details page
PYTHONPATH=. uv run python ecalendar.py mini 20260101 20261231 --weeknumbers --mini-details -of mini.svg

# Mini-icon calendar with squircle day-number icons, 4 columns, landscape
PYTHONPATH=. uv run python ecalendar.py mini-icon 20260101 20261231 -mis squircles --mini-columns 4 -o landscape -of mini_icon.svg

# Candybar vertical year-strip for a full year
PYTHONPATH=. uv run python ecalendar.py candybar 20260101 20261231 -th corporate -of candybar.svg

# Candybar with weekends suppressed and vertical (rotated) month names
PYTHONPATH=. uv run python ecalendar.py candybar 20260101 20261231 --candybar-suppress-weekends --candybar-month-rotation -90 -of candybar.svg

# Timeline with custom today-line styling
PYTHONPATH=. uv run python ecalendar.py timeline 20260101 20261231 -tll 120 -tld below -of timeline.svg

# Blockplan view
PYTHONPATH=. uv run python ecalendar.py blockplan 20260101 20261231 -th corporate -of blockplan.svg

# Gantt chart: task table + bars + dependency arrows, plus chart_details.svg
PYTHONPATH=. uv run python ecalendar.py gantt 20260101 20260630 -th default -of chart.svg

# Compact activities plan
PYTHONPATH=. uv run python ecalendar.py compactplan 20260309 20260424 -th corporate -of compact.svg

# Excel workbook with project-planning template
PYTHONPATH=. uv run python ecalendar.py excelheader 20260101 20260630 -th corporate -of plan.xlsx

# Excel workbook with blockplan-style data rows (events + durations, sorted by start date)
PYTHONPATH=. uv run python ecalendar.py excelblockplan 20260101 20260630 -th corporate -of plan.xlsx

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
PYTHONPATH=. uv run python ecalendar.py palettesheet Set2 -of set2.svg
PYTHONPATH=. uv run python ecalendar.py patternsheet -f wiggle -of wiggle.svg
PYTHONPATH=. uv run python ecalendar.py iconsheet -f arrow -of arrows.svg
PYTHONPATH=. uv run python ecalendar.py colorsheet -of colors.svg
PYTHONPATH=. uv run python ecalendar.py fontsheet -f roboto -of roboto.svg

# Same sheets split into printable pages (colors_p01.svg, colors_p02.svg, ...)
PYTHONPATH=. uv run python ecalendar.py colorsheet -f blue --paginate -cols 6 -rows 8 -of colors.svg
PYTHONPATH=. uv run python ecalendar.py palettesheet Set2 --paginate -cols 4 -rows 2 -of set2.svg
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
| `--candybar-month-rotation` | `DEGREES` | `candybar` | Rotate the month-name label (e.g. -90 for vertical, reading up) |  |
| `--candybar-month-shading` |  | `candybar` | Tint day cells per month (alternating bands; theme can set colors) |  |
| `--candybar-month-side` |  | `candybar` | Side for the merged month-name box (default: right) | choices `left, right` |
| `--candybar-no-week-numbers` |  | `candybar` | Hide the week-number column (shown by default) | default `False` |
| `--candybar-row-height` | `POINTS` | `candybar` | Fixed week-row height in points (default: 0 = auto-fit to page) |  |
| `--candybar-suppress-weekends` |  | `candybar` | Drop Sat/Sun columns (default: weekends are shown) |  |
| `--candybar-weekend-fill` | `COLOR` | `candybar` | Shade Sat/Sun day cells with this color (default: no weekend shading) |  |
| `--color`, `-c` | `COLOR` | `fontsheet`, `iconsheet`, `patternsheet` | Glyph color (default: #222222) (`iconsheet`: Stroke color for icons (default: #333333)) (`patternsheet`: Fill color for pattern tiles (default: #333333)) | `fontsheet`: default `#222222`; `iconsheet`, `patternsheet`: default `#333333` |
| `--columns`, `-cols` | `N` | `colorsheet`, `fontsheet`, `iconsheet`, `palettesheet` | Swatch columns per page (requires --paginate; default: 8) (`fontsheet`: Font columns per page (requires --paginate; default: 2). Ignored with --fullset, which is always a single column.) (`iconsheet`: Icon columns per page (requires --paginate; default: 8)) (`palettesheet`: Swatch columns per page (requires --paginate; default: 12)) |  |
| `--country`, `-cc` | `CODE` | `blockplan`, `candybar`, `compactplan`, `excelblockplan`, `excelheader`, `exportdata`, `gantt`, `mini`, `mini-icon`, `pit`, `text-mini`, `timeline`, `weekly` | ISO 3166-1 alpha-2 country code(s) for government holidays. Accepts a single code (e.g. US) or a comma-separated list (e.g. US,CA,GB) to include holidays from multiple countries. If omitted, US and CA holidays are loaded by default. (`excelblockplan`, `excelheader`: ISO 3166-1 alpha-2 country code(s) for holidays. Accepts a single code (e.g. US) or a comma-separated list (e.g. US,CA,GB) to include holidays from multiple countries.) |  |
| `--database`, `-db` | `PATH` | `blockplan`, `candybar`, `colors`, `colorsheet`, `compactplan`, `excelblockplan`, `excelheader`, `exportdata`, `gantt`, `icons`, `iconsheet`, `mini`, `mini-icon`, `palettes`, `palettesheet`, `papersizes`, `patterns`, `patternsheet`, `pit`, `text-mini`, `timeline`, `weekly` | Path to SQLite database file (default: calendar.db) | default `calendar.db` |
| `--date-placement` |  | `pit` | Where each event date is drawn: inline (a line inside the label box, with the name/notes — never collides; default), axis (opposite the axis at the marker — the ruler look, but dates collide when events cluster), or none. | choices `inline, axis, none` |
| `--direction` |  | `pit` | Axis direction (default: horizontal). Note: --orientation remains the page-orientation flag (portrait/landscape). | choices `horizontal, vertical` |
| `--embed-data` |  | `blockplan`, `candybar`, `compactplan`, `gantt`, `mini`, `mini-icon`, `pit`, `timeline`, `weekly` | Embed source event data (CSV) inside SVG metadata | default `False` |
| `--empty`, `-e` |  | `blockplan`, `candybar`, `compactplan`, `excelblockplan`, `gantt`, `mini`, `mini-icon`, `pit`, `text-mini`, `timeline`, `weekly` | Create blank calendar (no events) (`excelblockplan`: Create blank workbook (no events)) | default `False` |
| `--event-icon` | `NAME` | `pit` | DB icon name drawn inside each event's label box, on the name line and to the left of the name. Does NOT change the axis marker (always a built-in circle). |  |
| `--filter`, `-f` | `TEXT` | `colorsheet`, `fontsheet`, `iconsheet`, `patternsheet` | Filter colors by name substring (case-insensitive) (`fontsheet`: Filter fonts by name substring (case-insensitive)) (`iconsheet`: Filter icons by name substring (case-insensitive)) (`patternsheet`: Filter patterns by name substring (case-insensitive)) |  |
| `--fiscal` | `TYPE` | `blockplan`, `candybar`, `compactplan`, `gantt`, `mini`, `mini-icon`, `pit`, `text-mini`, `timeline`, `weekly` | Enable fiscal calendar overlay (nrf-454, nrf-445, nrf-544, 13-period). weekly/mini: period labels and day-box colors. text-mini: period start markers. timeline: fiscal period/quarter bands (see --fiscal-show-periods/quarters). blockplan/compactplan: NRF-aware fiscal_quarter bands. | choices `nrf-454, nrf-445, nrf-544, 13-period` |
| `--fiscal-colors` |  | `candybar`, `mini`, `mini-icon`, `weekly` | Use fiscal period colors instead of Gregorian month colors for day box backgrounds | default `False` |
| `--fiscal-show-periods` |  | `timeline` | Show a fiscal period band row above the timeline axis (requires --fiscal) | default `False` |
| `--fiscal-show-quarters` |  | `timeline` | Show a fiscal quarter band row above the timeline axis (requires --fiscal) | default `False` |
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
| `--ignorecomplete`, `-ic` |  | `blockplan`, `candybar`, `compactplan`, `excelblockplan`, `exportdata`, `gantt`, `mini`, `mini-icon`, `pit`, `text-mini`, `timeline`, `weekly` | Exclude 100%% complete items | default `False` |
| `--includenotes`, `-notes` |  | `blockplan`, `compactplan`, `gantt`, `pit`, `timeline`, `weekly` | Show notes with event names | default `False` |
| `--label-fill-opacity`, `-lfo` | `0.0-1.0` | `timeline` | Fill opacity for callout label boxes (default: 0.25). |  |
| `--label-icon-gap` | `POINTS` | `pit` | Horizontal gap (points) between the label-box icon and the start of the event name (default: 4.0). |  |
| `--label-icon-size` | `POINTS` | `pit` | Longest viewBox side of the label-box icon, in points. Defaults to the event-name font size so the glyph fits cleanly on the name baseline. |  |
| `--label-side` |  | `pit` | Which side(s) of the axis the labels occupy. primary = above (horizontal) / right (vertical); secondary = below / left; both = chronologically alternating. Default: both. | choices `primary, secondary, both` |
| `--leader-dash` | `DASHARRAY` | `pit` | SVG stroke-dasharray for leaders, e.g. "4,2". |  |
| `--leader-label-anchor` |  | `pit` | Where the leader meets the label box along the axis. center (default) joins the box middle and never collides; start/end join the leading/trailing edge and may overlap on dense timelines. | choices `start, center, end` |
| `--leader-length` | `POINTS` | `pit` | Distance from the axis to the first row of labels, i.e. the leader length (default: 8.0). Larger values lengthen leaders and widen row-to-row spacing. |  |
| `--leader-stub` | `POINTS` | `pit` | Length of the straight perpendicular segment where each leader meets its label box (default: 6.0). Keeps the arrowhead flush with the line; 0 disables. Equivalent to pit.leader.end_stub. |  |
| `--margin`, `-m` |  | `blockplan`, `candybar`, `compactplan`, `gantt`, `mini`, `mini-icon`, `pit`, `timeline`, `weekly` | Add page margins | default `False` |
| `--marker-size` | `POINTS` | `pit` | Bounding-box size of the axis marker (built-in circle / diamond) in points (default: 7.0). |  |
| `--milestone-icon` | `NAME` | `pit` | DB icon name drawn inside each milestone's label box, on the name line and to the left of the name. Does NOT change the axis marker (always a built-in diamond). |  |
| `--milestones`, `-mo` |  | `blockplan`, `candybar`, `compactplan`, `excelblockplan`, `exportdata`, `gantt`, `mini`, `mini-icon`, `pit`, `text-mini`, `timeline`, `weekly` | Show only milestones | default `False` |
| `--mini-columns`, `-mc` | `N` | `mini`, `mini-icon`, `text-mini` | Number of months per row in mini calendar (default: 3) |  |
| `--mini-details` |  | `mini`, `mini-icon` | Generate a second SVG with mini calendar event details | default `False` |
| `--mini-grid-lines` |  | `mini`, `mini-icon` | Draw grid lines between day cells | default `False` |
| `--mini-icon-set`, `-mis` | `SET` | `mini-icon` | Icon set to use for day numbers (choices: squares, darksquare, darkcircles, circles, squircles, darksquircles; default: squares) | choices `squares, darksquare, darkcircles, circles, squircles, darksquircles` |
| `--mini-no-adjacent`, `-mna` |  | `mini`, `mini-icon`, `text-mini` | Hide leading/trailing days from adjacent months | default `False` |
| `--mini-rows`, `-mr` | `N` | `mini`, `mini-icon`, `text-mini` | Number of rows of months (0 = auto from date range) |  |
| `--mini-title-format` | `FMT` | `mini`, `mini-icon` | Format string for month title (default: MMM YY) |  |
| `--monthnames`, `-mn` |  | `weekly` | Show month names on calendar | default `False` |
| `--no-tick-labels` |  | `pit` | Draw tick marks but no tick labels. |  |
| `--no-ticks` |  | `pit` | Suppress axis tick marks and labels. |  |
| `--no-today-line` |  | `pit` | Suppress the today line. | default `True` |
| `--nodurations`, `-nd` |  | `blockplan`, `candybar`, `compactplan`, `excelblockplan`, `exportdata`, `gantt`, `mini`, `mini-icon`, `text-mini`, `timeline`, `weekly` | Exclude multi-day durations | default `False` |
| `--noevents`, `-ne` |  | `blockplan`, `candybar`, `compactplan`, `excelblockplan`, `exportdata`, `gantt`, `mini`, `mini-icon`, `pit`, `text-mini`, `timeline`, `weekly` | Exclude single-day events | default `False` |
| `--orientation`, `-o` |  | `blockplan`, `candybar`, `compactplan`, `gantt`, `mini`, `mini-icon`, `pit`, `timeline`, `weekly` | Page orientation (default: landscape) | default `landscape`; choices `portrait, landscape` |
| `--outputfile`, `-of` (`-o` for `exportdata`) | `PATH` | `blockplan`, `candybar`, `colorsheet`, `compactplan`, `excelblockplan`, `excelheader`, `exportdata`, `fontsheet`, `gantt`, `iconsheet`, `mini`, `mini-icon`, `palettesheet`, `patternsheet`, `pit`, `text-mini`, `timeline`, `weekly` | Output filename (always written under output/) (`colorsheet`: Output SVG path (default: output/colorsheet.svg). With --paginate, a '_pNN' suffix is appended per page (e.g. colorsheet_p01.svg).) (`excelblockplan`: Output .xlsx file name (always written under output/; default: output/ExcelBlockplan.xlsx)) (`excelheader`: Output .xlsx file name (always written under output/; default: output/excelheader.xlsx)) (`exportdata`: Output CSV file name (always written under output/; default: output/exportdata_YYYYMMDD.csv)) (`fontsheet`: Output file name and path (default: output/fontsheet.svg). With --paginate, a '_pNN' suffix is appended per page (e.g. fontsheet_p01.svg).) (`iconsheet`: Output file name and path (default: output/iconsheet.svg). With --paginate, a '_pNN' suffix is appended per page (e.g. iconsheet_p01.svg).) (`palettesheet`: Output file path (default: output/palettesheet.svg, or output/<NAME>.svg when a palette is named). With --paginate, a '_pNN' suffix is appended per page (e.g. palettesheet_p01.svg).) (`patternsheet`: Output file name and path (default: output/patternsheet.svg)) | `blockplan`, `candybar`, `compactplan`, `gantt`, `mini`, `mini-icon`, `pit`, `text-mini`, `timeline`, `weekly`: default `ecalendar.svg` |
| `--overflow`, `-x` |  | `weekly` | Create overflow page showing items | default `False` |
| `--paginate` |  | `colorsheet`, `fontsheet`, `iconsheet`, `palettesheet` | Split the colors across multiple printable SVG pages instead of one large sheet. Enables --columns/--rows/--sized; without it a single SVG containing every color is produced (the default). (`fontsheet`: Split the fonts across multiple printable SVG pages instead of one large sheet. Enables --columns/--rows/--sized; without it a single SVG containing every font is produced (the default).) (`iconsheet`: Split the icons across multiple printable SVG pages instead of one large sheet. Enables --columns/--rows; without it a single SVG containing every icon is produced (the default).) (`palettesheet`: Split the swatches across multiple printable SVG pages instead of one large sheet. Enables --columns/--rows/--sized; without it a single SVG containing every palette is produced (the default). When every palette is rendered, each page is packed with as many complete palettes as fit; a palette is never split across pages.) | default `False` |
| `--papersize`, `-ps` | `SIZE` | `blockplan`, `candybar`, `compactplan`, `gantt`, `mini`, `mini-icon`, `pit`, `timeline`, `weekly` | Paper size (default: Widescreen). | default `Widescreen` |
| `--quiet`, `-q` |  | `blockplan`, `candybar`, `colors`, `colorsheet`, `compactplan`, `excelblockplan`, `excelheader`, `exportdata`, `fonts`, `fontsheet`, `gantt`, `help`, `icons`, `iconsheet`, `mini`, `mini-icon`, `palettes`, `palettesheet`, `papersizes`, `patterns`, `patternsheet`, `pit`, `text-mini`, `themes`, `timeline`, `weekly` | Suppress all output except errors | default `False` |
| `--rollups`, `-ro` |  | `blockplan`, `candybar`, `compactplan`, `excelblockplan`, `exportdata`, `gantt`, `mini`, `mini-icon`, `pit`, `text-mini`, `timeline`, `weekly` | Show only rollup entries | default `False` |
| `--rows`, `-rows` | `N` | `colorsheet`, `fontsheet`, `iconsheet`, `palettesheet` | Swatch rows per page (requires --paginate; default: 10) (`fontsheet`: Font rows per page (requires --paginate; default: 10)) (`iconsheet`: Icon rows per page (requires --paginate; default: 10)) (`palettesheet`: Swatch rows per page — with no palette name this is the page's height budget for packing whole palettes (requires --paginate; default: 10)) |  |
| `--shade`, `-sh` |  | `candybar`, `mini`, `mini-icon`, `weekly` | Shade current date | default `False` |
| `--shrink` |  | `blockplan`, `candybar`, `gantt`, `mini`, `mini-icon`, `pit`, `timeline`, `weekly` | Shrink SVG width/height/viewBox to the bounding box of rendered content, removing blank page whitespace. | default `False` |
| `--sized` | `N` | `colorsheet`, `fontsheet`, `iconsheet`, `palettesheet` | Swatch box width in points (the height scales with it to keep the sheet's aspect ratio; the label/spacing gaps are unchanged). Requires --paginate; default: 110. (`fontsheet`: Sample text size in points; entry heights follow it. Requires --paginate; default: 16.) (`iconsheet`: Icon cell size in points (one integer sets both width and height; the label/spacing gaps are unchanged). Requires --paginate; default: 24.) (`palettesheet`: Swatch box size in points (one integer sets both width and height; the label/spacing gaps are unchanged). Requires --paginate; default: 80.) |  |
| `--status` | `LIST` | `blockplan`, `candybar`, `compactplan`, `excelblockplan`, `exportdata`, `gantt`, `mini`, `mini-icon`, `pit`, `text-mini`, `timeline`, `weekly` | Comma-separated event statuses to include (active, draft, cancelled, archived, on-hold). Use 'all' for no filter. Default: active. |  |
| `--theme`, `-th` | `THEME` | `blockplan`, `candybar`, `compactplan`, `excelblockplan`, `excelheader`, `gantt`, `mini`, `mini-icon`, `pit`, `timeline`, `weekly` | Theme name or path to .yaml theme file (e.g., 'corporate', 'dark') (`excelblockplan`, `excelheader`: Theme name or path to .yaml theme file) |  |
| `--tick-interval` | `DAYS` | `pit` | For --tick-unit interval, days between ticks (default: 1). |  |
| `--tick-label-format` | `FMT` | `pit` | Arrow date format for tick labels (e.g. 'MMM D'). For week/interval units the timeband label is used when omitted. |  |
| `--tick-length` | `POINTS` | `pit` | Half-length of each axis tick mark, per side (default: 5.0). |  |
| `--tick-unit` |  | `pit` | Axis tick granularity (timeband unit). Default: month. | choices `month, week, fiscal_quarter, fiscal_period, interval, date, year` |
| `--today-date` | `YYYYMMDD` | `pit` | Override the today-line position. Lets a forward-dated presentation be prepared with the 'correct' today indicator. |  |
| `--today-label` | `TEXT` | `pit` | Today-line label text (default: "today"; "" suppresses). |  |
| `--today-line` |  | `pit` | Draw the today line (default: on). |  |
| `--today-line-direction`, `-tld` |  | `timeline` | Which side of the timeline axis the today line extends to: 'above' (upward only), 'below' (downward only), or 'both' (default). | choices `above, below, both` |
| `--today-line-length`, `-tll` | `POINTS` | `timeline` | Length of the today line in points (default: 0 = full available area). When direction is 'both', length is split equally above and below the axis. |  |
| `--verbose`, `-v` |  | `blockplan`, `candybar`, `colors`, `colorsheet`, `compactplan`, `excelblockplan`, `excelheader`, `exportdata`, `fonts`, `fontsheet`, `gantt`, `help`, `icons`, `iconsheet`, `mini`, `mini-icon`, `palettes`, `palettesheet`, `papersizes`, `patterns`, `patternsheet`, `pit`, `text-mini`, `themes`, `timeline`, `weekly` | Increase verbosity (-v, -vv, -vvv) | default `0` |
| `--watermark-image`, `-wi` |  | `blockplan`, `candybar`, `compactplan`, `gantt`, `mini`, `mini-icon`, `pit`, `timeline`, `weekly` | Watermark image file |  |
| `--watermark-rotation-angle` | `DEGREES` | `blockplan`, `candybar`, `compactplan`, `gantt`, `mini`, `mini-icon`, `pit`, `timeline`, `weekly` | Rotate text watermark by degrees (clockwise coordinates) |  |
| `--watermark-text`, `-wt` |  | `blockplan`, `candybar`, `compactplan`, `gantt`, `mini`, `mini-icon`, `pit`, `timeline`, `weekly` | Watermark text |  |
| `--week-number-mode`, `-wnm` |  | `mini`, `mini-icon`, `text-mini`, `weekly` | Week number mode (iso or custom) | default `iso`; choices `iso, custom` |
| `--week1-start` | `YYYYMMDD` | `mini`, `mini-icon`, `text-mini`, `weekly` | Anchor date for week 1 (YYYYMMDD). Implies --weeknumbers and custom mode. |  |
| `--weekend-days` | `DAYS` | `blockplan`, `compactplan`, `excelblockplan`, `excelheader`, `gantt`, `timeline`, `weekly` | Comma-separated ISO weekday list (0=Mon..6=Sun) marking non-working days for holiday/weekend classification. Defaults to Sat/Sun when weekends are shown. (`excelblockplan`, `excelheader`: Comma-separated ISO weekday list (0=Mon..6=Sun) marking non-working days for holiday/weekend classification.) |  |
| `--weekends`, `-we` |  | `blockplan`, `candybar`, `compactplan`, `excelblockplan`, `excelheader`, `gantt`, `mini`, `mini-icon`, `pit`, `text-mini`, `timeline`, `weekly` | Weekend style: 0=work week only, 1=full week Sunday start, 2=half weekends Sunday start, 3=full week Monday start, 4=half weekends Monday start (`excelblockplan`, `excelheader`: Weekend style: 0=work week only (default), 1=full week Sunday start, 2=half weekends Sunday start, 3=full week Monday start, 4=half weekends Monday start) | default `0`; choices `0, 1, 2, 3, 4` |
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

### `excelheader`

| Name | Required | Description | Choices |
|---|---|---|---|
| `START_DATE` | no | Start date in YYYYMMDD format (will be adjusted to full week) |  |
| `END_DATE` | no | End date in YYYYMMDD format (will be adjusted to full week) |  |

Generates an Excel workbook (`.xlsx`) using the shared blockplan-style layout:
columns A–AS carry all 45 events-table field names in schema order (`id`,
`status`, `priority`, `wbs`, `rollup`, `milestone`, `percent_complete`, `name`,
`effort`, `duration`, `start_date`, `end_date`, `earliest_start_date`,
`latest_start_date`, `earliest_end_date`, `latest_end_date`, `predecessors`,
`resource_names`, `resource_group`, `notes`, `icon`, `color`, `tags`, then the
schedule data elements: `source_id`, `critical`, `start_time`, `end_time`,
`duration_text`, `effort_text`, `actual_start_date`, `actual_start_time`,
`actual_end_date`, `actual_end_time`, `deadline`, `start_variance`,
`finish_variance`, `fixed_cost`, `cost`, `percent_work_complete`, `successors`,
`custom1`–`custom5`), column AT is reserved for the continuation marker (used by
`excelblockplan`), and one column per visible day starts at column AU. Timeband
rows place their heading label in the last label column with segment values
starting at the first date column. After the column-header row, `excelheader`
writes 100 empty data rows decorated with holiday shading and vertical-line
borders so the workbook can be used as a planning template. Timeband
configuration uses `excelheader.top_time_bands` and
`excelheader.vertical_lines` from the active theme.

The label columns are **not** frozen — with the full events-table column set
they are far wider than a screen, and freezing them would push the calendar
grid out of view. `excelheader` freezes the timeband rows only;
`excelblockplan` sets no freeze pane at all, since its rows are independent
records rather than a grid you scroll within.

### `excelblockplan`

| Name | Required | Description | Choices |
|---|---|---|---|
| `START_DATE` | no | Start date in YYYYMMDD format (will be adjusted to full week) |  |
| `END_DATE` | no | End date in YYYYMMDD format (will be adjusted to full week) |  |

Generates the same workbook skeleton as `excelheader` but populates the data
rows with one record per event/duration sourced from the events table. The
command-line surface mirrors `blockplan` so the same filter flags work:
`--theme`, `--weekends`, `--weekend-days`, `--country`, `--noevents`,
`--nodurations`, `--ignorecomplete`, `--milestones`, `--rollups`,
`--WBS`, `--status`, `--empty`. (There is no `--includenotes` — the
Notes column is always emitted.)

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

Default output path: `output/ExcelBlockplan.xlsx`. Configure via
`excelblockplan.top_time_bands`, `excelblockplan.vertical_lines` and the
matching `excelblockplan.*` colour/font keys in the active theme — these
fall back to the corresponding `excelheader.*` keys when unset, so a single
theme can style both views consistently.

#### `blockplan` rendering behavior

In blockplan, items are first assigned to configured lanes, then rendered separately as events or durations:

- Lane assignment is driven by each lane's `match` rules. Supported filters include WBS prefixes, resource groups, resource name substrings, task-name substrings, notes substrings, milestone/rollup flags, event type, and priority filters/ranges.
- If `blockplan_lane_match_mode` is `first`, an item stops at the first matching lane. If it is `all`, the same item can appear in multiple lanes.
- If `blockplan_show_unmatched_lane` is enabled, unmatched items are collected into the configured unmatched lane instead of disappearing.
- Durations are drawn as horizontal bars inside the lane's duration section. Bars are packed into rows to avoid overlap. Standard duration bars use `blockplan_palette[event.priority % len(blockplan_palette)]`; durations with notes and `-notes` enabled switch to a taller weekly-style bar with a fixed `lightsteelblue` fill and separate note line.
- Events are drawn as point markers with a text label to the right. If the event has an icon and that icon resolves from the icon table, the icon is used as the marker; otherwise a filled circle is drawn.
- Event rows are assigned to avoid horizontal label collisions. If enabled, event dates render above the event name, and notes render on a separate line below the name.

#### `compactplan` rendering behavior

In compactplan, durations and milestones are rendered relative to a horizontal dashed axis spanning the full content width:

- Duration lines are placed using a greedy row assignment that alternates above and below the axis. Row 0 is immediately above the axis, row 1 is immediately below, row 2 is further above, row 3 further below, and so on. Durations are sorted by start date before placement; the first row with no x-overlap is chosen.
- Duration line colors are assigned per `resource_group`, cycling through `compact_plan.palette` in sorted group order. An individual event's `Color` field in the database overrides the group palette color.
- **Duration start icons**: when `compact_plan.show_duration_icons` is `true` (the default), an icon is drawn at the start (left) end of every duration line. Icons are assigned per resource group by cycling through the named icon list (`compact_plan.duration_icon_list`, default `"darksquare"`). The icon is drawn in the same color as the line. `compact_plan.duration_icon_height` controls the icon size in points (default `8.0`). Available icon lists are `darksquare`, `squares`, `darkcircles`, `circles`, `squircles`, and `darksquircles`; all are defined in `config/config.py` as `ICON_SETS`.
- Milestone markers are drawn on the axis at the milestone date. Marker shape priority: `event.Icon` from the database → `compact_plan.milestone_icon` from the active theme → built-in flag shape (vertical stem + pennant). If `show_milestone_labels` is enabled, the task name is drawn in italic to the right of the marker.
- Column header time bands follow the same schema as `blockplan.top_time_bands`. Supported units: `week`, `month`, `fiscal_quarter`, `fiscal_period`, `interval`, `date`, `dow`, `countdown`, `countup`, `icon` (see [time_bands](#time_bands--shared-band-catalog) for the full reference). Week-unit columns support `{n}` (sequential week number), `{start}` and `{end}` (M/D date strings) format tokens. Alternate-fill columns (`alt_fill_color`) color every other column segment. Each band supports a `text_align` key (`"left"` / `"center"` / `"right"`, default `"left"`) that controls the horizontal alignment of the label within its segment — `"left"` pins the text to the left edge, `"center"` centres it, and `"right"` pins it to the right edge. Text is always shrunk to fit the segment width regardless of alignment.
- The layout is content-first and always shrunk: the axis is fixed at the vertical centre of the content area, duration rows are placed around it, then the header bands float `compact_plan.header_bottom_y` pts above the topmost row and the legend floats `compact_plan.key_top_y` pts below the bottommost row. The SVG viewBox is trimmed to exactly the rendered content, producing the smallest possible output.
- The legend and milestone roster are rendered **side by side** in a two-column layout starting at the same vertical position. The fraction of the total width given to the left column is controlled by `compact_plan.legend_column_split` (default `0.5`; a fixed 8 pt gap separates the columns).
  - **Left column** (controlled by `compact_plan.show_legend`): one row per resource group. When `show_duration_icons` is enabled the row layout is `[icon] [swatch line] [Group Name: names…]`; otherwise `[swatch line] [Group Name: names…]`. The icon matches the one drawn on the duration line for that group. Names are **wrapped**: as many comma-separated names as fit are placed on the header row; any that overflow wrap onto continuation rows indented to align with the text start (no icon or swatch repeated).
  - **Right column** (controlled by `compact_plan.show_milestone_list`): a date-sorted roster of every milestone marker. Each row shows the date (formatted by `compact_plan.milestone_list_date_format`, Arrow format string, default `M/D`) in a fixed-width left sub-column and the task name in the remaining sub-column width.
- **Continuation icons**: when a duration event's end date extends beyond the specified calendar end date the line is clamped to the right edge of the timeline. If the global `continuation.show` is `true` (the default), a small icon is drawn at the right edge of the clamped line and a corresponding legend entry is appended below the milestone roster. The icon name (default `"arrow-right"`), display height in points (default `8.0`), and color (default: inherits the line color) come from the global `continuation.icon_after`, `continuation.icon_height`, and `continuation.icon_color` keys (compactplan is horizontal-only and only clips on its trailing end, so it reads `icon_after`). A theme may instead `define icon:continuation` and bind it to `ec-continuation-icon` — values declared there (`icon`, `size`, `color`) override the global defaults. The legend text is set by `compact_plan.continuation_legend_text` (default `"activity continues"`) and the gap above it by `continuation_section_gap` (default `4.0` pts). Icons are loaded from the `icons` table in the database. See [Continuation Icons](#continuation-icons-global-theme-section) for the full key catalog and orientation-aware list form.
- All text areas (band headers, milestone labels, legend entries, milestone roster, continuation legend) support independent font name, font size, color, and opacity settings in the theme via the `compact_plan` section.
- `--shade` highlights the current day column when today falls within the date range.
- `--weekends` controls whether weekend columns are included in the x-axis day list (same as all other commands).

### `gantt`

| Name | Required | Description | Choices |
|---|---|---|---|
| `START_DATE` | no | Start date in YYYYMMDD format (will be adjusted to full week) |  |
| `END_DATE` | no | End date in YYYYMMDD format (will be adjusted to full week) |  |

### `help`

| Name | Required | Description | Choices |
|---|---|---|---|
| `subcommand` | yes | Subcommand to show help for | weekly, mini, mini-icon, candybar, text-mini, timeline, pit, blockplan, gantt, compactplan, excelheader, excelblockplan, themes, papersizes, patterns, patternsheet, icons, iconsheet, colors, colorsheet, palettes, palettesheet, fonts, fontsheet, exportdata |

### `mini`

| Name | Required | Description | Choices |
|---|---|---|---|
| `START_DATE` | no | Start date in YYYYMMDD format (will be adjusted to full week) |  |
| `END_DATE` | no | End date in YYYYMMDD format (will be adjusted to full week) |  |

#### `mini` day styling behavior

In the SVG mini calendar, day-level styling is driven by holidays, special days, and events:

- An icon replaces the day number when the resolved day style has an icon. This can come from a holiday icon, a special-day icon, or an event `Icon` value. If both milestone and non-milestone event icons exist on the same day, the milestone icon wins.
- A day number is circled when any event on that day has `Milestone` set and `mini_calendar.circle_milestones` is enabled.
- A day number is bold when the day contains a milestone, or when any event on that day has `Priority <= 1`.
- A day number changes color when one of these applies: the day is from an adjacent month, the day is a holiday, or an event's `Resource_Group` maps to a configured resource-group color.
- Adjacent-month day cells can be shown or hidden with `mini_calendar.show_adjacent` (default: `true`) or `--mini-no-adjacent`.
- A configurable outline can be drawn around each entire month grid (title + DOW header + day cells) using `mini_calendar.month_outline_color/width/opacity/dasharray`; the outline is disabled by default (color is `null`).
- Day cells can also receive SVG pattern decorations from top-level `style_rules` entries with `apply_to: day_box` (the mini renderer reads the same `style_rules` list as weekly).
- If none of those overrides apply, the day number uses the default mini-calendar day color from the active theme/config.
- `--shade` affects the current day by shading the cell background only; it does not by itself make the number bold or change the number color.

### `mini-icon`

| Name | Required | Description | Choices |
|---|---|---|---|
| `START_DATE` | no | Start date in YYYYMMDD format (will be adjusted to full week) |  |
| `END_DATE` | no | End date in YYYYMMDD format (will be adjusted to full week) |  |

#### `mini-icon` day rendering behavior

`mini-icon` is a variant of `mini` that replaces plain day-number text with SVG icon images drawn at 80 % of the cell height. Everything else — grid layout, month rows/columns, holidays, events, milestones, week numbers, adjacent-month cells, pattern decorations, and the optional details page — behaves identically to `mini`.

**Icon selection priority (highest → lowest):**

1. `icon_replace` from an event, holiday, or special-day rule on that date — replaces the day icon entirely.
2. `icon_append` from an event, holiday, or special-day rule — used when no `icon_replace` is present.
3. Day-number icon from the configured icon set — one of 31 per-day icons (1–31) looked up by name from the icon database.
4. Plain day-number text — rendered as a fallback if the icon name is not found in the database.

**Available icon sets** (`--mini-icon-set` / `-mis`):

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
`--mini-columns`, `--mini-rows`, `--weeknumbers`, `--week1-start`, `--week-number-mode`, `--mini-no-adjacent` (`-mna`), `--mini-grid-lines`, `--mini-details`, `--mini-title-format`, `--shade`, `--weekends`, `--theme`, `--papersize`, `--orientation`, `--margin`, `--header`, `--footer`, `--watermark`, and all filter flags.

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

**Month box.** The right-hand column (or left, via `--candybar-month-side`) holds a **merged month-name box** that spans every week row belonging to that month. A week is attributed to the month of its last visible day, so a boundary week such as Jan 27–Feb 2 is labeled *Feb* (matching the spreadsheet reference). The month label supports the full set of SVG text attributes — font, size, color, opacity, anchor, and **rotation** (e.g. `--candybar-month-rotation -90` runs the name vertically, reading up the box). Box fill/stroke and label styling are theme-configurable under the `candybar:` section.

**Decoration and icons.** Day cells use the **same rule engine as `mini`/`mini-icon`** — holidays, special days, events, and theme `style_rules` / `box:day` rules drive cell shading, SVG pattern decorations, milestone circles, and icon placement (`icon_replace` / `icon_append`). Day cells show the day number by default and swap in an icon only when a rule requests one.

**Cell shading (months & weekends).** In addition to the rule engine, candybar has two built-in base shades drawn *under* the rule/holiday shade (so holidays still win):

- **Month banding** — enable with `--candybar-month-shading` (or `candybar.month_shading: true`). Day cells are tinted per calendar month, cycling through `candybar.month_shade_colors` (a list of colors; `none` skips shading that month). With no colors set it defaults to `["none", "gainsboro"]` so alternate months are tinted. Opacity via `candybar.month_shade_opacity` (default 0.12).
- **Weekend tint** — set `--candybar-weekend-fill COLOR` (or `candybar.weekend_fill`) to shade the Sat/Sun day cells, with `candybar.weekend_opacity` (default 0.15). Independent of the rule engine — plain weekends are tinted even when they aren't holidays. (Only visible when weekends are shown.)

The `corporate` theme ships with both enabled as a demonstration.

**Weekend suppression.** Candybar **shows weekends by default** (7-column Mon–Sun strip), independent of the `--weekends` / `weekend_style` setting. Pass `--candybar-suppress-weekends` (or set `candybar.suppress_weekends: true` in a theme) to drop the Sat/Sun columns for a 5-column Mon–Fri strip.

**Candybar-specific options:**

| Option | Argument | Description |
|---|---|---|
| `--candybar-row-height` | `POINTS` | Fixed week-row height (default: 0 = auto-fit to page). |
| `--candybar-cell-width` | `POINTS` | Fixed day-cell width (default: 0 = square, width == row height). |
| `--candybar-max-rows-per-page` | `N` | Split into side-by-side strips after N rows (0 = single strip). |
| `--candybar-suppress-weekends` |  | Drop Sat/Sun columns (default: weekends are shown). |
| `--candybar-no-week-numbers` |  | Hide the week-number column (shown by default). |
| `--candybar-month-side` | `{left,right}` | Side for the merged month box (default: right). |
| `--candybar-month-rotation` | `DEGREES` | Rotate the month-name label (e.g. -90 for vertical). |
| `--candybar-weekend-fill` | `COLOR` | Shade Sat/Sun day cells (default: no weekend shading). |
| `--candybar-month-shading` |  | Tint day cells per month (alternating bands; theme sets colors). |

Candybar also accepts the shared `mini` options (`--weeknumbers` mode/anchor via `--week-number-mode` / `--week1-start`, `--theme`, `--papersize`, `--orientation`, `--margin`, `--header`, `--footer`, `--watermark`, `--shade`, `--fiscal` / `--fiscal-colors`, and the event filter flags `--noevents`, `--nodurations`, `--ignorecomplete`, `--milestones`, `--rollups`, `--WBS`, `--status`, `--empty`).

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

No positional arguments. Use `--filter` to narrow the rendered grid by pattern name and `--color` to set the tile fill (default `#333333`). Run `ecalendar.py patterns` to discover pattern names.

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

Exports filtered events and durations as a CSV file matching the schema consumed by `importers/import_events.py`. Supports the standard content filters (`--noevents`, `--nodurations`, `--ignorecomplete`, `--milestones`, `--rollups`, `--WBS`, `--status`) and `--country` for selecting which government holidays accompany the event rows. By default only `status='active'` events are exported — pass `--status all` or a specific list (e.g. `--status active,draft`) to widen the result. The `--outputfile` short form is `-o` (not `-of`); the default path is `output/exportdata_YYYYMMDD.csv` based on the run date.

The exported CSV includes every column of the `events` table that round-trips back through the importer: `task_name`, `status`, `start_date`, `finish_date`, `earliest_start_date`, `latest_start_date`, `earliest_end_date`, `latest_end_date`, `priority`, `wbs`, `rollup`, `milestone`, `percent_complete`, `effort`, `duration`, `predecessors`, `resource_names`, `resource_group`, `notes`, `icon`, `color`, `tags`.

### `text-mini`

| Name | Required | Description | Choices |
|---|---|---|---|
| `START_DATE` | no | Start date in YYYYMMDD format (will be adjusted to full week) |  |
| `END_DATE` | no | End date in YYYYMMDD format (will be adjusted to full week) |  |

#### `text-mini` symbol behavior

In the text mini calendar, each day cell shows either a formatted day number or one resolved symbol:

- Plain day numbers are shown only when no higher-priority symbol has been assigned to that day.
- Single-day events use symbols from `text_mini_event_symbols`.
- Milestones use symbols from `text_mini_milestone_symbols`.
- Multi-day durations use symbols from `text_mini_duration_symbols` on the start and end dates, and use `text_mini_duration_fill` for interior days.
- Holidays use symbols from `text_mini_holiday_symbols`.
- Special days marked `nonworkday` use symbols from `text_mini_nonworkday_symbols`.
- Symbol precedence is enforced by priority, highest to lowest: holidays, company nonworkdays, milestone events, duration start/end markers, duration interior fill, then regular single-day events.
- When multiple symbols compete for one day, the higher-priority symbol replaces the lower-priority one in the month grid. A details list is appended below the calendar for the assigned symbols.

### `timeline`

| Name | Required | Description | Choices |
|---|---|---|---|
| `START_DATE` | no | Start date in YYYYMMDD format (will be adjusted to full week) |  |
| `END_DATE` | no | End date in YYYYMMDD format (will be adjusted to full week) |  |

#### `timeline` rendering behavior

In timeline, single-day events and multi-day durations are rendered differently and use separate color cycles:

- Single-day events become callout boxes above the axis. Durations become bars below the axis.
- Event callout colors are assigned in sorted order from `timeline_top_colors`, cycling when there are more events than colors. Duration bar colors are assigned separately from `timeline_bottom_colors`, also cycling in sorted order.
- Event markers on the main axis are always plain circles; event icons, when present and found in the icon table, appear inside the event callout box next to the title instead of on the axis marker.
- Duration items render as a horizontal bar with start and end circles on the axis, plus start/end date labels below the bar.
- Event callout boxes are lane-positioned and horizontally offset to reduce collisions. Their connector lines are routed to avoid other boxes when possible.
- The timeline does not take a `--shade` flag. Instead, it has a dedicated today marker: a vertical line and label rendered only when the resolved today date falls inside the displayed date range.

### `weekly`

| Name | Required | Description | Choices |
|---|---|---|---|
| `START_DATE` | no | Start date in YYYYMMDD format (will be adjusted to full week) |  |
| `END_DATE` | no | End date in YYYYMMDD format (will be adjusted to full week) |  |

#### `weekly` rendering behavior

In weekly, day-box cells are drawn first, events and durations are placed into the available rows inside each visible day, then the day-number row is laid out with full knowledge of which days overflowed:

- Day-box background color is chosen from month colors by default, from fiscal-period colors when fiscal colors are enabled, or from holiday/company nonworkday colors when the date is marked as a special day. `--shade` overrides that fill for the current day only.
- The number of event rows per day box is derived from the box height, day-number height, and event-row height so the bottom row never bleeds into the next week's cell.
- Day-number row layout (left → right): fiscal label, week number, overflow icon, holiday/special-day icon(s), holiday name, day number. Every element is vertically centered with the day number — text/icon baselines shift by `0.3 × (day_num_size − element_size)` so labels with smaller fonts share a midline with the day number rather than a baseline.
  - **Week numbers** appear only on week-start days when `--weeknumbers` is enabled. They sit either in the left page margin (when one is present) or inside the day box past the fiscal label.
  - **Overflow icon** is drawn only on days where at least one event or duration could not fit into the available rows. Multiple overflows on the same day produce a single icon. The icon supports a themed halo via `apply_to: box:overflow` (see "Style Rules" below).
  - **Holiday / special-day icons** are drawn one per marking, in sequence after the overflow icon. Federal holidays come first, then company special days. Numeric icon IDs are resolved through the `fonticon` table.
  - **Holiday name** is drawn ONLY when there is exactly one marking AND no overflow on that day; otherwise the row is icon-only so multiple markings stay visible. The name follows immediately after the icon (left-justified) and shrinks to fit the space between the icons and the day number while the icon itself stays at the unshrunk theme size.
- Fiscal period labels appear only when fiscal labeling is enabled and the date qualifies as a fiscal boundary according to the fiscal lookup.
- Day-box pattern and color decorations come from top-level `style_rules` entries with `apply_to: day_box`. Rules can match on day context (federal/company holiday, nonworkday, weekend, date) and event criteria (task name, notes, WBS, percent complete, resource group/names, priority, milestone, rollup, event type). Rules layer additively in declaration order. If no rule supplies a pattern, `theme_weekly_hash_pattern` is used as the fallback pattern. See Complex Structures Reference for the full syntax.
- Single-day event text and event icons use the event's resource-group color when that group maps to a configured resource-group color; otherwise they use the default weekly event colors.
- Item placement order is controlled by `item_placement_order`. Type tokens (`milestones`, `events`, `durations`) determine grouping order, and `priority` or `alphabetical` determine ordering within each group.
- Events with notes need two free rows in the day box when `-notes` is enabled. Durations with notes also require two stacked rows for their double-height bar; if that space is not available, they overflow instead of being compressed into a one-row notes layout.
- Continuation dates on duration bars (drawn when a duration starts before the calendar's first visible day or ends after the last) sit **inside** the bar — the start date is drawn just right of the left continuation arrow, the end date is drawn just left of the right continuation arrow, both vertically centered with the bar's name baseline.

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

Themes are YAML files describing the visual style of SVG output via a single ordered `style_rules` list. Each rule either **defines** a named style token (text, box, line, or icon) or **applies** a style to a content surface (`box:day`, `box:duration`, etc.) or a lane assignment. Element-to-token bindings — *which* `ec-*` class consumes *which* token — are not part of any theme; they live in the built-in catalog at [`config/element_catalog.yaml`](config/element_catalog.yaml) and are shared by every theme. Non-styling configuration — format strings, geometry, fiscal semantics, structural lane and band declarations — lives in dedicated top-level sections.

There is one supported schema. Legacy themes (`text_styles` / `box_styles` / `line_styles` / `icon_styles` / `element_styles` / `axis` / `swimlane_rules` top-level keys) are rejected with a parse error pointing at `tools/migrate_theme.py`. Run the migrator once on any existing theme:

```bash
uv run python tools/migrate_theme.py --in-place path/to/theme.yaml
```

Several themes ship with the application, and all of them are already in the unified schema. The set changes between releases, so rather than relying on a static enumeration here, ask the application for the current list:

```bash
PYTHONPATH=. uv run python ecalendar.py themes
```

Two of the bundled themes serve as reference anchors:

- **`basic.yaml`** — the minimum viable theme. One value per required key, deliberately plain styling (Roboto-Regular, black on white, no patterns). Copy it as a starting point for new themes.
- **`SAMPLE.yaml`** — a complete annotated reference. Every required key is set; optional features (content rules for holidays/sprints/priorities, milestone halos, band alternation, vline patterns, swimlane fills, lane routing) appear as annotated examples.

### Unified Theme Format

A theme is one YAML document with these top-level sections (alphabetical here; order in the file is conventional but not enforced):

```yaml
theme:           # name, version, description
base:            # default font_family, default_missing_icon
layout:          # page margins (numeric points or unit-suffixed values)
header:          # header text content
footer:          # footer text content
events:          # item_placement_order (non-styling)
durations:       # geometry / placement
watermark:       # watermark text and rotation
fiscal:          # label_format, year_offset
colors:          # palette name references; holiday structural attrs
weekly:          # weekly format strings + overflow icon name
mini_calendar:   # mini title_format, layout dims, icon_set name
mini_details:    # column widths, header text, output_suffix
text_mini:       # glyph-set declarations
timeline:        # tick_label_format, geometry, today_date
compact_plan:    # axis-relative geometry, band references
blockplan:       # swimlane name list, label_column_ratio, lane policy
excelheader:     # XLSX-specific config (deliberate exception, see §10.4)
time_bands:      # shared band catalog (referenced by placement lists)
style_rules:     # the only styling section
```

`style_rules` is the heart of the schema. Every visual decision is one rule. See [Complex Structures Reference](#complex-structures-reference) for the full vocabulary.

#### Style Rules: Token Definitions

A token defines a named bundle of style properties — a text appearance, a box appearance, a line, or an icon. Use `define:` to introduce one:

```yaml
style_rules:
  - name: define text:heading
    define: text
    as: heading
    style:
      font: Roboto-Bold
      size: 10
      color: "#000000"

  - name: define box:cell
    define: box
    as: cell
    style:
      fill: white
      fill_opacity: 1.0
      stroke: "#E0E0E0"
      stroke_width: 0.25
      stroke_opacity: 1.0

  - name: define line:grid
    define: line
    as: grid
    style:
      color: "#CCCCCC"
      width: 0.5
      opacity: 1.0

  - name: define icon:event
    define: icon
    as: event
    style:
      color: "#333333"
      size: 10
```

Once defined, a token is addressable as `<kind>:<name>` — for example `text:heading`, `box:cell`, `line:grid`, `icon:event`. Token names are stable handles used in selectors and bindings.

#### Style Rules: Paper-Size and Visualizer Overrides

Rules with `apply_to: <kind>:<name>` add conditional layers on top of a definition. Later rules win:

```yaml
style_rules:
  - name: define text:heading
    define: text
    as: heading
    style: { font: Roboto-Bold, size: 10, color: black }

  - name: text:heading — small paper
    apply_to: text:heading
    select: { papersize: [3x5, 5x8] }
    style: { size: 7 }

  - name: text:heading — weekly visualizer accent
    apply_to: text:heading
    select: { visualizer: weekly }
    style: { color: navy }
```

#### Element Bindings: built-in catalog

`ec-*` CSS classes are bound to tokens by the built-in element catalog at [`config/element_catalog.yaml`](config/element_catalog.yaml) — themes no longer ship binding rules.  The catalog is the single source of truth: each `ec-*` class names a token kind (`text` / `box` / `line` / `icon`) and a token name (`heading`, `day_number`, `cell`, `grid`, etc.), and that pairing applies to every theme.

To rebind or tweak a single element from one theme, use the top-level `element_overrides:` map:

```yaml
element_overrides:
  ec-today-label:
    use: text:label       # remap to a different token
    color: red            # per-element color tweak (also valid alone)
  ec-watermark:
    use: text:caption     # pin watermark to caption styling in this theme only
  ec-axis-tick:
    color: "#888888"      # keep the catalog's text token, change just the color
```

`element_overrides:` keys must be `ec-*` class names that appear in the catalog. Omit `use:` to keep the catalog's default token while still applying a per-element color.  Authoring full `apply_to: element` rules in a theme is no longer supported; if you have an older theme that still ships them, run `tools/strip_element_bindings.py` (targeted, idempotent) to lift them into `element_overrides:`:

```bash
uv run python tools/strip_element_bindings.py path/to/theme.yaml
```

#### Style Rules: Content-Driven Styling

Rules with `apply_to:` set to a content surface (`box:day`, `box:event`, `box:duration`, `box:vline`, `box:milestone`, `text:event_name`, etc.) carry selectors that match against the data being rendered: federal holidays, milestones, priorities, task names, percent complete, etc.

```yaml
style_rules:
  - name: federal holidays — day box tint
    apply_to: box:day
    select: { federal_holiday: true }
    style:
      fill: tomato
      fill_opacity: 0.10
      pattern: diagonal-stripes
      pattern_color: tomato
      pattern_opacity: 0.12

  - name: sprint durations
    apply_to: box:duration
    select:
      task_name: [Sprint]
      event_type: duration
    style:
      fill: steelblue
      fill_opacity: 0.5

  - name: critical milestones
    apply_to: [icon:milestone, text:milestone_label]
    select: { priority_min: 1 }
    style:
      icon: flag
      color: red
      size: 14
```

A list-valued `apply_to:` fans the rule out: each style property is routed to every listed target that recognizes it. See [`style_rules` in Complex Structures Reference](#style_rules--unified-visual-styling-rules) for the full grammar.

#### Style Rules: Lane Routing (Blockplan)

`apply_to: lane` rules assign matched content to a swimlane. First match wins.

```yaml
style_rules:
  - name: route engineering tasks
    apply_to: lane
    select: { resource_group: [engineering, dev] }
    style: { swimlane: Engineering }

  - name: catch-all
    apply_to: lane
    select: {}
    style: { swimlane: Other }
```

#### Time Bands: Shared Catalog

Timebands across `blockplan`, `compact_plan`, and `excelheader` reference a single catalog under the top-level `time_bands:` map. Each visualizer's placement list is a list of catalog keys, optionally with inline geometry overrides.

```yaml
time_bands:
  fiscal_quarter:
    unit: fiscal_quarter
    label: Fiscal Quarter
    label_format: "FY{fy2} Q{q}"
    show_every: 1
  month:
    unit: month
    label: Month
    date_format: "MMM"
    show_every: 1

blockplan:
  top_bands: [fiscal_quarter, month]    # references
  bottom_bands: []

compact_plan:
  bands: [fiscal_quarter, month]

excelheader:
  top_bands: [fiscal_quarter, month]
  band_fonts:
    fiscal_quarter: { excel_font_name: "Arial Narrow", excel_font_size: 10 }
```

Band styling lives in `style_rules` keyed by `select.band: <catalog_key>`. ExcelHeader's `band_fonts` map and `vertical_lines` list are XLSX-only exceptions that do not flow through `style_rules` (they map to Excel cell formatting, not SVG primitives).

### CSS Element Catalog

Every SVG element gets a semantic CSS class. The authoritative list — including which token kind each class binds to by default — lives in [`config/element_catalog.yaml`](config/element_catalog.yaml). The table below mirrors that file. Adding a new `ec-*` class to a renderer requires an entry there; a CI test enforces the two stay in sync.

| CSS Class | Type | What it styles |
|-----------|------|---------------|
| `ec-heading` | text | Section/area heading text |
| `ec-label` | text | Short label text (DOW headers, tick labels) |
| `ec-day-number` | text | Day of month number |
| `ec-month-title` | text | Month name display |
| `ec-week-number` | text | Week number label |
| `ec-fiscal-label` | text | Fiscal period label |
| `ec-event-name` | text | Event/task name |
| `ec-event-notes` | text | Event notes/description |
| `ec-event-date` | text | Event date display |
| `ec-duration-date` | text | Duration start/end date |
| `ec-holiday-title` | text | Holiday/special day name |
| `ec-today-label` | text | Today marker label |
| `ec-header-text` | text | Page header text |
| `ec-footer-text` | text | Page footer text |
| `ec-watermark` | text | Watermark overlay text |
| `ec-background` | box | Page/area background |
| `ec-cell` | box | Content cell background |
| `ec-heading-cell` | box | Heading area background |
| `ec-band-cell` | box | Time band segment cell |
| `ec-callout-box` | box | Popup/callout box |
| `ec-vline-fill` | box | Vertical line fill column |
| `ec-day-box` | box | Day number box outline |
| `ec-pattern-fill` | box | SVG pattern overlay |
| `ec-grid-line` | line | Grid/cell boundary |
| `ec-axis-line` | line | Timeline axis line |
| `ec-axis-tick` | line | Axis tick mark |
| `ec-today-line` | line | Today marker line |
| `ec-separator` | line | Section divider |
| `ec-connector` | line | Connector line |
| `ec-vline` | line | Configured vertical line |
| `ec-duration-bar` | line | Duration span bar/line |
| `ec-hash-line` | line | Hash pattern line |
| `ec-strikethrough` | line | Strikethrough line |
| `ec-milestone-marker` | icon | Milestone indicator (bound to `icon:milestone`) |
| `ec-milestone-flag` | icon | Milestone flag pennant (bound to `icon:milestone`) |
| `ec-duration-marker` | icon | Duration start indicator |
| `ec-band-label` | text | Time-band segment label |
| `ec-band-heading-cell` | box | Heading-column cell carrying a band's label |
| `ec-event-icon` | icon | Event/holiday icon |
| `ec-duration-icon` | icon | Duration category icon |
| `ec-continuation-icon` | icon | Continuation arrow drawn on a duration that extends past the visible range (compactplan; timeline / blockplan use the global `continuation:` theme section directly — see [Continuation Icons](#continuation-icons-global-theme-section)) |
| `ec-overflow-icon` | icon | Overflow indicator |
| `ec-legend-swatch` | legend | Legend color swatch |
| `ec-legend-text` | legend | Legend item text |
| `ec-legend-icon` | legend | Legend item icon |

Modifier classes (added alongside element class): `ec-holiday`, `ec-nonworkday`, `ec-current-day`, `ec-adjacent`.

### Creating a New Theme

The fastest path is to copy `config/themes/basic.yaml` — the minimum viable theme — and edit. `basic.yaml` ships with every required key set to a plain default, so each line you change is a deliberate styling choice. Recipe:

1. Start with a `theme:` metadata block (name, version, description).
2. Define the `style_rules` tokens you need with `define:` entries — typically a few `text:` tokens (heading, body, day_number…), one or two `box:` tokens (cell, header), and any `icon:` tokens you reference.  The element catalog (`config/element_catalog.yaml`) lists the token names each `ec-*` element looks up.  Any required token you omit falls back to a safe default from `config/element_catalog_defaults.yaml`.
3. (Optional) Add an `element_overrides:` block if you need to rebind a single `ec-*` element to a different token (`use: text:label`) or pin a per-element color.  Most themes need no overrides; the catalog covers every element class out of the box.
4. Add content rules that should override the defaults — federal-holiday tinting, high-priority highlighting, sprint hatching — by appending `apply_to: box:day` (or `box:event`, etc.) entries with `select:` predicates.
5. Add any non-styling configuration you need: format strings under `weekly` / `mini_calendar` / `timeline` / `fiscal`; structural lists under `blockplan.swimlanes` and the shared `time_bands:` catalog; `colors.*_palette` palette names.

Validate before rendering:

```bash
uv run python tools/validate_theme.py config/themes/mytheme.yaml
```

The validator parses the YAML, checks every required key per visualizer, and emits a paste-ready snippet (from `basic.yaml`) for anything missing.

### External CSS Overrides

Since every SVG element has a semantic CSS class, you can apply external CSS to restyle elements when SVGs are embedded in HTML:

```css
/* Override event name color in embedded SVGs */
.ec-event-name { fill: darkblue; }

/* Hide grid lines */
.ec-grid-line { stroke: none; }
```

CSS class rules override inline SVG presentational attributes due to CSS specificity.

### Theme Resources

The fonts, patterns, and palettes available to themes live outside this document — fonts come from the `fonts/` directory and patterns/palettes are stored in the `calendar.db` SQLite database. Use the bundled discovery commands rather than relying on a static enumeration here:

| Resource | List command | Preview command |
|---|---|---|
| Fonts (~125 registered) | `ecalendar.py fonts` | `ecalendar.py fontsheet [-f NAME]` |
| Patterns (~350 in DB) | `ecalendar.py patterns` | `ecalendar.py patternsheet [-f NAME]` |
| Named colors | `ecalendar.py colors` | `ecalendar.py colorsheet [-f NAME]` |
| Palettes (~600 in DB) | `ecalendar.py palettes` | `ecalendar.py palettesheet NAME` |
| Icons | `ecalendar.py icons` | `ecalendar.py iconsheet [-f NAME]` |

Common entry points to remember:

- **Roboto family** (`Roboto-Regular`, `Roboto-Bold`, `RobotoCondensed-*`, …) is used as the default across themes.
- **JuliaMono** is the default monospace font for the mini calendar day numbers.
- Common palette names: `Greys`, `Pastel1`, `Pastel2`, `Set1`, `Set2`, `Set3`, `Dark2`, `Accent`, `Blues`, `Greens`, `Reds`, `Oranges`, `Purples`, `PuBuGn`, `YlOrRd` (run `palettes` for the full DB list).
- Common pattern names: `diagonal-stripes`, `horizontal-stripes`, `cross-hatch`, `brick-wall`, `circuit-board`, `polka-dots`, `wiggle`, `bamboo`, `temple`, `hexagons` (run `patterns` for the full DB list).

#### Color Value Formats

| Format | Example | Notes |
|---|---|---|
| CSS named color | `"navy"`, `"tomato"`, `"lightgrey"` | Standard CSS color names |
| Hex color | `"#1a2b3c"` | 6-digit hex |
| Palette reference | `"palette:Blues:3"` | `palette:NAME:INDEX` from DB palettes table |
| Transparent | `"none"` | No fill / transparent |

#### Continuation Icons (global theme section)

When a duration event extends beyond the visible date range, the
visualizer clamps the bar to the edge of the range and draws a small
icon at the clipped end to signal that the activity continues. The icon
on the **start** edge is the "before" icon (the duration starts *before*
the visualization start date); the icon on the **end** edge is the
"after" icon (the duration ends *after* the visualization end date).

These icons are shared by `timeline`, `blockplan`, and `compact_plan`,
so they live in a single top-level `continuation:` block in the theme
file rather than under any individual visualizer section.

| Theme key | Type | Default | Explanation |
|---|---|---|---|
| `continuation.show` | `bool` | `true` | Master switch — set to `false` to suppress all continuation icons |
| `continuation.icon_before` | `str` or `[str, str]` | `"arrow-left"` | Icon at the clipped *start* edge. See orientation pairing below. |
| `continuation.icon_after`  | `str` or `[str, str]` | `"arrow-right"` | Icon at the clipped *end* edge. |
| `continuation.icon_height` | `float` | `8.0` | Icon size in points |
| `continuation.icon_color`  | `str` or `null` | `null` | Icon color; `null` inherits the bar / line color |

**Orientation-aware icons.** `icon_before` and `icon_after` accept
either a bare string (used for any orientation) or a two-element
`[horizontal, vertical]` list. Element `[0]` is used by horizontally
oriented visualizers (`compact_plan`, `blockplan`, and a `timeline`
with `orientation: horizontal`); element `[1]` is used by a `timeline`
with `orientation: vertical`. This lets a single theme pair left/right
glyphs for the horizontal case with up/down glyphs for the vertical
case.

```yaml
continuation:
  show: true
  # Bare string — same icon for both orientations.
  icon_before: arrow-left
  icon_after: arrow-right
  icon_height: 8.0
  icon_color: null   # inherit from the bar / line
```

```yaml
continuation:
  show: true
  # Pair — element [1] kicks in when the timeline runs vertical.
  icon_before: [move-left, move-up]
  icon_after:  [move-right, move-down]
  icon_height: 14.0
  icon_color: white
```

**Per-visualizer notes.**

- **`compact_plan`** is horizontal-only and only clips its trailing
  end, so it reads `icon_after` and ignores `icon_before`. It also has
  its own compactplan-scoped `continuation_legend_text` and
  `continuation_section_gap` keys for the legend row it appends below
  the milestone roster (see the `compactplan` rendering section).
- **`blockplan`** is horizontal-only and uses both `icon_before` and
  `icon_after` to mark duration bars whose underlying event extends
  past either side of the visible range.
- **`timeline`** uses both icons. When `timeline.orientation` is
  `horizontal`, element `[0]` of each list is used (left edge for
  before, right edge for after). When `timeline.orientation` is
  `vertical`, element `[1]` is used (top edge for before, bottom edge
  for after).

A theme that wants to override the continuation icon used by
compactplan only — without changing the global keys — can `define
icon:continuation` and bind it to `ec-continuation-icon` via
`element_overrides:`. Token values (`icon`, `size`, `color`) take
precedence over the global `continuation.*` keys.

### Complete Theme Key Reference

> **Note:** the table below is auto-generated from `CalendarConfig`'s field
> docstrings and currently reflects the pre-migration field set. The
> styling-related fields (`*_font_color`, `*_fill_color`, etc.) are no longer
> read from theme files — they live in `style_rules` token definitions. The
> next regeneration of this table (after the `CalendarConfig` strip lands)
> will surface only the non-styling config that remains: format strings,
> geometry, fiscal semantics, palette references, structural lane and band
> lists. For the unified styling vocabulary, see
> [Complex Structures Reference → `style_rules`](#style_rules--unified-visual-styling-rules).

Grouped by visualization type. Within each group, rows are sorted alphabetically by `config field`.

#### `shared`

| Config field | Theme key | Type | Default | Explanation |
|---|---|---|---|---|
| `(meta)` | `theme.description` | `` | `` | Theme description text |
| `(meta)` | `theme.name` | `` | `` | Theme display name |
| `default_missing_icon` | `base.default_missing_icon` | `str | None` | `None` | default missing icon |
| `default_missing_icon_size` | `base.default_missing_icon_size` | `float | None` | `None` | drawn size of that stand-in glyph, in points; `None` keeps it the size of whatever it replaces |
| `desired_font_size` | `base.font_size` | `float | None` | `None` | Base font size fallback |
| `desired_font_size` | `base.size_rule` | `float | None` | `None` | Conditional font sizes by papersize |
| `duration_icon_color` | `durations.icon_color` | `str` | `'navy'` | icon color |
| `duration_notes_color` | `durations.notes_color` | `str` | `'darkgrey'` | notes color |
| `duration_notes_font` | `durations.notes_font` | `str` | `Fonts.RC_LIGHT_ITALIC` | notes font |
| `duration_stroke_dasharray` | `durations.stroke_dasharray` | `str | None` | `None` | stroke dasharray |
| `duration_text_color` | `durations.font_color` | `str` | `'navy'` | font color |
| `duration_text_font` | `durations.font_family` | `str` | `Fonts.RC_LIGHT` | font family |
| `event_icon_color` | `events.icon_color` | `str` | `'navy'` | icon color |
| `event_notes_color` | `events.notes_color` | `str` | `'darkgrey'` | notes color |
| `event_notes_font` | `events.notes_font` | `str` | `Fonts.RC_LIGHT_ITALIC` | notes font |
| `event_text_color` | `events.font_color` | `str` | `'navy'` | font color |
| `event_text_font` | `events.font_family` | `str` | `Fonts.RC_LIGHT` | font family |
| `event_text_font_size` | `events.size_rule` | `float | None` | `None` | Per-papersize event font size rule |
| `fiscal_period_end_label_format` | `fiscal.end_label_format` | `str` | `'{period_short} End'` | end label format |
| `fiscal_period_label_format` | `fiscal.label_format` | `str` | `'{prefix}{period_short}'` | label format |
| `fiscal_year_offset` | `fiscal.year_offset` | `int \| None` | `None` | added to calendar year to get fiscal year; null = auto (+1 for non-January start, 0 for NRF); 0 = same year, 1 = year+1, -1 = year-1 |
| `footer_center_font` | `footer.center.font_family` | `str` | `Fonts.RC_LIGHT` | font family |
| `footer_center_font_color` | `footer.center.font_color` | `str` | `'grey'` | font color |
| `footer_center_font_size` | `footer.center.size_rule` | `float | None` | `None` | Per-papersize footer-center font size rule |
| `footer_left_font_size` | `footer.left.size_rule` | `float | None` | `None` | Per-papersize footer-left font size rule |
| `footer_right_font_size` | `footer.right.size_rule` | `float | None` | `None` | Per-papersize footer-right font size rule |
| `group_colors` | `colors.group_colors` | `list` | `field(default_factory=lambda: ['bisque', 'skyblue', 'lawngreen', 'cyan', 'pur...` | List of group colors |
| `header_center_font` | `header.center.font_family` | `str` | `Fonts.R_BLACK_ITALIC` | font family |
| `header_center_font_color` | `header.center.font_color` | `str` | `'grey'` | font color |
| `header_center_font_size` | `header.center.size_rule` | `float | None` | `None` | Per-papersize header-center font size rule |
| `header_left_font` | `header.left.font_family` | `str` | `Fonts.R_BLACK_ITALIC` | font family |
| `header_left_font_color` | `header.left.font_color` | `str` | `'grey'` | font color |
| `header_left_font_size` | `header.left.size_rule` | `float | None` | `None` | Per-papersize header-left font size rule |
| `header_right_font_size` | `header.right.size_rule` | `float | None` | `None` | Per-papersize header-right font size rule |
| `watermark_image_rotation_angle` | `watermark.image_rotation_angle` | `float` | `0.0` | watermark image rotation angle |
| `item_placement_order` | `events.item_placement_order` | `list[str]` | `field(default_factory=lambda: ['priority'])` | item placement order |
| `margin_bottom` | `layout.margin.bottom` | `float | None` | `None` | Bottom margin; supports points or units like in/mm |
| `margin_left` | `layout.margin.left` | `float | None` | `None` | Left margin; supports points or units like in/mm |
| `margin_right` | `layout.margin.right` | `float | None` | `None` | Right margin; supports points or units like in/mm |
| `margin_top` | `layout.margin.top` | `float | None` | `None` | Top margin; supports points or units like in/mm |
| `theme_company_holiday_opacity` | `colors.company_holiday.opacity` | `float | None` | `None` | Company holiday opacity override (`alpha` accepted as deprecated alias) |
| `theme_company_holiday_color` | `colors.company_holiday.color` | `str | None` | `None` | Company holiday color override |
| `theme_federal_holiday_opacity` | `colors.federal_holiday.opacity` | `float | None` | `None` | Federal holiday opacity override (`alpha` accepted as deprecated alias) |
| `theme_federal_holiday_color` | `colors.federal_holiday.color` | `str | None` | `None` | Federal holiday color override |
| `theme_fiscal_palette` | `colors.fiscal_palette` | `str | None` | `None` | DB palette name for fiscal period colors |
| `theme_fiscal_period_colors` | `colors.fiscal_periods` | `dict[str, str] | None` | `None` | Fiscal period to color map |
| `theme_group_palette` | `colors.group_palette` | `str | None` | `None` | DB palette name for group colors |
| `theme_hash_line_color` | `colors.hash_lines` | `str | None` | `None` | Default hash line color |
| `theme_mini_adjacent_month_color` | `colors.mini_calendar.adjacent_month_color` | `str | None` | `None` | Mini adjacent-month day color override |
| `theme_mini_current_day_color` | `colors.mini_calendar.current_day_color` | `str | None` | `None` | Mini current-day shade override |
| `theme_mini_day_color` | `colors.mini_calendar.day_color` | `str | None` | `None` | Mini day number color override |
| `theme_mini_header_color` | `colors.mini_calendar.header_color` | `str | None` | `None` | Mini weekday header color override |
| `theme_mini_holiday_color` | `colors.mini_calendar.holiday_color` | `str | None` | `None` | Mini holiday day color override |
| `theme_mini_milestone_color` | `colors.mini_calendar.milestone_color` | `str | None` | `None` | Mini milestone marker color override |
| `theme_mini_nonworkday_fill_color` | `colors.mini_calendar.nonworkday_fill_color` | `str | None` | `None` | Mini non-workday cell fill color override |
| `theme_mini_title_color` | `colors.mini_calendar.title_color` | `str | None` | `None` | Mini title color override |
| `theme_mini_week_number_color` | `colors.mini_calendar.week_number_color` | `str | None` | `None` | Mini week number color override |
| `theme_month_palette` | `colors.month_palette` | `str | None` | `None` | DB palette name for month colors |
| `theme_month_colors` | `colors.months` | `dict[str, str] | None` | `None` | Month number to color map (01-12) |
| `theme_resource_group_colors` | `colors.resource_groups` | `dict[str, str] | None` | `None` | Resource-group to color map |
| `theme_special_day_type_colors` | `colors.special_day_types` | `dict[str, str] | None` | `None` | Special-day-type to color map |
| `theme_special_day_color` | `colors.special_day` | `str | None` | `None` | Special day accent color |
| `watermark_text` | `watermark.text` | `str` | `''` | text |
| `watermark_opacity` | `watermark.opacity` | `float` | `0.3` | opacity |
| `watermark_color` | `watermark.color` | `str` | `'white'` | color |
| `watermark_font` | `watermark.font_family` | `str` | `Fonts.R_BLACK` | font family |
| `watermark_resize_mode` | `watermark.resize_mode` | `str` | `'fit'` | "fit" (default) or "stretch" |
| `watermark_rotation_angle` | `watermark.rotation_angle` | `float` | `0.0` | rotation angle |
| `watermark_font_size` | `watermark.font_size` | `int | None` | `None` | font size |

#### `weekly`

| Config field | Theme key | Type | Default | Explanation |
|---|---|---|---|---|
| `day_box_fill_color` | `weekly.day_box.fill_color` | `str` | `'grey'` | fill color |
| `day_box_fill_opacity` | `weekly.day_box.fill_opacity` | `float` | `0.25` | fill opacity |
| `day_box_color` | `weekly.day_box.font_color` | `str` | `'navy'` | font color |
| `day_box_icon_color` | `weekly.day_box.icon_color` | `str` | `'red'` | icon color |
| `day_box_number_color` | `weekly.day_box.number_color` | `str` | `'white'` | number color |
| `day_box_number_font` | `weekly.day_box.number_font` | `str` | `Fonts.R_BLACK` | number font |
| `day_box_stroke_color` | `weekly.day_box.stroke_color` | `str` | `'grey'` | stroke color |
| `day_box_stroke_dasharray` | `weekly.day_box.stroke_dasharray` | `str | None` | `None` | stroke dasharray |
| `day_box_stroke_opacity` | `weekly.day_box.stroke_opacity` | `float` | `0.25` | stroke opacity |
| `day_box_stroke_width` | `weekly.day_box.stroke_width` | `int` | `2` | stroke width |
| `day_name_font` | `weekly.day_names.font_family` | `str` | `Fonts.RC_LIGHT_ITALIC` | font family |
| `day_name_font_color` | `weekly.day_names.font_color` | `str` | `'grey'` | font color |
| `day_name_font_size` | `weekly.day_names.size_rule` | `float | None` | `None` | Per-papersize day-name font size rule |
| `hash_pattern_opacity` | `weekly.day_box.hash_pattern_opacity` | `float` | `0.15` | hash pattern opacity |
| `overflow_indicator_color` | `weekly.overflow.color` | `str` | `'red'` | color |
| `overflow_indicator_icon` | `weekly.overflow.icon` | `str` | `'warningtriangle'` | icon |
| *(rule-based)* | `style_rules` entry with `apply_to: box:overflow` | — | — | Optional halo (fill/stroke/padding) painted behind the overflow icon. See "Style Rules" → Box Properties. |
| `theme_weekly_hash_pattern` | `weekly.day_box.hash_pattern` | `str | None` | `None` | hash pattern |
| *(replaced)* | `style_rules` (top-level) | `list[dict]` | `[]` | Replaces legacy `weekly.day_box.hash_rules`. See Complex Structures Reference. |
| `week_number_font` | `weekly.week_numbers.font_family` | `str` | `Fonts.RC_BOLD` | font family |
| `week_number_font_color` | `weekly.week_numbers.font_color` | `str` | `'grey'` | font color |
| `week_number_font_size` | `weekly.week_numbers.size_rule` | `float | None` | `None` | Per-papersize week-number font size rule |
| `week_number_label_format` | `weekly.week_numbers.label_format` | `str` | `'W{num:02d}'` | label format |

#### `mini`

| Config field | Theme key | Type | Default | Explanation |
|---|---|---|---|---|
| `mini_*_font_size` | `mini_calendar.size_rule` | `` | `` | Per-papersize mini font sizes |
| `mini_adjacent_month_color` | `mini_calendar.adjacent_month_color` | `str` | `'lightgrey'` | Leading/trailing days |
| `mini_cell_bold_font` | `mini_calendar.cell_bold_font` | `str` | `Fonts.R_BOLD` | Bold variant |
| `mini_cell_box_stroke_dasharray` | `mini_calendar.cell_box_stroke_dasharray` | `str | None` | `None` | cell box stroke dasharray |
| `mini_cell_font` | `mini_calendar.cell_font` | `str` | `Fonts.J_REGULAR` | Monospace day number font |
| `mini_cell_font_size` | `mini_calendar.cell_font_size` | `float | None` | `None` | cell font size |
| `mini_circle_milestones` | `mini_calendar.circle_milestones` | `bool` | `True` | Circle milestone day numbers |
| `mini_current_day_color` | `mini_calendar.current_day_color` | `str` | `'lightblue'` | Current day shade color |
| `mini_day_color` | `mini_calendar.day_color` | `str` | `'black'` | Default day number color |
| `mini_day_number_glyphs` | `mini_calendar.day_number_glyphs` | `list[str] \| None` | `None` | Optional explicit glyphs for day numbers 1-31 in SVG mini calendars |
| `mini_day_number_digits` | `mini_calendar.day_number_digits` | `list[str] \| None` | `None` | Optional digit glyph substitutions for SVG mini day numbers |
| *(replaced)* | `style_rules` (top-level) | `list[dict]` | `[]` | Replaces legacy `mini_calendar.day_box.hash_rules`. Mini renderer reads the same top-level `style_rules` filtered by `apply_to: day_box`. |
| `mini_details_*_font_size` | `mini_details.size_rule` | `` | `` | Per-papersize mini-details font sizes |
| `mini_details_column_widths` | `mini_details.column_widths` | `list[float]` | `field(default_factory=lambda: [0.16, 0.52, 0.1, 0.1, 0.12])` | column widths |
| `mini_details_header_color` | `mini_details.header_color` | `str` | `'grey'` | header color |
| `mini_details_header_font` | `mini_details.header_font` | `str` | `Fonts.RC_BOLD` | header font |
| `mini_details_headers` | `mini_details.headers` | `list[str]` | `field(default_factory=lambda: ['Start Date', 'Name / Description', 'Milestone...` | headers |
| `mini_details_notes_color` | `mini_details.notes_color` | `str` | `'darkgrey'` | notes color |
| `mini_details_notes_font` | `mini_details.notes_font` | `str` | `Fonts.RC_LIGHT_ITALIC` | notes font |
| `mini_details_notes_font_size` | `mini_details.notes_font_size` | `float | None` | `None` | notes font size |
| `mini_details_output_suffix` | `mini_details.output_suffix` | `str` | `'_details'` | output suffix |
| `mini_details_row_color` | `mini_details.row_color` | `str` | `'black'` | row color |
| `mini_details_row_font` | `mini_details.row_font` | `str` | `Fonts.RC_LIGHT` | row font |
| `mini_details_row_font_size` | `mini_details.row_font_size` | `float | None` | `None` | row font size |
| `mini_details_separator_stroke_dasharray` | `mini_details.separator_stroke_dasharray` | `str | None` | `None` | separator stroke dasharray |
| `mini_details_title_color` | `mini_details.title_color` | `str` | `'navy'` | title color |
| `mini_details_title_font` | `mini_details.title_font` | `str` | `Fonts.RC_BOLD` | title font |
| `mini_details_title_font_size` | `mini_details.title_font_size` | `float | None` | `None` | title font size |
| `mini_details_title_text` | `mini_details.title_text` | `str` | `'Event Details'` | title text |
| `mini_duration_bar_stroke_dasharray` | `mini_calendar.duration_bar_stroke_dasharray` | `str | None` | `None` | duration bar stroke dasharray |
| `mini_duration_bar_stroke_opacity` | `mini_calendar.duration_bar_stroke_opacity` | `float` | `0.7` | duration bar stroke opacity |
| `mini_grid_lines` | `mini_calendar.grid_lines` | `bool` | `False` | Draw a stroked outline around every day cell (also enabled by `--mini-grid-lines`) |
| `mini_grid_line_color` | `mini_calendar.grid_line_color` | `str` | `'lightgrey'` | mini grid line stroke color |
| `mini_grid_line_opacity` | `mini_calendar.grid_line_opacity` | `float` | `0.5` | mini grid line stroke opacity |
| `mini_grid_line_width` | `mini_calendar.grid_line_width` | `float` | `0.25` | mini grid line stroke width |
| `mini_grid_line_dasharray` | `mini_calendar.grid_line_dasharray` | `str | None` | `None` | grid line stroke dasharray |
| `mini_month_outline_color` | `mini_calendar.month_outline_color` | `str | None` | `None` | Outline color drawn around each entire month grid; `None` disables the outline |
| `mini_month_outline_width` | `mini_calendar.month_outline_width` | `float` | `0.5` | Month outline stroke width in points |
| `mini_month_outline_opacity` | `mini_calendar.month_outline_opacity` | `float` | `1.0` | Month outline stroke opacity (0–1) |
| `mini_month_outline_dasharray` | `mini_calendar.month_outline_dasharray` | `str | None` | `None` | Month outline stroke dasharray |
| `mini_hash_line_dasharray` | `mini_calendar.hash_line_dasharray` | `str | None` | `None` | hash line stroke dasharray |
| `mini_header_color` | `mini_calendar.header_color` | `str` | `'grey'` | header color |
| `mini_header_font` | `mini_calendar.header_font` | `str` | `Fonts.J_REGULAR` | Day-of-week header font |
| `mini_header_font_size` | `mini_calendar.header_font_size` | `float | None` | `None` | header font size |
| `mini_holiday_color` | `mini_calendar.holiday_color` | `str` | `'red'` | Holiday day number color |
| `mini_milestone_color` | `mini_calendar.milestone_color` | `str` | `'navy'` | Milestone circle color |
| `mini_milestone_stroke_color` | `mini_calendar.milestone_stroke_color` | `str` | `'navy'` | Milestone circle stroke color |
| `mini_milestone_stroke_opacity` | `mini_calendar.milestone_stroke_opacity` | `float` | `1.0` | Milestone circle stroke opacity |
| `mini_milestone_stroke_width` | `mini_calendar.milestone_stroke_width` | `float` | `1.0` | Milestone circle stroke width |
| `mini_nonworkday_fill_color` | `mini_calendar.nonworkday_fill_color` | `str` | `'lightblue'` | Non-work day fill color |
| `mini_show_adjacent` | `mini_calendar.show_adjacent` | `bool` | `True` | Show leading/trailing adjacent-month days |
| `mini_strikethrough_stroke_dasharray` | `mini_calendar.strikethrough_stroke_dasharray` | `str | None` | `None` | strikethrough stroke dasharray |
| `mini_title_color` | `mini_calendar.title_color` | `str` | `'navy'` | title color |
| `mini_title_font` | `mini_calendar.title_font` | `str` | `Fonts.RC_BOLD` | Month title font |
| `mini_title_font_size` | `mini_calendar.title_font_size` | `float | None` | `None` | title font size |
| `mini_title_format` | `mini_calendar.title_format` | `str` | `'MMMM YYYY'` | Arrow format string for title |
| `mini_week_number_color` | `mini_calendar.week_number_color` | `str` | `'black'` | Color for week numbers |
| `mini_week_number_font` | `mini_calendar.week_number_font` | `str` | `Fonts.J_REGULAR` | Font for week numbers |
| `mini_week_number_font_size` | `mini_calendar.week_number_font_size` | `float | None` | `None` | Week number font size |
| `mini_week_number_label_format` | `mini_calendar.week_number_label_format` | `str` | `'W{num}'` | week number label format |

#### `mini-icon`

`mini-icon` shares all theme keys from the `mini` section above — every `mini_calendar.*` theme key applies identically, because `MiniIconRenderer` subclasses the mini renderer and only swaps day numbers for glyphs. One key is used by `mini-icon` alone:

| Config field | Theme key | Type | Default | Explanation |
|---|---|---|---|---|
| `mini_icon_set` | `mini_calendar.icon_set` | `str` | `'squares'` | Icon set used for day-number icons. Choices: `squares`, `darksquare`, `circles`, `darkcircles`, `squircles`, `darksquircles`. `--mini-icon-set` / `-mis` overrides the theme. |

#### `text-mini`

| Config field | Theme key | Type | Default | Explanation |
|---|---|---|---|---|
| `text_mini_cell_width` | `text_mini.cell_width` | `int` | `2` | cell width |
| `text_mini_day_number_digits` | `text_mini.day_number_digits` | `list[str]` | `field(default_factory=lambda: ['\U0001ccf0', '\U0001ccf1', '\U0001ccf2', '\U0...` | day number digits |
| `text_mini_duration_fill` | `text_mini.duration_fill` | `str` | `'■'` | duration fill |
| `text_mini_duration_symbols` | `text_mini.duration_symbols` | `list[str]` | `field(default_factory=lambda: ['❶', '❷', '❸', '❹', '❺', '❻', '❼', '❽', '❾', '...` | duration symbols |
| `text_mini_event_symbols` | `text_mini.event_symbols` | `list[str]` | `field(default_factory=lambda: ['⚐', '⚑', '⛿', '⛳'])` | event symbols |
| `text_mini_holiday_symbols` | `text_mini.holiday_symbols` | `list[str]` | `field(default_factory=lambda: ['🅰', '🅱', '🅲', '🅳', '🅴', '🅵', '🅶', '🅷', '🅸', '...` | holiday symbols |
| `text_mini_milestone_symbols` | `text_mini.milestone_symbols` | `list[str]` | `field(default_factory=lambda: ['Ⅰ', 'Ⅱ', 'Ⅲ', 'Ⅳ', 'Ⅴ', 'Ⅵ', 'Ⅶ', 'Ⅷ', 'Ⅸ', '...` | milestone symbols |
| `text_mini_month_gap` | `text_mini.month_gap` | `int` | `4` | month gap |
| `text_mini_nonworkday_symbols` | `text_mini.nonworkday_symbols` | `list[str]` | `field(default_factory=lambda: ['𝒂', '𝒃', '𝒄', '𝒅', '𝒆', '𝒇', '𝒈', '𝒉', '𝒊', '...` | nonworkday symbols |
| `text_mini_week_number_digits` | `text_mini.week_number_digits` | `list[str]` | `field(default_factory=lambda: ['⁰', '¹', '²', '³', '⁴', '⁵', '⁶', '⁷', '⁸', '...` | week number digits |

#### `timeline`

| Config field | Theme key | Type | Default | Explanation |
|---|---|---|---|---|
| `theme_timeline_palette` | `timeline.palette` | `str | None` | `None` | palette |
| `timeline_axis_color` | `timeline.axis_color` | `str` | `'lightgrey'` | axis color |
| `timeline_axis_opacity` | `timeline.axis_opacity` | `float` | `0.85` | axis opacity |
| `timeline_axis_stroke_dasharray` | `timeline.axis_stroke_dasharray` | `str | None` | `None` | axis stroke dasharray |
| `timeline_axis_width` | `timeline.axis_width` | `float` | `2.0` | axis width |
| `timeline_background_color` | `timeline.background_color` | `str` | `'none'` | background color |
| `timeline_bottom_colors` | `timeline.bottom_colors` | `list[str]` | `field(default_factory=lambda: ['midnightblue', 'springgreen', 'deepskyblue', ...` | bottom colors |
| `timeline_connector_stroke_dasharray` | `timeline.connector_stroke_dasharray` | `str | None` | `None` | connector stroke dasharray |
| `timeline_date_color` | `timeline.date.font_color` | `str` | `'deepskyblue'` | font color |
| `timeline_date_font` | `timeline.date.font_family` | `str` | `Fonts.R_BOLD` | font family |
| `timeline_date_format` | `timeline.date_format` | `str` | `'MMM D'` | date format |
| `timeline_duration_*_font_size` | `timeline_durations.size_rule` | `` | `` | Per-papersize timeline duration font sizes |
| `timeline_duration_bar_stroke_dasharray` | `timeline.duration_bar_stroke_dasharray` | `str | None` | `None` | duration bar stroke dasharray |
| `timeline_duration_box_height` | `timeline_durations.box_height` | `float | None` | `None` | box height |
| `timeline_duration_box_width` | `timeline_durations.box_width` | `float | None` | `None` | box width |
| `timeline_duration_bracket_stroke_dasharray` | `timeline.duration_bracket_stroke_dasharray` | `str | None` | `None` | duration bracket stroke dasharray |
| `timeline_duration_date_color` | `timeline_durations.date_color` | `str | None` | `None` | date color |
| `timeline_duration_date_font` | `timeline_durations.date_font` | `str | None` | `None` | date font |
| `timeline_duration_date_font_size` | `timeline_durations.date_font_size` | `float | None` | `None` | date font size |
| `timeline_duration_lane_gap_y` | `timeline.duration_lane_gap_y` | `float` | `8.0` | duration lane gap y |
| `timeline_wbs_group_depth` | `timeline.wbs_group_depth` | `int` | `2` | leading WBS segments that group chart items: every event, milestone and duration bar in a group takes one color from `timeline.top_colors`, and bars in a group sort together. `0` disables grouping, leaving each layout to cycle its own palette per item. Also accepted at its original key, `timeline_durations.wbs_group_depth` |
| `timeline_duration_name_font_size` | `timeline_durations.name_font_size` | `float | None` | `None` | name font size |
| `timeline_duration_notes_font_size` | `timeline_durations.notes_font_size` | `float | None` | `None` | notes font size |
| `timeline_duration_offset_y` | `timeline.duration_offset_y` | `float` | `44.0` | duration offset y |
| `timeline_duration_text_color` | `timeline_durations.text_color` | `str | None` | `None` | text color |
| `timeline_event_*_font_size` | `timeline_events.size_rule` | `` | `` | Per-papersize timeline event font sizes |
| `timeline_event_box_height` | `timeline_events.box_height` | `float | None` | `None` | box height |
| `timeline_event_box_width` | `timeline_events.box_width` | `float | None` | `None` | box width. `None` sizes each callout from its own text, so the boxes come out ragged; every shipped theme pins a value so one timeline's boxes share a width |
| `timeline_event_name_font_size` | `timeline_events.name_font_size` | `float | None` | `None` | name font size |
| `timeline_event_notes_font_size` | `timeline_events.notes_font_size` | `float | None` | `None` | notes font size |
| `timeline_event_text_color` | `timeline_events.text_color` | `str | None` | `None` | text color |
| `timeline_holiday_date_color` | `timeline.holiday_date_color` | `str | None` | `None` | holiday date color; falls back to the icon color, then the tick color |
| `timeline_holiday_date_font_size` | `timeline.holiday_date_font_size` | `float | None` | `None` | holiday date font size; defaults to 0.68 x the icon size |
| `timeline_holiday_date_format` | `timeline.holiday_date_format` | `str | None` | `None` | holiday date format; falls back to `timeline.date_format` |
| `timeline_holiday_icon_color` | `timeline.holiday_icon_color` | `str | None` | `None` | holiday icon color; `None` keeps the icon's own colors |
| `timeline_holiday_icon_size` | `timeline.holiday_icon_size` | `float` | `10.0` | holiday icon size |
| `timeline_holiday_icon_y_offset` | `timeline.holiday_icon_y_offset` | `float` | `4.0` | gap below the axis to the top of the holiday icon |
| `timeline_icon_size` | `timeline.icon_size` | `float` | `8.0` | icon size |
| `timeline_label_fill_opacity` | `timeline.label_fill_opacity` | `float` | `0.25` | label fill opacity |
| `timeline_label_stroke_dasharray` | `timeline.label_stroke_dasharray` | `str | None` | `None` | label stroke dasharray |
| `timeline_label_stroke_width` | `timeline.label_stroke_width` | `float` | `1.0` | label stroke width |
| `timeline_leader_direct` | `timeline.leader.direct` | `bool` | `True` | route each leader straight from its axis dot to its own box. `False` restores labella's routing, which threads it through every ancestor row — a curve-and-line pair per row |
| `timeline_leader_end_stub` | `timeline.leader.end_stub` | `float` | `4.0` | straight perpendicular segment where a callout leader meets its box; `0` = pure bezier |
| `timeline_leader_start_stub` | `timeline.leader.start_stub` | `float` | `4.0` | straight perpendicular segment where a callout leader leaves the axis dot; `0` = pure bezier |
| `timeline_marker_radius` | `timeline.marker_radius` | `float` | `6` | marker radius |
| `timeline_marker_stroke_color` | `timeline.marker_stroke_color` | `str` | `'black'` | marker stroke color |
| `timeline_marker_stroke_width` | `timeline.marker_stroke_width` | `float` | `1.0` | marker stroke width |
| `timeline_notes_color` | `timeline.notes.font_color` | `str` | `'deepskyblue'` | font color |
| `timeline_notes_font` | `timeline.notes.font_family` | `str` | `Fonts.RC_BOLD` | font family |
| `timeline_show_holiday_dates` | `timeline.show_holiday_dates` | `bool` | `True` | print each holiday's date under its icon |
| `timeline_show_holiday_icons` | `timeline.show_holiday_icons` | `bool` | `True` | draw the government-holiday icon row below the axis |
| `timeline_tick_color` | `timeline.tick_color` | `str` | `'grey'` | tick color |
| `timeline_tick_label_format` | `timeline.tick_label_format` | `str` | `'MMM D'` | tick label format |
| `timeline_tick_stroke_dasharray` | `timeline.tick_stroke_dasharray` | `str | None` | `None` | tick stroke dasharray |
| `timeline_title_color` | `timeline.title.font_color` | `str` | `'deepskyblue'` | font color |
| `timeline_title_font` | `timeline.title.font_family` | `str` | `Fonts.R_BOLD` | font family |
| `timeline_today_date` | `timeline.today_date` | `str` | `''` | today date |
| `timeline_today_label_color` | `timeline.today_label_color` | `str` | `'grey'` | today label color |
| `timeline_today_label_offset_y` | `timeline.today_label_offset_y` | `float` | `10.0` | today label offset y |
| `timeline_today_label_text` | `timeline.today_label_text` | `str` | `'Today'` | today label text |
| `timeline_today_line_color` | `timeline.today_line_color` | `str` | `'grey'` | today line color |
| `timeline_today_line_dasharray` | `timeline.today_line_dasharray` | `str | None` | `None` | today line stroke dasharray |
| `timeline_top_colors` | `timeline.top_colors` | `list[str]` | `field(default_factory=lambda: ['deepskyblue', 'gold', 'tomato', 'springgreen'...` | top colors |

#### `blockplan`

| Config field | Theme key | Type | Default | Explanation |
|---|---|---|---|---|
| `blockplan_*_font_size` | `blockplan.size_rule` | `` | `` | Per-papersize blockplan font sizes |
| `blockplan_background_color` | `blockplan.background_color` | `str` | `'none'` | background color |
| `blockplan_band_font` | `blockplan.band_font` | `str` | `Fonts.RC_BOLD` | band font |
| `blockplan_band_font_size` | `blockplan.band_font_size` | `float | None` | `None` | band font size |
| `blockplan_band_row_height` | `blockplan.band_row_height` | `float` | `10.0` | band row height |
| `blockplan_bottom_time_bands` | `blockplan.bottom_time_bands` | `list[dict]` | `[]` | time-band rows rendered below swimlanes; same structure as top_time_bands |
| `blockplan_duration_bar_height` | `blockplan.duration_bar_height` | `float` | `8.0` | duration bar height |
| `blockplan_duration_color` | `blockplan.duration_color` | `str` | `'navy'` | duration color |
| `blockplan_duration_date_color` | `blockplan.duration_date_color` | `str \| None` | `None` | start/end date label color; null = duration_color |
| `blockplan_duration_date_font` | `blockplan.duration_date_font` | `str` | `'RobotoCondensed-LightItalic'` | date label font |
| `blockplan_duration_date_font_size` | `blockplan.duration_date_font_size` | `float \| None` | `None` | date label font size |
| `blockplan_duration_date_format` | `blockplan.duration_date_format` | `str` | `'M/D'` | Arrow date format for start/end labels |
| `blockplan_duration_fill_opacity` | `blockplan.duration_fill_opacity` | `float` | `0.35` | duration fill opacity |
| `blockplan_duration_font` | `blockplan.duration_font` | `str` | `Fonts.RC_LIGHT` | duration font |
| `blockplan_duration_font_size` | `blockplan.duration_font_size` | `float \| None` | `None` | duration font size |
| `blockplan_duration_icon_visible` | `blockplan.duration_icon_visible` | `bool` | `False` | show event icon inside duration bar when available |
| `blockplan_duration_notes_color` | `blockplan.duration_notes_color` | `str \| None` | `None` | notes text color; null = durations.notes_color |
| `blockplan_duration_show_end_date` | `blockplan.duration_show_end_date` | `bool` | `False` | show end date below bar right edge |
| `blockplan_duration_show_start_date` | `blockplan.duration_show_start_date` | `bool` | `False` | show start date below bar left edge |
| `blockplan_duration_stroke_color` | `blockplan.duration_stroke_color` | `str \| None` | `None` | bar border color; null = no border |
| `blockplan_duration_stroke_dasharray` | `blockplan.duration_stroke_dasharray` | `str \| None` | `None` | bar border dash pattern |
| `blockplan_duration_stroke_opacity` | `blockplan.duration_stroke_opacity` | `float` | `1.0` | bar border opacity |
| `blockplan_duration_stroke_width` | `blockplan.duration_stroke_width` | `float` | `1.0` | bar border width in points |
| `blockplan_duration_text_color` | `blockplan.duration_text_color` | `str \| None` | `None` | bar label text color; null = durations.font_color |
| `blockplan_event_color` | `blockplan.event_color` | `str` | `'navy'` | event color |
| `blockplan_event_date_color` | `blockplan.event_date_color` | `str` | `'grey'` | event date color |
| `blockplan_event_date_font` | `blockplan.event_date_font` | `str` | `Fonts.RC_LIGHT` | event date font |
| `blockplan_event_date_font_size` | `blockplan.event_date_font_size` | `float | None` | `None` | event date font size |
| `blockplan_event_date_format` | `blockplan.event_date_format` | `str` | `'YYYY-MM-DD'` | event date format |
| `blockplan_event_font` | `blockplan.event_font` | `str` | `Fonts.RC_LIGHT` | event font |
| `blockplan_event_font_size` | `blockplan.event_font_size` | `float | None` | `None` | event font size |
| `blockplan_event_show_date` | `blockplan.event_show_date` | `bool` | `False` | event show date |
| `blockplan_fiscal_year_start_month` | `blockplan.fiscal_year_start_month` | `int` | `10` | fiscal year start month |
| `blockplan_grid_color` | `blockplan.grid_color` | `str` | `'grey'` | grid color |
| `blockplan_grid_dasharray` | `blockplan.grid_dasharray` | `str \| None` | `None` | swimlane border dash pattern |
| `blockplan_grid_line_width` | `blockplan.grid_line_width` | `float` | `1.0` | swimlane border line width in points |
| `blockplan_grid_opacity` | `blockplan.grid_opacity` | `float` | `0.6` | grid opacity |
| `blockplan_header_font` | `blockplan.header_font` | `str` | `Fonts.RC_BOLD` | header font |
| `blockplan_header_font_size` | `blockplan.header_font_size` | `float | None` | `None` | header font size |
| `blockplan_header_heading_fill_color` | `blockplan.header_heading_fill_color` | `str` | `'none'` | header heading fill color |
| `blockplan_header_label_align_h` | `blockplan.header_label_align_h` | `str` | `'left'` | left \| center \| right |
| `blockplan_header_label_color` | `blockplan.header_label_color` | `str` | `'black'` | header label color |
| `blockplan_header_label_opacity` | `blockplan.header_label_opacity` | `float` | `1.0` | heading cell label text opacity |
| `blockplan_label_column_ratio` | `blockplan.label_column_ratio` | `float` | `0.16` | label column ratio |
| `blockplan_lane_heading_fill_color` | `blockplan.lane_heading_fill_color` | `str` | `'none'` | lane heading fill color |
| `blockplan_lane_label_align_h` | `blockplan.lane_label_align_h` | `str` | `'left'` | left \| center \| right |
| `blockplan_lane_label_align_v` | `blockplan.lane_label_align_v` | `str` | `'middle'` | top \| middle \| bottom |
| `blockplan_lane_label_color` | `blockplan.lane_label_color` | `str \| None` | `None` | lane label text color per-lane override; null = lane_label_color global |
| `blockplan_lane_label_font` | `blockplan.lane_label_font` | `str` | `Fonts.RC_BOLD` | lane label font |
| `blockplan_lane_label_font_size` | `blockplan.lane_label_font_size` | `float \| None` | `None` | lane label font size |
| `blockplan_lane_label_rotation` | `blockplan.lane_label_rotation` | `float` | `0` | lane label clockwise rotation in degrees; 0=horizontal, -90=bottom-to-top, 90=top-to-bottom |
| `blockplan_lane_match_mode` | `blockplan.lane_match_mode` | `str` | `'first'` | "first" or "all" |
| `blockplan_lane_split_ratio` | `blockplan.lane_split_ratio` | `float` | `0.5` | fraction of lane height for upper content section (0.0–1.0); 0.0 removes the divider |
| `blockplan_marker_radius` | `blockplan.marker_radius` | `float` | `2.0` | marker radius |
| `blockplan_palette` | `blockplan.palette` | `list[str]` | `field(default_factory=lambda: ['lightskyblue', 'gold', 'tomato', 'springgreen...` | palette |
| `blockplan_show_unmatched_lane` | `blockplan.show_unmatched_lane` | `bool` | `True` | show unmatched lane |
| `blockplan_swimlanes` | `blockplan.swimlanes` | `list[dict[str, Any]]` | see default | Lane visual definitions only. Routing is handled by top-level `swimlane_rules`. |
| *(new)* | `swimlane_rules` (top-level) | `list[dict]` | `[]` | Blockplan lane routing: `select:` + `apply_to: "lane name"`. First match wins. See Complex Structures Reference. |
| `blockplan_time_bands` | `blockplan.time_bands` | `list[dict[str, Any]]` | `field(default_factory=lambda: [{'label': 'Fiscal Quarter', 'unit': 'fiscal_qu...` | time bands |
| `blockplan_top_time_bands` | `blockplan.top_time_bands` | `list[dict]` | see default | time-band rows rendered above swimlanes; see Complex Structures Reference |
| `blockplan_timeband_fill_color` | `blockplan.timeband_fill_color` | `str` | `'none'` | timeband fill color |
| `blockplan_timeband_fill_opacity` | `blockplan.timeband_fill_opacity` | `float` | `1.0` | timeband fill opacity |
| `blockplan_timeband_fill_palette` | `blockplan.timeband_fill_palette` | `list[str]` | `field(default_factory=list)` | timeband fill palette |
| `blockplan_timeband_label_color` | `blockplan.timeband_label_color` | `str` | `'black'` | timeband label color |
| `blockplan_timeband_label_opacity` | `blockplan.timeband_label_opacity` | `float` | `1.0` | segment label text opacity |
| `blockplan_timeband_line_color` | `blockplan.timeband_line_color` | `str \| None` | `None` | time-band cell border color; null = grid_color |
| `blockplan_timeband_line_dasharray` | `blockplan.timeband_line_dasharray` | `str \| None` | `None` | time-band border dash pattern; null = grid_dasharray |
| `blockplan_timeband_line_opacity` | `blockplan.timeband_line_opacity` | `float \| None` | `None` | time-band border opacity; null = grid_opacity |
| `blockplan_timeband_line_width` | `blockplan.timeband_line_width` | `float \| None` | `None` | time-band border line width; null = grid_line_width |
| `blockplan_unmatched_lane_name` | `blockplan.unmatched_lane_name` | `str` | `'Unmatched'` | unmatched lane name |
| `blockplan_vertical_line_color` | `blockplan.vertical_line_color` | `str` | `'red'` | vertical line color |
| `blockplan_vertical_line_dasharray` | `blockplan.vertical_line_dasharray` | `str \| None` | `None` | vertical line dasharray |
| `blockplan_vertical_line_fill_color` | `blockplan.vertical_line_fill_color` | `str` | `'none'` | default column fill color for vertical lines |
| `blockplan_vertical_line_fill_opacity` | `blockplan.vertical_line_fill_opacity` | `float` | `0.15` | default column fill opacity |
| `blockplan_vertical_line_opacity` | `blockplan.vertical_line_opacity` | `float` | `0.9` | vertical line opacity |
| `blockplan_vertical_line_width` | `blockplan.vertical_line_width` | `float` | `1.5` | vertical line width |
| *(replaced)* | `style_rules` (top-level) | `list[dict]` | `[]` | Replaces legacy `blockplan.vertical_lines` — see Complex Structures Reference (`apply_to: vertical_line`). |
| `blockplan_week_start` | `blockplan.week_start` | `int` | `0` | 0=Monday |
| `theme_blockplan_palette_name` | `blockplan.palette_name` | `str | None` | `None` | palette name |


#### `excelheader`

| Config field | Theme key | Type | Default | Explanation |
|---|---|---|---|---|
| `excelheader_band_row_height` | `excelheader.band_row_height` | `float` | `18.0` | default timeband row height in points |
| `excelheader_font` | `excelheader.font_name` | `str` | `'Calibri'` | system-installed Excel font for all cells |
| `excelheader_font_size` | `excelheader.font_size` | `int` | `9` | default font size in points |
| `excelheader_header_heading_fill_color` | `excelheader.header_heading_fill_color` | `str` | `'none'` | heading cell (A:E) background color |
| `excelheader_header_label_align_h` | `excelheader.header_label_align_h` | `str` | `'left'` | heading cell alignment: left \| center \| right |
| `excelheader_header_label_color` | `excelheader.header_label_color` | `str` | `'black'` | heading cell label color |
| `excelheader_timeband_fill_color` | `excelheader.timeband_fill_color` | `str` | `'none'` | default segment fill color |
| `excelheader_timeband_fill_palette` | `excelheader.timeband_fill_palette` | `list[str]` | `[]` | palette names cycling across segments |
| `excelheader_timeband_label_color` | `excelheader.timeband_label_color` | `str` | `'black'` | default segment label color |
| `excelheader_top_time_bands` | `excelheader.top_time_bands` | `list[dict]` | see default | timeband rows; same schema as blockplan.top_time_bands |
| `excelheader_vertical_line_color` | `excelheader.vertical_line_color` | `str` | `'red'` | default vertical line color |
| `excelheader_vertical_line_dasharray` | `excelheader.vertical_line_dasharray` | `str \| None` | `None` | default vertical line dash pattern |
| `excelheader_vertical_line_fill_color` | `excelheader.vertical_line_fill_color` | `str` | `'none'` | default column fill color |
| `excelheader_vertical_line_fill_opacity` | `excelheader.vertical_line_fill_opacity` | `float` | `0.2` | default column fill opacity |
| `excelheader_vertical_line_opacity` | `excelheader.vertical_line_opacity` | `float` | `0.9` | default vertical line opacity |
| `excelheader_vertical_line_width` | `excelheader.vertical_line_width` | `float` | `1.5` | default vertical line width |
| `excelheader_vertical_lines` | `excelheader.vertical_lines` | `list[dict]` | `[]` | vertical lines rendered as right-cell borders |


#### `excelblockplan`

The dedicated `excelblockplan_*` theme fields were removed in 2026-07 —
the exporter never read them. Styling for the data-sheet variant follows
the `excelheader` settings (fonts, band placement, holiday colors), which
both Excel exports share.



## Complex Structures Reference

### `style_rules` — Unified Visual Styling Rules

`style_rules` is the only styling section. Each entry is a rule with three keys:

- **`select:`** — predicates (day context, event criteria, band segment, paper size, visualizer scope). An empty `select` matches everything; otherwise every constraint must be satisfied for the rule to apply.
- **`apply_to:`** — the target surface(s) to style. Accepts a single target or a list.
- **`style:`** — properties to set.

Rules are evaluated **in declaration order**. For token resolution and content surfaces, the **last matching rule wins** — later rules layer on top of earlier ones. For `apply_to: lane`, **first match wins** (lane assignment is a discrete choice, not a layered attribute).

A rule with a `define:` key creates a named token instead of styling a surface; the token becomes referenceable as `<kind>:<name>`.

```yaml
style_rules:

  - name: define text:day_number
    define: text
    as: day_number
    style: { font: Roboto-Bold, size: 11, color: black }

  - name: Federal Holidays
    apply_to: box:day
    select: { federal_holiday: true }
    style:
      fill: tomato
      fill_opacity: 0.10
      pattern: diagonal-stripes
      pattern_color: tomato
      pattern_opacity: 0.12

  - name: Sprint Durations
    apply_to: box:duration
    select:
      task_name: [Sprint]
      event_type: duration
    style:
      fill: steelblue
      stroke: white
      stroke_width: 1.0

  - name: Sprint Duration Name
    apply_to: text:event_name
    select:
      task_name: [Sprint]
      event_type: duration
    style: { color: white, font: OfficinaSans-Bold }

  - name: Priority 1 — box outline
    apply_to: [box:event, box:duration]
    select: { priority: 1 }
    style: { stroke: crimson, stroke_width: 1.5 }

  - name: Priority 1 — event name
    apply_to: text:event_name
    select: { priority: 1 }
    style: { color: crimson, font: OfficinaSans-Bold }
```

#### `apply_to:` — Targets

| Target | What gets styled |
|---|---|
| `text:<name>` | A text token (`text:heading`, `text:event_name`, `text:milestone_label`, …) |
| `box:<name>` | A box token. Canonical names: `box:day`, `box:event`, `box:duration`, `box:overflow`, `box:vline`, `box:milestone`, `box:swimlane_heading`, `box:swimlane_content`, `box:band`, plus shared `box:cell`/`box:header`/`box:callout`/`box:default`. |
| `line:<name>` | A line token (`line:grid`, `line:axis`, `line:today`, …) |
| `icon:<name>` | An icon token (`icon:event`, `icon:milestone`, `icon:overflow`, …) |
| `lane` | Route content to a swimlane via `style.swimlane` (blockplan) |

`apply_to: element` is no longer accepted in themes — element-to-token bindings live in [`config/element_catalog.yaml`](config/element_catalog.yaml).  Use the top-level `element_overrides:` map for per-theme tweaks (see "Element Bindings: built-in catalog" earlier).

A list-valued `apply_to:` fans the rule out: each style property is routed to every listed target that recognizes it. Unrecognized keys for a given target are silently dropped per-target.

#### `select:` — Day / Context Criteria

Use these on rules targeting `box:day`, and as filters on event-targeted rules.

| Key | Type | Description |
|---|---|---|
| `federal_holiday` | `bool` | Government holiday with nonworkday=1 |
| `company_holiday` | `bool` | Company special day with nonworkday=1 |
| `nonworkday` | `bool` | Any of the above, or weekend |
| `workday` | `bool` | Not nonworkday |
| `weekend` | `bool` | Falls on config weekend days |
| `date` | `str \| list` | Single `YYYYMMDD`, closed range `YYYYMMDD-YYYYMMDD`, or list of dates |
| `papersize` | `str \| list` | One of the recognized paper sizes (`letter`, `tabloid`, `3x5`, …) |
| `visualizer` | `str \| list` | Limit a rule to specific visualizers (`weekly`, `mini`, `timeline`, `blockplan`, `compactplan`) |

#### `select:` — Event Criteria

Matched against the data attached to the event/duration/milestone being drawn. All specified criteria must match (AND).

| Key | Type | Match style |
|---|---|---|
| `task_name` | `str \| list` | Substring (case-insensitive) |
| `notes` | `str \| list` | Substring |
| `resource_group` | `str \| list` | Case-insensitive exact |
| `resource_names` | `str \| list` | Substring (comma-split field) |
| `wbs` | `str` | `WBSFilter` expression: comma-separated tokens; `!` excludes; `*` matches one segment, `**` matches any remaining |
| `priority` | `int \| list` | Exact |
| `priority_min` / `priority_max` | `int` | Inclusive range |
| `percent_complete` | `int \| {min, max}` | Exact or range |
| `milestone` | `bool` | Flag field |
| `rollup` | `bool` | Flag field |
| `event_type` | `event \| duration \| any` | Point vs span vs either |
| `color` | `str` | Exact match on `Event.color` |
| `icon` | `str` | Exact match on `Event.icon` |
| `date_overlap` | `bool` | When `true`, `date` matches durations whose span overlaps the date/range (default: matches start date only) |

#### `select:` — Band Segment Criteria (for `apply_to: box:vline` and band rules)

| Key | Type | Description |
|---|---|---|
| `band` | `str` | Time-band catalog key (e.g. `month`, `fiscal_quarter`). Required for band-anchored rules. |
| `value` | `str` | Segment label to match when `repeat` is absent or false. |
| `repeat` | `bool` | When `true`, every segment in the band matches; `value` is ignored. |
| `swimlane` | `str` | Lane catalog name (used for `box:swimlane_*` and `text:swimlane_label` rules). |

#### `select:` — Aggregation Modifiers (for `apply_to: box:day`)

| Key | Default | Meaning |
|---|---|---|
| `min_match` | `1` | Minimum number of event criteria that must be true |
| `any_event` | `true` | Passes if *any* event on the day matches event criteria |
| `all_events` | `false` | Passes only if *all* events match |

#### `style:` — Box Properties (recognized by every `box:<name>` target)

| Property | Notes |
|---|---|
| `fill` | Scalar color, `none`, or list (list cycles across repeating instances) |
| `fill_opacity` | 0–1 |
| `fill_palette` | DB palette name (cycled across instances) |
| `fill_colors` | Explicit color list (cycled across instances) — takes priority over `fill_palette` |
| `stroke` | Border color |
| `stroke_width` | Border width in points |
| `stroke_opacity` | 0–1 |
| `dasharray` | SVG dash pattern, e.g. `"4 2"` |
| `pattern` | DB pattern name |
| `pattern_color` | Colorizes the pattern |
| `pattern_opacity` | 0–1 |
| `align` | `start` \| `center` \| `end` (placement hint for `box:vline`) |
| `padding` | Halo inset (in points) for icon halos like `box:milestone`, `box:overflow`. Default `size * 0.1`. |

Halo example for the weekly overflow icon — paint a small ring behind the indicator:

```yaml
- name: overflow halo
  apply_to: box:overflow
  style:
    fill: white
    stroke: red
    stroke_width: 0.5
    padding: 1
```

`box:overflow` is matched once per overflowed day with a single `date` selector context.

#### `style:` — Text Properties (recognized by every `text:<name>` target)

| Property | Notes |
|---|---|
| `font` | Font name from the registry |
| `size` | Point size |
| `color` | Text color |
| `weight` | `normal` \| `bold` |
| `italic` | `true` \| `false` |
| `opacity` | 0–1 |
| `align_h` | `left` \| `center` \| `right` (where meaningful, e.g. swimlane label) |
| `align_v` | `top` \| `middle` \| `bottom` |
| `rotation` | Degrees (for rotated labels) |

#### `style:` — Line Properties (recognized by every `line:<name>` target)

| Property | Notes |
|---|---|
| `color` | Line color |
| `width` | Line width in points |
| `opacity` | 0–1 |
| `dasharray` | SVG dash pattern |

#### `style:` — Icon Properties (recognized by every `icon:<name>` target)

| Property | Notes |
|---|---|
| `icon` | Glyph name (`diamond`, `flag`, `overflow`, …) |
| `color` | Icon color |
| `size` | Icon size in points. **Optional** — when omitted, each visualizer falls back to its own default: weekly event/duration icons use `event_icon_size` (which tracks the event-name text size); compactplan duration icons use `compact_plan.duration_icon_height`; continuation icons (compactplan / blockplan / timeline) use the global `continuation.icon_height`. Declaring `size:` on the bound `icon:` token overrides those defaults. |

#### `element_overrides:` — Per-Theme Element Tweaks

`element_overrides:` is a top-level mapping from `ec-*` class name to a small style bag.  It is the only supported way for a theme to influence the element catalog's bindings.

| Property | Notes |
|---|---|
| `use` | Reference to a token (`text:heading`, `box:cell`, …) that should replace the catalog default for this element. |
| `color` | Per-element color override applied on top of the resolved token. |

A missing entry means the catalog default applies unchanged.

#### `style:` — Lane-Routing Properties (for `apply_to: lane`)

| Property | Notes |
|---|---|
| `swimlane` | Catalog name of the swimlane this rule routes content to. |

#### Multiple targets in one rule

```yaml
style_rules:
  - name: muted completed items
    apply_to: [box:event, box:duration, text:event_name]
    select: { percent_complete: { min: 100 } }
    style:
      fill: "#f4f4f4"          # applies to the box: targets
      color: grey              # applies to text:event_name
      italic: true             # applies to text:event_name
```

Each target consumes only the style keys it recognizes; the others are silently dropped per-target. For property values that differ across targets, write separate rules with the same `select:`.

#### Per-Element Text Styling

To style a specific text role for a matched event/duration, write a rule targeting that text token directly. Example: make event names red for priority-1 events:

```yaml
- apply_to: text:event_name
  select: { priority: 1 }
  style: { color: red, weight: bold }
```

The recognized text-role tokens map to the CSS classes shown earlier:

| Token | CSS class | Where rendered |
|---|---|---|
| `text:event_name` | `ec-event-name` | Point event title (weekly, blockplan, timeline); duration bar / lane label title |
| `text:event_notes` | `ec-event-notes` | Event / duration notes line |
| `text:event_date` | `ec-event-date` | Point event date label |
| `text:duration_date` | `ec-duration-date` | Duration start/end date labels |
| `text:day_number` | `ec-day-number` | Large digit in weekly / mini day box |
| `text:week_number` | `ec-week-number` | Week-number label on row left edge |
| `text:month_title` | `ec-month-title` | Abbreviated month on first day of month |
| `text:holiday_title` | `ec-holiday-title` | Holiday / special day name in day box |
| `text:milestone_label` | (no class) | Text rendered next to a milestone marker |
| `text:swimlane_label` | (no class) | Lane heading text in blockplan |
| `text:band_label` | `ec-band-label` | Time-band segment text |

#### Date Range Matching

The `date` criterion is evaluated against the **day being rendered** for `box:day` rules, and against the **event's start date** for event/duration rules. Use `date_overlap: true` to match durations that overlap a date range rather than start within it.

| Format | Example | Meaning |
|---|---|---|
| Single date | `"20260321"` | Exactly that calendar day |
| Closed range | `"20260301-20260321"` | Start and end inclusive |
| List | `["20260101", "20260704", "20261225"]` | Any of the listed dates |

---

### Lane Routing (Blockplan)

Lane routing lives in `style_rules` with `apply_to: lane`. Each matched rule assigns content to a swimlane by name; **first match wins**. An empty `select: {}` is the catch-all and only useful as the final entry.

```yaml
style_rules:
  - name: Route Xstore
    apply_to: lane
    select: { resource_group: [Xstore] }
    style: { swimlane: "Xstore\nConversions" }

  - name: Route Triversity
    apply_to: lane
    select: { resource_group: [Triversity] }
    style: { swimlane: "Triversity\nPOSReady7" }

  - name: High-priority milestones to top lane
    apply_to: lane
    select: { milestone: true, priority: 1 }
    style: { swimlane: "Key Milestones" }

  - name: Unmatched catch-all
    apply_to: lane
    select: {}
    style: { swimlane: Other }
```

The `style.swimlane` value must match a `name` in `blockplan.swimlanes`. Events that match no rule and have no catch-all are placed into the unmatched lane if `blockplan.show_unmatched_lane: true`, or dropped from the blockplan otherwise.

---

### `swimlanes` — Blockplan Lane Structural Definitions

`blockplan.swimlanes` is the structural list — it declares which lanes exist and the geometric `split_ratio` (events/durations divider position). All *visual* properties (heading fill, content tint, label color, label alignment, label rotation) live in `style_rules` keyed by `select.swimlane: <name>`.

```yaml
blockplan:
  swimlanes:
    - name: "Xstore\nConversions"
      split_ratio: 0.5            # events upper half, durations lower half
    - name: "Key Milestones"
      split_ratio: 0.0            # 0.0 or 1.0 removes the events/durations divider
    - name: Other

style_rules:
  # Heading-cell background for the Xstore lane.
  - apply_to: box:swimlane_heading
    select: { swimlane: "Xstore\nConversions" }
    style: { fill: "#dceaff" }

  # Content-area tint for the Xstore lane.
  - apply_to: box:swimlane_content
    select: { swimlane: "Xstore\nConversions" }
    style: { fill: "#fafbff" }

  # Label color and alignment for the Xstore lane.
  - apply_to: text:swimlane_label
    select: { swimlane: "Xstore\nConversions" }
    style:
      color: red
      align_h: center
      align_v: middle
      rotation: 0

  # Key Milestones — gold heading + black label.
  - apply_to: box:swimlane_heading
    select: { swimlane: "Key Milestones" }
    style: { fill: gold }

  - apply_to: text:swimlane_label
    select: { swimlane: "Key Milestones" }
    style: { color: black }
```

---

### `time_bands` — Shared Band Catalog

A theme defines its time bands once under the top-level `time_bands:` map. Each visualizer's placement list is a list of *references* by catalog key, with optional inline geometry overrides.

```yaml
time_bands:
  fiscal_quarter:
    unit: fiscal_quarter
    label: Fiscal Quarter
    label_format: "FY{fy2} Q{q}"
    show_every: 1
  month:
    unit: month
    label: Month
    date_format: "MMM"
    show_every: 1
  countdown_launch:
    unit: countdown
    label: Days to Launch
    target_date: "2026-06-30"
    skip_weekends: true
    label_format: "{n}d"
  day:
    unit: countup
    label: Day
    start_date: "2026-01-01"
    skip_weekends: false
    label_format: "D+{n}"
  flags:
    unit: icon
    label: Flags
    row_height: 18
    icon_height: 12
    fill_color: "none"
    icon_rules:
      - { milestone: true,        icon: star,   color: "#cc6600" }
      - { resource_group: "QA",   icon: bug,    color: "#aa1144" }
      - { federal_holiday: true,  icon: flag,   color: "#888888" }

blockplan:
  top_bands:
    - { band: fiscal_quarter, row_height: 25 }   # inline geometry override
    - { band: month,          row_height: 20 }
    - { band: flags }
  bottom_bands: []

compact_plan:
  bands: [fiscal_quarter, month, flags]

excelheader:
  top_bands: [fiscal_quarter, month, flags]
  band_fonts:
    fiscal_quarter: { excel_font_name: "Arial Narrow", excel_font_size: 10 }

timeline:
  top_time_bands: [fiscal_quarter, month, flags]
```

Band styling lives in `style_rules`, keyed by `select.band: <catalog_key>`:

```yaml
style_rules:
  - apply_to: box:band
    select: { band: month }
    style: { fill: [lightblue, lightyellow] }   # list cycles across segments

  - apply_to: text:band_label
    select: { band: month }
    style: { color: navy }
```

#### Time-Band Structural Fields (in `time_bands:`)

| Key | Type | Description |
|---|---|---|
| `unit` | `str` | `fiscal_quarter` \| `fiscal_period` \| `month` \| `week` \| `interval` \| `date` \| `dow` \| `countdown` \| `countup` \| `icon` \| `holiday` |
| `label` | `str` | Text shown in the heading column cell |
| `label_format` | `str` | Format for week/fiscal_quarter/countdown/countup; placeholders: `{week}` `{fy}` `{fy2}` `{q}` `{n}` |
| `date_format` | `str` | Arrow format for month/date/dow labels; e.g. `"MMM"`, `"MMMM"`, `"D"`, `"ddd"` |
| `interval_days` | `int` | Segment length in days (interval unit only) |
| `anchor_date` | `str` (YYYY-MM-DD) | Alignment anchor for interval unit |
| `prefix` | `str` | Label prefix (interval unit); e.g. `"Sprint "` |
| `start_index` | `int` | First counter value (interval unit) |
| `max_index` | `int` | Counter resets to `start_index` after this value (interval unit) |
| `target_date` | `str` (YYYY-MM-DD) | **countdown only** — required: the date to count down to |
| `start_date` | `str` (YYYY-MM-DD) | **countup only** — required: the origin date to count up from (day 0) |
| `skip_weekends` | `bool` | **countdown/countup** — exclude Sat/Sun from the day count |
| `skip_nonworkdays` | `bool` | **countdown/countup** — exclude holidays & company non-workdays |
| `label_values` | `list[str\|null]` | Override displayed segment text; `null` = auto; `""` = blank |
| `show_every` | `int` | Merge N consecutive segments into one cell |
| `icon_rules` | `list[dict]` | **icon only** — required: list of icon rules (see below) |
| `icon_height` | `float` | **icon only** — display height of each icon in pts (defaults to `row_height * 0.65`) |
| `fill_color` | `str` | **icon only** — background fill for every day cell (`"none"` = transparent) |
| `nonworkdays_only` | `bool` | **holiday only** — hide observances that carry a flag but do not close the office (default `false`) |

> **`countdown` unit:** Each visible day cell shows the number of counting-days between that day and `target_date`. The value is **0** on the target day itself, **positive** for days before it (days remaining), and **negative** for days after (days elapsed). Use `label_format: "{n}d"` to append a suffix, or `label_format: "D-{n}"` for a launch-style label. Combine `skip_weekends: true` and `skip_nonworkdays: true` to count only business days.

> **`countup` unit:** Each visible day cell shows the number of counting-days elapsed since `start_date`. The value is **0** on the start day itself, **positive** for days after it (days elapsed), and **negative** for days before it (days prior to the origin). Use `label_format: "D+{n}"` for a project-day-style label. The same `skip_weekends` / `skip_nonworkdays` options apply.

> **`icon` unit:** Per-day glyph row instead of labeled segments. Each visible day gets one cell; rules in `icon_rules` are matched against the events on that day (and, optionally, the day's non-workday class), and any matching icon is drawn in the cell. Icons are deduplicated by name per day. Supported by `blockplan`, `compactplan`, `excelheader`, `excelblockplan`, and `timeline`. In `excelheader`/`excelblockplan` the icon is rendered as a centred filled bullet (`●`) coloured to the rule's `color`; the SVG visualizers render the actual icon glyph from the `icons` table. The icon-band heading cell still respects the band's `label`, so put a column-label like `"Flags"` on the band itself.
>
> Each entry in `icon_rules` is a dict. The only required key is `icon` (an icon name from the `icons` table — run `ecalendar.py icons` to list, `ecalendar.py iconsheet` to preview). Add one or more match keys to filter which events trigger the icon:
>
> | Rule key | Matches when… |
> |---|---|
> | `icon` | (required) icon name to draw |
> | `color` | fill color for the drawn icon (default `#333333`) |
> | `milestone` | event's milestone flag equals this bool |
> | `event_type` | `"milestone"` or `"duration"` |
> | `task_contains` | case-insensitive substring of the task name |
> | `resource_group` | exact match on `resource_group` |
> | `notes_contains` | case-insensitive substring of the event's notes |
> | `rollup` | rollup flag matches |
> | `priority` | exact priority (int) |
> | `priority_min` / `priority_max` | inclusive priority range |
> | `wbs_prefixes` | list of WBS prefixes; at least one must match |
> | `federal_holiday` | day is a federal holiday (no event needed) |
> | `company_holiday` | day is a company non-workday |
> | `weekend` | day is a Saturday/Sunday |
> | `nonworkday` | day matches any of the three classes above |
>
> A rule that contains any of the four day-based keys (`federal_holiday`, `company_holiday`, `weekend`, `nonworkday`) is evaluated once per visible day against the non-workday classifier rather than against events. All other rules evaluate against each event whose start (or `datekey`, for milestones) falls on that day.

> **`holiday` unit:** Per-day glyph row like `icon`, but the glyph comes from the holiday row itself rather than from theme rules, so each country brings its own flag and adding a country needs no theme edit — only its holidays loaded. Holidays are read for `--country`, and a day carrying two holidays from different countries draws both flags side by side. Supported by `gantt` and `blockplan`. It shows more than the non-workday shading does: shading goes through the non-workday classifier, which only reports holidays flagged `nonworkday`, so an observance such as Groundhog Day never reaches it. Set `nonworkdays_only: true` to narrow the band to the days that actually close the office.
>
> ```yaml
> time_bands:
>   holiday:
>     unit: holiday
>     label: Holidays
>     nonworkdays_only: false
> ```

Visual properties (segment fill, label color/font/size, alternation across segments) go in `style_rules` on `box:band` and `text:band_label`. Per-placement geometry (`row_height`, `show_every` overrides) goes inline on the reference, as shown in the `blockplan.top_bands` example above.

---

### Blockplan Vertical Marker Lines

Vertical marker lines (and optional column fills) in the blockplan are expressed as `style_rules` entries with `apply_to: box:vline`. Selectors pin the line to a band segment.

```yaml
style_rules:
  # Light grey dashed separator at the end of every Month segment.
  - name: month_separator
    apply_to: box:vline
    select: { band: month, repeat: true }
    style:
      align: end
      stroke: grey
      stroke_width: 1.0
      stroke_opacity: 0.4
      dasharray: "4,4"

  # Heavier navy line at the end of every Fiscal Quarter, with a soft column fill.
  - name: quarter_marker
    apply_to: box:vline
    select: { band: fiscal_quarter }
    style:
      align: end
      stroke: navy
      stroke_width: 1.5
      fill: lightyellow
      fill_opacity: 0.10

  # Highlight every weekend cell in the Date band with a soft fill (no line).
  - name: weekend_columns
    apply_to: box:vline
    select: { band: date, repeat: true, weekend: true }
    style:
      fill: "#E8E8E8"
      fill_opacity: 0.4
```

`align: start | center | end` controls which edge of the matched segment the line pins to. `fill` may be a scalar, `none`, or a list (cycled across the rule's matched segments).

---

## Visualization Setting Gaps

Each visualizer reads two kinds of theme content:

1. **Shared `style_rules`** — every visualizer consults the same top-level rule list. Rules scope themselves to a visualizer with `select.visualizer: weekly | mini | timeline | blockplan | compactplan | text-mini` or apply globally.
2. **Per-visualizer non-styling config** — format strings, geometry, fiscal semantics, and structural declarations remain in dedicated sections.

Per-visualizer non-styling surfaces:

- `weekly` — week-number format, day-name format, overflow icon name.
- `mini` — `mini_calendar.title_format`, layout dimensions; `mini_calendar.icon_set` names the glyph set the `mini-icon` variant draws day numbers from.
- `text-mini` — symbol/glyph name registry; not an SVG renderer.
- `timeline` — `timeline.tick_label_format`, axis/callout/lane geometry, `today_date` / `today_label_text` content references.
- `blockplan` — swimlane and timeband lists, `label_column_ratio`, lane match policy, vertical-line and band declarations (visual styling lives in `style_rules`, e.g. `apply_to: box:vline`).
- `compactplan` — axis-relative duration/legend geometry.
- `excelheader` — XLSX-specific band schema (`band_fonts`) and `vertical_lines`. These are **not** reached by `style_rules`: they map to Excel cell formatting and cell borders, not SVG primitives. See "Vertical Lines → Cell Right Borders" below.

Shared non-styling sections:

- `theme.*` — metadata.
- `base.*` — default font family, default missing-icon name.
- `events.*` — `item_placement_order` (algorithm; no styling).
- `durations.*` — placement / geometry only.
- `fiscal.*` — label format, year offset.
- `colors.*_palette` — palette names referenced by token style bags.

Anything that controls *appearance* — fills, strokes, fonts, colors, patterns, line widths, opacities, dasharrays — lives in `style_rules`, not in any per-visualizer section.

## Notes

- Paper-size-conditional styling is expressed as a `style_rules` entry with `select.papersize: [letter, tabloid]` (or similar). Later rules override earlier ones.
- `layout.margin.*` accepts numeric points or values with units such as `0.5in` and `10mm`.
- `colors.*_palette` keys reference DB palette names and resolve during render.
- Run `ecalendar.py help <subcommand>` for allowed values and focused help output.
- Run `uv run python tools/validate_theme.py <theme.yaml>` to check a theme against the unified schema.

---

## PIT (Points in Time) Subcommand

The `pit` subcommand generates a clean **Points-in-Time** SVG: a single axis line with one marker per event, connected by a labella-spaced bezier leader to a non-overlapping label box. It is the lightest-weight timeline style — no duration bars, no fiscal bands, no WBS hierarchy — designed for milestone charts, roadmaps, and presentation decks where clarity trumps density.

### Visual aesthetic

A single horizontal (or vertical) axis spans the project date range. Each event appears as a marker (filled circle, diamond, or DB icon glyph) on the axis, with a curved leader rising to a labeled box on the primary or secondary side. The box holds the event name, optional notes, and (by default) the date — see `--date-placement` to move the date back onto the axis or hide it. An optional "today" line crosses the axis as a perpendicular dashed rule.

### Usage examples

```bash
# Horizontal, both-side labels, default theme (landscape page)
uv run python ecalendar.py pit 20260101 20261231 \
  --orientation landscape --direction horizontal --label-side both \
  --tick-unit month --outputfile output/pit_2026.svg

# Vertical poster, milestones only, label-box trophy icons, accent theme
# (axis still uses the built-in diamond for each milestone — icons live in the box.)
uv run python ecalendar.py pit 20260101 20261231 \
  --orientation portrait --papersize tabloid \
  --direction vertical --label-side primary \
  --milestones \
  --milestone-icon trophy --marker-size 11 \
  --tick-unit fiscal_quarter \
  --theme accent \
  --outputfile output/pit_milestones_2026.svg

# Fiscal-quarter ticks, dashed leaders, includes notes
uv run python ecalendar.py pit 20260101 20271231 \
  --fiscal "4-5-4" --tick-unit fiscal_quarter \
  --includenotes --leader-dash "3,2" \
  --outputfile output/pit_program.svg

# Future-dated "today" line for a board presentation
uv run python ecalendar.py pit 20260101 20261231 \
  --today-date 20260901 --today-label "As of Q3" \
  --outputfile output/pit_q3_presentation.svg

# Custom themed output (dark theme, vertical direction) — DB icons
# in the label boxes alongside the event names, axis still uses the
# built-in circle/diamond shapes.
uv run python ecalendar.py pit 20260101 20261231 \
  --theme dark --direction vertical --label-side both \
  --event-icon dot --milestone-icon diamond \
  --outputfile output/pit_dark.svg
```

### Inherited content-filter flags

These flags are shared with other visualizers and apply identically to `pit`:

| Flag | Short | Description |
|---|---|---|
| `--noevents` | `-ne` | Exclude regular (non-milestone) events |
| `--milestones` | `-ms` | Include milestone events |
| `--rollups` | `-ro` | Include rollup events |
| `--ignorecomplete` | `-ic` | Skip events marked 100% complete |
| `--includenotes` | `-in` | Render the Notes field as a second label line |
| `--WBS` | | WBS filter expression (prefix-based, comma-separated, `!` excludes) |
| `--empty` | `-e` | Render with no events (blank axis) |
| `--status` | | Event status filter (active, draft, cancelled, on_hold, all) |

Multi-day duration events are **always dropped** — PIT renders only point-in-time events and milestones. Use the `timeline` subcommand for durations.

### PIT-specific flags

| Flag | Short | Default | Description |
|---|---|---|---|
| `--direction` | | `horizontal` | Axis direction: `horizontal` or `vertical`. **Note:** this is distinct from `--orientation` which controls page rotation. Equivalent to `pit.direction`. |
| `--label-side` | | `both` | Which side of the axis labels occupy: `primary`, `secondary`, or `both`. Equivalent to `pit.label_side`. |
| `--tick-unit` | | `month` | Axis tick granularity: `month`, `week`, `fiscal_quarter`, `fiscal_period`, `interval`, `date`, or `year`. A perpendicular tick mark is drawn at each segment boundary with the segment label centered in its span. |
| `--tick-interval` | | `1` | For `--tick-unit interval`, the number of days between ticks. |
| `--tick-label-format` | | unit default | Arrow date format applied to each tick's own date (e.g. `MMM D`, `M/D`, `D`), for any `--tick-unit` including `interval`. When omitted, the unit's own label is used instead (the running index for `interval`, `Week N` for `week`, `FY26 Q1` for `fiscal_quarter`, etc.). |
| `--tick-length` | | `5.0` | Half-length (points) of each tick mark, drawn on each side of the axis. |
| `--no-ticks` | | (ticks on) | Suppress axis tick marks and labels entirely. |
| `--no-tick-labels` | | (labels on) | Draw the tick marks but omit their labels. |
| `--date-placement` | | `inline` | Where each event date is drawn: `inline` (a line inside the label box, alongside the name/notes — the box grows to fit, and dates inherit the boxes' collision-free multi-row spacing so they never overlap), `axis` (opposite the axis at the marker — the "ruler tick" look, but dates collide when events cluster), or `none`. Equivalent to `pit.date_text.placement`. |
| `--today-line` / `--no-today-line` | | `--today-line` | Draw (or suppress) a perpendicular "today" line. Equivalent to `pit.today_line.show`. |
| `--today-date` | | real today | Override the today-line position with a fixed date (`YYYY-MM-DD` or `YYYYMMDD`). Useful for forward-dated presentation decks. |
| `--today-label` | | theme: `"today"` | Override the label text on the today line for this run. |
| `--event-icon` | | none | DB icon name drawn **inside each event's label box**, on the name line and to the left of the name. Does NOT change the axis marker (always a built-in circle). |
| `--milestone-icon` | | none | DB icon name drawn **inside each milestone's label box**, on the name line and to the left of the name. Does NOT change the axis marker (always a built-in diamond). |
| `--label-icon-size` | | name font size | Longest viewBox side (points) of the label-box icon. Equivalent to `pit.label.icon_size`. |
| `--label-icon-gap` | | `4.0` | Horizontal gap (points) between the label-box icon and the start of the event name. Equivalent to `pit.label.icon_gap`. |
| `--marker-size` | | `7.0` | Bounding-box size (in points) of the axis marker (built-in circle / diamond). Equivalent to `pit.axis.marker_size`. |
| `--leader-dash` | | none (solid) | SVG `stroke-dasharray` for leader lines, e.g. `"4,2"`. |
| `--leader-label-anchor` | | `center` | Where the leader meets the label box along the axis: `center`, `start`, or `end`. `center` joins the middle of the box and is collision-free (it matches labella's centered placement model). `start`/`end` join the leading/trailing edge and can overlap on dense timelines. |
| `--leader-length` | | `8.0` | Distance (in points) from the axis to the first row of labels — i.e. the leader length. Larger values lengthen leaders and widen row-to-row spacing. Equivalent to the theme's `pit.labella.layer_gap`. |
| `--leader-stub` | | `6.0` | Length (in points) of the straight, axis-perpendicular segment where each leader meets its label box. labella's leader béziers arrive at a shallow angle while an `orient="auto"` arrowhead points perpendicular, leaving the head visually detached; the stub gives the arrowhead a genuinely perpendicular segment to sit on. `0` disables (pure bézier). Equivalent to `pit.leader.end_stub`. |

### Theme bindings

Add a `pit:` block to your theme YAML between the `timeline:` and `blockplan:` sections. All seven built-in themes include a pre-built `pit:` block.

```yaml
pit:
  direction: horizontal        # horizontal | vertical (distinct from page --orientation)
  label_side: both             # primary | secondary | both
  axis:
    color: "#333333"
    width: 1.5
    marker_size: 7.0           # bounding box of the built-in circle/diamond marker
    marker_start: "none"        # "arrow-head" | "none" | custom-id
    marker_start_size: 4.0
    marker_end: "arrow-head"    # arrowhead at the end of the axis
    marker_end_size: 6.0
  tick_color: "#666666"
  tick_unit: month             # month|week|fiscal_quarter|fiscal_period|interval|date|year
  tick_interval: 1             # days between ticks when tick_unit: interval
  tick_label_format: null      # Arrow format for tick labels; null = unit default
  tick_length: 5.0             # half-length of each tick mark, per side
  show_ticks: true             # set false to hide axis ticks
  show_tick_labels: true       # set false for tick marks without labels

  # Optional: multiple tick rows (overrides the single tick_* scalars above).
  # See "Multiple tick bands" below. Accepts a list of band dicts (or a
  # single dict for one band).
  ticks:
    - unit: month              # coarse row: a tick + centered label per month
      label_format: MMM
      tick_length: 8.0
      label_gap: 16.0          # push this row's labels further from the axis
    - unit: week               # fine row: weekly ticks, no labels
      show_labels: false
      tick_length: 3.0
      tick_opacity: 0.4

  date_format: "MMM D"
  leader_label_anchor: center   # center | start | end — where the leader
                                # meets the label box (center is collision-free)

  name_text:                  # callout event-name font
    font_name: Offside-Regular
    font_size: 11
  notes_text:                 # callout notes font (shown when --notes is on)
    font_name: Offside-Regular
    font_size: 9

  date_text:
    color: "#444"
    font_name: Roboto-Regular
    font_size: 9
    offset: 6.0               # distance from axis to date text (axis mode)
    placement: inline         # inline | axis | none — inline puts the date
                              # inside the label box so dates never collide

  # Label-box icons (drawn inside the callout box, left of the event name).
  # The axis marker is always a built-in shape and is NOT affected by these.
  default_event_icon: null      # DB icon name or null (no icon)
  default_milestone_icon: null  # DB icon name or null (no icon)
  dot_color: steelblue
  milestone_color: gold
  # (label_palette on the label block cycles label-box fills; there is
  #  no per-event/milestone marker palette.)

  leader:
    color: grey
    width: 0.75
    dasharray: null
    opacity: 1.0
    linecap: round
    marker_start: "none"      # axis-end of each leader
    marker_start_size: 3.0
    marker_end: "arrow-head"  # ▶ at the label end
    marker_end_size: 5.0
    end_stub: 6.0             # straight perpendicular segment at the box end
                              # so the arrowhead sits flush (0 = pure bezier)
  leader_primary:
    color: deepskyblue        # override color for primary-side leaders
    marker_end_size: 6.0
  leader_secondary:
    color: steelblue
    dasharray: "3,2"          # dashed secondary leaders

  today_line:
    show: true                # set false to suppress the today line
    color: tomato
    width: 1.0
    dasharray: "4,2"
    opacity: 0.85
    linecap: round
    label: today
    label_color: tomato
    label_font_name: Roboto-Bold
    label_font_size: 9
    label_position: end       # start | middle | end
    marker_start: "none"
    marker_end: "none"        # set to "arrow-head" to point into the future

  arrow_head:
    color: grey               # fill color for all built-in arrowheads

  label:
    stroke_color: lightgrey
    stroke_width: 0.5
    fill_color: aliceblue
    fill_opacity: 0.85
    pattern: null             # DB pattern name (e.g. "diagonal-stripes")
    pattern_opacity: 0.15
    text_color: "#1b1f24"
    corner_radius: 2.0
    padding_x: 6.0
    padding_y: 3.0
    icon_size: null           # label-box icon longest side; null = name font size
    icon_gap: 4.0             # gap (points) between the icon and the event name
  label_palette: Pastel1      # round-robin palette for label box fills

  labella:                    # label-placement tuning
    layer_gap: 8.0            # axis→label gap = leader length (also row spacing)
    node_height: 24.0         # label box thickness perpendicular to the axis
    density: 0.75             # 0–1; lower packs fewer labels per row (more rows)
```

##### Callout text fonts (`name_text` / `notes_text`)

`pit.name_text` and `pit.notes_text` set the fonts for the event name and notes
inside each callout box. Resolution is **fallback-chained**, highest priority
first:

1. `pit.name_text.font_name` / `pit.notes_text.font_name` (this block).
2. `timeline.name_text.font_name` / `timeline.notes_text.font_name` — PIT
   borrows the timeline fonts when its own are unset.
3. Built-in defaults `Roboto-Bold` (name) and `Roboto-Regular` (notes).

> **Note:** before these keys existed, the PIT visualizer had *no* font hook of
> its own, so it always fell to step 2 — changing the PIT event font meant
> editing `timeline.name_text`, which also restyled the timeline. Set
> `pit.name_text` / `pit.notes_text` to give PIT its own font independent of the
> timeline. The font name must be one registered in `FONT_REGISTRY` (e.g. the
> `Roboto*`, `RobotoCondensed*`, `FiraSans*`, `Offside-Regular`, `JuliaMono*`
> families); unregistered names are ignored with a warning and fall through.

#### Multiple tick bands

By default the axis draws a single row of ticks driven by the scalar
`tick_unit` / `tick_interval` / `tick_label_format` / `tick_length` /
`show_tick_labels` fields. To stack several tick rows at different
granularities — e.g. month names over light weekly ticks — set `pit.ticks`
to a **list of band dicts** instead. When `ticks` is present it **overrides**
the scalar `tick_*` fields entirely; each band becomes its own row of tick
marks (and optional centered labels). A single dict is accepted as shorthand
for a one-band list. This mirrors the `timeline` visualizer's `ticks:` block.

Each band draws a tick at every segment boundary for its unit and centers
the segment label within its span. Per-band keys:

| Key | Default | Effect |
|---|---|---|
| `unit` | `month` | Tick granularity: `month`, `week`, `fiscal_quarter`, `fiscal_period`, `interval`, `date`, or `year`. |
| `interval_days` (`interval`) | `14` | Days between ticks when `unit: interval`. |
| `label_format` (`date_format`) | unit default | When set, an **Arrow date format applied to each tick's own date** (e.g. `MMM D`, `M/D`, `D`) — independent of the unit. When omitted, the unit's own generated label is used (see "Labeling date-interval ticks" below). |
| `prefix` | `""` | Text prepended to the label. Without `label_format` it prefixes the `interval` running index (`prefix: "Sprint "` → `Sprint 1`, `Sprint 2`); with `label_format` it prefixes the formatted date (`prefix: "Week of "` + `label_format: "MM/DD"` → `Week of 02/01`). |
| `start_index` | `1` | For `unit: interval` counter labels: the index of the first tick. |
| `max_index` | none | For `unit: interval` counter labels: wrap the index back to `start_index` after this value. |
| `anchor_date` | range start | For `unit: interval`: `YYYY-MM-DD` date the intervals are measured from, so boundaries stay fixed regardless of the visible range. |
| `show_labels` | `true` | Set `false` to draw tick marks for this band without labels. |
| `max_label_count` | `60` | Suppress labels for this band when it would draw more than this many. |
| `tick_length` | `5.0` | Half-length (points) of this band's tick marks, per side of the axis. |
| `tick_color` | theme `tick_color` | Stroke color for this band's ticks. |
| `tick_width` | `1.0` | Stroke width (points) of this band's ticks. |
| `tick_opacity` | `1.0` | Stroke opacity (0–1) of this band's ticks. |
| `tick_dasharray` | none | SVG `stroke-dasharray` for this band's ticks. |
| `label_color` (`font_color`) | this band's `tick_color` | Color of this band's labels. |
| `label_font_size` (`font_size`) | theme date-text size | Font size (points) of this band's labels. |
| `font` | theme date-text font | Font name for this band's labels. |
| `label_opacity` | `1.0` | Opacity (0–1) of this band's labels. |
| `label_offset` | auto | Distance (points) of the label baseline from the axis. Overrides the auto offset; use to place a finer row's labels closer to the axis than a coarser row. |
| `label_gap` | — | Alternative to `label_offset`: offset = `tick_length + label_gap`. |
| `label_align` | `center` | Where the label sits along the axis relative to its segment: `center` (centered in the span between this tick and the next), `start` (anchored at this tick — the segment's start boundary, e.g. the first of the month), or `end` (anchored at the next boundary). `left`/`right` are accepted as synonyms for `start`/`end`. |
| `label_side` | follows callout side | Which side of the axis this band's labels sit on, overriding the default (which is opposite the callout boxes). Horizontal axis: `above` / `below`; vertical axis: `left` / `right`. `primary` / `secondary` (or `top` / `bottom`) also work for either orientation. Lets different bands sit on opposite sides of the same axis. |

Example — month names with a light weekly grid beneath them:

```yaml
pit:
  ticks:
    - unit: month
      label_format: MMM
      tick_length: 8.0
      label_gap: 16.0          # month labels sit farther from the axis
      tick_width: 0.8
    - unit: week
      show_labels: false       # weekly ticks only, no labels
      tick_length: 3.0
      tick_opacity: 0.4
```

Both axis directions are supported: on a vertical axis the rows stack to the
left of the axis instead of below it. `label_align` follows the axis: `start`
aligns with the top boundary on a vertical axis and the left boundary on a
horizontal one.

By default tick labels are drawn on the **opposite side of the axis from the
callout label boxes**, so they never overlap the events. With
`--label-side primary` the boxes sit above (horizontal) / right (vertical) and
the tick labels go below / left; with `--label-side secondary` the boxes and
tick labels swap sides. `--label-side both` keeps the default below / left
placement for the tick labels.

To pin a band's labels to a specific side regardless of the callout side — or
to place two bands on **opposite** sides of the same axis — set `label_side`
per band. Use `above` / `below` on a horizontal axis and `left` / `right` on a
vertical one (`primary` / `secondary` work for either):

```yaml
pit:
  ticks:
    - unit: month
      label_format: MMM YY
      label_side: below        # month names beneath the axis
    - unit: week
      label_format: "W{week}"
      label_side: above        # week numbers above the axis
```

By default labels are centered in their span. To make a month name line up
with the tick marking the **first of the month** (rather than floating in the
middle of the month), set `label_align: start`:

```yaml
pit:
  ticks:
    - unit: month
      label_format: MMMM
      label_align: start        # "February" starts at the Feb 1 tick
      tick_length: 8.0
      label_gap: 10.0
```

##### Labeling date-interval ticks

`unit: interval` places a tick every `interval_days` days. How those ticks are
labeled depends on whether you give a `label_format`:

- **Calendar dates** — set `label_format` to an Arrow date format. The label is
  the actual date at each tick (every Nth day):

  ```yaml
  pit:
    ticks:
      - unit: interval
        interval_days: 14         # a tick every two weeks
        label_format: "MMM D"     # → "Feb 1", "Feb 15", "Mar 1", ...
        anchor_date: "2026-02-01" # optional: pin the interval boundaries
  ```

- **A running counter** (sprints, cycles, etc.) — omit `label_format`. The label
  is a running index you can shape with `prefix` / `start_index` / `max_index`:

  ```yaml
  pit:
    ticks:
      - unit: interval
        interval_days: 14
        prefix: "Sprint "        # → "Sprint 1", "Sprint 2", "Sprint 3", ...
        start_index: 1
  ```

- **A prefixed date** — combine `prefix` *with* `label_format`. The prefix is
  prepended to the formatted date:

  ```yaml
  pit:
    ticks:
      - unit: interval
        interval_days: 7
        prefix: "Week of "       # → "Week of 02/01", "Week of 02/08", ...
        label_format: "MM/DD"
  ```

The same rule applies to every unit: any unit gains date labels when you add a
`label_format` (e.g. `unit: week` + `label_format: "MMM D"` labels each week
start with its date instead of `Week N`), and falls back to the unit's own
label (`Week N`, `FY26 Q1`, the interval index, …) when you omit it. Use
`MMMM`/`MMM` for month names, `D` for the day of month, `M/D` or `YYYY-MM-DD`
for full dates. This matches the `timeline` visualizer's tick behavior.

#### Per-rule overrides in `style_rules`

The following extra keys are recognized inside a rule's `style:` block when `apply_to: event` (or `apply_to: all`):

| Key | Type | Effect |
|---|---|---|
| `marker_icon` | `"icon-name"` | Replace the built-in shape with the named DB icon. |
| `leader` | `{color, width, dasharray, opacity, linecap, linejoin, marker_start, marker_end, ...}` | Per-rule leader stroke override. Merges with (and wins over) the side and global defaults. |
| `label` | `{stroke_color, stroke_width, stroke_dasharray, fill_color, fill_opacity, pattern, pattern_opacity, text_color, corner_radius}` | Per-rule label box override. |

Example:
```yaml
style_rules:
  - name: Release milestones
    apply_to: event
    select:
      resource_group: release
      milestone: true
    style:
      marker_icon: "rocket"
      leader:
        color: "#c33"
        dasharray: "4,2"
        marker_end: "arrow-head"
        marker_end_size: 7.0
      label:
        fill_color: "palette:Reds:2"
        fill_opacity: 0.9
        pattern: "circuit-board"
        pattern_opacity: 0.12
```

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

Every run also writes a companion **details page** (`<output>_details.svg`) — see
[The details page](#the-details-page) below.

### Usage examples

```bash
# Six-month chart with the default theme
uv run python ecalendar.py gantt 20260202 20260731 -of gantt_h1.svg

# One programme only, using the WBS filter, with notes in the task rows
uv run python ecalendar.py gantt 20260202 20260731 --WBS NP --includenotes -of nimbuspay.svg

# Show weekends as shaded columns instead of removing them from the axis
uv run python ecalendar.py gantt 20260202 20260430 --weekends 1 -of gantt_7day.svg

# Milestones only, on a wide sheet, corporate theme
uv run python ecalendar.py gantt 20260101 20261231 --milestones -th corporate -ps Tabloid --orientation landscape -of milestones.svg

# Drop finished work and any single-day events; keep the multi-day bars
uv run python ecalendar.py gantt 20260202 20260731 --ignorecomplete --noevents -of gantt_open.svg

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
weekend — it has no column to shade, so it is reported on the details page instead.

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
300 references before numbering degrades. All of them are listed on the details page with
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
| Continuation icon | bars crossing `START_DATE` / `END_DATE` | Drawn inside the clipped edge, and reported on the details page |
| Today line | wall clock, or `gantt.today_date` | Same semantics as the `pit` view: suppressed when outside the range |

### Stacking the timescale

Both `gantt.top_bands` and `gantt.bottom_bands` take as many bands as you want, drawn
top to bottom in the order listed, each with its own `row_height`:

```yaml
gantt:
  top_bands:
    - { band: fiscal_quarter, row_height: 12 }
    - { band: month,          row_height: 12 }
    - { band: week,           row_height: 10 }
    - { band: dow,            row_height: 9 }
  bottom_bands:
    - { band: month_2, row_height: 10 }
    - { band: date,    row_height: 9 }
```

Bands name entries in the theme's top-level `time_bands:` catalog, the same catalog
`blockplan` and `compactplan` draw from. Omitting `bottom_bands` mirrors the top stack
onto the bottom axis; an empty list removes that axis entirely.

If the two stacks plus the column-header row together want more than 75% of the content
height, every chrome row is scaled down in proportion — no band is dropped, and the task
body always keeps positive height.

### Pagination

The chart splits across pages on both axes when it does not fit:

- **Vertically**, when there are more rows than the page height allows. Every page repeats
  the column headers and the full timescale.
- **Horizontally**, when a day column would fall below `gantt.min_day_width` (4 pt by
  default; set it to `0` to fit any range onto one page, however thin the columns). Every
  page repeats the task table, and the timescale *continues* rather than restarting — week
  48 is followed by week 49, not by week 1.

Pages run row-major, so following one task's bar across the date range means turning
consecutive pages. Continuation files are named `<output>_p2.svg`, `<output>_p3.svg`, and
so on.

### The details page

Every run writes `<output>_details.svg` alongside the chart; set
`gantt.show_details: false` in a theme to suppress it. It has two sections:

1. **Tasks** — every row in chart order, through the same columns as the chart's table.
2. **Exceptions** — one line per item the chart could not show faithfully:

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

The exception log paginates rather than truncating (`<output>_details_p2.svg`, …) — a
report that quietly dropped its last few lines would defeat the purpose.

### Inherited content-filter flags

These flags are shared with the other plan views and apply identically to `gantt`:

| Flag | Short | Description |
|---|---|---|
| `--noevents` | `-ne` | Exclude single-day events |
| `--nodurations` | `-nd` | Exclude multi-day durations |
| `--milestones` | `-mo` | Show only milestones |
| `--rollups` | `-ro` | Show only rollup entries |
| `--ignorecomplete` | `-ic` | Exclude 100% complete items |
| `--includenotes` | `-notes` | Show notes with event names |
| `--WBS` | | WBS filter expression (comma-separated, `!` excludes) |
| `--status` | | Event status filter (`active` by default; `all` for everything) |
| `--weekends` | `-w` | Weekend style 0-4 (see above) |
| `--country` | `-cc` | Country code(s) for government holidays |
| `--empty` | `-e` | Render the frame and timescale with no tasks |

A filtered-out task stops being a link target as well as a row: its dependents draw the
off-chart stub instead of an arrow.

### Theme reference

All keys live under `gantt:` in a theme file. `config/themes/SAMPLE.yaml` carries the
fully annotated set; `config/themes/default.yaml` shows a working configuration including
`columns:` and band references.

| Key | Default | Purpose |
|---|---|---|
| `table_width_ratio` | `0.38` | Task table's share of the content width |
| `row_height` | `14.0` | Fixed row height |
| `header_row_height` | `18.0` | Column-header row height |
| `band_row_height` | `10.0` | Default height per time-band row |
| `indent_per_level` | `8.0` | Points of indent per WBS level |
| `bar_height` | `8.0` | Duration-bar thickness |
| `min_day_width` | `4.0` | Split the range across pages below this; `0` disables |
| `sort` | `[wbs, start_date]` | Row ordering |
| `columns` | 16-column set | The task table (see above) |
| `top_bands` / `bottom_bands` | month + week | Timescale rows; reference the `time_bands` catalog. **Any number of bands** in either stack, each with its own `row_height`. Omit `bottom_bands` and the bottom axis mirrors the top |
| `progress_color` | `black` | Percent-complete line |
| `progress_width` | `1.5` | Percent-complete line width |
| `float_opacity_scale` | `0.4` | Float-bar opacity, relative to the bar |
| `milestone_icon` | `diamond-fill` | Milestone glyph |
| `deadline_icon` | `square-fill` | Deadline glyph |
| `rollup_icon` / `milestone_flag_icon` | `check` | Task-table icon columns |
| `snapped_event_icon` | `arrow-left-circle` | Event moved off a hidden weekend |
| `offchart_dep_icon` | `crosssquare` | Marker for a predecessor that is nowhere in the chart |
| `link_ref_icon_families` | `[circle-, darkcircle-, square-]` | Numbered-icon families for cross-page links, used in order |
| `link_ref_family_size` | `100` | Numbers available per family |
| `link_ref_max_icons` | `2` | Icons drawn in one reference cell |
| `continuation_icon` | `arrow-bar-right` | Bar clipped at a range edge |
| `show_dependencies` | `true` | Draw dependency arrows |
| `arrow_marker_end` | `arrow-head` | Arrowhead marker; `none` to omit |
| `arrow_marker_end_size` | `6.0` | Arrowhead size in points |
| `arrow_linecap` / `arrow_linejoin` | `round` | Leader stroke joins |
| `show_today_line` | `true` | Draw the today line |
| `today_date` | `null` | Fix "today" at a `YYYYMMDD` date for a forward-dated review |
| `show_details` | `true` | Write the companion `_details.svg` page |
| `details_title_text` | `Gantt Details` | Title on the companion page |

Bars, milestones and arrows are styled through `style_rules` like every other element:

```yaml
style_rules:
  - name: critical-path bars in red
    apply_to: box:duration
    select: { tags: critical }
    style: { fill: crimson, fill_opacity: 0.8 }
  - name: dependency arrows
    apply_to: line:dependency_arrow
    style: { stroke: navy, stroke_width: 1.0, stroke_opacity: 0.85 }
```

The `ec-*` classes the Gantt emits — usable from an external stylesheet — are
`ec-column-header`, `ec-task-cell`, `ec-row-band`, `ec-duration-bar`, `ec-progress-line`,
`ec-float-bar`, `ec-rollup-bracket`, `ec-dependency-arrow`, `ec-milestone-marker`,
`ec-band-cell`, `ec-tick-label`, `ec-today-line`, and `ec-grid-line`.

## ExcelHeader Subcommand

The `excelheader` subcommand generates an Excel workbook (`.xlsx`) containing timeband rows in the top rows of a worksheet, followed by a fixed column-header row and 100 blank data rows. It is intended as a ready-to-use project planning template.

### Usage

```bash
ecalendar.py excelheader START_DATE END_DATE [options]
ecalendar.py excelheader 20260101 20260630 --theme corporate --weekends 0 --country US
```

### Options

| Flag | Short | Default | Description |
|---|---|---|---|
| `--outputfile` | `-of` | `output/excelheader.xlsx` | Destination `.xlsx` path |
| `--theme` | `-th` | none | Theme name or `.yaml` path |
| `--weekends` | `-we` | `0` | Weekend style (0 = workweek only, 1–4 = include weekends) |
| `--weekend-days` |  | — | Comma-separated ISO weekday list (`0=Mon..6=Sun`) overriding the implicit Sat/Sun pair |
| `--country` | `-cc` | none | ISO 3166-1 alpha-2 country code(s) for government holidays. Comma-separated (e.g. `US,CA,GB`) for multi-country merging. |
| `--database` | `-db` | `calendar.db` | SQLite database path |
| `--verbose` | `-v` | — | Increase verbosity (`-v`, `-vv`, `-vvv`) |
| `--quiet` | `-q` | — | Suppress output path echo |

### Workbook Layout

```
Columns A–E  : Activity  |  Effort  |  Duration  |  Scheduled Start  |  Scheduled End
Columns F+   : one column per visible calendar day (width = 3 characters)
Rows 1..N    : timeband rows — one per entry in excelheader.top_time_bands
Row  N+1     : column-header row with the A–E labels
Rows N+2..   : 100 empty data rows for project tracking
```


### Timeband Configuration

ExcelHeader's bands are *references* into the shared top-level `time_bands:` catalog. Per-band geometry overrides (`row_height`, `show_every`) can go inline; per-band Excel-font overrides live in `excelheader.band_fonts` keyed by catalog name (deliberate exception — Excel uses system-installed fonts that aren't in the ecalendar font registry, so the XLSX side keeps its own narrow font slot):

```yaml
excelheader:
  font_name: "Calibri"           # workbook-wide default font
  font_size: 9                   # workbook-wide default size in points
  band_row_height: 18

  top_bands: [fiscal_quarter, month, day]

  band_fonts:
    fiscal_quarter:
      excel_font_name: "Arial Narrow"
      excel_font_size: 10
    month:
      excel_font_size: 9

  # Vertical lines: XLSX-only feature — these render as right-cell borders
  # in Excel, not as SVG box:vline rules.  See "Vertical Lines →
  # Cell Right Borders" below.
  vertical_line_color: red
  vertical_line_width: 1.5
  vertical_lines:
    - band: month
      repeat: true
      align: end
      color: navy
      width: 2.0

time_bands:
  fiscal_quarter:
    unit: fiscal_quarter
    label: Quarter
    label_format: "FY{fy2} Q{q}"
  month:
    unit: month
    label: Month
    date_format: "MMM"
  day:
    unit: date
    label: Day
    date_format: "D"
```

All standard `unit` types are supported in the catalog: `fiscal_quarter`, `month`, `week`, `interval`, `date`, `dow`, `countdown`, `countup`, `icon`, and `holiday`.

Icon bands (`unit: "icon"`) render a colored bullet symbol (●) in each day cell where a matching event exists. Icons are matched using `icon_rules` on the catalog entry — the same rule schema as blockplan icon bands. Example:

```yaml
time_bands:
  events:
    unit: icon
    label: Events
    row_height: 14
    icon_rules:
      - milestone: true
        icon: diamond
        color: "#4472C4"
      - task_contains: Release
        icon: star
        color: "#E74C3C"

excelheader:
  top_bands: [events]
```

### Excel Font Settings

Global font settings for the workbook are configured under the `excelheader` section (uses system-installed fonts, not the ecalendar font registry):

```yaml
excelheader:
  font_name: "Calibri"   # default font for all cells
  font_size: 9           # default font size in points
```

Per-band font overrides live in `excelheader.band_fonts`, keyed by the catalog name (a deliberate XLSX-only exception — SVG renderers go through `text:band_label` in `style_rules` instead):

```yaml
excelheader:
  band_fonts:
    fiscal_quarter:
      excel_font_name: "Arial Narrow"
      excel_font_size: 10
```

### Holiday Decoration

Each visible day column is checked against government holidays (via the `holidays` Python package) and company special days in the database:

- **Federal/government holidays** — background shaded with `colors.federal_holiday.color` from the theme; the cell displays a country flag emoji (e.g. 🇺🇸 for US).
- **Company non-workdays** — background shaded with `colors.company_holiday.color` from the theme; the cell displays 🏢.

Holiday shading is applied in:
- **Date/dow band cells** — the individual day segment cell is shaded and its label replaced with the emoji.
- **Column-header row** — holiday columns are shaded.
- **All 100 data rows** — holiday columns are shaded throughout.

### Vertical Lines → Cell Right Borders

ExcelHeader keeps its own list of vertical lines under `excelheader.vertical_lines` (independent of the blockplan's `style_rules`-driven vertical lines). Each entry is translated to a right-side border on the corresponding date columns. The border is applied to the column-header row and all 100 data rows.

| `align` value | Border position |
|---|---|
| `"end"` (default) | Right border on the last column of the segment |
| `"start"` | Right border on the first column of the segment |
| `"center"` | Right border on the middle column of the segment |

Border style: `medium` (width > 1.5 pt) or `thin` (≤ 1.5 pt). Color from `color` key or `excelheader.vertical_line_color`.

```yaml
excelheader:
  vertical_lines:
    - band: "Month"
      repeat: true
      align: "end"
      color: "navy"
      width: 2.0
```
