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

## Phase 1 — per-renderer migration

Renderer files and their CalendarConfig-styling-field reference counts (from
`grep -rE "config\.(day_box|mini_|timeline_|blockplan_|weekly_|compact_plan_|theme_|fiscal_period_)\w+"`):

| Renderer | File | Field reads | Token mapping |
|---|---|---|---|
| timeline | `visualizers/timeline/renderer.py` | 96 | `text:event_name`, `text:event_notes`, `text:event_date`, `text:duration_date`, `text:today_label`, `box:event`, `box:duration`, `box:milestone`, `box:callout`, `line:axis`, `line:today`, `line:tick`, `icon:event`, `icon:milestone` |
| blockplan | `visualizers/blockplan/renderer.py` | 95 | `text:band_label`, `text:swimlane_label`, `text:event_name`, `text:event_notes`, `text:duration_date`, `box:band`, `box:band_heading`, `box:swimlane_heading`, `box:swimlane_content`, `box:duration`, `box:event`, `box:milestone`, `box:vline`, `line:grid`, `icon:event`, `icon:milestone` |
| mini | `visualizers/mini/renderer.py` | 47 | `text:day_number`, `text:month_title`, `text:week_number`, `text:holiday_title`, `box:day`, `box:cell`, `line:grid`, `icon:milestone` |
| weekly | `visualizers/weekly/renderer.py` | 37 | `text:day_number`, `text:month_title`, `text:week_number`, `text:event_name`, `text:event_notes`, `text:event_date`, `text:holiday_title`, `box:day`, `box:cell`, `line:grid`, `icon:event`, `icon:overflow` |
| mini (day_styles) | `visualizers/mini/day_styles.py` | 19 | `box:day` (federal/company-holiday content rules); follow the existing `find_rules` pattern |
| mini (layout) | `visualizers/mini/layout.py` | 17 | geometry only — most reads stay on CalendarConfig non-styling fields |
| text-mini | `visualizers/text_mini/renderer.py` | 12 | `text_mini.*` glyph-set fields stay (these aren't styling — they're symbol declarations) |
| mini-icon | `visualizers/mini_icon/renderer.py` | 10 | inherits from mini; mostly `mini_calendar.icon_set` (non-styling) |
| svg_base | `renderers/svg_base.py` | 10 | shared base — migrate after at least one visualizer is on the new path |
| compactplan | `visualizers/compactplan/renderer.py` | 1 | minimal — start here for the easiest first migration |

Recommended order: compactplan → mini-icon → text-mini → mini → weekly →
timeline → blockplan. Smaller-impact first, biggest last. Each visualizer is
its own commit.

### Per-renderer migration recipe

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

### Per-renderer punch list

#### compactplan (1 field read, smallest)
- [ ] `visualizers/compactplan/renderer.py` — replace 1 reference
- [ ] Verify against `default`, `TJX` themes
- [ ] Commit

#### mini-icon (10 reads)
- [ ] `visualizers/mini_icon/renderer.py` — separate `mini_calendar.icon_set`
      reads (non-styling, stays) from styling reads (token queries)
- [ ] `visualizers/mini_icon/visualizer.py` — verify it only reads
      non-styling config; if so, no change needed
- [ ] Commit

#### text-mini (12 reads, non-themed glyph renderer)
- [ ] `visualizers/text_mini/renderer.py` — `text_mini.*` glyph-set fields
      stay on CalendarConfig (they're symbol declarations, not styling).
      Only the few color/font-family reads need migrating.
- [ ] Commit

#### mini (47 + 19 + 17 = 83 reads)
- [ ] `visualizers/mini/renderer.py` — text:day_number, text:month_title,
      text:week_number, text:holiday_title, box:day, box:cell, line:grid,
      icon:milestone
- [ ] `visualizers/mini/day_styles.py` — content rules on `box:day` via
      `find_rules`; existing federal/company-holiday logic translates
      cleanly
- [ ] `visualizers/mini/layout.py` — most reads are geometry
      (`mini_columns`, `mini_rows`, etc.); only `_color` and `_font` reads
      need migrating
- [ ] `visualizers/mini/visualizer.py` — should be minimal styling reads
- [ ] Commit

#### weekly (37 reads)
- [ ] `visualizers/weekly/renderer.py` — text:day_number, text:month_title,
      text:week_number, text:event_name, text:event_notes, text:event_date,
      text:holiday_title, box:day, box:cell, line:grid, icon:event,
      icon:overflow
- [ ] `visualizers/weekly/layout.py` — geometry only; verify no styling reads
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
- [ ] `renderers/svg_base.py` — shared rendering primitives. Migrate after
      at least two visualizers are on the new path so the migration pattern
      is established.
- [ ] Commit

#### excelheader (XLSX path)
- [ ] `visualizers/excelheader.py` — most reads are XLSX-specific and stay
      (per design §10.4). Only the SVG-equivalent styling fields need
      migrating (band fills/colors, fonts other than `excel_font_*`).
- [ ] Commit

---

## Phase 2 — strip `CalendarConfig` styling defaults

After every renderer is on `config.theme`, the corresponding CalendarConfig
fields become dead — they're populated by `ThemeEngine.apply()` from the
decompiled legacy sections but nothing reads them. Stripping them is safe
and reveals any consumer the migration missed.

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
      including `tests/test_theme_engine.py` (which had a pre-existing sort
      failure on `main` that may or may not still apply).
- [ ] **Run the render completeness probe** —
      `tests/test_render_completeness.py` — exit 0.
- [ ] **Run `tools/validate_theme.py`** against every in-tree theme; all
      should pass.
- [ ] **Update the design document** (`design_unified_style_rules.html`)
      to mark the implementation complete: the "End of design" footer can
      drop the "Next step: implement the unified loader..." text.

---

## Estimated effort

The renderer migration is mechanical but voluminous. Time estimates per
visualizer (assuming careful work, SVG diffing, and test runs):

| Step | Estimated time |
|---|---|
| compactplan | 30 minutes |
| mini-icon | 30 minutes |
| text-mini | 1 hour |
| mini | 3-4 hours |
| weekly | 2-3 hours |
| timeline | 5-6 hours |
| blockplan | 5-6 hours |
| svg_base | 1-2 hours |
| excelheader | 1-2 hours |
| Phase 2 (strip) | 2-3 hours |
| Phase 3 (delete bridge) | 1 hour |
| Phase 4 (validation) | 2-3 hours |
| **Total** | **25-32 hours** |

This is genuinely multi-day work — at a focused 4-hour daily pace, the
remaining cutover is roughly a working week.

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
```
