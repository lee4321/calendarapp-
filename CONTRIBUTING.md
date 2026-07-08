# Contributing to EventCalendar

A quick orientation for anyone (human or agent) changing this codebase.
The architecture reading order lives in `docs/architecture/README.md`
(built during the 2026-07 consolidation — `docs/archive/CONSOLIDATION_PLAN.md`); this file covers working practices.

## Ground rules

- Python is run with `uv run python …` (never a bare `python`).
- Tests: `uv run python -m pytest tests/ -q` — the whole suite runs in ~10 s;
  run it after every change, not just at the end.
- Rendering regression guard: `tools/refcorpus.sh check` renders all 9
  visualizers × 3 themes and diffs against the baseline in
  `output/_refcorpus/`, ignoring only the `<desc>` metadata block.
  - Pure refactors and comment passes must be **byte-identical**.
  - Deliberate visual changes: inspect the diff, then re-baseline with
    `tools/refcorpus.sh render` in the same commit.
- SVG attribute *order* is significant to the guard: drawsvg emits kwargs in
  call order, so keep kwarg order stable when touching draw helpers.

## Layering

```
vendor/  →  shared/  →  renderers/  →  visualizers/<viz>/  →  cli/ + ecalendar.py
config/ is importable from every layer; imports nothing above shared/.
```

- Visualizers never import each other. Cross-visualizer reuse goes through
  `shared/` or `renderers/` (see `shared/labella_layout.py`,
  `renderers/svg_patterns.py` for the pattern).
- `ecalendar.py` holds only `run()`; argument parsing and config assembly
  live under `cli/`.

## Commenting standards

1. **Module docstring** on every production file: one paragraph — what it
   owns, what it consumes/produces, who calls it.
   (`visualizers/factory.py` and `shared/labella_layout.py` are the models.)
2. **Class docstrings** state the lifecycle: what is populated in `__init__`
   vs per-render, and which methods are the entry points.
3. **Method docstrings** on all public methods and any private method over
   ~20 lines.
4. **"Why" comments** only where the code cannot say it: coordinate-system
   transforms (`_svg_y`, PDF origin bottom-left vs SVG Y-down), token-vs-
   legacy precedence chains, weekend-style quirks, drawsvg API workarounds.
   Never restate what the next line does, and never write comments that
   talk to a reviewer about the change ("now we…", "this was moved from…").
5. Prefer deleting a confusing construct over explaining it — but behavior
   changes never ride along with a comment commit.

## Style-resolution vocabulary (the jargon you meet in hour one)

- **token** — a `"<kind>:<name>"` style bag (`text:day_number`,
  `line:duration_bar`) resolved from theme `style_rules` via
  `UnifiedTheme.resolve_token(token, ctx)`.
- **ctx** — the selector context, e.g. `{"visualizer": "weekly",
  "papersize": "letter"}`. Rules opt in via `select:`.
- **`_tk(token)`** — per-render token cache on `BaseSVGRenderer`; renderers
  declare a `TOKENS` tuple and read `self._tk("…").get("size")`.
- **rule** — a `style_rules` entry with `apply_to:` + `select:` + `style:`;
  content rules (per-day/per-event) are fetched with `find_rules`.
- **element (`ec-*`)** — a CSS-class-like handle bound to a token in
  `config/element_catalog.yaml`; renderers fetch merged styles via
  `config.get_text_style("ec-…")` / `get_box_style` / `get_line_style`.
  Per-theme tweaks go in the theme's top-level `element_overrides:`.
- **nwd** — non-workday (weekends, federal/company holidays);
  `shared/day_classifier.classify_day()` produces the class set.
- **weekend styles 0–4** — 0 workweek-only, 1/2 Sunday-start (2 = half
  weekend boxes), 3/4 Monday-start (4 = half). Use the
  `weekend_style_*()` predicates in `config/config.py`, never raw ints.
- **CoordinateDict** — layout output: element name → `(x, y, w, h)` in PDF
  coordinates (origin bottom-left, Y up); renderers flip with `_svg_y()`.
  Day boxes are keyed by `YYYYMMDD` strings.
- **atfile** — `@file` CLI argument files, one token per line,
  `--flag=value` form (see the `*.txt` presets at the repo root).
