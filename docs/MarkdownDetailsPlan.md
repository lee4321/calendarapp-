# Run Folder, Markdown Details & Event CSV — Implementation Plan

Status: implemented (2026-09-14, branch `markdown-details`). Beyond the plan, compactplan's
`show_legend` and `legend_swatch_width` (key-page only) were retired too.

## 1. Goal

Each visualization run writes **one folder** under `output/`. The folder holds:

1. the visualization SVG, plus gantt continuation pages;
2. **`<stem>.md`**, a Markdown details document that **replaces every companion
   detail/key SVG** (gantt `_details`, weekly `_overflow`, mini/mini-icon/candybar
   `_details`, compactplan `_key`);
3. **`<stem>.csv`**, the event data that was included in the visualization;
4. **`icons/`**, one standalone SVG per distinct icon or mark the main visualization
   drew. All are one uniform size, and the Markdown references them.

The Markdown document contains:

* **An Events table.** Columns come from the theme and use the **same column schema
  as `gantt.columns`**. Any `events` table column can be listed, plus render-derived
  columns. These include **the icons actually assigned to each event**: the
  compactplan key's marks, and the icons every other visualizer drew.
* **Color Key**: the colors assigned, their sources, and the events carrying each.
* **Icons & Symbols**: every icon or mark drawn and what it means.
* **Exceptions**: overflows, clipped or snapped bars, unplaced labels, off-chart
  dependencies, dropped icons, and so on.
* **Holidays & Special Days**: a separate table with its own configurable columns.

Once the Markdown document is proven a superset of the old pages (§9), **all
companion SVG page generation is removed** (§8).

## 2. What exists today

| Companion (to be removed) | Where | Content |
|---|---|---|
| Gantt details `_details.svg` | `visualizers/gantt/details.py` | Tasks (via `gantt.columns`; icon columns as "Yes"); Exceptions (Task, Date, Ref, Issue, Detail) from `GanttException` (8 kinds) |
| Weekly overflow `_overflow.svg` | `renderers/svg_base.py::_render_overflow_svg` (`--overflow`) | Event, Start, End, Overflowed on (from `OverflowEntry`) |
| Mini / mini-icon / candybar `_details.svg` | `visualizers/mini/renderer.py::_render_details_svg` + `renderers/event_listing.py` | Events (`mini_details.headers`; notes + "End:" sub-line); Holidays & Special Days (range label, country prefix, kind, notes) |
| Compactplan key `_key.svg` | `visualizers/compactplan/renderer.py::_render_key_svg` | Mark column: `_bar_mark` (bar color swatch + **start icon** + before/after continuation arrows), `_milestone_mark` (**milestone icon** or pennant flag in the milestone color), `_holiday_mark` (**holiday icon**); rows in color-assignment rank; Symbols section |
| Text-mini details (inside `.txt`) | `visualizers/text_mini/renderer.py` | `DetailEntry(symbol, date_text, text, category)`. **Stays**: it is the text view's own content, not a companion SVG |

Building blocks we reuse:

* **Column model.** `visualizers/gantt/columns.py`: `GanttColumn`,
  `resolve_columns`, `cell_value`, `cell_icon_visible`, `FIELD_ALIASES`.
* **Icon drawing.** Every DB icon a renderer draws goes through
  `BaseSVGRenderer._draw_icon_svg()` (`renderers/svg_base.py:1159`). That includes
  fallback-icon substitution and recoloring, so it is the single place to capture
  assigned icons.
* **CSV.** `cli/exportdata.py::_events_to_csv_string()` writes the re-importable
  column set that `--embed` already reuses (`svg_base.py::_add_embedded_data`).
* **Holiday rows.** `event_listing.holiday_special_rows()`.
* **Output paths.** `cli/args.py::_to_output_dir_path()` is the traversal guard. The
  default stem is `<command><YYYYMMDDHHMM>` (`ecalendar.py` ~l.245).

## 3. Run folder

### 3.1 Layout

```
output/
  gantt202609141530/
    gantt202609141530.svg          ← main visualization
    gantt202609141530_p2.svg       ← continuation pages (gantt only)
    gantt202609141530.md           ← details document
    gantt202609141530.csv          ← event data included in the run
    icons/
      diamond-fill--1f77b4.svg     ← DB icon, recolored as drawn
      arrow-bar-right--000000.svg
      mark-swatch--1f77b4.svg      ← non-icon marks (swatch, flag, bar)
      mark-flag--d62728.svg
```

* **Folder name** = output stem. `--outputfile chart.svg` becomes
  `output/chart/chart.svg`. The default stays `<command><timestamp>`.
* **Scope.** All visualization commands: the 9 SVG views plus text-mini (which
  gets `.txt`, `.md` and `.csv`, and no `icons/`). The utilities (`excelblockplan`,
  `exportdata`, `*sheet`, list commands) keep writing flat files under `output/`.
* **Re-running into an existing folder.** Before writing, delete only the
  generator-owned artifacts: `<stem>.svg`, `<stem>_p*.svg`, `<stem>.md`,
  `<stem>.csv`, `<stem>.txt`, `icons/`. Anything else a user put there is left
  alone, and a shorter re-run leaves no stale pages.

### 3.2 Code

* **`shared/run_paths.py`**: a `RunPaths` dataclass built once in `run()`.
  * Fields: `dir`, `stem`, `main` (svg/txt), `page(n)`, `markdown`, `csv`,
    `icons_dir`, `icon(filename)`.
  * `prepare()` creates the folder and clears the owned artifacts.
* **`cli/args.py`**: `_to_output_dir_path` becomes `_to_run_paths(filename,
  extension)`. It keeps the basename-only guard and the empty-name `ConfigError`.
  The icon filename slug is also sanitized (`[a-z0-9-]`), so an icon name cannot
  escape `icons/`.
* **`config/config.py`**: add `run_paths: RunPaths | None`. `config.outputfile`
  stays, set to `run_paths.main`, so the renderers' `save_svg(config.outputfile)`
  calls are unchanged.
  * Gantt `_page_output_path` delegates to `run_paths.page(n)`.
  * `details_output_path` / `numbered_page_path` are deleted with the companions.
* **`visualizers/base.py`**: `VisualizationResult` gains `output_dir: str` and
  `files: list[str]`. `run()` prints the folder and logs the file list.

### 3.3 Consumers of the old flat layout (must be updated)

| Consumer | Change |
|---|---|
| `tools/generate_gallery.py` | glob `output/*/<stem>.svg`; contact sheet links into folders |
| `tools/refcorpus.sh` | `mv output/refcorpus_*/ "$dest"/`; `check` compares folder trees recursively |
| `slint_ui/ecalendar_app.py` (~l.221–300, 588) | preview lookup resolves `output/<stem>/<stem>.svg` |
| `slint_ui/verify_argv.py` (l.36–37) | same |
| `tui/` | any output preview/open path (audit during implementation) |
| `tests/test_ecalendar_cli.py` | output path assertions |

## 4. Shared column model

Move the gantt column model into **`renderers/table_columns.py`**:
`TableColumn` (with `GanttColumn` as an alias), `resolve_columns(entries, config)`,
`cell_value`, `cell_icon_visible`, `FIELD_ALIASES`, `resolve_field`.
`visualizers/gantt/columns.py` re-exports these (with `noqa: F401`) and keeps
`LINK_REF_FIELD` and `column_x_positions`.

**Every `events` DDL column resolves.**
* The table spellings (`name`, `start_date`, `end_date`) are handled by aliases.
* `id`, `user_id` and `import_id` become new optional `Event` fields
  (`db_id`, `user_id`, `import_id`). Verify the row keys
  `get_all_events_in_range()` returns first.
* A test parses `db utils/events.sql` + `EVENTS_SCHEMA_ADDITIONS` and fails on any
  column that does not resolve.

**Synthetic (render-derived) fields**, filled from the render record (§5):

| Field | Value |
|---|---|
| `icons` | **Every icon/mark assigned to the event, in draw order**: start icon, milestone icon or flag, rollup/deadline icon, event icon, continuation arrows. In Markdown each is an image link to its `icons/` file |
| `icon` | The primary assigned icon (first of `icons` that is a DB icon) |
| `marker` | The compactplan-key composite: color swatch or flag, then `icons`. The drop-in equivalent of the old key's mark column, available to every visualizer |
| `event_icon` | The raw `events.icon` value, as text |
| `assigned_color` | The fill actually drawn (swatch image + hex) |
| `color_source` | `event color` / `rule: <name>` / `group palette: <group>` / `wbs palette` / `default` |
| `category` | `event` / `milestone` / `duration` |
| `lane` | swimlane / timeline lane |
| `drawn` | `yes` / `partial` / `no` |
| `page` | chart page number |
| `ref` | gantt cross-page link-ref icons |
| `exceptions` | count of exception rows for the event |
| `continues_before`, `continues_after` | clipped at the range edge |
| `color_rank` | sort key: color assignment order (the compactplan key ordering, generalized) |

**Column keys in Markdown and CSV:**

| Key | Markdown | CSV |
|---|---|---|
| `field`, `header` | as-is | as-is |
| `align` | alignment row `:---` / `:---:` / `---:` | ignored |
| `format`, `date_format` | applied | applied |
| `render: icon`, `icon` | the icon image when the value is truthy (e.g. `milestone`) | icon name |
| `indent` | `&nbsp;&nbsp;` per WBS level | ignored |
| `max_lines` | `>1` keeps newlines as `<br>`; `1` collapses them | newlines kept (quoted) |
| `truncate` + optional `max_chars` | ellipsize | ignored |
| `width` | accepted, ignored (a gantt list pastes verbatim) | ignored |

## 5. Render record: `renderers/details_record.py`

Renderers write to this ledger while they draw. Nothing is re-derived afterwards.

```python
@dataclass(frozen=True)
class IconUse:
    icon: str  # resolved name, or "mark-swatch" / "mark-flag" / ...
    color: str | None
    # role: start | milestone | rollup | deadline | event | continuation_before |
    # continuation_after | holiday | day_number | overflow | symbol | ...
    role: str
    file: str  # icons/<slug>--<hex>.svg, assigned by the exporter


@dataclass
class EventNote:
    event: Event
    raw: dict
    icons: list[IconUse]
    assigned_color: str | None = None
    color_source: str | None = None
    category: str = "event"
    lane: str | None = None
    drawn: str = "yes"
    page: int | None = None
    refs: tuple[str, ...] = ()
    continues_before: bool = False
    continues_after: bool = False


@dataclass(frozen=True)
class DetailsException:
    visualizer: str
    kind: str
    task: str = ""
    datekey: str = ""
    start: str = ""
    end: str = ""
    ref: str = ""
    detail: str = ""


@dataclass
class DetailsRecord:
    visualizer: str
    events: list[EventNote]  # every event passed to the renderer
    colors: list[ColorEntry]  # color, label, source, rank
    symbols: list[SymbolEntry]  # IconUse + meaning
    unowned_icons: list[IconUse]  # day-number icons, overflow indicators, ...
    exceptions: list[DetailsException]
    visible_daykeys: list[str]
```

### 5.1 Capturing assigned icons

1. **One choke point.** `_draw_icon_svg()` records an `IconUse` every time it
   actually draws, using the name really drawn (the fallback name when the fallback
   was substituted) and the color really used. The role comes from the call's
   `css_class`: `ec-milestone-marker` → `milestone`, `ec-duration-marker` → `start`,
   `ec-continuation-icon` → `continuation_*`, `ec-legend-icon` → `holiday`, and so
   on. A small table in `details_record.py` holds the mapping, and unknown classes
   map to `icon`.
2. **Ownership.** `BaseSVGRenderer` gains context managers
   `with self._event_scope(evt):` and `with self._holiday_scope(daykey, name):`.
   Each renderer wraps its per-event and per-holiday draw calls in them. An icon
   drawn inside a scope attaches to that event's `EventNote.icons` (or the holiday
   row); outside any scope it goes to `unowned_icons`.
3. **Non-icon marks.** Marks drawn as geometry are recorded explicitly with
   `self._note_mark(kind, color, role)`: the compactplan bar swatch
   (`_draw_swatch`), the milestone pennant (`_draw_flag_marker`), gantt bars and
   diamonds, and the weekly duration bar color. The icon exporter renders these as
   `mark-*` SVGs, so the `marker` column reproduces the compactplan key's mark
   column for every visualizer.

Per-visualizer scope wrapping:

| Visualizer | Event scope wraps | Holiday scope wraps | Marks | Exceptions recorded |
|---|---|---|---|---|
| gantt | bar, milestone, rollup, deadline, link-ref marks per row | holiday band flags | bar swatch, milestone diamond | all 8 `GanttException` kinds, moved to `DetailsException` |
| weekly | event and duration drawing (event icons, duration icons) | day-box holiday titles/icons | duration bar color | `overflow` (from `OverflowEntry`) |
| mini, mini-icon, candybar | day-style event icons (`mini/day_styles.py`) | holiday/special-day icons | day fill color | `icon_dropped` (corner icons shed, `day_styles.py` ~l.69/683) |
| compactplan | `_draw_start_icon`, milestone icon/flag, continuation arrows | holiday icons on the axis | bar swatch, pennant flag | `name_truncated`, `date_omitted` (~l.1302) |
| timeline | callout icons, duration caps | holiday icons | duration bar | `label_unplaced` (~l.87), `lane_clipped` (~l.2391) |
| blockplan | item icons, milestone markers | holiday/nonworkday icons | lane/item fill | `unassigned_lane`, items not drawn |
| pit | callout icons | — | — | `multi_day_skipped` (log-only today, ~l.122) |
| text-mini | `DetailEntry.symbol` → `icons` (as text, no file) | — | — | — |

Color key sources: compactplan `assigned_colors`, `_wbs_group_colors`
(timeline/blockplan), `theme_resource_group_colors` / `Resource_Group_colors`
(weekly, mini), and the holiday colors (`theme_federal_holiday_color`,
`theme_company_holiday_color`). The compactplan symbols come from `_key_symbols()`,
refactored to return `SymbolEntry` values instead of `RowMark` callables.

## 6. Outputs written from the record

All three writers run at the end of `BaseSVGRenderer.render()`, after the main SVG
is saved. `TextMiniCalendarVisualizer` calls the Markdown and CSV writers directly.

### 6.1 Icon exporter: `renderers/icon_export.py`

* Dedupes `IconUse`s by `(icon, color)` across events, holidays, symbols and
  unowned icons, and writes `icons/<slug>--<hex>.svg`.
* **Uniform size.** Every file is exactly `details.icons.size` (default 16):
  `<svg width="16" height="16" viewBox="0 0 16 16">`. The glyph is scaled to fit,
  aspect preserved and centered.
* **Recoloring.** Factor the recolor + viewBox handling out of `_draw_icon_svg`
  into `colorize_icon_markup(markup, color)`, used by both drawing and export, so
  an exported icon is pixel-faithful to the chart.
* **`mark-*` files** are drawn with drawsvg at the same size: a swatch rect
  (bar-height proportions, centered), a pennant flag, and a bar with a continuation
  arrow.
* Writes only icons the main visualization drew.

### 6.2 Markdown writer: `renderers/markdown_details.py`

`build_markdown(record, config, run_paths) -> str` is pure.

1. `# {title_text}`, then metadata: visualizer, date range, theme, generated
   timestamp, command line, and a link to `<stem>.svg` and `<stem>.csv`.
2. `## Events`: `columns`, `sort` (gantt sort syntax + `color_rank`), optional
   `group_by` (`category` | `lane` | `resource_group` | `assigned_color` | `none`).
3. `## Color Key`: Swatch | Color | Assigned to | Source | Events.
4. `## Icons & Symbols`: Icon | Name | Role | Meaning | Used by (count). Covers every
   file in `icons/`.
5. `## Exceptions`: `exception_columns` over `visualizer`, `kind`, `issue`, `task`,
   `date`, `start`, `end`, `ref`, `detail`; `empty_exceptions_text` when empty.
6. `## Holidays & Special Days`: `holiday_columns` over the extended holiday row
   (§6.4), with `icon` rendered from its `icons/` file.

Icon cells use `![name](icons/<file>)`. The files are already the uniform size, so
no `width` attribute is needed and they render in GitHub, VS Code and Obsidian. In
`icon_mode: name` the cell is `` `name` ``; `none` leaves it empty. Cell escaping:
`|` becomes `\|`, and `<`, `>`, `&` are HTML-escaped.

### 6.3 CSV writer: `renderers/event_csv.py`

* **Rows.** Every event passed to the renderer after content filters (the same set
  `--embed` embeds), in Events-table order. `drawn` tells drawn events apart from
  considered-but-not-drawn ones.
* **`csv.columns: exportdata`** (default): the `_EXPORTDATA_COLUMNS` set via
  `_event_to_row`, so the file re-imports through `importers/import_events.py`.
* **`csv.render_columns: true`** (default) appends `assigned_color`, `color_source`,
  `icons` (`;`-joined names), `category`, `lane`, `drawn`, `page`, `exceptions`.
  **Verify that the importer ignores unknown columns.** If it does not, prefix these
  columns (e.g. `render_*`) and teach the importer to skip that prefix. Either way,
  a round-trip test covers it.
* **`csv.columns: [ ... ]`**: an explicit list in the shared column schema,
  formatted with `cell_value`; icon columns emit names.

### 6.4 Holiday rows

Move `holiday_special_rows()` from `renderers/event_listing.py` (deleted with the
companions) to `shared/holiday_listing.py`. Extend each row with:
* `start_date`, `end_date`, `country`, `nonworkday`;
* for special days: `company`, `language`, `fullday`, `starthour`, `endhour`, `tags`;
* `date` (the range label) and `icons` (`IconUse`s from the holiday scope).

Rows are built from `record.visible_daykeys`.

## 7. Theme and CLI

### 7.1 New theme category: `details:`

It sits in General Settings right after `overflow:`, because it applies to every
visualizer. It holds the Markdown, icon and CSV settings.

```yaml
details:
  markdown:
    enable: true
    title_text: Calendar Details
    sections: [events, colors, symbols, exceptions, holidays]
    events_section_text: Events
    colors_section_text: Color Key
    symbols_section_text: Icons & Symbols
    exceptions_section_text: Exceptions
    holidays_section_text: Holidays & Special Days
    empty_exceptions_text: Every item was drawn as scheduled.
    empty_cell_text: ''
    icon_mode: file          # file | name | none
    color_mode: swatch       # swatch | hex | name
    group_by: none
    sort: [start_date, end_date, name]
    # Same per-column keys as gantt.columns.
    columns:
      - { field: source_id,        header: ID,        align: right }
      - { field: marker,           header: Key,       align: center }
      - { field: name,             header: Task Name, indent: true }
      - { field: category,         header: Type }
      - { field: status,           header: Status }
      - { field: priority,         header: Pri,       align: right }
      - { field: wbs,              header: WBS }
      - { field: percent_complete, header: '%',       align: right, format: '{:.0%}' }
      - { field: start_date,       header: Start,     date_format: YYYY-MM-DD }
      - { field: end_date,         header: Finish,    date_format: YYYY-MM-DD }
      - { field: resource_names,   header: Resources }
      - { field: resource_group,   header: Group }
      - { field: assigned_color,   header: Color }
      - { field: notes,            header: Notes,     max_lines: 3 }
      - { field: drawn,            header: Drawn }
    exception_columns:
      - { field: issue,  header: Issue }
      - { field: task,   header: Task }
      - { field: date,   header: Date, date_format: YYYY-MM-DD }
      - { field: ref,    header: Ref }
      - { field: detail, header: Detail }
    holiday_columns:
      - { field: icons,      header: Icon, align: center }
      - { field: date,       header: Date }
      - { field: name,       header: Name }
      - { field: kind,       header: Kind }
      - { field: nonworkday, header: Non-work }
      - { field: notes,      header: Notes }
  icons:
    enable: true
    size: 16
  csv:
    enable: true
    columns: exportdata
    render_columns: true
```

Plumbing:
* `config/unified_theme.py`: add `details` to `VALID_SECTIONS`.
* `config/theme_engine.py`: `("details.markdown", k)`, `("details.icons", k)` and
  `("details.csv", k)` map to `details_md_*`, `details_icons_*` and `details_csv_*`.
* `config/config.py`: the fields, with the defaults above.
* `config/required_keys.py`: the new keys, `used_by` all visualizers.
* `basic.yaml`: example values.
* **Every bundled theme** (default, corporate, dark, vibrant, Julia, accent,
  minimal, TJX, SAMPLE) gets the section.
* **Strict validation.** An unknown `field` in any of the three column lists raises
  `ThemeError` listing the valid fields.

### 7.2 CLI

* **New.** `--details-md` / `--no-details-md`, `--icons` / `--no-icons`,
  `--csv` / `--no-csv`, through the enable/disable override pattern
  (`cli/config_assembly.py` ~l.141). They beat the theme, and are registered on
  every visualization command via one helper in `cli/args.py`. No short flags.
* **Removed.** `--mini-details` / `--no-mini-details`, and weekly `--overflow`
  (overflow is now always reported in the Markdown Exceptions). Regenerate the
  option catalog (`tools/generate_option_catalog.py`) consumed by the Slint UI and
  TUI.

## 8. Retiring the companion SVGs

This lands only after the superset guard (§9) is green.

**Code removed:**
* `renderers/details_page.py` (`DetailsPageWriter`, `DetailsColumn`,
  `details_output_path`, `numbered_page_path`).
* `visualizers/gantt/details.py`. `GanttException` and its `KIND_*` labels move into
  the shared exception registry in `renderers/details_record.py`.
* `renderers/event_listing.py`. Holiday rows move per §6.4; the rest goes.
* `svg_base.py`: `_OVERFLOW_COLUMNS`, `_render_overflow_svg`, the
  `include_overflow` branch.
* `mini/renderer.py`: `_render_details_svg`, the `_details_*` aliases,
  `_collect_holiday_special_rows` (visible daykeys now go to the record).
* `compactplan/renderer.py`: `_render_key_svg`, `_bar_mark`, `_milestone_mark`,
  `_holiday_mark`, `_key_column_width`, `_key_arrow_end`. `_key_color_ranks` /
  `_key_row_order` become the generic `color_rank`, and `_ChartKey` is replaced by
  the record.
* `gantt/renderer.py`: the `render_details_pages` call and `_details_page_count`.

**Config and theme keys removed:**
* `include_mini_details` and all `mini_details_*` fields (headers, column_widths,
  title, section texts, font colors/sizes, separator dasharray).
* `include_gantt_details`, `gantt_details_title_text`,
  `gantt_details_output_suffix`.
* `compactplan_key_*`, `compactplan_show_holiday_list`.
* `include_overflow`, `overflow_title_text`, `overflow_output_suffix`.
  `overflow.icon` / `overflow.color` stay, since they mark the chart itself.
* The `text:details_body` token and its `setfontsizes` entries
  (`config.py` ~l.2473–2722).

**Theme migration** (following the `excelheader` precedent):
* A theme still carrying `mini_details:`, `gantt.show_details`,
  `gantt.details_*`, `compact_plan.key_*`, or `overflow.title_text` /
  `output_suffix` raises `ThemeError` naming `details:`.
* `tools/migrate_theme.py` converts:
  * `mini_details.headers` + `column_widths` → `details.markdown.columns`, mapping
    the five default headers onto `start_date`, `name`, `milestone`, `priority`,
    `resource_group`;
  * the section texts → `details.markdown.*_section_text`;
  * `gantt.show_details` / `mini_details.enable` → `details.markdown.enable`.
* `ec-row-band`'s catalog description drops "every companion details page".

**Tests:**
* Delete `test_details_page.py`, `test_gantt_details.py`,
  `test_mini_details_page.py`, `test_weekly_overflow_page.py`.
* Retarget to Markdown/record assertions: `test_compactplan.py`,
  `test_gantt_marks.py`, `test_gantt_pagination.py`, `test_holiday_labels.py`,
  `test_theme_engine.py`, `test_timeline.py`, `test_week_numbers.py`,
  `test_ecalendar_cli.py`.

**Docs:**
* Update `USER_GUIDE.md`, `DefaultRendererValues.md` (regenerate via
  `tools/generate_default_renderer_values.py`), `architecture/render-pipeline.md`,
  `architecture/visualizers.md`, `changelog.md`.
* Leave `GanttImplementationPlan.md` and `archive/` as history.

## 9. Superset guard

The old pages are deleted, so their content has to be frozen **before** removal:

1. **Phase 3, before deletion.** Add a recording stub for `DetailsPageWriter`. Run
   each companion (gantt details, weekly overflow, mini, mini-icon and candybar
   details, compactplan key) over a fixture database, and dump every section, row
   cell, sub-line and mark to `tests/fixtures/details_superset/<view>.json`. Marks
   are recorded as their icon name + color, and swatch/flag kind + color.
2. **`tests/test_details_superset.py`** renders the same fixture and asserts:
   * every non-empty cell and sub-line value appears in the Markdown;
   * every recorded mark appears as an `icons/` file referenced from that event's
     or holiday's row. This is the check that assigned icons reach the Events
     table.

The frozen fixtures remain after the companions are gone, so the guarantee holds
from then on.

## 10. Phases

Each phase passes ruff + ty + pytest (pre-commit). Refcorpus keeps main SVGs
byte-identical: recording is side-effect free.

1. **Column model extraction** (§4). No output change.
2. **Run folder** (§3), including the gallery, refcorpus, Slint UI and TUI updates.
   The companion SVGs temporarily land inside the folder too.
3. **Record + icon capture + writers + theme + CLI additions** (§5–7), wired for
   gantt and weekly. Capture the superset fixtures (§9 step 1).
4. **Remaining visualizers**: mini, mini-icon, candybar, compactplan, timeline,
   blockplan, pit, text-mini, including the new exception kinds.
   `test_details_superset.py` goes green.
5. **Retire the companion SVGs** (§8): code, config, themes, `migrate_theme.py`,
   CLI flag removal, tests, option catalog.
6. **Docs + memory**.

## 11. Tests (in addition to §9)

* **Run folder.** Stem → folder mapping; traversal guard (`../x.svg`, `.`, empty);
  owned-artifact cleanup leaves foreign files; gantt `_p2` inside the folder;
  text-mini folder has no `icons/`.
* **Icons.**
  * Every exported file has identical `width`/`height`/`viewBox`.
  * `(icon, color)` dedupe; the fallback name is recorded when substituted.
  * A slug cannot escape `icons/`.
  * Every `icons/` file is referenced by the Markdown, and every reference exists.
* **Icon ownership.** Per visualizer, an event with a known icon has that `IconUse`
  in its `EventNote.icons` with the expected role (compactplan start icon +
  continuation arrows, gantt milestone, weekly event icon, mini day icon, timeline
  callout icon).
* **Columns.** Every events DDL column resolves; a gantt `columns:` list pastes
  into `details.markdown.columns`; unknown field raises `ThemeError`.
* **Markdown.** Escaping, alignment, indent, format/date_format, group_by, sort by
  `color_rank`, empty sections.
* **CSV.** Row set equals the renderer's event set; `exportdata` columns round-trip
  through the importer; render columns present or absent per setting; explicit
  column list formatting.
* **Themes / CLI.** All bundled themes validate; retired keys raise with a pointer;
  `migrate_theme.py` conversion; CLI enable/disable beats theme
  (`test_cli_theme_precedence.py`); removed flags are rejected.
* **Refcorpus.** Main SVGs byte-identical (modulo the path move). `.md`/`.csv`
  compared after stripping the generated timestamp line.

## 12. Decisions (defaults; revisit if wrong)

* **Theme category renamed to `details:`**, with `markdown` / `icons` / `csv`
  subsections, since it now governs three outputs rather than one.
* **All three outputs are on by default**, because the Markdown now replaces
  pages that were on by default.
* **The folder is not optional** for visualization commands. Utilities stay flat.
* **Re-running reuses the folder** and clears only generator-owned artifacts.
  Minute-resolution default stems can collide within the same minute, exactly as
  flat files do today.
* **Text-mini keeps its inline details section**: it is the text view itself, not
  a companion SVG. It also gains `.md`/`.csv`.
* **CSV defaults to the re-importable `exportdata` columns** plus render columns.
* **`--overflow` is removed** rather than kept as a no-op, following the
  `--ignorecomplete` / `--rollups` precedent.
