# Plan: Unified Theme Model with CSS Styling

## Context

The current theming system has ~200+ config fields with massive duplication across visualizers. Each visualizer independently defines its own font, color, fill, stroke, and opacity fields — even when the visual concept is identical. All styling is applied as inline SVG attributes with no CSS classes, no `<style>` block, and no element naming. This makes themes verbose, the SVG output unstyled and unstructured, and post-production editing impossible.

The goal is:
1. A single theme definition with shared style tokens across all SVG visualizers
2. CSS-based styling: every SVG element gets a semantic CSS class, and a `<style>` block in the SVG drives appearance
3. Named elements: a consistent class naming scheme so elements are identifiable and externally styleable

## Current State

**No CSS at all.** The draw methods (`_draw_rect`, `_draw_text`, `_draw_line`, `_draw_circle`) apply all styling as inline SVG attributes (`fill=`, `stroke=`, `fill-opacity=`). No `class` or `id` attributes are set. No `<style>` element exists in the output SVG. The `drawsvg` library supports arbitrary kwargs on shapes (so `class_="foo"` works) and `drawing.append_css()` for injecting `<style>` blocks.

**~245 config fields** with massive per-visualizer duplication (see previous analysis).

---

## Part 1: CSS Architecture

### 1.1 Class Naming Convention

Every SVG element gets a CSS class following this pattern:

```
ec-{element}                    — shared across visualizers
ec-{visualizer}-{element}       — visualizer-specific override
```

The `ec-` prefix (EventCalendar) prevents collisions when SVGs are embedded in other documents.

### 1.2 Consolidated Element Name Catalog

Every element name is semantic and shared across visualizers. If two visualizers draw the same concept (event name, month title, grid line), they use the same CSS class.

#### Text Elements

| CSS Class | What it styles | Used in |
|-----------|---------------|---------|
| `ec-heading` | Section/area heading text | Month titles (mini), band headings (blockplan), lane labels (blockplan), details page title, callout titles |
| `ec-label` | Short label text | DOW headers (mini, weekly), band segment labels (blockplan), axis tick labels |
| `ec-day-number` | Day of month number | Weekly day boxes, mini calendar cells |
| `ec-month-title` | Month name display | Mini month title, blockplan month band labels, timeline month labels |
| `ec-week-number` | Week number label | Weekly margin, mini calendar column |
| `ec-fiscal-label` | Fiscal period label | Weekly day rows, mini cells, blockplan bands |
| `ec-event-name` | Event/task name | Weekly events, timeline callouts, blockplan items, details rows, compact legend |
| `ec-event-notes` | Event notes/description | Weekly notes, timeline callout notes, details row notes |
| `ec-event-date` | Event date display | Blockplan event dates, timeline callout dates, compact milestone dates |
| `ec-duration-date` | Duration start/end date | Blockplan duration dates, timeline duration dates |
| `ec-holiday-title` | Holiday/special day name | Weekly day boxes |
| `ec-today-label` | Today marker label | Timeline, blockplan, compact plan |
| `ec-header-text` | Page header text | All visualizers (left/center/right) |
| `ec-footer-text` | Page footer text | All visualizers (left/center/right) |
| `ec-watermark` | Watermark overlay text | All visualizers |

#### Box/Rectangle Elements

| CSS Class | What it styles | Used in |
|-----------|---------------|---------|
| `ec-background` | Page/area background | All visualizers |
| `ec-cell` | Content cell background | Weekly day boxes, mini day cells, blockplan icon cells |
| `ec-heading-cell` | Heading area background | Blockplan band headings, blockplan lane headings |
| `ec-band-cell` | Time band segment cell | Blockplan time bands, compact plan time bands |
| `ec-callout-box` | Popup/callout box | Timeline event callouts |
| `ec-vline-fill` | Vertical line fill column | Blockplan vertical line fills |
| `ec-day-box` | Day number box outline | Mini calendar day number outlines |
| `ec-pattern-fill` | SVG pattern overlay | Weekly hash patterns, mini hash patterns |

#### Line Elements

| CSS Class | What it styles | Used in |
|-----------|---------------|---------|
| `ec-grid-line` | Grid/cell boundary | Weekly day boxes, mini calendar grid, blockplan grid |
| `ec-axis-line` | Timeline axis line | Timeline, blockplan, compact plan |
| `ec-axis-tick` | Axis tick mark | Timeline, blockplan |
| `ec-today-line` | Today marker line | Timeline, blockplan, compact plan |
| `ec-separator` | Section divider | Details header separator, blockplan lane divider |
| `ec-connector` | Connector line | Timeline callout connectors |
| `ec-vline` | Configured vertical line | Blockplan pinned vertical lines |
| `ec-duration-bar` | Duration span bar/line | Mini duration bars, timeline duration bars, compact duration lines |
| `ec-hash-line` | Hash pattern line | Mini diagonal hash lines |
| `ec-strikethrough` | Strikethrough line | Mini calendar strikethrough |

#### Marker Elements

| CSS Class | What it styles | Used in |
|-----------|---------------|---------|
| `ec-milestone-marker` | Milestone indicator | Mini circles, timeline markers, compact plan flags |
| `ec-milestone-flag` | Milestone flag pennant | Compact plan flag shape |
| `ec-duration-marker` | Duration start indicator | Timeline duration start markers |

#### Icon Elements

| CSS Class | What it styles | Used in |
|-----------|---------------|---------|
| `ec-event-icon` | Event/holiday icon | Weekly event icons, weekly holiday icons, mini icons |
| `ec-duration-icon` | Duration category icon | Compact plan duration icons |
| `ec-overflow-icon` | Overflow indicator | Weekly overflow marker |

#### Legend Elements

| CSS Class | What it styles | Used in |
|-----------|---------------|---------|
| `ec-legend-swatch` | Legend color swatch | Compact plan legend |
| `ec-legend-text` | Legend item text | Compact plan legend |
| `ec-legend-icon` | Legend item icon | Compact plan legend |

#### Modifier Classes (compound — added alongside element class)

| CSS Class | What it modifies | Used in |
|-----------|-----------------|---------|
| `ec-holiday` | Holiday day styling | Weekly cells, mini cells |
| `ec-nonworkday` | Nonworkday styling | Weekly cells, mini cells |
| `ec-current-day` | Current day highlight | Weekly cells, mini cells |
| `ec-adjacent` | Adjacent month day (dimmed) | Mini calendar |

**Total: ~40 unique elements** (down from ~60 visualization-specific elements)

### 1.3 CSS Generation from Theme

The theme engine generates a `<style>` block injected into the SVG via `drawing.append_css()`. Style tokens map directly to CSS rules:

```css
/* Text elements — generated from element_styles + text_styles */
.ec-heading      { fill: #000000; fill-opacity: 1.0; }
.ec-label        { fill: #444444; fill-opacity: 1.0; }
.ec-event-name   { fill: #333333; fill-opacity: 1.0; }
.ec-event-notes  { fill: #666666; fill-opacity: 1.0; }
.ec-fiscal-label { fill: #888888; fill-opacity: 1.0; }
.ec-week-number  { fill: #444444; fill-opacity: 1.0; }
.ec-month-title  { fill: #000000; fill-opacity: 1.0; }
.ec-day-number   { fill: #444444; fill-opacity: 1.0; }

/* Box elements — generated from element_styles + box_styles */
.ec-cell {
  fill: white; fill-opacity: 1.0;
  stroke: #E0E0E0; stroke-width: 0.25; stroke-opacity: 1.0;
}
.ec-heading-cell {
  fill: #F0F0F0; fill-opacity: 1.0;
  stroke: none;
}
.ec-band-cell {
  fill: #F8F8F8; fill-opacity: 0.5;
  stroke: none;
}

/* Line elements — generated from element_styles + line_styles */
.ec-grid-line  { stroke: #CCCCCC; stroke-width: 0.5; stroke-opacity: 1.0; }
.ec-axis-line  { stroke: #333333; stroke-width: 1.0; stroke-opacity: 1.0; }
.ec-today-line { stroke: red; stroke-width: 1.5; stroke-dasharray: 4,2; }
.ec-separator  { stroke: #EEEEEE; stroke-width: 0.5; }
.ec-connector  { stroke: #999999; stroke-width: 0.5; stroke-dasharray: 2,2; }

/* Modifier classes (compound — added alongside element class) */
.ec-holiday    { fill: #FFE0E0; fill-opacity: 0.5; }
.ec-nonworkday { fill: #F0F0F0; }
.ec-current-day { fill: #FFFFCC; fill-opacity: 0.3; }
.ec-adjacent   { fill-opacity: 0.4; }
```

### 1.4 How CSS Interacts with Text-to-Path

Text is rendered as `<g>` groups containing `<path>` glyphs. CSS `fill` on the `<g>` cascades to child paths. The `text_to_svg_group()` function is updated to:
1. Accept a `css_class` parameter
2. Emit `<g class="ec-event-name" fill="...">` instead of just `<g fill="...">`
3. When CSS is active, omit inline `fill`/`fill-opacity` — let CSS drive it
4. Keep inline attributes as fallback when CSS class is not provided (backward compat)

### 1.5 Dual-Mode Rendering: CSS + Inline Fallback

Since text is rendered as `<path>` outlines (not `<text>` elements), not all CSS properties apply. The approach:

- **CSS-driven properties**: `fill`, `fill-opacity`, `stroke`, `stroke-width`, `stroke-opacity`, `stroke-dasharray` — these work on `<rect>`, `<line>`, `<circle>`, `<path>`, and `<g>`
- **Inline-only properties**: Geometry (`x`, `y`, `width`, `height`, `d`, `transform`) — always inline
- **Font properties in CSS are decorative-only**: Since we use `<path>` not `<text>`, CSS `font-family`/`font-size` don't affect rendering. Font selection remains in Python code via style tokens. CSS drives color/opacity only for text groups.

Draw methods updated signature:
```python
_draw_rect(x, y, w, h, *, css_class=None, fill=..., stroke=..., ...)
_draw_text(x, y, text, font_name, font_size, *, css_class=None, fill=..., ...)
_draw_line(x1, y1, x2, y2, *, css_class=None, stroke=..., ...)
_draw_circle(cx, cy, r, *, css_class=None, stroke=..., fill=..., ...)
```

When `css_class` is provided:
- The element gets `class="ec-..."` attribute
- Inline style attributes are still set (for standalone SVG viewing without the `<style>` block)
- CSS rules override inline attrs due to specificity (CSS class > presentational attributes in SVG)

---

## Part 2: Unified Theme Structure

### 2.1 Text Styles (`text_styles:`)

```yaml
text_styles:
  heading:
    font: Roboto-Bold
    size: 10
    color: "#000000"
    opacity: 1.0
    alignment: left
  body:
    font: RobotoCondensed-Light
    size: 8
    color: "#333333"
  body_secondary:
    font: RobotoCondensed-LightItalic
    size: 7
    color: "#666666"
  label:
    font: RobotoCondensed-Bold
    size: 7
    color: "#444444"
  caption:
    font: RobotoCondensed-Light
    size: 6
    color: "#888888"
```

Papersize scaling via `size_rules` on individual styles. Element-to-style binding in the flat `element_styles` map.

### 2.2 Color Scheme (`colors:`)

```yaml
colors:
  background: "white"
  foreground: "#333333"
  accent: "#2196F3"
  muted: "#999999"
  month_palette: "Greys"
  fiscal_palette: "Blues"
  group_palette: "Pastel1"
  event_colors: ["#4E79A7", "#F28E2B", "#E15759"]
  federal_holiday: { color: "#FFE0E0", opacity: 0.5 }
  company_holiday: { color: "#E0FFE0", opacity: 0.5 }
  special_day: "#FFCCCC"
  special_day_types: { federal: "#FFE0E0", company: "#E0FFE0", nonworkday: "#F0F0F0" }
  resource_groups: { a: "#AEC7E8", b: "#FFBB78", c: "#98DF8A", d: "#FF9896" }
```

### 2.3 Box Styles (`box_styles:`)

Each box style defines a static fill plus optional palette-based cycling. When `fill_palette` or `fill_colors` is present, the renderer cycles through colors for repeating instances of that element (e.g., successive month cells, time band segments). Static `fill` acts as the fallback when no palette is set or for non-repeating contexts.

```yaml
box_styles:
  default:
    fill: "white"
    fill_opacity: 1.0
    stroke: "#CCC"
    stroke_width: 0.5
    stroke_opacity: 1.0
    stroke_dasharray: null
    fill_palette: null         # named palette from DB (e.g., "Greys", "Pastel1")
    fill_colors: null          # inline color list (e.g., ["#F0F0F0", "#E8E8E8", ...])

  header:
    fill: "#F0F0F0"
    stroke: null

  cell:
    fill: "white"
    stroke: "#E0E0E0"
    stroke_width: 0.25
    fill_palette: "Greys"      # month-colored day boxes cycle through this palette

  highlight:
    fill: "#FFFFCC"
    fill_opacity: 0.3
    stroke: null

  timeband:
    fill: "#F8F8F8"
    fill_opacity: 0.5
    stroke: null
    fill_palette: "Pastel1"    # time band segments cycle through this palette
```

**Palette resolution priority:** `fill_colors` (inline list) > `fill_palette` (DB lookup) > `fill` (static fallback). Only one of `fill_colors` or `fill_palette` should be set. The renderer calls `palette[index % len(palette)]` to cycle.

**Applies to all box/rectangle elements:** `ec-cell`, `ec-band-cell`, `ec-heading-cell`, `ec-callout-box`, `ec-vline-fill`, `ec-day-box`, `ec-background`, `ec-pattern-fill`. Any box element can use palette cycling when its context involves repeating instances.

### 2.4 Line Styles (`line_styles:`)

Every line style includes the full set of line properties: `color`, `width`, `opacity`, and `dasharray`. All four are always available on every line element.

```yaml
line_styles:
  grid:
    color: "#CCCCCC"
    width: 0.5
    opacity: 1.0
    dasharray: null
  axis:
    color: "#333333"
    width: 1.0
    opacity: 1.0
    dasharray: null
  separator:
    color: "#EEEEEE"
    width: 0.5
    opacity: 1.0
    dasharray: null
  today:
    color: "red"
    width: 1.5
    opacity: 1.0
    dasharray: "4,2"
  connector:
    color: "#999999"
    width: 0.5
    opacity: 1.0
    dasharray: "2,2"
```

### 2.5 Axis Definition (`axis:`) — Shared

```yaml
axis:
  line_style: axis
  tick: { color: "#666", label_style: caption, date_format: "MMM D" }
  today: { line_style: today, label_color: "red", label_text: "Today" }
```

### 2.6 Icons, Patterns, Watermark, Header/Footer, Events/Durations

```yaml
icons:
  event: { color: "#333333", size: 10 }
  duration: { color: "#666666" }
  overflow: { icon: "↓", color: "red" }
  default_missing: "📌"

patterns:
  default_pattern: diagonal-stripes
  default_opacity: 0.15
  hash_rules:
    - pattern: diagonal-stripes
      color: "#999999"
      opacity: 0.15
      when: { day_type: [weekend, holiday] }

header:
  left: { text_style: heading }
  center: { text_style: heading }
  right: { text_style: heading }
footer:
  left: { text_style: caption }
  center: { text_style: caption }
  right: { text_style: caption }

watermark:
  text: ""
  text_style: heading
  opacity: 0.08
  rotation_angle: -30

events:
  name: { text_style: body }
  notes: { text_style: body_secondary }
  icon_color: "#333333"
  item_placement_order: [events, milestones, durations]

durations:
  name: { text_style: body }
  notes: { text_style: body_secondary }
  stroke_dasharray: "4,2"
  date: { text_style: caption, format: "MMM D" }
```

### 2.7 Element-to-Style Binding Map

A single flat map defines which style token each named element uses. Every element — shared or visualizer-specific — is listed here. There are no per-visualizer overrides or cascading; if you need different styling for a specific visualizer, create a new theme.

```yaml
element_styles:
  # --- Text elements ---
  ec-heading:        { text_style: heading }
  ec-label:          { text_style: label }
  ec-day-number:     { text_style: label }
  ec-month-title:    { text_style: heading }
  ec-week-number:    { text_style: label }
  ec-fiscal-label:   { text_style: caption }
  ec-event-name:     { text_style: body }
  ec-event-notes:    { text_style: body_secondary }
  ec-event-date:     { text_style: caption }
  ec-duration-date:  { text_style: caption }
  ec-holiday-title:  { text_style: body }
  ec-today-label:    { text_style: label, color: "red" }
  ec-header-text:    { text_style: heading }
  ec-footer-text:    { text_style: caption }
  ec-watermark:      { text_style: heading }

  # --- Box/rectangle elements ---
  ec-background:     { box_style: default }
  ec-cell:           { box_style: cell }
  ec-heading-cell:   { box_style: header }
  ec-band-cell:      { box_style: timeband }
  ec-callout-box:    { box_style: default }
  ec-vline-fill:     { box_style: highlight }
  ec-day-box:        { box_style: cell }
  ec-pattern-fill:   { box_style: default }

  # --- Line elements ---
  ec-grid-line:      { line_style: grid }
  ec-axis-line:      { line_style: axis }
  ec-axis-tick:      { line_style: axis }
  ec-today-line:     { line_style: today }
  ec-separator:      { line_style: separator }
  ec-connector:      { line_style: connector }
  ec-vline:          { line_style: grid }
  ec-duration-bar:   { line_style: axis }
  ec-hash-line:      { line_style: grid }
  ec-strikethrough:  { line_style: grid }

  # --- Marker elements ---
  ec-milestone-marker: { line_style: axis }
  ec-milestone-flag:   { line_style: axis }
  ec-duration-marker:  { line_style: axis }

  # --- Icon elements ---
  ec-event-icon:     { icon_style: event }
  ec-duration-icon:  { icon_style: duration }
  ec-overflow-icon:  { icon_style: overflow }

  # --- Legend elements ---
  ec-legend-swatch:  { line_style: axis }
  ec-legend-text:    { text_style: body }
  ec-legend-icon:    { icon_style: event }
```

---

## Part 3: Implementation Phases

### Phase 1: Style Primitives + CSS Generator

**Files:** `config/styles.py` (new), `renderers/css_generator.py` (new)

1. Create dataclasses: `TextStyle`, `BoxStyle` (includes `fill_palette` and `fill_colors`), `LineStyle`, `IconStyle`, `AxisStyle`
2. `ThemeStyles` container: holds named dicts of all style types + flat element-to-style binding map
4. `CSSGenerator.generate(theme_styles) → str` produces `<style>` block content from bindings
5. Map each element class to its resolved style, emit CSS rules

### Phase 2: Update Draw Methods for CSS Classes

**Files:** `renderers/svg_base.py`, `renderers/glyph_cache.py`

1. Add `css_class: str | None = None` parameter to `_draw_rect`, `_draw_text`, `_draw_line`, `_draw_circle`, `_draw_icon_svg`
2. When set, attach `class_=css_class` kwarg to drawsvg shapes
3. For `_draw_text` → update `text_to_svg_group()` to emit `class="..."` on the `<g>` element
4. Add `_inject_css(drawing, css_content)` method that calls `drawing.append_css(css_content)` once per SVG
5. Keep inline attributes as fallback — CSS overrides them via specificity

### Phase 3: Theme YAML Schema + Loader Rewrite

**Files:** `config/theme_engine.py`

1. Parse new YAML sections: `text_styles`, `box_styles`, `line_styles`, `colors`, `axis`, `icons`, `patterns`, `element_styles`
2. Resolve references: `{ text_style: body }` → look up `text_styles.body` → `TextStyle` object
3. Build `ThemeStyles` container on `CalendarConfig`
4. Generate CSS string and store on config for injection during render
5. No cascading/override logic — one flat element map per theme; different needs → different theme file

### Phase 4: Adapt CalendarConfig

**Files:** `config/config.py`

1. Add `theme_styles: ThemeStyles | None` field
2. Add `svg_css: str | None` field (pre-generated CSS string)
3. Accessor methods: `config.get_element_text_style("ec-event-name") → TextStyle`
4. Accessor methods: `config.get_element_box_style("ec-weekly-day-box") → BoxStyle`
5. Deprecate flat `theme_*` fields; populate them from resolved styles during transition

### Phase 5: Migrate Renderers + Assign CSS Classes

**Order:** svg_base → weekly → mini → blockplan → timeline → compact_plan

For each renderer, update every draw call to:
1. Pass the appropriate `css_class="ec-..."` string
2. Use style token lookups instead of direct config field access
3. Call `_inject_css()` once at the start of each SVG page

Example migration (weekly renderer):
```python
# Before:
self._draw_rect(x, y, w, h, fill=config.day_box_fill_color,
                stroke=config.day_box_stroke_color, ...)

# After:
box = config.get_element_box_style("ec-cell")
self._draw_rect(x, y, w, h, css_class="ec-cell",
                fill=box.fill, stroke=box.stroke, ...)
```

### Phase 6: Convert Theme YAML Files

**Files:** All 9 files in `config/themes/`

Rewrite each theme from flat per-visualizer fields to the new token-based structure with `element_styles` bindings.

### Phase 7: Update USER_GUIDE.MD

**Files:** `USER_GUIDE.MD`

Document the new theme system:
1. Theme YAML structure: `text_styles`, `box_styles`, `line_styles`, `colors`, `axis`, `icons`, `patterns`, `element_styles`
2. How to create a new theme from scratch (no need to replicate existing themes — define only the style tokens and element bindings you need)
3. Full element catalog with CSS class names and what each styles
4. Box style palette cycling (`fill_palette`, `fill_colors`)
5. Line style properties (`color`, `width`, `opacity`, `dasharray`)
6. How CSS classes appear in SVG output and how to apply external CSS overrides
7. Example: minimal theme file showing the required sections

### Phase 8: Remove Deprecated Fields

Remove ~200 flat fields from `CalendarConfig` and the old `THEME_TO_CONFIG_MAP`.

---

## Field Reduction Estimate

| Category | Current Fields | New Tokens | Reduction |
|----------|---------------|------------|-----------|
| Text (font/size/color/opacity/align) | ~90 | ~5 named styles + ~15 element bindings | ~80% |
| Rectangle fills | ~30 | ~5 named box styles + ~10 bindings | ~75% |
| Line/stroke | ~40 | ~5 named line styles + ~8 bindings | ~80% |
| Axis/timeline | ~25 | 1 shared axis def + ~3 overrides | ~85% |
| Colors/palettes | ~25 | ~15 (already fairly unified) | ~40% |
| Opacity (separate fields) | ~35 | 0 (folded into style objects) | ~100% |
| **Total** | **~245** | **~60** | **~75%** |

---

## Key Files to Modify

| File | Change |
|------|--------|
| `config/styles.py` | **NEW** — Style dataclasses + ThemeStyles container |
| `renderers/css_generator.py` | **NEW** — CSS `<style>` block generation |
| `renderers/svg_base.py` | Add `css_class` param to all draw methods, CSS injection |
| `renderers/glyph_cache.py` | Add `css_class` param to `text_to_svg_group()` |
| `config/theme_engine.py` | Rewrite loader for new YAML schema |
| `config/config.py` | Add `ThemeStyles`, accessors, deprecate flat fields |
| `visualizers/weekly/renderer.py` | Assign CSS classes, use style lookups |
| `visualizers/mini/renderer.py` | Assign CSS classes, use style lookups |
| `visualizers/blockplan/renderer.py` | Assign CSS classes, use style lookups |
| `visualizers/timeline/renderer.py` | Assign CSS classes, use style lookups |
| `visualizers/compactplan/renderer.py` | Assign CSS classes, use style lookups |
| `config/themes/*.yaml` | All 9 theme files rewritten |
| `USER_GUIDE.MD` | Document new theme system, element catalog, how to create themes from scratch |

## Verification

- Run `uv run python -m pytest tests/ -v` after each phase
- Generate SVGs with each theme before/after; visually diff to confirm parity
- Inspect generated SVG: verify `<style>` block present, all elements have `class="ec-..."` attributes
- Open SVG in browser dev tools: confirm CSS rules match elements, overrides work
- Test external CSS override: load SVG, inject custom `<style>` to restyle elements — verify it works
- Validate all 9 theme YAMLs load without warnings
- Test papersize-conditional font scaling
