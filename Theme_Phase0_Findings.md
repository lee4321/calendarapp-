# Theme simplification: Phase 0 findings

## Baseline (before any change)

- Test suite: 1,815 passed.
- Refcorpus: 973 files rendered into `output/_refcorpus` (default, dark and corporate themes). `tools/refcorpus.sh check` passes, so the render is deterministic. A copy is kept in `output/_refcorpus_phase0` as the before-picture. `output/` is gitignored.
- `tools/refcorpus.sh` renders three themes. Dark and corporate are deleted in Phase 4, so the script needs its theme list cut to `default` then.

## CLI audit

The CLI has no flags for today, axis, ticks, bands, leaders, palettes or holiday icons. Those exist only as theme keys, so decision 10 (view-independent flags) touches few flags.

| Flag | Registered on | Finding |
|---|---|---|
| `--fiscal TYPE` | 10 SVG/text views | Already view-independent. Its help text mentions `theme timeline.show_fiscal_*`, which goes away. |
| `--fiscal-year-offset N` | same 10 | Already view-independent, and in `_CLI_CONFIG_OVERRIDES`. |
| `--direction` | pit (dest `direction`) and timeline (dest `timeline_direction`) | Same flag, two destinations, two config fields (`pit_direction`, `timeline_orientation`). One shared axis orientation is the view-independent form. |
| `--weeknumbers`, `--week-number-mode`, `--week1-start` | weekly, mini, mini-icon, text-mini | Calendar maths and display switches, not decoration. No change planned. |
| `--monthnames` | weekly | Weekly-only display switch. Structure; stays. |
| `--candybar-*`, `--mini-columns`, `--mini-rows` | one view each | Structure; stay. |
| `--details-md`, `--csv`, `--icons` and their `--no-*` forms | 10 views | Run output switches, already view-independent. |

Result: the CLI work is small. Only `--direction` needs merging, and the `--fiscal` help text needs rewriting.

## default.yaml inventory

485 leaf values in 26 top-level sections.

| Section | Leaf values | Decoration-named keys | Class |
|---|---:|---:|---|
| `theme` | 3 | 0 | global/other |
| `base` | 4 | 3 | global/other |
| `events` | 2 | 1 | global/other |
| `durations` | 4 | 3 | global/other |
| `watermark` | 7 | 3 | global/other |
| `continuation` | 5 | 5 | global/other |
| `overflow` | 1 | 1 | global/other |
| `details` | 84 | 20 | global/other |
| `fiscal` | 3 | 3 | global/other |
| `colors` | 8 | 8 | global/other |
| `weekly` | 3 | 3 | view |
| `mini_calendar` | 21 | 16 | view |
| `text_mini` | 10 | 8 | view |
| `candybar` | 21 | 11 | view |
| `timeline` | 31 | 27 | view |
| `timeline_events` | 7 | 0 | view |
| `timeline_durations` | 3 | 1 | view |
| `pit` | 82 | 69 | view |
| `compact_plan` | 16 | 12 | view |
| `blockplan` | 44 | 29 | view |
| `gantt` | 71 | 33 | view |
| `time_bands` | 29 | 29 | global/other |
| `excelblockplan` | 4 | 4 | view |
| `layout` | 4 | 0 | global/other |
| `style_rules` | 1 | 0 | global/other |
| `element_overrides` | 17 | 9 | global/other |

### Decoration-named keys inside view sections (candidates to move to the shared decoration blocks)

#### `weekly` (3 of 3)

- `weekly.number_duration_icons` = `True`
- `weekly.week_numbers.label_format` = `'W{num:02d}'`
- `weekly.day_box.hash_pattern_opacity` = `0.1`

#### `mini_calendar` (16 of 21)

- `mini_calendar.number_duration_icons` = `True`
- `mini_calendar.cell_bold_font` = `'OfficinaSans-Book'`
- `mini_calendar.cell_font_size` = `None`
- `mini_calendar.title_font_size` = `None`
- `mini_calendar.header_font_size` = `None`
- `mini_calendar.day_number_glyphs` = `None`
- `mini_calendar.day_number_digits` = `None`
- `mini_calendar.adjacent_month_color` = `'lightgrey'`
- `mini_calendar.holiday_color` = `'red'`
- `mini_calendar.nonworkday_fill_color` = `'lightblue'`
- `mini_calendar.milestone_color` = `'navy'`
- `mini_calendar.milestone_stroke_color` = `'navy'`
- `mini_calendar.current_day_color` = `'lightblue'`
- `mini_calendar.week_number_font_size` = `12`
- `mini_calendar.week_number_label_format` = `'W{num}'`
- `mini_calendar.event_icon_opacity` = `0.6`

#### `text_mini` (8 of 10)

- `text_mini.week_number_digits` = `None`
- `text_mini.day_number_digits` = `None`
- `text_mini.event_symbols` = `['⯍', '⟠', '⨷', '✢', '🞭', '🞹', '🮻', '🯀', '🞿', '🟈', '❖', '◊', '𜱪', '🟃', '🟎', '🟉', '⯌', '🟒', '🟋', '🞻', '🞯', '🟂', '🟐', '⭐', '🃟', '⊛'
- `text_mini.milestone_symbols` = `['🄰', '🄱', '🄲', '🄳', '🄴', '🄵', '🄶', '🄷', '🄸', '🄹', '🄺', '🄻', '🄼', '🄽', '🄾', '🄿', '🅀', '🅁', '🅂', '🅃', '🅄', '🅅', '🅆', '🅇', '🅈',
- `text_mini.holiday_symbols` = `['🅰', '🅱', '🅲', '🅳', '🅴', '🅵', '🅶', '🅷', '🅸', '🅹', '🅺', '🅻', '🅼', '🅽', '🅾', '🅿', '🆀', '🆁', '🆂', '🆃', '🆄', '🆅', '🆆', '🆇', '🆈', '
- `text_mini.nonworkday_symbols` = `['𝒂', '𝒃', '𝒄', '𝒅', '𝒆', '𝒇', '𝒈', '𝒉', '𝒊', '𝒋', '𝒌', '𝒍', '𝒎', '𝒏', '𝒐', '𝒑', '𝒒', '𝒓', '𝒔', '𝒕', '𝒖', '𝒗', '𝒘', '𝒙', '𝒚'
- `text_mini.duration_symbols` = `None`
- `text_mini.duration_fill` = `None`

#### `candybar` (11 of 21)

- `candybar.number_duration_icons` = `True`
- `candybar.grid_line_color` = `'lightgrey'`
- `candybar.weekend_fill` = `None`
- `candybar.weekend_opacity` = `0.25`
- `candybar.month_shade_opacity` = `0.12`
- `candybar.month.font` = `'OfficinaSans-Book'`
- `candybar.month.color` = `'navy'`
- `candybar.month.opacity` = `1.0`
- `candybar.month_box.fill` = `None`
- `candybar.month_box.stroke` = `'lightgrey'`
- `candybar.month_box.opacity` = `1.0`

#### `timeline` (27 of 31)

- `timeline.number_duration_icons` = `True`
- `timeline.leader.direct` = `True`
- `timeline.leader.start_stub` = `4.0`
- `timeline.leader.end_stub` = `4.0`
- `timeline.show_holiday_icons` = `True`
- `timeline.holiday_icon_size` = `10.0`
- `timeline.holiday_icon_color` = `None`
- `timeline.holiday_icon_y_offset` = `5.0`
- `timeline.show_holiday_dates` = `True`
- `timeline.holiday_date_format` = `'M/D'`
- `timeline.holiday_date_font_size` = `None`
- `timeline.holiday_date_color` = `None`
- `timeline.tick_label_gap` = `None`
- `timeline.tick_label_offset_y` = `None`
- `timeline.axis_width` = `3`
- `timeline.date_format` = `'M/D'`
- `timeline.tick_label_format` = `'M/D'`
- `timeline.today_date` = `''`
- `timeline.today_label_text` = `'Today'`
- `timeline.today_label_offset_y` = `5.0`
- `timeline.today_line_color` = `'grey'`
- `timeline.marker_stroke_color` = `''`
- `timeline.marker_stroke_width` = `1.0`
- `timeline.marker_radius` = `4.0`
- `timeline.icon_size` = `8`
- `timeline.label_fill_opacity` = `0.25`
- `timeline.palette` = `'colorblind2'`

#### `timeline_durations` (1 of 3)

- `timeline_durations.date_font_size` = `9`

#### `pit` (69 of 82)

- `pit.number_duration_icons` = `True`
- `pit.axis.color` = `'lightgrey'`
- `pit.axis.width` = `1.5`
- `pit.axis.marker_size` = `7.0`
- `pit.axis.marker_start` = `'none'`
- `pit.axis.marker_start_size` = `4.0`
- `pit.axis.marker_end` = `'arrow-head'`
- `pit.axis.marker_end_size` = `8`
- `pit.tick_color` = `'grey'`
- `pit.ticks.[0].unit` = `'month'`
- `pit.ticks.[0].show_labels` = `True`
- `pit.ticks.[0].label_format` = `'MMMM'`
- `pit.ticks.[0].label_align` = `'start'`
- `pit.ticks.[0].label_side` = `'below'`
- `pit.ticks.[0].tick_length` = `8.0`
- `pit.ticks.[0].label_gap` = `16.0`
- `pit.ticks.[1].unit` = `'week'`
- `pit.ticks.[1].week_start` = `0`
- `pit.ticks.[1].label_align` = `'start'`
- `pit.ticks.[1].label_format` = `'M/D'`
- `pit.ticks.[1].label_side` = `'above'`
- `pit.ticks.[1].show_labels` = `True`
- `pit.ticks.[1].max_label_count` = `400`
- `pit.ticks.[1].tick_length` = `4.0`
- `pit.ticks.[1].label_gap` = `4.0`
- `pit.ticks.[1].tick_opacity` = `0.5`
- `pit.date_format` = `'ddd MMM D'`
- `pit.name_text.font_name` = `'OfficinaSans-Book'`
- `pit.notes_text.font_name` = `'OfficinaSans-Book'`
- `pit.date_text.color` = `'grey'`
- `pit.date_text.font_name` = `'OfficinaSans-Book'`
- `pit.date_text.font_size` = `9`
- `pit.dot_color` = `'deepskyblue'`
- `pit.milestone_color` = `'gold'`
- `pit.leader.color` = `'grey'`
- `pit.leader.width` = `0.75`
- `pit.leader.dasharray` = `None`
- `pit.leader.opacity` = `1.0`
- `pit.leader.linecap` = `'round'`
- `pit.leader.marker_start` = `'none'`
- `pit.leader.marker_start_size` = `3.0`
- `pit.leader.marker_end` = `'arrow-head'`
- `pit.leader.marker_end_size` = `5.0`
- `pit.leader_primary.color` = `'deepskyblue'`
- `pit.leader_secondary.color` = `'steelblue'`
- `pit.today_line.show` = `True`
- `pit.today_line.color` = `'tomato'`
- `pit.today_line.width` = `1.0`
- `pit.today_line.dasharray` = `'4,2'`
- `pit.today_line.opacity` = `0.85`
- `pit.today_line.linecap` = `'round'`
- `pit.today_line.linejoin` = `'round'`
- `pit.today_line.label` = `'today'`
- `pit.today_line.label_color` = `'tomato'`
- `pit.today_line.label_font_name` = `'Roboto-Bold'`
- `pit.today_line.label_font_size` = `9`
- `pit.today_line.label_position` = `'end'`
- `pit.today_line.marker_start` = `'none'`
- `pit.today_line.marker_start_size` = `4.0`
- `pit.today_line.marker_end` = `'none'`
- `pit.today_line.marker_end_size` = `6.0`
- `pit.arrow_head.color` = `'grey'`
- `pit.label.stroke_color` = `'lightgrey'`
- `pit.label.stroke_width` = `0.5`
- `pit.label.fill_color` = `'aliceblue'`
- `pit.label.fill_opacity` = `0.85`
- `pit.label.text_color` = `'#1b1f24'`
- `pit.label.icon_size` = `None`
- `pit.label_palette` = `'Pastel1'`

#### `compact_plan` (12 of 16)

- `compact_plan.palette` = `['#92d050', '#6b9bc7', 'gold', 'tomato', 'plum', 'khaki']`
- `compact_plan.show_axis` = `True`
- `compact_plan.number_duration_icons` = `True`
- `compact_plan.duration_date_format` = `'M/D'`
- `compact_plan.duration_date_color` = `None`
- `compact_plan.duration_name_color` = `None`
- `compact_plan.continuation_legend_text` = `'activity continues'`
- `compact_plan.continuation_before_legend_text` = `'activity began earlier'`
- `compact_plan.show_axis_legend` = `True`
- `compact_plan.legend_axis_text` = `'timeline'`
- `compact_plan.federal_holiday_icon` = `None`
- `compact_plan.bands` = `['date_range', 'week', 'date']`

#### `blockplan` (29 of 44)

- `blockplan.number_duration_icons` = `True`
- `blockplan.fiscal_year_start_month` = `2`
- `blockplan.week_start` = `0`
- `blockplan.header_font_size` = `None`
- `blockplan.band_font_size` = `None`
- `blockplan.timeband_fill_palette` = `'accent'`
- `blockplan.timeband_fill_opacity` = `1.0`
- `blockplan.lane_label_font_size` = `None`
- `blockplan.event_date_font_size` = `None`
- `blockplan.event_date_format` = `'M/D'`
- `blockplan.marker_radius` = `2.0`
- `blockplan.duration_date_format` = `'M/D'`
- `blockplan.federal_holiday_icon` = `'flag-duotone'`
- `blockplan.palette` = `['lightskyblue', 'gold', 'tomato', 'springgreen', 'plum', 'khaki']`
- `blockplan.top_bands.[0].band` = `'fiscal_quarter'`
- `blockplan.top_bands.[0].row_height` = `12`
- `blockplan.top_bands.[0].stroke_color` = `'black'`
- `blockplan.top_bands.[1].band` = `'month_2'`
- `blockplan.top_bands.[1].row_height` = `12`
- `blockplan.top_bands.[1].stroke_color` = `'grey'`
- `blockplan.top_bands.[2].band` = `'date'`
- `blockplan.top_bands.[2].row_height` = `12`
- `blockplan.top_bands.[2].stroke_color` = `'grey'`
- `blockplan.top_bands.[3].band` = `'dow'`
- `blockplan.top_bands.[3].row_height` = `12`
- `blockplan.top_bands.[3].stroke_color` = `'grey'`
- `blockplan.top_bands.[4].band` = `'holiday'`
- `blockplan.top_bands.[4].row_height` = `12`
- `blockplan.top_bands.[4].stroke_color` = `'grey'`

#### `gantt` (33 of 71)

- `gantt.number_duration_icons` = `True`
- `gantt.arrow_marker_end` = `'arrow-head'`
- `gantt.arrow_marker_end_size` = `6.0`
- `gantt.arrow_linecap` = `'round'`
- `gantt.arrow_linejoin` = `'round'`
- `gantt.band_row_height` = `10.0`
- `gantt.continuation_icon` = `'arrow-bar-right'`
- `gantt.progress_color` = `'black'`
- `gantt.float_opacity_scale` = `0.4`
- `gantt.show_today_line` = `True`
- `gantt.today_date` = `None`
- `gantt.columns.[3].date_format` = `'dd MM/DD'`
- `gantt.columns.[4].date_format` = `'dd MM/DD'`
- `gantt.top_bands.[0].band` = `'fiscal_quarter'`
- `gantt.top_bands.[0].row_height` = `12`
- `gantt.top_bands.[1].band` = `'month'`
- `gantt.top_bands.[1].row_height` = `12`
- `gantt.top_bands.[2].band` = `'dow'`
- `gantt.top_bands.[2].row_height` = `10`
- `gantt.top_bands.[3].band` = `'date'`
- `gantt.top_bands.[3].row_height` = `10`
- `gantt.top_bands.[4].band` = `'holiday'`
- `gantt.top_bands.[4].row_height` = `10`
- `gantt.bottom_bands.[0].band` = `'holiday'`
- `gantt.bottom_bands.[0].row_height` = `10`
- `gantt.bottom_bands.[1].band` = `'date'`
- `gantt.bottom_bands.[1].row_height` = `10`
- `gantt.bottom_bands.[2].band` = `'dow'`
- `gantt.bottom_bands.[2].row_height` = `10`
- `gantt.bottom_bands.[3].band` = `'month'`
- `gantt.bottom_bands.[3].row_height` = `12`
- `gantt.bottom_bands.[4].band` = `'fiscal_quarter'`
- `gantt.bottom_bands.[4].row_height` = `12`

#### `excelblockplan` (4 of 4)

- `excelblockplan.number_duration_icons` = `True`
- `excelblockplan.band_row_height` = `18.0`
- `excelblockplan.font_name` = `'Calibri'`
- `excelblockplan.font_size` = `9`

## Key names repeated across view sections

- `number_duration_icons` — blockplan, candybar, compact_plan, excelblockplan, gantt, mini_calendar, pit, timeline, weekly
- `date_format` — gantt, pit, timeline
- `palette` — blockplan, compact_plan, timeline
- `cell_width` — candybar, text_mini
- `day_number_digits` — mini_calendar, text_mini
- `duration_icon_visible` — blockplan, timeline
- `today_date` — gantt, timeline
- `marker_radius` — blockplan, timeline
- `icon_size` — pit, timeline
- `box_width` — timeline_durations, timeline_events
- `box_height` — timeline_durations, timeline_events
- `row_height` — blockplan, gantt
- `band_row_height` — excelblockplan, gantt
- `header_label_align_h` — blockplan, gantt
- `width` — gantt, pit
- `band` — blockplan, gantt
- `label_format` — pit, weekly
- `font_name` — excelblockplan, pit
- `font_size` — excelblockplan, pit
- `week_start` — blockplan, pit
- `header_font_size` — blockplan, mini_calendar
- `duration_show_start_date` — blockplan, compact_plan
- `duration_show_end_date` — blockplan, compact_plan
- `duration_date_format` — blockplan, compact_plan
- `federal_holiday_icon` — blockplan, compact_plan
- `stroke_color` — blockplan, pit
- `color` — candybar, pit
- `milestone_color` — mini_calendar, pit
- `opacity` — candybar, pit

## style_rules

- 74 rules: 34 conditional, 40 define
- rules selecting on `visualizer:`: 8
- rules selecting on `papersize:`: 2
- `element_overrides` entries: 16
