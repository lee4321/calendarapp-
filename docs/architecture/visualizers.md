# Visualizers

Every SVG visualizer is a package under `visualizers/<name>/` with
`layout.py` (geometry → CoordinateDict, PDF coords) and `renderer.py`
(a `BaseSVGRenderer` subclass overriding `_render_content`). The table in
`visualizers/factory.py` pairs each view name with its layout and renderer;
`BaseVisualizer` runs filter → layout → render. Only views that change that
workflow have a `visualizer.py`: mini (month-boundary dates and week numbers,
shared with mini-icon), candybar (week-boundary dates) and text-mini (text
output). Views with a single content rectangle use `ContentAreaLayout`.
Class-inheritance exceptions are noted below.

## weekly — the flagship calendar

Grid of day boxes, one column per weekday (weekend style 0–4 drives which
columns exist and whether weekend boxes are half-width). Events render as
text lines inside their day box; multi-day durations as bars spanning
boxes; what doesn't fit is marked on its day and reported in the run's
details document. Day
decoration (fills, hash lines, DB pattern tiles, holiday titles, fiscal
period labels) resolves per day through StyleEngine content rules +
`box:cell`/`line:hash` tokens.

## mini — compact month grids

Months in a column/row arrangement (`--mini-columns/rows`). Day styling is
centralized in `day_styles.DayStyleResolver` → a `DayStyle` record per
cell (shade, circle, strikethrough, icon, pattern). Rendering is
three-pass per cell — background, duration bars, foreground — so bars sit
under day numbers. Corner icons past the fourth are reported as
exceptions in the run's details document.

## mini-icon — mini with glyph day numbers

Extends the mini family; day numbers render as icon glyphs from a named
set (`--mini-icon-set`, e.g. `squircles` — the `klee/` SVG collection
loaded into the DB icon table).

## candybar — vertical year strip

`CandybarRenderer(MiniCalendarRenderer)`: one row per ISO week, month
names in merged boxes on the side (rotatable), optional weekend
suppression. Reuses the entire mini decoration engine (day styles, tokens
under the `mini` visualizer ctx).

## text-mini — plain-text month grid

Text output (`.txt`), no theme/styling; geometry and symbols only. The
only visualizer with zero styling reads.

## timeline — labella callouts on a time axis

Continuous date axis (horizontal or vertical, `--orientation` +
`--label-side`). Point events become callouts placed by the shared
labella engine (`shared/labella_layout.py` — Force/VPSC label
de-collision); durations pack into greedy lanes on the other side of the
axis. Month ticks, optional timebands (horizontal only), today line.

## pit — points-in-time poster

Milestone/event dots on an axis with labella-placed label boxes on one or
both sides. Sibling of timeline's adapter with PIT extras: inline dates
in the label box, label icons, leader-path perpendicular stubs so
arrowheads sit flush, and a soft cap of 80 events/side (warns, still
renders).

## blockplan — spreadsheet-like program plan

Top/bottom time-band rows around a swimlane region; see the page-anatomy
diagram in `visualizers/blockplan/renderer.py`'s module docstring. Lane
routing: theme `swimlane_rules` (LaneEngine) or legacy per-lane `match:`
dicts. Rule-driven vertical lines/column fills pin to band segments.

## gantt — task table plus dependency chart

Task table on the left, timescale chart on the right; page-anatomy diagram
in `visualizers/gantt/renderer.py`'s module docstring. Split across small
modules: `columns.py` (the task table's column model, resolution and
wrap/truncate), `rows.py` (WBS-numeric ordering and indentation),
`bars.py` (bar geometry on the visible-day axis), `dependencies.py` (link
resolution and curved-leader routing), `layout.py` (page frame plus
`plan_pages`).

Two things shape everything else. First, the axis is a list of *visible*
days, so under `weekend_style 0` all horizontal geometry is column-index
based, not linear in date. Second, the chart paginates on both axes
(`_p2`, `_p3`, …), which is why band segments are built once for the whole
range and sliced per page rather than rebuilt — otherwise interval
counters restart at every break.

Dependencies come from `events.predecessors`, parsed by
`shared/predecessors.py` and resolved against `events.source_id`. Each
link leaves and enters the edge its type implies (FS/SS/FF/SF); lag is
parsed and stored but does not shift geometry.  The leader itself is the
PIT construction — perpendicular stub, `hCurveBetween` cubic, arrowhead
as an `orient="auto"` SVG marker — so the two views draw connectors the
same way. Anything the chart cannot
show faithfully — a clipped bar, an event moved off a hidden weekend, an
off-chart predecessor — is recorded in the render record and listed in
the run's details document instead of being silently dropped.

## compactplan — dense activity plan

Time bands on top, then activity rows grouped by resource group with a
palette-cycled legend. Shares `shared/timeband.py` segment building with
blockplan and the same nwd-fill helpers (kept per-visualizer: different
config namespaces).

## excelblockplan — XLSX export

Not SVG: `visualizers/excelblockplan.py` writes the workbook — timeband
heading rows, the column-header row, then data rows (events + durations
sorted by start; none with `--empty`, which leaves an empty planning
template). It reads config directly — no layout/renderer split. Verified by
the completeness probes in `tests/`.

## sheets — inspection previews

`visualizers/sheets.py` (no package): standalone SVG-string builders for
`palettesheet` / `colorsheet` / `fontsheet` / `iconsheet` /
`patternsheet`. They bypass the layout/renderer pipeline entirely.
