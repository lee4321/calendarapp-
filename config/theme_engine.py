"""
CSS-like theme engine for calendar styling.

Loads YAML theme files and applies cascading style overrides
to CalendarConfig instances. Supports a three-level cascade:

1. base: section (global defaults, like CSS * selector)
2. Section-level (e.g., header.font_family)
3. Element-level (e.g., header.left.font_color)

CLI arguments always override theme values.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from pathlib import Path
from typing import Any, TYPE_CHECKING

import yaml

if TYPE_CHECKING:
    from config.config import CalendarConfig

logger = logging.getLogger(__name__)


# ─── Mapping from theme YAML paths to CalendarConfig field names ───
# Each entry: (yaml_section_path, yaml_key) -> config_field_name
THEME_TO_CONFIG_MAP: dict[tuple[str, str], str] = {
    # Header
    ("header.left", "font_family"): "header_left_font",
    ("header.left", "font_color"): "header_left_font_color",
    ("header.center", "font_family"): "header_center_font",
    ("header.center", "font_color"): "header_center_font_color",
    # Footer
    ("footer.center", "font_family"): "footer_center_font",
    ("footer.center", "font_color"): "footer_center_font_color",
    # Day names (weekly)
    ("weekly.day_names", "font_family"): "day_name_font",
    ("weekly.day_names", "font_color"): "day_name_font_color",
    # Week numbers (weekly)
    ("weekly.week_numbers", "font_family"): "week_number_font",
    ("weekly.week_numbers", "font_color"): "week_number_font_color",
    ("weekly.week_numbers", "label_format"): "week_number_label_format",
    # Day box (weekly)
    ("weekly.day_box", "stroke_color"): "day_box_stroke_color",
    ("weekly.day_box", "stroke_opacity"): "day_box_stroke_opacity",
    ("weekly.day_box", "stroke_width"): "day_box_stroke_width",
    ("weekly.day_box", "stroke_dasharray"): "day_box_stroke_dasharray",
    ("weekly.day_box", "hash_pattern"): "theme_weekly_hash_pattern",
    ("weekly.day_box", "hash_pattern_opacity"): "hash_pattern_opacity",
    ("weekly.day_box", "fill_color"): "day_box_fill_color",
    ("weekly.day_box", "fill_opacity"): "day_box_fill_opacity",
    ("weekly.day_box", "number_font"): "day_box_number_font",
    ("weekly.day_box", "number_color"): "day_box_number_color",
    ("weekly.day_box", "font_color"): "day_box_color",
    # Base / global
    ("base", "default_missing_icon"): "default_missing_icon",
    ("base", "default_missing_icon_size"): "default_missing_icon_size",
    # Events (icon/placement only — text fields moved to weekly.name_text/notes_text)
    ("events", "icon_color"): "event_icon_color",
    ("events", "item_placement_order"): "item_placement_order",
    # Durations (icon/stroke only — text fields moved to weekly.name_text/notes_text)
    ("durations", "icon_color"): "duration_icon_color",
    ("durations", "stroke_dasharray"): "duration_stroke_dasharray",
    # Weekly text styling — kept survivors only.  Phase 2 stripped the
    # weekly_text_* set entirely (font_name/color/size/opacity/alignment),
    # plus name_text_alignment + notes_text_alignment (no readers).
    ("weekly.name_text", "font_name"): "weekly_name_text_font_name",
    ("weekly.name_text", "font_color"): "weekly_name_text_font_color",
    ("weekly.name_text", "font_size"): "weekly_name_text_font_size",
    ("weekly.name_text", "font_opacity"): "weekly_name_text_font_opacity",
    ("weekly.notes_text", "font_name"): "weekly_notes_text_font_name",
    ("weekly.notes_text", "font_color"): "weekly_notes_text_font_color",
    ("weekly.notes_text", "font_size"): "weekly_notes_text_font_size",
    ("weekly.notes_text", "font_opacity"): "weekly_notes_text_font_opacity",
    # Timeline.  Phase 2 strip dropped 11 dead translations:
    # background_color, duration_bar_stroke_dasharray,
    # duration_bracket_stroke_dasharray, text_font_color/_opacity/_alignment
    # / _font_size, name_text_font_opacity/_alignment,
    # notes_text_font_opacity/_alignment.
    ("timeline", "axis_color"): "timeline_axis_color",
    ("timeline", "axis_opacity"): "timeline_axis_opacity",
    ("timeline", "axis_width"): "timeline_axis_width",
    ("timeline", "tick_color"): "timeline_tick_color",
    ("timeline", "date_format"): "timeline_date_format",
    ("timeline", "tick_label_format"): "timeline_tick_label_format",
    ("timeline", "today_date"): "timeline_today_date",
    ("timeline", "today_label_text"): "timeline_today_label_text",
    ("timeline", "today_label_offset_y"): "timeline_today_label_offset_y",
    ("timeline", "today_line_color"): "timeline_today_line_color",
    ("timeline", "today_label_color"): "timeline_today_label_color",
    ("timeline", "marker_stroke_color"): "timeline_marker_stroke_color",
    ("timeline", "marker_stroke_width"): "timeline_marker_stroke_width",
    ("timeline", "marker_radius"): "timeline_marker_radius",
    ("timeline", "icon_size"): "timeline_icon_size",
    ("timeline", "duration_offset_y"): "timeline_duration_offset_y",
    ("timeline", "duration_lane_gap_y"): "timeline_duration_lane_gap_y",
    ("timeline", "duration_icon_visible"): "timeline_duration_icon_visible",
    ("timeline", "label_stroke_width"): "timeline_label_stroke_width",
    ("timeline", "label_fill_opacity"): "timeline_label_fill_opacity",
    ("timeline", "axis_stroke_dasharray"): "timeline_axis_stroke_dasharray",
    ("timeline", "tick_stroke_dasharray"): "timeline_tick_stroke_dasharray",
    ("timeline", "today_line_dasharray"): "timeline_today_line_dasharray",
    ("timeline", "label_stroke_dasharray"): "timeline_label_stroke_dasharray",
    ("timeline", "top_colors"): "timeline_top_colors",
    ("timeline", "bottom_colors"): "timeline_bottom_colors",
    ("timeline", "show_fiscal_periods"): "timeline_show_fiscal_periods",
    ("timeline", "show_fiscal_quarters"): "timeline_show_fiscal_quarters",
    ("timeline", "palette"): "theme_timeline_palette",
    ("timeline", "top_time_bands"): "timeline_top_time_bands",
    ("timeline", "bottom_time_bands"): "timeline_bottom_time_bands",
    ("timeline", "ticks"): "timeline_ticks",
    # Government-holiday marks drawn under the axis (icon + its date).
    ("timeline", "show_holiday_icons"): "timeline_show_holiday_icons",
    ("timeline", "holiday_icon_size"): "timeline_holiday_icon_size",
    ("timeline", "holiday_icon_color"): "timeline_holiday_icon_color",
    ("timeline", "holiday_icon_y_offset"): "timeline_holiday_icon_y_offset",
    ("timeline", "show_holiday_dates"): "timeline_show_holiday_dates",
    ("timeline", "holiday_date_format"): "timeline_holiday_date_format",
    ("timeline", "holiday_date_font_size"): "timeline_holiday_date_font_size",
    ("timeline", "holiday_date_color"): "timeline_holiday_date_color",
    # Timeline orientation + labella label-placement options.
    ("timeline", "orientation"): "timeline_orientation",
    ("timeline", "label_side"): "timeline_label_side",
    ("timeline.leader", "direct"): "timeline_leader_direct",
    ("timeline.leader", "start_stub"): "timeline_leader_start_stub",
    ("timeline.leader", "end_stub"): "timeline_leader_end_stub",
    ("timeline.labella", "layer_gap"): "timeline_labella_layer_gap",
    ("timeline.labella", "node_height"): "timeline_labella_node_height",
    ("timeline.labella", "density"): "timeline_labella_density",
    ("timeline.labella", "min_pos"): "timeline_labella_min_pos",
    ("timeline.labella", "max_pos"): "timeline_labella_max_pos",
    # Timeline text styling — kept survivors only.
    ("timeline.text", "font_name"): "timeline_text_font_name",
    ("timeline.name_text", "font_name"): "timeline_name_text_font_name",
    ("timeline.name_text", "font_color"): "timeline_name_text_font_color",
    ("timeline.name_text", "font_size"): "timeline_name_text_font_size",
    ("timeline.notes_text", "font_name"): "timeline_notes_text_font_name",
    ("timeline.notes_text", "font_color"): "timeline_notes_text_font_color",
    ("timeline.notes_text", "font_size"): "timeline_notes_text_font_size",
    # Timeline box/date fields (not renamed)
    ("timeline_events", "box_width"): "timeline_event_box_width",
    ("timeline_events", "box_height"): "timeline_event_box_height",
    ("timeline_durations", "box_width"): "timeline_duration_box_width",
    ("timeline_durations", "box_height"): "timeline_duration_box_height",
    ("timeline", "wbs_group_depth"): "timeline_wbs_group_depth",
    # Accepted where it first shipped, when grouping only reached the bars.
    ("timeline_durations", "wbs_group_depth"): "timeline_wbs_group_depth",
    ("timeline_durations", "date_font"): "timeline_duration_date_font",
    ("timeline_durations", "date_font_size"): "timeline_duration_date_font_size",
    ("timeline_durations", "date_color"): "timeline_duration_date_color",
    ("timeline.date", "font_family"): "timeline_date_font",
    ("timeline.date", "font_color"): "timeline_date_color",
    # Blockplan.  Phase 2 strip dropped 23 dead translations:
    # background_color, band_font, band_row_height, event_date_color/_font,
    # header_font, lane_heading_fill_color, lane_label_color/_font,
    # name_text_alignment / _font_color / _font_name / _font_opacity,
    # notes_text_alignment / _font_opacity, text_alignment / _font_color
    # / _font_name / _font_opacity / _font_size, timeband_fill_color,
    # timeband_label_color / _label_opacity (per-band YAML overrides
    # cover those slots; tokens cover the rest).
    ("blockplan", "grid_color"): "blockplan_grid_color",
    ("blockplan", "grid_opacity"): "blockplan_grid_opacity",
    ("blockplan", "grid_line_width"): "blockplan_grid_line_width",
    ("blockplan", "grid_dasharray"): "blockplan_grid_dasharray",
    ("blockplan", "timeband_line_color"): "blockplan_timeband_line_color",
    ("blockplan", "timeband_line_width"): "blockplan_timeband_line_width",
    ("blockplan", "timeband_line_opacity"): "blockplan_timeband_line_opacity",
    ("blockplan", "timeband_line_dasharray"): "blockplan_timeband_line_dasharray",
    ("blockplan", "label_column_ratio"): "blockplan_label_column_ratio",
    ("blockplan", "fiscal_year_start_month"): "blockplan_fiscal_year_start_month",
    ("blockplan", "week_start"): "blockplan_week_start",
    ("blockplan", "show_unmatched_lane"): "blockplan_show_unmatched_lane",
    ("blockplan", "unmatched_lane_name"): "blockplan_unmatched_lane_name",
    ("blockplan", "lane_match_mode"): "blockplan_lane_match_mode",
    ("blockplan", "palette"): "blockplan_palette",
    ("blockplan", "palette_name"): "theme_blockplan_palette_name",
    ("blockplan", "top_time_bands"): "blockplan_top_time_bands",
    ("blockplan", "bottom_time_bands"): "blockplan_bottom_time_bands",
    ("blockplan", "swimlanes"): "blockplan_swimlanes",
    ("blockplan", "header_label_color"): "blockplan_header_label_color",
    ("blockplan", "header_label_opacity"): "blockplan_header_label_opacity",
    ("blockplan", "header_label_align_h"): "blockplan_header_label_align_h",
    ("blockplan", "header_heading_fill_color"): "blockplan_header_heading_fill_color",
    ("blockplan", "timeband_fill_color"): "blockplan_timeband_fill_color",
    ("blockplan", "timeband_fill_palette"): "blockplan_timeband_fill_palette",
    ("blockplan", "timeband_fill_opacity"): "blockplan_timeband_fill_opacity",
    # Non-workday highlighting
    ("blockplan", "federal_holiday_fill_color"): "blockplan_federal_holiday_fill_color",
    ("blockplan", "federal_holiday_fill_opacity"): "blockplan_federal_holiday_fill_opacity",
    ("blockplan", "company_holiday_fill_color"): "blockplan_company_holiday_fill_color",
    ("blockplan", "company_holiday_fill_opacity"): "blockplan_company_holiday_fill_opacity",
    ("blockplan", "weekend_fill_color"): "blockplan_weekend_fill_color",
    ("blockplan", "weekend_fill_opacity"): "blockplan_weekend_fill_opacity",
    ("blockplan", "federal_holiday_icon"): "blockplan_federal_holiday_icon",
    ("blockplan", "company_holiday_icon"): "blockplan_company_holiday_icon",
    ("blockplan", "weekend_icon"): "blockplan_weekend_icon",
    ("blockplan", "lane_label_align_h"): "blockplan_lane_label_align_h",
    ("blockplan", "lane_label_align_v"): "blockplan_lane_label_align_v",
    ("blockplan", "lane_label_rotation"): "blockplan_lane_label_rotation",
    ("blockplan", "lane_split_ratio"): "blockplan_lane_split_ratio",
    ("blockplan", "event_show_date"): "blockplan_event_show_date",
    ("blockplan", "event_date_font_size"): "blockplan_event_date_font_size",
    ("blockplan", "event_date_format"): "blockplan_event_date_format",
    ("blockplan", "duration_fill_opacity"): "blockplan_duration_fill_opacity",
    ("blockplan", "duration_stroke_color"): "blockplan_duration_stroke_color",
    ("blockplan", "duration_stroke_width"): "blockplan_duration_stroke_width",
    ("blockplan", "duration_stroke_opacity"): "blockplan_duration_stroke_opacity",
    ("blockplan", "duration_stroke_dasharray"): "blockplan_duration_stroke_dasharray",
    ("blockplan", "duration_bar_height"): "blockplan_duration_bar_height",
    ("blockplan", "duration_icon_visible"): "blockplan_duration_icon_visible",
    ("blockplan", "duration_show_start_date"): "blockplan_duration_show_start_date",
    ("blockplan", "duration_show_end_date"): "blockplan_duration_show_end_date",
    ("blockplan", "duration_date_format"): "blockplan_duration_date_format",
    ("blockplan", "duration_date_font"): "blockplan_duration_date_font",
    ("blockplan", "duration_date_font_size"): "blockplan_duration_date_font_size",
    ("blockplan", "duration_date_color"): "blockplan_duration_date_color",
    ("blockplan", "duration_date_inset"): "blockplan_duration_date_inset",
    ("blockplan", "marker_radius"): "blockplan_marker_radius",
    ("blockplan", "vertical_line_color"): "blockplan_vertical_line_color",
    ("blockplan", "vertical_line_width"): "blockplan_vertical_line_width",
    ("blockplan", "vertical_line_dasharray"): "blockplan_vertical_line_dasharray",
    ("blockplan", "vertical_line_opacity"): "blockplan_vertical_line_opacity",
    ("blockplan", "vertical_line_fill_color"): "blockplan_vertical_line_fill_color",
    ("blockplan", "vertical_line_fill_opacity"): "blockplan_vertical_line_fill_opacity",
    ("blockplan", "header_font_size"): "blockplan_header_font_size",
    ("blockplan", "band_font_size"): "blockplan_band_font_size",
    ("blockplan", "lane_label_font_size"): "blockplan_lane_label_font_size",
    # Blockplan text styling — only font_size + name fields kept; the
    # color / opacity / alignment trios were stripped (see header).
    ("blockplan.name_text", "font_size"): "blockplan_name_text_font_size",
    ("blockplan.notes_text", "font_name"): "blockplan_notes_text_font_name",
    ("blockplan.notes_text", "font_color"): "blockplan_notes_text_font_color",
    ("blockplan.notes_text", "font_size"): "blockplan_notes_text_font_size",
    # Gantt.  `columns` is a list of column dicts (layout, not style) and
    # rides the same scalar path as blockplan.swimlanes.
    ("gantt", "columns"): "gantt_columns",
    ("gantt", "table_width_ratio"): "gantt_table_width_ratio",
    ("gantt", "row_height"): "gantt_row_height",
    ("gantt", "header_row_height"): "gantt_header_row_height",
    ("gantt", "indent_per_level"): "gantt_indent_per_level",
    ("gantt", "sort"): "gantt_sort",
    ("gantt", "top_time_bands"): "gantt_top_time_bands",
    ("gantt", "bottom_time_bands"): "gantt_bottom_time_bands",
    ("gantt", "band_row_height"): "gantt_band_row_height",
    ("gantt", "min_day_width"): "gantt_min_day_width",
    ("gantt", "milestone_icon"): "gantt_milestone_icon",
    ("gantt", "deadline_icon"): "gantt_deadline_icon",
    ("gantt", "rollup_icon"): "gantt_rollup_icon",
    ("gantt", "milestone_flag_icon"): "gantt_milestone_flag_icon",
    ("gantt", "snapped_event_icon"): "gantt_snapped_event_icon",
    ("gantt", "offchart_dep_icon"): "gantt_offchart_dep_icon",
    ("gantt", "link_ref_icon_families"): "gantt_link_ref_icon_families",
    ("gantt", "link_ref_family_size"): "gantt_link_ref_family_size",
    ("gantt", "link_ref_max_icons"): "gantt_link_ref_max_icons",
    ("gantt", "continuation_icon"): "gantt_continuation_icon",
    ("gantt", "bar_height"): "gantt_bar_height",
    ("gantt", "progress_color"): "gantt_progress_color",
    ("gantt", "progress_width"): "gantt_progress_width",
    ("gantt", "float_opacity_scale"): "gantt_float_opacity_scale",
    ("gantt", "show_dependencies"): "gantt_show_dependencies",
    ("gantt", "arrow_marker_end"): "gantt_arrow_marker_end",
    ("gantt", "arrow_marker_end_size"): "gantt_arrow_marker_end_size",
    ("gantt", "arrow_linecap"): "gantt_arrow_linecap",
    ("gantt", "arrow_linejoin"): "gantt_arrow_linejoin",
    ("gantt", "show_today_line"): "gantt_show_today_line",
    ("gantt", "today_date"): "gantt_today_date",
    ("gantt", "show_details"): "include_gantt_details",
    ("gantt", "details_title_text"): "gantt_details_title_text",
    ("gantt", "details_output_suffix"): "gantt_details_output_suffix",
    # Compact Activities Plan
    ("compact_plan", "time_bands"): "compactplan_time_bands",
    ("compact_plan", "band_row_height"): "compactplan_band_row_height",
    # Compact plan text styling (uniform).  Phase 2 strip dropped the
    # color / opacity / alignment translations — the unified-theme
    # text:event_name / text:event_notes / text:label tokens cover those
    # slots; only font_name / font_size remain as legacy fallbacks.
    ("compact_plan.text", "font_name"): "compactplan_text_font_name",
    ("compact_plan.text", "font_size"): "compactplan_text_font_size",
    ("compact_plan.name_text", "font_name"): "compactplan_name_text_font_name",
    ("compact_plan.name_text", "font_size"): "compactplan_name_text_font_size",
    ("compact_plan.notes_text", "font_name"): "compactplan_notes_text_font_name",
    ("compact_plan.notes_text", "font_size"): "compactplan_notes_text_font_size",
    ("compact_plan", "show_axis"): "compactplan_show_axis",
    ("compact_plan", "axis_width"): "compactplan_axis_width",
    ("compact_plan", "axis_padding"): "compactplan_axis_padding",
    ("compact_plan", "duration_line_width"): "compactplan_duration_line_width",
    ("compact_plan", "show_duration_icons"): "compactplan_show_duration_icons",
    ("compact_plan", "duration_icon_list"): "compactplan_duration_icon_list",
    ("compact_plan", "duration_icon_height"): "compactplan_duration_icon_height",
    ("compact_plan", "lane_spacing"): "compactplan_lane_spacing",
    ("compact_plan", "palette"): "compactplan_palette",
    ("compact_plan", "palette_name"): "theme_compactplan_palette_name",
    ("compact_plan", "milestone_icon"): "compactplan_milestone_icon",
    ("compact_plan", "milestone_flag_width"): "compactplan_milestone_flag_width",
    ("compact_plan", "milestone_flag_height"): "compactplan_milestone_flag_height",
    ("compact_plan", "show_milestone_labels"): "compactplan_show_milestone_labels",
    ("compact_plan", "show_legend"): "compactplan_show_legend",
    ("compact_plan", "legend_swatch_width"): "compactplan_legend_swatch_width",
    ("compact_plan", "legend_row_height"): "compactplan_legend_row_height",
    ("compact_plan", "header_bottom_y"): "compactplan_header_bottom_y",
    ("compact_plan", "key_top_y"): "compactplan_key_top_y",
    ("compact_plan", "show_milestone_list"): "compactplan_show_milestone_list",
    ("compact_plan", "milestone_list_date_format"): "compactplan_milestone_list_date_format",
    ("compact_plan", "milestone_list_row_height"): "compactplan_milestone_list_row_height",
    ("compact_plan", "milestone_list_date_col_width"): "compactplan_milestone_list_date_col_width",
    ("compact_plan", "show_holiday_list"): "compactplan_show_holiday_list",
    ("compact_plan", "holiday_list_date_format"): "compactplan_holiday_list_date_format",
    ("compact_plan", "holiday_list_row_height"): "compactplan_holiday_list_row_height",
    ("compact_plan", "holiday_list_date_col_width"): "compactplan_holiday_list_date_col_width",
    ("compact_plan", "holiday_list_icon_col_width"): "compactplan_holiday_list_icon_col_width",
    ("compact_plan", "holiday_list_icon_height"): "compactplan_holiday_list_icon_height",
    ("compact_plan", "legend_column_split"): "compactplan_legend_column_split",
    ("compact_plan", "legend_team_columns"): "compactplan_legend_team_columns",
    ("compact_plan", "continuation_legend_text"): "compactplan_continuation_legend_text",
    ("compact_plan", "show_axis_legend"): "compactplan_show_axis_legend",
    ("compact_plan", "legend_axis_text"): "compactplan_legend_axis_text",
    # Non-workday highlighting for date/dow timeband cells
    ("compact_plan", "federal_holiday_fill_color"): "compactplan_federal_holiday_fill_color",
    ("compact_plan", "federal_holiday_fill_opacity"): "compactplan_federal_holiday_fill_opacity",
    ("compact_plan", "company_holiday_fill_color"): "compactplan_company_holiday_fill_color",
    ("compact_plan", "company_holiday_fill_opacity"): "compactplan_company_holiday_fill_opacity",
    ("compact_plan", "weekend_fill_color"): "compactplan_weekend_fill_color",
    ("compact_plan", "weekend_fill_opacity"): "compactplan_weekend_fill_opacity",
    ("compact_plan", "federal_holiday_icon"): "compactplan_federal_holiday_icon",
    ("compact_plan", "company_holiday_icon"): "compactplan_company_holiday_icon",
    ("compact_plan", "weekend_icon"): "compactplan_weekend_icon",
    # Overflow (weekly)
    ("weekly.overflow", "icon"): "overflow_indicator_icon",
    ("weekly.overflow", "color"): "overflow_indicator_color",
    # Continuation icons (global — shared by timeline / blockplan / compact_plan)
    ("continuation", "show"): "show_continuation_icon",
    ("continuation", "icon_before"): "continuation_icon_before",
    ("continuation", "icon_after"): "continuation_icon_after",
    ("continuation", "icon_height"): "continuation_icon_height",
    ("continuation", "icon_color"): "continuation_icon_color",
    # Watermark
    ("watermark", "text"): "watermark_text",
    ("watermark", "color"): "watermark_color",
    ("watermark", "font_family"): "watermark_font",
    ("watermark", "font_size"): "watermark_font_size",
    ("watermark", "resize_mode"): "watermark_resize_mode",
    ("watermark", "opacity"): "watermark_opacity",
    ("watermark", "rotation_angle"): "watermark_rotation_angle",
    ("watermark", "image_rotation_angle"): "watermark_image_rotation_angle",
    # Fiscal labels
    ("fiscal", "label_format"): "fiscal_period_label_format",
    ("fiscal", "end_label_format"): "fiscal_period_end_label_format",
    ("fiscal", "year_offset"): "fiscal_year_offset",
    # Mini calendar
    # mini-icon has no section of its own — it is the mini renderer with day
    # numbers swapped for glyphs, so it reads mini_calendar like the rest.
    ("mini_calendar", "icon_set"): "mini_icon_set",
    ("mini_calendar", "cell_font"): "mini_cell_font",
    ("mini_calendar", "cell_bold_font"): "mini_cell_bold_font",
    ("mini_calendar", "title_font"): "mini_title_font",
    ("mini_calendar", "title_font_size"): "mini_title_font_size",
    ("mini_calendar", "title_color"): "mini_title_color",
    ("mini_calendar", "header_font_size"): "mini_header_font_size",
    ("mini_calendar", "cell_font_size"): "mini_cell_font_size",
    ("mini_calendar", "day_number_glyphs"): "mini_day_number_glyphs",
    ("mini_calendar", "day_number_digits"): "mini_day_number_digits",
    ("mini_calendar", "day_color"): "mini_day_color",
    ("mini_calendar", "adjacent_month_color"): "mini_adjacent_month_color",
    ("mini_calendar", "show_adjacent"): "mini_show_adjacent",
    ("mini_calendar", "holiday_color"): "mini_holiday_color",
    ("mini_calendar", "nonworkday_fill_color"): "mini_nonworkday_fill_color",
    ("mini_calendar", "milestone_color"): "mini_milestone_color",
    ("mini_calendar", "milestone_stroke_color"): "mini_milestone_stroke_color",
    ("mini_calendar", "milestone_stroke_width"): "mini_milestone_stroke_width",
    ("mini_calendar", "milestone_stroke_opacity"): "mini_milestone_stroke_opacity",
    ("mini_calendar", "circle_milestones"): "mini_circle_milestones",
    ("mini_calendar", "grid_lines"): "mini_grid_lines",
    ("mini_calendar", "grid_line_color"): "mini_grid_line_color",
    ("mini_calendar", "grid_line_width"): "mini_grid_line_width",
    ("mini_calendar", "grid_line_opacity"): "mini_grid_line_opacity",
    ("mini_calendar", "month_outline_color"): "mini_month_outline_color",
    ("mini_calendar", "month_outline_width"): "mini_month_outline_width",
    ("mini_calendar", "month_outline_opacity"): "mini_month_outline_opacity",
    ("mini_calendar", "month_outline_dasharray"): "mini_month_outline_dasharray",
    ("mini_calendar", "week_number_font_size"): "mini_week_number_font_size",
    ("mini_calendar", "week_number_label_format"): "mini_week_number_label_format",
    # mini_calendar.day_box.hash_rules removed — use style_rules instead
    # Mini details page — kept survivors only.  Phase 2 stripped
    # title_color/_font + header_color/_font, plus the text/name_text/notes_text
    # alignment + name fields with no readers.
    ("mini_details", "title_text"): "mini_details_title_text",
    ("mini_details", "title_font_size"): "mini_details_title_font_size",
    ("mini_details.text", "font_color"): "mini_details_text_font_color",
    ("mini_details.text", "font_opacity"): "mini_details_text_font_opacity",
    ("mini_details.name_text", "font_color"): "mini_details_name_text_font_color",
    ("mini_details.name_text", "font_size"): "mini_details_name_text_font_size",
    ("mini_details.name_text", "font_opacity"): "mini_details_name_text_font_opacity",
    ("mini_details.notes_text", "font_size"): "mini_details_notes_text_font_size",
    ("mini_details", "headers"): "mini_details_headers",
    ("mini_details", "column_widths"): "mini_details_column_widths",
    ("mini_details", "output_suffix"): "mini_details_output_suffix",
    # Text mini calendar
    ("text_mini", "cell_width"): "text_mini_cell_width",
    ("text_mini", "month_gap"): "text_mini_month_gap",
    ("text_mini", "week_number_digits"): "text_mini_week_number_digits",
    ("text_mini", "day_number_digits"): "text_mini_day_number_digits",
    ("text_mini", "event_symbols"): "text_mini_event_symbols",
    ("text_mini", "milestone_symbols"): "text_mini_milestone_symbols",
    ("text_mini", "holiday_symbols"): "text_mini_holiday_symbols",
    ("text_mini", "nonworkday_symbols"): "text_mini_nonworkday_symbols",
    ("text_mini", "duration_symbols"): "text_mini_duration_symbols",
    ("text_mini", "duration_fill"): "text_mini_duration_fill",
    ("mini_calendar", "title_format"): "mini_title_format",
    ("mini_calendar", "current_day_color"): "mini_current_day_color",
    ("mini_calendar", "grid_line_dasharray"): "mini_grid_line_dasharray",
    (
        "mini_calendar",
        "strikethrough_stroke_dasharray",
    ): "mini_strikethrough_stroke_dasharray",
    ("mini_calendar", "hash_line_dasharray"): "mini_hash_line_dasharray",
    (
        "mini_calendar",
        "duration_bar_stroke_opacity",
    ): "mini_duration_bar_stroke_opacity",
    (
        "mini_details",
        "separator_stroke_dasharray",
    ): "mini_details_separator_stroke_dasharray",
    # Candybar (vertical year-strip)
    ("candybar", "row_height"): "candybar_row_height",
    ("candybar", "cell_width"): "candybar_cell_width",
    ("candybar", "weeknum_col_ratio"): "candybar_weeknum_col_ratio",
    ("candybar", "month_col_ratio"): "candybar_month_col_ratio",
    ("candybar", "week_start"): "candybar_week_start",
    ("candybar", "suppress_weekends"): "candybar_suppress_weekends",
    ("candybar", "show_week_numbers"): "candybar_show_week_numbers",
    ("candybar", "max_rows_per_page"): "candybar_max_rows_per_page",
    ("candybar", "grid_lines"): "candybar_grid_lines",
    ("candybar", "grid_line_color"): "candybar_grid_line_color",
    ("candybar", "weekend_fill"): "candybar_weekend_fill",
    ("candybar", "weekend_opacity"): "candybar_weekend_opacity",
    ("candybar", "month_shading"): "candybar_month_shading",
    ("candybar", "month_shade_colors"): "candybar_month_shade_colors",
    ("candybar", "month_shade_opacity"): "candybar_month_shade_opacity",
    ("candybar", "month_label_side"): "candybar_month_label_side",
    ("candybar", "month_format"): "candybar_month_format",
    ("candybar.month", "font"): "candybar_month_font",
    ("candybar.month", "size"): "candybar_month_font_size",
    ("candybar.month", "color"): "candybar_month_color",
    ("candybar.month", "opacity"): "candybar_month_opacity",
    ("candybar.month", "anchor"): "candybar_month_anchor",
    ("candybar.month", "rotation"): "candybar_month_rotation",
    ("candybar.month_box", "fill"): "candybar_month_box_fill",
    ("candybar.month_box", "stroke"): "candybar_month_box_stroke",
    ("candybar.month_box", "opacity"): "candybar_month_box_opacity",
    ("timeline", "connector_stroke_dasharray"): "timeline_connector_stroke_dasharray",
    # ExcelHeader
    ("excelheader", "font_name"): "excelheader_font",
    ("excelheader", "font_size"): "excelheader_font_size",
    ("excelheader", "top_time_bands"): "excelheader_top_time_bands",
    ("excelheader", "vertical_lines"): "excelheader_vertical_lines",
    ("excelheader", "vertical_line_color"): "excelheader_vertical_line_color",
    ("excelheader", "vertical_line_width"): "excelheader_vertical_line_width",
    ("excelheader", "band_row_height"): "excelheader_band_row_height",
    ("excelheader", "header_heading_fill_color"): "excelheader_header_heading_fill_color",
    ("excelheader", "header_label_color"): "excelheader_header_label_color",
    ("excelheader", "header_label_align_h"): "excelheader_header_label_align_h",
    ("excelheader", "timeband_fill_color"): "excelheader_timeband_fill_color",
    ("excelheader", "timeband_fill_palette"): "excelheader_timeband_fill_palette",
    ("excelheader", "timeband_label_color"): "excelheader_timeband_label_color",
    # Non-workday highlighting
    ("excelheader", "federal_holiday_fill_color"): "excelheader_federal_holiday_fill_color",
    ("excelheader", "company_holiday_fill_color"): "excelheader_company_holiday_fill_color",
    ("excelheader", "weekend_fill_color"): "excelheader_weekend_fill_color",
    # ExcelBlockplan — mirrors excelheader keys; None values fall back to the
    # excelheader_* equivalents at render time.
    # Stripped in Phase 2 (no consumers): vertical_line_dasharray /
    # vertical_line_opacity / vertical_line_fill_color /
    # vertical_line_fill_opacity (XLSX borders are color+style only),
    # federal_holiday_icon / company_holiday_icon / weekend_icon (XLSX
    # cells render glyphs as fills, not as icon SVGs).
    # PIT (Points in Time) — scalar mappings.
    # Nested sub-blocks (axis, leader, label, today_line, etc.) are
    # handled by ThemeEngine._apply_pit_blocks() called from apply().
    ("pit", "direction"): "pit_direction",
    ("pit", "label_side"): "pit_label_side",
    ("pit", "tick_color"): "theme_pit_tick_color",
    ("pit", "tick_unit"): "pit_tick_unit",
    ("pit", "tick_interval"): "pit_tick_interval",
    ("pit", "tick_label_format"): "pit_tick_label_format",
    ("pit", "tick_length"): "pit_tick_length",
    ("pit", "show_ticks"): "pit_show_ticks",
    ("pit", "show_tick_labels"): "pit_show_tick_labels",
    ("pit", "ticks"): "pit_ticks",
    ("pit", "date_format"): "pit_date_format",
    ("pit", "leader_label_anchor"): "pit_leader_label_anchor",
    ("pit", "default_event_icon"): "pit_default_event_icon",
    ("pit", "default_milestone_icon"): "pit_default_milestone_icon",
    ("pit", "dot_color"): "theme_pit_dot_color",
    ("pit", "milestone_color"): "theme_pit_milestone_color",
    ("pit", "label_palette"): "theme_pit_label_palette",
    # Callout label text fonts. Without these the PIT renderer falls back to
    # the timeline name_text/notes_text fonts (then hardcoded Roboto-*).
    ("pit.name_text", "font_name"): "pit_name_text_font_name",
    ("pit.name_text", "font_size"): "pit_name_text_font_size",
    ("pit.notes_text", "font_name"): "pit_notes_text_font_name",
    ("pit.notes_text", "font_size"): "pit_notes_text_font_size",
    # labella label-placement tuning. layer_gap is the axis→label gap,
    # i.e. the visible leader length (also sets row-to-row spacing with
    # node_height). Mirrors the timeline.labella block.
    ("pit.labella", "layer_gap"): "pit_labella_layer_gap",
    ("pit.labella", "node_height"): "pit_labella_node_height",
    ("pit.labella", "density"): "pit_labella_density",
}

# Valid top-level sections in a theme file
VALID_SECTIONS = frozenset(
    {
        "theme",
        "base",
        "header",
        "footer",
        "weekly",
        "events",
        "durations",
        "timeline",
        "timeline_events",
        "timeline_durations",
        "watermark",
        "continuation",
        "colors",
        "mini_calendar",
        "fiscal",
        "mini_details",
        "text_mini",
        "candybar",
        "layout",
        "blockplan",
        "gantt",
        "excelheader",
        "excelblockplan",
        "compact_plan",
        # Shared band catalog referenced by blockplan / compactplan /
        # excelheader placement lists (design §10).
        "time_bands",
        # New unified theme format sections
        "text_styles",
        "box_styles",
        "line_styles",
        "icon_styles",
        "axis",
        "icons",
        "patterns",
        "element_styles",
        "style_rules",
        "swimlane_rules",
        # Per-theme overrides of the built-in element catalog
        # (config/element_catalog.yaml).
        "element_overrides",
        # PIT (Points in Time) visualizer
        "pit",
    }
)

# Sections that indicate new unified theme format
# Unified-format themes ship `style_rules` instead of the legacy
# `text_styles` / `element_styles` sections.  Phase 3 path (b) made
# `style_rules` the single source of truth — `text_styles` /
# `element_styles` are no longer produced by the decompiler (which was
# removed) and won't appear in any post-migration theme YAML.
_NEW_FORMAT_SECTIONS = frozenset({"style_rules"})

# Sections whose font names refer to system-installed fonts (Excel output),
# not to FONT_REGISTRY.
FONT_VALIDATION_SKIP_SECTIONS = frozenset({"excelheader", "excelblockplan"})


def is_font_key(key: Any) -> bool:
    """True if ``key`` names a theme setting whose value is a FONT_REGISTRY name.

    Matched by shape rather than an explicit list, so keys added to themes
    later (``*_font``, ``*_font_name``) are validated without touching this
    module.  The size/color/opacity companions (``font_size``,
    ``header_font_size``, ``font_color``) deliberately do not match, and
    neither does the ``band_fonts`` mapping.

    ``key`` is whatever YAML produced — colour maps are keyed by ints — so
    non-string keys simply are not font keys.
    """
    if not isinstance(key, str):
        return False
    return key == "font" or key.endswith(("_font", "font_name", "font_family"))


def iter_font_references(data: Any, path: str = "") -> Iterator[tuple[str, str]]:
    """Yield ``(dotted_path, font_name)`` for every font name in theme data.

    Recurses through lists as well as dicts: ``style_rules`` is a list, so a
    dict-only walk sees none of the ``style.font`` values a unified theme
    actually renders with.
    """
    if isinstance(data, dict):
        for key, value in data.items():
            current_path = f"{path}.{key}" if path else key
            if not path and key in FONT_VALIDATION_SKIP_SECTIONS:
                continue
            if is_font_key(key):
                if isinstance(value, str) and value:
                    yield current_path, value
            else:
                yield from iter_font_references(value, current_path)
    elif isinstance(data, list):
        for index, item in enumerate(data):
            yield from iter_font_references(item, f"{path}[{index}]")


def find_unregistered_fonts(
    data: Any,
    registry: dict[str, str] | None = None,
) -> list[tuple[str, str]]:
    """Return ``(dotted_path, font_name)`` for font names missing from the registry.

    Every such reference is a latent ``KeyError`` from
    :func:`config.config.get_font_path` at render time.
    """
    if registry is None:
        from config.config import FONT_REGISTRY

        registry = FONT_REGISTRY
    return [
        (path, font)
        for path, font in iter_font_references(data)
        if font not in registry
    ]


class ThemeError(Exception):
    """Raised when theme loading or validation fails."""

    pass


class ThemeEngine:
    """
    Loads YAML theme files and applies cascading style overrides
    to CalendarConfig.

    Usage::

        engine = ThemeEngine()
        engine.load("corporate")        # built-in theme name
        engine.load("./mytheme.yaml")   # or a file path
        engine.apply(config)
    """

    BUILTIN_THEMES_DIR = Path(__file__).parent / "themes"

    def __init__(self) -> None:
        self._theme_data: dict[str, Any] = {}
        self._theme_name: str = ""

    @property
    def theme_name(self) -> str:
        """Name of the currently loaded theme."""
        return self._theme_name

    @classmethod
    def list_available_themes(cls) -> list[str]:
        """Return names of built-in themes (without .yaml extension), sorted.

        Sorts on the stem (post-extension-strip) rather than the full path so
        the result is stably ordered as plain theme names — `TJXmini` <
        `TJXmini-icon` (Python's string comparison: shorter shared-prefix
        sorts first).  Sorting the paths first would give the opposite
        order because `.` (0x2E) > `-` (0x2D), so `TJXmini-icon.yaml` sorts
        before `TJXmini.yaml` at the path level.
        """
        themes: list[str] = []
        if cls.BUILTIN_THEMES_DIR.exists():
            for f in cls.BUILTIN_THEMES_DIR.glob("*.yaml"):
                themes.append(f.stem)
        return sorted(themes)

    def load(self, theme_path_or_name: str) -> None:
        """
        Load a theme from a file path or built-in name.

        Args:
            theme_path_or_name: Either a path to a .yaml file,
                or the name of a built-in theme (e.g. "corporate").

        Raises:
            ThemeError: If the file cannot be found or parsed.
        """
        path = Path(theme_path_or_name)

        # If not a direct path, look in built-in themes
        if not path.exists():
            builtin = self.BUILTIN_THEMES_DIR / f"{theme_path_or_name}.yaml"
            if builtin.exists():
                path = builtin
            else:
                available = ", ".join(self.list_available_themes())
                raise ThemeError(
                    f"Theme not found: '{theme_path_or_name}'. "
                    f"Available built-in themes: {available}"
                )

        try:
            with open(path, "r") as f:
                self._theme_data = yaml.safe_load(f) or {}
        except yaml.YAMLError as e:
            raise ThemeError(f"Invalid YAML in theme file '{path}': {e}")

        meta = self._theme_data.get("theme", {})
        self._theme_name = (
            meta.get("name", path.stem) if isinstance(meta, dict) else path.stem
        )
        self._validate()
        logger.info("Loaded theme: %s", self._theme_name)

    def _validate(self) -> None:
        """Validate the loaded theme data (warnings only, non-fatal)."""
        unknown = set(self._theme_data.keys()) - VALID_SECTIONS
        if unknown:
            logger.warning(
                "Theme '%s' has unknown sections: %s",
                self._theme_name,
                unknown,
            )

        for font_path, font in find_unregistered_fonts(self._theme_data):
            logger.warning(
                "Theme '%s' font '%s' at '%s' is not in FONT_REGISTRY; "
                "rendering will fail when this style is used",
                self._theme_name,
                font,
                font_path,
            )

    def _resolve_value(self, section_path: str, key: str) -> Any | None:
        """
        Resolve a value using CSS-like cascading.

        Checks in order:
        1. section_path.key  (e.g. header.left.font_family)
        2. parent_section.key (e.g. header.font_family)
        3. base.key          (e.g. base.font_family)

        Returns None if not found at any level.
        """
        # Level 1: exact path (e.g. header.left)
        parts = section_path.split(".")
        node: Any = self._theme_data
        for part in parts:
            if isinstance(node, dict) and part in node:
                node = node[part]
            else:
                node = None
                break
        if isinstance(node, dict) and key in node:
            return node[key]

        # Level 2: parent section (for nested like header.left -> header)
        if len(parts) > 1:
            parent = self._theme_data.get(parts[0], {})
            if isinstance(parent, dict) and key in parent:
                return parent[key]

        # Level 3: base section
        base = self._theme_data.get("base", {})
        if isinstance(base, dict) and key in base:
            return base[key]

        return None

    @staticmethod
    def _normalize_papersize(value: str | None) -> str:
        """Normalize paper size labels for case-insensitive matching."""
        return str(value or "").strip().lower()

    def _get_theme_node(self, section_path: str) -> Any | None:
        """Return exact node at section_path from theme data, or None."""
        node: Any = self._theme_data
        for part in section_path.split("."):
            if not isinstance(node, dict) or part not in node:
                return None
            node = node[part]
        return node

    def _find_matching_size_rule(
        self, rules: Any, section_name: str, papersize: str | None
    ) -> tuple[int, dict[str, Any]] | None:
        """
        Find the first size_rule entry whose when.papersize list matches papersize.

        Args:
            rules: The raw size_rule value from the theme node (validated as list here)
            section_name: Human-readable section path for warning messages
            papersize: Paper size to match against (case-insensitive)

        Returns:
            (index, rule_dict) of the first match, or None if no match.
        """
        if not isinstance(rules, list):
            logger.warning(
                "Theme: %s.size_rule must be a list; got %r",
                section_name,
                type(rules).__name__,
            )
            return None

        p = self._normalize_papersize(papersize)
        for idx, rule in enumerate(rules):
            if not isinstance(rule, dict):
                logger.warning(
                    "Theme: %s.size_rule[%d] must be an object; got %r",
                    section_name,
                    idx,
                    rule,
                )
                continue
            when = rule.get("when", {})
            if not isinstance(when, dict):
                logger.warning(
                    "Theme: %s.size_rule[%d].when must be an object", section_name, idx
                )
                continue
            paper_values = when.get("papersize")
            if not isinstance(paper_values, list):
                logger.warning(
                    "Theme: %s.size_rule[%d].when.papersize must be a list",
                    section_name,
                    idx,
                )
                continue
            if p in {self._normalize_papersize(v) for v in paper_values}:
                return idx, rule
        return None

    def _resolve_desired_font_size(self, papersize: str | None) -> float | None:
        """
        Resolve desired base font size from base.font_size / base.size_rule.

        base.font_size provides a fallback; base.size_rule entries can override
        by matching papersize names.
        """
        desired: float | None = None
        base_font_size = self._resolve_value("base", "font_size")
        if base_font_size is not None:
            try:
                desired = float(base_font_size)
            except (TypeError, ValueError):
                logger.warning(
                    "Theme: base.font_size must be numeric; got %r", base_font_size
                )

        base_node = self._theme_data.get("base", {})
        if not isinstance(base_node, dict):
            return desired
        rules = base_node.get("size_rule")
        if rules is None:
            return desired

        # Iterate manually so we can skip rules missing font_size before checking papersize
        if not isinstance(rules, list):
            logger.warning(
                "Theme: base.size_rule must be a list; got %r", type(rules).__name__
            )
            return desired

        p = self._normalize_papersize(papersize)
        for idx, rule in enumerate(rules):
            if not isinstance(rule, dict):
                logger.warning(
                    "Theme: base.size_rule[%d] must be an object; got %r", idx, rule
                )
                continue
            if "font_size" not in rule:
                logger.warning("Theme: base.size_rule[%d] missing font_size", idx)
                continue
            when = rule.get("when", {})
            if not isinstance(when, dict):
                logger.warning("Theme: base.size_rule[%d].when must be an object", idx)
                continue
            paper_values = when.get("papersize")
            if not isinstance(paper_values, list):
                logger.warning(
                    "Theme: base.size_rule[%d].when.papersize must be a list", idx
                )
                continue
            if p in {self._normalize_papersize(v) for v in paper_values}:
                try:
                    return float(rule["font_size"])
                except (TypeError, ValueError):
                    logger.warning(
                        "Theme: base.size_rule[%d].font_size must be numeric; got %r",
                        idx,
                        rule["font_size"],
                    )
                    return desired
        return desired

    def _resolve_size_rule_match(
        self, section_path: str, papersize: str | None
    ) -> dict[str, Any] | None:
        """
        Return the first matching size_rule entry for a section path.

        Matching is case-insensitive against when.papersize values.
        """
        node = self._get_theme_node(section_path)
        if not isinstance(node, dict):
            return None
        rules = node.get("size_rule")
        if rules is None:
            return None
        result = self._find_matching_size_rule(rules, section_path, papersize)
        return result[1] if result is not None else None

    def _apply_element_size_rules(self, config: "CalendarConfig") -> None:
        """
        Apply per-element size_rule matches to explicit *_font_size config fields.

        For single-field sections, 'font_size' sets that field.
        For multi-field sections, use specific keys (e.g. title_font_size). If a
        generic 'font_size' is provided, it applies to all font-size fields in
        that section.
        """
        section_targets: dict[str, list[tuple[str, str]]] = {
            "header.left": [("font_size", "header_left_font_size")],
            "header.center": [("font_size", "header_center_font_size")],
            "header.right": [("font_size", "header_right_font_size")],
            "footer.left": [("font_size", "footer_left_font_size")],
            "footer.center": [("font_size", "footer_center_font_size")],
            "footer.right": [("font_size", "footer_right_font_size")],
            "weekly.day_names": [("font_size", "day_name_font_size")],
            "weekly.week_numbers": [("font_size", "week_number_font_size")],
            "events": [("font_size", "event_text_font_size")],
            "mini_calendar": [
                ("cell_font_size", "mini_cell_font_size"),
                ("title_font_size", "mini_title_font_size"),
                ("header_font_size", "mini_header_font_size"),
                ("week_number_font_size", "mini_week_number_font_size"),
            ],
            "mini_details": [
                ("title_font_size", "mini_details_title_font_size"),
            ],
            "blockplan": [
                ("header_font_size", "blockplan_header_font_size"),
                ("band_font_size", "blockplan_band_font_size"),
                ("lane_label_font_size", "blockplan_lane_label_font_size"),
            ],
        }

        papersize = getattr(config, "papersize", "")
        for section_path, targets in section_targets.items():
            rule = self._resolve_size_rule_match(section_path, papersize)
            if rule is None:
                continue

            generic = rule.get("font_size")
            for theme_key, config_field in targets:
                raw = rule.get(theme_key, generic)
                if raw is None:
                    continue
                try:
                    setattr(config, config_field, float(raw))
                except (TypeError, ValueError):
                    logger.warning(
                        "Theme: %s.size_rule font value for %s must be numeric; got %r",
                        section_path,
                        theme_key,
                        raw,
                    )

    def _apply_layout_overrides(self, config: "CalendarConfig") -> None:
        """
        Apply layout-level overrides (currently explicit side margins with units).

        Theme schema:
            layout:
              margin:
                top: "0.5in"
                right: "10mm"
                bottom: 12        # points if numeric
                left:
                  value: 0.25
                  unit: "in"
        """
        layout = self._theme_data.get("layout", {})
        if not isinstance(layout, dict):
            return
        margin = layout.get("margin", {})
        if not isinstance(margin, dict):
            return

        from config.config import parse_length_to_points

        any_side = False
        side_to_field = {
            "left": "margin_left",
            "right": "margin_right",
            "top": "margin_top",
            "bottom": "margin_bottom",
        }
        for side, field in side_to_field.items():
            if side not in margin:
                continue
            raw = margin.get(side)
            if raw is None:
                continue
            try:
                points = float(parse_length_to_points(raw))
            except ValueError as e:
                logger.warning("Theme: layout.margin.%s invalid: %s", side, e)
                continue
            if points < 0:
                logger.warning(
                    "Theme: layout.margin.%s must be >= 0; got %r", side, raw
                )
                continue
            setattr(config, field, points)
            any_side = True

        if any_side:
            config.include_margin = True

    def apply(self, config: "CalendarConfig") -> "CalendarConfig":
        """
        Apply theme overrides to a CalendarConfig instance.

        Mutates config in place and returns it for chaining.
        Only sets values that the theme explicitly defines.

        Args:
            config: The CalendarConfig to apply theme to.

        Returns:
            The same config instance with theme values applied.
        """
        if not self._theme_data:
            return config

        desired_font_size = self._resolve_desired_font_size(
            getattr(config, "papersize", "")
        )
        if desired_font_size is not None:
            config.desired_font_size = desired_font_size

        # Apply element-level styling via the mapping
        for (section_path, key), config_field in THEME_TO_CONFIG_MAP.items():
            value = self._resolve_value(section_path, key)
            if value is not None:
                try:
                    setattr(config, config_field, value)
                except (TypeError, ValueError) as e:
                    logger.warning(
                        "Theme: could not set %s=%r: %s",
                        config_field,
                        value,
                        e,
                    )

        # Apply optional papersize-conditioned font-size rules per element.
        self._apply_element_size_rules(config)
        # Apply layout-level overrides (margins).
        self._apply_layout_overrides(config)

        # Raise on old hash_rules / swimlanes.match keys that should have been migrated.
        self._check_deprecated_rule_keys()

        # Load unified style_rules and swimlane_rules.
        self._load_rule_lists(config)

        # If mini week number label format isn't set, fall back to week_numbers
        if self._resolve_value("mini_calendar", "week_number_label_format") is None:
            wn_format = self._resolve_value("weekly.week_numbers", "label_format")
            if wn_format is not None:
                config.mini_week_number_label_format = wn_format

        # Apply color maps
        self._apply_color_maps(config)

        # Apply PIT sub-block decomposition (axis/leader/label/today_line/etc.)
        self._apply_pit_blocks(config)

        # Resolve band placement lists against the top-level time_bands catalog.
        # Post-migration themes ship a catalog of named bands at the top level
        # and per-visualizer placement lists (compact_plan.bands,
        # blockplan.top_bands, etc.) that reference catalog entries by name.
        # The renderers still read flat lists of band dicts from
        # config.compactplan_time_bands / blockplan_top_time_bands / etc., so
        # this expands the references into those flat lists.
        self._apply_band_placements(config)

        # Synthesize box:day rules from colors.federal_holiday /
        # colors.company_holiday before parsing — see method docstring.
        self._synthesize_holiday_box_day_rules()

        # Build the parsed UnifiedTheme (design §6) — single source of
        # truth for both the runtime API (resolve_token / find_rules) and
        # the ThemeStyles object (now derived from theme.rules in
        # _build_theme_styles, post-Phase-3-path-b).
        try:
            from config.unified_theme import parse_theme  # local import to avoid cycles
            config.theme = parse_theme(self._theme_data)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Theme '%s' could not be parsed as a unified theme: %s. "
                "ThemeStyles will be empty.",
                self._theme_name, exc,
            )
            config.theme = None

        # Build ThemeStyles from the parsed UnifiedTheme.
        if self._is_new_format():
            self._build_theme_styles(config)

        # Phase 2 wave 2: inject heuristic-derived size tokens so renderers
        # can drop their `tk.get("size") or config.<legacy>` fallback chain.
        # Reads the legacy size fields setfontsizes() wrote earlier in the
        # boot sequence — no-op on the first apply (legacy fields still at
        # their dataclass defaults), takes effect on the second apply (after
        # setfontsizes ran).  See config.config._inject_heuristic_size_tokens.
        from config.config import _inject_heuristic_size_tokens
        _inject_heuristic_size_tokens(config)

        return config

    def _synthesize_holiday_box_day_rules(self) -> None:
        """Convert ``colors.federal_holiday`` / ``colors.company_holiday`` into
        equivalent ``box:day`` rules so the unified-theme runtime is the
        single source of truth for holiday cell shading.

        Resolves Open Issue §2 of the runtime cutover: previously the mini
        renderer ran *two* layers (legacy ``_apply_holidays`` chain reading
        ``theme_federal_holiday_color`` first, then a ``find_rules("box:day")``
        pass overriding it).  The two layers produced surprising last-write-
        wins precedence when a theme defined both a ``colors.federal_holiday``
        section and an explicit ``apply_to: box:day`` rule.

        After this method runs, ``colors.federal_holiday.color`` is exposed
        as a synthesized ``box:day`` rule selected on
        ``{federal_holiday: true, nonworkday: true}``; ``colors.company_holiday``
        becomes the analogous rule on ``{company_holiday: true, nonworkday: true}``.
        Synthesized rules are *prepended* to ``style_rules`` so explicit
        theme rules later in the file still win in declaration order — matching
        the pre-migration "explicit overrides built-in" expectation.

        ``fill_opacity`` is hardcoded to the legacy mini-renderer values
        (0.2 federal, 0.25 company) rather than read from the section's
        ``alpha`` key, because the pre-migration mini code ignored ``alpha``
        and used those constants directly.  Other consumers
        (weekly / blockplan) continue to read ``alpha`` via the legacy
        CalendarConfig fields.

        Theme color, icon, and pattern from the holiday/special_day DB
        record itself remain handled by the legacy chains in
        ``mini/day_styles.py`` — those are per-row data, not theme style.
        """
        data = self._theme_data
        if not isinstance(data, dict):
            return
        colors = data.get("colors")
        if not isinstance(colors, dict):
            return

        synthesized: list[dict] = []
        fed = colors.get("federal_holiday")
        if isinstance(fed, dict) and fed.get("color"):
            synthesized.append({
                "name": "synthesized: colors.federal_holiday → box:day fill",
                "apply_to": "box:day",
                "select": {"federal_holiday": True, "nonworkday": True},
                "style": {"fill": fed["color"], "fill_opacity": 0.2},
            })
        comp = colors.get("company_holiday")
        if isinstance(comp, dict) and comp.get("color"):
            synthesized.append({
                "name": "synthesized: colors.company_holiday → box:day fill",
                "apply_to": "box:day",
                "select": {"company_holiday": True, "nonworkday": True},
                "style": {"fill": comp["color"], "fill_opacity": 0.25},
            })
        if not synthesized:
            return

        existing = data.get("style_rules")
        if not isinstance(existing, list):
            existing = []
        data["style_rules"] = synthesized + existing

    # Placement-list locations in a theme, paired with the target CalendarConfig
    # field that each visualizer's renderer reads.  Each entry may be a string
    # (catalog name) or a dict with ``band: <name>`` plus per-placement
    # overrides.
    _BAND_PLACEMENTS: tuple[tuple[str, str, str], ...] = (
        ("compact_plan", "bands",         "compactplan_time_bands"),
        ("blockplan",    "top_bands",     "blockplan_top_time_bands"),
        ("blockplan",    "bottom_bands",  "blockplan_bottom_time_bands"),
        ("gantt",        "top_bands",     "gantt_top_time_bands"),
        ("gantt",        "bottom_bands",  "gantt_bottom_time_bands"),
        ("excelheader",  "top_bands",     "excelheader_top_time_bands"),
        ("timeline",     "top_bands",     "timeline_top_time_bands"),
        ("timeline",     "bottom_bands",  "timeline_bottom_time_bands"),
    )

    def _apply_pit_blocks(self, config: "CalendarConfig") -> None:
        """Decompose the pit: YAML sub-blocks into individual config fields.

        Simple scalar keys from pit: are handled by THEME_TO_CONFIG_MAP.
        Nested blocks (axis, leader, leader_primary, leader_secondary,
        today_line, date_text, arrow_head, label) are handled here so each
        sub-key is written to its individual theme_pit_* or pit_* field.
        """
        pit = self._theme_data.get("pit", {})
        if not isinstance(pit, dict):
            return

        def _str(v: Any) -> str | None:
            return str(v) if v is not None else None

        def _flt(v: Any) -> float | None:
            try:
                return float(v)
            except (TypeError, ValueError):
                return None

        # --- pit.axis ---
        axis = pit.get("axis", {})
        if isinstance(axis, dict):
            if "color" in axis:
                config.theme_pit_axis_color = _str(axis["color"])
            if "width" in axis:
                v = _flt(axis["width"])
                if v is not None:
                    config.pit_axis_stroke_width = v
            if "marker_start" in axis:
                config.pit_axis_marker_start = str(axis["marker_start"])
            if "marker_start_size" in axis:
                v = _flt(axis["marker_start_size"])
                if v is not None:
                    config.pit_axis_marker_start_size = v
            if "marker_end" in axis:
                config.pit_axis_marker_end = str(axis["marker_end"])
            if "marker_end_size" in axis:
                v = _flt(axis["marker_end_size"])
                if v is not None:
                    config.pit_axis_marker_end_size = v
            # Bounding-box size of the built-in axis marker (circle/diamond).
            if "marker_size" in axis:
                v = _flt(axis["marker_size"])
                if v is not None:
                    config.pit_marker_size = v

        # --- pit.date_text ---
        date_text = pit.get("date_text", {})
        if isinstance(date_text, dict):
            if "color" in date_text:
                config.theme_pit_date_text_color = _str(date_text["color"])
            if "font_name" in date_text:
                config.theme_pit_date_text_font_name = _str(date_text["font_name"])
            if "font_size" in date_text:
                v = _flt(date_text["font_size"])
                if v is not None:
                    config.theme_pit_date_text_font_size = v
            if "offset" in date_text:
                v = _flt(date_text["offset"])
                if v is not None:
                    config.pit_date_text_offset = v
            if "placement" in date_text:
                config.pit_date_placement = str(date_text["placement"])

        # --- pit.leader (global leader defaults) ---
        def _apply_leader(d: dict, side: str = "global") -> None:
            """Apply one pit leader block (color/width/dasharray/stubs);
            side is "global" or a concrete side for per-side overrides."""
            if not isinstance(d, dict):
                return
            if side == "global":
                if "color" in d:
                    config.theme_pit_leader_color = _str(d["color"])
                if "width" in d:
                    v = _flt(d["width"])
                    if v is not None:
                        config.pit_leader_stroke_width = v
                if "dasharray" in d:
                    config.pit_leader_stroke_dasharray = _str(d["dasharray"])
                if "opacity" in d:
                    v = _flt(d["opacity"])
                    if v is not None:
                        config.pit_leader_stroke_opacity = v
                if "linecap" in d:
                    config.pit_leader_stroke_linecap = str(d["linecap"])
                if "linejoin" in d:
                    config.pit_leader_stroke_linejoin = str(d["linejoin"])
                if "marker_start" in d:
                    config.pit_leader_marker_start = str(d["marker_start"])
                if "marker_start_size" in d:
                    v = _flt(d["marker_start_size"])
                    if v is not None:
                        config.pit_leader_marker_start_size = v
                if "marker_end" in d:
                    config.pit_leader_marker_end = str(d["marker_end"])
                if "marker_end_size" in d:
                    v = _flt(d["marker_end_size"])
                    if v is not None:
                        config.pit_leader_marker_end_size = v
                if "end_stub" in d:
                    v = _flt(d["end_stub"])
                    if v is not None:
                        config.pit_leader_end_stub = v
            elif side == "primary":
                if "color" in d:
                    config.theme_pit_leader_primary_color = _str(d["color"])
            elif side == "secondary":
                if "color" in d:
                    config.theme_pit_leader_secondary_color = _str(d["color"])

        _apply_leader(pit.get("leader", {}), "global")
        _apply_leader(pit.get("leader_primary", {}), "primary")
        _apply_leader(pit.get("leader_secondary", {}), "secondary")

        # --- pit.today_line ---
        tl = pit.get("today_line", {})
        if isinstance(tl, dict):
            if "show" in tl:
                config.pit_show_today_line = bool(tl["show"])
            if "color" in tl:
                config.theme_pit_today_line_color = _str(tl["color"])
            if "width" in tl:
                v = _flt(tl["width"])
                if v is not None:
                    config.theme_pit_today_line_width = v
            if "dasharray" in tl:
                config.theme_pit_today_line_dasharray = _str(tl["dasharray"])
            if "opacity" in tl:
                v = _flt(tl["opacity"])
                if v is not None:
                    config.theme_pit_today_line_opacity = v
            if "linecap" in tl:
                config.theme_pit_today_line_linecap = _str(tl["linecap"])
            if "linejoin" in tl:
                config.theme_pit_today_line_linejoin = _str(tl["linejoin"])
            if "label" in tl:
                config.pit_today_line_label = str(tl["label"]) if tl["label"] is not None else ""
            if "label_color" in tl:
                config.theme_pit_today_line_label_color = _str(tl["label_color"])
            if "label_font_name" in tl:
                config.theme_pit_today_line_label_font_name = _str(tl["label_font_name"])
            if "label_font_size" in tl:
                v = _flt(tl["label_font_size"])
                if v is not None:
                    config.theme_pit_today_line_label_font_size = v
            if "label_position" in tl:
                config.theme_pit_today_line_label_position = _str(tl["label_position"])
            if "marker_start" in tl:
                config.pit_today_line_marker_start = str(tl["marker_start"])
            if "marker_start_size" in tl:
                v = _flt(tl["marker_start_size"])
                if v is not None:
                    config.pit_today_line_marker_start_size = v
            if "marker_end" in tl:
                config.pit_today_line_marker_end = str(tl["marker_end"])
            if "marker_end_size" in tl:
                v = _flt(tl["marker_end_size"])
                if v is not None:
                    config.pit_today_line_marker_end_size = v

        # --- pit.arrow_head ---
        ah = pit.get("arrow_head", {})
        if isinstance(ah, dict) and "color" in ah:
            config.theme_pit_arrow_head_color = _str(ah["color"])

        # --- pit.label ---
        lbl = pit.get("label", {})
        if isinstance(lbl, dict):
            if "stroke_color" in lbl:
                config.theme_pit_label_stroke_color = _str(lbl["stroke_color"])
            if "stroke_width" in lbl:
                v = _flt(lbl["stroke_width"])
                if v is not None:
                    config.pit_label_stroke_width = v
            if "fill_color" in lbl:
                config.theme_pit_label_fill_color = _str(lbl["fill_color"])
            if "fill_opacity" in lbl:
                v = _flt(lbl["fill_opacity"])
                if v is not None:
                    config.pit_label_fill_opacity = v
            if "pattern" in lbl:
                config.theme_pit_label_pattern = _str(lbl["pattern"])
            if "text_color" in lbl:
                config.theme_pit_label_text_color = _str(lbl["text_color"])
            if "corner_radius" in lbl:
                v = _flt(lbl["corner_radius"])
                if v is not None:
                    config.pit_label_corner_radius = v
            if "padding_x" in lbl:
                v = _flt(lbl["padding_x"])
                if v is not None:
                    config.pit_label_padding_x = v
            if "padding_y" in lbl:
                v = _flt(lbl["padding_y"])
                if v is not None:
                    config.pit_label_padding_y = v
            # Label-box icon sizing (glyph longest side / gap before name).
            if "icon_size" in lbl:
                config.pit_label_icon_size = _flt(lbl["icon_size"])
            if "icon_gap" in lbl:
                v = _flt(lbl["icon_gap"])
                if v is not None:
                    config.pit_label_icon_gap = v

    def _apply_band_placements(self, config: "CalendarConfig") -> None:
        """Expand placement-list references against the top-level time_bands catalog.

        Each placement entry is one of:

        * A string — looked up in the catalog as-is.  Unknown names are
          dropped with a warning.
        * A dict carrying ``band: <name>`` plus per-placement overrides —
          the overrides are merged on top of the catalog entry.
        * A bare dict with ``unit:`` (etc.) — passed through unchanged, so
          inline-only placements still work.
        """
        catalog = self._theme_data.get("time_bands")
        if not isinstance(catalog, dict):
            catalog = {}

        for section, key, config_field in self._BAND_PLACEMENTS:
            section_data = self._theme_data.get(section)
            if not isinstance(section_data, dict):
                continue
            placements = section_data.get(key)
            if not isinstance(placements, list):
                continue

            resolved: list[dict] = []
            for entry in placements:
                resolved_entry = self._resolve_band_placement(
                    entry, catalog, section=section, key=key,
                )
                if resolved_entry is not None:
                    resolved.append(resolved_entry)

            if resolved:
                try:
                    setattr(config, config_field, resolved)
                except (TypeError, ValueError) as exc:
                    logger.warning(
                        "Theme: could not set %s=%r: %s",
                        config_field, resolved, exc,
                    )

    def _resolve_band_placement(
        self,
        entry: Any,
        catalog: dict,
        *,
        section: str,
        key: str,
    ) -> dict | None:
        """Resolve one placement entry against the catalog.  Returns None on miss."""
        if isinstance(entry, str):
            cat = catalog.get(entry)
            if not isinstance(cat, dict):
                logger.warning(
                    "Theme: %s.%s references unknown time_band '%s'",
                    section, key, entry,
                )
                return None
            return dict(cat)

        if isinstance(entry, dict):
            name = entry.get("band")
            if isinstance(name, str):
                cat = catalog.get(name)
                if not isinstance(cat, dict):
                    logger.warning(
                        "Theme: %s.%s references unknown time_band '%s'",
                        section, key, name,
                    )
                    return None
                merged = dict(cat)
                for k, v in entry.items():
                    if k == "band":
                        continue
                    merged[k] = v
                return merged
            # Bare inline band definition (no catalog reference) — pass through.
            return dict(entry)

        logger.warning(
            "Theme: %s.%s contains a non-string/non-dict entry %r — skipped",
            section, key, entry,
        )
        return None

    def _apply_color_maps(self, config: "CalendarConfig") -> None:
        """Apply the colors: section to theme override fields on config."""
        colors = self._theme_data.get("colors", {})
        if not isinstance(colors, dict):
            return

        if "months" in colors and isinstance(colors["months"], dict):
            # Ensure keys are strings (YAML may parse "01" as int 1)
            config.theme_month_colors = {
                str(k).zfill(2): v for k, v in colors["months"].items()
            }

        if "fiscal_periods" in colors and isinstance(colors["fiscal_periods"], dict):
            # Ensure keys are strings (YAML may parse "01" as int 1)
            config.theme_fiscal_period_colors = {
                str(k).zfill(2): v for k, v in colors["fiscal_periods"].items()
            }

        if "hash_lines" in colors:
            config.theme_hash_line_color = colors["hash_lines"]

        if "resource_groups" in colors and isinstance(colors["resource_groups"], dict):
            config.theme_resource_group_colors = {
                str(k).lower(): v for k, v in colors["resource_groups"].items()
            }

        if "group_colors" in colors and isinstance(colors["group_colors"], list):
            config.group_colors = colors["group_colors"]

        # Holiday colors
        fed = colors.get("federal_holiday", {})
        if isinstance(fed, dict):
            if "color" in fed:
                config.theme_federal_holiday_color = fed["color"]
            # "opacity" is the current key; "alpha" accepted as a
            # deprecated alias (SIMPLIFICATION_PLAN 1.3).
            if "opacity" in fed:
                config.theme_federal_holiday_opacity = fed["opacity"]
            elif "alpha" in fed:
                config.theme_federal_holiday_opacity = fed["alpha"]

        comp = colors.get("company_holiday", {})
        if isinstance(comp, dict):
            if "color" in comp:
                config.theme_company_holiday_color = comp["color"]
            if "opacity" in comp:
                config.theme_company_holiday_opacity = comp["opacity"]
            elif "alpha" in comp:
                config.theme_company_holiday_opacity = comp["alpha"]

        # DB palette name references (resolved at render time)
        for yaml_key, config_field in (
            ("month_palette", "theme_month_palette"),
            ("fiscal_palette", "theme_fiscal_palette"),
            ("group_palette", "theme_group_palette"),
        ):
            val = colors.get(yaml_key)
            if val is not None:
                setattr(config, config_field, val)

        # Mini calendar theme color overrides
        # title_color / header_color / week_number_color were dropped in
        # the Phase 2 strip pass — no renderer reads them post-migration
        # (text:month_title / text:label / text:week_number tokens cover
        # those styling slots).
        mc = colors.get("mini_calendar", {})
        if isinstance(mc, dict):
            _MINI_COLOR_FIELDS = {
                "day_color": "theme_mini_day_color",
                "adjacent_month_color": "theme_mini_adjacent_month_color",
                "holiday_color": "theme_mini_holiday_color",
                "nonworkday_fill_color": "theme_mini_nonworkday_fill_color",
                "milestone_color": "theme_mini_milestone_color",
                "current_day_color": "theme_mini_current_day_color",
            }
            for yaml_key, config_field in _MINI_COLOR_FIELDS.items():
                if yaml_key in mc:
                    setattr(config, config_field, mc[yaml_key])

    # ─── New unified theme format support ─────────────────────────────────

    def _is_new_format(self) -> bool:
        """Return True if the theme uses the new unified format."""
        return bool(self._theme_data.keys() & _NEW_FORMAT_SECTIONS)

    def _build_theme_styles(self, config: "CalendarConfig") -> None:
        """Build ThemeStyles directly from the parsed UnifiedTheme.

        Replaces the legacy `_parse_text_styles` / `_parse_box_styles` /
        `_parse_line_styles` / `_parse_icon_styles` / `_parse_element_bindings`
        path that consumed the decompiled `self._theme_data["text_styles"]`
        etc. sections.  The decompiler bridge now exists only as a no-op
        compatibility shim during load (kept until any direct legacy-section
        readers are confirmed retired).

        Requires `config.theme` to be already populated (UnifiedTheme).
        """
        from config.styles import ThemeStyles
        from renderers.css_generator import generate_css

        theme = getattr(config, "theme", None)
        if theme is None:
            return

        text_styles = self._parse_text_styles_unified(theme)
        box_styles = self._parse_box_styles_unified(theme)
        line_styles = self._parse_line_styles_unified(theme)
        icon_styles = self._parse_icon_styles_unified(theme)
        self._apply_catalog_defaults(
            text_styles, box_styles, line_styles, icon_styles,
        )
        element_bindings = self._build_element_bindings_from_catalog(
            text_styles, box_styles, line_styles, icon_styles,
            element_overrides=self._theme_data.get("element_overrides") or {},
        )

        theme_styles = ThemeStyles(
            text_styles=text_styles,
            box_styles=box_styles,
            line_styles=line_styles,
            icon_styles=icon_styles,
            element_bindings=element_bindings,
        )
        theme_styles.css = generate_css(theme_styles)
        config.theme_styles = theme_styles

    @staticmethod
    def _parse_text_styles_unified(theme) -> dict:
        """Build {name: TextStyle} from `define text:<name>` rules."""
        from config.styles import TextStyle

        result: dict = {}
        for rule in theme.rules:
            if rule.define != "text" or not rule.as_name:
                continue
            style = rule.style or {}
            try:
                size = float(style.get("size", 8.0))
            except (TypeError, ValueError):
                size = 8.0
            try:
                opacity = float(style.get("opacity", 1.0))
            except (TypeError, ValueError):
                opacity = 1.0
            result[rule.as_name] = TextStyle(
                font=str(style.get("font", "RobotoCondensed-Light")),
                size=size,
                color=str(style.get("color", "#333333")),
                opacity=opacity,
                alignment=str(style.get("alignment", "start")),
                # size_rules are conditional rules, not part of the define;
                # they apply via UnifiedTheme.resolve_token().  TextStyle's
                # size_rules field is now informational/unused in the
                # post-Phase-1 token path.
                size_rules=(),
            )
        return result

    @staticmethod
    def _parse_box_styles_unified(theme) -> dict:
        """Build {name: BoxStyle} from `define box:<name>` rules.

        Reads the unified-form keys (`fill`, `stroke`, `dasharray`) directly
        — no decompiler-rename round-trip.
        """
        from config.styles import BoxStyle

        result: dict = {}
        for rule in theme.rules:
            if rule.define != "box" or not rule.as_name:
                continue
            style = rule.style or {}
            fc = style.get("fill_colors")
            if isinstance(fc, list):
                fill_colors = tuple(fc)
            else:
                fill_colors = None
            try:
                fill_opacity = float(style.get("fill_opacity", 1.0))
            except (TypeError, ValueError):
                fill_opacity = 1.0
            try:
                stroke_width = float(style.get("stroke_width", 0.5))
            except (TypeError, ValueError):
                stroke_width = 0.5
            try:
                stroke_opacity = float(style.get("stroke_opacity", 1.0))
            except (TypeError, ValueError):
                stroke_opacity = 1.0
            result[rule.as_name] = BoxStyle(
                fill=str(style.get("fill", "white")),
                fill_opacity=fill_opacity,
                stroke=style.get("stroke"),
                stroke_width=stroke_width,
                stroke_opacity=stroke_opacity,
                stroke_dasharray=style.get("dasharray"),
                fill_palette=style.get("fill_palette"),
                fill_colors=fill_colors,
            )
        return result

    @staticmethod
    def _parse_line_styles_unified(theme) -> dict:
        """Build {name: LineStyle} from `define line:<name>` rules."""
        from config.styles import LineStyle

        result: dict = {}
        for rule in theme.rules:
            if rule.define != "line" or not rule.as_name:
                continue
            style = rule.style or {}
            try:
                width = float(style.get("width", 0.5))
            except (TypeError, ValueError):
                width = 0.5
            try:
                opacity = float(style.get("opacity", 1.0))
            except (TypeError, ValueError):
                opacity = 1.0
            result[rule.as_name] = LineStyle(
                color=str(style.get("color", "#CCCCCC")),
                width=width,
                opacity=opacity,
                dasharray=style.get("dasharray"),
            )
        return result

    @staticmethod
    def _parse_icon_styles_unified(theme) -> dict:
        """Build {name: IconStyle} from `define icon:<name>` rules."""
        from config.styles import IconStyle

        result: dict = {}
        for rule in theme.rules:
            if rule.define != "icon" or not rule.as_name:
                continue
            style = rule.style or {}
            # Only carry through `size` when the theme actually declared it;
            # leaving it as None lets renderers fall back to their own size
            # (e.g. event_icon_size) instead of an arbitrary 10pt.
            size: float | None = None
            if "size" in style:
                try:
                    size = float(style["size"])
                except (TypeError, ValueError):
                    size = None
            result[rule.as_name] = IconStyle(
                color=str(style.get("color", "#333333")),
                size=size,
                icon=style.get("icon"),
            )
        return result

    # ec-class binding kind → ElementBinding field name.
    _BIND_KIND_TO_FIELD: dict[str, str] = {
        "text": "text_style",
        "box": "box_style",
        "line": "line_style",
        "icon": "icon_style",
    }

    # One-time warning state — keep noise out of the log on repeated apply().
    _FALLBACK_TOKENS_WARNED: set[tuple[str, str]] = set()

    @classmethod
    def _apply_catalog_defaults(
        cls,
        text_styles: dict,
        box_styles: dict,
        line_styles: dict,
        icon_styles: dict,
    ) -> None:
        """Fill in any catalog-referenced token the theme did not define.

        Looks at every ``(kind, token)`` pair the catalog binds an
        element to and, if the theme's token dict is missing that name,
        substitutes the fallback from ``element_catalog_defaults.yaml``.
        Logs a one-time INFO so theme authors can see what they inherited.
        """
        from config.element_catalog import iter_required_tokens, load_default_tokens
        from config.styles import BoxStyle, IconStyle, LineStyle, TextStyle

        defaults = load_default_tokens()
        kind_to_dict = {
            "text": text_styles,
            "box": box_styles,
            "line": line_styles,
            "icon": icon_styles,
        }
        kind_to_factory = {
            "text": cls._textstyle_from_dict,
            "box": cls._boxstyle_from_dict,
            "line": cls._linestyle_from_dict,
            "icon": cls._iconstyle_from_dict,
        }
        for kind, token in iter_required_tokens(None):
            dest = kind_to_dict[kind]
            if token in dest:
                continue
            fallback_body = defaults.get(kind, {}).get(token)
            if fallback_body is None:
                # The catalog loader already enforces this can't happen, but
                # be defensive.
                continue
            dest[token] = kind_to_factory[kind](fallback_body)
            if (kind, token) not in cls._FALLBACK_TOKENS_WARNED:
                cls._FALLBACK_TOKENS_WARNED.add((kind, token))
                logger.info(
                    "Theme: %s:%s not defined; using catalog fallback",
                    kind, token,
                )

    @staticmethod
    def _textstyle_from_dict(body: dict):
        """Build a TextStyle from an element_overrides body dict;
        malformed numbers fall back to defaults rather than raising."""
        from config.styles import TextStyle
        try:
            size = float(body.get("size", 8.0))
        except (TypeError, ValueError):
            size = 8.0
        try:
            opacity = float(body.get("opacity", 1.0))
        except (TypeError, ValueError):
            opacity = 1.0
        return TextStyle(
            font=str(body.get("font", "RobotoCondensed-Light")),
            size=size,
            color=str(body.get("color", "#333333")),
            opacity=opacity,
            alignment=str(body.get("alignment", "start")),
            size_rules=(),
        )

    @staticmethod
    def _boxstyle_from_dict(body: dict):
        """Build a BoxStyle from an element_overrides body dict;
        malformed numbers fall back to defaults rather than raising."""
        from config.styles import BoxStyle
        try:
            fill_opacity = float(body.get("fill_opacity", 1.0))
        except (TypeError, ValueError):
            fill_opacity = 1.0
        try:
            stroke_width = float(body.get("stroke_width", 0.5))
        except (TypeError, ValueError):
            stroke_width = 0.5
        try:
            stroke_opacity = float(body.get("stroke_opacity", 1.0))
        except (TypeError, ValueError):
            stroke_opacity = 1.0
        return BoxStyle(
            fill=str(body.get("fill", "white")),
            fill_opacity=fill_opacity,
            stroke=body.get("stroke"),
            stroke_width=stroke_width,
            stroke_opacity=stroke_opacity,
            stroke_dasharray=body.get("dasharray"),
        )

    @staticmethod
    def _linestyle_from_dict(body: dict):
        """Build a LineStyle from an element_overrides body dict;
        malformed numbers fall back to defaults rather than raising."""
        from config.styles import LineStyle
        try:
            width = float(body.get("width", 0.5))
        except (TypeError, ValueError):
            width = 0.5
        try:
            opacity = float(body.get("opacity", 1.0))
        except (TypeError, ValueError):
            opacity = 1.0
        return LineStyle(
            color=str(body.get("color", "#CCCCCC")),
            width=width,
            opacity=opacity,
            dasharray=body.get("dasharray"),
        )

    @staticmethod
    def _iconstyle_from_dict(body: dict):
        from config.styles import IconStyle
        size: float | None = None
        if "size" in body:
            try:
                size = float(body["size"])
            except (TypeError, ValueError):
                size = None
        return IconStyle(
            color=str(body.get("color", "#333333")),
            size=size,
            icon=body.get("icon"),
        )

    @classmethod
    def _build_element_bindings_from_catalog(
        cls,
        text_styles: dict,
        box_styles: dict,
        line_styles: dict,
        icon_styles: dict,
        *,
        element_overrides: dict,
    ) -> dict:
        """Build {ec-class: ElementBinding} from the built-in catalog.

        Every entry in ``config/element_catalog.yaml`` becomes a binding
        whose target style is looked up in the theme's parsed token dicts.
        Per-theme ``element_overrides:`` may remap an element to a
        different token or pin a per-element color.
        """
        from config.element_catalog import load_catalog
        from config.styles import ElementBinding

        kind_to_dict = {
            "text": text_styles,
            "box": box_styles,
            "line": line_styles,
            "icon": icon_styles,
        }
        catalog = load_catalog()
        result: dict = {}
        for class_name, entry in catalog.items():
            kind = entry.kind
            token_name = entry.token
            color_override: str | None = None
            extra = element_overrides.get(class_name) if isinstance(element_overrides, dict) else None
            if isinstance(extra, dict):
                use = extra.get("use")
                if isinstance(use, str) and ":" in use:
                    o_kind, _, o_token = use.partition(":")
                    if o_kind in cls._BIND_KIND_TO_FIELD:
                        kind, token_name = o_kind, o_token
                color_value = extra.get("color")
                if isinstance(color_value, str) and color_value:
                    color_override = color_value
            field_name = cls._BIND_KIND_TO_FIELD.get(kind)
            if field_name is None:
                continue
            kind_dict = kind_to_dict.get(kind, {})
            style_obj = kind_dict.get(token_name)
            if style_obj is None:
                logger.warning(
                    "Theme: element %s references unknown token %s:%s",
                    class_name, kind, token_name,
                )
                continue
            binding = ElementBinding()
            setattr(binding, field_name, style_obj)
            if color_override is not None:
                binding.color = color_override
            result[class_name] = binding
        return result

    # ── Rule-list support ─────────────────────────────────────────────────────

    def _check_deprecated_rule_keys(self) -> None:
        """Raise ThemeError if the YAML contains old-format rule keys."""
        # Per-theme `apply_to: element` bindings are now sourced from the
        # built-in element catalog (config/element_catalog.yaml).  Themes
        # may pin per-element tweaks via the top-level `element_overrides:`
        # mapping instead.  Reject leftover bindings with a clear pointer.
        style_rules = self._theme_data.get("style_rules") or []
        if isinstance(style_rules, list):
            for i, raw in enumerate(style_rules):
                if not isinstance(raw, dict):
                    continue
                apply_to = raw.get("apply_to")
                targets = (
                    [apply_to] if isinstance(apply_to, str)
                    else list(apply_to) if isinstance(apply_to, list)
                    else []
                )
                if "element" in targets:
                    name = raw.get("name", f"rule_{i}")
                    raise ThemeError(
                        f"style_rules[{i}] {name!r}: apply_to: element is no longer "
                        "supported in themes.  Element-to-token bindings live in "
                        "config/element_catalog.yaml; use the top-level "
                        "`element_overrides:` section for per-theme tweaks.  "
                        "Run tools/strip_element_bindings.py to convert this theme."
                    )

        weekly = self._theme_data.get("weekly", {}) or {}
        day_box = (weekly.get("day_box", {}) or {}) if isinstance(weekly, dict) else {}
        if isinstance(day_box, dict) and "hash_rules" in day_box:
            if day_box["hash_rules"]:  # non-empty list is an error; empty list is tolerated
                raise ThemeError(
                    "weekly.day_box.hash_rules is deprecated — run tools/migrate_theme.py "
                    "to convert to style_rules"
                )

        mini = self._theme_data.get("mini_calendar", {}) or {}
        mini_day_box = (mini.get("day_box", {}) or {}) if isinstance(mini, dict) else {}
        if isinstance(mini_day_box, dict) and "hash_rules" in mini_day_box:
            if mini_day_box["hash_rules"]:
                raise ThemeError(
                    "mini_calendar.day_box.hash_rules is deprecated — run "
                    "tools/migrate_theme.py to convert to style_rules"
                )

        blockplan = self._theme_data.get("blockplan", {}) or {}
        swimlanes = (blockplan.get("swimlanes", []) or []) if isinstance(blockplan, dict) else []
        for lane in (swimlanes if isinstance(swimlanes, list) else []):
            if isinstance(lane, dict) and "match" in lane:
                raise ThemeError(
                    f"blockplan.swimlanes[{lane.get('name', '?')!r}].match is deprecated — "
                    "run tools/migrate_theme.py to convert to swimlane_rules"
                )

    def _load_rule_lists(self, config: "CalendarConfig") -> None:
        """Load style_rules and swimlane_rules from the top-level theme data."""
        style_rules = self._theme_data.get("style_rules")
        if isinstance(style_rules, list):
            config.theme_style_rules = style_rules

        swimlane_rules = self._theme_data.get("swimlane_rules")
        if isinstance(swimlane_rules, list):
            config.theme_swimlane_rules = swimlane_rules
