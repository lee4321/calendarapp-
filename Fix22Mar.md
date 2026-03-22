# Plan: CLI Option Cleanup — Remove Silently-Ignored Arguments

## Context

The analysis (Analysis of CalendarApp 21 Mar.txt) identified CLI options exposed on views that never honor them. Users who pass `--shade` to `timeline` or `--monthnames` to `blockplan` get no error and no effect — silent garbage in, garbage out. The goal is to make argparse itself enforce the boundary: unsupported options produce an error, not silence.

Key confirmed facts from code review:
- `--weeknumbers` is **already** weekly-specific (line 738) — no action needed
- `--shade` is honored by weekly, mini, AND mini-icon (which inherits `MiniCalendarRenderer`)
- `text_mini` uses `config.includeevents` (checked at renderer.py:75) but not `includedurations`
- `text_mini` benefits from base-class `_filter_events` (ignorecomplete, milestones, rollups, WBS)
- All config-wiring uses `getattr(args, field, default)`, so removing an arg from a parser won't break wiring for other parsers

---

## Changes

### 1. `ecalendar.py` — Output loop (line 528): exclude `text_mini`

**Current:** `for view_parser in (weekly, mini, mini_icon, text_mini, timeline, blockplan, compactplan):`

**Change to:** `for view_parser in (weekly, mini, mini_icon, timeline, blockplan, compactplan):`

Then add a `text_mini`-specific output group immediately after (just the two options it actually uses):
```python
text_mini_out = text_mini.add_argument_group("Output Options")
text_mini_out.add_argument("--outputfile", "-of", ...)
text_mini_out.add_argument("--theme", "-th", ...)
```

### 2. `ecalendar.py` — Layout/content loop (line 571): exclude `text_mini`

**Current:** `for view_parser in (weekly, mini, mini_icon, text_mini, timeline, blockplan, compactplan):`

**Change to:** `for view_parser in (weekly, mini, mini_icon, timeline, blockplan, compactplan):`

Then add a `text_mini`-specific section covering the subset of options it honors:
- Layout: `--weekends`
- Content: `--empty`, `--noevents`, `--ignorecomplete`, `--milestones`, `--rollups`, `--WBS`, `--country`

**Not** added for text-mini: `--margin`, `--header`, `--footer`, `--monthnames`, `--monthnumbers`, header/footer text, watermark/imagemark, `--shade`, `--nodurations`, `--includenotes`, `--overflow`

### 3. `ecalendar.py` — Move `--shade` out of the shared content group

Remove from the content_group block inside the big loop. Add a new targeted loop after the content group:
```python
for view_parser in (weekly, mini, mini_icon):
    view_parser.add_argument("--shade", "-sh", action="store_true", help="Shade current date")
```

### 4. `ecalendar.py` — Move `--monthnames` / `--monthnumbers` to weekly-specific

Remove from the layout_group block inside the big loop. Add both to the weekly-specific block (around line 737–762):
```python
weekly.add_argument("--monthnames", "-mn", ...)
weekly.add_argument("--monthnumbers", "-mu", ...)
```

### 5. `ecalendar.py` — Move `--overflow` to weekly-specific

Remove from the content_group block inside the big loop. Add to the weekly-specific block:
```python
weekly.add_argument("--overflow", "-x", ...)
```

### 6. Remove `supported_options` dead code

Remove the property definition and all overrides from:
- `visualizers/base.py` (base definition, lines ~209–223)
- `visualizers/weekly/visualizer.py`
- `visualizers/mini/visualizer.py`
- `visualizers/mini_icon/visualizer.py`
- `visualizers/text_mini/visualizer.py`
- `visualizers/timeline/visualizer.py`
- `visualizers/blockplan/visualizer.py`
- `visualizers/compactplan/visualizer.py`

---

## Files Modified

| File | Change |
|------|--------|
| `ecalendar.py` | Restructure 2 loops; move 4 args; add text-mini-specific groups |
| `visualizers/base.py` | Remove `supported_options` property |
| `visualizers/weekly/visualizer.py` | Remove `supported_options` override |
| `visualizers/mini/visualizer.py` | Remove `supported_options` override |
| `visualizers/mini_icon/visualizer.py` | Remove `supported_options` override |
| `visualizers/text_mini/visualizer.py` | Remove `supported_options` override |
| `visualizers/timeline/visualizer.py` | Remove `supported_options` override |
| `visualizers/blockplan/visualizer.py` | Remove `supported_options` override |
| `visualizers/compactplan/visualizer.py` | Remove `supported_options` override |

---

## Verification

1. `uv run python ecalendar.py timeline --shade` → argparse error (not silent ignore)
2. `uv run python ecalendar.py blockplan --monthnames` → argparse error
3. `uv run python ecalendar.py mini --overflow` → argparse error
4. `uv run python ecalendar.py text-mini --papersize A4` → argparse error
5. `uv run python ecalendar.py weekly --shade --monthnames --overflow` → still works (these are now weekly-only, and that's fine)
6. `uv run python ecalendar.py text-mini --weekends 1 --noevents --country US` → still works
7. `uv run python -m pytest tests/ -v` → all tests pass
