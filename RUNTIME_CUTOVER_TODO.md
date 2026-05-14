# Runtime cutover — remaining work

This list captures the work that's left on the `unified-style-rules` branch
after the format-and-infrastructure migration landed. The design document
(`design_unified_style_rules.html`) is the spec; this file is the punch list.

The work splits into three phases that must land in order:

1. **Per-renderer migration** — replace `config.<styling_field>` reads with
   `config.theme.resolve_token(...)` / `config.theme.find_rules(...)`. One
   visualizer at a time. Each renderer's tests + the render completeness
   probe (`tests/test_render_completeness.py`) gate the migration.

2. **Strip `CalendarConfig` styling defaults** — once no consumer reads a
   field, remove its `field(default=…)` and (eventually) the field itself.

3. **Delete the decompiler bridge** — once `CalendarConfig` no longer needs
   the legacy styling sections populated by `theme_engine.apply()`, remove
   `config/style_rules_decompiler.py`, its invocation in `theme_engine.load()`,
   and the corresponding tests.

The integration point already exists: `CalendarConfig.theme` is a
`UnifiedTheme` populated by `ThemeEngine.apply()`. Each migration step just
swaps reads from one source to the other.

---

## Status — 2026-05-11

### Done

| Renderer | Commit | Notes |
|---|---|---|
| compactplan | `02ad87fe` | Sole `theme_style_rules` read sourced from `config.theme.sections`. SVG byte-identical. |
| mini-icon | `a416c0a9` | 10 reads (day/grid/milestone) on tokens. SVG byte-identical on SAMPLE + basic. |
| text-mini | n/a | Confirmed zero styling reads (all 12 are geometry / formatting / symbol declarations). |
| svg_base helper hoist | `6a2f4244` | Added `BaseSVGRenderer._resolve_token(config, token, ctx)` for reuse. Not a migration of svg_base's own 10 reads. |
| mini family | `8f0ce7b5` | 83 reads across `renderer.py` + `day_styles.py`. SVG **NOT** byte-identical — see Open issues §1 and §2. |

### Pattern that emerged from the mini migration

Apply this template when picking up weekly / timeline / blockplan:

- **Token cache per render.** Add a `_populate_<viz>_tokens(config)` method
  called at the top of `_render_content` that pre-resolves every token the
  visualizer needs into `self._<viz>_tokens`. Per-cell draw code reads via
  a small `self._tk("text:day_number")` accessor — dict lookups, not rule
  walks per cell.

- **Token-first, legacy-fallback at every read site.** Each replacement
  takes the shape:

  ```python
  font  = tk.get("font")  or _ts.font
  size  = tk.get("size")  or config.<legacy_field>
  color = tk.get("color") or _ts.color
  ```

  The legacy field stays as the fallback chain so the no-theme path still
  works. Phase 2 stripping then runs grep over the renderer and removes
  fields with zero remaining references.

- **`find_rules` for content rules.** When the renderer needs to react to
  per-day / per-event predicates (federal_holiday tint, sprint highlight,
  etc.), call `theme.find_rules("box:day", ctx)` (or the relevant target)
  and layer each returned rule's `style` bag onto the in-progress draw
  state. See `mini/day_styles.py::_apply_box_day_rules` for the shape.

- **StyleEngine input rerouted.** Replace `config.theme_style_rules` reads
  with a per-package `_<viz>_style_rules(config)` helper that prefers
  `config.theme.sections["style_rules"]` and falls back to the legacy
  field. See `compactplan/renderer.py::_resolve_style_rules` and
  `mini/renderer.py::_mini_style_rules`.

- **Mini-specific / page-specific reads stay.** When a field has no
  unified-token analogue (e.g. `mini_month_outline_*` for the month grid
  border, `mini_details_output_suffix` for the second SVG filename),
  leave it on CalendarConfig and add a one-line comment naming why. These
  get reconsidered in Phase 2.

---

## Open issues — must resolve before continuing

The mini migration surfaced these. Each affects rendered output, future
migrations, or the Phase 2/3 cleanup story. Resolve before applying the
pattern to weekly / timeline / blockplan.

### 1. Theme-defined text sizes now override `setfontsizes` output — RESOLVED

**Resolution (option c).** `setfontsizes()` now consults
`config.theme.resolve_token(<token>)["size"]` for every field that has a
unified-theme analogue, and only falls back to the page-height heuristic
when the token is unset (or no theme is loaded).  Per-visualizer ctx
(`{"visualizer": "mini" | "weekly" | "timeline" | "blockplan",
"papersize": <name>}`) is supplied so themes can write per-visualizer or
per-papersize overrides via `select:`.  Page-chrome fields (header_*,
footer_*, blockplan_header_font_size, watermark_font_size) have no token
analogue and continue to use the heuristic unconditionally.

The mini renderer's existing `tk.get("size") or config.<legacy>` pattern
now behaves consistently: when a token defines `size:`, both branches
return the same value; when it doesn't, the legacy field carries the
heuristic.  This makes Phase 2 stripping safe — there is no precedence
inversion to silently flip.

**Field-to-token mapping** (centralized in `config/config.py::setfontsizes`):

| CalendarConfig field | Token | Visualizer ctx |
|---|---|---|
| `week_number_font_size` | `text:week_number` | weekly |
| `day_name_font_size` / `color_key_font_size` | `text:label` | weekly |
| `day_box_number_font_size` / `day_box_icon_font_size` | `text:day_number` | weekly |
| `fiscal_period_label_font_size` | `text:fiscal_label` | (none — shared) |
| `weekly_name_text_font_size` / `weekly_text_font_size` / `event_icon_font_size` | `text:event_name` | weekly |
| `weekly_notes_text_font_size` | `text:event_notes` | weekly |
| `mini_cell_font_size` | `text:day_number` | mini |
| `mini_title_font_size` | `text:month_title` | mini |
| `mini_header_font_size` | `text:label` | mini |
| `mini_week_number_font_size` | `text:week_number` | mini |
| `mini_details_title_font_size` | `text:heading` | mini |
| `mini_details_header_font_size` | `text:label` | mini |
| `mini_details_name_text_font_size` / `mini_details_text_font_size` | `text:event_name` | mini |
| `mini_details_notes_text_font_size` | `text:event_notes` | mini |
| `timeline_name_text_font_size` / `timeline_text_font_size` | `text:event_name` | timeline |
| `timeline_notes_text_font_size` | `text:event_notes` | timeline |
| `blockplan_band_font_size` | `text:band_label` | blockplan |
| `blockplan_lane_label_font_size` | `text:swimlane_label` | blockplan |
| `blockplan_name_text_font_size` / `blockplan_text_font_size` | `text:event_name` | blockplan |
| `blockplan_notes_text_font_size` | `text:event_notes` | blockplan |
| `blockplan_event_date_font_size` | `text:event_date` | blockplan |
| `blockplan_duration_date_font_size` | `text:duration_date` | blockplan |

**Visible effect** matches the issue's "concrete effect" description:
basic.yaml's `text:label size: 7` now sets `mini_header_font_size = 7`
(was ~9.5 from heuristic); SAMPLE.yaml's `text:day_number size: 11` now
sets both `mini_cell_font_size` and `day_box_number_font_size = 11`
(were ~9.5 / ~10.3).  The visible shift is the design intent.

**Future audit (theme authors).** Themes that want paper-aware scaling
for a token should remove the explicit `size:` from its `define` rule
(or scope it with `select: { papersize: <name> }`).  The migrator
faithfully copied legacy text-style sizes when emitting `define` rules,
so most current themes opt out of scaling by default — that's a theme
cleanup task, not a runtime fix.

### 2. `box:day` content rules now fire in addition to legacy holiday chains

**What changed.** `mini/day_styles.py::_apply_box_day_rules` now walks
`theme.find_rules("box:day", ctx)` and overlays each matching rule's
`style` bag onto the `DayStyle`. Previously the legacy `StyleEngine` only
matched `apply_to: day_box` rules; the unified `apply_to: box:day` form
was silently dropped.

**Concrete effect.** SAMPLE's federal-holiday rule
(`fill: tomato`, `pattern: diagonal-stripes`) now overrides the
`theme_federal_holiday_color` (`lightblue`) that the legacy
`_apply_holidays` chain sets first. Two layers run; the second wins.

**Why this matters.** The two-layer approach (legacy hardcoded chain +
new find_rules pass) is in place to be conservative, but it's confusing:
the visible output depends on which layer's data is present in the theme.
Themes that define *both* a `colors.federal_holiday.color` and a
`box:day` rule will see the box:day rule win — sometimes silently
surprising the theme author.

**Options.**

- **(a) Delete the legacy chains.** Remove the
  `theme_federal_holiday_color` / `theme_mini_holiday_color` /
  `mini_holiday_color` resolution in `_apply_holidays` and
  `_apply_special_days` entirely; `box:day` rules become the only path
  for holiday tinting. Themes without box:day rules lose holiday tints.

- **(b) Keep both layers, document the order.** Leave the current shape;
  add a comment block in `day_styles.py` describing the precedence and a
  release note flagging the change for theme authors.

- **(c) Convert legacy chains to synthesized box:day rules.** Have
  `theme_engine.apply()` emit equivalent `box:day` rules from the
  `colors.federal_holiday` section, so there's only one runtime path.
  Requires deciding what happens when a theme defines both.

Recommendation: **(c)**. Removes the dual code path while preserving
backward-compatible rendering for themes that haven't migrated their
color-section conventions to style_rules.

### 3. Pre-existing failure in `tests/test_theme_engine.py`

The full migration has been running `--ignore=tests/test_theme_engine.py`
since the branch started; the failure pre-dates this work. Before Phase 4
(`uv run python -m pytest tests/` exit 0), this needs to be either fixed
or explicitly retired.

### 4. Mini renderer leaves residual legacy reads in place

`mini/renderer.py` still reads `config.mini_month_outline_*`,
`config.mini_details_*`, `config.fiscal_period_label_font_size`,
`config.mini_cell_bold_font`, and the legacy day_styles color chains.
These are documented as "no clean token analogue" or "shared field, awaits
sibling-renderer migration." Until they're addressed (Phase 2 stripping
or token invention), `CalendarConfig` cannot drop those fields.

Decisions needed before Phase 2:

- `mini_month_outline_*` → invent `box:month_outline` token, or accept as
  permanent CalendarConfig (mini-specific layout, not styling).
- `mini_details_*` (color/opacity/font-size) → bind to `text:event_name`
  / `text:event_notes` / `text:label`, or leave as page-specific.
- `fiscal_period_label_font_size` is shared with weekly; coordinate the
  two renderers' migrations so the field can be stripped at the same time.
- The legacy holiday color chains in `day_styles.py` (lines 123, 166,
  181, 188, 204, 232) — resolved together with Open issue §2.

### 5. `_resolve_token` cache shape is per-visualizer

`MiniCalendarRenderer._populate_mini_tokens` hardcodes the list of tokens
the renderer queries. As each migration lands, every visualizer adds its
own similar method. This is fine for the first few; if patterns repeat,
consider hoisting to `BaseSVGRenderer` with a per-subclass declarative
list.

### 6. Icon halo / background tokens are defined but never drawn

The design ([design_unified_style_rules.html](design_unified_style_rules.html) §10.3 / §11.4)
specifies that each icon glyph token is paired with an optional `box:`
token for a halo or background rect behind the glyph:

| Icon token (glyph) | Halo token (background) |
|---|---|
| `icon:milestone` | `box:milestone` |
| `icon:event` | `box:event` |
| `icon:duration` | `box:duration` |

Worked example from the design (critical-milestone halo):

```yaml
- name: critical milestone — halo
  apply_to: box:milestone
  select: { priority_min: 1 }
  style:
    fill: "#fde0e0"
    fill_opacity: 0.6
    stroke: red
    stroke_width: 0.5
```

**Where it stands today.**

- Every reference theme defines `box:milestone` (basic.yaml / SAMPLE.yaml
  ship it as the no-op `fill: none, stroke: none`; other themes pick it
  up via `_backfill_from_basic` in `tools/migrate_theme.py`).
- A grep across all renderers turns up exactly one consumer of any
  `box:` content-rule token — `mini/day_styles.py::_apply_box_day_rules`
  reading `box:day` — and that wiring landed only in commit `8f0ce7b5`.
  `box:milestone`, `box:event`, `box:duration` have zero readers.
- Every icon-drawing site in the compactplan renderer (and weekly,
  timeline, blockplan, mini) calls `_draw_icon_svg(...)` directly with
  no preceding rect, so a theme that sets `box:milestone.fill: gold`
  today parses cleanly, validates, binds, and renders nothing.

**Wiring required.** Two pieces:

1. **`_draw_icon_svg` (or a wrapper) draws the halo rect first.**
   When a paired `box:` token resolves to a non-empty style bag for the
   current context, paint a rect at the icon's bounding box before the
   glyph. Honour `fill` / `fill_opacity` / `stroke` / `stroke_width` /
   `pattern` / `pattern_color` / `pattern_opacity` / `dasharray` — the
   same vocabulary as `box:day`. Decide whether the rect inflates
   beyond the glyph (a true halo) or hugs it; either way, expose a
   small `padding` (or radius) override on the token.

2. **Each icon call-site forwards the halo token name.** The cleanest
   shape is to extend `_draw_icon_svg` with a `box_token: str | None`
   kwarg; the icon-call-site sites pass `"box:milestone"` etc., and
   the helper does the `find_rules` / `resolve_token` lookup itself.
   Five compactplan sites to update (duration start, continuation,
   non-workday band cell, legend, milestone marker), plus the
   equivalents in weekly / timeline / blockplan / mini.

**Decisions needed before implementation.**

- *Per-icon-context routing.* `box:milestone` is the same token for
  every milestone everywhere. Should compactplan's duration-start icons
  consult `box:duration` even though they're inside a duration row, or
  is the halo concept reserved for milestones (per the design example)?
  Either is defensible; pick one before writing the call-sites.
- *Halo geometry.* The design's example sets only `fill` / `stroke`;
  it doesn't say whether the rect is the same dimensions as the icon
  or inflated. Probably want a default of `icon_size * 1.2` square,
  with a token-level `padding` override.
- *Selector context for `find_rules("box:milestone", ctx)`.* The
  context dict needs to carry the same event-attribute predicates
  that the design's worked example uses (`priority_min`, `task_name`,
  `percent_complete`, etc.). The mini `_apply_box_day_rules` ctx is a
  day-context (federal_holiday / company_holiday / workday); icon
  halo ctx would mirror what `StyleEngine.evaluate_event` already
  matches against. Likely needs a small `_event_ctx(event)` helper
  alongside the existing day-context builder.

Treat this as a Phase 1.5 deliverable — best done once at least one
of weekly / timeline / blockplan is on the new token path so the
helper can land on `BaseSVGRenderer` with two or three callers
already exercising the pattern, rather than on `MiniCalendarRenderer`
alone.

---

## Phase 1 — per-renderer migration

Renderer files and their CalendarConfig-styling-field reference counts (from
`grep -rE "config\.(day_box|mini_|timeline_|blockplan_|weekly_|compact_plan_|theme_|fiscal_period_)\w+"`):

| Renderer | File | Field reads | Status | Token mapping |
|---|---|---|---|---|
| compactplan | `visualizers/compactplan/renderer.py` | 1 | **done** (`02ad87fe`) | `style_rules` |
| mini-icon | `visualizers/mini_icon/renderer.py` | 10 | **done** (`a416c0a9`) | `text:day_number`, `line:grid`, `icon:milestone` |
| text-mini | `visualizers/text_mini/renderer.py` | 12 | **done** (no-op) | symbols only, no styling reads |
| mini | `visualizers/mini/renderer.py` | 47 | **done** (`8f0ce7b5`) | full set per pattern above |
| mini (day_styles) | `visualizers/mini/day_styles.py` | 19 | **done** (`8f0ce7b5`) | `find_rules("box:day", ctx)` pass added; legacy chains remain (see Open issue §2) |
| mini (layout) | `visualizers/mini/layout.py` | 17 | **skipped** | geometry only; no styling reads requiring migration |
| weekly | `visualizers/weekly/renderer.py` | 37 | pending | `text:day_number`, `text:month_title`, `text:week_number`, `text:event_name`, `text:event_notes`, `text:event_date`, `text:holiday_title`, `box:day`, `box:cell`, `line:grid`, `icon:event`, `icon:overflow` |
| timeline | `visualizers/timeline/renderer.py` | 96 | pending | `text:event_name`, `text:event_notes`, `text:event_date`, `text:duration_date`, `text:today_label`, `box:event`, `box:duration`, `box:milestone`, `box:callout`, `line:axis`, `line:today`, `line:tick`, `icon:event`, `icon:milestone` |
| blockplan | `visualizers/blockplan/renderer.py` | 95 | pending | `text:band_label`, `text:swimlane_label`, `text:event_name`, `text:event_notes`, `text:duration_date`, `box:band`, `box:band_heading`, `box:swimlane_heading`, `box:swimlane_content`, `box:duration`, `box:event`, `box:milestone`, `box:vline`, `line:grid`, `icon:event`, `icon:milestone` |
| svg_base | `renderers/svg_base.py` | 10 | pending | shared base — migrate after weekly/timeline establish patterns |
| excelheader | `visualizers/excelheader.py` | TBD | pending | most reads are XLSX-specific (per design §10.4); only the SVG-equivalent styling fields migrate |

Recommended order for the remaining work: **resolve Open issue §2**
(§1 is done — see Open issues section), then weekly → timeline →
blockplan → svg_base → excelheader.

### Per-renderer migration recipe

(Unchanged — apply the same recipe as before, but with the pattern
section above guiding shape decisions.)

For each renderer (one commit each):

- [ ] **Enumerate the styling fields.** Run
      `grep -nE "config\.(day_box|mini_|timeline_|...)\w+" visualizers/<name>/renderer.py`
      and list every distinct CalendarConfig field the renderer reads.
- [ ] **Map each field to a token query.** Use the table above. Most fields
      map to `config.theme.resolve_token("<kind>:<name>")[<property>]`. Fields
      that depend on event data (federal_holiday tint, sprint highlight)
      become `config.theme.find_rules("box:day", ctx)` walks.
- [ ] **Replace the reads.** Build a small helper at the top of the renderer
      (e.g. `def _text_style(name, ctx): return self.config.theme.resolve_token(f"text:{name}", ctx)`)
      so each call site stays one line.
- [ ] **Capture a pre-migration SVG baseline** by checking out the previous
      commit and running the visualizer against `default.yaml`, `corporate.yaml`,
      `dark.yaml`, and `TJX.yaml`. Save the outputs.
- [ ] **Migrate the renderer.** Replace one field at a time, running the
      visualizer's existing tests (`tests/test_<name>.py`) between substantial
      groups of changes.
- [ ] **Diff post-migration SVG output** against the baseline. Acceptable
      differences: rounding noise, attribute order. Anything substantive needs
      investigation — either the token resolution is producing a wrong value or
      a content rule isn't firing where it used to.
- [ ] **Run the render completeness probe** —
      `uv run python -m pytest tests/test_render_completeness.py` — exit 0.
- [ ] **Run the full suite** —
      `uv run python -m pytest tests/ --ignore=tests/test_theme_engine.py` — exit 0.
- [ ] **Commit** with a message that lists the fields migrated and the
      visualizer/theme combinations the diffs covered.

### Per-renderer punch list (remaining)

#### weekly (37 reads)
- [ ] `visualizers/weekly/renderer.py` — text:day_number, text:month_title,
      text:week_number, text:event_name, text:event_notes, text:event_date,
      text:holiday_title, box:day, box:cell, line:grid, icon:event,
      icon:overflow
- [ ] `visualizers/weekly/layout.py` — geometry only; verify no styling reads
- [ ] Coordinate `fiscal_period_label_font_size` migration with mini (Open
      issue §4) so the field can be stripped in Phase 2
- [ ] Commit

#### timeline (96 reads, largest)
- [ ] `visualizers/timeline/renderer.py` — full token set (events,
      durations, callouts, axis, today, ticks, milestones)
- [ ] `visualizers/timeline/layout.py` — geometry only
- [ ] Commit

#### blockplan (95 reads, second-largest)
- [ ] `visualizers/blockplan/renderer.py` — full token set (bands,
      swimlanes, events, durations, milestones, vlines, grid)
- [ ] `visualizers/blockplan/layout.py` — geometry only
- [ ] Lane routing already lives in `config.theme.route_lane(ctx)`;
      replace any direct read of `config.blockplan_lane_match_mode` /
      legacy swimlane-rules infrastructure
- [ ] Commit

#### svg_base (10 reads)
- [ ] `renderers/svg_base.py` — shared rendering primitives. Already has
      `_resolve_token()` helper from the mini-icon prep commit. Migrate
      after weekly + timeline are on the new path so the pattern is
      fully established.
- [ ] Commit

#### excelheader (XLSX path)
- [ ] `visualizers/excelheader.py` — most reads are XLSX-specific and stay
      (per design §10.4). Only the SVG-equivalent styling fields need
      migrating (band fills/colors, fonts other than `excel_font_*`).
- [ ] Commit

---

## Phase 1.5 — wire icon halo / background tokens

The `box:<icon-token>` halo design (Open issue §6) is independent
from the per-renderer field migrations and can land in parallel.
Land it after at least one of weekly / timeline / blockplan is on
the new token path so the helper can live on `BaseSVGRenderer` with
multiple existing callers, rather than being scaffolded on
`MiniCalendarRenderer` alone.

Token pairs to wire:

| Glyph | Halo |
|---|---|
| `icon:milestone` | `box:milestone` |
| `icon:event`     | `box:event`     |
| `icon:duration`  | `box:duration`  |

### Recipe

- [ ] **Event/context builder.** Add a `_event_ctx(event)` helper
      (next to the existing day-context builder in
      `shared/rule_engine.py` or as a new staticmethod on
      `BaseSVGRenderer`) that produces the selector dict
      `find_rules("box:milestone", ctx)` needs — `event_type`,
      `milestone`, `task_name`, `notes`, `resource_group`,
      `resource_names`, `wbs`, `priority`, `percent_complete`,
      `rollup`, plus the ambient `visualizer` / `papersize` tags.
- [ ] **`_draw_icon_svg` halo support.** Extend the signature with
      a `box_token: str | None = None` kwarg.  When set, the helper
      itself calls `find_rules(box_token, ctx)` (passing the icon
      bounding box + ctx through), and paints a rect with the
      merged style bag before the glyph.  Honour the full box
      vocabulary: `fill`, `fill_opacity`, `stroke`, `stroke_width`,
      `stroke_opacity`, `dasharray`, `pattern`, `pattern_color`,
      `pattern_opacity`, plus a token-level `padding` (default 0)
      that inflates the rect beyond the glyph for a true halo
      effect.
- [ ] **Compactplan call-sites — five.**
      `visualizers/compactplan/renderer.py`:
      duration start icon (line ~286), continuation icon (~309),
      non-workday band-cell icon (~519), legend icon (~944), and
      milestone marker (~746 — uses `drawsvg.Raw`; needs a small
      refactor to go through `_draw_icon_svg`).  Each gets
      `box_token="box:duration"` / `"box:milestone"` /
      `"box:event"` per the routing decision below.
- [ ] **Weekly / timeline / blockplan / mini call-sites.** Audit
      every `_draw_icon_svg` call in each renderer and add the
      paired `box_token` argument.
- [ ] **Routing decision — settle two questions before writing
      call-sites:**
      * Do duration-start icons consult `box:duration` (matches
        the row's data) or stay un-haloed?
      * Does the non-workday band-cell icon consult any halo token,
        or is its band-cell fill considered sufficient background?
- [ ] **Reference theme example.** Add an annotated `box:milestone`
      rule (or `box:event` for compactplan) to `SAMPLE.yaml` so
      theme authors can copy-paste a working halo without re-reading
      the design doc.
- [ ] **Validation.** Render `compactplan 20190401 20190731
      --theme TJXcompactplan` (or the SAMPLE equivalent) with a
      temporarily uncommented `box:milestone.fill: gold` rule and
      confirm a gold rect appears behind every milestone glyph.
      Then put it back to `fill: none` and confirm the rect is
      gone (no zero-opacity ghost rects in the SVG).
- [ ] **Commit.**

---

## Phase 2 — strip `CalendarConfig` styling defaults

After every renderer is on `config.theme`, the corresponding CalendarConfig
fields become dead — they're populated by `ThemeEngine.apply()` from the
decompiled legacy sections but nothing reads them. Stripping them is safe
and reveals any consumer the migration missed.

**Blocker:** Open issue §4 must be resolved first.  (§1 is done — the
precedence story is now consistent: tokens win when defined, heuristic
falls back when not, and the renderer's `tk.get(x) or config.<legacy>`
shape returns the same value either way.)  For Phase 2 to also strip
the page-aware `setfontsizes` heuristic safely, `setfontsizes` will
need to *write* its computed sizes back into the unified-theme token
registry (so the renderer's direct `tk.get("size")` read still gets a
value when no theme defines `size:`).  That's a Phase 2 design decision
the strip pass needs to settle.

- [ ] **Identify candidate fields.** A field is a candidate if every
      `grep` for `config.<field>` (excluding tests and theme_engine itself)
      returns nothing.
- [ ] **Strip in batches** by family — all `day_box_*` together, all
      `mini_*` together, etc. Each batch is one commit.
- [ ] **For each batch:** delete the `field(default=...)` (move to
      `field(default=None)` first if the field is still legally referenced
      from `ThemeEngine.apply()` populating it), run the full suite.
- [ ] **Once a field has no `setattr(config, <field>, ...)` in
      theme_engine.py either**, delete the field from the dataclass
      entirely. The `_setattr_from_theme` paths in
      `theme_engine._apply_color_maps()`, `apply()`, etc. also delete.

The end state: `CalendarConfig` has only non-styling fields — geometry,
format strings, palette references, fiscal semantics, the loaded
`UnifiedTheme`, and the runtime-only fields like `papersize` and date range.

---

## Phase 3 — delete the decompiler bridge

Decompiler removal is safe once no `CalendarConfig` field requires the
synthesized legacy sections.

- [ ] **Confirm `ThemeEngine.apply()` no longer reads from
      `self._theme_data["text_styles"]`, `["box_styles"]`, etc.** by removing
      `_parse_text_styles`, `_parse_box_styles`, `_parse_line_styles`,
      `_parse_icon_styles`, `_parse_element_bindings` calls — they should
      now be unused.
- [ ] **Delete the decompiler call** in `ThemeEngine.load()`.
- [ ] **Delete `config/style_rules_decompiler.py`** and
      `tests/test_style_rules_decompiler.py`.
- [ ] **Delete the legacy-section parsers** from `theme_engine.py`
      (`_parse_text_styles` etc.) — they have no consumers.
- [ ] **Delete `_unified_theme_data` and the copy.deepcopy** in
      `ThemeEngine.load()` — `_theme_data` is now the unified form, no
      snapshot needed.

---

## Phase 4 — final validation

- [ ] **Re-render every visualizer × theme combination** and diff against
      the pre-migration baseline saved at the start of Phase 1. Visual
      regressions must be explained.
- [ ] **Run the full test suite** — `uv run python -m pytest tests/` —
      including `tests/test_theme_engine.py` (Open issue §3 — fix or
      retire the pre-existing failure before this gate).
- [ ] **Run the render completeness probe** —
      `tests/test_render_completeness.py` — exit 0.
- [ ] **Run `tools/validate_theme.py`** against every in-tree theme; all
      should pass.
- [ ] **Update the design document** (`design_unified_style_rules.html`)
      to mark the implementation complete: the "End of design" footer can
      drop the "Next step: implement the unified loader..." text.

---

## Estimated effort (revised)

The renderer migration is mechanical but voluminous. Time estimates per
visualizer (assuming careful work, SVG diffing, and test runs):

| Step | Estimated time | Status |
|---|---|---|
| compactplan | 30 minutes | **done** |
| mini-icon | 30 minutes | **done** |
| text-mini | 1 hour | **done** (no-op) |
| mini | 3-4 hours | **done** |
| Open issue §1 resolution (font-size precedence) | 1 hour | **done** |
| **Open issue §2 resolution (dual box:day chain)** | **1-2 hours** | **blocker** |
| weekly | 2-3 hours | pending |
| timeline | 5-6 hours | pending |
| blockplan | 5-6 hours | pending |
| svg_base | 1-2 hours | pending |
| excelheader | 1-2 hours | pending |
| Phase 1.5 (icon halo wiring) | 3-4 hours | parallel to Phase 1; lands after first non-mini renderer migrates |
| Phase 2 (strip) | 2-3 hours | blocked on Phase 1 + Open §4 |
| Phase 3 (delete bridge) | 1 hour | blocked on Phase 2 |
| Phase 4 (validation) | 2-3 hours | blocked on Phase 3 + Open §3 |
| **Remaining total** | **~25-35 hours** | |

---

## Useful invocations

```bash
# Inspect a converted theme:
uv run python tools/validate_theme.py config/themes/default.yaml

# Re-render every visualizer × reference theme:
uv run python -m pytest tests/test_render_completeness.py

# Render one combination and look at the SVG:
uv run python ecalendar.py weekly 20260101 20260131 --theme default \
    -of output/weekly_default.svg

# Find every CalendarConfig field reference in a renderer:
grep -nE "config\.(day_box|mini_|timeline_|blockplan_|weekly_|compact_plan_|theme_|fiscal_period_)\w+" \
    visualizers/<name>/renderer.py

# Full suite (skipping the pre-existing failure on main):
uv run python -m pytest tests/ --ignore=tests/test_theme_engine.py

# SVG diff a pre/post change for one theme:
git stash && uv run python ecalendar.py mini 20260101 20260131 \
    --theme SAMPLE -of mini_pre.svg --quiet && cp output/mini_pre.svg /tmp/ \
    && git stash pop && uv run python ecalendar.py mini 20260101 20260131 \
    --theme SAMPLE -of mini_post.svg --quiet \
    && diff /tmp/mini_pre.svg output/mini_post.svg | head -60
```
