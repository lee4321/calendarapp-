# EventCalendar User Guide

This guide is generated from the current codebase (`ecalendar.py`, `config/theme_engine.py`, `config/config.py`) and reflects the exact implemented CLI/theme surface.

## Commands

| Command | What it does |
|---|---|
| `weekly` | Generate a weekly calendar SVG. |
| `mini` | Generate a mini calendar SVG. |
| `mini-icon` | Generate a mini calendar SVG using icon images for day numbers instead of numerals. |
| `text-mini` | Generate a text mini calendar. |
| `timeline` | Generate a timeline SVG. |
| `blockplan` | Generate a blockplan SVG. |
| `compactplan` | Generate a compressed activities timeline SVG showing durations as colored lines above/below a central axis, grouped by resource group. |
| `excelheader` | Generate an `.xlsx` workbook with timeband header rows and a project-planning template. |
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

# Timeline with custom today-line styling
PYTHONPATH=. uv run python ecalendar.py timeline 20260101 20261231 -tll 120 -tld below -of timeline.svg

# Blockplan view
PYTHONPATH=. uv run python ecalendar.py blockplan 20260101 20261231 -th corporate -of blockplan.svg

# Compact activities plan
PYTHONPATH=. uv run python ecalendar.py compactplan 20260309 20260424 -th corporate -of compact.svg

# Excel workbook with project-planning template
PYTHONPATH=. uv run python ecalendar.py excelheader 20260101 20260630 -th corporate -of plan.xlsx

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
PYTHONPATH=. uv run python ecalendar.py patternsheet -f wave -of waves.svg
PYTHONPATH=. uv run python ecalendar.py iconsheet -f arrow -of arrows.svg
PYTHONPATH=. uv run python ecalendar.py colorsheet -of colors.svg
PYTHONPATH=. uv run python ecalendar.py fontsheet -f roboto -of roboto.svg
```

## Command-Line Option Catalog (All Options)

| Option(s) | Metavar | Commands | Description | Defaults/Choices |
|---|---|---|---|---|
| `--WBS` |  | `blockplan`, `compactplan`, `exportdata`, `mini`, `mini-icon`, `text-mini`, `timeline`, `weekly` | WBS filter expression. Comma-separated tokens; '!' excludes. Segments are dot-separated. '*' matches a segment, '**' matches any remaining segments (implicit if omitted). |  |
| `--color`, `-c` | `COLOR` | `fontsheet`, `iconsheet`, `patternsheet` | Stroke/glyph color (icons & patterns default `#333333`; fontsheet default `#222222`) | `iconsheet`: default `#333333`; `patternsheet`: default `#333333`; `fontsheet`: default `#222222` |
| `--country`, `-cc` | `CODE` | `blockplan`, `compactplan`, `excelheader`, `exportdata`, `mini`, `mini-icon`, `text-mini`, `timeline`, `weekly` | ISO 3166-1 alpha-2 country code(s) for government holidays. Accepts a single code (e.g. `US`) or a comma-separated list (e.g. `US,CA,GB`). If omitted on render commands, all holidays from the government table are included; `exportdata` defaults to `US,CA`. |  |
| `--database`, `-db` | `PATH` | `blockplan`, `colors`, `colorsheet`, `compactplan`, `excelheader`, `exportdata`, `icons`, `iconsheet`, `mini`, `mini-icon`, `palettes`, `palettesheet`, `papersizes`, `patterns`, `patternsheet`, `text-mini`, `timeline`, `weekly` | Path to SQLite database file (default: calendar.db) | `blockplan`: default `calendar.db` |
| `--duration-fill-opacity`, `-dfo` | `0.0-1.0` | `timeline` | Fill opacity for duration bar rectangles (default: 0.25). |  |
| `--empty`, `-e` |  | `blockplan`, `compactplan`, `mini`, `mini-icon`, `text-mini`, `timeline`, `weekly` | Create blank calendar (no events) | `blockplan`: default `False` |
| `--filter`, `-f` | `TEXT` | `colorsheet`, `fontsheet`, `iconsheet`, `patternsheet` | Filter items by name substring (case-insensitive) |  |
| `--fullset` |  | `fontsheet` | Show every glyph in the font instead of the three fixed sample rows | `fontsheet`: default `False` |
| `--fiscal` | `TYPE` | `weekly` | Enable fiscal calendar overlay (nrf-454, nrf-445, nrf-544, 13-period) | `weekly`: choices `nrf-454, nrf-445, nrf-544, 13-period` |
| `--fiscal-colors` |  | `weekly` | Use fiscal period colors instead of Gregorian month colors for day box backgrounds | `weekly`: default `False` |
| `--footercenter`, `-fc` |  | `blockplan`, `compactplan`, `mini`, `mini-icon`, `timeline`, `weekly` | Center footer text |  |
| `--footerleft`, `-fl` |  | `blockplan`, `compactplan`, `mini`, `mini-icon`, `timeline`, `weekly` | Left footer text |  |
| `--footerright`, `-fr` |  | `blockplan`, `compactplan`, `mini`, `mini-icon`, `timeline`, `weekly` | Right footer text |  |
| `--footer`, `-ft` |  | `blockplan`, `compactplan`, `mini`, `mini-icon`, `timeline`, `weekly` | Include page footer | `blockplan`: default `False` |
| `--headercenter`, `-hc` |  | `blockplan`, `compactplan`, `mini`, `mini-icon`, `timeline`, `weekly` | Center header text |  |
| `--headerleft`, `-hl` |  | `blockplan`, `compactplan`, `mini`, `mini-icon`, `timeline`, `weekly` | Left header text |  |
| `--headerright`, `-hr` |  | `blockplan`, `compactplan`, `mini`, `mini-icon`, `timeline`, `weekly` | Right header text |  |
| `--header`, `-ht` |  | `blockplan`, `compactplan`, `mini`, `mini-icon`, `timeline`, `weekly` | Include page header | `blockplan`: default `False` |
| `--ignorecomplete`, `-ic` |  | `blockplan`, `compactplan`, `exportdata`, `mini`, `mini-icon`, `text-mini`, `timeline`, `weekly` | Exclude 100%% complete items | `blockplan`: default `False` |
| `--imagemark`, `-wi` |  | `blockplan`, `compactplan`, `mini`, `mini-icon`, `timeline`, `weekly` | Watermark image file |  |
| `--includenotes`, `-notes` |  | `blockplan`, `compactplan`, `mini`, `mini-icon`, `text-mini`, `timeline`, `weekly` | Include notes with events | `blockplan`: default `False` |
| `--milestones`, `-mo` |  | `blockplan`, `compactplan`, `exportdata`, `mini`, `mini-icon`, `text-mini`, `timeline`, `weekly` | Show only milestones | `blockplan`: default `False` |
| `--label-fill-opacity`, `-lfo` | `0.0-1.0` | `timeline` | Fill opacity for callout label boxes (default: 0.25). |  |
| `--margin`, `-m` |  | `blockplan`, `compactplan`, `mini`, `mini-icon`, `timeline`, `weekly` | Add page margins | `blockplan`: default `False` |
| `--mini-columns`, `-mc` | `N` | `mini`, `mini-icon`, `text-mini` | Number of months per row in mini calendar (default: 3) |  |
| `--mini-details` |  | `mini`, `mini-icon` | Generate a second SVG with mini calendar event details | `mini`: default `False` |
| `--mini-grid-lines` |  | `mini`, `mini-icon` | Draw grid lines between day cells | `mini`: default `False` |
| `--mini-icon-set`, `-mis` | `SET` | `mini-icon` | Icon set to use for day numbers (default: squares) | `mini-icon`: choices `squares, darksquare, darkcircles, circles, squircles, darksquircles` |
| `--mini-no-adjacent`, `-mna` |  | `mini`, `mini-icon`, `text-mini` | Hide leading/trailing days from adjacent months | `mini`: default `False` |
| `--mini-rows`, `-mr` | `N` | `mini`, `mini-icon`, `text-mini` | Number of rows of months (0 = auto from date range) |  |
| `--mini-title-format` | `FMT` | `mini`, `mini-icon`, `text-mini` | Arrow format string for month title (default: MMM YY) |  |
| `--monthnames`, `-mn` |  | `blockplan`, `compactplan`, `mini`, `mini-icon`, `timeline`, `weekly` | Show month names on calendar | `blockplan`: default `False` |
| `--nodurations`, `-nd` |  | `blockplan`, `compactplan`, `exportdata`, `mini`, `mini-icon`, `text-mini`, `timeline`, `weekly` | Exclude multi-day durations | `blockplan`: default `False` |
| `--noevents`, `-ne` |  | `blockplan`, `compactplan`, `exportdata`, `mini`, `mini-icon`, `text-mini`, `timeline`, `weekly` | Exclude single-day events | `blockplan`: default `False` |
| `--orientation`, `-o` |  | `blockplan`, `compactplan`, `mini`, `mini-icon`, `timeline`, `weekly` | Page orientation (default: portrait) | `blockplan`: default `portrait`; choices `portrait, landscape` |
| `--outputfile`, `-of` (`-o` for `exportdata`) | `PATH` | `blockplan`, `colorsheet`, `compactplan`, `excelheader`, `exportdata`, `fontsheet`, `iconsheet`, `mini`, `mini-icon`, `palettesheet`, `patternsheet`, `text-mini`, `timeline`, `weekly` | Output file path. Render commands write under `output/` by default. Defaults: `blockplan`/`weekly`/`mini`/`mini-icon`/`text-mini`/`timeline`/`compactplan` → `output/calendar.svg`; `excelheader` → `output/excelheader.xlsx`; `exportdata` → `output/exportdata_YYYYMMDD.csv`; `colorsheet` → `output/colorsheet.svg`; `iconsheet` → `output/iconsheet.svg`; `patternsheet` → `output/patternsheet.svg`; `fontsheet` → `output/fontsheet.svg`; `palettesheet` → `output/pallet.svg`. | |
| `--overflow`, `-x` |  | `weekly` | Create overflow page showing items | default `False` |
| `--papersize`, `-ps` | `SIZE` | `blockplan`, `compactplan`, `mini`, `mini-icon`, `timeline`, `weekly` | Paper size (default: Tabloid). | `blockplan`: default `Tabloid` |
| `--quiet`, `-q` |  | `blockplan`, `colors`, `colorsheet`, `compactplan`, `excelheader`, `exportdata`, `fonts`, `fontsheet`, `help`, `icons`, `iconsheet`, `mini`, `mini-icon`, `palettes`, `palettesheet`, `papersizes`, `patterns`, `patternsheet`, `text-mini`, `themes`, `timeline`, `weekly` | Suppress all output except errors | `blockplan`: default `False` |
| `--rollups`, `-ro` |  | `blockplan`, `compactplan`, `exportdata`, `mini`, `mini-icon`, `text-mini`, `timeline`, `weekly` | Show only rollup entries | `blockplan`: default `False` |
| `--shade`, `-sh` |  | `mini`, `mini-icon`, `weekly` | Shade current date | `weekly`: default `False` |
| `--shrink` |  | `blockplan`, `compactplan`, `mini`, `mini-icon`, `timeline`, `weekly` | Shrink SVG width/height/viewBox to the bounding box of rendered content, removing blank page whitespace. | `blockplan`: default `False` |
| `--status` | `LIST` | `blockplan`, `compactplan`, `exportdata`, `mini`, `mini-icon`, `text-mini`, `timeline`, `weekly` | Comma-separated event statuses to include. Allowed values: `active`, `draft`, `cancelled`, `archived`, `on-hold`. Use `all` for no filter. Default: `active`. See [Event Status](#event-status) for details. | default `active` |
| `--theme`, `-th` | `THEME` | `blockplan`, `compactplan`, `excelheader`, `mini`, `mini-icon`, `text-mini`, `timeline`, `weekly` | Theme name or path to .yaml theme file (e.g., 'corporate', 'dark') |  |
| `--today-line-direction`, `-tld` |  | `timeline` | Which side of the timeline axis the today line extends to: 'above' (upward only), 'below' (downward only), or 'both' (default). | `timeline`: choices `above, below, both` |
| `--today-line-length`, `-tll` | `POINTS` | `timeline` | Length of the today line in points (default: 0 = full available area). When direction is 'both', length is split equally above and below the axis. |  |
| `--verbose`, `-v` |  | `blockplan`, `colors`, `colorsheet`, `compactplan`, `excelheader`, `exportdata`, `fonts`, `fontsheet`, `help`, `icons`, `iconsheet`, `mini`, `mini-icon`, `palettes`, `palettesheet`, `papersizes`, `patterns`, `patternsheet`, `text-mini`, `themes`, `timeline`, `weekly` | Increase verbosity (-v, -vv, -vvv) | `blockplan`: default `0` |
| `--watermark-rotation-angle` | `DEGREES` | `blockplan`, `compactplan`, `mini`, `mini-icon`, `timeline`, `weekly` | Rotate text watermark by degrees (clockwise in SVG coordinates) |  |
| `--watermark`, `-wt` |  | `blockplan`, `compactplan`, `mini`, `mini-icon`, `timeline`, `weekly` | Watermark text |  |
| `--week-number-mode`, `-wnm` |  | `mini`, `mini-icon`, `text-mini`, `weekly` | Week number mode (iso or custom) | default `iso`; choices `iso, custom` |
| `--week1-start` | `YYYYMMDD` | `mini`, `mini-icon`, `text-mini`, `weekly` | Anchor date for week 1 numbering (YYYYMMDD). Implies --weeknumbers and custom mode. |  |
| `--weekend-days` | `DAYS` | `blockplan`, `compactplan`, `excelheader`, `mini`, `mini-icon`, `text-mini`, `timeline`, `weekly` | Comma-separated ISO weekday list (`0=Mon..6=Sun`) marking non-working days for holiday/weekend classification. Overrides the implicit Sat/Sun pair selected by `--weekends`. |  |
| `--weekends`, `-we` |  | `blockplan`, `compactplan`, `excelheader`, `mini`, `mini-icon`, `text-mini`, `timeline`, `weekly` | Weekend style: 0=work week only, 1=full week Sunday start, 2=half weekends Sunday start, 3=full week Monday start, 4=half weekends Monday start | `blockplan`: default `0`; choices `0, 1, 2, 3, 4` |
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

| Name | Required | Description |
|---|---|---|
| `START_DATE` | yes | Start date in YYYYMMDD format |
| `END_DATE` | yes | End date in YYYYMMDD format |

Generates an Excel workbook (`.xlsx`) with timeband rows at the top, a column-header row, and 100 empty data rows ready for project planning. Timeband configuration uses `excelheader.top_time_bands` and `excelheader.vertical_lines` from the active theme. See [ExcelHeader](#excelheader-subcommand) for full details.

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
- Column header time bands follow the same schema as `blockplan.top_time_bands`. Supported units: `week`, `month`, `fiscal_quarter`, `interval`. Week-unit columns support `{n}` (sequential week number), `{start}` and `{end}` (M/D date strings) format tokens. Alternate-fill columns (`alt_fill_color`) color every other column segment. Each band supports a `text_align` key (`"left"` / `"center"` / `"right"`, default `"left"`) that controls the horizontal alignment of the label within its segment — `"left"` pins the text to the left edge, `"center"` centres it, and `"right"` pins it to the right edge. Text is always shrunk to fit the segment width regardless of alignment.
- The layout is content-first and always shrunk: the axis is fixed at the vertical centre of the content area, duration rows are placed around it, then the header bands float `compact_plan.header_bottom_y` pts above the topmost row and the legend floats `compact_plan.key_top_y` pts below the bottommost row. The SVG viewBox is trimmed to exactly the rendered content, producing the smallest possible output.
- The legend and milestone roster are rendered **side by side** in a two-column layout starting at the same vertical position. The fraction of the total width given to the left column is controlled by `compact_plan.legend_column_split` (default `0.5`; a fixed 8 pt gap separates the columns).
  - **Left column** (controlled by `compact_plan.show_legend`): one row per resource group. When `show_duration_icons` is enabled the row layout is `[icon] [swatch line] [Group Name: names…]`; otherwise `[swatch line] [Group Name: names…]`. The icon matches the one drawn on the duration line for that group. Names are **wrapped**: as many comma-separated names as fit are placed on the header row; any that overflow wrap onto continuation rows indented to align with the text start (no icon or swatch repeated).
  - **Right column** (controlled by `compact_plan.show_milestone_list`): a date-sorted roster of every milestone marker. Each row shows the date (formatted by `compact_plan.milestone_list_date_format`, Arrow format string, default `M/D`) in a fixed-width left sub-column and the task name in the remaining sub-column width.
- **Continuation icons**: when a duration event's end date extends beyond the specified calendar end date the line is clamped to the right edge of the timeline. If `compact_plan.show_continuation_icon` is `true` (the default), a small icon is drawn at the right edge of the clamped line and a corresponding legend entry is appended below the milestone roster. The icon name (default `"arrow-right"`), display height in points (default `8.0`), and color (default: inherits the line color) are set by `compact_plan.continuation_icon`, `continuation_icon_height`, and `continuation_icon_color` respectively. A theme may instead `define icon:continuation` and bind it to `ec-continuation-icon` — values declared there (`icon`, `size`, `color`) override the `compact_plan.continuation_icon*` defaults. The legend text is set by `continuation_legend_text` (default `"activity continues"`) and the gap above it by `continuation_section_gap` (default `4.0` pts). Icons are loaded from the `icons` table in the database.
- All text areas (band headers, milestone labels, legend entries, milestone roster, continuation legend) support independent font name, font size, color, and opacity settings in the theme via the `compact_plan` section.
- `--shade` highlights the current day column when today falls within the date range.
- `--weekends` controls whether weekend columns are included in the x-axis day list (same as all other commands).

### `help`

| Name | Required | Description | Choices |
|---|---|---|---|
| `subcommand` | yes | Subcommand to show help for | weekly, mini, mini-icon, text-mini, timeline, blockplan, compactplan, themes, papersizes, patterns, icons, colors, palettes, fonts, exportdata |

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
`--mini-columns`, `--mini-rows`, `--weeknumbers`, `--week1-start`, `--week-number-mode`, `--mini-no-adjacent` (`-mna`), `--mini-grid-lines`, `--mini-details`, `--mini-title-format`, `--shade`, `--weekends`, `--weekend-days`, `--theme`, `--papersize`, `--orientation`, `--margin`, `--header`, `--footer`, `--watermark`, and all filter flags.

### `palettesheet`

| Name | Required | Description | Choices |
|---|---|---|---|
| `NAME` | yes | Name of the palette to preview (case-sensitive, from DB `palettes` table) |  |

Renders a single named palette as an SVG swatch sheet. Run `ecalendar.py palettes` to discover palette names.

### `patternsheet`

No positional arguments. Use `--filter` to narrow the rendered grid by pattern name and `--color` to set the tile fill (default `#333333`). Run `ecalendar.py patterns` to discover pattern names.

### `iconsheet`

No positional arguments. Use `--filter` to narrow the rendered grid by icon name and `--color` to set the stroke color (default `#333333`). Run `ecalendar.py icons` to discover icon names.

### `colorsheet`

No positional arguments. Use `--filter` to narrow the rendered grid by color name. Run `ecalendar.py colors` to discover color names.

### `fontsheet`

No positional arguments. Three sample rows (uppercase, lowercase, digits/punct) are drawn for each registered font. Use `--filter` to narrow by font name, `--color` to set glyph color (default `#222222`), and `--fullset` to render every glyph in each font instead of the three fixed rows. Note that `--database` is not accepted because font files come from the `fonts/` directory rather than the DB.

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
- The `--shade` flag does not shade timeline events or bars. Instead, the timeline has a dedicated today marker: a vertical line and label rendered only when the resolved today date falls inside the displayed date range.

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

## Theme System

Themes are YAML files describing the visual style of SVG output via a single ordered `style_rules` list. Each rule either **defines** a named style token (text, box, line, or icon) or **applies** a style to a specific surface (an `ec-*` element class, a content surface like `box:day` or `box:duration`, or a lane assignment). Non-styling configuration — format strings, geometry, fiscal semantics, structural lane and band declarations — lives in dedicated top-level sections.

There is one supported schema. Legacy themes (`text_styles` / `box_styles` / `line_styles` / `icon_styles` / `element_styles` / `axis` / `swimlane_rules` top-level keys) are rejected with a parse error pointing at `tools/migrate_theme.py`. Run the migrator once on any existing theme:

```bash
uv run python tools/migrate_theme.py --in-place path/to/theme.yaml
```

The 17 bundled themes (`default`, `corporate`, `dark`, `vibrant`, `accent`, `leemini`, `Julia`, `TJX`, `TJX*`, `minimal`, `basic`, `SAMPLE`) are already in the unified schema. Two reference themes serve as anchors:

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

#### Style Rules: Element Bindings

`ec-*` CSS classes are bound to tokens by `apply_to: element` rules with `select.element: <ec-name>` and `style.use: <token>`:

```yaml
style_rules:
  - name: bind ec-heading
    apply_to: element
    select: { element: ec-heading }
    style: { use: text:heading }

  - name: bind ec-today-label
    apply_to: element
    select: { element: ec-today-label }
    style: { use: text:label, color: red }   # per-element color override
```

A list-valued `select.element` binds several classes at once. Additional style keys override the referenced token.

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

Every SVG element gets a semantic CSS class. These classes appear in the SVG output and can be used for external CSS overrides.

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
| `ec-continuation-icon` | icon | Continuation arrow drawn on a duration that extends past the visible range (compactplan) |
| `ec-overflow-icon` | icon | Overflow indicator |
| `ec-legend-swatch` | legend | Legend color swatch |
| `ec-legend-text` | legend | Legend item text |
| `ec-legend-icon` | legend | Legend item icon |

Modifier classes (added alongside element class): `ec-holiday`, `ec-nonworkday`, `ec-current-day`, `ec-adjacent`.

### Creating a New Theme

The fastest path is to copy `config/themes/basic.yaml` — the minimum viable theme — and edit. `basic.yaml` ships with every required key set to a plain default, so each line you change is a deliberate styling choice. Recipe:

1. Start with a `theme:` metadata block (name, version, description).
2. Define the `style_rules` tokens you need with `define:` entries — typically a few `text:` tokens (heading, body, day_number…), one or two `box:` tokens (cell, header), and any `icon:` tokens you reference.
3. Bind tokens to the `ec-*` element classes that need them via rules of the form:

   ```yaml
   - apply_to: element
     select: { element: ec-name }
     style: { use: text:heading }
   ```

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
| `footer_left_font` | `footer.left.font_family` | `str` | `Fonts.RC_LIGHT` | font family |
| `footer_left_font_color` | `footer.left.font_color` | `str` | `'grey'` | font color |
| `footer_left_font_size` | `footer.left.size_rule` | `float | None` | `None` | Per-papersize footer-left font size rule |
| `footer_right_font` | `footer.right.font_family` | `str` | `Fonts.RC_LIGHT` | font family |
| `footer_right_font_color` | `footer.right.font_color` | `str` | `'grey'` | font color |
| `footer_right_font_size` | `footer.right.size_rule` | `float | None` | `None` | Per-papersize footer-right font size rule |
| `group_colors` | `colors.group_colors` | `list` | `field(default_factory=lambda: ['bisque', 'skyblue', 'lawngreen', 'cyan', 'pur...` | List of group colors |
| `header_center_font` | `header.center.font_family` | `str` | `Fonts.R_BLACK_ITALIC` | font family |
| `header_center_font_color` | `header.center.font_color` | `str` | `'grey'` | font color |
| `header_center_font_size` | `header.center.size_rule` | `float | None` | `None` | Per-papersize header-center font size rule |
| `header_left_font` | `header.left.font_family` | `str` | `Fonts.R_BLACK_ITALIC` | font family |
| `header_left_font_color` | `header.left.font_color` | `str` | `'grey'` | font color |
| `header_left_font_size` | `header.left.size_rule` | `float | None` | `None` | Per-papersize header-left font size rule |
| `header_right_font` | `header.right.font_family` | `str` | `Fonts.R_BLACK_ITALIC` | font family |
| `header_right_font_color` | `header.right.font_color` | `str` | `'grey'` | font color |
| `header_right_font_size` | `header.right.size_rule` | `float | None` | `None` | Per-papersize header-right font size rule |
| `imagemark_rotation_angle` | `watermark.imagemark_rotation_angle` | `float` | `0.0` | imagemark rotation angle |
| `item_placement_order` | `events.item_placement_order` | `list[str]` | `field(default_factory=lambda: ['priority'])` | item placement order |
| `margin_bottom` | `layout.margin.bottom` | `float | None` | `None` | Bottom margin; supports points or units like in/mm |
| `margin_left` | `layout.margin.left` | `float | None` | `None` | Left margin; supports points or units like in/mm |
| `margin_right` | `layout.margin.right` | `float | None` | `None` | Right margin; supports points or units like in/mm |
| `margin_top` | `layout.margin.top` | `float | None` | `None` | Top margin; supports points or units like in/mm |
| `theme_company_holiday_alpha` | `colors.company_holiday.alpha` | `float | None` | `None` | Company holiday alpha override |
| `theme_company_holiday_color` | `colors.company_holiday.color` | `str | None` | `None` | Company holiday color override |
| `theme_federal_holiday_alpha` | `colors.federal_holiday.alpha` | `float | None` | `None` | Federal holiday alpha override |
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
| `watermark` | `watermark.text` | `str` | `''` | text |
| `watermark_alpha` | `watermark.alpha` | `float` | `0.3` | alpha |
| `watermark_color` | `watermark.color` | `str` | `'white'` | color |
| `watermark_font` | `watermark.font_family` | `str` | `Fonts.R_BLACK` | font family |
| `watermark_resize_mode` | `watermark.resize_mode` | `str` | `'fit'` | "fit" (default) or "stretch" |
| `watermark_rotation_angle` | `watermark.rotation_angle` | `float` | `0.0` | rotation angle |
| `watermark_size` | `watermark.font_size` | `int | None` | `None` | font size |

#### `weekly`

| Config field | Theme key | Type | Default | Explanation |
|---|---|---|---|---|
| `day_box_fill_color` | `weekly.day_box.fill_color` | `str` | `'grey'` | fill color |
| `day_box_fill_opacity` | `weekly.day_box.fill_opacity` | `float` | `0.25` | fill opacity |
| `day_box_font_color` | `weekly.day_box.font_color` | `str` | `'navy'` | font color |
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
| `mini_details_header_font_size` | `mini_details.header_font_size` | `float | None` | `None` | header font size |
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

`mini-icon` shares all theme keys from the `mini` section above — every `mini_calendar.*` theme key applies identically. The one additional config field is not theme-configurable (set via `--mini-icon-set` / `-mis`):

| Config field | Theme key | Type | Default | Explanation |
|---|---|---|---|---|
| `mini_icon_set` | *(not themeable)* | `str` | `'squares'` | Icon set used for day-number icons. Choices: `squares`, `darksquare`, `circles`, `darkcircles`, `squircles`, `darksquircles`. |

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
| `timeline_callout_offset_y` | `timeline.callout_offset_y` | `float` | `96.0` | callout offset y |
| `timeline_connector_stroke_dasharray` | `timeline.connector_stroke_dasharray` | `str | None` | `None` | connector stroke dasharray |
| `timeline_date_color` | `timeline.date.font_color` | `str` | `'deepskyblue'` | font color |
| `timeline_date_font` | `timeline.date.font_family` | `str` | `Fonts.R_BOLD` | font family |
| `timeline_date_format` | `timeline.date_format` | `str` | `'MMM D'` | date format |
| `timeline_duration_*_font_size` | `timeline_durations.size_rule` | `` | `` | Per-papersize timeline duration font sizes |
| `timeline_duration_bar_fill_opacity` | `timeline.duration_bar_fill_opacity` | `float` | `0.25` | duration bar fill opacity |
| `timeline_duration_bar_stroke_dasharray` | `timeline.duration_bar_stroke_dasharray` | `str | None` | `None` | duration bar stroke dasharray |
| `timeline_duration_box_height` | `timeline_durations.box_height` | `float | None` | `None` | box height |
| `timeline_duration_box_width` | `timeline_durations.box_width` | `float | None` | `None` | box width |
| `timeline_duration_bracket_stroke_dasharray` | `timeline.duration_bracket_stroke_dasharray` | `str | None` | `None` | duration bracket stroke dasharray |
| `timeline_duration_date_color` | `timeline_durations.date_color` | `str | None` | `None` | date color |
| `timeline_duration_date_font` | `timeline_durations.date_font` | `str | None` | `None` | date font |
| `timeline_duration_date_font_size` | `timeline_durations.date_font_size` | `float | None` | `None` | date font size |
| `timeline_duration_lane_gap_y` | `timeline.duration_lane_gap_y` | `float` | `8.0` | duration lane gap y |
| `timeline_duration_name_font_size` | `timeline_durations.name_font_size` | `float | None` | `None` | name font size |
| `timeline_duration_notes_font_size` | `timeline_durations.notes_font_size` | `float | None` | `None` | notes font size |
| `timeline_duration_offset_y` | `timeline.duration_offset_y` | `float` | `44.0` | duration offset y |
| `timeline_duration_text_color` | `timeline_durations.text_color` | `str | None` | `None` | text color |
| `timeline_event_*_font_size` | `timeline_events.size_rule` | `` | `` | Per-papersize timeline event font sizes |
| `timeline_event_box_height` | `timeline_events.box_height` | `float | None` | `None` | box height |
| `timeline_event_box_width` | `timeline_events.box_width` | `float | None` | `None` | box width |
| `timeline_event_name_font_size` | `timeline_events.name_font_size` | `float | None` | `None` | name font size |
| `timeline_event_notes_font_size` | `timeline_events.notes_font_size` | `float | None` | `None` | notes font size |
| `timeline_event_text_color` | `timeline_events.text_color` | `str | None` | `None` | text color |
| `timeline_icon_size` | `timeline.icon_size` | `float` | `8.0` | icon size |
| `timeline_label_fill_opacity` | `timeline.label_fill_opacity` | `float` | `0.25` | label fill opacity |
| `timeline_label_stroke_dasharray` | `timeline.label_stroke_dasharray` | `str | None` | `None` | label stroke dasharray |
| `timeline_label_stroke_width` | `timeline.label_stroke_width` | `float` | `1.0` | label stroke width |
| `timeline_marker_radius` | `timeline.marker_radius` | `float` | `6` | marker radius |
| `timeline_marker_stroke_color` | `timeline.marker_stroke_color` | `str` | `'black'` | marker stroke color |
| `timeline_marker_stroke_width` | `timeline.marker_stroke_width` | `float` | `1.0` | marker stroke width |
| `timeline_notes_color` | `timeline.notes.font_color` | `str` | `'deepskyblue'` | font color |
| `timeline_notes_font` | `timeline.notes.font_family` | `str` | `Fonts.RC_BOLD` | font family |
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
| `excelheader_font_name` | `excelheader.font_name` | `str` | `'Calibri'` | system-installed Excel font for all cells |
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
| `element` | Bind a CSS class to a token via `select.element` + `style.use` |
| `lane` | Route content to a swimlane via `style.swimlane` (blockplan) |

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
| `size` | Icon size in points. **Optional** — when omitted, each visualizer falls back to its own default: weekly event/duration icons use `event_icon_font_size` (which tracks the event-name text size); compactplan duration and continuation icons use `compact_plan.duration_icon_height` and `continuation_icon_height` respectively. Declaring `size:` on the bound `icon:` token overrides those defaults. |

#### `style:` — Element-Binding Properties (for `apply_to: element`)

| Property | Notes |
|---|---|
| `use` | Reference to a token (`text:heading`, `box:cell`, …). The element inherits the resolved token's style. |
| Any text/box/line/icon property | Overrides the referenced token for this element only. |

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

blockplan:
  top_bands:
    - { band: fiscal_quarter, row_height: 25 }   # inline geometry override
    - { band: month,          row_height: 20 }
  bottom_bands: []

compact_plan:
  bands: [fiscal_quarter, month]

excelheader:
  top_bands: [fiscal_quarter, month]
  band_fonts:
    fiscal_quarter: { excel_font_name: "Arial Narrow", excel_font_size: 10 }
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
| `unit` | `str` | `fiscal_quarter` \| `month` \| `week` \| `interval` \| `date` \| `dow` \| `countdown` \| `countup` |
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

> **`countdown` unit:** Each visible day cell shows the number of counting-days between that day and `target_date`. The value is **0** on the target day itself, **positive** for days before it (days remaining), and **negative** for days after (days elapsed). Use `label_format: "{n}d"` to append a suffix, or `label_format: "D-{n}"` for a launch-style label. Combine `skip_weekends: true` and `skip_nonworkdays: true` to count only business days.

> **`countup` unit:** Each visible day cell shows the number of counting-days elapsed since `start_date`. The value is **0** on the start day itself, **positive** for days after it (days elapsed), and **negative** for days before it (days prior to the origin). Use `label_format: "D+{n}"` for a project-day-style label. The same `skip_weekends` / `skip_nonworkdays` options apply.

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
- `mini` — `mini_calendar.title_format`, layout dimensions; `mini_calendar.icon_set` name (mini-icon variant).
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

Freeze panes are set at column F / the column-header row so timebands and label columns stay visible when scrolling.

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

All standard `unit` types are supported in the catalog: `fiscal_quarter`, `month`, `week`, `interval`, `date`, `dow`, `countdown`, `countup`, and `icon`.

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
