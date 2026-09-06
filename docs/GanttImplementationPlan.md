# Gantt Visualization — Implementation Plan

Derived from `gantt_chart_requirements.txt`, the answers to `GanttPlanQuestions.HTML`
(2026-08-07), and the existing codebase. Every answer is folded into the sections below;
§13 lists the residual assumptions.

---

## 1. Scope

A new `gantt` subcommand producing:

| Output | Contents |
|---|---|
| `<output>.svg` | Task table (left) + timescale chart (right), page 1 |
| `<output>_p2.svg`, `_p3.svg`, … | Vertical and/or horizontal continuation pages |
| `<output>_details.svg` | Companion details page — event listing **plus** the exception log |

Genuinely new machinery (confirmed by answer 36): the task-table column grid, dependency
parsing + arrow routing, progress lines, float bars, rollup brackets, and two-axis
pagination. Everything else is reused: timebands (`shared/timeband.py`), day
classification (`shared/day_classifier.py`), `RuleEngine` (`shared/rule_engine.py`),
today-line semantics (`visualizers/pit/renderer.py:1007`), content filters
(`visualizers/base.py:filter_events`), icon rendering (`visualizers/pit/markers.py`),
text/glyph rendering (`renderers/glyph_cache.py`, `renderers/text_utils.py`), page chrome
and paper/orientation (`renderers/svg_base.py`).

---

## 2. New and changed files

**New**

```
visualizers/gantt/__init__.py
visualizers/gantt/visualizer.py     # orchestration, factory registration
visualizers/gantt/layout.py         # column/row/timescale geometry + page planning
visualizers/gantt/renderer.py       # SVG drawing of one page
visualizers/gantt/columns.py        # column model: resolve, format, wrap/truncate
visualizers/gantt/rows.py           # row ordering (WBS-numeric) and indentation
visualizers/gantt/bars.py           # bar geometry on the visible-day axis
visualizers/gantt/dependencies.py   # link graph + curved-leader routing
visualizers/gantt/details.py        # gantt_details.svg (listing + exception log)
shared/predecessors.py              # MS Project dependency-string parser
importers/generators/gantt_generator.py   # test-data generator
tests/test_gantt_columns.py
tests/test_gantt_rows.py
tests/test_gantt_layout.py
tests/test_gantt_bars.py
tests/test_gantt_marks.py
tests/test_gantt_dependencies.py
tests/test_gantt_pagination.py
tests/test_gantt_render.py
tests/test_gantt_details.py
tests/test_predecessors_parser.py
```

**Changed**

```
shared/data_models.py            # Event gains the four float-date fields
config/config.py                 # gantt_* fields + text-token size table entries
config/theme_engine.py           # ("gantt", <key>) → gantt_* mappings, band + column sections
config/element_catalog.yaml      # 7 new ec-* bindings
config/themes/*.yaml (all 10)    # gantt: section; columns in default/SAMPLE
cli/args.py                      # gantt subcommand, added to _svg_views / _weekend_days_views / _includenotes_views
cli/config_assembly.py           # nothing new beyond standard wiring (answer 31)
visualizers/factory.py           # "gantt" → GanttVisualizer
docs/REQUIREMENTS.html, USER_GUIDE.md, ARCHITECTURE.md, changelog.md
```

---

## 3. Data layer

### 3.1 Dependency parsing — `shared/predecessors.py`

**Built in phase 1.** Shipped shape:

```python
@dataclass(frozen=True)
class Link:
    ref: str                    # source_id of the predecessor, as written
    type: str = "FS"            # "FS" | "SS" | "FF" | "SF", upper-cased
    lag_days: float = 0.0       # signed; 0.0 when absent or unparseable
    lag_percent: float | None = None   # "+50%" lags
    lag_elapsed: bool = False   # MS Project elapsed units, "+3ed"
    lag_text: str | None = None # as written, kept for reporting
```

- `parse_links(text) -> list[Link]` for the common case;
  `parse_links_with_rejects(text) -> tuple[list[Link], list[str]]` for the details page.
- Grammar per token: `<ref>[FS|SS|FF|SF][±<lag>]`. A bare numeric token is a `source_id`
  with type `FS`, lag `0` (answer 2). Lag magnitudes go through
  `shared/duration_parser.parse_duration`, so working-calendar semantics are shared.
- A token with no readable reference is dropped and reported. A token whose *lag* is
  unparseable keeps its link with zero lag and is still reported — the dependency is the
  primary information, lag is advisory.
- Resolution key is `events.source_id`, never `events.id` (answer 2, matching
  `importers/import_events.py:108`). Rows with a null/blank `source_id` can be link
  targets only by exact string match of what the PM tool wrote; they are otherwise
  unlinkable and get an exception-log line.
- Three documented ambiguities, each pinned by a test: `,` is always a list separator (so
  a decimal-comma lag splits); a type suffix is believed only at end-of-token or before a
  sign, and only after an alphanumeric (keeping hex GUIDs intact); an untyped reference
  ending in a signed number splits into ref + lag.

### 3.2 Degradation when data is absent (answer 1)

Each feature is independently gated on the data actually present — no configuration
needed, and no errors:

| Missing | Effect |
|---|---|
| `predecessors` / `successors` empty | No arrows drawn |
| `wbs` empty | No indentation, row sorts into the post-WBS block |
| `earliest_*` / `latest_*` empty | No float bars (answer 24) |
| `rollup` start/end empty | No bracket (answer 20) |
| `percent_complete` null | No progress line |

The current `calendar.db` has none of this data (105 rows: 0 predecessors, 0 WBS, 0
float dates), so a working chart against today's DB is the *degenerate* case and must
be part of the test matrix.

### 3.3 Test data — `importers/generators/gantt_generator.py`

Follows the existing generator contract (`import_events.py --generate`, Title_Case
DataFrame columns). Emits a ~40-row project exercising every code path:

- 3-level WBS hierarchy (`1`, `1.1`, `1.1.1`, …) with real rollup rows and deliberate
  numeric-vs-lexical ordering traps (`1.9` before `1.10`).
- `source_id` values, and predecessor strings covering all four link types, positive and
  negative lag, multi-predecessor lists, one forward reference, one **backward** link
  (successor starting before its predecessor ends), and one reference to a row that the
  default filters exclude (drives the off-chart stub, answer 27).
- `percent_complete` at 0 / 0.5 / 1.0, milestones (`end_date` anchored), deadlines,
  float dates on a subset only, notes long enough to force truncation, tasks that start
  before `--start` and end after `--end`, and a single-day event landing on a Saturday
  (drives the snap-forward icon, answer 22).

Loaded via:

```bash
uv run python importers/import_events.py --generate importers/generators/gantt_generator.py
```

Tests build this dataset in-memory rather than depending on `calendar.db` state.

---

## 4. Configuration

### 4.1 `config/config.py` — new fields (abridged)

```python
# ── Gantt: table ──────────────────────────────────────────────────────────
gantt_columns: list[dict[str, Any]]        # see §4.2; default = the 16-column set
gantt_table_width_ratio: float = 0.38      # table share of content width
gantt_row_height: float = 14.0             # fixed and uniform (answer 9)
gantt_header_row_height: float = 18.0
gantt_indent_per_level: float = 8.0
gantt_sort: list[str] = ["wbs", "start_date"]

# ── Gantt: timescale ──────────────────────────────────────────────────────
gantt_top_time_bands: list[dict[str, Any]]     # blockplan band schema (answer 17)
gantt_bottom_time_bands: list[dict[str, Any]]  # defaults to a copy of the top bands
gantt_band_row_height: float = 10.0

# ── Gantt: marks ──────────────────────────────────────────────────────────
gantt_milestone_icon: str = "diamond-fill"
gantt_deadline_icon: str = "square-fill"          # answer 21
gantt_rollup_icon: str = "check"                  # answer 4
gantt_milestone_flag_icon: str = "check"          # answer 4 (milestone column)
gantt_snapped_event_icon: str = "arrow-left-circle"   # answer 22
gantt_offchart_dep_icon: str = "crosssquare"          # answer 27
gantt_continuation_icon: str = "arrow-bar-right"      # answer 16 (mirrored at the left edge)
gantt_progress_color: str = "black"
gantt_float_opacity_scale: float = 0.4

# ── Gantt: today line (mirrors PIT, answer 32) ────────────────────────────
gantt_show_today_line: bool = True
gantt_today_date: str | None = None        # YYYYMMDD override, else wall clock

# ── Gantt: details page ───────────────────────────────────────────────────
include_gantt_details: bool = True
gantt_details_output_suffix: str = "_details"
gantt_details_title_text: str = "Gantt Details"
```

All four named icons (`check`, `square-fill`, `arrow-left-circle`, `crosssquare`) are
confirmed present in the `icon` table (8 284 rows).

`gantt_bottom_time_bands` stays `None` until a theme declares `gantt.bottom_bands`;
`CalendarConfig.get_gantt_bottom_bands()` deep-copies the top bands when it is unset
(answer 17). The mirror is resolved on read, **not** in `__post_init__` — construction
happens before the theme applies, so mirroring there would copy the dataclass defaults
and silently ignore a theme's own `top_bands`.

### 4.2 Theme section — `gantt:` with a dedicated `gantt.columns:` (answer 29)

Column definitions are layout configuration, not `style_rules` styling — they get their
own section, exactly as `blockplan.swimlanes` does:

```yaml
gantt:
  table_width_ratio: 0.38
  row_height: 14.0
  indent_per_level: 8.0
  sort: [wbs, start_date]
  milestone_icon: diamond-fill
  deadline_icon: square-fill
  columns:
    - field: source_id
      header: ID
      width: 0.06
      align: right
    - field: name
      header: Task Name
      width: 0.30
      align: left
      max_lines: 2          # answer 9 — truncate with ellipsis past this
      indent: true          # WBS-driven indentation applies to this column
    - field: status        { width: 0.07 }
    - field: priority      { width: 0.05, align: right }
    - field: wbs           { width: 0.07 }
    - field: rollup        { width: 0.05, render: icon, icon: check }
    - field: milestone     { width: 0.05, render: icon, icon: check }
    - field: percent_complete { width: 0.06, align: right, format: "{:.0%}" }
    - field: effort_text   { header: Effort,   width: 0.07 }   # answer 3
    - field: duration_text { header: Duration, width: 0.07 }   # answer 3
    - field: start_date    { width: 0.09, date_format: "dd MM/DD/YY" }
    - field: end_date      { width: 0.09, date_format: "dd MM/DD/YY" }
    - field: resource_names { width: 0.12, max_lines: 1 }
    - field: resource_group { width: 0.10 }
    - field: notes          { width: 0.16, max_lines: 2 }
    - field: deadline       { width: 0.09, date_format: "dd MM/DD/YY" }
```

Per-column keys: `field`, `header`, `width` (fraction of the table width, renormalized),
`align` (`left|center|right`), `max_lines`, `wrap` (bool), `truncate` (bool, default
true), `render` (`text|icon`), `icon`, `format`, `date_format`, `indent`.

`date_format` goes through the existing `shared/date_utils.format_arrow_date`, which
already implements the `dd` two-letter-weekday extension (answer 30) — confirmed by
`tests/test_date_format.py:22`. No new date code.

Every active theme YAML gets a `gantt:` section (answer 35). There are **10**, not the
19 the first draft of this plan counted — the rest of `config/themes/` is `.yaml.bak`
files. `default.yaml` and `SAMPLE.yaml` carry the full annotated set including
`columns:`; the other eight carry the required geometry plus the visual knobs a theme is
likely to differ on (`dark.yaml` needs `progress_color: whitesmoke` — black is invisible
on its background).

`gantt` joined `config/required_keys.py::VISUALIZERS` in phase 8, with four required
keys: `table_width_ratio`, `row_height`, `header_row_height`, `band_row_height`.
`columns` is deliberately **not** required — `CalendarConfig` carries a complete default,
so requiring it would duplicate sixteen lines into every theme file for no gain.

Two section registries must both learn the name or every theme load warns and the
`UnifiedTheme` parse fails: `config/theme_engine.py::VALID_SECTIONS` and
`config/unified_theme.py::VALID_SECTIONS`.

### 4.3 `config/theme_engine.py`

- `("gantt", "<key>") → "gantt_<key>"` entries in the scalar map.
- Band sections registered alongside the existing ones near line 1143:
  `("gantt", "top_bands", "gantt_top_time_bands")`,
  `("gantt", "bottom_bands", "gantt_bottom_time_bands")`.
- `columns` handled as a list-of-dicts section (same treatment as
  `blockplan.swimlanes`), not flattened.

### 4.4 `config/element_catalog.yaml` — accepted additions (answer 34)

```yaml
ec-column-header:     { kind: text, token: label,     scope: [gantt], description: "Task-table column header" }
ec-task-cell:         { kind: text, token: body,      scope: [gantt], description: "Task-table cell text" }
ec-row-band:          { kind: box,  token: cell,      scope: [gantt], description: "Alternating task-row band" }
ec-progress-line:     { kind: line, token: axis,      scope: [gantt], description: "Percent-complete line on a duration bar" }
ec-dependency-arrow:  { kind: line, token: grid,      scope: [gantt], description: "Dependency arrow" }
ec-float-bar:         { kind: box,  token: duration,  scope: [gantt], description: "Earliest/latest float span" }
ec-rollup-bracket:    { kind: line, token: axis,      scope: [gantt], description: "Rollup summary bracket" }
```

Existing classes are reused for everything else (`ec-duration-bar`, `ec-event-icon`,
`ec-milestone-marker`, `ec-band-cell`, `ec-grid-line`, `ec-today-line`,
`ec-continuation-icon`, `ec-background`, `ec-separator`). `scope: [gantt]` must also be
added to those shared entries where the scope list is explicit rather than `[all]`.
`tests/test_element_catalog.py` enforces that every `ec-*` literal in the new renderer
appears here.

### 4.5 `style_rules`

Bars, events and milestones are styled through the existing
`RuleEngine.evaluate_event` (`apply_to: box:duration` / `box:event`). Dependency arrows
use `apply_to: line:dependency_arrow`, evaluated against the **successor** task's fields
via the new `RuleEngine.evaluate_target(target, event)` — a small generalization that
`evaluate_event` now delegates to.

Targets must be spelled `<kind>:<name>`: `config/unified_theme.py` accepts only that form
plus `element` and `lane`, and an unrecognized target makes the entire theme fail to parse
— silently emptying `ThemeStyles` — so an invented name like `gantt_arrow` is not an
option. Selection criteria are the existing event-field matchers
(`_matches_event_fields`); no new match vocabulary. Arrows are drawn whenever link data
resolves; `style_rules` govern only their appearance (answer 28).

Four of the new `ec-*` classes — `ec-progress-line`, `ec-float-bar`,
`ec-rollup-bracket`, `ec-dependency-arrow` — are registered in
`renderers/css_generator.py::_INLINE_STYLED_CLASSES`. Their colors vary per item, and CSS
beats presentation attributes in the cascade, so without this the generated class rule
silently overrides the renderer: that is what turned the documented-black progress line
grey and pinned float bars to a fixed opacity.

---

## 5. CLI

New `gantt` subcommand in `cli/args.py`, registered into `_svg_views`,
`_weekend_days_views`, and `_includenotes_views`. Standard flag set only (answer 31):
paper/orientation, theme, header/footer, watermark, date range, weekends, and the full
Content Filtering group (`--noevents`, `--nodurations`, `--ignorecomplete`,
`--milestones`, `--rollups`, `--WBS`, `--status`, `--country`, `--empty`). No
gantt-specific flags, so no `_CLI_CONFIG_OVERRIDES` additions are required. Registered in
`visualizers/factory.py` as `"gantt"`.

---

## 6. Layout — `visualizers/gantt/layout.py`

### 6.1 Row model

1. Filter events via the shared `filter_events` (no bypass, so `--WBS`/`--status`/etc.
   behave identically to every other view).
2. Sort: WBS **segment-wise numerically** — each segment parsed as int where possible,
   falling back to a case-folded string, so `1.9 < 1.10`. Rows with empty WBS sort into a
   second block after all WBS rows, ordered by `start_date` (answer 7).
3. Indent level = WBS segment count − 1; empty WBS ⇒ level 0 (answer 8).
4. No synthesized parent rows — only imported rows are drawn (answer 6).
5. Row height fixed and uniform (answer 9); overflow within a cell is truncated with an
   ellipsis at `max_lines`, measured with the existing PIL-backed text measurement.

### 6.2 Time axis

- Extent is the `--start`/`--end` calendar range, as in every other view (answer 15).
- `weekend_style == 0`: non-working columns are **removed entirely** — the axis is a list
  of visible days, so all x-geometry is column-index based, never linear date
  interpolation. `weekend_style != 0`: all days are columns and non-working days are
  shaded behind the bars (answer 13). Reuses `blockplan`'s `_visible_days` approach and
  `shared/day_classifier.py` for holiday/weekend classification.
- Bands built with `shared.timeband.build_segments` from `gantt_top_time_bands` /
  `gantt_bottom_time_bands` (answer 17).

### 6.3 Pagination (answers 10–12)

`plan_pages()` returns a grid of `(row_slice, day_slice)` pages:

- **Vertical**: rows split by available body height; every page repeats the column
  headers and the full timescale bands.
- **Horizontal**: visible days split by available chart width; every page repeats the
  task-table columns, and the timescale **continues** from the previous page.
  `_build_all_segments` calls `build_segments` once over the whole range and pages slice
  the result, so interval counters carry over — verified as `W48 → W49` across a break
  rather than restarting at `W1`. The split triggers when a day column would fall below
  `gantt_min_day_width` (default 4.0pt; `0` disables horizontal pagination entirely).
- Page order: row-major (all horizontal pages for row block 1, then row block 2).
- Filenames: `<output>.svg`, then `_p2`, `_p3`, … — unpadded, per answer 12. Note this
  deliberately differs from `visualizers/sheets.py`, which zero-pads (`_p03`).
- Continuation pages are written during `_render_content`, each into its own drawing with
  the same chrome (the pattern `mini`'s details page already uses); page 1 stays in the
  drawing the base class saves. `GanttRenderer.render()` adds the extras to
  `VisualizationResult.page_count`.

---

## 7. Renderer — `visualizers/gantt/renderer.py`

Draw order (back to front), per page:

1. Background, non-working-day shading, grid lines, row bands.
2. Top/bottom timescale bands; task-table column headers.
3. Task-table cells (text or icon per column config; `check` default for `rollup` and
   `milestone`, answer 4).
4. Today line — `gantt_show_today_line` / `gantt_today_date`, identical semantics to PIT
   (`YYYYMMDD` override else wall clock, suppressed when outside the range, answer 32).
5. Float bars: `earliest_start→start`, `start→latest_start`, `earliest_end→end`,
   `end→latest_end`, drawn as the bar color at reduced opacity; skipped entirely when the
   fields are empty (answer 24).
6. Duration bars; single-day events as one-day-wide rectangles (or a style-rule icon).
7. Progress line on each bar — length is the `percent_complete` fraction of the
   **working-day** span (answer 18), so it lines up with the drawn bar when weekends are
   hidden; full width at 100 %. Default black.
8. Rollup brackets — downward-facing brackets spanning the rollup row's own
   `start_date`/`end_date`, suppressed when either is empty. No progress line, no float
   bars (answers 19, 20).
9. Milestone icons anchored on `end_date` (answer 23); deadline icons (`square-fill`,
   answer 21).
10. Dependency arrows, last so they sit above the bars.

**Edge cases, each also logged to the details page:**

| Case | Rendering |
|---|---|
| Bar extends past `--end` | Continuation icon inside the bar's **right** edge (answer 16) |
| Bar starts before `--start` | Continuation icon inside the bar's **left** edge (answer 16) |
| Single-day event on a hidden weekend | Drawn on the next working day with `arrow-left-circle` (answer 22). A *multi-day* span with no visible day at all cannot be placed sensibly, so it is reported (`KIND_UNDRAWN`) rather than moved. |
| Holiday hidden because it falls on a hidden weekend | Nothing drawn (answer 14) |
| Predecessor not on the visible chart | Stub arrow terminating in a `crosssquare` icon (answer 27) |

### 7.1 Dependency arrows — `visualizers/gantt/dependencies.py`

- Build `source_id → row` index; resolve each `Link`; drop and log unresolved refs.
- **Type-correct edge anchoring** (answer 25 as amended 2026-08-07). Each arrow leaves and
  enters the edge its link type implies, at the vertical center of the bar or icon:

  | Type | Exits predecessor | Enters successor |
  |---|---|---|
  | FS | right edge | left edge |
  | SS | left edge | left edge |
  | FF | right edge | right edge |
  | SF | right edge | left edge, approached from the right |

  Rationale: the fixture's 36 links include 16 where the successor starts before the
  predecessor ends, and nearly all of those are `SS`/`FF` links behaving exactly as
  defined. Forcing them to FS geometry would render correct schedules as backward
  doglegs. Lag is still **not** applied to geometry — an `SS+3d` arrow anchors at both
  left edges without the 3-day offset — so the parsed `lag_days`/`lag_percent` remain
  unused in v1 as originally planned.
- Routing stays uniform regardless of type. **Revised 2026-08-08** to the PIT leader
  construction: a perpendicular stub off the exit edge, a `hCurveBetween` cubic across
  the gap (control points on the horizontal midline, so the curve leaves and arrives
  tangentially), and a matching stub into the entry edge. The arrowhead is an SVG
  `<marker>` with `orient="auto"`, so it follows the tangent instead of being fixed
  left or right. A backward link is the same construction; the curve doubles back. No
  collision avoidance — overlaps are accepted. This supersedes the original orthogonal
  three-segment dogleg (requirement §58, answer 26).
- Arrows whose predecessor row is off the current *page* but on the chart are clipped at
  the page boundary; arrows whose predecessor is off the *chart* get the stub + icon.

---

## 8. `gantt_details.svg` — `visualizers/gantt/details.py`

Follows the format of the existing details page (`visualizers/mini/renderer.py:870`
`_render_details_svg`): its own drawing, same page chrome (watermark, decorations,
header/footer), title, column table, written to
`<output><gantt_details_output_suffix>.svg`.

Two sections:

1. **Task listing** — the rendered rows in chart order, using the same column model.
2. **Exception log** — one line per item the chart could not show faithfully, each with
   the task name, date, and reason:
   - holidays hidden because they fall on a hidden weekend (answer 14);
   - duration bars clipped at `--start` or `--end` (answer 16);
   - single-day events snapped forward off a hidden weekend (answer 22);
   - dependencies pointing off-chart (answer 27);
   - unparseable predecessor tokens and unresolvable `source_id` references (§3.1).

Exceptions are accumulated during layout/render into a typed
`GanttException(kind, task, datekey, detail)` list carried on the renderer, so the
details page never re-derives geometry. Enabled by `include_gantt_details` (default on).

Two details specific to this page:

- It **paginates** rather than truncating (`_details_p2.svg`, …). The other details pages
  in the codebase stop at the page bottom; here the log is the whole point, so an entry
  that does not fit continues rather than disappearing. `DetailsPageWriter` flows content
  down the page and replays the current section's heading after each break.
- Column widths are reused from the chart's table for proportion but floored at 4% and
  renormalized: a column that only ever holds a glyph on the chart (`rollup`, `milestone`
  at 2%) has to hold the word "Yes" here.

`GanttRenderer` counts chart continuation pages and details pages separately
(`_extra_page_count`, `_details_page_count`); `render()` adds both, so
`VisualizationResult.page_count` equals the number of files written.

---

## 9. Tests

| File | Covers |
|---|---|
| `test_predecessors_parser.py` | All four link types, lag signs/units, bare numerics, multi-token, malformed input |
| `test_gantt_columns.py` | Column resolution, width renormalization, alignment, wrap/truncate at `max_lines`, `dd` date formatting, icon columns |
| `test_gantt_layout.py` | Numeric WBS sort (`1.9` < `1.10`), empty-WBS block placement, indent depth, weekend removal vs shading, band continuity |
| `test_gantt_dependencies.py` | Resolution by `source_id`, per-type edge anchoring (FS/SS/FF/SF), forward/backward routing geometry, off-chart stubs |
| `test_gantt_pagination.py` | Row and day splitting, header/timescale repetition, band index continuity, `_p2`/`_p3` naming |
| `test_gantt_render.py` | Bar/progress/float/bracket/milestone/deadline geometry, continuation icons, snapped events, today line, degenerate dataset (no WBS/predecessors/floats), details-page exception log |

Extended: `test_element_catalog.py` (new `ec-*`), `test_required_keys.py` and
`test_validate_theme.py` (the `gantt:` section in all 19 themes),
`test_ecalendar_cli.py` (subcommand registration and flag set).

Run with `uv run python -m pytest tests/ -v`.

---

## 10. Delivery phases

| Phase | Content | Verifiable at end |
|---|---|---|
| 1 ✅ | `shared/predecessors.py`, `gantt_generator.py`, parser tests | **Done 2026-08-07** — 46-task fixture transforms 46/46, 36 links across all four types, 38 parser tests |
| 2 ✅ | Config fields, `gantt:` + `gantt.columns:` in `default.yaml`, theme-engine wiring, element-catalog entries, CLI + factory registration | **Done 2026-08-07** — `gantt` renders the page frame against default/basic/SAMPLE; 20 config tests |
| 3 ✅ | Layout: rows, sort, indent, columns, time axis, weekend handling | **Done 2026-08-07** — table, bands, shading and cells render; 51 tests across columns/rows/layout/render |
| 4 ✅ | Bars, single-day events, milestones, deadlines, progress lines, float bars, rollup brackets, today line, continuation icons | **Done 2026-08-07** — full chart renders; 62 tests over geometry + marks |
| 5 ✅ | Dependency arrows: per-type edge anchoring, backward doglegs, off-chart stubs | **Done 2026-08-07** — arrows on the generated dataset; 28 tests |
| 6 ✅ | Two-axis pagination and `_pN` output | **Done 2026-08-07** — vertical and horizontal splits, continuous timescale; 21 tests |
| 7 ✅ | `gantt_details.svg` with the exception log | **Done 2026-08-07** — listing + log, paginating; 19 tests |
| 8 ✅ | `gantt:` sections in the remaining themes; `gantt` joins `required_keys.VISUALIZERS`; docs | **Done 2026-08-07** — 9 themes updated (not 18: the rest are `.yaml.bak`), all render; docs updated; suite green |

Phases 1–2 and 3–4 are the natural review checkpoints; 5 and 6 are independent and can be
reordered.

---

## 11. Reuse checklist (answer 36)

| Need | Existing code |
|---|---|
| Time bands | `shared/timeband.py::build_segments`, blockplan band dicts |
| Weekend/holiday classification | `shared/day_classifier.py`, blockplan `_visible_days` |
| Content filtering | `visualizers/base.py::filter_events` |
| WBS filter expressions | `shared/wbs_filter.py` |
| Style rules | `shared/rule_engine.py::RuleEngine.evaluate_event` |
| Today line | `visualizers/pit/renderer.py::_draw_today_line` |
| Icon draw from DB | `visualizers/pit/markers.py` |
| Date formatting incl. `dd` | `shared/date_utils.py::format_arrow_date` |
| Text measure / wrap | `renderers/text_utils.py`, `renderers/glyph_cache.py` |
| Page chrome, paper, watermark, `<desc>` | `renderers/svg_base.py` |
| Details-page pattern | `visualizers/mini/renderer.py::_render_details_svg` |
| Pagination precedent | `visualizers/sheets.py` (note: different suffix padding) |

---

## 12. Risks

1. **Arrow legibility.** Without collision avoidance (answer 26), dense projects will
   produce crossing doglegs. Mitigation: arrows are style-rule driven and can be styled
   thin/dashed; routing quality is a defined follow-up. Per-type edge anchoring (§7.1)
   removes the largest single source of visual noise — `SS`/`FF` links no longer render
   as spurious backward routes.
2. **Horizontal pagination + dependency arrows.** A link whose endpoints land on
   different horizontal pages can only be shown as a clipped stub on each. Handled as the
   off-page case; flagged in the details log.
3. **Column width budget.** Sixteen default columns at a 0.38 table ratio leaves ~2–3 mm
   per narrow column on Letter portrait. The default set is legible on landscape/wide
   paper; portrait users will need to trim `gantt.columns` in their theme.
4. **`source_id` integrity.** Link resolution assumes `source_id` is populated and stable
   across imports. Imports without it silently yield an arrow-free chart plus a details
   log full of unresolved references — which is the intended degradation, but worth
   calling out in the user guide.

---

## 13. Assumptions carried forward

- `diamond-fill` is the default milestone icon (the requirements say "filled diamond");
  verified present in the `icon` table, as are `check`, `square-fill`,
  `arrow-left-circle`, `crosssquare`, and `arrow-bar-right`.
- `arrow-bar-right` is the default continuation icon, mirrored for the left edge; answer
  16 specifies placement but not the glyph.
- Alternating row banding is on by default and themeable (`ec-row-band`); not specified
  either way.
- The details page is on by default (`include_gantt_details = True`), matching
  `include_mini_details`.
- Lag values are parsed and stored but do not shift arrow geometry in v1. Link *type* does
  drive geometry, through edge anchoring only (§7.1) — so an `SS+3d` arrow anchors
  correctly at both left edges but is not offset by three days.

---

## 14. Cross-page dependency references (design, 2026-08-08)

Answers folded in 2026-08-08. **Built 2026-08-08** — 26 tests in
`tests/test_gantt_crosspage.py`, plus the prerequisite fix below.

### The problem

Every undrawable link gets the same anonymous `crosssquare` stub today. A reader learns
*that* a dependency exists but not **which** task it points at, and there is nothing on
the other page to connect the stub to. With two-axis pagination a link's two ends are
routinely on different pages, so this is the common case, not the edge.

### The change

Each event with off-page successors gets **one number**, drawn as a numbered icon at
both ends of the break:

* On the page holding the **event**: one stub arrow leaves its bar and terminates in the
  numbered icon — regardless of how many successors it could not reach (answer 3).
* On the page holding each unreachable **successor**: the same numbered icon appears in a
  new left-most task-table column, on that successor's own row (answer 2).

So the number identifies the *source event*, and every successor it could not reach
carries that number. The reader sees ⑦ at the end of a stub on page 1 and finds ⑦ in the
reference column beside each of the tasks it feeds on page 3.

Numbers are assigned only to links that could not be drawn (answer 4). A link whose ends
share a page is drawn as an ordinary arrow and carries no number.

### Prerequisite fix (defect, phase 6)

`_draw_page` passes the page's row slice to `_draw_dependencies`, so
`resolve_dependencies` builds its `source_id` index from **that page only**. A
predecessor on another page therefore resolves to "no task carries source_id 'X'" — it
reports the task as missing when it plainly exists, and `KIND_OFFCHART_DEPENDENCY` is
unreachable in practice. Reproduced with 12 tasks over 2 pages:

```
→ unresolved_predecessor | t11 | no task carries source_id '0'
```

The fix is to pass all rows and keep the drawn set as the page's anchors — what
`resolve_dependencies` was built for. Without it there is no far-end row to number.

### Numbering

* Assigned **once per chart**, before any page renders, so a number means the same thing
  in every file.
* One number per **source event**, not per link (answer 3): an event with three
  unreachable successors gets one number, one stub, and stamps that number on all three
  successor rows.
* Order: by the source event's row index — ascending in reading order.
* Icon families run in sequence as numbers are exhausted (answer 1):
  `circle-1…100`, then `darkcircle-1…100`, then `square-1…100` — 300 references before
  any degradation. Past 300 the stub falls back to the unnumbered `crosssquare` and the
  exhaustion is recorded once in the exception log.
* Name resolution is padding-tolerant: `circle-7` and `square-7` exist unpadded, while
  `darkcircle` zero-pads its single digits (`darkcircle-07`). The resolver tries
  `<prefix><n>` then `<prefix><n:02d>`, so a theme can name any family without the
  renderer knowing its convention.

### Links with no far end

A reference matching no task, or an unparseable token, has no successor row to stamp, so
it keeps today's behavior: an unnumbered `crosssquare` stub on the row that named it.
The rule a reader can rely on stays clean — **numbered ⇒ the other end is somewhere in
this document; unnumbered ⇒ it is not.**

### The reference column

* Synthetic field `link_ref` — computed, not an `events` column, so the column model must
  accept a value the renderer supplies rather than reading it off `Event`.
* Default: first column, before `source_id`; `render: icon`, centered, width `0.03`
  (the rest renormalize around it).
* Theme-configurable like every other column — movable, renamable, removable.
* One row can be the far end of links from several source events, so a cell may hold more
  than one icon. Up to `gantt.link_ref_max_icons` (default 2) are drawn side by side; the
  details page always lists every reference, so nothing is lost to column width.
* Populated only on pages where that row is drawn — which is the point: the icon and its
  stub live in different files.

### Details page

The exception log gains a **Ref** column so ⑦ resolves to named tasks without
page-flipping. Unnumbered entries show an em dash.

### Configuration

| Key | Default | Purpose |
|---|---|---|
| `gantt.link_ref_icon_families` | `[circle-, darkcircle-, square-]` | Numbered-icon families, used in order |
| `gantt.link_ref_family_size` | `100` | Numbers available per family |
| `gantt.link_ref_max_icons` | `2` | Icons drawn in one reference cell |
| `gantt.offchart_dep_icon` | `crosssquare` | Unchanged; now the *unnumbered* fallback |

### Files touched

`dependencies.py` (grouping + numbering; `Dependency` gains `ref_number`),
`renderer.py` (pass all rows, numbered stub per source event, per-row reference markers,
draw the new column), `columns.py` (synthetic column values), `details.py` (Ref column),
`config/config.py`, `config/theme_engine.py`, `config/themes/default.yaml` +
`SAMPLE.yaml`, and tests.
