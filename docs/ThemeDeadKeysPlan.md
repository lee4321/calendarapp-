# Theme Dead-Key Cleanup Plan

Status: **executed 2026-09-14 — see §7**  ·  Date: 2026-09-14  ·  Scope: `config/themes/*.yaml` (10 themes) plus the registry/docs that keep the dead keys alive

## 1. Summary

A theme key can do nothing in four ways:

| Tier | What it means | Keys (distinct paths) | Themes affected |
|---|---|---|---|
| **A** | **Nothing consumes the key.** It isn't in `THEME_TO_CONFIG_MAP`, not reached by cascade, and not handled by any `_apply_*` method. | 70 | all 10 |
| **B** | **Only a no-theme fallback reads the key.** It maps to a `CalendarConfig` field that is read only by `CalendarConfig._fallback_*_style()`, which runs only when a theme has no `style_rules:`. Every shipped theme has `style_rules:`, so these keys do nothing in shipped themes. | 48 set in themes | 8 |
| **C** | **`style_rules` content never takes effect.** This covers tokens nothing resolves, rules whose selector is never bound, and style keys no reader looks at. | ~20 rules / tokens | SAMPLE, basic, all (tokens) |
| **D** | **The registry or docs keep dead keys alive.** `required_keys.py` requires 6 keys that have no effect, and the USER_GUIDE key table still lists stripped fields. | 6 + doc table | — |

The Phase 2 strips (`30d8bef3`, `e9862c78`, `7f55ef84`) removed the translations and config fields. The theme YAMLs were never re-swept, so every loaded theme still carries the dead values. Nothing warns about them: `ThemeEngine._validate()` checks top-level section names only, never keys inside a section.

## 2. Method (reproducible)

1. I flattened every theme to dotted key paths. Free-form maps were not descended: `style_rules`, `time_bands` entries, `element_overrides`, and `colors.months`, `fiscal_periods` and `resource_groups`.
2. I classified each path against every consumer in `config/theme_engine.py`:
   - an exact `THEME_TO_CONFIG_MAP` hit, or a cascade hit (the parent section key, or the `base.` key)
   - `size_rule` targets and `layout.margin.*`
   - the `colors` handlers, `_apply_pit_blocks` and `_BAND_PLACEMENTS`
   - the wholesale sections: `style_rules`, `swimlane_rules`, `element_overrides` and `time_bands`
3. I confirmed that renderers read raw theme sections for `style_rules` and `swimlane_rules` only. Every other section value reaches a renderer through a `CalendarConfig` field.
4. For each mapped field, I grepped non-test code outside `theme_engine.py` and `config.py` for readers. Any hits inside `config.py` were then checked by hand.
5. For tokens, I checked reachability through three routes: `element_catalog.yaml`, renderer `TOKENS` tuples and literals, and `element_overrides` `use:` targets.

The scratch scripts are not committed. Phase 0 below turns this method into a permanent check.

## 3. Findings

### Tier A — keys nothing consumes (remove from themes)

"7 full" = Julia, TJX, accent, corporate, dark, default, vibrant.

**blockplan** (translations dropped in `30d8bef3`)

| Key | Themes |
|---|---|
| `background_color`, `band_font`, `header_font`, `lane_heading_fill_color`, `lane_label_color`, `event_date_color`, `event_date_font`, `timeband_label_opacity`, `name_text.font_color`, `name_text.font_name` | 7 full |
| `lane_label_font`, `timeband_label_color` | 7 full except TJX |
| `band_row_height` | all 10 — still in `REQUIRED_KEYS`, see Tier D |

**compact_plan** (already listed in `tools/migrate_theme.py::_DEAD_LEGACY_KEYS`)

| Key | Themes |
|---|---|
| `axis_color`, `axis_dasharray`, `milestone_color`, `text.font_color` | 7 full |
| `continuation_section_gap`, `duration_icon_color` | TJX, default |
| `axis_opacity`, `duration_opacity`, `duration_stroke_dasharray`, `name_text.font_color`, `name_text.font_opacity`, `text.font_opacity` | TJX |
| `legend_area_ratio` | all 10 — still in `REQUIRED_KEYS`, see Tier D |

**mini_calendar / mini_details** (translations dropped in `7f55ef84`)

| Key | Themes |
|---|---|
| `mini_calendar.cell_box_stroke_dasharray`, `duration_bar_stroke_dasharray`, `header_color`, `header_font`, `week_number_color`, `week_number_font` | 7 full |
| `mini_calendar.day_box: null` (empty leftover of removed `hash_rules`) | 7 full |
| `mini_details.header_color`, `header_font`, `header_font_size`, `title_color`, `title_font`, `name_text.font_name`, `notes_text.font_color`, `notes_text.font_name` | 7 full |

**timeline**

| Key | Themes |
|---|---|
| `background_color`, `duration_bar_stroke_dasharray`, `duration_bracket_stroke_dasharray` | 7 full |
| `date.font_size` | default |
| `event_axis_padding` | TJX |

**header / footer.** Only `header.left`/`header.center`/`footer.center` `font_family`/`font_color` are mapped. `*.right` and `footer.left` have no config fields at all.

| Key | Themes |
|---|---|
| `header.right.font_color`, `header.right.font_family` | Julia, accent, corporate, vibrant |
| `footer.left.font_color`, `footer.right.font_color`, `footer.right.font_family` | Julia, accent, corporate |
| `header.{left,center,right}.text`, `footer.{left,center,right}.text` (header text comes only from `--headerleft` etc.) | SAMPLE |

**pit.** `_apply_pit_blocks` reads only `color` from `leader_primary` and `leader_secondary`, and has no `pattern_opacity` or `stroke_dasharray` on `label`.

| Key | Themes |
|---|---|
| `pit.label.pattern_opacity`, `pit.label.stroke_dasharray`, `pit.leader_primary.marker_end_size`, `pit.leader_secondary.dasharray`, `pit.leader_secondary.marker_start`, `pit.leader_secondary.marker_start_size` | 6 (7 full except TJX) |

**Other**

| Key | Themes |
|---|---|
| `candybar.day_color`, `candybar.month.bold` | 6 (7 full except TJX) |
| `weekly.day_box.icon_color` | 7 full |
| `excelblockplan.band_fonts.fiscal_quarter.excel_font_{name,size}`: the reader wants `excel_font_name`/`excel_font_size` **on the band placement entry** (`visualizers/excelblockplan.py:700`) | SAMPLE |
| `theme.version`, `theme.description`: nothing reads them, but they are metadata (`version` is required). **Keep.** | all 10 |

### Tier B — keys read only by the no-`style_rules` fallback

Each of these maps to a config field whose only reader is `_fallback_text_style` / `_fallback_box_style` / `_fallback_line_style` / `_fallback_icon_style` in `config/config.py`. `get_*_style()` calls those builders only when `theme_styles` has no binding. For a theme with `style_rules:`, the element catalog binds every `ec-*` class (enforced by `tests/test_element_catalog.py`), so the fallback never runs.

All keys below are set in the 7 full themes unless noted.

- **weekly:** `day_box.fill_color`, `day_box.fill_opacity`, `day_box.font_color`, `day_box.number_color`, `day_box.number_font`, `day_names.font_color`, `day_names.font_family`, `name_text.font_color`, `name_text.font_name`, `notes_text.font_color`, `notes_text.font_name`, `week_numbers.font_color`, `week_numbers.font_family`
- **timeline:** `axis_color`, `axis_opacity`, `axis_stroke_dasharray`, `label_stroke_dasharray`, `label_stroke_width`, `marker_stroke_color`, `marker_stroke_width`, `tick_stroke_dasharray`, `today_label_color`, `today_line_dasharray`, `date.font_color`
- **blockplan:** `header_heading_fill_color`, `timeband_fill_color`, `vertical_line_{color,width,opacity,dasharray,fill_color,fill_opacity}` (vertical_line_* not in TJX)
- **mini:** `mini_calendar.title_color`, `mini_calendar.title_font`, `mini_calendar.hash_line_dasharray`, `mini_calendar.strikethrough_stroke_dasharray`, `mini_calendar.duration_bar_stroke_opacity`, `mini_details.separator_stroke_dasharray`
- **global:** `durations.icon_color`, `durations.stroke_dasharray` (+SAMPLE), `overflow.color`, `watermark.color`, `header.left.font_color` / `header.center.font_color` (Julia, accent, corporate, vibrant), `footer.center.font_color` (Julia, accent, corporate)

**Not in Tier B.** Several `*_font_size` keys also feed `_inject_heuristic_size_tokens`: `blockplan.{header,event_date,duration_date,lane_label}_font_size`, `mini_calendar.week_number_font_size`, `mini_details.title_font_size` and `weekly.notes_text.font_size`. That function synthesizes a token `size` whenever the resolved token has none. These keys are **conditionally live**, so leave them alone in this pass.

**Dead mapping, no field reader anywhere:** `("compact_plan.notes_text", "font_size")` → `compactplan_notes_text_font_size`. No theme sets it.

### Tier C — `style_rules` content that never takes effect

**Tokens defined but unreachable.** These are not in the element catalog, not in any renderer's `TOKENS` tuple or literals, and not the target of any `use:`:

| Token | Defined in | Note |
|---|---|---|
| `text:base` | all 10 | Required (Tier D). USER_GUIDE §"What the required keys do" already calls it inert. |
| `text:milestone_label` | all 10 | Required (Tier D) |
| `box:swimlane_heading`, `box:swimlane_content` | all 10 | Required (Tier D) |
| `box:band_heading` | SAMPLE, basic | Not required, so it can be deleted now |

Tokens that *look* unused but are live through `element_overrides` `use:` — keep them: `box:highlight`, `box:timeband`, `line:connector`, `line:tick`, `line:mini_grid`, `text:body_secondary`, `text:label_bold`.

**SAMPLE.yaml rules that never fire** (rule indexes in `style_rules`):

| Rule | Why it never fires |
|---|---|
| [47] `priority 1 — event name` → `text:event_name`, `{color, weight}` | Text tokens are resolved once per page with a visualizer/papersize context, which never binds `priority`. Also, no reader looks at `weight`. |
| [48] `completed items — visual fade` → `box:event`, `box:duration`, `text:event_name` | `fill` works through `rule_engine`. `color` on a box and `italic` have no reader, and the `text:event_name` target has the same problem as [47]. |
| [50] `critical milestone — label` → `text:milestone_label` | The token is never resolved, and nothing reads `weight`. |
| [54]–[63] per-lane `box:swimlane_heading` / `text:swimlane_label` with `select: {swimlane: …}` | No code binds a `swimlane` context key, and `box:swimlane_heading` is never resolved. The working mechanism is the per-lane `fill_color` / `label_color` keys in `blockplan.swimlanes` (`visualizers/blockplan/renderer.py:2312`). |

SAMPLE is the documented example theme, so these rules actively teach patterns that don't work.

**Minor**

- `default.yaml` `time_bands.dow_2` is defined but no placement list references it.

### Tier D — registry and docs that keep dead keys alive

- **`config/required_keys.py`** requires `blockplan.band_row_height`, `compact_plan.legend_area_ratio`, `style_rules:text:base`, `text:milestone_label`, `box:swimlane_heading` and `box:swimlane_content`. None of them affect output; USER_GUIDE line ~1380 already admits this. As long as they are required, `validate_theme.py` forces every theme to carry dead values.
- **`docs/USER_GUIDE.md` §"Complete Theme Key Reference"** (~lines 1615–2010) still lists stripped mappings, for example `blockplan.band_font`, `blockplan.lane_heading_fill_color`, `mini_calendar.header_font`, `timeline.background_color` and `weekly.day_box.icon_color`. Its own header note says it reflects the pre-migration field set.
- **`tools/migrate_theme.py::_DEAD_LEGACY_KEYS`** covers only the header/footer/events/durations/watermark/compact_plan subset. It is also dead code for already-migrated themes, so it is not a guard.

## 4. Proposed changes (one commit per phase)

### Phase 0 — Guard first (no theme edits)

1. Add `find_unconsumed_keys(theme_data) -> list[str]` in `config/theme_engine.py`. It encodes the consumer set from §2: map, cascade, size_rule, margin, colors, pit blocks, band placements and wholesale sections. Keep it next to `THEME_TO_CONFIG_MAP` so that adding a mapping automatically "consumes" its key.
2. Call it from `ThemeEngine._validate()` and log **warnings**. This matches how unknown sections are handled; it must not raise, so user themes keep loading.
3. Call it from `tools/validate_theme.py` as well, reporting the keys as `warn  unconsumed key …` without changing the exit code.
4. Add `tests/test_theme_dead_keys.py`. It asserts that each shipped theme has zero unconsumed keys, with an explicit allowlist (`theme.version`, `theme.description`). Mark it `xfail` until Phase 1 lands, then flip it to a hard assertion.

### Phase 1 — Remove Tier A from all themes

- Delete every Tier A key except the `theme.*` metadata and the two required keys (those move in Phase 3).
- **SAMPLE only:** delete `header/footer.*.text`, and move `excelblockplan.band_fonts.fiscal_quarter.*` onto the matching `excelblockplan.top_bands` placement entry as `excel_font_name` / `excel_font_size`. This is a behavior change, but it makes what the theme already intends take effect.
- Remove `time_bands.dow_2` from default.yaml.
- **Verify** with byte-identical rendering (except the SAMPLE excel fix):
  ```bash
  tools/refcorpus.sh render
  ```
  Run the command above on `main` before editing, then run the check after editing:
  ```bash
  tools/refcorpus.sh check
  ```
  Also run `uv run python -m pytest tests/ -v` and `tools/validate_theme.py` on each theme.
- Tests that may reference removed values: `tests/test_theme_engine.py`, `tests/test_blockplan.py` and `tests/test_timeline.py` use `background_color` / `band_font` / `header_font` / `event_date_*` / `lane_*`. Review each one: most build their own theme dicts rather than loading the YAMLs, so they are probably unaffected.

### Phase 2 — Remove Tier B from all themes

- Delete the Tier B keys listed in §3.
- **Verify** with a byte-identical `refcorpus check`. The refcorpus renders 3 themes only, so also render every visualizer for the other themes before and after and diff them, ignoring `<desc>`. That covers Julia, accent, corporate, vibrant, TJX, dark, SAMPLE, basic and minimal.
- **Do not** remove the mappings or fallback fields in this phase. They still serve user themes without `style_rules:` (see Decision 2).

### Phase 3 — Required-key registry and unreachable tokens

1. Remove the 6 inert entries from `REQUIRED_KEYS`, and the matching assertions in `tests/test_required_keys.py` and `tests/test_unified_theme.py`, if any.
2. Delete `blockplan.band_row_height` and `compact_plan.legend_area_ratio` from all themes. Delete the `text:base`, `text:milestone_label`, `box:swimlane_heading`, `box:swimlane_content` and `box:band_heading` definitions.
   - `basic.yaml` supplies the example snippets for missing-key errors, so check `_example_for` still resolves every remaining required key.
   - Keep `text:base` in `element_catalog_defaults.yaml` only if something reads it there; otherwise drop it.
3. Rewrite SAMPLE rules [47], [48], [50] and [54]–[63] into mechanisms that work, or delete them (see Decision 4):
   - lane colors → `blockplan.swimlanes[].fill_color` / `label_color`
   - "completed fade" → `box:event` / `box:duration` `fill` + `fill_opacity`
   - priority emphasis → `box:event` fill or `icon_color`
4. Remove `weight:`, `italic:` and box-level `color:` from SAMPLE, or add readers (Decision 4).
5. Update USER_GUIDE §"What the required keys do", since that caveat paragraph becomes obsolete.

### Phase 4 — Docs and tooling tidy-up

- Regenerate or prune the USER_GUIDE "Complete Theme Key Reference" so it lists only keys `find_unconsumed_keys` accepts. Ideally generate it from `THEME_TO_CONFIG_MAP` so it can't drift again.
- Drop the dead mapping `("compact_plan.notes_text", "font_size")` and its unread field `compactplan_notes_text_font_size`.
- Regenerate `docs/DefaultRendererValues.md` via `tools/generate_default_renderer_values.py` if anything it cites changed.
- Update the `theme-required-keys` project memory note.

## 5. Decisions needed from the reviewer

1. **Header/footer right-slot fonts (Tier A).** Remove them (recommended; every header/footer slot is styled by `text:heading` / `text:caption` through the catalog anyway), or add mappings plus config fields for `header.right`, `footer.left` and `footer.right`?
2. **Tier B scope.** Theme-only removal (recommended for this pass), or also strip the mappings, the `_fallback_*_style` field reads and the config fields? The larger strip changes the rendering of user themes that have no `style_rules:`, so it needs a deprecation decision of its own.
3. **Warning vs. error for unconsumed keys.** A warning in `ThemeEngine` and `validate_theme.py` (recommended), or a hard `ThemeError` like the retired sections get?
4. **SAMPLE.yaml illustrative rules.** Rewrite them onto working mechanisms (recommended — SAMPLE is documentation), or implement the missing features: a `swimlane` context binding for lane tokens, per-event text token resolution, and `weight`/`italic` readers?
5. **PIT leader per-side extras.** Delete the six `pit.leader_*` / `pit.label.*` extras (recommended), or extend `_apply_pit_blocks` so `leader_primary` / `leader_secondary` honor dasharray, markers and the rest, as the themes imply?
6. **`theme.version` / `theme.description`.** Keep them as unread metadata (recommended), or start reading `version` for schema gating?

## 6. Out of scope

- The contents of `time_bands` entries, `gantt.columns` and `blockplan.swimlanes` entries. Spot checks found every key present there has a reader (`interval_days`, `prefix`, `start_index`, `nonworkdays_only`, `split_ratio`, …).
- Selector keys other than `swimlane` and `priority`-on-text-tokens. All the others are bound somewhere in `rule_engine` or `day_classifier`.
- The stale copy of the themes under `.claude/worktrees/quizzical-boyd-036a9d/`.

## 7. Execution record (2026-09-14)

All recommendations in §5 were accepted and carried out.

**Verification method.** Before any edit, the 10 themes were frozen and every visualizer (weekly, mini, mini-icon, candybar, timeline, blockplan, compactplan, pit, gantt) was rendered for every theme, giving 170 files. A second render from the same frozen themes was byte-identical, which confirmed determinism. Each phase was then re-rendered and diffed against that baseline, ignoring `<desc>`.

| Phase | Result |
|---|---|
| 0 | `find_unconsumed_keys()` added to `config/theme_engine.py`. `ThemeEngine._validate()` logs a warning and `tools/validate_theme.py` prints `warn` for each dead key. `tests/test_theme_dead_keys.py` is a hard assertion over all shipped themes. The size-rule, mini-color, colors and pit-block tables became module constants, shared by the apply code and the detector. |
| 1 | Tier A keys removed from all themes. **All 170 renders identical.** |
| 2 | Tier B keys removed from all themes. **All 170 renders identical.** |
| 3 | The 6 inert `REQUIRED_KEYS` entries, their theme values, and the dead-token rules were removed. The 11 SAMPLE rules that never fired were deleted or folded into working mechanisms. **All 170 renders identical**, except `blockplan_SAMPLE.svg`, which now shows the lane colors SAMPLE always intended. |
| 4 | USER_GUIDE key table pruned from 328 to 263 rows, and the dead mapping `compact_plan.notes_text.font_size` and its field removed. `DefaultRendererValues.md` regenerated with no change. |

**Deviations from the plan, found during verification**

- **`timeline.marker_stroke_color` and `marker_stroke_width` are live, so they were kept.** The catalog binds `ec-milestone-marker` as an icon, but the timeline asks `get_box_style()` for it. The lookup misses and falls through to the config-field fallback. Removing the color changed 5 timeline renders. A kind-aware recheck of every Tier B field then found only these two keys.
- **`time_bands.dow_2` was removed from default.yaml only.** TJX references its own `dow_2`.
- **`excelblockplan.band_fonts` was never read anywhere.** It was documented in 4 places in USER_GUIDE and emitted by `tools/migrate_theme.py`. The docs now use per-placement `excel_font_name` / `excel_font_size`, which `visualizers/excelblockplan.py` does read.
- **`tools/migrate_theme.py` stopped emitting dead content:**
  - `base.size_rule` / `font_size` stay in `base` instead of becoming `text:base` rules.
  - Lane visuals stay on `blockplan.swimlanes[]` instead of becoming `select: {swimlane}` rules; only `match:` becomes a lane-routing rule.
  - Excel band fonts stay on the placement entry.
- **USER_GUIDE lane docs rewritten.** "`swimlanes` — Blockplan Lane Definitions" now documents the per-lane keys the renderer reads. The `text:milestone_label` / `box:swimlane_*` references and the obsolete "required keys with no visible effect" caveat were removed.
- **Pre-existing, not changed:** `default.yaml` fails `validate_theme.py` for `blockplan.swimlanes`. The lanes were commented out in `7f31ba0b` (default theme layout tuning), and the frozen pre-edit copy fails the same way.
