# Code-bloat reduction plan

**Status:** proposed (2026-09-26), baseline `339fb0d`
**Goal:** shrink the repository and the code a maintainer has to hold in their
head, without changing rendered output. Every phase must leave
`tools/refcorpus.sh check` byte-identical (modulo `<desc>`) and the test suite
green, unless the phase says otherwise.

This plan follows `docs/archive/CONSOLIDATION_PLAN.md` (July 2026) and the
mostly-finished `docs/SIMPLIFICATION_PLAN.md`. That earlier work already removed
most literal copy-paste. An 8-line sliding-window scan finds very little
duplicated text across files. The bloat that is left falls into three kinds:

1. **Repository weight**: generated output, duplicate files and unused fonts
   committed to the tree.
2. **Parallel implementations**: the same algorithm written twice, once per
   orientation or visualizer, with small differences.
3. **Parallel styling paths**: four ways to style one element, each with its
   own config fields, mapping table and fallback code.

---

## Baseline measurements

| Area | Size | Notes |
|---|---|---|
| Tracked files (excl. `fonts/`) | 45.5 MB | 40.9 MB of this is six `_sh_*.svg` files at the repo root |
| `fonts/` | 76 MB, 135 files | 106 files (67 MB) are not named by any theme, code or test |
| Python (app + tools + tests) | 75,078 lines | tests 26,487 |
| `visualizers/timeline/renderer.py` | 4,338 lines | 10 horizontal/vertical method pairs, 1,820 lines between them |
| `CalendarConfig` | 601 fields | 306 are style fields (font/color/size/opacity/stroke) |
| `THEME_TO_CONFIG_MAP` | 420 entries | YAML key → flat config field |
| Shipped themes | 9,269 YAML lines | about 60% of each theme's values are copied verbatim from `default.yaml` |
| Test coverage | 85% overall | 50 tests fail on a fresh clone because `calendar.db` is not tracked |

---

## Phase 0: Repository hygiene (no code changes, about 1 day)

Low risk and a large payoff. Do this first.

> **Status (2026-09-26):** 0.1–0.4 done. `retire-ui-frontends.md` was moved to
> `docs/archive/` rather than deleted, because `docs/archive/UI_FRONTENDS.md`
> cites it as its source. 0.5 and 0.6 are still open and need an owner's decision.

| # | Action | Saves |
|---|---|---|
| 0.1 | Delete the six root `_sh_*.svg` reference sheets. They are output of the `*sheet` subcommands, and `_sh_icon.svg` is byte-identical to `_sh_iconsheet.svg`. Add `/_sh_*.svg` to `.gitignore`. | 40.9 MB |
| 0.2 | Delete `calendar.db.sql`, which is byte-identical to `db utils/create.calendar.db.sql`. | 135 lines |
| 0.3 | Move `db utils/` to `tools/db/`. The space in the name forces quoting everywhere and breaks `xargs`/`git ls-files` pipelines. | — |
| 0.4 | Delete completed plans: `.claude/plans/retire-ui-frontends.md` (done 2026-09-18), `iridescent-conjuring-comet.md` (`_r()` is in `svg_base.py`) and `uv-check-cleanup.md` (ruff is now clean). Move `docs/SIMPLIFICATION_PLAN.md` (Parts 1–2 done, Part 3 marked stale), `docs/design_unified_style_rules.html` (171 KB design record for work that has shipped) and `docs/GoPort.HTML` into `docs/archive/`. | 3 files, 2 docs out of the working set |
| 0.5 | Move the 106 unreferenced fonts (67 MB) out of the main tree, either into a separate optional font-pack repository or into Git LFS. Keep only the fonts that `Fonts`, themes and tests name. `_build_font_registry()` already scans the folder, so an extra font directory only needs a search path (`ECAL_FONT_DIRS`). **Also do a licence review:** `AmericanTypewriter`, `VAGRounded`, `OfficinaSans/Serif`, `LetterGothic`, `NewsGothic`, `SilvermoonITC` and `Orator` are normally commercial faces and probably should not be redistributed. | up to 67 MB |
| 0.6 | Optional: the clone is shallow here, but the SVGs and fonts are also in history. If clone size matters, run `git filter-repo` once, coordinated with every clone owner. | history |

**Verification:** the test suite, and `deploy_copy.sh` into a scratch folder followed by `uv run python ecalendar.py weekly`.

---

## Phase 1: Dead code (about 0.5 day)

> **Status (2026-09-26):** done, apart from the vulture gate (see the last bullet).
> Everything in the table was removed; the test-only items went with the tests
> that only exercised them, and `_boxes_overlap` moved into `tests/test_timeline.py`
> as a local helper. Removed in the same pass: `day_names` (also unused), the
> duplicate `ICON_SETS` and the unused `ICON_SET_NAMES` in
> `visualizers/mini_icon/renderer.py`, and the unused `side_config`
> parameter of `PITRenderer._draw_callout_groups`.

Each item below was flagged by `vulture` and then confirmed with `git grep`. None has a caller in app code.

| Symbol | Location | Referenced by |
|---|---|---|
| `weekend_style_starts_monday`, `_has_half_weekends`, `_includes_weekends` | `config/config.py:2408-2422` | nothing |
| `create_sample_blockplan_swimlanes_from_wbs` | `config/config.py:1818` | tests only |
| `INCH_TO_CM`, `CM_TO_INCH`, `MM_TO_INCH`, `INCH_TO_PT`, `CM_TO_PT`, `MM_TO_PT` | `config/config.py:1889` | nothing (`_UNIT_TO_PT` is used instead) |
| `month_names`, `month_short` | `config/config.py:1899` | nothing (arrow and `calendar` provide these) |
| `CatalogEntry.token_ref` | `config/element_catalog.py:44` | nothing |
| `UnifiedTheme.has_section`, `route_lane` | `config/unified_theme.py:213,258` | `route_lane` by tests only |
| `make_log_fn` | `importers/common.py:77` | nothing |
| `get_pattern_svg`, `get_paper_size_names` | `shared/db_access.py:673-690` | the second by tests only |
| `_same_row_overlap` | `shared/labella_layout.py:533` | nothing |
| `_should_include_event` | `visualizers/base.py:398` | nothing (a back-compat shim over `filter_events`) |
| `VisualizerFactory.register` | `visualizers/factory.py:53` | nothing |
| `_label_icon_size`, `_label_icon_gap`, unused import `_partition_for_both` | `visualizers/pit/labella_adapter.py` | nothing |
| `_draw_icon_marker`, `MarkerSpec.is_icon` | `visualizers/pit/markers.py` | tests only |
| `_marker_attr_pair` | `visualizers/pit/renderer.py:306` | nothing |
| `_boxes_overlap` | `visualizers/timeline/renderer.py:1345` | tests only |

Also:

- Replace the six hand-typed icon-name lists in `config/config.py:1936-2166`
  (`squares`, `circles`, …, `darksquircle-1..31`: about 230 lines) with
  one comprehension: `ICON_SETS = {name: [f"{prefix}-{n}" for n in range(1, 32)] …}`.
- Add `uvx vulture --min-confidence 80` to the pre-commit hook with a
  whitelist file for dataclass fields and argparse callbacks, so dead
  code is caught when it is created.
  **Not adopted.** vulture matches names across the whole program, so at 80%
  it misses an unused import whenever the same name is used in another file,
  and adds almost nothing beyond ruff's F401/F841. At 60% it reports about 150
  false positives on `CalendarConfig` fields that the theme engine sets by
  name. Ruff's `ARG` rules check per file but report 270 findings, mostly
  override signatures. Periodic manual sweeps
  (`uvx vulture --min-confidence 60 . --exclude vendor,.venv`) remain useful.

About 450 lines saved.

---

## Phase 2: Collapse parallel implementations (about 2 weeks, highest leverage)

Order these by payoff and risk. Land each as its own PR and check each with the refcorpus.

### 2.1 Timeline horizontal/vertical twins (saves about 800 lines)

Ten methods in `visualizers/timeline/renderer.py` exist twice, as `X` and
`X_vertical`: `_layout_durations`, `_draw_duration`,
`_draw_duration_contents`, `_draw_duration_connectors`,
`_draw_axis_ticks_from_band`, `_draw_month_ticks`, `_draw_fiscal_bands`,
`_draw_timeline_bands`, `_draw_holiday_icons` and `_draw_today_marker`.
Together they come to 880 + 940 lines. The vertical copies differ by an x↔y
swap and a sign.

- Add an `AxisFrame` to `shared/orientation.py` holding `along(day)`,
  `across(offset)`, `rect(along0, along1, across0, across1)` and
  `text_anchor(side)`. It is built once per render from `Orientation`.
- Rewrite each pair as one method that calls the frame. Delete the
  `_vertical` variants one pair at a time, starting with the simplest
  (`_draw_duration_connectors`, `_draw_month_ticks`), and run the refcorpus
  after each one.
- Split the 480-line `_render_content` into `layout → bands → durations →
  callouts → chrome` steps. This makes it possible to split the file into
  `timeline/{bands,durations,callouts}.py`.

### 2.2 Plan-family time bands and non-workday fills (saves about 250 lines)

`blockplan/renderer.py` and `compactplan/renderer.py` both define
`_build_segments`, `_band_row_h`, `_nwd_fill_for_classes`,
`_nwd_fill_opacity_for_classes` and `_nwd_icon_for_classes`. The
blockplan copies add band-level `fill_rules`. `excelblockplan.py` already
imports `BlockPlanRenderer` and `_BandSegment` to reuse some of this.
Move the superset into `shared/timeband.py`, which already exists, and
make `excelblockplan` import from there rather than from another renderer.

### 2.3 Identical layouts (saves about 200 lines)

`blockplan`, `compactplan`, `timeline` and `pit` `layout.py` differ only in
the name of the content-area key (`"BlockPlanArea"`, `"TimelineArea"`, …).
Give `BaseLayout` a default `calculate()` that takes an `area_key` class
attribute, and delete the four subclasses' bodies, or the files entirely
(see 2.4).

### 2.4 Visualizer registration boilerplate (saves about 250 lines, 10 files)

Each `visualizers/<name>/visualizer.py` is a 30-line class that returns a
name, a list of options, a layout and a renderer, and each `__init__.py`
re-exports it. Replace them with one declarative table in
`visualizers/factory.py`:

```python
VISUALIZERS = {
    "blockplan": Spec(BlockPlanLayout, BlockPlanRenderer, options=[...]),
    ...
}
```

Keep a subclass only where a visualizer overrides behaviour
(`validate_config`, mini/text-mini pagination).

### 2.5 Importer CLIs (saves about 200 lines)

`import_events.py` and `import_specialdays.py` each carry their own
`setup_logging`, `log` and `normalize_row`, and a `main()` (387 and 240
lines) whose argparse block and list/remove/import loop are the same apart
from help strings. `importers/common.py` has a third `setup_logging`.
Move the shared parser and the loop into `common.run_importer(spec)`, so each
importer declares only its extra flags and `transform_row`.

### 2.6 Labella adapters (saves about 100 lines)

`pit/labella_adapter.py` and `timeline/labella_adapter.py` (593 lines
combined) both wrap `shared/labella_layout.py` and both partition by
`Side`. Move the partition, label-size measurement and node construction
into `shared/labella_layout.py`, and keep only the per-view item → node
mapping in each adapter.

---

## Phase 3: Single styling path (about 3–4 weeks, largest structural win)

`docs/architecture/theme-resolution.md` documents a four-level precedence
chain at every draw site:

1. per-item rule
2. token (`style_rules`)
3. element style (`element_catalog` plus `element_overrides`)
4. legacy flat `CalendarConfig` field or module default

Each level has its own data and code:

- **Level 4:** 306 style fields on `CalendarConfig`, 420 entries in
  `THEME_TO_CONFIG_MAP`, `_fallback_{text,box,line,icon}_style`
  (`config.py:1672-1812`), `setfontsizes()` and
  `_inject_heuristic_size_tokens()`, which writes level-4 values back into
  level 2.
- **Level 3:** `element_catalog.yaml`, `element_catalog_defaults.yaml`,
  `_apply_catalog_defaults`.
- **Level 2:** `UnifiedTheme`, the token cache in `svg_base`.

Target: tokens are the only styling source. Built-in defaults become a
`style_rules` block in `element_catalog_defaults.yaml` instead of Python
dataclass defaults.

Steps (each one a PR checked with the refcorpus):

1. **Inventory.** Extend `tools/generate_default_renderer_values.py` to emit,
   for each of the 306 style fields, the token that supersedes it (or
   "none"). Fields with a token are mechanical to remove; fields without one
   get a token first.
2. **Move defaults into data.** Move `Fonts.*` and hard-coded colours/sizes
   from `CalendarConfig` into the defaults YAML as token definitions.
3. **Migrate one visualizer at a time.** Suggested order: text-mini, mini,
   candybar, weekly, then the plan family. Switch its draw sites to `_tk()`
   or `get_*_style()`, then delete the fields it no longer reads, their
   `THEME_TO_CONFIG_MAP` rows and their fallback branches.
4. **Retire the font-size heuristic write-back.** Once every size is a token,
   `setfontsizes` becomes a single "compute default size from page height"
   token definition.

Expected result: `CalendarConfig` goes down to about 300 fields (geometry,
filters, fiscal, runtime), `THEME_TO_CONFIG_MAP` shrinks to about 100 rows,
`config.py` shrinks by about 1,000 lines and `theme_engine.py` by about 600.
There is also one place to look when asking "why is this text red?"

### 3.5 Theme inheritance (saves about 4,000 YAML lines)

Add `extends: default` to theme YAML, applied as a deep merge before
validation. `style_rules`, `swimlane_rules` and the other
`_WHOLESALE_SECTIONS` should replace, not merge. Then strip every value
that equals the parent's from the other eight shipped themes. Each theme
becomes a short diff that says what makes it distinctive. `SAMPLE.yaml`
keeps its full form as documentation. `tools/validate_theme.py` checks the
merged result.

---

## Phase 4: Retire one-shot migration tooling (about 0.5 day, after a notice period)

`tools/migrate_theme.py` (1,456 lines) and `tools/strip_element_bindings.py`
convert the pre-July theme schema. The runtime already rejects that schema.
All shipped themes are converted, and `tests/test_migration_e2e.py`,
`test_excelblockplan_theme.py` and `test_removed_companion_pages.py` exist
mainly to test the converter.

Follow the precedent set when the TUI and Slint UI were retired:

1. Tag `pre-migrator-retirement`.
2. Delete both tools and their tests.
3. Change the `ThemeError` messages in `theme_engine.py:2145-2220` and
   `unified_theme.py:405-420` to say
   `git checkout pre-migrator-retirement -- tools/migrate_theme.py`.

Saves about 1,900 lines. The "tombstone" tests (`test_removed_*`,
`test_theme_dead_keys`) should be reviewed at the same time. Keep the
assertions that guard against reintroducing removed flags, and drop the ones
that only restate old behaviour.

---

## Phase 5: Developer-experience fixes (about 1 day)

- **Fresh-clone test failures.** 50 tests error because `calendar.db` is
  gitignored and nothing builds it. Add a session-scoped pytest fixture that
  builds a minimal database from `tools/db/create.calendar.db.sql` plus a
  small seed (one palette, a few icons and patterns, paper sizes), or mark
  those tests `@pytest.mark.needs_db` and skip them with a clear reason.
- **`docs/DefaultRendererValues.md` churn.** It quotes source line numbers,
  so almost every commit regenerates it, and the pre-commit hook restages it.
  Emit `file:function` instead of `file:line`. The diffs then become
  meaningful and the pre-commit step can go.
- **`.python-version`** pins `cpython-3.14.3-macos-aarch64-none`, so
  `uv sync` fails on Linux and CI. `deploy_copy.sh` already works around
  this. Pin `3.14` instead.
- **`docs/changelog.md`.** Recent entries are single 300–500-word
  paragraphs that repeat the commit bodies. Cap entries at one or two
  sentences and link the commit.

---

## Expected totals

| Phase | Effort | Repo size | Lines removed | Risk |
|---|---|---|---|---|
| 0 Hygiene | 1 d | −41 MB (up to −108 MB with fonts) | ~300 | very low |
| 1 Dead code | 0.5 d | — | ~450 | very low |
| 2 Parallel impls | ~2 wk | — | ~1,800 | medium (refcorpus-guarded) |
| 3 Single styling path + `extends` | 3–4 wk | — | ~1,600 Python + ~4,000 YAML | medium-high |
| 4 Migrator retirement | 0.5 d | — | ~1,900 | low |
| 5 DX fixes | 1 d | — | — (adds a DB fixture) | low |

That is roughly 6,000 Python lines (8% of all Python, and a larger share of
non-test code) and 4,000 YAML lines. The biggest maintainability gains are
2.1 (one timeline code path), 3 (one styling path) and 3.5 (themes that
contain only what is distinctive about them).

## Ground rules for every PR in this plan

- Run `tools/refcorpus.sh render` on the base commit first, then run `check` after the change. Any diff must be explained in the PR.
- Make no behaviour change and no rename in the same PR as a structural move.
- Update `docs/architecture/*.md` in the same PR when a module's role changes.
