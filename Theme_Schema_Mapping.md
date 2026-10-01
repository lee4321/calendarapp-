# Theme schema mapping: version 2.0 keys to version 3.0

Every key the current theme engine reads (`THEME_TO_CONFIG_MAP`, the `pit:` blocks, `colors:`) and where it goes in the version-3.0 schema (`config/theme_schema.py`). Generated and checked by a script: every destination below resolves to a real schema field.

- 428 old keys
- 247 move into a shared decoration block (`fonts`, `text`, `boxes`, `icons`, `lines`, `palettes`, `timescale`, `today`, `holidays`, `shading`, `week_numbers`, `fiscal`, `events`, `durations`)
- 151 stay as structure in a view block (or in `details`, `layout`, `watermark`, `continuation`, `overflow`, which are already global)
- 30 are removed

`timescale.*[]` below means "the same key on every timescale row". `timescale.primary[]` means the row that plays that role (for example candybar's month row).

## `weekly`

| Old key | New |
|---|---|
| `weekly.week_numbers.label_format` | `week_numbers.label_format` |
| `weekly.day_box.hash_pattern` | `weekly.day_box.hash_pattern` |
| `weekly.day_box.hash_pattern_opacity` | `weekly.day_box.hash_pattern_opacity` |
| `weekly.day_box.hash_pattern_target_size` | `weekly.day_box.hash_pattern_target_size` |
| `weekly.day_box.hash_pattern_scale` | `weekly.day_box.hash_pattern_scale` |
| `weekly.number_duration_icons` | removed: one global `durations.number_duration_icons` (icon set) and `durations.replace_icons_with_numbers` |
| `weekly.month_shade_opacity` | `shading.month_opacity` |
| `weekly.duration_fill_color` | `boxes.duration.fill` |
| `weekly.duration_stroke_color` | `boxes.duration.stroke` |
| `weekly.name_text.font_size` | `text.event_name.size` |
| `weekly.notes_text.font_size` | `text.event_notes.size` |

## `base`

| Old key | New |
|---|---|
| `base.shade_current_day` | `today.highlight.show` |
| `base.default_missing_icon` | `icons.missing.name` |
| `base.default_missing_icon_size` | `icons.missing.size` |
| `base.default_missing_icon_color` | `icons.missing.color` |

## `events`

| Old key | New |
|---|---|
| `events.icon_color` | `icons.event.color` |
| `events.item_placement_order` | `events.item_placement_order` |

## `durations`

| Old key | New |
|---|---|
| `durations.icon_color` | `icons.duration.color` |
| `durations.stroke_dasharray` | `durations.stroke_dasharray` |
| `durations.icon_list` | `durations.number_duration_icons` |
| `durations.icon_size` | `durations.icon_size` |
| `durations.icon_background_color` | `durations.icon_background_color` |
| `durations.icon_stroke_color` | `durations.icon_stroke_color` |

## `mini_calendar`

| Old key | New |
|---|---|
| `mini_calendar.number_duration_icons` | removed: one global `durations.number_duration_icons` (icon set) and `durations.replace_icons_with_numbers` |
| `mini_calendar.icon_set` | `mini_calendar.icon_set` |
| `mini_calendar.cell_bold_font` | `text.label_bold.font` |
| `mini_calendar.title_font_size` | `text.month_title.size` |
| `mini_calendar.header_font_size` | `text.label.size` |
| `mini_calendar.cell_font_size` | `text.day_number.size` |
| `mini_calendar.day_number_glyphs` | `mini_calendar.glyphs.day_number` |
| `mini_calendar.day_number_digits` | `mini_calendar.glyphs.day_number_digits` |
| `mini_calendar.adjacent_month_color` | `mini_calendar.adjacent_month_color` |
| `mini_calendar.show_adjacent` | `mini_calendar.show_adjacent` |
| `mini_calendar.holiday_color` | `holidays.federal.color` |
| `mini_calendar.nonworkday_fill_color` | `holidays.company.color` |
| `mini_calendar.milestone_color` | `icons.milestone.color` |
| `mini_calendar.milestone_stroke_color` | `boxes.milestone.stroke` |
| `mini_calendar.circle_milestones` | `mini_calendar.circle_milestones` |
| `mini_calendar.event_icon_scale` | `mini_calendar.event_icon_scale` |
| `mini_calendar.event_icon_opacity` | `mini_calendar.event_icon_opacity` |
| `mini_calendar.grid_lines` | `mini_calendar.grid_lines` |
| `mini_calendar.month_outline_color` | `mini_calendar.month_outline.color` |
| `mini_calendar.month_outline_width` | `mini_calendar.month_outline.width` |
| `mini_calendar.month_outline_opacity` | `mini_calendar.month_outline.opacity` |
| `mini_calendar.month_outline_dasharray` | `mini_calendar.month_outline.dasharray` |
| `mini_calendar.week_number_font_size` | `text.week_number.size` |
| `mini_calendar.week_number_label_format` | `week_numbers.label_format` |
| `mini_calendar.title_format` | `mini_calendar.title_format` |
| `mini_calendar.current_day_color` | `today.highlight.color` |
| `mini_calendar.strikethrough_stroke_dasharray` | removed: no longer read by any renderer |
| `mini_calendar.duration_bar_stroke_opacity` | removed: no longer read by any renderer |

## `candybar`

| Old key | New |
|---|---|
| `candybar.number_duration_icons` | removed: one global `durations.number_duration_icons` (icon set) and `durations.replace_icons_with_numbers` |
| `candybar.row_height` | `candybar.row_height` |
| `candybar.cell_width` | `candybar.cell_width` |
| `candybar.weeknum_col_ratio` | `candybar.weeknum_col_ratio` |
| `candybar.month_col_ratio` | `candybar.month_col_ratio` |
| `candybar.week_start` | `candybar.week_start` |
| `candybar.suppress_weekends` | `candybar.suppress_weekends` |
| `candybar.show_week_numbers` | `candybar.show_week_numbers` |
| `candybar.max_rows_per_page` | `candybar.max_rows_per_page` |
| `candybar.grid_lines` | `candybar.grid_lines` |
| `candybar.grid_line_color` | `lines.grid.color` |
| `candybar.weekend_fill` | `holidays.weekend.color` |
| `candybar.weekend_opacity` | `holidays.weekend.opacity` |
| `candybar.month_shading` | `candybar.month_shading` |
| `candybar.month_shade_colors` | `palettes.month` |
| `candybar.month_shade_opacity` | `shading.month_opacity` |
| `candybar.month_label_side` | removed: candybar's month row is `timescale.primary` (right side) |
| `candybar.month_format` | `timescale.primary[].format` |
| `candybar.month.font` | `timescale.primary[].text.font` |
| `candybar.month.size` | `timescale.primary[].text.size` |
| `candybar.month.color` | `timescale.primary[].text.color` |
| `candybar.month.opacity` | `timescale.primary[].text.opacity` |
| `candybar.month.anchor` | `timescale.primary[].text.align` |
| `candybar.month.rotation` | `timescale.primary[].text.rotation` |
| `candybar.month_box.fill` | `timescale.primary[].fill` |
| `candybar.month_box.stroke` | `timescale.primary[].border.color` |
| `candybar.month_box.opacity` | `timescale.primary[].fill_opacity` |

## `timeline`

| Old key | New |
|---|---|
| `timeline.number_duration_icons` | removed: one global `durations.number_duration_icons` (icon set) and `durations.replace_icons_with_numbers` |
| `timeline.axis_width` | `lines.axis.width` |
| `timeline.date_format` | `events.date.format` |
| `timeline.tick_label_format` | `timescale.primary[].format (a row's own format)` |
| `timeline.tick_label_gap` | `timescale.primary[].tick.label_gap` |
| `timeline.tick_label_offset_y` | removed: tick length + label_gap replace the combined offset |
| `timeline.today_date` | `today.date` |
| `timeline.today_label_text` | `today.label` |
| `timeline.today_label_offset_y` | `today.label_offset` |
| `timeline.today_line_color` | `lines.today.color` |
| `timeline.today_line_length` | `today.length` |
| `timeline.today_line_direction` | `today.direction` |
| `timeline.marker_stroke_color` | `events.marker.stroke_color` |
| `timeline.marker_stroke_width` | `events.marker.stroke_width` |
| `timeline.marker_radius` | `events.marker.radius` |
| `timeline.icon_size` | `icons.event.size` |
| `timeline.duration_offset_y` | `timeline.duration_offset_y` |
| `timeline.duration_lane_gap_y` | `timeline.duration_lane_gap_y` |
| `timeline.duration_icon_visible` | `durations.show_icons` |
| `timeline.label_fill_opacity` | `boxes.callout.fill_opacity` |
| `timeline.top_colors` | removed: row fills (`timescale.*[].fill`) |
| `timeline.bottom_colors` | removed: row fills (`timescale.*[].fill`) |
| `timeline.show_fiscal_periods` | removed: a `fiscal_period` row in `timescale` |
| `timeline.show_fiscal_quarters` | removed: a `fiscal_quarter` row in `timescale` |
| `timeline.palette` | `palettes.event` |
| `timeline.top_time_bands` | removed: `timescale.primary` |
| `timeline.bottom_time_bands` | removed: `timescale.secondary` |
| `timeline.ticks` | removed: `timescale` rows with a `tick:` facet |
| `timeline.show_holiday_icons` | `holidays.show_icons` |
| `timeline.holiday_icon_size` | `holidays.icon_size` |
| `timeline.holiday_icon_color` | `holidays.icon_color` |
| `timeline.holiday_icon_y_offset` | `holidays.icon_y_offset` |
| `timeline.show_holiday_dates` | `holidays.show_dates` |
| `timeline.holiday_date_format` | `holidays.date_format` |
| `timeline.holiday_date_font_size` | `holidays.date_font_size` |
| `timeline.holiday_date_color` | `holidays.date_color` |
| `timeline.orientation` | `timescale.axis.orientation` |
| `timeline.label_side` | `timeline.label_side` |
| `timeline.duration_side` | `timeline.duration_side` |
| `timeline.leader.direct` | `lines.leader.route` |
| `timeline.leader.start_stub` | `lines.leader.start_stub` |
| `timeline.leader.end_stub` | `lines.leader.end_stub` |
| `timeline.labella.layer_gap` | `timeline.labella.layer_gap` |
| `timeline.labella.node_height` | `timeline.labella.node_height` |
| `timeline.labella.density` | `timeline.labella.density` |
| `timeline.labella.min_pos` | `timeline.labella.min_pos` |
| `timeline.labella.max_pos` | `timeline.labella.max_pos` |
| `timeline.name_text.font_size` | `text.event_name.size` |
| `timeline.notes_text.font_size` | `text.event_notes.size` |
| `timeline.wbs_group_depth` | `durations.wbs_group_depth` |

## `blockplan`

| Old key | New |
|---|---|
| `blockplan.number_duration_icons` | removed: one global `durations.number_duration_icons` (icon set) and `durations.replace_icons_with_numbers` |
| `blockplan.label_column_ratio` | `blockplan.label_column_ratio` |
| `blockplan.band_label_column_ratio` | `blockplan.band_label_column_ratio` |
| `blockplan.fiscal_year_start_month` | `fiscal.year_start_month` |
| `blockplan.week_start` | `fiscal.week_start` |
| `blockplan.show_unmatched_lane` | `blockplan.show_unmatched_lane` |
| `blockplan.unmatched_lane_name` | `blockplan.unmatched_lane_name` |
| `blockplan.lane_match_mode` | `blockplan.lane_match_mode` |
| `blockplan.palette` | `palettes.event` |
| `blockplan.palette_name` | `palettes.event` |
| `blockplan.wbs_group_depth` | `durations.wbs_group_depth` |
| `blockplan.top_time_bands` | removed: `timescale.primary` / `timescale.secondary` |
| `blockplan.bottom_time_bands` | removed: `timescale.primary` / `timescale.secondary` |
| `blockplan.swimlanes` | `blockplan.swimlanes` |
| `blockplan.header_label_align_h` | `timescale.heading_align` |
| `blockplan.timeband_fill_color` | `boxes.band.fill` |
| `blockplan.timeband_fill_palette` | `boxes.band.fill_palette` |
| `blockplan.timeband_fill_opacity` | `boxes.band.fill_opacity` |
| `blockplan.federal_holiday_fill_color` | `holidays.federal.color` |
| `blockplan.federal_holiday_fill_opacity` | `holidays.federal.opacity` |
| `blockplan.company_holiday_fill_color` | `holidays.company.color` |
| `blockplan.company_holiday_fill_opacity` | `holidays.company.opacity` |
| `blockplan.weekend_fill_color` | `holidays.weekend.color` |
| `blockplan.weekend_fill_opacity` | `holidays.weekend.opacity` |
| `blockplan.federal_holiday_icon` | `holidays.federal.icon` |
| `blockplan.company_holiday_icon` | `holidays.company.icon` |
| `blockplan.weekend_icon` | `holidays.weekend.icon` |
| `blockplan.lane_label_align_h` | `blockplan.lane_label_align_h` |
| `blockplan.lane_label_align_v` | `blockplan.lane_label_align_v` |
| `blockplan.lane_label_rotation` | `blockplan.lane_label_rotation` |
| `blockplan.lane_split_ratio` | `blockplan.lane_split_ratio` |
| `blockplan.event_show_date` | `events.date.show` |
| `blockplan.event_date_font_size` | `events.date.font_size` |
| `blockplan.event_date_format` | `events.date.format` |
| `blockplan.duration_bar_height` | `blockplan.duration_bar_height` |
| `blockplan.duration_row_gap` | `blockplan.duration_row_gap` |
| `blockplan.duration_icon_visible` | `durations.show_icons` |
| `blockplan.duration_show_start_date` | `durations.dates.show_start` |
| `blockplan.duration_show_end_date` | `durations.dates.show_end` |
| `blockplan.duration_date_format` | `durations.dates.format` |
| `blockplan.duration_date_font_size` | `durations.dates.font_size` |
| `blockplan.marker_radius` | `events.marker.radius` |
| `blockplan.header_font_size` | `text.label.size` |
| `blockplan.band_font_size` | `text.band_label.size` |
| `blockplan.lane_label_font_size` | `text.swimlane_label.size` |
| `blockplan.name_text.font_size` | `text.event_name.size` |
| `blockplan.notes_text.font_size` | `text.event_notes.size` |

## `gantt`

| Old key | New |
|---|---|
| `gantt.number_duration_icons` | removed: one global `durations.number_duration_icons` (icon set) and `durations.replace_icons_with_numbers` |
| `gantt.columns` | `gantt.columns` |
| `gantt.header_label_align_h` | `timescale.heading_align` |
| `gantt.table_width_ratio` | `gantt.table_width_ratio` |
| `gantt.row_height` | `gantt.row_height` |
| `gantt.header_row_height` | `gantt.header_row_height` |
| `gantt.indent_per_level` | `gantt.indent_per_level` |
| `gantt.top_time_bands` | removed: `timescale.primary` / `timescale.secondary` |
| `gantt.bottom_time_bands` | removed: `timescale.primary` / `timescale.secondary` |
| `gantt.band_row_height` | `timescale.*[].height` |
| `gantt.min_day_width` | `gantt.min_day_width` |
| `gantt.milestone_icon` | `gantt.marks.milestone` |
| `gantt.deadline_icon` | `gantt.marks.deadline` |
| `gantt.rollup_icon` | `gantt.marks.rollup` |
| `gantt.milestone_flag_icon` | `gantt.marks.milestone_flag` |
| `gantt.snapped_event_icon` | `gantt.marks.snapped_event` |
| `gantt.offchart_dep_icon` | `gantt.marks.offchart_dependency` |
| `gantt.link_ref_icon_families` | `gantt.marks.link_ref_icon_families` |
| `gantt.link_ref_family_size` | `gantt.marks.link_ref_family_size` |
| `gantt.link_ref_max_icons` | `gantt.marks.link_ref_max_icons` |
| `gantt.continuation_icon` | `continuation.icon_after` |
| `gantt.bar_height` | `gantt.bar_height` |
| `gantt.progress_color` | `lines.progress.color` |
| `gantt.progress_width` | `lines.progress.width` |
| `gantt.float_opacity_scale` | `gantt.float_opacity_scale` |
| `gantt.show_dependencies` | `gantt.show_dependencies` |
| `gantt.arrow_marker_end` | `lines.dependency.marker_end` |
| `gantt.arrow_marker_end_size` | `lines.dependency.marker_end_size` |
| `gantt.arrow_linecap` | `lines.dependency.linecap` |
| `gantt.arrow_linejoin` | `lines.dependency.linejoin` |
| `gantt.show_today_line` | `today.show` |
| `gantt.today_date` | `today.date` |

## `pit`

| Old key | New |
|---|---|
| `pit.number_duration_icons` | removed: one global `durations.number_duration_icons` (icon set) and `durations.replace_icons_with_numbers` |
| `pit.direction` | `timescale.axis.orientation` |
| `pit.label_side` | `pit.label_side` |
| `pit.tick_color` | `lines.tick.color` |
| `pit.tick_unit` | removed: a `timescale` row's `unit` |
| `pit.tick_interval` | `timescale.*[].interval_days` |
| `pit.tick_label_format` | `timescale.*[].format` |
| `pit.tick_length` | `timescale.*[].tick.length` |
| `pit.show_ticks` | removed: rows with a `tick:` facet draw; none = no ticks |
| `pit.show_tick_labels` | `timescale.*[].tick.show_labels` |
| `pit.ticks` | removed: `timescale` rows with a `tick:` facet |
| `pit.date_format` | `events.date.format` |
| `pit.leader_label_anchor` | `pit.leader_label_anchor` |
| `pit.default_event_icon` | `icons.event.name` |
| `pit.default_milestone_icon` | `icons.milestone.name` |
| `pit.dot_color` | `icons.event.color` |
| `pit.milestone_color` | `icons.milestone.color` |
| `pit.label_palette` | `palettes.label` |
| `pit.name_text.font_name` | `text.event_name.font` |
| `pit.name_text.font_size` | `text.event_name.size` |
| `pit.notes_text.font_name` | `text.event_notes.font` |
| `pit.notes_text.font_size` | `text.event_notes.size` |
| `pit.labella.layer_gap` | `pit.labella.layer_gap` |
| `pit.labella.node_height` | `pit.labella.node_height` |
| `pit.labella.density` | `pit.labella.density` |
| `pit.axis.color` | `lines.axis.color` |
| `pit.axis.marker_end` | `lines.axis.marker_end` |
| `pit.axis.marker_end_size` | `lines.axis.marker_end_size` |
| `pit.axis.marker_size` | `timescale.axis.marker_size` |
| `pit.axis.marker_start` | `lines.axis.marker_start` |
| `pit.axis.marker_start_size` | `lines.axis.marker_start_size` |
| `pit.axis.width` | `lines.axis.width` |
| `pit.date_text.color` | `text.event_date.color` |
| `pit.date_text.font_name` | `text.event_date.font` |
| `pit.date_text.font_size` | `text.event_date.size` |
| `pit.date_text.offset` | `pit.date_offset` |
| `pit.date_text.placement` | `pit.date_placement` |
| `pit.leader.color` | `lines.leader.color` |
| `pit.leader.dasharray` | `lines.leader.dasharray` |
| `pit.leader.end_stub` | `lines.leader.end_stub` |
| `pit.leader.linecap` | `lines.leader.linecap` |
| `pit.leader.linejoin` | `lines.leader.linejoin` |
| `pit.leader.marker_end` | `lines.leader.marker_end` |
| `pit.leader.marker_end_size` | `lines.leader.marker_end_size` |
| `pit.leader.marker_start` | `lines.leader.marker_start` |
| `pit.leader.marker_start_size` | `lines.leader.marker_start_size` |
| `pit.leader.opacity` | `lines.leader.opacity` |
| `pit.leader.width` | `lines.leader.width` |
| `pit.leader_primary.color` | `lines.leader_primary.color` |
| `pit.leader_secondary.color` | `lines.leader_secondary.color` |
| `pit.today_line.color` | `lines.today.color` |
| `pit.today_line.dasharray` | `lines.today.dasharray` |
| `pit.today_line.date` | `today.date` |
| `pit.today_line.label` | `today.label` |
| `pit.today_line.label_color` | `text.today_label.color` |
| `pit.today_line.label_font_name` | `text.today_label.font` |
| `pit.today_line.label_font_size` | `text.today_label.size` |
| `pit.today_line.label_position` | `today.label_position` |
| `pit.today_line.linecap` | `lines.today.linecap` |
| `pit.today_line.linejoin` | `lines.today.linejoin` |
| `pit.today_line.marker_end` | `lines.today.marker_end` |
| `pit.today_line.marker_end_size` | `lines.today.marker_end_size` |
| `pit.today_line.marker_start` | `lines.today.marker_start` |
| `pit.today_line.marker_start_size` | `lines.today.marker_start_size` |
| `pit.today_line.opacity` | `lines.today.opacity` |
| `pit.today_line.show` | `today.show` |
| `pit.today_line.width` | `lines.today.width` |
| `pit.arrow_head.color` | removed: an arrowhead takes its line's colour |
| `pit.label.corner_radius` | `boxes.callout.corner_radius` |
| `pit.label.fill_color` | `boxes.callout.fill` |
| `pit.label.fill_opacity` | `boxes.callout.fill_opacity` |
| `pit.label.icon_gap` | `pit.label.icon_gap` |
| `pit.label.icon_size` | `pit.label.icon_size` |
| `pit.label.padding_x` | `pit.label.padding_x` |
| `pit.label.padding_y` | `pit.label.padding_y` |
| `pit.label.pattern` | `boxes.callout.pattern` |
| `pit.label.stroke_color` | `boxes.callout.stroke` |
| `pit.label.stroke_width` | `boxes.callout.stroke_width` |
| `pit.label.text_color` | `text.event_name.color` |

## `excelblockplan`

| Old key | New |
|---|---|
| `excelblockplan.number_duration_icons` | removed: one global `durations.number_duration_icons` (icon set) and `durations.replace_icons_with_numbers` |
| `excelblockplan.font_name` | `excelblockplan.font_name` |
| `excelblockplan.font_size` | `excelblockplan.font_size` |
| `excelblockplan.top_time_bands` | removed: `timescale.primary` / `timescale.secondary` |
| `excelblockplan.vertical_lines` | `timescale.*[].vline` |
| `excelblockplan.vertical_line_color` | `timescale.*[].vline.color` |
| `excelblockplan.vertical_line_width` | `timescale.*[].vline.width` |
| `excelblockplan.band_row_height` | `timescale.*[].height` |
| `excelblockplan.header_heading_fill_color` | `boxes.header.fill` |
| `excelblockplan.header_label_color` | `text.label.color` |
| `excelblockplan.header_label_align_h` | `timescale.heading_align` |
| `excelblockplan.timeband_fill_color` | `boxes.band.fill` |
| `excelblockplan.timeband_fill_palette` | `boxes.band.fill_palette` |
| `excelblockplan.timeband_label_color` | `timescale.*[].text.color` |
| `excelblockplan.federal_holiday_fill_color` | `holidays.federal.color` |
| `excelblockplan.company_holiday_fill_color` | `holidays.company.color` |
| `excelblockplan.weekend_fill_color` | `holidays.weekend.color` |

## `timeline_events`

| Old key | New |
|---|---|
| `timeline_events.box_width` | `timeline.events.box_width` |
| `timeline_events.box_height` | `timeline.events.box_height` |
| `timeline_events.placement` | `timeline.events.placement` |
| `timeline_events.row_gap` | `timeline.events.row_gap` |
| `timeline_events.box_gap` | `timeline.events.box_gap` |
| `timeline_events.inner_pad` | `timeline.events.inner_pad` |
| `timeline_events.icon_column_ratio` | `timeline.events.icon_column_ratio` |

## `timeline_durations`

| Old key | New |
|---|---|
| `timeline_durations.box_width` | `timeline.durations.box_width` |
| `timeline_durations.icon_column_ratio` | `timeline.durations.icon_column_ratio` |
| `timeline_durations.box_height` | `timeline.durations.box_height` |
| `timeline_durations.wbs_group_depth` | `durations.wbs_group_depth` |
| `timeline_durations.date_font_size` | `durations.dates.font_size` |

## `details`

| Old key | New |
|---|---|
| `details.markdown.enable` | `details.markdown.enable` |
| `details.markdown.title_text` | `details.markdown.title_text` |
| `details.markdown.sections` | `details.markdown.sections` |
| `details.markdown.events_section_text` | `details.markdown.events_section_text` |
| `details.markdown.colors_section_text` | `details.markdown.colors_section_text` |
| `details.markdown.symbols_section_text` | `details.markdown.symbols_section_text` |
| `details.markdown.exceptions_section_text` | `details.markdown.exceptions_section_text` |
| `details.markdown.holidays_section_text` | `details.markdown.holidays_section_text` |
| `details.markdown.empty_exceptions_text` | `details.markdown.empty_exceptions_text` |
| `details.markdown.empty_cell_text` | `details.markdown.empty_cell_text` |
| `details.markdown.icon_mode` | `details.markdown.icon_mode` |
| `details.markdown.color_mode` | `details.markdown.color_mode` |
| `details.markdown.group_by` | `details.markdown.group_by` |
| `details.markdown.sort` | `details.markdown.sort` |
| `details.markdown.columns` | `details.markdown.columns` |
| `details.markdown.exception_columns` | `details.markdown.exception_columns` |
| `details.markdown.holiday_columns` | `details.markdown.holiday_columns` |
| `details.icons.enable` | `details.icons.enable` |
| `details.icons.size` | `details.icons.size` |
| `details.csv.enable` | `details.csv.enable` |
| `details.csv.columns` | `details.csv.columns` |
| `details.csv.render_columns` | `details.csv.render_columns` |

## `compact_plan`

| Old key | New |
|---|---|
| `compact_plan.time_bands` | removed: `timescale.primary` / `timescale.secondary` |
| `compact_plan.band_row_height` | `timescale.*[].height` |
| `compact_plan.text.font_name` | `text.event_name.font` |
| `compact_plan.text.font_size` | `text.event_name.size` |
| `compact_plan.name_text.font_name` | `text.event_name.font` |
| `compact_plan.name_text.font_size` | `text.event_name.size` |
| `compact_plan.notes_text.font_name` | `text.event_name.font` |
| `compact_plan.show_axis` | `timescale.axis.show` |
| `compact_plan.axis_width` | `lines.axis.width` |
| `compact_plan.axis_padding` | `timescale.axis.padding` |
| `compact_plan.duration_line_width` | `compact_plan.duration_line_width` |
| `compact_plan.number_duration_icons` | removed: one global `durations.number_duration_icons` (icon set) and `durations.replace_icons_with_numbers` |
| `compact_plan.duration_show_start_date` | `durations.dates.show_start` |
| `compact_plan.duration_show_end_date` | `durations.dates.show_end` |
| `compact_plan.duration_date_format` | `durations.dates.format` |
| `compact_plan.duration_date_column_ratio` | `compact_plan.duration_date_column_ratio` |
| `compact_plan.duration_date_color` | `durations.dates.color` |
| `compact_plan.duration_name_color` | `text.event_name.color` |
| `compact_plan.lane_spacing` | `compact_plan.lane_spacing` |
| `compact_plan.palette` | `palettes.event` |
| `compact_plan.palette_name` | `palettes.event` |
| `compact_plan.milestone_icon` | `icons.milestone.name` |
| `compact_plan.milestone_flag_width` | `compact_plan.milestone_flag_width` |
| `compact_plan.milestone_flag_height` | `compact_plan.milestone_flag_height` |
| `compact_plan.show_milestone_labels` | `compact_plan.show_milestone_labels` |
| `compact_plan.header_bottom_y` | `compact_plan.header_bottom_y` |
| `compact_plan.continuation_legend_text` | `compact_plan.continuation_legend_text` |
| `compact_plan.continuation_before_legend_text` | `compact_plan.continuation_before_legend_text` |
| `compact_plan.show_axis_legend` | `compact_plan.show_axis_legend` |
| `compact_plan.legend_axis_text` | `compact_plan.legend_axis_text` |
| `compact_plan.federal_holiday_fill_color` | `holidays.federal.color` |
| `compact_plan.federal_holiday_fill_opacity` | `holidays.federal.opacity` |
| `compact_plan.company_holiday_fill_color` | `holidays.company.color` |
| `compact_plan.company_holiday_fill_opacity` | `holidays.company.opacity` |
| `compact_plan.weekend_fill_color` | `holidays.weekend.color` |
| `compact_plan.weekend_fill_opacity` | `holidays.weekend.opacity` |
| `compact_plan.federal_holiday_icon` | `holidays.federal.icon` |
| `compact_plan.company_holiday_icon` | `holidays.company.icon` |
| `compact_plan.weekend_icon` | `holidays.weekend.icon` |

## `overflow`

| Old key | New |
|---|---|
| `overflow.icon` | `overflow.icon` |

## `continuation`

| Old key | New |
|---|---|
| `continuation.show` | `continuation.show` |
| `continuation.icon_before` | `continuation.icon_before` |
| `continuation.icon_after` | `continuation.icon_after` |
| `continuation.icon_height` | `continuation.icon_height` |
| `continuation.icon_color` | `continuation.icon_color` |

## `watermark`

| Old key | New |
|---|---|
| `watermark.text` | `watermark.text` |
| `watermark.font_family` | `watermark.font_family` |
| `watermark.font_size` | `watermark.font_size` |
| `watermark.resize_mode` | `watermark.resize_mode` |
| `watermark.opacity` | `watermark.opacity` |
| `watermark.rotation_angle` | `watermark.rotation_angle` |
| `watermark.image` | `watermark.image` |
| `watermark.image_rotation_angle` | `watermark.image_rotation_angle` |

## `fiscal`

| Old key | New |
|---|---|
| `fiscal.label_format` | `fiscal.label_format` |
| `fiscal.end_label_format` | `fiscal.end_label_format` |
| `fiscal.year_offset` | `fiscal.year_offset` |
| `fiscal.use_period_colors` | `fiscal.use_period_colors` |

## `text_mini`

| Old key | New |
|---|---|
| `text_mini.cell_width` | `text_mini.cell_width` |
| `text_mini.month_gap` | `text_mini.month_gap` |
| `text_mini.week_number_digits` | `text_mini.glyphs.week_number_digits` |
| `text_mini.day_number_digits` | `text_mini.glyphs.day_number_digits` |
| `text_mini.event_symbols` | `text_mini.glyphs.event` |
| `text_mini.milestone_symbols` | `text_mini.glyphs.milestone` |
| `text_mini.holiday_symbols` | `text_mini.glyphs.holiday` |
| `text_mini.nonworkday_symbols` | `text_mini.glyphs.nonworkday` |
| `text_mini.duration_symbols` | `text_mini.glyphs.duration` |
| `text_mini.duration_fill` | `text_mini.glyphs.duration_fill` |

## `colors`

| Old key | New |
|---|---|
| `colors.company_holiday.alpha` | `holidays.company.opacity` |
| `colors.company_holiday.color` | `holidays.company.color` |
| `colors.company_holiday.opacity` | `holidays.company.opacity` |
| `colors.federal_holiday.alpha` | `holidays.federal.opacity` |
| `colors.federal_holiday.color` | `holidays.federal.color` |
| `colors.federal_holiday.opacity` | `holidays.federal.opacity` |
| `colors.fiscal_palette` | `palettes.fiscal` |
| `colors.fiscal_periods` | `palettes.fiscal_period_colors` |
| `colors.group_colors` | `palettes.group_colors` |
| `colors.group_palette` | `palettes.group` |
| `colors.hash_lines` | `palettes.hash_lines` |
| `colors.month_palette` | `palettes.month` |
| `colors.months` | `palettes.month_colors` |
| `colors.mini_calendar.adjacent_month_color` | `mini_calendar.adjacent_month_color` |
| `colors.mini_calendar.holiday_color` | `holidays.federal.color` |
| `colors.mini_calendar.nonworkday_fill_color` | `holidays.company.color` |
| `colors.mini_calendar.milestone_color` | `icons.milestone.color` |
| `colors.mini_calendar.current_day_color` | `today.highlight.color` |
| `colors.mini_calendar.adjacent_month_opacity` | `mini_calendar.adjacent_month_opacity` |
| `colors.mini_calendar.fiscal_period_opacity` | `fiscal.period_opacity` |
| `colors.mini_calendar.current_day_opacity` | `today.highlight.opacity` |
| `colors.mini_calendar.nonworkday_fill_opacity` | `holidays.company.opacity` |
| `colors.mini_calendar.special_nonworkday_opacity` | `holidays.company.opacity` |

## `layout`

| Old key | New |
|---|---|
| `layout.margin` | `layout.margin` |

## Old mechanisms with no key-for-key successor

- `time_bands:` catalog and the `top_bands` / `bottom_bands` / `bands` placement lists: replaced by `timescale.primary` / `timescale.secondary`, rows fully inline.
- `style_rules` `define` rules (40 in `default.yaml`): replaced by the `text`, `boxes`, `icons` and `lines` role tables. Conditional rules stay, minus the `visualizer`, `papersize`, `band` and `repeat` selectors.
- `element_overrides`: removed; `config/element_catalog.yaml` keeps the element-to-role binding.
- `size_rule` lists (paper-size font scaling) on `header`, `footer`, `weekly`, `events`, `mini_calendar`, `blockplan`: replaced by `text.<role>.size_by_paper`.
- `blockplan_vline_*` rules and `excelblockplan.vertical_lines`: replaced by the `vline` facet of a timescale row.
- `band <name> — segment` rules: replaced by the row's own `fill` / `fill_palette`.
- `fill_rules` on a band (per-day-class recolouring of single-day cells): replaced by the global `holidays` fills, which every view applies to single-day cells.
- `timeline.leader.direct: false` (labella's own chained routing through every row): no successor. Every leader is one curve (`lines.leader.route: curve`) or a straight run (`route: straight`).
- `extends:` / `unset:`: removed (decision 18).
