# Plan: Clear `uv check` / ruff findings

## Context

Baseline taken 2026-09-13 on `main` @ 67a2747a with uv 0.12.13.

| Check | Result |
|---|---|
| `uv lock --check`, `uv pip check` | Clean — lockfile current, deps compatible |
| `uv run python -m pytest tests/` | **1509 passed** (13.6 s) |
| `uv check` (ty) | **870 diagnostics** — 540 tests, 23 `vendor/`, 307 app code |
| `uvx ruff check .` (no project config) | **1012 findings**, 621 auto-fixable |

The code works; the checks mostly flag loose types. A handful of findings are
real or latent bugs, and those come first. Neither ruff nor ty is configured in
`pyproject.toml`, so results follow whatever defaults the installed tool
version has.

### ty diagnostics by cause

| Cause | ~Count | Where |
|---|---|---|
| Test fakes: configs typed `object`, `_DummyDB`/`_StubDB`/`_HolidayDB`/`_DB` not matching `CalendarDB` | 220 | tests |
| Optional values (`str \| None`, `float \| None`, `_tk(...).get()`) passed to `_draw_text`, `get_font_path`, `float()` | 200 | visualizers, renderers |
| `self._drawing: Drawing \| None` used without narrowing | 30 | `svg_base.py`, `compactplan`, `gantt` |
| `DayAxis.first/last -> date \| None` compared directly | 12 | `gantt/bars.py`, `gantt/renderer.py` |
| Third-party typing gaps (fonttools `ttfont["head"].unitsPerEm`, textual `App` attributes/`Select`) | 25 | `glyph_cache.py`, `tools/`, `tui/` |
| Vendored labella | 23 | `vendor/labella` |
| Real/latent bugs | ~10 | see Phase 1 |

### ruff findings by kind

Mostly mechanical: `UP037` quoted annotations (358), `I001` import order (90),
`UP045` `Optional[]` (38), `F401` unused imports (27 app / 18 tests), `F841`
unused variables (24 app / 4 tests), `BLE001` blind `except Exception` (52,
all app code). `B023` (23, `blockplan/renderer.py:1771`) is a **false
positive**: `_draw_icon_and_text` is called inside the same loop iteration
that defines it.

---

## Phase 0 — Configure the tools (small, do first)

In `pyproject.toml`:

- `[tool.ty.src] exclude = ["vendor", ".claude"]` — drops the 23 vendored findings.
- `[tool.ruff]` with `extend-exclude = ["vendor", ".claude"]` and an explicit
  rule set (e.g. `E`, `F`, `I`, `UP`, `B`, `SIM`, `RUF`) so results don't
  shift when ruff changes its defaults. Leave `BLE`, `DTZ`, `S`, `EXE` off for
  now. Calendar dates are naive on purpose, so `DTZ` would be noise.
- Add `ruff` to the `dev` dependency group so `uv run ruff` is pinned in `uv.lock`.

Re-run both tools and record the new baseline.

**Done 2026-09-13.** `ruff==0.16.7` is in the dev group. E4/E7/E9 are selected
instead of all of `E`, because E501 alone was 459 findings. `allowed-confusables
= ["–", "×"]` removes 83 deliberate en dash and multiplication sign findings;
30 other confusables are still reported. New baseline:

| Check | Result |
|---|---|
| `uv check --locked` | 847 (540 tests, 307 app, 0 vendor) |
| `uv run ruff check .` | 926, 608 auto-fixable |
| pytest | 1509 passed |

## Phase 1 — Real / latent bugs (each with a test)

1. **List `fill` leaks into day styles.** `shared/rule_engine.py:388` keeps a
   list `fill` for every `apply_to` target. The comment there says only
   `vertical_line` sees lists, but that's not true: a `day_box` rule with
   `fill: [red, blue]` returns `['red', 'blue']` (reproduced). That list lands
   in `DayStyle.shade_color` (`visualizers/mini/day_styles.py:398`) and becomes
   the SVG fill string `"['red', 'blue']"`. No shipped theme does this yet.
   Fix: keep lists only for `vertical_line`, and for other targets use the
   first element (or raise `ThemeError` when the theme loads). Tighten
   `StyleResult.fill_color` typing to match.
2. **`CalendarDB.get_connection` has the wrong annotation.**
   `shared/db_access.py:256` says `-> Iterator[Connection]` but returns a
   context manager. That causes the `with` errors in `importers/common.py:446,475`.
   Change it to `AbstractContextManager[sqlite3.Connection]`.
3. **Dead config write.** `config/config.py:2742` sets
   `config.timeline_text_font_size`, which isn't a `CalendarConfig` field, and
   nothing reads it. Delete the line.
4. **`float(None)` risk.** `float(tk.get("size"))` and similar in
   `blockplan/renderer.py`, `mini/renderer.py`, `mini_icon/renderer.py`.
   `_tk()` returns `{}` for unknown tokens (`svg_base.py:95`). Verify whether
   token resolution always supplies `size`, `width` and `opacity`. If not,
   give each call site a default, or have `_tk` return typed defaults.
5. **Fonts without a Unicode cmap.** `renderers/glyph_cache.py:53,132` index
   `getBestCmap()` without handling its `None` return. Guard it and fall back
   to an empty map.
6. **Gantt shared mutable class attribute.** `visualizers/gantt/renderer.py:157`
   declares `_holiday_days: ClassVar[...] = {}` but assigns it per instance at
   :199. Make it a plain instance attribute set in `__init__`.
7. **Small typing bugs:** `importers/common.py:79` `-> callable` should be
   `Callable[[str], None]`. `importers/import_events.py:351` ignores
   `spec is None` / `spec.loader is None`; raise a clear error instead.
8. **Duplicate import.** `visualizers/mini/day_styles.py:20` repeats line 16's
   `from dataclasses import dataclass, field` (F811).
9. **`ecalendar.py:514` `page_opts`.** A `dict(...)` mixing bool and int
   values is passed as `**kwargs`. Pass the keywords directly.

**Done 2026-09-13.** Items 1–3 and 5–9 are fixed. Item 4 is not a bug:
`_inject_heuristic_size_tokens` gives every blockplan text token a `size:`,
and all 10 shipped themes plus the no-theme case resolve one. Fix notes:

- Item 1 is fixed centrally. `_build_style_result(..., keep_fill_list=False)`
  collapses a list to its first non-empty color; `evaluate_band_segment`
  passes `True`. The list guards in `excelblockplan.py` and
  `gantt/renderer.py` went away with it. Gantt bars now take a list fill's
  first color, where before they ignored the rule.
- Tests: `test_rule_engine_fill_lists.py`, `test_glyph_cache.py`, plus one
  each in `test_mini_day_styles.py`, `test_gantt_render.py` and
  `test_import_events_columns.py`. All 7 bug tests failed before the fix.
- Items 2, 3, 7 (annotation), 8 and 9 are type-only; `uv check` confirms them.
- `importers/common.py`, `renderers/glyph_cache.py`, `shared/db_access.py`
  and `visualizers/mini/day_styles.py` are CRLF files. Edit them without
  normalizing line endings, or the diff rewrites every line.

After: pytest 1517 passed; `uv check` 833 (540 tests, 293 app).

## Phase 2 — Mechanical ruff autofix (one commit per rule group)

Use `uv run ruff check --fix` with safe fixes only, grouped so diffs stay reviewable:
`I001`, then `UP037`/`UP045`/`UP006`/`UP035`, then `F401`/`F541`/`RUF100`/`PIE790`.
Remove the 24 app `F841` unused variables by hand, since some may hint at
dropped logic. Suppress `B023` on the blockplan closure, or pass the loop
values as parameters.

Guard: tests pass, and generated SVGs are byte-identical before and after
(render each view × theme to `output/` and `diff -r`).

**Done 2026-09-13.** Five commits (`03ee522a` through the second I001 pass).
Every commit passed the full test suite, `tools/refcorpus.sh check` (40
files identical apart from `<desc>`), and an import of all 116 app modules
plus `ecalendar`. Notes:

- **RUF100 was not applied.** It strips `noqa` comments that still document
  intent: `# noqa: BLE001 - surface any failure in the UI`, and E402 notes
  about imports placed after a `sys.path` fix. It also dropped the `noqa` on
  a deliberate re-export. If you want RUF100, first set
  `lint.external = ["BLE001"]` and keep the explanatory text.
- **F401 has re-exports to watch.** `pit/labella_adapter.py` imports
  `partition_for_both as _partition_for_both` for tests; it now has a `noqa`.
  `text_mini/__init__.py` got an `__all__`. Searching for the bare name
  misses aliases, but pytest collection catches them.
- **F841 was all leftovers,** with no dropped logic. A delete can make an
  earlier variable unused (timeline `start_day`) or match an identical line
  that is still used, so match by line after checking.
- **B023** was fixed by binding the blockplan closure's 9 loop values as
  keyword defaults.
- **The annotation pass unsorts imports.** Moving imports to
  `collections.abc` needed a second I001 pass.
- Ruff preserves CRLF endings; each commit was checked.

After: pytest 1517 passed; `uv check` 832 (540 tests, 292 app); ruff 316,
51 auto-fixable. Remaining top rules: RUF059 unused unpacked variable (54),
RUF012 mutable class default (31), B905 zip without `strict` (30), SIM102
collapsible if (28), RUF001 confusable characters (26), E741 ambiguous
names (13), E402 (10, compactplan's late imports plus one test). None of
these are in Phase 2's scope.

## Phase 3 — App-code typing (target: zero ty errors outside tests)

- `BaseSVGRenderer`: add a `drawing` property that asserts `_drawing is not None`,
  and switch the ~30 `self._drawing.` uses to it.
- `_tk()`: return `Mapping[str, Any]`, or a `TypedDict` of token keys, so
  `.get()` stops producing `Unknown | None`.
- Optional config fields: narrow once where each value is resolved (after
  `theme_* or default` fallbacks), not at every draw call.
- `DayAxis.first/last`: callers already return early on empty axes. Add an
  `assert first is not None` there, or split out a non-empty axis type.
- Third-party gaps (fonttools tables, textual `App` subclass attributes):
  cast to the app's own `App` subclass in `tui/screens`, and put narrow
  `# ty: ignore[unresolved-attribute]` comments on the fonttools lines.

## Phase 4 — Test typing

- Add a `CalendarDataSource` `Protocol` in `shared/db_access.py` covering the
  methods renderers call, and annotate `render()`/`calculate()` with it. The
  test fakes then satisfy it structurally (~130 errors).
- Replace config stand-ins typed as `object` (e.g. in
  `tests/test_pit_visualizer.py`, 209 errors) with a real `CalendarConfig`
  factory or `cast(CalendarConfig, ...)`.
- Remove the 18 unused test imports, and rename the loop variable `date` in
  `tests/test_timeline.py` (F402, it shadows `datetime.date`).

## Phase 5 — Keep it clean

Add `uv check --locked && uv run ruff check . && uv run python -m pytest tests/ -q`
as the pre-commit step (or add it to `commit.sh`), so new code can't regress.

## Order and sizing

| Phase | Effort | Risk |
|---|---|---|
| 0 config | 15 min | none |
| 1 bugs | half day | low, each change comes with a test |
| 2 ruff autofix | 1–2 h | low with the SVG diff guard |
| 3 app typing | 1–2 days | medium: touches every renderer; do one visualizer per commit |
| 4 test typing | half day | low |
| 5 gate | 15 min | none |
