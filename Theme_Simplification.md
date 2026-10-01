# Plan: one decoration model, one default theme

Based on a read of the theme YAMLs, `config/theme_engine.py`, `shared/timeband.py`, the config fields and the renderers' band, tick, today-line and leader code. Decisions from the open questions are folded in below; what is still open is at the end.

## What the code shows

- **Half of `default.yaml` is not decoration.** `style_rules` and `element_overrides` take about 575 of its 1,148 lines. They sit beside section keys, `time_bands` and `theme_*` config fields, so one visual has several places to be set. That is the "set here, override there" problem.
- **Band rows are drawn five times.** The five implementations are in `blockplan/renderer.py:468`, `compactplan/renderer.py:484`, `gantt/renderer.py:488-675`, `timeline/renderer.py:2227` plus `_draw_fiscal_bands` at `:3041`, and `excelblockplan.py:671`.
- **Axis ticks are implemented twice more.** Timeline has `_compute_band_ticks`, `_draw_axis_ticks_from_band` and `_draw_month_ticks`. Pit has `_pit_tick_segments` and `_draw_axis_ticks`.
- **Today lines are drawn four times**, in timeline, pit, gantt and compactplan.
- **Lines are drawn in several places.**
  - Leaders: `timeline/labella_adapter.py` and `pit/labella_adapter.py`.
  - Markers: `pit/markers.py`.
  - Dependency arrows: `gantt/dependencies.py` and `_draw_arrow`.
  - Connectors: `timeline._draw_duration_connectors`.
- **`AxisFrame` already exists** in `timeline/axis.py`. It is orientation-agnostic, so it is the right seed for the shared span mapper.
- **Decoration is spread beyond the duration views.**
  - `number_duration_icons` has 9 per-view flags.
  - Palettes are set in `colors:`, `blockplan.palette`, `compact_plan.palette`, `timeline.palette`, `pit.label_palette` and `timeband_fill_palette`.
  - Holiday handling is split across `colors.*_holiday`, `mini_calendar.holiday_color`, `blockplan` and `compact_plan.*_holiday_icon`, the timeline `holiday_*` keys, and `text_mini.holiday_symbols`.
  - Fonts appear as `base.font_family`, `cell_bold_font`, `today_line.label_font_name` and the watermark font.
  - `week_start` and `fiscal_year_start_month` are set in the blockplan block and per band.
- **text_mini symbols are inline arrays.** The event, milestone, holiday, nonworkday and duration symbol lists, plus the week and day digit lists, are literals in the theme and `CalendarConfig` (`text_mini_*_symbols`, `text_mini_*_digits`).
- **Legacy machinery is large.**
  - `config/retired_style_keys.py` and `tools/convert_style_keys.py`
  - `legacy_hint`, `_check_retired_style_keys`, `_check_deprecated_rule_keys` and `_is_new_format` in `theme_engine`
  - the `time_bands` catalog and `_apply_band_placements`
  - the `label_format` / `date_format` alias in `shared/timeband.py`
  - the "legacy config field" layer in `docs/architecture/theme-resolution.md`
  - the 9 non-default themes

## Principles (rules the code can enforce)

1. **Decoration is declared once, at the top level.** Fonts, text/box/icon/line roles, palettes, timescale, today, holidays and duration icons are all declared there.
2. **View blocks hold structure only.** Examples are gantt columns, blockplan swimlanes, weekly day-box geometry, pit direction and labella tuning, Excel column widths. A view block may not contain any key that the decoration schema owns.
3. **`style_rules` is for conditional content styling only.** It selects events or days and styles them. It defines nothing, `element_overrides` is gone, and rules cannot select on visualizer or paper size.
4. **One schema is the single source of truth.** Dataclasses are the only defaults. They drive validation, `demonstration.yaml` completeness, the docs key reference and CLI help.
5. **Every element has one draw routine.** Each view calls it with its own geometry.

## Decisions

| # | Decision |
|---|---|
| 1 | One band stack for all views. No per-view selection and no `views:` filter. |
| 2 | Output will change versus the refcorpus. Parity is not a gate; the refcorpus is re-baselined at each phase after review. |
| 3 | `style_rules` `define` rules and `element_overrides` are removed. |
| 4 | Schema dataclasses are the only defaults. A theme may omit anything. |
| 5 | The 9 non-default theme files are deleted. |
| 6 | A row may declare both `tick:` and cell facets. `top_bands` / `bottom_bands` are renamed `primary` / `secondary` (sides of the axis). |
| 7 | Candybar's merged month boxes and weekly's fiscal period labels move to the timescale engine. |
| 8 | Gantt pagination runs continuously across pages. |
| 9 | Excel formatting uses Excel units. |
| 10 | CLI overrides become view-independent flags. |
| 11 | `number_duration_icons` names the icon set. A second global flag, `replace_icons_with_numbers`, defaults to true. |
| 12 | Names accepted: `timescale`, `lines`, `palettes`, `fonts`, `holidays`. |
| 13 | Old themes are not supported. The program fails with a message that the specified theme is not supported. |
| 14 | text_mini glyphs move to a new `Glyphs` database table. A theme names a glyph group for each role. |
| 15 | Grid views draw only the rows whose unit their geometry can express and skip the rest. Candybar's `primary` side is the right side, so `secondary` is the left. |
| 16 | One density rule in the engine: a label wider than its segment is compressed horizontally to fit (never hidden), and a row is dropped when its segments are narrower than the theme's `timescale.min_segment_width`. Gantt's `min_day_width` pagination stays as view structure. |
| 17 | The `select: visualizer:` and `select: papersize:` selectors are removed. Styles are view-independent, per-view differences come from structure keys, and paper-size scaling is a `size_by_paper` field on `text:` roles. |
| 18 | `extends:` inheritance is removed. |
| 19 | When `replace_icons_with_numbers` is false, the icon-set name is ignored. |
| 20 | No generic `--set <path>=<value>` CLI capability. Only the view-independent flags from decision 10. |
| 21 | Excel-specific decoration (column widths, font name, font size) stays in the `excelblockplan:` block. Excel rows share `height` and the row model with the other views. |
| 22 | Glyph group names are free-form text. The week and day digit lists and `text_mini_duration_fill` (currently "⸬") move into Glyphs, and `mini_calendar.day_number_glyphs` / `day_number_digits` use it too. |
| 23 | A separate script creates and seeds the `glyphs` table. The program does not create it. If the table is missing, the run fails with a message naming the script. The script is run before testing the changes. |
| 24 | At a page break, a segment that would be clipped is dropped from the first page and drawn in full, with its label, on the following page. |
| 25 | Unsupported or misplaced theme content stops the run. A version mismatch says the theme is "not supported". An unknown or misplaced key names its path and the valid keys. |
| 26 | `element_catalog.yaml` stays as the code-side binding of element to role, with its fallback values removed. Roles are defined only in the theme and the schema defaults. |
| 27 | A gantt segment wider than a whole page is drawn clipped on every page it crosses, with its label repeated where it fits. |
| 28 | An unset glyph group means "use the font's own digits". A theme names a group only when it wants glyphs. |

## Target theme shape

```yaml
theme:      { name, version: '3.0' }
fonts:      { family }                       # default family; the registry of names stays in code
text:       # role -> {font, size, color, opacity, align, size_by_paper}: heading, label, day_number,
            #   month_title, week_number, fiscal_label, event_name, event_notes, event_date, …
boxes:      # role -> {fill, fill_opacity, stroke, stroke_width, fill_palette, …}: cell, day, header, band, callout, …
icons:      # role -> {color, size}: event, duration, milestone, overflow, …
lines:      # role -> LineSpec: axis, tick, leader{primary,secondary}, dependency, today, border, grid, separator
palettes:   # month, fiscal, group, event, band
timescale:
  axis:      { line: axis, padding, marker_start, marker_end }    # axis views
  min_segment_width: 3                 # rows with narrower segments are dropped
  primary:   [ <row>, <row>, … ]       # rows fully inline: no catalog, no "use"
  secondary: [ <row>, … ]
today:      { show, date, label, line: today, day_highlight: {…} }
holidays:   { federal: {color, opacity, icon}, company: {…}, show_dates, date_format, icon_size }
durations:  { number_duration_icons: darksquare, replace_icons_with_numbers: true,
              icon_size, icon_background_color, icon_stroke_color }
continuation: { … }                    # unchanged
overflow:     { … }                    # unchanged
fiscal:     { year_start_month, week_start, label formats }
style_rules: [ … conditional content rules only … ]
<view>:     # weekly, mini_calendar, candybar, timeline, pit, gantt, blockplan, compact_plan,
            # excelblockplan, text_mini: structure keys only
text_mini:  { glyphs: { event: <group>, milestone: <group>, duration: <group>, holiday: <group>,
                        nonworkday: <group>, special_day: <group>,
                        day_number_digits: <group>, week_number_digits: <group> } }
```

A timescale row is the single "divide a distance into day segments and group them" object:

```yaml
- unit: month            # date|dow|week|month|quarter|fiscal_quarter|fiscal_period|year|interval|holiday|icon|countdown|countup
  every: 1               # show_every
  label: Month           # row heading (table views)
  format: MMMM           # one format key; the label_format / date_format alias goes away
  height: 12
  fill: …  opacity: …    # background, or a palette role
  border: { … }          # LineSpec fields inline, or a named line
  text: { font, size, color, align }
  tick: { length, label_side, label_align }   # honoured by axis views (timeline, pit)
  holidays: { nonworkdays_only: true }
```

- **Table views** (blockplan, compactplan, gantt, excel) draw a row as a band of cells. `primary` is above the content and `secondary` below.
- **Axis views** (timeline, pit) draw the same row as ticks and labels along the axis. `primary` is the primary side of the axis and `secondary` the other, following `shared/orientation.py`: above for a horizontal axis, right for a vertical one.
- **Grid views** (candybar, weekly) draw the rows whose unit their geometry can express, such as month, fiscal period, fiscal quarter or week number, and skip the rest. Candybar's `primary` is its right side and `secondary` its left. Weekly uses fiscal rows for its period labels and colouring. Mini, mini-icon and text-mini draw none.
- **Density:** a label is suppressed when its segment is narrower than the text, and a row is dropped when its segments are narrower than `timescale.min_segment_width`.
- A facet a view doesn't use, such as `tick:` in blockplan, is valid and ignored.
- Gantt segments are built once over the whole date range, so grouping by `every` runs continuously across pages. A segment that would cross a page break is dropped from the first page and drawn in full, with its label, on the next page. The first page then has a gap after its last whole segment.

`lines:` roles share one `LineSpec`:

```yaml
color, width, opacity, dasharray, linecap, linejoin,
marker_start, marker_start_size, marker_end, marker_end_size,
start_stub, end_stub,
route: straight | direct | curve
```

The axis, tick, leader, dependency arrow, today line, borders and grid all use `LineSpec`.

### Glyphs table (text_mini)

```sql
CREATE TABLE glyphs (
  glyph_group TEXT NOT NULL,   -- e.g. 'event-a', 'holiday-letters', 'digits-circled'
  seq         INTEGER NOT NULL, -- cycle order within the group
  glyph       TEXT NOT NULL,
  PRIMARY KEY (glyph_group, seq)
);
```

- Group names are free-form text. Which groups exist, and what they hold, is data, not schema.
- Everything now inline moves into rows: the event, milestone, duration, holiday and nonworkday symbol lists, the week and day digit lists, `text_mini_duration_fill`, and the `mini_calendar` day-number glyph and digit lists.
- **A separate script creates and seeds the table** (for example `tools/db/create_glyphs.py`). It holds the seed data taken from the current literals in `config.py` and `default.yaml`, and it can be re-run. `tools/db/build_db.py` calls it for test databases.
- **The program never creates the table.** When `glyphs` is missing, the run stops with a message that names the script and the command to run it.
- The script is run against `calendar.db` and the test databases before any testing of the changes.
- The text_mini and mini renderers keep their existing logic for choosing a glyph per day (`_cycle` per role); only the source of the glyphs changes, from `config.text_mini_*` / `config.mini_*` to `db.get_glyphs(group)`.
- A `glyphs` listing command is added next to `patterns`, `fonts` and `papersizes`.
- Theme side: `text_mini.glyphs` and `mini_calendar.glyphs` each name a group per role. A named group that doesn't exist stops the run and lists the groups that do.

## Shared code (the consolidation)

| New shared module | Replaces |
|---|---|
| `shared/span.py` | Generalises `AxisFrame` and `shared/orientation.py` into a day→position mapper. It handles horizontal or vertical, a portion of the canvas, and page ranges for gantt pagination. It replaces the `pos_for_day` closures in timeline and pit and the per-view day-to-x math. |
| `renderers/timescale.py` | Builds segments (`shared/timeband`, `holiday_band`, `icon_band`), groups them by `every`, and draws rows as cells or ticks. It replaces the 5 band drawers, the 2 tick drawers, `_draw_fiscal_bands`, candybar's month boxes and weekly's fiscal labels. Excel keeps its own writer but consumes the same row model. |
| `renderers/lines.py` | `LineSpec`, `MarkerSpec`, stub routing and `draw_line`. It replaces the line code in `pit/markers.py`, both labella adapters' drawing, `gantt._draw_arrow`, the connector code and 4 today-line drawers. |
| `shared/today.py` | One `resolve_today`, used by every view. |
| `shared/holidays.py` | One mark resolver for flags, icons, colours and date text. It replaces the timeline holiday code, `gantt._draw_holiday_band_row` and the blockplan and compactplan federal/company icon keys. |
| `config/theme_schema.py` | The dataclass schema. It drives the strict loader, defaults, docs and the completeness test. |
| `shared/db_access.py` glyph queries | `get_glyphs(group)`, `list_glyph_groups()`, and the missing-table error. |
| `tools/db/create_glyphs.py` | Creates and seeds the `glyphs` table. Replaces the inline symbol and digit lists in `CalendarConfig` and the themes. |

After this, `CalendarConfig` loses its prefixed decoration fields (`pit_*`, `timeline_*`, `gantt_*`, `theme_*`, `*_time_bands`, 9 `*_number_duration_icons`, `text_mini_*_symbols`, `text_mini_*_digits`, `text_mini_duration_fill`, `mini_day_number_*`) in favour of `config.decoration`. `theme_engine.py` (2,268 lines) shrinks to a loader, because there is no `THEME_TO_CONFIG_MAP` to maintain.

## Phases

No dual-path shims. Each cutover deletes the old code in the same change.

- **Phase 0 – Baseline and inventory. Done; see `Theme_Phase0_Findings.md`.**
  - Render the refcorpus for `default.yaml` across all views as a before-picture. Per memory, `check` fails until you render once, and you need `UV_NO_SYNC=1`.
  - Run an inventory script that lists every decoration key the default theme sets, and where.
  - Audit CLI flags that write per-view decoration fields, starting from `_CLI_CONFIG_OVERRIDES` in `cli/config_assembly.py`.
- **Phase 1 – Schema and loader. Done; see `config/theme_schema.py`, `config/theme_loader.py` and `Theme_Schema_Mapping.md`.**
  - Add `theme_schema.py` and the strict loader. Theme version 3.0 is required.
  - A theme with another version stops the run with "theme '<name>' is not supported". An unknown or misplaced key reports its path and the valid keys. Neither message points to a converter.
- **Phase 2 – Shared engines and the Glyphs table. Done; see Phase 2 results below.**
  - Build `span`, `lines`, `timescale`, `today` and `holidays`, each with unit tests built from schema objects, no theme file involved.
  - Write the glyphs create-and-seed script, the listing command and the DB queries, then run the script against `calendar.db` and the test databases.
- **Phase 3 – Cut over, one family per change.** Each step ends with a gallery review and a re-baseline of the refcorpus.
  - a) Table views: blockplan, compactplan, gantt and excel use `timescale`. **Timescale and the holiday and weekend treatment of band cells are done (see Phase 3a results below); today, lines, durations, events, palettes and the role tables are still to do for these views.**
  - b) Axis views: timeline and pit use `timescale` and `lines`. Their tick, fiscal-band, today and leader code goes.
  - c) Gantt arrows and dependencies move to `lines`.
  - d) Weekly, mini and candybar consume `palettes`, `holidays`, `text`, `today.day_highlight`, `fiscal` and `durations`. Candybar month boxes and weekly fiscal labels move to the timescale engine. Their `current_day_color`, `holiday_color` and similar keys go.
  - e) text_mini and mini read their glyphs from the Glyphs table.
- **Phase 4 – Themes.**
  - Rewrite `default.yaml` in the new shape, with one band stack. Start from gantt's, the richest, and tune it with the gallery.
  - Fold the `style_rules` definitions into `text`, `boxes`, `icons` and `lines`.
  - Write `demonstration.yaml`, heavily commented, with every supported attribute and its allowed values.
  - Delete Julia, SAMPLE, TJX, accent, basic, corporate, dark, minimal and vibrant.
  - Fix their fixtures: `tests/test_theme_engine*.py`, `test_validate_theme.py`, `test_required_keys.py`, `test_timeline.py`, the gallery tool, and `basic.yaml` as the example source for missing-key messages.
- **Phase 5 – Legacy purge.** Delete all of these:
  - `retired_style_keys.py`, `tools/convert_style_keys.py` and their tests
  - `legacy_hint`, `_check_retired_style_keys`, `_check_deprecated_rule_keys`, `_is_new_format`
  - the `time_bands` catalog and `_apply_band_placements` / `_resolve_band_placement`
  - the `timeline.show_fiscal_*` flags
  - the timeband format aliases
  - the "legacy config field" precedence layer
  - `element_overrides`, `element_catalog_defaults.yaml`, the `define` rule parser and the `visualizer:` / `papersize:` selectors
  - `config/theme_inheritance.py`, `extends:` / `unset:` handling and `tools/derive_theme.py`, with their tests
  - `required_keys.py` and the missing-key example machinery in `tools/validate_theme.py`, since defaults now live in the schema
- **Phase 6 – Docs and help.**
  - Update these:
    - `docs/USER_GUIDE.md` (3,391 lines; the Theme System, time_bands, Theme bindings and Timeband Configuration sections)
    - `docs/architecture/theme-resolution.md` and `visualizers.md`
    - `docs/cli_theme_overrides.html`
    - the help text in `cli/args.py` (the `--fiscal` description mentions `theme timeline.show_fiscal_*`, and the `themes` listing prints the theme names)
    - `docs/changelog.md`
    - the generated option catalog
  - Run `tools/check_user_guide.py` against the new schema.
  - Update the memory notes (theme structure, built-in themes list).
- **Guards that stay behind** (these enforce the principle):
  1. A view block may contain only its own structure keys.
  2. `demonstration.yaml` loads and contains every schema key.
  3. `CalendarConfig` has no per-view decoration fields.
  4. Each decoration element (today line, axis, band row, leader) has exactly one draw function.

## Phase 2 results

New modules, each with tests, none wired into a renderer yet:

| Module | What it does |
|---|---|
| `shared/span.py` | `Span` (days to positions; hidden days own no cell and snap forward), `Frame` (horizontal or vertical placement, ported from `AxisFrame`), `paginate` and `clip_segments`. |
| `shared/today.py` | `parse_day`, `resolve_today` (pinned date or the clock), `today_position`. |
| `shared/holidays.py` | `resolve_day_styles`: classes, fill, opacity, static icon and country flags per day, from the `holidays` block. |
| `renderers/lines.py` | `line_path` (straight or curve, with stubs), `MarkerRegistry` (arrow-head, circle, diamond, square; start markers are mirrored, not auto-reversed), `line_svg`, `draw_line`, `stroke_attrs`. Its curve matches labella's `hCurveBetween` / `vCurveBetween` exactly, which a test asserts. |
| `renderers/timescale.py` | `plan_rows` turns rows into cells, ticks and vlines with resolved styles; `draw_cells`, `draw_headings`, `draw_ticks`, `draw_vlines` draw a plan. Applies the density rule, grouping by `every`, palettes, holiday fills and flags. |
| `tools/db/create_glyphs.py`, `glyphs_seed.json` | Creates and seeds the `glyphs` table (10 groups, 201 glyphs). `tools/db/build_db.py` calls it. |
| `shared/db_access.py`, `cli/errors.py`, `ecalendar.py` | `get_glyphs`, `list_glyph_groups`, `GlyphsTableMissingError` (names the script), and a `glyphs` listing command. |

Also done: `shared/timeband.py` gained `quarter` and `year` units, so quarters, fiscal quarters, months, weeks, days and increments are all available to ticks and bands. I ran the glyphs script against `calendar.db`. Tests: 1,996 passed; ruff and ty are clean.

Schema changes made while building the engines:
- `Route` is `straight | curve`. `direct` is gone: labella's chained routing (`leader.direct: false`) has no successor.
- `RowTick.label_side` is gone. A row's side of the axis is the list it sits in.
- `TimescaleRow.fill_rules` and `palettes.band` are gone. A row's unset fill comes from `boxes.band` (a single fill or a palette cycled per cell), and holiday and weekend tints come from `holidays`, for every view.
- `TimescaleRow.fill_opacity` is unset by default so it can fall back to `boxes.band`.

Left for Phase 3: `renderers/timescale.py` still reaches `shared/timeband.py` through a small dictionary adapter (`_band_dict`), because that module reads the old key names. Phase 3 rewrites `shared/timeband.py` to take rows and deletes the adapter along with the old band drawers.

## Phase 3a results (table views: timescale)

Blockplan, compactplan, gantt and Excel now draw their bands from `timescale.primary` / `timescale.secondary` through `renderers/timescale.py`, and the old band code is gone from all four.

- **Deleted:** blockplan's `_draw_time_bands`, vertical-line and band-style methods (about 900 lines); gantt's band stack, heading, row and holiday-row drawers and its segment builder; compactplan's band drawer and segment builder; Excel's segment grouping, vertical-line mapping and its dependency on `BlockPlanRenderer`.
- **Deleted config:** the `*_time_bands` fields and `get_gantt_bottom_bands`, the dead holiday, weekend, timebands-fill, header-alignment and `band_row_height` fields (blockplan, compactplan, gantt) and 15 Excel fields, with their theme keys in all ten themes. `required_keys.py` and `generate_default_renderer_values.py` follow.
- **Transitional plumbing:** `CalendarConfig.theme_v3` holds the version-3.0 theme. `ecalendar.run()` loads `config/themes_v3/default.yaml` into it whether or not `--theme` is given. Both go when the last view is cut over and `default.yaml` is rewritten (Phase 4).
- **Checked against the baseline:** a refcorpus check shows only blockplan, compactplan and gantt differ from the Phase 0 render (all three themes). Weekly, mini, mini-icon, candybar, timeline, pit and text-mini are byte-identical, which confirms the unmigrated views are untouched. Excel isn't in the corpus.
- **Tests:** 1,939 pass. `tests/band_helpers.py` puts rows on a config for tests. About 60 tests were rewritten for the new rows; `test_theme_band_references.py` is deleted, since the dangling-catalog failure it guarded no longer exists for these views. Tests of removed features (rule-driven vertical lines with column fills, per-band heading styles, bottom-bands-mirror-top, `fill_rules`) are replaced or dropped.

Follow-up decisions applied:
- **Column fills.** A row can now carry `vfill` (a `fill` or `fill_palette`, plus `fill_opacity`) that shades the column under each of its segments down the content area. Blockplan, gantt and compactplan draw it; it works alongside `vline`. Excel does not, since its cells carry the event data.
- **Holiday rows** keep the schema default of closing holidays only (`holidays.nonworkdays_only: true`).
- **Excel** appends the secondary rows after the last data row (or after the column headers when there are no events).
- **Gantt pagination** now breaks days with `shared.span.paginate`, using every row's segments: a page ends before a month or week that fits a page would be cut, and a segment longer than a page is clipped on every page with its label repeated.
- The refcorpus was re-baselined after these changes; only blockplan, compactplan and gantt differ from the Phase 0 baseline kept in `output/_refcorpus_phase0`.

Day-to-position and today (done in the follow-up):
- **One mapper.** `Span` gained `index_at_or_after/before`, `left_of`, `center_of`, `is_visible` and `boundary`. Gantt's `DayAxis` is deleted; compactplan's `day_x`, `_seg_x` and `_date_to_x` and blockplan's `_boundary_x` are deleted. All three use `Span`, as do the timescale engine and the gantt page planner.
- **One today mark.** `renderers/today_line.py` draws the line (`lines.today`) and its label (`text.today_label`) from the theme's `today` block, across the content of blockplan, compactplan and gantt. The fields `gantt_show_today_line` and `gantt_today_date` are gone with their theme keys. `today.date` pins the day for every view.
- **One axis line.** Compactplan draws its axis through the line engine from `lines.axis`, with `timescale.axis.show` and `timescale.axis.padding`. The three `compactplan_*axis*` fields and theme keys are gone. The schema's default axis no longer has an arrowhead, so pit will set one in the default theme when it moves.
- **Gantt non-working columns** are shaded from the theme's `holidays` fills through `resolve_day_styles`, replacing the `box:day` rule evaluation.
- **Transitional default theme** now sets `lines.axis`, `today` and a grey `holidays.weekend`.
- Refcorpus: still only blockplan, compactplan and gantt differ from the baseline; every other view is untouched. 1,960 tests pass.

Still to do in 3a for the table views: durations and events decoration, palettes, and the role tables (text, boxes, icons, lines) in place of the `define` rules and tokens. Dependency arrows and the compactplan duration-bar strokes move to `lines` with the axis views.

Behaviour changes to review (all follow from your decisions):
- The today line, with a "Today" label, now appears in blockplan and compactplan as well as gantt, and sits at the centre of today's cell instead of its left edge.
- Every table view shows the same stack. The default is gantt's five rows, mirrored below. Compactplan has a footer (secondary rows hang below the chart); Excel appends them after the data.
- A label that doesn't fit its cell is hidden (decision 16), where the old code shrank it.
- Every row gets a heading cell, labelled or not; gantt used to skip unlabelled rows.
- Row headings use the row's own text style and `timescale.heading_align`; the separate heading font, size, colour and per-band alignment are gone.

## Phase 3b results (axis views: timeline and pit)

Both views now draw from the shared engines: `Frame.over_range` for positions, `plan_axis_scale` / `draw_axis_beside` / `draw_axis_edges` for the timescale, `draw_today`, and `leader_ends` / `leader_style` plus `draw_line` for leaders. `timeline/axis.py`, the per-view tick, fiscal-band and holiday code, `leader_path_d` and the stub rewriting are deleted, along with the config fields and theme-engine maps that fed them.

Behaviour changes (accepted under decision 2):

- Leaders take `lines.leader` (and the `leader_primary` / `leader_secondary` recolours), not the event colour.
- Pit's axis arrowhead is gone from the default; `timescale.axis.marker_size` sets it when wanted.
- Fiscal bands sit at the page edges. A row without `tick:` is an edge band in both views.
- Positions use cell semantics, so a tick marks the start of its cell.
- Holiday rows draw icon marks with dates beside the axis, sized from `holidays`. Pit gains edge bands and holiday marks it did not have.

Verification: 1,909 tests pass, ruff and ty are clean. The refcorpus differs for blockplan, compactplan, gantt, pit and timeline only; it has been re-baselined.

## Phase 3a follow-up results (table views: roles, durations, events, palettes)

Blockplan, compactplan and gantt (`STYLES_FROM_ROLES = True` on the renderer) now read their styles from the theme's role tables.

- **Roles:** `config/role_styles.py` turns `text`, `boxes`, `icons` and `lines` into the `ThemeStyles` the `config.get_*_style()` accessors read, and into the per-token dictionaries `_tk()` returns. Paper-size scaling is `size_by_paper`; a role without a `font` takes `fonts.family`. Roles the theme omits take the schema defaults.
- **Style rules:** the table views build their `StyleEngine` from `theme_v3.style_rules`. `role_styles.style_rules()` spells a rule's role attributes the way the engine reads them (a `line:` rule's `color`, `width`, `marker_end` and so on). The dependency-arrow target is `line:dependency`.
- **Decoration moved out of config:** 25 fields went, with their theme-engine map entries and keys in the nine old themes: `blockplan_palette`, `compactplan_palette` and their `theme_*_palette_name` (now `palettes.event`, resolved by `shared/palettes.py`); the blockplan and compactplan duration date show/format/colour fields (`durations.dates.*`); `blockplan_duration_icon_visible` (`durations.show_icons`); `blockplan_wbs_group_depth` (`durations.wbs_group_depth`); `blockplan_event_show_date`, `blockplan_event_date_format` and `blockplan_marker_radius` (`events.date`, `events.marker`); `compactplan_duration_name_color` (new `durations.name_color`, unset = contrast with the bar); `gantt_progress_*` (`lines.progress`); `gantt_arrow_*` (`lines.dependency`); `gantt_bar_fill_color` (`boxes.duration.fill`).
- **Transitional default theme** gained `lines.dependency` (navy), a black `boxes.duration` stroke, and the resource-group a to d fill rules.
- **Behaviour changes:** blockplan and compactplan share one duration date format (`M/D`); dependency arrows use `lines.dependency` unless a rule overrides; an old theme's `define` rules no longer reach these three views (only `theme_v3` does).
- **Cell labels** wider than their cell are now compressed to fit instead of hidden (updates decision 16).

Left for the table views: Excel's own style rules (still read from the old theme), and the `ec-*` bindings for roles the schema lacks (`box:vline`, `box:fiscal_band`), which still take the catalog fallback.

## Phase 3b follow-up results (axis views: roles, markers, palettes)

Timeline and pit set `STYLES_FROM_ROLES` (pit adopts the roles at the top of its render), so their text, box, icon and line styles come from the role tables, and their style rules from `theme_v3.style_rules`.

- **Text:** name, notes and date text read `text.event_name`, `text.event_notes` and `text.event_date` (font, size for the paper, colour) through `role_styles.role_text`, in the layout adapters as well as the renderers, so measured and drawn text agree. The page-height size heuristics for timeline and pit are gone.
- **Markers and icons:** `events.marker` (radius, stroke), `icons.event` (size, colour, default icon name) and `icons.milestone` (colour, default icon name) replace the `timeline_marker_*`, `timeline_icon_size`, `pit_dot_*`, `pit_milestone_color` and `pit_default_*_icon` fields.
- **Dates and durations:** `events.date.format` for both views; `durations.show_icons`, `durations.dates.font_size` and `durations.wbs_group_depth` for timeline.
- **Palettes:** timeline callouts, bars and WBS groups cycle `palettes.event` for both sides (the top and bottom colour lists are gone; the palette is resolved to colours once per render). Pit label fills cycle `boxes.callout.fill_palette` if set, else use `boxes.callout.fill`. `palettes.label` is unused by any view and goes at the Phase-4 schema trim.
- **Callout boxes:** `boxes.callout` (fill, opacity, stroke, corner radius, pattern) styles pit's label boxes.
- **Per-event rules:** `shared.callouts.evaluate_callout_style` folds a rule aimed at `line:leader` into the event's leader and one aimed at `box:callout` into its label box, in the role vocabulary (`color`, `width`, `fill`, ...). The old `style: {leader: ..., label: ...}` nesting is gone for these views.
- **Deleted:** 41 config fields, their theme-engine map entries, the timeline palette resolution, the pit decoration sub-blocks (`pit.date_text` colour, font; `pit.label` stroke, fill, pattern, text colour, corner radius) and the matching keys in the nine old themes. `pit.date_text.offset`/`placement` and `pit.label` padding and icon keys stay as structure.
- **Behaviour changes:** timeline and pit share one date format (`M/D`); pit callout boxes now default to the schema's `boxes.callout` (white at 25%, grey 1 pt stroke) instead of unfilled; marker colour defaults come from `icons.*`.

Still to move for these views: the structure keys they read from config (`timeline_event_box_*`, `timeline_labella_*`, `pit_label_padding_*`, ...), which become `timeline:` / `pit:` block reads when `CalendarConfig` loses its per-view fields.

## Phase 3c results (weekly, mini, mini-icon, candybar)

These four views set `STYLES_FROM_ROLES` (candybar and mini-icon inherit it from mini), take their rules from `theme_v3.style_rules`, and resolve the theme's named palettes once per render (`shared.palettes.resolve_theme_palettes`: month and fiscal colour maps, group and event colours; a missing database palette warns and falls back to the built-in colours).

- **Holidays:** weekly day boxes and mini cells take federal and company fill and opacity from `holidays.*` (mini through `shared.holidays.style_for`); candybar's weekend tint is `holidays.weekend`. The synthesized `box:day` rules and `ThemeEngine._apply_color_maps` are gone.
- **Today:** `today.highlight` replaces `shade_current_day` and the mini current-day colour and opacity.
- **Other palettes and shading:** `palettes.month_colors`, `palettes.fiscal_period_colors`, `palettes.group_colors`, `palettes.hash_lines`, `shading.month_opacity`, `fiscal.use_period_colors`, `fiscal.period_opacity`, `fiscal.label_format` and `fiscal.end_label_format`.
- **Mini:** `mini_calendar.*` (adjacent-month colour and opacity, circled milestones, icon scale and opacity, grid lines, month outline, title format, icon set), `week_numbers.label_format`, `text.label_bold` for the bold cell font, and `boxes.milestone` / `icons.milestone` for the milestone circle.
- **Candybar:** the grid colour is `lines.grid`. Month boxes take their format, text (including rotation), fill, palette and border from the first `month` row of `timescale.primary` (the right side); no month row means no month boxes. Month banding uses the month colour map. The `month_label_side` option is gone, so the month column is always on the right.
- **Weekly pattern settings** stay in `weekly.day_box` (this settles the open question: they are not moved to `boxes.day`); the tile validation moved from `CalendarConfig` to the schema.
- **Every view:** `icons.missing` replaces the three `default_missing_icon*` fields, so the missing-icon marker (red exclamation circle by default) now shows in all views.
- **Rules:** a rule aimed at a text role (`text:event_name`, `text:day_number`, ...) now restyles that text for the events or days it selects, in the role vocabulary.
- **Deleted:** about 70 config fields, `_apply_color_maps`, the holiday rule synthesis, the sentinel palette fields, and the matching keys in the nine old themes (the old themes were rewritten with a YAML dump, so their comments are gone).

Not moved yet: the weekly fiscal period labels are still drawn by the weekly renderer (formatted from `fiscal.*`, styled by `text.fiscal_label`); candybar's month geometry still comes from its own layout. Mini and text-mini glyphs still come from config lists, not the Glyphs table (Phase 3e).

## Phase 3c completion (fiscal period labels and candybar months on the timescale engine)

- **Fiscal period labels.** The theme's first `fiscal_period` timescale row now declares what a period is called and how it looks, for weekly, mini and text-mini alike (`renderers.timescale.period_labels` / `grid_period_labels`). The row's `format` is the label template (unset, `fiscal.label_format`), its `text` styles the label over `text.fiscal_label`, and the new `end_format` adds a label on a period's last day (unset, none). A period that opens on a hidden day is labelled on its first visible day; a period joined part-way through has no start label. `fiscal.end_label_format` and `shared.fiscal_renderer.period_label_days` are gone.
- **One declaration, every view.** The default theme now has a `fiscal_period` row on both sides of the timescale. Table and axis views draw it too when `--fiscal` supplies a fiscal calendar; without one the row has nothing to show and the engine drops it.
- **Candybar months.** The layout emits one `MonthRow_C<chunk>_<day>` cell per week row (keyed by the row's last visible day) in place of the merged `MonthBox_*` boxes. The renderer lays the first `month` row of `timescale.primary` down each strip as a vertical span, so the engine merges consecutive rows of a month into one cell and draws its fill, border and label like any other month row. Labels read bottom to top unless the row sets `text.rotation`. `ec-month-box` and `ec-month-box-label` are gone from the element catalog.
- **Cell labels** that run across the axis (horizontal text in a vertical column) are compressed to the column's width, not the cell's length.

## Phase 3e results (glyph groups from the database)

Text-mini and the mini day numbers now read their glyphs from the `glyphs` table (`shared/glyphs.py`), as decisions 14, 22, 23 and 28 describe.

- **Text-mini:** `text_mini.glyphs.{event, milestone, duration, holiday, nonworkday}` name the symbol groups and default to the seeded `text-mini-*` groups; `duration_fill` names a one-glyph group (default `duration-fill`, and `·` if a theme unsets it); `day_number_digits` and `week_number_digits` are unset by default, which prints the font's own digits.
- **Mini (and mini-icon, candybar):** `mini_calendar.glyphs.day_number` (a 31-glyph group) and `day_number_digits` (a 10-glyph group); unset uses the font's own digits, and a day-number group beats a digits group.
- **Errors:** a group the table lacks stops the run with `<theme key>: glyph group '<name>' not found; groups in the database: ...`. A database without the table keeps the `tools/db/create_glyphs.py` message.
- **Deleted:** the ten `text_mini_*` / `mini_day_number_*` config lists, their theme-engine entries and the keys in the old themes. `text_mini.glyphs.special_day` is gone from the schema; special days use the non-working-day group.
- **Tests:** fake databases get `get_glyphs` from `tests/fakes.py` (`GlyphsFromSeed`), which reads the seed file.

## Phase 4 results (themes) and the legacy purge it forced (most of Phase 5)

- **One theme model.** `--theme` (a built-in name or a path; `default` when absent) is loaded by `config.theme_loader.load_theme` into `config.theme_v3` before any command-line option is applied, so an option always beats the theme. The theme's `layout.margin` sets the page margins (`cli.config_assembly.load_run_theme`). A theme of another version stops the run with "not supported"; an unknown key names its path and the valid keys; an unknown details column or glyph group says so. The transitional plumbing (`themes_v3/`, `transitional_v3_theme`, the second apply pass) is gone.
- **Themes.** `config/themes/default.yaml` is rewritten in the new shape (decoration plus the structure values the old default carried). `config/themes/demonstration.yaml` is generated from the schema by `tools/generate_demonstration_theme.py`: every key, its default, the values it accepts, and the schema's own notes. `tests/test_demonstration_theme.py` fails if the file drifts from the generator, does not load, or leaves a schema key out. The nine other themes are deleted.
- **Views read the theme directly.** About 130 structure and general `CalendarConfig` fields (timeline, pit, blockplan, gantt, compact plan, candybar, details, watermark, continuation, overflow, fiscal ...) are gone; renderers read `config.theme_v3.<block>.<key>`. The command-line options that used to write them (`_CLI_CONFIG_OVERRIDES`) now write theme paths (`theme:candybar.row_height`) through `config.theme_paths.set_path`.
- **Text sizes are roles.** `setfontsizes` now sets only the layout ratios and the header and footer sizes (which follow the page height); the page-height heuristics and `_inject_heuristic_size_tokens` are deleted.
- **Numbered duration icons** are one switch, `durations.replace_icons_with_numbers` (on by default), replacing the nine per-view flags.
- **Deleted modules:** `theme_engine.py`, `theme_inheritance.py`, `unified_theme.py`, `retired_style_keys.py`, `required_keys.py`, `palette_resolver.py`, `element_catalog_defaults.yaml`; tools `convert_style_keys.py`, `derive_theme.py`, `validate_theme.py`, `generate_default_renderer_values.py` and `docs/DefaultRendererValues.md`; and the tests of those modules. `config/element_catalog.yaml` stays as the element-to-role binding, with no fallback values.
- **Behaviour changes:** `palette:NAME:INDEX` colour references are not supported in version-3.0 themes; `extends:` / `unset:` are gone; blockplan swimlane rules (`swimlane_rules`) are gone, lanes come from `blockplan.swimlanes`; gantt's continuation icon is the shared `continuation.icon_after`; table-column and swimlane alignment accept `start | middle | end` (`left | center | right` still read in column entries).

Still to do (Phase 6): `docs/USER_GUIDE.md` and the architecture docs still describe the old theme model and the removed themes (`tools/check_user_guide.py` reports 14 stale examples), `docs/cli_theme_overrides.html`, the `--help` text, the changelog, and `StyleEngine`'s now-unused `visualizer` selector and `LaneEngine`.

## Remaining open questions

All earlier questions about the table views are answered; the open ones are the Phase 1 schema calls, each taking its stated recommendation unless you say otherwise.

1. **Weekly hash patterns** (from Phase 1). `weekly.day_box.hash_pattern*` stays in the weekly block because only weekly draws it. `BoxRole` already has `pattern`, `pattern_color` and `pattern_opacity`, so it could be `boxes.day.pattern*` instead. Recommendation: move it to `boxes.day`, and the weekly block disappears.
2. **Mini-calendar appearance keys** (from Phase 1). `adjacent_month_color`, `adjacent_month_opacity`, `event_icon_scale` and `event_icon_opacity` stay in the `mini_calendar` block. They are colour and opacity keys that no other view has an analogue for. The structure-only guard has them on a short allowlist. Recommendation: keep them there.
3. **One event-date format** (from Phase 1). Timeline defaults to `M/D` and pit to `ddd MMM D`. The schema has a single `events.date.format` for every view, so one of them changes.
4. **Gantt, blockplan and Excel headings** (from Phase 1). The label-column heading alignment is now one `timescale.heading_align`. Gantt and blockplan defaulted to left, Excel to right.
5. **`text.label_bold` colour** (from Phase 1). `default.yaml` sets it to `yellow`, which looks like a leftover. The schema default is grey. Recommendation: confirm grey.

## Phase 6 results (docs and help text)

- `docs/USER_GUIDE.md`: Theme System chapter rewritten for the v3 schema (strict loading, roles, palettes, one timescale, style rules, glyph groups, view blocks, swimlanes, creating a theme, element catalog, run details); per-command sections updated; all 44 guide commands run via `tools/check_user_guide.py`; no dead in-guide anchors.
- CLI help (`--theme`, `--fiscal`) and the generated option catalog refreshed.
- Architecture docs rewritten or patched: `theme-resolution.md` (new model), `overview.md`, `render-pipeline.md` (theme loads first, no second pass), `visualizers.md`, `ARCHITECTURE_ecalendar.md`, `CONTRIBUTING.md`, `cli_theme_overrides.html` (now generated from `_CLI_CONFIG_OVERRIDES`), `changelog.md`.
- Code cleanup: `StyleEngine` lost its `visualizer` argument and `_view_matches` (the loader already rejects `select: visualizer`); the unused `LaneEngine` is gone; `excelblockplan.column_width` is wired.
- Gate: ruff, ty and 1694 tests pass.
