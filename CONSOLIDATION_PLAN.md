# CalendarApp Consolidation & Maintainability Plan

**Goal:** simplify the code, reduce lines of code, and make the codebase easy for a
human developer to learn — through consolidation, deletion, commenting, architecture
drawings, and a refreshed `USER_GUIDE.md`.

**Relationship to other plan docs:**
- `SIMPLIFICATION_PLAN.md` — naming-convention and theme-gap work. Complementary;
  its Parts 1–2 (renames) slot naturally into Phase 3 here. Its Part 3
  (new opacity/background fields, ~96 new config fields) **conflicts** with the
  LOC-reduction goal and should be deferred or re-scoped until this plan lands.
- `RUNTIME_CUTOVER_TODO.md` — the unified-theme migration is **complete** (all
  renderers migrated, decompiler bridge deleted, Phase 4 validation done). This
  plan harvests the cleanup that completion unlocked. The TODO file itself gets
  archived in Phase 1.

---

## Baseline (measured 2026-07-08)

| Area | LOC | Notes |
|---|---:|---|
| `visualizers/` | 17,887 | 9 visualizers + 2 Excel exporters |
| `config/` | 5,754 | config.py **2,596** (573 dataclass fields, 52 `theme_*`), theme_engine.py 1,941 |
| `ecalendar.py` | 4,349 | argparse builder alone is ~1,535 lines |
| `importers/` | 3,886 | three near-clone CLI importers |
| `shared/` | 3,223 | healthy — mostly single-purpose modules |
| `tools/` | 2,886 | ~1,905 of it is finished one-shot theme migration tooling |
| `renderers/` | 1,825 | svg_base.py 1,413 |
| `tui/` + `slint_ui/` | 2,090 | alternative front-ends |
| `vendor/labella` | 1,343 | vendored, leave alone |
| `timescales.py` | 238 | orphan — nothing imports it |
| **Production total** | **~37,400** | excludes tests/vendor |
| `tests/` | 10,829 | safety net: **586 tests, all passing in ~9s** (2026-07-08) |

**Comment density in the big renderers** (comment lines / total):
blockplan 2.6%, weekly 4.0%, timeline 5.6%, svg_base 5.2%. These are the files a
new developer must read first, and they are the least explained.

**Target:** remove ~6,000–8,000 production LOC (16–20%) with zero rendering
changes, then document what remains.

---

## Guardrails (apply to every phase)

1. **Full test suite green** before and after each phase:
   `uv run python -m pytest tests/ -v`.
2. **Reference SVG corpus.** Before any code change, render every visualizer
   (weekly, mini, mini-icon, candybar, text-mini, timeline, blockplan,
   compactplan, pit) × 3 themes (default, dark, corporate) into
   `output/_refcorpus/`. After each phase, re-render and diff — byte-identical
   modulo timestamp/command-line `<desc>` metadata, the same discipline used in
   the runtime cutover. A ~30-line `tools/refcorpus.sh` script makes this one
   command.
3. **One concern per commit.** Deletion commits contain only deletions;
   consolidation commits move code without changing behavior; comment commits
   touch no logic.
4. Excel outputs (`excelheader`, `excelblockplan`) compared via the existing
   completeness probes in `tests/`.

---

## Phase 1 — Delete dead weight (zero behavior risk)

Pure removal. Everything here is unreferenced by the runtime, or a completed
one-shot artifact.

### 1.1 Finished migration tooling  — RESOLVED 2026-07-08 (partial delete)
**Gate outcome:** `tools/migrate_theme.py` and `tools/strip_element_bindings.py`
are **live**, not one-shot: `validate_theme.py` imports `convert_theme`, and
`theme_engine.py` / `unified_theme.py` runtime errors direct users with
old-format themes to run them. External old-format themes are an anticipated
input. They stay, along with `tests/test_migration_e2e.py`.
- [x] Delete `tools/migrate_theme_v1_to_v2.py` (548) — superseded; its
      conversions (hash_rules, swimlanes[].match, vertical_lines) are part of
      `migrate_theme.py`'s pipeline; only its own test referenced it.
- [x] Delete `tests/test_migrate_theme_vertical_lines.py` (126).
- [x] `git tag pre-consolidation` preserves the deleted state.
Actual yield: ~674 LOC (vs ~2,600 planned — the gate did its job).

### 1.2 Orphans and root clutter  (~240 LOC + repo hygiene)
- [ ] Delete `timescales.py` (238 lines, zero importers).
- [ ] Move stray root files out of the repo root: `Candybar.xlsx`,
      `Pyodide_Port.html`, `_completeness_excelheader_*.xlsx`,
      `calendar.db.bak.*`, `move_calendarapp.sh`, generated SVGs at root.
      Destination: `attic/` (gitignored) or plain deletion for the .bak files.
- [ ] Add `.gitignore` entries: `*.bak.*`, `output/`, `_completeness_*.xlsx`.

### 1.3 Archive completed planning docs  (repo-root readability)
The root has ~14 planning/design docs; a newcomer cannot tell which are live.
- [ ] Create `docs/archive/`; move completed docs there:
      `RUNTIME_CUTOVER_TODO.md`, `WeekendRedesign.md`, `RuleRedesign.md`,
      `weekendredesign_plan.html`, `design_unified_style_rules.html`,
      `pit_plan.html`, `Analysis of CalendarApp 21 Mar.txt`,
      `security_recommendation.*`, `textualUI.html`, `REQUIREMENTS.html`.
- [ ] Update `SIMPLIFICATION_PLAN.md`: mark items 24–27 done (already marked),
      strike Part 3 or move it to a `FUTURE_FEATURES.md`.
- [ ] Root ends up with: `README`-level docs only — `USER_GUIDE.md`,
      `ARCHITECTURE.md` (Phase 5), `CONSOLIDATION_PLAN.md`, `changelog.md`,
      the CLI preset `.txt` files (or move those into `presets/`).

**Phase 1 yield: ~2,900 LOC deleted + a repo root a newcomer can navigate.**

---

## Phase 2 — Consolidate duplicated engine code

Measured duplication (same-name, same-purpose functions in multiple files —
see Appendix A for the raw counts).

### 2.1 Importer framework  — DONE 2026-07-08 (~1,675 LOC removed)
**Discovery during execution:** `import_holidays.py` (892) was dead code —
it inserts into a `government` table that no longer exists in calendar.db
and that nothing reads: `CalendarDB.load_python_holidays()` now sources
government holidays in-memory from the `holidays` package. The importer
crashed on `--list` and on import against the shipped DB. Deleted outright
(with its TUI spec entry) rather than refactored; recoverable from the
`pre-consolidation` tag if an external workflow still needs it.

- [x] `importers/common.py` expanded with: `parse_import_pattern`,
      `compute_file_hash`, `determine_file_type`, `read_file`, `find_files`,
      `convert_date`, `process_dates`, `ImportResult`, and a table-
      parameterized `ImportDatabase` base (`ROW_TABLE`/`UNIT_LABEL` +
      `extra_migrations()` hook) plus shared `list_import_history` /
      `remove_import` CLI actions.
- [x] `import_events.py` 1,513 → 1,069; `import_specialdays.py` 992 → 653.
      Each keeps only: column mapping, `transform_row`, `import_file`
      orchestration, CLI `main` (and events' generator-script support).
- [x] CLI entry points unchanged; `tui/importers_spec.py` still works.
- [x] Verified: imports of sample CSVs into scratch DB copies produce
      byte-identical rows and import_history before vs after; only the
      `--list` header was deliberately unified ("Events"/"Days" → "Rows").
- Deferred to a later pass: merging the two `import_file` orchestrations
  and `main()` bodies (different flags/flows; diminishing returns).

### 2.2 Merge the two labella adapters  (~250–350 LOC saved)
`visualizers/pit/labella_adapter.py` (610) and
`visualizers/timeline/labella_adapter.py` (358) share 8 identically-named
helpers (`_resolve_font_path`, `_renderer_node_height`, `_partition_for_both`,
`_node_along_axis_extent`, `_measured_text_width`, `_line_height_extent`,
`_layout_one_side`, `_extra`).
- [ ] Diff the shared helpers; hoist identical ones into
      `shared/labella_adapter.py` (next to the vendored `vendor/labella`).
- [ ] Keep the genuinely different entry points (`layout_callouts` vs
      `layout_pit_callouts`) as thin per-visualizer functions in that module
      or in the visualizer packages.

### 2.3 Hoist SVG pattern-decoration helpers  (~200–300 LOC saved)
`_ensure_svg_pattern_def` exists in 3 renderers; `_colorize_pattern_svg` and
`_parse_svg_tile_size` in 2; plus per-renderer `_pattern_svg_cache` /
`_registered_pattern_ids` reset logic.
- [ ] Create `renderers/svg_patterns.py` (or extend `svg_base.py`) with a
      `PatternRegistry` owning: pattern SVG cache, def deduplication by
      `(name, color)`, colorization, tile-size parsing, per-page reset.
- [ ] All renderers call the one implementation; delete the copies.

### 2.4 Token-cache plumbing into the base renderer  (~100–200 LOC saved)
`_tk()` + `_populate_<viz>_tokens()` + the lazy-populate guard are copied in 4
renderers (weekly, mini, timeline, blockplan) — a pattern the cutover doc
explicitly says "mirrors" across files.
- [ ] Add to `BaseSVGRenderer`: `_tk(token)`, `_populate_tokens(config)`, and a
      class attribute `TOKENS: tuple[str, ...]` each renderer declares.
- [ ] Preserves the Wave-3 lazy-populate fix for test fixtures in one place
      instead of four.

### 2.5 Small shared-helper sweep  (~100–150 LOC saved)
- [ ] `_nwd_icon_for_classes` / `_nwd_fill_for_classes` /
      `_nwd_fill_opacity_for_classes` (duplicated ×2) → `shared/day_classifier.py`.
- [ ] `_draw_circle` (×2) → `svg_base.py` next to `_draw_rect`/`_draw_line`.
- [ ] `_visible_days`, `_build_segments` (×2 each) → compare; hoist if identical.

**Phase 2 yield: ~1,900–2,500 LOC removed, and every future fix lands once
instead of 2–4 times.**

---

## Phase 3 — Slim the giants (structure, not rewrite)

### 3.1 Split `ecalendar.py` (4,349 → ~1,200)
Measured seams (top-level defs):
| Lines | Content | New home |
|---|---|---|
| 225–1760 | `_create_argument_parser` (~1,535 lines) | `cli/args.py` |
| 1801–2185 | config assembly + logging + DB open | `cli/config_assembly.py` |
| 2384–2500 | palette resolution | `config/palette_resolver.py` |
| 2609–2680 | exportdata CSV helpers | `cli/exportdata.py` |
| 2678–3655 | 6 sheet generators (palette/color/font/icon/pattern) | `visualizers/sheets.py` |
| 3655–4349 | `run()` dispatch | stays in `ecalendar.py` |

- [ ] Move, don't rewrite. `ecalendar.py` keeps `run()`, the exceptions, and
      imports — the CLI surface and `uv run python ecalendar.py …` unchanged.
- [ ] The 6 sheet generators share swatch/label helpers — dedupe while moving
      (est. 100–200 LOC).
- [ ] Update `ARCHITECTURE_ecalendar.md` module map (it already documents these
      exact groupings — the split makes the doc's structure physical).

### 3.2 CalendarConfig field audit — BATCH 1 DONE 2026-07-08
Audit script (AST field extraction + whole-tree reference count, with the
`svg_base` dynamic `{prefix}_text`/`{prefix}_font_size` names protected)
found **109 of 566 fields with zero production reads**.

- [x] **Batch 1 stripped (30 fields)** — zero reads *and* zero CLI/test refs:
      all 16 `excelblockplan_*` theme fields (the exporter never read them),
      `header_right_font(_color)`, `footer_left/right_font(_color)` (header/
      footer styling flows from the `heading`/`caption` element-catalog
      tokens, not these fields), `doc_subject`/`doc_keywords` (`<desc>` uses
      only title/author), `candybar_day_color`, `candybar_month_bold`,
      `pit_label_stroke_dasharray`, `theme_pit_event_palette`,
      `theme_pit_milestone_palette`, `timeline_event_axis_padding`.
      Matching THEME_TO_CONFIG_MAP entries and the `_BAND_PLACEMENTS`
      excelblockplan tuple removed.
- [x] **Finding:** all 7 theme YAMLs set `pit.event_palette` /
      `pit.milestone_palette` — those keys were never wired to any renderer
      (silent no-ops). Keys removed from the YAMLs; if per-event/milestone
      pit palettes are wanted, that's a feature to build, not a config key.
- [ ] **Batch 2 (~79 remaining candidates)** need case-by-case review:
      `margin_*`/`include_margin` are FALSE positives (read inside
      `config.resolve_page_margins()`); heuristic size fields are alive via
      `_HEURISTIC_TOKEN_FIELDS`; a few are CLI-written (removing changes CLI
      surface, e.g. `timeline_duration_bar_fill_opacity`); several are
      referenced only by tests. Audit script:
      scratchpad `audit_config_fields.py` (rerunnable).
- [ ] Group surviving fields under section banner comments — fold into the
      Phase 4 commenting pass.
- [ ] Fold in `SIMPLIFICATION_PLAN.md` Part 1 renames *after* Batch 2.

### 3.3 theme_engine.py dead-map audit — DONE 2026-07-08 (clean bill)
- [x] Audited all 358 distinct map targets and every direct `config.<f> =`
      write in theme_engine against the live CalendarConfig fields: **zero
      stale entries** (beyond those removed with Batch 1). Prior cleanup
      waves were thorough.
- [x] `config/required_keys.py` is live — powers `tools/validate_theme.py`
      missing-key errors and migrate_theme. Keeps its keep.
- Net: verification pass; the estimated 200–400 LOC did not exist.

### 3.4 Big renderers — extract only at natural seams
timeline/renderer.py (2,724) and blockplan/renderer.py (2,268) are large but
cohesive. Do **not** force splits. Candidates only if a seam is clean:
- timeline: callout layout/metrics cluster → `timeline/callouts.py`.
- blockplan: swimlane matching/engine cluster → `blockplan/lanes.py`.
- [ ] Decide per-file during Phase 4 commenting (reading them fully anyway).

**Phase 3 yield: ~700–1,100 LOC removed; every remaining file under ~2,700
lines and findable by name.**

---

## Phase 4 — Commenting pass (understanding, not decoration)

Standards (add to `CONTRIBUTING.md`):
1. **Module docstring** on every production file: one paragraph — what it owns,
   what it consumes/produces, who calls it. (The `factory.py` docstring is the
   model.)
2. **Class docstrings** state the lifecycle: what's populated in `__init__` vs
   per-render, and which methods are the entry points.
3. **Method docstrings** on all public methods and any private method >20 lines.
4. **"Why" comments** only where code can't say it: coordinate-system
   transforms (`_svg_y`, PDF-origin math), token-vs-legacy precedence chains,
   weekend-style quirks, drawsvg API workarounds. No "what the next line does"
   comments.
5. **Glossary** in `ARCHITECTURE.md` for the jargon a newcomer hits in hour one:
   token / rule / ctx, `tk`, nwd (non-workday), weekend styles 0–4,
   CoordinateDict, atfile, style bag, lane/band/swimlane, callout, capsule.

Priority order = size × current comment density:
| File | LOC | Density now |
|---|---:|---:|
| `visualizers/blockplan/renderer.py` | 2,268 | 2.6% |
| `visualizers/weekly/renderer.py` | 1,931 | 4.0% |
| `renderers/svg_base.py` | 1,413 | 5.2% |
| `visualizers/timeline/renderer.py` | 2,724 | 5.6% |
| `visualizers/mini/renderer.py` + `day_styles.py` | 1,854 | — |
| `config/theme_engine.py` | 1,941 | 7.9% |
| `shared/rule_engine.py`, `shared/db_access.py` | 1,465 | — |

- [ ] One commit per file/package; zero logic changes (corpus diff must be
      byte-identical, not just modulo-timestamp).
- [ ] Do this **after** Phases 2–3 so comments describe the consolidated code.

---

## Phase 5 — Architecture drawings

Format: **Mermaid inside markdown** — renders on GitHub, diffs as text, never
rots into a stale PNG. Location: `docs/architecture/`, with a root
`ARCHITECTURE.md` as the index (absorb/extend `ARCHITECTURE_ecalendar.md`,
which already covers the CLI layer well).

Drawings to produce:
1. **System overview** (flowchart): CLI args/atfiles → config assembly → theme
   engine (YAML → UnifiedTheme) → CalendarDB (SQLite) → VisualizerFactory →
   layout → renderer → SVG / XLSX / CSV outputs. One page, ~20 nodes max.
2. **Render pipeline sequence** (sequenceDiagram): one `weekly` run end-to-end —
   `run()` → visualizer → layout CoordinateDict → renderer `_render_content` →
   drawsvg. The exemplar every other visualizer maps onto.
3. **Theme resolution** (flowchart): theme YAML sections → tokens/rules →
   `resolve_token` / `find_rules` with ctx → renderer token cache → draw call;
   include the precedence chain (token > legacy field > module default).
4. **Module dependency map** (graph): `visualizers/* → {shared, renderers,
   config}`; makes the layering rule visible ("visualizers never import each
   other; shared imports nothing above it").
5. **Data model** (erDiagram): events / holidays / specialdays / patterns /
   palettes tables → `Event` dataclass → which visualizers consume what.
6. **Per-visualizer one-pagers** (9 short files): layout strategy sketch,
   coordinate conventions, its renderer's method tree — `ARCHITECTURE_ecalendar.md`'s
   call-graph style, ~1 page each, not 640 lines each.
7. **Importer flow** (after Phase 2.1): file → hash/dedup → transform →
   staging → commit, with the ImporterBase hook points.

- [ ] Add a `docs/architecture/README.md` "reading order for new developers":
      overview → pipeline → weekly one-pager → theme resolution → the rest.
- [ ] Draw **after** Phase 3 so the diagrams show the final structure.

---

## Phase 6 — USER_GUIDE.md refresh

The guide is 2,581 lines and structurally good (workflows → option catalog →
per-command reference). Work needed:
- [ ] **Verify every example command runs** against the current CLI — script it:
      extract fenced commands, run each with `--output` pointed at a temp dir,
      fail on non-zero exit. Keep the script as `tools/check_user_guide.py` so
      the guide can't silently rot.
- [ ] **Regenerate the option catalog** from the argparse tree (post Phase 3.1
      split, `cli/args.py` makes this introspectable) — a small generator
      emits the "Command-Line Option Catalog" section; hand-written prose stays.
- [ ] Remove/redirect references to fields stripped in Phase 3.2 and names
      changed by any SIMPLIFICATION_PLAN renames.
- [ ] Add a short **"Theming" chapter** for users: theme YAML anatomy, token
      syntax, `select:` rules, palette references — currently tribal knowledge
      in design docs.
- [ ] Add a 10-line **"For developers"** pointer to `ARCHITECTURE.md` and the
      reading order.

---

## Phase 7 — Final validation & wrap-up

- [ ] Full corpus diff (all 9 visualizers × 3 themes) vs the Phase 0 corpus.
- [ ] Full test suite; update test-count baseline in this doc.
- [ ] LOC re-measure; record actual vs target in the table below.
- [ ] `changelog.md` entry; archive this plan to `docs/archive/` when done.

---

## Sequencing & effort

| Phase | Depends on | Est. effort | Est. LOC removed |
|---|---|---|---:|
| 0. Corpus + baseline | — | 1–2 h | — |
| 1. Delete dead weight | 0 | 2–3 h | ~2,900 |
| 2.1 Importer framework | 0 | 6–8 h | ~1,300 |
| 2.2 Labella merge | 0 | 2–3 h | ~300 |
| 2.3 Pattern registry | 0 | 2–3 h | ~250 |
| 2.4 Token cache hoist | 0 | 2 h | ~150 |
| 2.5 Small helpers | 0 | 1–2 h | ~120 |
| 3.1 ecalendar split | 0 | 3–4 h | ~150 (dedupe) |
| 3.2 Config field audit | 2.4 | 4–6 h | ~400 |
| 3.3 theme_engine audit | 3.2 | 2–3 h | ~300 |
| 3.4 Renderer seams | 4 (reading) | optional | — |
| 4. Commenting pass | 2, 3 | 8–12 h | (adds ~800) |
| 5. Architecture drawings | 3 | 6–8 h | — |
| 6. USER_GUIDE refresh | 3, 5 | 4–6 h | — |
| 7. Final validation | all | 1–2 h | — |
| **Total** | | **~45–65 h** | **~5,900–6,900 net** |

Phases 1, 2.x, and 3.1 are independent of each other and can each land as a
standalone PR. Docs (4–6) come last by design: they describe the destination,
not the journey.

---

## Appendix A — Measured duplication evidence (2026-07-08)

Same-name method definitions across visualizer renderers:
```
6× _render_content        (legitimate — base-class override)
4× _tk                    (copy — Phase 2.4)
3× _ensure_svg_pattern_def(copy — Phase 2.3)
2× _parse_svg_tile_size   (copy — Phase 2.3)
2× _colorize_pattern_svg  (copy — Phase 2.3)
2× _nwd_icon_for_classes  (copy — Phase 2.5)
2× _nwd_fill_for_classes  (copy — Phase 2.5)
2× _nwd_fill_opacity_for_classes (copy — Phase 2.5)
2× _draw_circle           (copy — Phase 2.5)
2× _visible_days          (verify — Phase 2.5)
2× _build_segments        (verify — Phase 2.5)
```

Function names appearing in all 3 importers (25 total at 3×, 8 more at 2×):
`transform_row, transaction, setup_logging, read_file, process_dates, main,
log, import_file, get_next_import_id, find_files, determine_file_type,
delete_import_record, create_import_record, convert_date, compute_file_hash,
check_duplicate, _migrate_schema, __init__` (×3);
`remove_import, parse_import_pattern, normalize_row, list_imports,
list_import_history, get_max_import_id, get_import_by_id, delete_by_import_id` (×2).

Labella adapter helpers duplicated between `pit/` and `timeline/`:
`_resolve_font_path, _renderer_node_height, _partition_for_both,
_node_along_axis_extent, _measured_text_width, _line_height_extent,
_layout_one_side, _extra`.
