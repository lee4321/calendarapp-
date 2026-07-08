# Visualizers

Every SVG visualizer is a package under `visualizers/<name>/` with the same
three files: `layout.py` (geometry → CoordinateDict, PDF coords),
`renderer.py` (a `BaseSVGRenderer` subclass overriding `_render_content`),
and `visualizer.py` (thin orchestrator registered in `factory.py`).
Class-inheritance exceptions are noted below.

## weekly — the flagship calendar

Grid of day boxes, one column per weekday (weekend style 0–4 drives which
columns exist and whether weekend boxes are half-width). Events render as
text lines inside their day box; multi-day durations as bars spanning
boxes; what doesn't fit goes to the `_overflow.svg` table page. Day
decoration (fills, hash lines, DB pattern tiles, holiday titles, fiscal
period labels) resolves per day through StyleEngine content rules +
`box:cell`/`line:hash` tokens.

## mini — compact month grids

Months in a column/row arrangement (`--mini-columns/rows`). Day styling is
centralized in `day_styles.DayStyleResolver` → a `DayStyle` record per
cell (shade, circle, strikethrough, icon, pattern). Rendering is
three-pass per cell — background, duration bars, foreground — so bars sit
under day numbers. Optional second page: `_render_details_svg`
(`--mini-details`).

## mini-icon — mini with glyph day numbers

Extends the mini family; day numbers render as icon glyphs from a named
set (`--mini-icon-set`, e.g. `squircles` — the `klee/` SVG collection
loaded into the DB icon table).

## candybar — vertical year strip

`CandybarRenderer(MiniCalendarRenderer)`: one row per ISO week, month
names in merged boxes on the side (rotatable), optional weekend
suppression. Reuses the entire mini decoration engine (day styles, tokens
under the `mini` visualizer ctx) and the mini details page.

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

## compactplan — dense activity plan

Time bands on top, then activity rows grouped by resource group with a
palette-cycled legend. Shares `shared/timeband.py` segment building with
blockplan and the same nwd-fill helpers (kept per-visualizer: different
config namespaces).

## excelheader / excelblockplan — XLSX exports

Not SVG: `visualizers/excelheader.py` writes a project-planning workbook
template (bands, heading rows); `excelblockplan.py` writes data rows
(events + durations sorted by start). Both read config directly — no
layout/renderer split. Verified by the completeness probes in `tests/`.

## sheets — inspection previews

`visualizers/sheets.py` (no package): standalone SVG-string builders for
`palettesheet` / `colorsheet` / `fontsheet` / `iconsheet` /
`patternsheet`. They bypass the layout/renderer pipeline entirely.
