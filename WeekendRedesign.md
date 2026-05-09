# Design: configurable weekend days

## 1. Terminology fix (important)

The user spec says ISO 8601 (Mon=1 … Sun=7, so Sat/Sun = 6, 7). The existing field is documented as "ISO weekday" but actually uses Python's `date.weekday()` (Mon=0 … Sun=6, so Sat/Sun = 5, 6). That mismatch is currently latent because nothing tests the boundary, but it will bite us as soon as the feature is widely used.

**Decision:** standardize on **ISO 8601 (1–7)** at every external surface — CLI, theme YAML, error messages, docs. Keep Python-`weekday()` (0–6) only as an internal implementation detail at the comparison site. Convert at the edges.

- Old internal storage `weekend_days: list[int]` (0–6) → new storage `weekend_days: list[int]` (1–7).
- `get_weekend_days()` returns a `frozenset[int]` of Python-`weekday()` values (0–6) — the *internal* form, named `get_weekend_weekday_set()` to make the convention explicit. Every comparison site uses `d.weekday() in <set>`.
- One conversion happens in `get_weekend_weekday_set()`: `{(iso - 1) % 7 for iso in weekend_days}`.

## 2. Config field

`config/config.py:115`

```python
# ISO 8601 weekday list: 1=Mon .. 7=Sun. Default None means
# "derive from weekend_style" for backward compatibility.
weekend_days: list[int] | None = None
```

`__post_init__` validates: list of ints, each in `1..7`, no duplicates, length 0–7. (Empty list = no weekends, valid.)

## 3. Resolution rules

`CalendarConfig.get_weekend_weekday_set() -> frozenset[int]` (returns 0–6 Python form):

| `weekend_days` | `weekend_style` | result (ISO) | Python form |
|---|---|---|---|
| `[6, 7]` (explicit) | any | Sat, Sun | `{5, 6}` |
| `[]` (explicit empty) | any | none | `{}` |
| `[5, 6]` (Fri/Sat) | any | Fri, Sat | `{4, 5}` |
| `None` | 0 | none | `{}` |
| `None` | 1–4 | Sat, Sun | `{5, 6}` |

So **default is Sat/Sun = ISO 6, 7** as requested, and existing `weekend_style` semantics are preserved when `weekend_days` is unset.

## 4. CLI surface

The flag already exists at `ecalendar.py:495`, but it currently parses 0–6. Change to ISO 1–7 in three places (weekly, blockplan, text-mini parsers) and in `_parse_weekend_days()` at `ecalendar.py:1767`.

```
--weekend-days 6,7         # Sat/Sun (default)
--weekend-days 5,6         # Fri/Sat (Middle East)
--weekend-days 7           # Sun only
--weekend-days ""          # no weekends (empty)
--weekend-days 1,2,3,4,5,6,7   # all 7 (every day a weekend)
```

Help text: `"Comma-separated ISO weekday list (1=Mon..7=Sun) marking non-working days. Defaults to 6,7 (Sat/Sun) when weekends are shown."`

## 5. Theme YAML surface

Add to General Settings, alongside `fiscal:` and `colors:` in every theme:

```yaml
base:
  weekend_days: [6, 7]    # ISO 1=Mon..7=Sun
```

Theme engine mapping (one new line in `_THEME_FIELD_MAP`):

```python
("base", "weekend_days"): "weekend_days",
```

CLI overrides theme (existing precedence, no special handling needed). To explicitly disable in a theme: `weekend_days: []`.

## 6. Visualizer call-site changes

Replace each hard-coded weekend check with `d.weekday() in config.get_weekend_weekday_set()`. Sites:

- `visualizers/blockplan/renderer.py:1931` — `_visible_days()` (currently `weekday() < 5`)
- `visualizers/compactplan/renderer.py:1204` — `_visible_days()` (same)
- `visualizers/excelheader.py:332` — date cursor loop (same)
- `shared/day_classifier.py:34` — already correct, no change
- `visualizers/weekly/` — **see §7 below** (special)
- `visualizers/mini/layout.py:278` — `is_workweek` filter; switch from `weekday() < 5` to the weekend set when `weekend_style == 0`
- `visualizers/text_mini/` — same as mini

To make this robust we add a small helper on `CalendarConfig`:

```python
def is_weekend(self, d: date) -> bool:
    return d.weekday() in self.get_weekend_weekday_set()
```

## 7. Weekly visualizer constraint

The 7-day grid in `visualizers/weekly/layout.py` is built around `weekend_style` (0 = 5-col workweek, 1/3 = 7-col, 2/4 = 5+2 half-cols). It assumes the *layout-level* weekend is always Sat/Sun.

**Decision: keep `weekend_style` as the sole driver of weekly-grid geometry.** `weekend_days` controls only *day classification* (shading, holiday styling, hash patterns, blockplan/compactplan/excelheader visible-day filtering, mini workday filtering). In the weekly view, if a user configures `weekend_days = [5, 6]` (Fri/Sat) with `weekend_style = 2`, the grid still has Sat/Sun in the small columns, but Friday will additionally be classified and shaded as a weekend day. Document this clearly; emit no warning (it's a valid combination).

A future v2 could generalize the weekly grid to arbitrary weekend sets, but that's a separate, much bigger layout change. Out of scope here.

## 8. Date-range adjustment

`shared/date_utils.py:126` hardcodes "Saturday → next Monday" / "Sunday → next Monday" for `weekend_style == 0`. This snaps a user's range to a working day at the **start** of the calendar period. Decision: leave as-is; `weekend_style` still controls range snapping. `weekend_days` is for classification only. (Same rationale as §7.)

## 9. Tests

- `tests/test_weekend_days.py` (new) — covers `get_weekend_weekday_set()` for: default, explicit `[6,7]`, `[5,6]`, `[]`, `[1..7]`, ISO→Python conversion correctness.
- `_parse_weekend_days()` — accepts ISO 1–7, rejects 0 and 8, rejects duplicates, accepts empty string.
- One end-to-end test per affected visualizer asserting that with `weekend_days=[5]` (Fri only), Friday is classified as weekend and Sat/Sun are not.
- Theme-engine test: `base.weekend_days: [5, 6]` round-trips into `config.weekend_days`.

## 10. Migration / back-compat

- Default behavior unchanged (Sat/Sun when weekends shown).
- Existing themes have no `weekend_days` key → no change.
- Existing `--weekend-days` users: **breaking change** from 0–6 to 1–7. The flag was added recently; check `git log` for actual usage. Mitigation: the parser detects a `0` and produces a clear error pointing to the new ISO convention.
- Update `config/config.py:110` docstring and `USER_GUIDE.md` (the docs pass landed in c35a29eb).

## 11. Files touched

| File | Change |
|---|---|
| `config/config.py` | Field doc + ISO range, rename `get_weekend_days` → `get_weekend_weekday_set`, add `is_weekend()`, validation 1–7 |
| `config/theme_engine.py` | Add `("base","weekend_days")` mapping |
| `ecalendar.py` | `_parse_weekend_days` ISO 1–7, help text in 3 parsers |
| `shared/day_classifier.py` | Rename call to `get_weekend_weekday_set` |
| `visualizers/blockplan/renderer.py` | `_visible_days` uses config helper |
| `visualizers/compactplan/renderer.py` | same |
| `visualizers/excelheader.py` | same |
| `visualizers/mini/layout.py` | `is_workweek` filter uses helper |
| `visualizers/text_mini/renderer.py` | same |
| 7× theme YAMLs | optional `base.weekend_days` (omit by default) |
| `tests/test_weekend_days.py` | new |

---

## Open questions before proceeding

1. **ISO convention**: confirmed 1=Mon … 7=Sun (so default `[6, 7]`)? User message said "iso days 6 and 7" which matches ISO 8601 — verify before ripping up the existing 0–6 storage.
2. **Weekly grid scope**: OK to leave the weekly 7-day grid driven by `weekend_style` (i.e. `weekend_days` only changes classification/shading there)? Generalizing the grid to arbitrary weekend sets is a much larger layout rewrite.
3. **Date-range snapping** in `shared/date_utils.py`: same question — leave snapping driven by `weekend_style`?
