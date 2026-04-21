# Unified `style_rules` Design

## Core Concept

Two top-level rule lists replace the existing per-visualizer rule systems:

- **`style_rules:`** — visual styling (colors, fonts, patterns, strokes) for day boxes, events, and durations. Each rule has **`select`** (what to match), **`apply_to`** (which visual element type: `day_box`, `event`, `duration`), and **`style`** (properties to apply).
- **`swimlane_rules:`** — blockplan lane routing only. Same **`select`** syntax, but **`apply_to`** is a **lane name string** identifying which swimlane matched content is placed into. Lane visual properties (colors, label alignment, split ratio) remain in `blockplan.swimlanes` as before.

Keeping routing separate from styling means a rule that places an event into a lane does not also have to declare how that event looks, and vice versa — the two concerns compose independently.

---

## YAML Syntax

```yaml
style_rules:

  - name: "Federal Holidays"
    select:
      federal_holiday: true
    apply_to: [day_box, event, duration]
    style:
      fill_color: tomato
      fill_opacity: 0.10
      pattern: diagonal-stripes
      pattern_color: tomato
      pattern_opacity: 0.12

  - name: "Xstore Conversions"
    select:
      resource_group: ["Xstore"]
    apply_to: [event, duration]
    style:
      fill_color: "#C8102E"
      text:
        event_name:
          font_color: white
        duration_name:
          font_color: white

  - name: "Completed Work"
    select:
      percent_complete: { min: 100 }
    apply_to: [event, duration, day_box]
    style:
      pattern: diagonal-stripes
      pattern_color: mediumseagreen
      pattern_opacity: 0.10
      stroke_dasharray: null

  - name: "Sprint Durations"
    select:
      task_name: ["Sprint"]
      event_type: duration
    apply_to: duration
    style:
      fill_color: steelblue
      stroke_color: white
      stroke_width: 1.0
      font_color: white

  - name: "Non-Workdays"
    select:
      nonworkday: true
    apply_to: day_box
    style:
      fill_color: "#E8E8E8"
      fill_opacity: 0.4
      pattern: diagonal-stripes
      pattern_color: silver
      pattern_opacity: 0.08

  - name: "Priority 1"
    select:
      priority: 1
    apply_to: [event, duration]
    style:
      stroke_color: crimson
      stroke_width: 1.5
      text:
        event_name:
          font: OfficinaSans-Bold
          font_color: crimson
        event_notes:
          font_color: "#CC4444"
          font_size: 8
        event_date:
          font_color: crimson
          font_size: 7
        duration_name:
          font: OfficinaSans-Bold
          font_color: white
        duration_start_date:
          font_color: gold
          font_size: 8
        duration_end_date:
          font_color: gold
          font_size: 8

  - name: "Code Freeze Window"
    select:
      date: "20190301-20190321"
    apply_to: [day_box, event, duration]
    style:
      fill_color: steelblue
      fill_opacity: 0.15
      pattern: diagonal-stripes
      pattern_color: steelblue
      pattern_opacity: 0.10

  - name: "Launch Day"
    select:
      date: "20190321"
    apply_to: day_box
    style:
      fill_color: gold
      fill_opacity: 0.40
      stroke_color: goldenrod
      stroke_width: 2.0

  - name: "Q3 Events in Freeze"
    select:
      date: "20190301-20190321"
      resource_group: ["Xstore"]
      event_type: duration
    apply_to: duration
    style:
      fill_color: "#C8102E"
      stroke_color: white
      stroke_width: 1.5
      text:
        duration_name:
          font: OfficinaSans-Bold
          font_color: white
        duration_notes:
          font: OfficinaSans-BookItalic
          font_color: "#FFCCCC"
        duration_start_date:
          font_color: white
          font_size: 8
        duration_end_date:
          font_color: white
          font_size: 8

  - name: "Freeze Window Day Boxes"
    select:
      date: "20190301-20190321"
    apply_to: day_box
    style:
      text:
        day_number:
          font_color: steelblue
          font_size: 11
        week_number:
          font_color: "#4477AA"
        holiday_title:
          font_color: white
          font_size: 8
```

```yaml
# Swimlane routing — apply_to is the target lane name, not a visual element type.
# First matching rule wins. An empty select: {} acts as a catch-all.
swimlane_rules:

  - name: "Route Xstore"
    select:
      resource_group: ["Xstore"]
    apply_to: "Xstore\nConversions"

  - name: "Route Triversity"
    select:
      resource_group: ["Triversity"]
    apply_to: "Triversity\nPOSReady7"

  - name: "Route IC Fix"
    select:
      resource_group: ["ICFix"]
    apply_to: "IC Fix"

  - name: "Route Post PI6"
    select:
      resource_group: ["PostPI6"]
    apply_to: "Post PI6"

  - name: "High-priority milestones to top lane"
    select:
      milestone: true
      priority: 1
    apply_to: "Key Milestones"

  - name: "Unmatched catch-all"
    select: {}
    apply_to: "Other"
```

```yaml
# Lane visual definitions — separate from routing; no match: key.
blockplan:
  swimlanes:
    - name: "Xstore\nConversions"
      fill_color: none
      label_color: red
      label_align_h: center
      split_ratio: 0.5
    - name: "Triversity\nPOSReady7"
      fill_color: none
      label_color: navy
      label_align_h: center
    - name: "IC Fix"
      fill_color: none
      label_color: darkgreen
    - name: "Post PI6"
      fill_color: none
      label_color: grey
    - name: "Key Milestones"
      fill_color: gold
      label_color: black
      split_ratio: 0.0
    - name: "Other"
      fill_color: "#F0F0F0"
      label_color: dimgrey
```

---

## `select:` Criteria

Rules support two context domains. A rule matches when **all specified criteria** are satisfied (AND logic). Use `min_match:` for OR-style behavior.

### Day/context criteria (derived from the date and DB)

| Key | Type | Notes |
|---|---|---|
| `federal_holiday` | bool | Government holiday with nonworkday=1 |
| `company_holiday` | bool | Company special day with nonworkday=1 |
| `nonworkday` | bool | Any of the above, or weekend |
| `workday` | bool | Not nonworkday |
| `weekend` | bool | Falls on config weekend days |
| `date` | str | Single date (`YYYYMMDD`) or closed range (`YYYYMMDD-YYYYMMDD`) |

### Event criteria (matched against Event fields on the day/event being styled)

| Key | Type | Match style |
|---|---|---|
| `task_name` | str \| list | Substring |
| `notes` | str \| list | Substring |
| `resource_group` | str \| list | Case-insensitive exact |
| `resource_names` | str \| list | Substring (comma-split field) |
| `wbs` | str | `WBSFilter` expression — comma-separated tokens; `!` prefix excludes; segments are `.`-separated; `*` matches one segment, `**` matches any remaining (implicit if omitted); e.g. `"PROJ.*,!PROJ.3"` |
| `priority` | int \| list | Exact |
| `priority_min` / `priority_max` | int | Inclusive range |
| `percent_complete` | int \| `{min, max}` | Exact or range |
| `milestone` | bool | Flag field |
| `rollup` | bool | Flag field |
| `event_type` | `event` \| `duration` \| `any` | Point vs span |
| `color` | str | Exact match on the Event.color field |
| `icon` | str | Exact match on the Event.icon field |

### Aggregation modifiers (for `apply_to: day_box`)

Controls how event-level criteria are tested across all events on a day.

| Key | Default | Meaning |
|---|---|---|
| `min_match` | 1 | Min criteria that must be true |
| `any_event` | true | Passes if *any* event on the day matches event criteria |
| `all_events` | false | Passes only if *all* events match |

---

## `apply_to:` Targets

### In `style_rules`

| Value | What gets styled |
|---|---|
| `day_box` | Weekly day cell background + pattern; mini calendar cell |
| `event` | Point event icon, name text, date text |
| `duration` | Duration bar fill, stroke, label text |
| `all` | All three of the above |

A single rule can specify `apply_to: [day_box, duration]` to style multiple target types.

### In `swimlane_rules`

`apply_to` is a **lane name string** matching the `name` field of an entry in `blockplan.swimlanes`. It is not a list — each routing rule routes to exactly one lane. First matching rule wins.

---

## `style:` Properties

### Fill and background

| Property | Applies to | Notes |
|---|---|---|
| `fill_color` | day_box, event, duration | Background / bar fill |
| `fill_opacity` | day_box, event, duration | |
| `pattern` | day_box | SVG pattern name from DB |
| `pattern_color` | day_box | Colorizes the pattern |
| `pattern_opacity` | day_box | |

### Stroke and border

| Property | Applies to | Notes |
|---|---|---|
| `stroke_color` | day_box, event, duration | Border / outline color |
| `stroke_width` | day_box, event, duration | |
| `stroke_opacity` | day_box, event, duration | |
| `stroke_dasharray` | day_box, event, duration | SVG dash pattern, e.g. `"4 2"` |

### Text — shorthand

Flat keys apply to **all** text elements rendered for the matched target. Use these when uniform styling is sufficient.

| Property | Applies to | Notes |
|---|---|---|
| `font` | day_box, event, duration | Font name — applied to all sub-elements |
| `font_size` | day_box, event, duration | Point size — applied to all sub-elements |
| `font_color` | day_box, event, duration | Color — applied to all sub-elements |
| `font_opacity` | day_box, event, duration | Opacity — applied to all sub-elements |

### Text — per-element (`text:` block)

A nested `text:` block provides per-element control. Any key omitted inherits from the shorthand or the theme default. Sub-element keys map directly to the CSS element classes used by the renderers.

```yaml
style:
  text:
    event_name:         # ec-event-name  — point event title
      font: OfficinaSans-Bold
      font_size: 10
      font_color: crimson
      font_opacity: 1.0
    event_notes:        # ec-event-notes — point event notes line
      font: OfficinaSans-BookItalic
      font_size: 8
      font_color: grey
    event_date:         # ec-event-date  — point event date label
      font_size: 7
      font_color: darkgrey
    duration_name:      # duration title in bar or label column
      font: OfficinaSans-Bold
      font_color: white
    duration_notes:     # duration notes line
      font: OfficinaSans-BookItalic
      font_color: "#DDDDDD"
    duration_start_date:  # start date printed on or beside duration bar
      font_size: 8
      font_color: gold
    duration_end_date:    # end date printed on or beside duration bar
      font_size: 8
      font_color: gold
    day_number:         # ec-day-number  — large digit in day box corner
      font: InstrumentSerif-Regular
      font_size: 11
      font_color: "#FF7800"
    week_number:        # ec-week-number — week label beside row
      font: InstrumentSerif-Regular
      font_color: yellow
    month_indicator:    # ec-month-title — abbreviated month shown on 1st of month
      font_color: navy
      font_size: 8
    holiday_title:      # ec-holiday-title — special day / holiday name in day box
      font_color: white
      font_size: 8
      font: OfficinaSans-BookItalic
```

### Text element reference

| `text:` key | CSS class | Where rendered |
|---|---|---|
| `event_name` | `ec-event-name` | Point event title (weekly, blockplan, timeline) |
| `event_notes` | `ec-event-notes` | Point event notes line |
| `event_date` | `ec-event-date` | Point event date label |
| `duration_name` | `ec-event-name` | Duration bar / lane label title |
| `duration_notes` | `ec-event-notes` | Duration notes line |
| `duration_start_date` | `ec-duration-date` | Start date beside duration bar |
| `duration_end_date` | `ec-duration-date` | End date beside duration bar |
| `day_number` | `ec-day-number` | Large digit in weekly / mini day box |
| `week_number` | `ec-week-number` | Week number label on row left edge |
| `month_indicator` | `ec-month-title` | Abbreviated month on first day of month |
| `holiday_title` | `ec-holiday-title` | Holiday / special day name in day box |

### Icons

| Property | Applies to | Notes |
|---|---|---|
| `icon` | event | Override the event icon glyph |
| `icon_color` | event | Icon color |

---

## Rule Evaluation Semantics

### `style_rules`

Rules are evaluated **in declaration order**. Later rules **layer on top of** earlier ones — they do not replace. This matches the existing hash_rules behavior and allows compositing (e.g., a federal holiday rule lays down a red pattern; a "Sprint" rule on the same day adds a steelblue overlay). A `None` field in a later `StyleResult` leaves the earlier value intact.

### `swimlane_rules`

Rules are evaluated **in declaration order** and **first-match wins** — an event is placed into the lane named by the first rule whose `select:` criteria it satisfies. An empty `select: {}` matches everything and is therefore only useful as a final catch-all. Events that match no rule and have no catch-all are placed into the unmatched lane if `blockplan.show_unmatched_lane: true`, or dropped from the blockplan otherwise.

---

## Implementation Architecture

### Phase 0 — Create reference theme file

**New file:** `config/themes/reference.yaml`

This file is the canonical definition of every key the theme engine can read. It uses only the new `style_rules` / `swimlane_rules` format — no legacy `hash_rules` or `swimlanes.match` keys. Every key appears with a comment explaining its scope, accepted values, and which visualizers consume it. Omitting a key from a user-created theme inherits the value shown here.

The reference theme ships with neutral, safe defaults (no strong colors, no opinionated fonts) so it can be used as a starting point for any new theme by copying and editing.

#### File structure and comment conventions

```yaml
# ══════════════════════════════════════════════════════════════════════════════
# reference.yaml — CalendarApp canonical theme reference
#
# Every key the theme engine reads appears below with a description comment.
# Keys marked [all] apply to every visualizer.
# Keys marked [weekly], [blockplan], [mini], [timeline], [compact] are scoped.
# Omitting a key inherits the built-in default shown in the comment.
# ══════════════════════════════════════════════════════════════════════════════

theme:
  name: "Reference"           # Display name shown in --list-themes output
  version: "3.0"              # Theme format version; must be "3.0" for new format
  description: "Canonical reference theme — copy and edit to create a new theme"

# ── Unified style tokens ──────────────────────────────────────────────────────
# Named style objects referenced by element_styles below.
# Define as many or as few as needed; unused tokens are ignored.

text_styles:
  # Each entry: font (registered font name), size (points), color (CSS color),
  # opacity (0–1), alignment (start|middle|end), size_rules (list, see below).
  heading:
    font: "RobotoCondensed-Bold"   # [all] primary heading font
    size: 12                        # base point size; overridden by size_rules
    color: "#333333"
    opacity: 1.0
    alignment: start
    size_rules:                     # conditional size by paper size [all]
      - font_size: 10
        when: { papersize: ["letter", "ledger", "tabloid"] }
      - font_size: 8
        when: { papersize: ["3x5", "5x8"] }

  body:
    font: "RobotoCondensed-Light"   # [all] event names, duration labels
    size: 10
    color: "#333333"

  body_italic:
    font: "RobotoCondensed-LightItalic"  # [all] notes lines
    size: 9
    color: "#666666"

  caption:
    font: "RobotoCondensed-Light"   # [all] dates, small labels
    size: 8
    color: "#666666"

  day_number:
    font: "RobotoCondensed-Bold"    # [weekly][mini] large digit in day box corner
    size: 11
    color: "#333333"

  week_number:
    font: "RobotoCondensed-Light"   # [weekly][mini] week label beside each row
    size: 9
    color: "#888888"

  month_title:
    font: "RobotoCondensed-Bold"    # [mini] month heading above mini grid
    size: 11
    color: "#333333"

box_styles:
  # Each entry: fill, fill_opacity, stroke, stroke_width, stroke_opacity,
  # stroke_dasharray (SVG dash string or null).
  default:
    fill: "white"
    fill_opacity: 1.0
    stroke: "none"

  cell:
    fill: "#F8F8FF"             # [weekly][mini] day cell default background
    fill_opacity: 0.25
    stroke: "none"
    stroke_width: 0.5
    stroke_opacity: 1.0

  header:
    fill: "none"                # [all] header/footer background
    stroke: "none"

  timeband:
    fill: "none"                # [blockplan] time band row background
    fill_opacity: 1.0
    stroke: "none"

  highlight:
    fill: "lightblue"           # [blockplan] vertical line column fill
    fill_opacity: 0.3
    stroke: "none"

  callout:
    fill: "white"               # [timeline] event callout box
    fill_opacity: 0.25
    stroke: "#CCCCCC"
    stroke_width: 1.0

line_styles:
  # Each entry: color, width (points), opacity (0–1), dasharray (SVG or null).
  grid:
    color: "#CCCCCC"            # [all] cell border and grid lines
    width: 0.5
    opacity: 0.5

  axis:
    color: "#AAAAAA"            # [timeline][blockplan] main axis line
    width: 2.0
    opacity: 0.9

  separator:
    color: "#CCCCCC"            # [mini_details] row separator lines
    width: 0.5
    opacity: 0.5

  today:
    color: "#FF4444"            # [all] today indicator line
    width: 1.5
    opacity: 1.0
    dasharray: null

  connector:
    color: "#888888"            # [timeline] dependency connector lines
    width: 0.5
    opacity: 1.0
    dasharray: "4 2"

icon_styles:
  # Each entry: color, size (points).
  event:
    color: "#333333"            # [all] point event icon
    size: 10

  duration:
    color: "#555555"            # [all] duration bar icon
    size: 10

  overflow:
    color: "red"                # [weekly][mini] overflow indicator icon
    size: 10

# ── Axis ─────────────────────────────────────────────────────────────────────
axis:
  line_style: axis              # references a line_styles token above
  tick:
    color: "#888888"            # [timeline][blockplan] tick mark color
    label_style: caption        # references a text_styles token
    date_format: "M/D"          # arrow date format string for tick labels
  today:
    line_style: today           # references a line_styles token
    label_color: "#FF4444"      # [all] "Today" label color
    label_text: "Today"         # [all] overridable label string

# ── Element bindings ─────────────────────────────────────────────────────────
# Maps CSS element classes to style tokens. Every ec-* class used by the
# renderers must appear here. Tokens must be defined in the sections above.
element_styles:
  # Text elements
  ec-heading:        { text_style: heading }      # section headings [all]
  ec-label:          { text_style: caption }      # generic small labels [all]
  ec-day-number:     { text_style: day_number }   # day box digit [weekly][mini]
  ec-month-title:    { text_style: month_title }  # mini calendar month heading
  ec-week-number:    { text_style: week_number }  # week number label [weekly][mini]
  ec-fiscal-label:   { text_style: caption }      # fiscal period label [weekly]
  ec-event-name:     { text_style: body }         # event/duration title [all]
  ec-event-notes:    { text_style: body_italic }  # notes line [all]
  ec-event-date:     { text_style: caption }      # point event date label [all]
  ec-duration-date:  { text_style: caption }      # duration start/end dates [all]
  ec-holiday-title:  { text_style: body }         # holiday name in day box [weekly][mini]
  ec-today-label:    { text_style: caption }      # "Today" axis label [timeline][blockplan]
  ec-header-text:    { text_style: heading }      # header left/center/right [all]
  ec-footer-text:    { text_style: caption }      # footer left/center/right [all]
  ec-watermark:      { text_style: heading }      # watermark text [all]

  # Box elements
  ec-background:     { box_style: default }       # page background [all]
  ec-cell:           { box_style: cell }          # day cell rectangle [weekly][mini]
  ec-day-box:        { box_style: cell }          # alias for ec-cell
  ec-heading-cell:   { box_style: header }        # blockplan lane heading cell
  ec-band-cell:      { box_style: timeband }      # blockplan time band cell
  ec-callout-box:    { box_style: callout }       # timeline event callout
  ec-vline-fill:     { box_style: highlight }     # blockplan vertical line column fill
  ec-pattern-fill:   { box_style: default }       # SVG pattern overlay rect [weekly][mini]

  # Line elements
  ec-grid-line:      { line_style: grid }         # cell grid lines [all]
  ec-axis-line:      { line_style: axis }         # timeline/blockplan axis
  ec-axis-tick:      { line_style: axis }         # axis tick marks
  ec-today-line:     { line_style: today }        # today vertical indicator [all]
  ec-separator:      { line_style: separator }    # mini_details row separators
  ec-connector:      { line_style: connector }    # timeline connectors
  ec-vline:          { line_style: grid }         # blockplan vertical lines
  ec-duration-bar:   { line_style: axis }         # duration bar stroke
  ec-hash-line:      { line_style: grid }         # legacy hash line stroke
  ec-strikethrough:  { line_style: grid }         # strikethrough on past events

  # Marker elements
  ec-milestone-marker: { line_style: axis }       # milestone diamond/flag
  ec-milestone-flag:   { line_style: axis }
  ec-duration-marker:  { line_style: axis }       # duration start/end cap

  # Icon elements
  ec-event-icon:     { icon_style: event }        # point event glyph [all]
  ec-duration-icon:  { icon_style: duration }     # duration bar glyph [all]
  ec-overflow-icon:  { icon_style: overflow }     # overflow indicator [weekly][mini]

  # Legend elements
  ec-legend-swatch:  { line_style: axis }         # legend color swatch [timeline][compact]
  ec-legend-text:    { text_style: body }
  ec-legend-icon:    { icon_style: event }

# ── General settings ─────────────────────────────────────────────────────────

base:
  font_family: "RobotoCondensed-Light"  # [all] fallback font when no token matches
  font_color: "#333333"                  # [all] fallback text color
  default_missing_icon: "applet-closed" # [all] icon shown when event icon not found
  size_rule:                             # [all] global font-size override by paper size
    - font_size: 10
      when: { papersize: ["letter", "ledger", "tabloid"] }
    - font_size: 8
      when: { papersize: ["3x5", "5x8"] }

header:
  font_family: "RobotoCondensed-Bold"   # [all] header left/center/right font
  font_color: "#333333"

footer:
  font_family: "RobotoCondensed-Light"  # [all] footer left/center/right font
  font_color: "#888888"

events:
  icon_color: "#333333"                 # [all] default point event icon color
  item_placement_order: ["milestones", "events", "durations"]
  # Controls row stacking order within a day box or lane.
  # Tokens: milestones | events | durations | priority | alphabetical

durations:
  icon_color: "#555555"                 # [all] default duration icon color
  stroke_dasharray: null                # [all] duration bar dash; null = solid

watermark:
  text: null                            # [all] watermark string; null disables
  color: "#AAAAAA"
  font_family: "RobotoCondensed-Light"
  opacity: 0.3
  font_size: null                       # null = auto-fit to page
  resize_mode: "fit"                    # fit | fill | fixed
  rotation_angle: 45.0                  # degrees clockwise
  image_rotation_angle: 45.0           # rotation when watermark is an image

fiscal:
  fiscal_year_start_month: 1
  # [weekly][blockplan] Calendar month the fiscal year begins (1=Jan … 12=Dec).
  # Used to align fiscal period boundaries and quarter labels.
  # Common values: 1 (calendar year), 2 (NRF retail), 10 (US federal).
  label_format: "{prefix}{period_short}"       # [weekly][blockplan] period start label
  end_label_format: "{period_short} End"        # [weekly][blockplan] period end label
  year_offset: 0
  # Fiscal year number relative to start calendar year:
  #   0  = start year  (FY starting Feb 2026 → FY2026)
  #  +1  = start year + 1  (FY starting Oct 2025 → FY2026, US federal default)
  #  -1  = start year − 1

# ── Colors ───────────────────────────────────────────────────────────────────

colors:
  month_palette: "Pastel1"
  # [all] DB palette name — 12 colors sampled and mapped to calendar months.
  # Resolved at render time via db.sample_palette_n(name, 12).

  fiscal_palette: "Greys"
  # [weekly][blockplan] DB palette name — 13 colors mapped to fiscal periods.

  group_palette: "Set2"
  # [blockplan][timeline][compact] DB palette name — cycled by resource group.

  hash_lines: "#333333"
  # [weekly][mini] default color for legacy hash line strokes.

  federal_holiday:
    color: "tomato"           # [weekly][mini][blockplan] day box fill for fed holidays
    alpha: 0.15               # fill opacity

  company_holiday:
    color: "gold"             # [weekly][mini][blockplan] day box fill for company holidays
    alpha: 0.20               # fill opacity

  resource_groups:            # [blockplan][timeline] explicit group → color overrides
    # group_name: "css-color"
    # Unlisted groups cycle through group_palette.

# ── Weekly calendar ───────────────────────────────────────────────────────────

weekly:
  day_names:
    font_family: "RobotoCondensed-Light"  # [weekly] day-of-week header labels
    font_color: "#666666"

  week_numbers:
    font_family: "RobotoCondensed-Light"  # [weekly] week number label
    font_color: "#888888"
    label_format: "W{num:02d}"           # format string; {num} = ISO week number

  day_box:
    stroke_color: "#CCCCCC"      # [weekly] day cell border color
    stroke_opacity: 0.5          # [weekly] day cell border opacity
    stroke_width: 0.5            # [weekly] day cell border width (points)
    stroke_dasharray: null       # [weekly] null = solid border
    fill_color: "#F8F8FF"        # [weekly] default fill when no month color set
    fill_opacity: 0.25
    number_font: "RobotoCondensed-Bold"   # [weekly] day number digit font
    number_color: "#333333"               # [weekly] day number digit color
    icon_color: "#333333"                 # [weekly] icon color inside day box
    font_color: "#333333"                 # [weekly] general text inside day box
    hash_pattern_opacity: 0.15           # [weekly] global default pattern opacity

  name_text:                    # [weekly] event/duration name line
    font_name: "RobotoCondensed-Light"
    font_color: "#333333"

  notes_text:                   # [weekly] event/duration notes line
    font_name: "RobotoCondensed-LightItalic"
    font_color: "#666666"

  overflow:
    icon: "overflow"            # [weekly] icon shown when events exceed day box
    color: "red"

# ── Timeline ──────────────────────────────────────────────────────────────────

timeline:
  background_color: "none"      # [timeline] page background; none = transparent
  axis_color: "#AAAAAA"         # [timeline] main horizontal axis color
  axis_opacity: 0.9
  axis_width: 2.0
  tick_color: "#888888"         # [timeline] tick mark color
  date_format: "M/D"            # [timeline] tick label date format (arrow)
  tick_label_format: "M/D"
  today_line_color: "#FF4444"   # [timeline] today vertical line color
  today_label_color: "#FF4444"
  today_label_text: "Today"
  today_label_offset_y: 10.0    # [timeline] vertical offset of "Today" label (points)
  marker_stroke_color: "#333333" # [timeline] milestone marker outline
  marker_stroke_width: 1.0
  marker_radius: 4.0            # [timeline] milestone circle radius (points)
  icon_size: 8                  # [timeline] event icon size (points)
  callout_offset_y: 30.0        # [timeline] vertical gap between axis and callout box
  duration_offset_y: 30.0       # [timeline] gap between axis and duration rows
  duration_lane_gap_y: 8.0      # [timeline] gap between stacked duration rows
  label_stroke_width: 1.0       # [timeline] callout box border width
  label_fill_opacity: 0.25      # [timeline] callout box fill opacity
  duration_bar_fill_opacity: 0.75 # [timeline] duration bar fill opacity
  axis_stroke_dasharray: null
  tick_stroke_dasharray: null
  today_line_dasharray: null
  label_stroke_dasharray: null
  duration_bar_stroke_dasharray: null
  connector_stroke_dasharray: "4 2"
  duration_bracket_stroke_dasharray: null
  top_colors: []                # [timeline] explicit color list for top-lane durations
  bottom_colors: []             # [timeline] explicit color list for bottom-lane durations
  name_text:
    font_name: "RobotoCondensed-Light"    # [timeline] event/duration name
    font_color: "#333333"
  notes_text:
    font_name: "RobotoCondensed-LightItalic"  # [timeline] notes line
    font_color: "#666666"
  date:
    font_family: "RobotoCondensed-Light"  # [timeline] date label beside markers
    font_color: "#666666"

timeline_events:
  box_height: 24                # [timeline] callout box height (points)

timeline_durations:
  box_height: 24                # [timeline] duration row height (points)
  date_font: "RobotoCondensed-Light"
  date_font_size: 9
  date_color: "#666666"

# ── Block plan ────────────────────────────────────────────────────────────────

blockplan:
  background_color: "none"       # [blockplan] page background
  grid_color: "#CCCCCC"          # [blockplan] cell grid line color
  grid_opacity: 0.5
  grid_line_width: 0.5
  grid_dasharray: null

  timeband_fill_color: ["white", "#F0F0F0"]
  # [blockplan] alternating fill colors for time band segments (list or single color)

  timeband_fill_opacity: 1.0
  timeband_line_color: null      # null → inherits grid_color
  timeband_line_width: null      # null → inherits grid_line_width
  timeband_line_opacity: null    # null → inherits grid_opacity
  timeband_line_dasharray: null

  label_column_ratio: 0.08       # [blockplan] fraction of total width for lane label column
  band_row_height: 20.0          # [blockplan] default time band row height (points)
  fiscal_year_start_month: 1     # [blockplan] fiscal year start month (1=Jan)
  week_start: 0                  # [blockplan] 0=Monday, 6=Sunday
  duration_date_font_size: 8     # [blockplan] font size for start/end date labels

  show_unmatched_lane: false     # [blockplan] show a lane for events matching no swimlane_rule
  unmatched_lane_name: "Other"   # [blockplan] name of the unmatched catch-all lane
  lane_match_mode: "first"       # [blockplan] first = first swimlane_rule wins; all = multi-lane

  header_font: "RobotoCondensed-LightItalic"  # [blockplan] time band header font
  header_font_size: 10
  header_label_color: "#666666"  # [blockplan] time band header label text color
  header_label_opacity: 1.0
  header_label_align_h: "left"   # [blockplan] left | center | right
  header_heading_fill_color: "none"  # [blockplan] heading column cell fill

  band_font: "RobotoCondensed-Light"  # [blockplan] time band segment label font
  band_font_size: 10
  timeband_label_opacity: 1.0

  federal_holiday_fill_color: "tomato"   # [blockplan] non-workday cell fill — federal
  company_holiday_fill_color: "gold"     # [blockplan] non-workday cell fill — company
  weekend_fill_color: "#E8E8E8"          # [blockplan] non-workday cell fill — weekend

  lane_split_ratio: 0.5
  # [blockplan] position of events/durations divider within each lane (0.0–1.0).
  # 0.0 or 1.0 removes the divider. Overridden per-lane in swimlanes[].

  lane_heading_fill_color: "none"        # [blockplan] default lane heading cell background
  lane_label_font_size: 12              # [blockplan] lane label font size
  lane_label_color: "#333333"           # [blockplan] lane label text color
  lane_label_align_h: "center"          # [blockplan] left | center | right
  lane_label_align_v: "middle"          # [blockplan] top | middle | bottom
  lane_label_rotation: -90              # [blockplan] degrees; 0=horizontal, -90=bottom-to-top

  duration_date_font: "RobotoCondensed-LightItalic"  # [blockplan] start/end date font
  duration_fill_opacity: 1.0
  duration_stroke_color: "white"        # [blockplan] duration bar outline color
  duration_stroke_width: 1.0
  duration_stroke_opacity: 1.0
  duration_stroke_dasharray: null
  duration_bar_height: 20               # [blockplan] duration bar height (points)
  duration_icon_visible: true           # [blockplan] show icon at start of duration bar
  duration_show_start_date: true        # [blockplan] print start date beside bar
  duration_show_end_date: true          # [blockplan] print end date beside bar
  duration_date_format: "M/D"          # [blockplan] arrow format for start/end dates
  duration_date_color: "#666666"
  event_show_date: false                # [blockplan] print date beside milestone marker
  event_date_font: "RobotoCondensed-LightItalic"
  event_date_font_size: null            # null = inherits band_font_size
  event_date_color: "#666666"
  event_date_format: "MM/DD"
  marker_radius: 3.0                    # [blockplan] milestone marker radius (points)

  name_text:
    font_name: "RobotoCondensed-Light"  # [blockplan] event/duration name text
    font_color: "#333333"
  notes_text:
    font_name: "RobotoCondensed-LightItalic"  # [blockplan] notes line
    font_color: "#666666"

  # Lane visual definitions — routing is in swimlane_rules below.
  swimlanes: []
  # Each entry:
  #   name (str)                  — displayed in the heading cell; must match apply_to in swimlane_rules
  #   fill_color (str|null)       — heading cell background; null = lane_heading_fill_color
  #   label_color (str|null)      — label text color; null = lane_label_color
  #   timeline_fill_color (str)   — content area background tint; "none" = transparent
  #   label_align_h (str)         — left | center | right
  #   label_align_v (str)         — top | middle | bottom
  #   split_ratio (float)         — per-lane override of lane_split_ratio

  top_time_bands: []
  # [blockplan] Ordered list of time band rows above the swim lanes.
  # Each entry:
  #   label (str)                 — heading cell text; used as band identifier in vertical_lines
  #   unit (str)                  — fiscal_quarter | month | week | date | countdown
  #   date_format (str)           — arrow format string for segment labels
  #   label_format (str)          — template for fiscal/countdown labels
  #   fill_color (str|list)       — segment fill; list = alternating colors
  #   row_height (float)          — row height in points; overrides band_row_height
  #   show_every (int)            — label every Nth segment (1 = all)
  #   label_color (str)           — heading column label color
  #   font_color (str)            — segment content label color
  #   excel_font_name (str)       — ExcelHeader font override for this band
  #   excel_font_size (int)       — ExcelHeader font size override

  bottom_time_bands: []         # [blockplan] same structure as top_time_bands; rendered below lanes

  vertical_lines: []
  # [blockplan] Vertical line and column-fill rules pinned to time band segments.
  # Each entry:
  #   band (str)                  — time band label to pin to (case-insensitive)
  #   align (str)                 — start | center | end within segment
  #   repeat (bool)               — true = apply to every segment; omit value when true
  #   value (str)                 — segment label to match (required when repeat absent)
  #   color (str)                 — line color
  #   width (float)               — line width (points)
  #   opacity (float)             — line opacity
  #   dash_array (str|null)       — SVG dash pattern; null = solid
  #   fill_color (str|list)       — column fill color; list = alternating per segment
  #   fill_opacity (float)        — fill opacity
  #   match (dict)                — day classification filter: weekend, federal_holiday,
  #                                  company_holiday, nonworkday (bool values)

# ── Mini calendar ─────────────────────────────────────────────────────────────

mini_calendar:
  cell_font: "RobotoCondensed-Light"    # [mini] day number font
  cell_bold_font: "RobotoCondensed-Bold"  # [mini] bold day number (milestone days)
  cell_font_size: null           # null = auto from base size_rule
  title_font: "RobotoCondensed-Bold"    # [mini] month heading font
  title_font_size: null
  title_format: "MMMM YYYY"     # [mini] arrow format for month heading
  title_color: "#333333"
  header_font: "RobotoCondensed-Light"  # [mini] day-of-week column header font
  header_font_size: null
  header_color: "#888888"
  day_number_glyphs: null        # [mini] custom glyph set for day digits; null = standard
  day_number_digits: null        # [mini] digit override list (e.g. Arabic-Indic numerals)
  day_color: "#333333"           # [mini] default day number color
  adjacent_month_color: "#CCCCCC"  # [mini] color for days from adjacent months
  show_adjacent: true            # [mini] render adjacent-month days in first/last week
  holiday_color: "red"           # [mini] federal holiday day number color
  nonworkday_fill_color: "#E8E8E8"  # [mini] company holiday / non-workday cell fill
  milestone_color: "#333333"    # [mini] day number color when day has a milestone
  circle_milestones: true        # [mini] draw circle around milestone day numbers
  milestone_stroke_color: "#333333"
  milestone_stroke_width: 1.0
  milestone_stroke_opacity: 1.0
  current_day_color: "lightblue" # [mini] fill for today's cell
  week_number_font: "RobotoCondensed-Light"  # [mini] week number label font
  week_number_font_size: null
  week_number_color: "#AAAAAA"
  week_number_label_format: "W{num}"  # {num} = ISO week number
  grid_line_color: "#DDDDDD"    # [mini] cell grid line color
  grid_line_width: 0.25
  grid_line_opacity: 0.5
  grid_line_dasharray: null
  cell_box_stroke_dasharray: null     # [mini] day cell border dash
  strikethrough_stroke_dasharray: null  # [mini] past-event strikethrough dash
  hash_line_dasharray: null           # [mini] legacy hash line dash (deprecated)
  duration_bar_stroke_dasharray: null
  duration_bar_stroke_opacity: null

# ── Mini details ──────────────────────────────────────────────────────────────

mini_details:
  title_text: "Event Details"          # [mini] section heading text
  title_font: "RobotoCondensed-Bold"
  title_font_size: null
  title_color: "#333333"
  header_font: "RobotoCondensed-Bold"  # [mini] column header font
  header_font_size: null
  header_color: "#888888"
  name_text:
    font_name: "RobotoCondensed-Light"
    font_color: "#333333"
  notes_text:
    font_name: "RobotoCondensed-LightItalic"
    font_color: "#666666"
  separator_stroke_dasharray: null
  headers:                             # [mini] column header labels (ordered list)
    - "Start Date"
    - "Name / Description"
    - "Milestone"
    - "Priority"
    - "Group"
  column_widths: [0.16, 0.52, 0.10, 0.10, 0.12]
  # [mini] fractional column widths (must sum to 1.0)

# ── Text mini ─────────────────────────────────────────────────────────────────

text_mini:
  cell_width: 2                  # [text_mini] character width per day cell
  month_gap: 4                   # [text_mini] blank lines between months
  week_number_digits: null       # [text_mini] digits for week numbers; null = standard
  day_number_digits: null        # [text_mini] digits for day numbers; null = standard
  event_symbols: null            # [text_mini] symbol list for events; null = default
  milestone_symbols: null        # [text_mini] symbol list for milestones
  holiday_symbols: null          # [text_mini] symbol list for holidays
  nonworkday_symbols: null       # [text_mini] symbol list for non-workdays
  duration_symbols: null         # [text_mini] symbol list for duration spans
  duration_fill: null            # [text_mini] fill character for duration spans

# ── Excel header ──────────────────────────────────────────────────────────────

excelheader:
  font_name: "Calibri"           # [excelheader] default Excel font for all cells
  font_size: 9                   # [excelheader] default font size (points)
  # Per-band font overrides are set inline in blockplan.top_time_bands entries
  # using excel_font_name and excel_font_size keys.

# ── Compact plan ──────────────────────────────────────────────────────────────

compact_plan:
  palette: null                  # [compact] explicit color list; null = built-in defaults
  palette_name: null             # [compact] DB palette name; overrides palette list
  axis_color: "#AAAAAA"          # [compact] axis line color
  axis_dasharray: "2 6"
  axis_opacity: 0.5
  axis_padding: 5.0              # [compact] gap (points) from axis to nearest duration row
  axis_width: 1.0
  show_axis: true
  milestone_color: "#333333"     # [compact] milestone marker color
  header_bottom_y: 8.0           # [compact] gap below header band block (points)
  key_top_y: 8.0                 # [compact] gap above legend/key block (points)
  band_row_height: 10.0          # [compact] time band row height (points)
  duration_line_width: 5.0       # [compact] duration line thickness (points)
  duration_opacity: 1.0
  duration_stroke_dasharray: null
  lane_spacing: 6.0              # [compact] vertical gap between stacked duration rows
  show_duration_icons: true      # [compact] draw icon at start of each duration line
  duration_icon_list: "darksquare"  # [compact] icon set name (darksquare|squares|darkcircles|…)
  duration_icon_height: 5.0
  duration_icon_color: null      # null = use line color
  milestone_flag_height: 9.0     # [compact] milestone flag stem height (points)
  milestone_flag_width: 7.0      # [compact] milestone pennant width (points)
  milestone_icon: null           # [compact] icon name; null = draw built-in flag shape
  show_milestone_labels: false   # [compact] render task name beside marker
  legend_column_split: 0.5       # [compact] fraction of width for legend column
  show_legend: true
  legend_row_height: 10.0
  legend_swatch_width: 10.0
  show_milestone_list: true      # [compact] render date-sorted milestone roster
  milestone_list_date_format: "M/D"
  milestone_list_date_color: "#333333"
  milestone_list_row_height: 10.0
  milestone_list_date_col_width: 32.0
  milestone_list_section_gap: 6.0
  show_continuation_icon: true   # [compact] icon when duration extends past view edge
  continuation_icon: "move-right"
  continuation_icon_height: 8.0
  continuation_icon_color: null  # null = use line color
  continuation_legend_text: "activity continues"
  continuation_section_gap: 4.0
  text:
    font_name: "RobotoCondensed-Light"  # [compact] general text font
    font_color: "#333333"
    font_opacity: 1.0
  name_text:
    font_name: "RobotoCondensed-Light"  # [compact] milestone label font
    font_color: "#595959"
    font_opacity: 1.0
  time_bands: []                 # [compact] same structure as blockplan.top_time_bands

# ══════════════════════════════════════════════════════════════════════════════
# Style rules — visual styling for day boxes, events, and durations.
# See RuleRedesign.md for full select:/style: reference.
# Rules are evaluated in declaration order; later rules layer over earlier ones.
# ══════════════════════════════════════════════════════════════════════════════

style_rules: []

# ══════════════════════════════════════════════════════════════════════════════
# Swimlane rules — blockplan lane routing only.
# apply_to is the lane name string (must match a name in blockplan.swimlanes).
# First matching rule wins. Empty select: {} is a catch-all.
# ══════════════════════════════════════════════════════════════════════════════

swimlane_rules: []
```

#### Authoring guidelines for the reference file

- Every key at every nesting level has a comment on the same line or the line above. The comment states the visualizers it affects in brackets (`[all]`, `[weekly]`, `[blockplan]`, etc.), accepted value types, and any constraint (e.g., "must sum to 1.0", "null = auto").
- Keys that accept a DB palette name note that resolution happens at render time.
- Deprecated paths (`hash_rules`, `swimlanes.match`) do not appear anywhere in the file.
- `style_rules: []` and `swimlane_rules: []` appear as empty lists with the block comment above them, so the structure is visible even when no rules are defined.
- The file is validated against `ThemeEngine` on every CI run using `uv run python -m pytest tests/test_reference_theme.py` to guarantee it parses without error and that all element class references resolve.

---

### Phase 1 — Migrate existing theme YAML files

**New script:** `tools/migrate_theme.py`

Converts all existing theme files in `config/themes/` from the old per-visualizer rule keys to `style_rules` in a single pass. Run once before any other phase. The script reads each YAML file, transforms the old keys, removes them, and writes the result back in place (or to a new path with `--output-dir`).

#### Conversions performed

**`weekly.day_box.hash_rules` → `style_rules`**

Each hash rule becomes a `style_rules` entry with `apply_to: day_box`. The `when:` block becomes `select:`, and pattern/color/opacity move into `style:`.

```yaml
# BEFORE
weekly:
  day_box:
    hash_rules:
      - pattern: diagonal-stripes
        color: gold
        opacity: 0.15
        when:
          milestone: true
      - pattern: diagonal-stripes
        color: tomato
        opacity: 0.12
        when:
          federal_holiday: true

# AFTER
style_rules:
  - name: "hash_rule_0"
    select:
      milestone: true
    apply_to: day_box
    style:
      pattern: diagonal-stripes
      pattern_color: gold
      pattern_opacity: 0.15
  - name: "hash_rule_1"
    select:
      federal_holiday: true
    apply_to: day_box
    style:
      pattern: diagonal-stripes
      pattern_color: tomato
      pattern_opacity: 0.12
```

**`mini_calendar.day_box.hash_rules` → `style_rules`**

Same conversion as above; generated entries get `apply_to: day_box` (the mini renderer reads the same `style_rules` list filtered by target).

**`blockplan.swimlanes[].match` → `swimlane_rules`**

Each swimlane's `match:` block becomes a `swimlane_rules` entry where `apply_to` is the lane name string. The visual properties of the lane (`fill_color`, `label_color`, `timeline_fill_color`, `split_ratio`, `label_align_h`, `label_align_v`) are left untouched in `blockplan.swimlanes` — only the `match:` key is removed from each lane entry.

```yaml
# BEFORE
blockplan:
  swimlanes:
    - name: "Xstore\nConversions"
      fill_color: none
      label_color: red
      label_align_h: center
      split_ratio: 0.5
      match:
        resource_groups: ["Xstore"]

# AFTER
swimlane_rules:
  - name: "Route Xstore"
    select:
      resource_group: ["Xstore"]
    apply_to: "Xstore\nConversions"

blockplan:
  swimlanes:
    - name: "Xstore\nConversions"   # match: key removed; visual props unchanged
      fill_color: none
      label_color: red
      label_align_h: center
      split_ratio: 0.5
```

#### Keys removed after migration

The following YAML keys are deleted from theme files and are no longer read by the theme engine:

- `weekly.day_box.hash_rules`
- `mini_calendar.day_box.hash_rules`
- `blockplan.swimlanes[].match` (routing lifted to `swimlane_rules`; lane visual props stay)
- `config.theme_weekly_hash_rules` (internal config field, removed)
- `config.theme_mini_day_box_hash_rules` (internal config field, removed)

#### ThemeEngine error on old keys

After migration, `ThemeEngine.apply()` raises `ThemeValidationError` if it encounters `weekly.day_box.hash_rules` or `blockplan.swimlanes[].match` in a loaded YAML, so stale unconverted themes fail loudly.

---

### Phase 2 — Shared rule evaluators

**New file:** `shared/rule_engine.py`

Two separate engines with a shared `select:` evaluator underneath.

```python
@dataclass
class StyleResult:
    # Fill
    fill_color: str | None = None
    fill_opacity: float | None = None
    # Pattern
    pattern: str | None = None
    pattern_color: str | None = None
    pattern_opacity: float | None = None
    # Stroke
    stroke_color: str | None = None
    stroke_width: float | None = None
    stroke_opacity: float | None = None
    stroke_dasharray: str | None = None
    # Text — per element (keyed by text element name)
    text: dict[str, TextStyle] | None = None
    # Icon
    icon: str | None = None
    icon_color: str | None = None


class StyleEngine:
    """Evaluates style_rules; results layer additively in declaration order."""
    def __init__(self, rules: list[dict]): ...

    def evaluate_day(self, day_context: DayContext) -> StyleResult:
        """Layer all matching rules for a day; None fields left unset."""

    def evaluate_event(self, event: Event, day_context: DayContext | None = None) -> StyleResult:
        """Layer all matching rules for a single event or duration."""


class LaneEngine:
    """Evaluates swimlane_rules; first-match wins."""
    def __init__(self, rules: list[dict]): ...

    def assign(self, event: Event, day_context: DayContext | None = None) -> str | None:
        """Return the lane name for the first matching rule, or None if unmatched."""
```

`StyleResult` fields are `None` by default — `None` means "not overridden; use the theme or renderer default." Rules layer additively: a later rule that sets `pattern_color` does not clear `fill_color` set by an earlier rule.

`TextStyle` within `StyleResult.text` follows the same None-means-inherit pattern per field (`font`, `font_size`, `font_color`, `font_opacity`).

Both engines share a private `_matches(rule_select, event, day_context) -> bool` function so that criteria evaluation logic is written exactly once.

---

### Phase 3 — Wire renderers to consume `StyleResult` and `LaneEngine`

Replace per-visualizer ad-hoc coloring and routing logic:

| Renderer | `StyleEngine` replaces | `LaneEngine` replaces |
|---|---|---|
| `visualizers/weekly/renderer.py` | `_resolve_day_hash_decorations()`, `_resolve_day_box_fill()`, per-event color lookup | — |
| `visualizers/mini/renderer.py` | `_apply_holidays()`, `_apply_special_days()`, hash decoration loop | — |
| `visualizers/blockplan/renderer.py` | Duration/event color palette cycling | `_assign_events_to_lanes()` |
| `visualizers/timeline/renderer.py` | Event/duration fill and text color resolution | — |

Each renderer constructs the appropriate `DayContext` and/or `Event`, calls `StyleEngine.evaluate_day()` or `evaluate_event()`, and applies non-`None` fields from `StyleResult` over the renderer's built-in defaults. The blockplan renderer additionally calls `LaneEngine.assign()` for each event before placing it.

---

### Phase 4 — Remove legacy config fields and theme engine code

Delete from `config/config.py`:
- `theme_weekly_hash_rules`
- `theme_mini_day_box_hash_rules`
- `DayHashContext` dataclass (absorbed into `DayContext` used by `RuleEngine`)

Delete from `config/theme_engine.py`:
- All fanout code that populated the above fields
- The `THEME_TO_CONFIG_MAP` entries for the removed fields

Update `tests/` to remove any references to the deleted fields and add coverage for `RuleEngine.evaluate_day()` and `evaluate_event()`.

---

## Date Range Matching

The `date` criterion is evaluated against the **day being rendered** for `apply_to: day_box`, and against the **event's start date** for `apply_to: event` / `duration`.

### Formats

| Format | Example | Meaning |
|---|---|---|
| Single date | `"20190321"` | Exactly that calendar day |
| Closed range | `"20190301-20190321"` | Start and end inclusive |
| List | `["20190101", "20190704", "20191225"]` | Any of the listed dates |

### Interaction with event-level criteria

When `date` is combined with event criteria (e.g., `resource_group`), the semantics follow the `any_event` / `all_events` aggregation modifiers for `day_box` targets:

```yaml
# Day box is decorated if it falls in the range AND any event on that day
# belongs to the Xstore group.
- name: "Xstore days in freeze"
  select:
    date: "20190301-20190321"
    resource_group: ["Xstore"]
  apply_to: day_box
  style:
    pattern: diagonal-stripes
    pattern_color: steelblue
```

For `apply_to: event` / `duration`, the date criterion tests the event's own start date — it does **not** test whether the event *spans* the date. To match durations that overlap a date range (rather than start within it), use `date_overlap: true`:

```yaml
- name: "Durations overlapping freeze"
  select:
    date: "20190301-20190321"
    date_overlap: true        # match if any part of the duration falls in range
    event_type: duration
  apply_to: duration
  style:
    fill_color: steelblue
```

### Implementation note

Date parsing uses `YYYYMMDD` strings throughout the codebase (same format as `Event.start` / `Event.end` and `DayHashContext`). The rule evaluator splits on `-` at position 8 to distinguish a range (`len == 17`) from a single date (`len == 8`). List form is a YAML sequence and requires no special parsing.

---

## Key Tradeoffs

**Day-box vs event-level context split:** `style_rules` with `apply_to: day_box` aggregate across all events on a day before evaluating (same as the old hash_rules). Event-level rules match one event at a time. When a rule targets both `day_box` and `event`, the engine runs two passes — one per event to produce `StyleResult` for that event, one per day (aggregating events) to produce `StyleResult` for the day box. The `any_event`/`all_events` modifiers control the aggregation.

**Two rule lists instead of one:** `style_rules` and `swimlane_rules` share the same `select:` syntax but have different `apply_to` semantics (visual target type vs lane name string). This is a small cognitive cost, but it eliminates the conceptual mismatch of hiding a routing directive inside a visual style block, and it lets the two concerns evolve independently — e.g., adding a `priority` sorting modifier to `swimlane_rules` without touching `style_rules`.
