# CalendarApp Codebase Simplification Plan

## Overview

This plan addresses three areas of improvement:
1. **Naming inconsistencies** across visualizers and config fields
2. **Theme file and CLI preset gaps** vs. available configuration options
3. **Text decoration gaps** where theme control is incomplete

---

## Part 1: Naming Inconsistency Reconciliation

### 1.1 Font Field Naming

**Problem:** Three conventions coexist for font references.

| Current Pattern | Where Used | Proposed Standard |
|---|---|---|
| `event_text_font` | Weekly events/durations | `event_font` |
| `blockplan_event_font` | Blockplan events | `blockplan_event_font` (already correct) |
| `excelheader_font_name` | Excel export | `excelheader_font` |

**Steps:**
1. Rename `event_text_font` -> `event_font` in `CalendarConfig`
2. Rename `duration_text_font` -> `duration_font` in `CalendarConfig`
3. Rename `excelheader_font_name` -> `excelheader_font` in `CalendarConfig`
4. Add `__post_init__` deprecation aliases for old names (one release cycle)
5. Update all renderer references (weekly/renderer.py, timeline/renderer.py)
6. Update theme_engine.py mappings
7. Update SAMPLE.yaml and all 7 theme YAML files
8. Update CLI argparse if any of these are CLI-exposed

### 1.2 Color Field Naming

**Problem:** Text colors use three incompatible suffixes: `_font_color`, `_text_color`, `_color`.

| Current | Where Used | Proposed Standard |
|---|---|---|
| `header_left_font_color` | Header/footer (6 fields) | Keep `_font_color` for header/footer |
| `event_text_color` | Weekly events | `event_color` |
| `duration_text_color` | Weekly durations | `duration_color` |
| `mini_title_color` | Mini calendar | `mini_title_color` (keep) |
| `timeline_event_text_color` | Timeline events | `timeline_event_color` |
| `timeline_duration_text_color` | Timeline durations | `timeline_duration_color` |
| `blockplan_duration_text_color` | Blockplan (redundant with `blockplan_duration_color`) | Remove; keep `blockplan_duration_color` |
| `day_box_font_color` | Weekly day box | `day_box_color` |

**Convention to adopt:**
- `*_font_color` for header/footer/day-names/week-numbers (elements where "font" is the primary concept)
- `*_color` for content items (events, durations, titles, labels) — drop `text_` and `font_` qualifiers
- `*_notes_color` for notes text (already consistent)

**Steps:**
1. Rename `event_text_color` -> `event_color`, `duration_text_color` -> `duration_color` in CalendarConfig
2. Rename `timeline_event_text_color` -> `timeline_event_color`, `timeline_duration_text_color` -> `timeline_duration_color`
3. Remove `blockplan_duration_text_color` (duplicate of `blockplan_duration_color`)
4. Rename `day_box_font_color` -> `day_box_color`
5. Add deprecation aliases in `__post_init__`
6. Update all renderers, theme_engine.py, SAMPLE.yaml, all theme YAMLs

### 1.3 Opacity vs. Alpha

**Problem:** Three fields use `alpha` while 28+ use `opacity` for the same concept.

| Current | Proposed |
|---|---|
| `watermark_alpha` | `watermark_opacity` |
| `theme_federal_holiday_alpha` | `theme_federal_holiday_opacity` |
| `theme_company_holiday_alpha` | `theme_company_holiday_opacity` |

**Steps:**
1. Rename all three fields in CalendarConfig
2. Update theme_engine.py mappings (watermark section, colors.federal_holiday, colors.company_holiday)
3. Update SAMPLE.yaml and all theme YAMLs (`alpha:` -> `opacity:`)
4. Update weekly/renderer.py and mini/renderer.py holiday rendering
5. Add deprecation aliases

### 1.4 Watermark Field Naming

**Problem:** Watermark fields deviate from standard conventions.

| Current | Proposed |
|---|---|
| `watermark` (the text) | `watermark_text` |
| `watermark_size` | `watermark_font_size` |
| `watermark_alpha` | `watermark_opacity` (see 1.3) |
| `imagemark` | `watermark_image` |
| `imagemark_width` | `watermark_image_width` |
| `imagemark_height` | `watermark_image_height` |
| `imagemark_rotation_angle` | `watermark_image_rotation_angle` |

**Steps:**
1. Rename all 7 fields in CalendarConfig
2. Update CLI argparse flags (`--watermark` -> `--watermark-text`, etc.)
3. Update theme_engine.py mappings
4. Update SAMPLE.yaml and all theme YAMLs
5. Update renderers that reference these fields

### 1.5 Background/Fill/Shade Naming

**Problem:** Area backgrounds use three conventions: `fill_color`, `background_color`, `shade`.

**Convention to adopt:**
- `*_background_color` for whole-page/whole-section backgrounds
- `*_fill_color` for cell/box/area fills
- Retire `shade` entirely

| Current | Proposed |
|---|---|
| `mini_nonworkday_shade` | `mini_nonworkday_fill_color` |
| `theme_mini_nonworkday_shade` | `theme_mini_nonworkday_fill_color` |

**Steps:**
1. Rename the 2 shade fields in CalendarConfig
2. Update mini/renderer.py and mini/day_styles.py
3. Update theme_engine.py, SAMPLE.yaml, all theme YAMLs

### 1.6 Theme Override CamelCase Cleanup

**Problem:** Legacy theme override fields lack snake_case.

| Current | Proposed |
|---|---|
| ~~`theme_specialdaycolor`~~ | `theme_special_day_color` |
| ~~`theme_hashlinecolor`~~ | `theme_hash_line_color` |
| ~~`theme_fiscalperiodcolors`~~ | `theme_fiscal_period_colors` |
| ~~`theme_monthcolors`~~ | `theme_month_colors` |

**Steps:**
1. Rename all 4 fields in CalendarConfig
2. Update all renderers referencing these fields
3. Update theme_engine.py color mappings
4. Add deprecation aliases

### 1.7 Event/Duration Font Size Naming

**Problem:** Font size fields use inconsistent qualifiers.

| Current | Proposed |
|---|---|
| `event_text_font_size` | `event_font_size` |
| `event_icon_font_size` | `event_icon_size` |
| `timeline_event_name_font_size` | `timeline_event_font_size` |
| `timeline_event_notes_font_size` | `timeline_event_notes_font_size` (keep) |
| `timeline_duration_name_font_size` | `timeline_duration_font_size` |
| `timeline_duration_notes_font_size` | `timeline_duration_notes_font_size` (keep) |

**Steps:**
1. Rename fields in CalendarConfig
2. Update theme_engine.py mappings
3. Update all renderers

### 1.8 Stroke vs. Line Naming

**Problem:** `mini_grid_line_color` combines both `line_` and `stroke_`, while other fields use one or the other.

**Convention to adopt:**
- `*_line_*` for visual line elements (grid lines, axis lines, today line, timeband dividers)
- `*_stroke_*` for SVG stroke properties on shapes (boxes, bars, circles, duration bars)
- Never combine both (`grid_line_color` -> `grid_line_color`)

**Steps:**
1. Rename mini grid line fields: `mini_grid_line_color` -> `mini_grid_line_color`, etc.
2. Rename other combined fields similarly
3. Update mini/renderer.py, theme_engine.py, SAMPLE.yaml, all theme YAMLs

---

## Part 2: Theme File and CLI Preset Updates

### 2.1 Update SAMPLE.yaml to Be Complete Reference

**Fields missing from SAMPLE.yaml that should be added:**

**In `base:` section:**
- `default_missing_icon` (already present in some themes)

**In `layout:` section (new or expand):**
- `margin_top`, `margin_bottom`, `margin_left`, `margin_right` (as percentage fields)
- `header_percent`, `footer_percent`, `day_name_percent`, `week_number_percent`, `month_percent`, `color_key_percent`

**In `header:` / `footer:` sections:**
- `font_size` for each of left/center/right (currently only font_family and font_color)

**In `events:` / `durations:` sections:**
- `font_size` (event_text_font_size / duration uses same)
- `icon_font_size` (event_icon_font_size)
- `notes_font_size` (currently auto-scaled at 90%)

**In `weekly:` section:**
- `day_box.number_font_size` (day_box_number_font_size)
- `day_box.icon_font_size` (day_box_icon_font_size)
- `day_names.font_size` (day_name_font_size)
- `week_numbers.font_size` (week_number_font_size)

**In `colors:` section:**
- `mini_calendar.current_day_color` (mini_current_day_color)

**In `fiscal:` section:**
- `period_label_font` (fiscal_period_label_font)
- `period_label_font_size` (fiscal_period_label_font_size)
- `period_label_color` (fiscal_period_label_color)

**In `mini_calendar:` section:**
- `duration_bar_height` (mini_duration_bar_height)
- `duration_bar_stroke_opacity` (mini_duration_bar_stroke_opacity)
- `show_adjacent` (mini_show_adjacent)
- `circle_milestones` (mini_circle_milestones)

**Steps:**
1. Add all missing fields to SAMPLE.yaml with descriptive comments
2. Group them logically within existing sections per the current structure
3. Ensure every field has a comment explaining its purpose and valid values

### 2.2 Update All 7 Theme YAMLs

After SAMPLE.yaml is updated, each theme file should be reviewed for completeness. Not every theme needs every field (they inherit defaults), but key visual fields should be present.

**Steps:**
1. For each theme (default, corporate, dark, vibrant, Julia, leemini, accent):
   - Compare against updated SAMPLE.yaml
   - Add any missing fields that the theme actively needs to customize
   - Ensure section ordering matches SAMPLE.yaml
2. Validate all themes load correctly via `uv run python -m pytest tests/ -v`

### 2.3 Update CLI Preset .txt Files

Each preset file should document ALL relevant flags for its visualizer type, even if commented out.

**weekly.txt additions needed:**
- `# --fiscal TYPE` (fiscal calendar type)
- `# --fiscal-show-periods` / `# --fiscal-show-quarters` / `# --fiscal-year-offset`
- `# --color COLOR` (base color override)

**mini.txt additions needed:**
- `# --fiscal TYPE` / `# --fiscal-colors`
- `# --header LEFT` / `# --headercenter` / `# --headerright`
- `# --footer LEFT` / `# --footercenter` / `# --footerright`
- `# --noevents` / `# --nodurations` / `# --milestones` / `# --rollups`
- `# --includenotes` / `# --ignorecomplete`
- `# --mini-details`

**timeline.txt additions needed:**
- `# --fiscal TYPE` / `# --fiscal-colors`
- `# --fiscal-show-periods` / `# --fiscal-show-quarters`
- `# --weeknumbers` / `# --week-number-mode` / `# --week1-start`

**text-mini.txt additions needed:**
- `# --fiscal TYPE` / `# --fiscal-colors`
- `# --today-line-direction` / `# --today-line-length`

**Steps:**
1. For each .txt file, add commented-out lines for all missing flags
2. Group flags logically matching the SAMPLE.yaml section order:
   - Date range / page layout
   - Content filtering (events, durations, milestones)
   - Visual style (theme, color, weekend style)
   - Fiscal calendar
   - Visualizer-specific options
   - Output
3. Add brief comments explaining each flag's purpose

### 2.4 Add Missing theme_engine.py Mappings

Fields that exist in CalendarConfig and should be theme-configurable but lack THEME_TO_CONFIG_MAP entries:

**Font sizes (add to appropriate sections):**
```python
("header", "left", "font_size"): "header_left_font_size",
("header", "center", "font_size"): "header_center_font_size",
("header", "right", "font_size"): "header_right_font_size",
("footer", "left", "font_size"): "footer_left_font_size",
("footer", "center", "font_size"): "footer_center_font_size",
("footer", "right", "font_size"): "footer_right_font_size",
("weekly", "day_names", "font_size"): "day_name_font_size",
("weekly", "week_numbers", "font_size"): "week_number_font_size",
("weekly", "day_box", "number_font_size"): "day_box_number_font_size",
("weekly", "day_box", "icon_font_size"): "day_box_icon_font_size",
("events", "font_size"): "event_text_font_size",
("events", "icon_font_size"): "event_icon_font_size",
("events", "notes_font_size"): "event_notes_font_size",
("durations", "font_size"): "duration_font_size",
```

**Fiscal label styling:**
```python
("fiscal", "period_label_font"): "fiscal_period_label_font",
("fiscal", "period_label_font_size"): "fiscal_period_label_font_size",
("fiscal", "period_label_color"): "fiscal_period_label_color",
```

**Mini calendar extras:**
```python
("mini_calendar", "duration_bar_height"): "mini_duration_bar_height",
("mini_calendar", "duration_bar_stroke_opacity"): "mini_duration_bar_stroke_opacity",
("mini_calendar", "show_adjacent"): "mini_show_adjacent",
("mini_calendar", "circle_milestones"): "mini_circle_milestones",
("mini_calendar", "current_day_color"): "mini_current_day_color",
```

**Steps:**
1. Add all missing mappings to `THEME_TO_CONFIG_MAP` in theme_engine.py
2. Update `VALID_SECTIONS` if new sections are needed
3. Test with each theme YAML to ensure no mapping errors

---

## Part 3: Text Decoration Gap Resolution

### 3.1 Gap Summary Matrix

Currently, text elements across visualizers support these decoration properties unevenly:

| Property | Weekly | Mini | Timeline | Blockplan | Compactplan |
|---|:---:|:---:|:---:|:---:|:---:|
| font_name | All | All | All | All | All |
| font_size | All | All | All | All | All |
| font_color | All | All | All | All | All |
| background_color | None | None | None | Partial (headers, lanes) | None |
| font_opacity | None | Partial (day numbers only) | None | Partial (headers, bands) | All |
| background_opacity | None | None | None | None | None |

### 3.2 Add Font Opacity Support (Priority 1)

**New config fields to add per visualizer:**

**Weekly (11 fields):**
- `day_box_number_opacity`, `day_box_icon_opacity`, `day_box_font_opacity`
- `event_opacity`, `event_notes_opacity`, `event_icon_opacity`
- `duration_opacity`, `duration_notes_opacity`, `duration_icon_opacity`
- `day_name_font_opacity`, `week_number_font_opacity`

**Header/Footer (6 fields):**
- `header_left_font_opacity`, `header_center_font_opacity`, `header_right_font_opacity`
- `footer_left_font_opacity`, `footer_center_font_opacity`, `footer_right_font_opacity`

**Mini (5 fields):**
- `mini_title_opacity`, `mini_header_opacity`, `mini_day_opacity`
- `mini_week_number_opacity`, `mini_adjacent_month_opacity`

**Timeline (6 fields):**
- `timeline_title_opacity`, `timeline_notes_opacity`, `timeline_date_opacity`
- `timeline_event_opacity`, `timeline_duration_opacity`, `timeline_duration_date_opacity`

**Blockplan (extend existing, add 6 fields):**
- `blockplan_event_opacity`, `blockplan_event_notes_opacity`, `blockplan_event_date_opacity`
- `blockplan_duration_opacity`, `blockplan_duration_notes_opacity`, `blockplan_duration_date_opacity`
- (blockplan header/timeband/lane labels already have opacity)

**Steps:**
1. Add all ~34 new opacity fields to CalendarConfig (default: `1.0`)
2. Add theme_engine.py mappings for each
3. Add to SAMPLE.yaml under appropriate sections
4. Update `_draw_text()` calls in each renderer to pass `fill_opacity` parameter
5. Verify `text_to_svg_group()` in glyph_cache.py supports opacity on `<g>` elements (add if missing)

### 3.3 Add Text Background Color Support (Priority 2)

This requires a rendering change: drawing a filled rectangle behind text before drawing the text glyphs.

**New config fields per text element (pattern: `*_background_color`, `*_background_opacity`):**

**Weekly (8 pairs = 16 fields):**
- `day_box_number_background_color` / `_opacity`
- `event_background_color` / `_opacity`
- `event_notes_background_color` / `_opacity`
- `duration_background_color` / `_opacity`
- `duration_notes_background_color` / `_opacity`
- `day_name_background_color` / `_opacity`
- `week_number_background_color` / `_opacity`
- `fiscal_period_label_background_color` / `_opacity`

**Header/Footer (6 pairs = 12 fields):**
- `header_{left,center,right}_background_color` / `_opacity`
- `footer_{left,center,right}_background_color` / `_opacity`

**Mini (5 pairs = 10 fields):**
- `mini_title_background_color` / `_opacity`
- `mini_header_background_color` / `_opacity`
- `mini_day_background_color` / `_opacity` (distinct from cell fill)
- `mini_week_number_background_color` / `_opacity`
- `mini_details_title_background_color` / `_opacity`

**Timeline (4 pairs = 8 fields):**
- `timeline_title_background_color` / `_opacity`
- `timeline_event_background_color` / `_opacity`
- `timeline_duration_background_color` / `_opacity`
- `timeline_date_background_color` / `_opacity`

**Blockplan (5 pairs = 10 fields):**
- `blockplan_event_background_color` / `_opacity`
- `blockplan_event_notes_background_color` / `_opacity`
- `blockplan_duration_background_color` / `_opacity`
- `blockplan_duration_notes_background_color` / `_opacity`
- `blockplan_band_background_color` / `_opacity`

**Compactplan (3 pairs = 6 fields):**
- `compactplan_milestone_label_background_color` / `_opacity`
- `compactplan_legend_background_color` / `_opacity`
- `compactplan_band_background_color` / `_opacity`

**Implementation steps:**
1. Add ~62 new fields to CalendarConfig (default: `"none"` for color, `1.0` for opacity)
2. Add theme_engine.py mappings
3. Add to SAMPLE.yaml
4. Modify `BaseSVGRenderer._draw_text()` in svg_base.py to accept optional `background_color` and `background_opacity` parameters
5. When background_color is not "none", draw a filled rect (using text bounding box from PIL measurement) before the text glyphs
6. Update each renderer's `_draw_text()` calls to pass through background params from config

### 3.4 Equalize Opacity Support Across Visualizers

**Problem:** Compactplan has opacity on all text; blockplan has it on headers/bands; weekly/mini/timeline have none.

**Steps:**
1. After adding the font opacity fields (3.2), ensure all renderers pass them through
2. Audit each renderer's `_draw_text()` calls to verify opacity is consistently applied
3. Add integration tests that verify opacity values appear in SVG output

---

## Part 4: Implementation Order

### Phase 1: Naming Cleanup (Non-Breaking with Aliases)
1. Add deprecation alias mechanism in `CalendarConfig.__post_init__`
2. Execute renames 1.1 through 1.8
3. Update theme_engine.py to accept both old and new YAML keys
4. Update all 7 theme YAMLs to use new names
5. Run full test suite

### Phase 2: Theme/CLI Completeness
1. Update SAMPLE.yaml (2.1)
2. Add missing theme_engine.py mappings (2.4)
3. Update 7 theme YAMLs (2.2)
4. Update 4 CLI preset .txt files (2.3)
5. Run full test suite

### Phase 3: Font Opacity (New Feature)
1. Add ~34 opacity fields to CalendarConfig (3.2)
2. Add theme_engine.py mappings
3. Modify glyph rendering to support opacity
4. Update each renderer
5. Add to SAMPLE.yaml and relevant theme YAMLs
6. Test with each visualizer type

### Phase 4: Text Background Color (New Feature)
1. Add ~62 background fields to CalendarConfig (3.3)
2. Implement background rect drawing in `_draw_text()` (3.3 step 4-5)
3. Add theme_engine.py mappings
4. Update renderers
5. Add to SAMPLE.yaml
6. Test with each visualizer type

### Phase 5: Cleanup
1. Remove deprecation aliases after one release cycle
2. Final audit of all naming for consistency
3. Update any documentation

---

## Appendix A: Complete Naming Convention Reference

After all changes, the naming convention should be:

| Concept | Convention | Example |
|---|---|---|
| Font family | `*_font` | `event_font`, `blockplan_event_font` |
| Font size | `*_font_size` | `event_font_size`, `mini_title_font_size` |
| Text/content color | `*_color` | `event_color`, `mini_title_color` |
| Font color (header/footer) | `*_font_color` | `header_left_font_color` |
| Notes text | `*_notes_font`, `*_notes_color` | `event_notes_font`, `event_notes_color` |
| Area fill | `*_fill_color`, `*_fill_opacity` | `day_box_fill_color` |
| Page background | `*_background_color` | `timeline_background_color` |
| Text background | `*_background_color`, `*_background_opacity` | `event_background_color` |
| Transparency | `*_opacity` (never `alpha`) | `watermark_opacity` |
| Line elements | `*_line_color`, `*_line_width` | `mini_grid_line_color` |
| Shape strokes | `*_stroke_color`, `*_stroke_width` | `day_box_stroke_color` |
| Dash patterns | `*_stroke_dasharray` or `*_dasharray` | `duration_stroke_dasharray` |
| Displayed text content | `*_text` | `watermark_text`, `header_left_text` |
| Image assets | `watermark_image*` | `watermark_image`, `watermark_image_width` |

## Appendix B: Fields to Rename (Complete List)

| # | Current Name | New Name | Location |
|---|---|---|---|
| 1 | `event_text_font` | `event_font` | config.py, weekly/renderer.py, timeline/renderer.py |
| 2 | `event_text_color` | `event_color` | config.py, weekly/renderer.py, timeline/renderer.py |
| 3 | `event_text_font_size` | `event_font_size` | config.py, weekly/renderer.py |
| 4 | `duration_text_font` | `duration_font` | config.py, weekly/renderer.py, timeline/renderer.py |
| 5 | `duration_text_color` | `duration_color` | config.py, weekly/renderer.py, timeline/renderer.py |
| 6 | `timeline_event_text_color` | `timeline_event_color` | config.py, timeline/renderer.py |
| 7 | `timeline_duration_text_color` | `timeline_duration_color` | config.py, timeline/renderer.py |
| 8 | `timeline_event_name_font_size` | `timeline_event_font_size` | config.py, timeline/renderer.py |
| 9 | `timeline_duration_name_font_size` | `timeline_duration_font_size` | config.py, timeline/renderer.py |
| 10 | `blockplan_duration_text_color` | (remove, use `blockplan_duration_color`) | config.py, blockplan/renderer.py |
| 11 | `day_box_font_color` | `day_box_color` | config.py, weekly/renderer.py |
| 12 | `excelheader_font_name` | `excelheader_font` | config.py, excelheader.py |
| 13 | `watermark` | `watermark_text` | config.py, renderers/svg_base.py |
| 14 | `watermark_size` | `watermark_font_size` | config.py, renderers/svg_base.py |
| 15 | `watermark_alpha` | `watermark_opacity` | config.py, renderers/svg_base.py |
| 16 | `imagemark` | `watermark_image` | config.py, renderers/svg_base.py |
| 17 | `imagemark_width` | `watermark_image_width` | config.py, renderers/svg_base.py |
| 18 | `imagemark_height` | `watermark_image_height` | config.py, renderers/svg_base.py |
| 19 | `imagemark_rotation_angle` | `watermark_image_rotation_angle` | config.py, renderers/svg_base.py |
| 20 | `theme_federal_holiday_alpha` | `theme_federal_holiday_opacity` | config.py, weekly/renderer.py, mini/renderer.py |
| 21 | `theme_company_holiday_alpha` | `theme_company_holiday_opacity` | config.py, weekly/renderer.py, mini/renderer.py |
| 22 | `mini_nonworkday_shade` | `mini_nonworkday_fill_color` | config.py, mini/renderer.py, mini/day_styles.py |
| 23 | `theme_mini_nonworkday_shade` | `theme_mini_nonworkday_fill_color` | config.py, mini/renderer.py |
| 24 | ~~`theme_specialdaycolor`~~ | `theme_special_day_color` | config.py, weekly/renderer.py | **DONE** |
| 25 | ~~`theme_hashlinecolor`~~ | `theme_hash_line_color` | config.py, weekly/renderer.py | **DONE** |
| 26 | ~~`theme_fiscalperiodcolors`~~ | `theme_fiscal_period_colors` | config.py, weekly/renderer.py, mini/renderer.py | **DONE** |
| 27 | ~~`theme_monthcolors`~~ | `theme_month_colors` | config.py, weekly/renderer.py, mini/renderer.py | **DONE** |
| 28 | `mini_grid_line_color` | `mini_grid_line_color` | config.py, mini/renderer.py |
| 29 | `mini_grid_line_width` | `mini_grid_line_width` | config.py, mini/renderer.py |
| 30 | `mini_grid_line_opacity` | `mini_grid_line_opacity` | config.py, mini/renderer.py |
| 31 | `mini_grid_line_dasharray` | `mini_grid_line_dasharray` | config.py, mini/renderer.py |
| 32 | `event_icon_font_size` | `event_icon_size` | config.py, weekly/renderer.py |
