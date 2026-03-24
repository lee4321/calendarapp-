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
    ("header.right", "font_family"): "header_right_font",
    ("header.right", "font_color"): "header_right_font_color",
    # Footer
    ("footer.left", "font_family"): "footer_left_font",
    ("footer.left", "font_color"): "footer_left_font_color",
    ("footer.center", "font_family"): "footer_center_font",
    ("footer.center", "font_color"): "footer_center_font_color",
    ("footer.right", "font_family"): "footer_right_font",
    ("footer.right", "font_color"): "footer_right_font_color",
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
    ("weekly.day_box", "hash_rules"): "theme_weekly_hash_rules",
    ("weekly.day_box", "hash_pattern"): "theme_weekly_hash_pattern",
    ("weekly.day_box", "hash_pattern_opacity"): "hash_pattern_opacity",
    ("weekly.day_box", "fill_color"): "day_box_fill_color",
    ("weekly.day_box", "fill_opacity"): "day_box_fill_opacity",
    ("weekly.day_box", "number_font"): "day_box_number_font",
    ("weekly.day_box", "number_color"): "day_box_number_color",
    ("weekly.day_box", "icon_color"): "day_box_icon_color",
    ("weekly.day_box", "font_color"): "day_box_font_color",
    # Base / global
    ("base", "default_missing_icon"): "default_missing_icon",
    # Events (icon/placement only — text fields moved to weekly.name_text/notes_text)
    ("events", "icon_color"): "event_icon_color",
    ("events", "item_placement_order"): "item_placement_order",
    # Durations (icon/stroke only — text fields moved to weekly.name_text/notes_text)
    ("durations", "icon_color"): "duration_icon_color",
    ("durations", "stroke_dasharray"): "duration_stroke_dasharray",
    # Weekly text styling (uniform)
    ("weekly.text", "font_name"): "weekly_text_font_name",
    ("weekly.text", "font_color"): "weekly_text_font_color",
    ("weekly.text", "font_size"): "weekly_text_font_size",
    ("weekly.text", "font_opacity"): "weekly_text_font_opacity",
    ("weekly.text", "alignment"): "weekly_text_alignment",
    ("weekly.name_text", "font_name"): "weekly_name_text_font_name",
    ("weekly.name_text", "font_color"): "weekly_name_text_font_color",
    ("weekly.name_text", "font_size"): "weekly_name_text_font_size",
    ("weekly.name_text", "font_opacity"): "weekly_name_text_font_opacity",
    ("weekly.name_text", "alignment"): "weekly_name_text_alignment",
    ("weekly.notes_text", "font_name"): "weekly_notes_text_font_name",
    ("weekly.notes_text", "font_color"): "weekly_notes_text_font_color",
    ("weekly.notes_text", "font_size"): "weekly_notes_text_font_size",
    ("weekly.notes_text", "font_opacity"): "weekly_notes_text_font_opacity",
    ("weekly.notes_text", "alignment"): "weekly_notes_text_alignment",
    # Timeline
    ("timeline", "background_color"): "timeline_background_color",
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
    ("timeline", "callout_offset_y"): "timeline_callout_offset_y",
    ("timeline", "duration_offset_y"): "timeline_duration_offset_y",
    ("timeline", "duration_lane_gap_y"): "timeline_duration_lane_gap_y",
    ("timeline", "label_stroke_width"): "timeline_label_stroke_width",
    ("timeline", "label_fill_opacity"): "timeline_label_fill_opacity",
    ("timeline", "duration_bar_fill_opacity"): "timeline_duration_bar_fill_opacity",
    ("timeline", "axis_stroke_dasharray"): "timeline_axis_stroke_dasharray",
    ("timeline", "tick_stroke_dasharray"): "timeline_tick_stroke_dasharray",
    ("timeline", "today_line_stroke_dasharray"): "timeline_today_line_stroke_dasharray",
    ("timeline", "label_stroke_dasharray"): "timeline_label_stroke_dasharray",
    (
        "timeline",
        "duration_bar_stroke_dasharray",
    ): "timeline_duration_bar_stroke_dasharray",
    ("timeline", "top_colors"): "timeline_top_colors",
    ("timeline", "bottom_colors"): "timeline_bottom_colors",
    ("timeline", "show_fiscal_periods"): "timeline_show_fiscal_periods",
    ("timeline", "show_fiscal_quarters"): "timeline_show_fiscal_quarters",
    ("timeline", "palette"): "theme_timeline_palette",
    # Timeline text styling (uniform)
    ("timeline.text", "font_name"): "timeline_text_font_name",
    ("timeline.text", "font_color"): "timeline_text_font_color",
    ("timeline.text", "font_size"): "timeline_text_font_size",
    ("timeline.text", "font_opacity"): "timeline_text_font_opacity",
    ("timeline.text", "alignment"): "timeline_text_alignment",
    ("timeline.name_text", "font_name"): "timeline_name_text_font_name",
    ("timeline.name_text", "font_color"): "timeline_name_text_font_color",
    ("timeline.name_text", "font_size"): "timeline_name_text_font_size",
    ("timeline.name_text", "font_opacity"): "timeline_name_text_font_opacity",
    ("timeline.name_text", "alignment"): "timeline_name_text_alignment",
    ("timeline.notes_text", "font_name"): "timeline_notes_text_font_name",
    ("timeline.notes_text", "font_color"): "timeline_notes_text_font_color",
    ("timeline.notes_text", "font_size"): "timeline_notes_text_font_size",
    ("timeline.notes_text", "font_opacity"): "timeline_notes_text_font_opacity",
    ("timeline.notes_text", "alignment"): "timeline_notes_text_alignment",
    # Timeline box/date fields (not renamed)
    ("timeline_events", "box_width"): "timeline_event_box_width",
    ("timeline_events", "box_height"): "timeline_event_box_height",
    ("timeline_durations", "box_width"): "timeline_duration_box_width",
    ("timeline_durations", "box_height"): "timeline_duration_box_height",
    ("timeline_durations", "date_font"): "timeline_duration_date_font",
    ("timeline_durations", "date_font_size"): "timeline_duration_date_font_size",
    ("timeline_durations", "date_color"): "timeline_duration_date_color",
    ("timeline.date", "font_family"): "timeline_date_font",
    ("timeline.date", "font_color"): "timeline_date_color",
    # Blockplan
    ("blockplan", "background_color"): "blockplan_background_color",
    ("blockplan", "grid_color"): "blockplan_grid_color",
    ("blockplan", "grid_opacity"): "blockplan_grid_opacity",
    ("blockplan", "grid_line_width"): "blockplan_grid_line_width",
    ("blockplan", "grid_dasharray"): "blockplan_grid_dasharray",
    ("blockplan", "timeband_line_color"): "blockplan_timeband_line_color",
    ("blockplan", "timeband_line_width"): "blockplan_timeband_line_width",
    ("blockplan", "timeband_line_opacity"): "blockplan_timeband_line_opacity",
    ("blockplan", "timeband_line_dasharray"): "blockplan_timeband_line_dasharray",
    ("blockplan", "label_column_ratio"): "blockplan_label_column_ratio",
    ("blockplan", "band_row_height"): "blockplan_band_row_height",
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
    ("blockplan", "timeband_label_color"): "blockplan_timeband_label_color",
    ("blockplan", "timeband_label_opacity"): "blockplan_timeband_label_opacity",
    ("blockplan", "timeband_fill_color"): "blockplan_timeband_fill_color",
    ("blockplan", "timeband_fill_palette"): "blockplan_timeband_fill_palette",
    ("blockplan", "timeband_fill_opacity"): "blockplan_timeband_fill_opacity",
    ("blockplan", "lane_heading_fill_color"): "blockplan_lane_heading_fill_color",
    ("blockplan", "lane_label_align_h"): "blockplan_lane_label_align_h",
    ("blockplan", "lane_label_align_v"): "blockplan_lane_label_align_v",
    ("blockplan", "lane_label_rotation"): "blockplan_lane_label_rotation",
    ("blockplan", "lane_split_ratio"): "blockplan_lane_split_ratio",
    ("blockplan", "event_show_date"): "blockplan_event_show_date",
    ("blockplan", "event_date_font"): "blockplan_event_date_font",
    ("blockplan", "event_date_font_size"): "blockplan_event_date_font_size",
    ("blockplan", "event_date_color"): "blockplan_event_date_color",
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
    ("blockplan", "marker_radius"): "blockplan_marker_radius",
    ("blockplan", "vertical_lines"): "blockplan_vertical_lines",
    ("blockplan", "vertical_line_color"): "blockplan_vertical_line_color",
    ("blockplan", "vertical_line_width"): "blockplan_vertical_line_width",
    ("blockplan", "vertical_line_dasharray"): "blockplan_vertical_line_dasharray",
    ("blockplan", "vertical_line_opacity"): "blockplan_vertical_line_opacity",
    ("blockplan", "vertical_line_fill_color"): "blockplan_vertical_line_fill_color",
    ("blockplan", "vertical_line_fill_opacity"): "blockplan_vertical_line_fill_opacity",
    ("blockplan", "header_font"): "blockplan_header_font",
    ("blockplan", "band_font"): "blockplan_band_font",
    ("blockplan", "lane_label_font"): "blockplan_lane_label_font",
    ("blockplan", "header_font_size"): "blockplan_header_font_size",
    ("blockplan", "band_font_size"): "blockplan_band_font_size",
    ("blockplan", "lane_label_font_size"): "blockplan_lane_label_font_size",
    # Blockplan text styling (uniform)
    ("blockplan.text", "font_name"): "blockplan_text_font_name",
    ("blockplan.text", "font_color"): "blockplan_text_font_color",
    ("blockplan.text", "font_size"): "blockplan_text_font_size",
    ("blockplan.text", "font_opacity"): "blockplan_text_font_opacity",
    ("blockplan.text", "alignment"): "blockplan_text_alignment",
    ("blockplan.name_text", "font_name"): "blockplan_name_text_font_name",
    ("blockplan.name_text", "font_color"): "blockplan_name_text_font_color",
    ("blockplan.name_text", "font_size"): "blockplan_name_text_font_size",
    ("blockplan.name_text", "font_opacity"): "blockplan_name_text_font_opacity",
    ("blockplan.name_text", "alignment"): "blockplan_name_text_alignment",
    ("blockplan.notes_text", "font_name"): "blockplan_notes_text_font_name",
    ("blockplan.notes_text", "font_color"): "blockplan_notes_text_font_color",
    ("blockplan.notes_text", "font_size"): "blockplan_notes_text_font_size",
    ("blockplan.notes_text", "font_opacity"): "blockplan_notes_text_font_opacity",
    ("blockplan.notes_text", "alignment"): "blockplan_notes_text_alignment",
    # Compact Activities Plan
    ("compact_plan", "background_color"): "compactplan_background_color",
    ("compact_plan", "time_bands"): "compactplan_time_bands",
    ("compact_plan", "band_row_height"): "compactplan_band_row_height",
    # Compact plan text styling (uniform)
    ("compact_plan.text", "font_name"): "compactplan_text_font_name",
    ("compact_plan.text", "font_color"): "compactplan_text_font_color",
    ("compact_plan.text", "font_size"): "compactplan_text_font_size",
    ("compact_plan.text", "font_opacity"): "compactplan_text_font_opacity",
    ("compact_plan.text", "alignment"): "compactplan_text_alignment",
    ("compact_plan.name_text", "font_name"): "compactplan_name_text_font_name",
    ("compact_plan.name_text", "font_color"): "compactplan_name_text_font_color",
    ("compact_plan.name_text", "font_size"): "compactplan_name_text_font_size",
    ("compact_plan.name_text", "font_opacity"): "compactplan_name_text_font_opacity",
    ("compact_plan.name_text", "alignment"): "compactplan_name_text_alignment",
    ("compact_plan.notes_text", "font_name"): "compactplan_notes_text_font_name",
    ("compact_plan.notes_text", "font_color"): "compactplan_notes_text_font_color",
    ("compact_plan.notes_text", "font_size"): "compactplan_notes_text_font_size",
    ("compact_plan.notes_text", "font_opacity"): "compactplan_notes_text_font_opacity",
    ("compact_plan.notes_text", "alignment"): "compactplan_notes_text_alignment",
    ("compact_plan", "show_axis"): "compactplan_show_axis",
    ("compact_plan", "axis_color"): "compactplan_axis_color",
    ("compact_plan", "axis_width"): "compactplan_axis_width",
    ("compact_plan", "axis_dasharray"): "compactplan_axis_dasharray",
    ("compact_plan", "axis_opacity"): "compactplan_axis_opacity",
    ("compact_plan", "axis_padding"): "compactplan_axis_padding",
    ("compact_plan", "duration_line_width"): "compactplan_duration_line_width",
    ("compact_plan", "duration_stroke_dasharray"): "compactplan_duration_stroke_dasharray",
    ("compact_plan", "duration_opacity"): "compactplan_duration_opacity",
    ("compact_plan", "show_duration_icons"): "compactplan_show_duration_icons",
    ("compact_plan", "duration_icon_list"): "compactplan_duration_icon_list",
    ("compact_plan", "duration_icon_height"): "compactplan_duration_icon_height",
    ("compact_plan", "duration_icon_color"): "compactplan_duration_icon_color",
    ("compact_plan", "lane_spacing"): "compactplan_lane_spacing",
    ("compact_plan", "palette"): "compactplan_palette",
    ("compact_plan", "palette_name"): "theme_compactplan_palette_name",
    ("compact_plan", "milestone_color"): "compactplan_milestone_color",
    ("compact_plan", "milestone_icon"): "compactplan_milestone_icon",
    ("compact_plan", "milestone_flag_width"): "compactplan_milestone_flag_width",
    ("compact_plan", "milestone_flag_height"): "compactplan_milestone_flag_height",
    ("compact_plan", "show_milestone_labels"): "compactplan_show_milestone_labels",
    ("compact_plan", "show_legend"): "compactplan_show_legend",
    ("compact_plan", "legend_swatch_width"): "compactplan_legend_swatch_width",
    ("compact_plan", "legend_row_height"): "compactplan_legend_row_height",
    ("compact_plan", "legend_area_ratio"): "compactplan_legend_area_ratio",
    ("compact_plan", "header_bottom_y"): "compactplan_header_bottom_y",
    ("compact_plan", "key_top_y"): "compactplan_key_top_y",
    ("compact_plan", "show_milestone_list"): "compactplan_show_milestone_list",
    ("compact_plan", "milestone_list_date_format"): "compactplan_milestone_list_date_format",
    ("compact_plan", "milestone_list_date_color"): "compactplan_milestone_list_date_color",
    ("compact_plan", "milestone_list_row_height"): "compactplan_milestone_list_row_height",
    ("compact_plan", "milestone_list_date_col_width"): "compactplan_milestone_list_date_col_width",
    ("compact_plan", "milestone_list_section_gap"): "compactplan_milestone_list_section_gap",
    ("compact_plan", "legend_column_split"): "compactplan_legend_column_split",
    ("compact_plan", "legend_team_columns"): "compactplan_legend_team_columns",
    ("compact_plan", "show_continuation_icon"): "compactplan_show_continuation_icon",
    ("compact_plan", "continuation_icon"): "compactplan_continuation_icon",
    ("compact_plan", "continuation_icon_height"): "compactplan_continuation_icon_height",
    ("compact_plan", "continuation_icon_color"): "compactplan_continuation_icon_color",
    ("compact_plan", "continuation_legend_text"): "compactplan_continuation_legend_text",
    ("compact_plan", "continuation_section_gap"): "compactplan_continuation_section_gap",
    ("compact_plan", "show_axis_legend"): "compactplan_show_axis_legend",
    ("compact_plan", "legend_axis_text"): "compactplan_legend_axis_text",
    # Overflow (weekly)
    ("weekly.overflow", "icon"): "overflow_indicator_icon",
    ("weekly.overflow", "color"): "overflow_indicator_color",
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
    ("mini_calendar", "cell_font"): "mini_cell_font",
    ("mini_calendar", "cell_bold_font"): "mini_cell_bold_font",
    ("mini_calendar", "title_font"): "mini_title_font",
    ("mini_calendar", "title_font_size"): "mini_title_font_size",
    ("mini_calendar", "title_color"): "mini_title_color",
    ("mini_calendar", "header_font"): "mini_header_font",
    ("mini_calendar", "header_font_size"): "mini_header_font_size",
    ("mini_calendar", "header_color"): "mini_header_color",
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
    ("mini_calendar", "grid_line_stroke_color"): "mini_grid_line_stroke_color",
    ("mini_calendar", "grid_line_stroke_width"): "mini_grid_line_stroke_width",
    ("mini_calendar", "grid_line_stroke_opacity"): "mini_grid_line_stroke_opacity",
    ("mini_calendar", "week_number_font"): "mini_week_number_font",
    ("mini_calendar", "week_number_font_size"): "mini_week_number_font_size",
    ("mini_calendar", "week_number_color"): "mini_week_number_color",
    ("mini_calendar", "week_number_label_format"): "mini_week_number_label_format",
    ("mini_calendar.day_box", "hash_rules"): "theme_mini_day_box_hash_rules",
    # Mini details page
    ("mini_details", "title_text"): "mini_details_title_text",
    ("mini_details", "title_font"): "mini_details_title_font",
    ("mini_details", "title_font_size"): "mini_details_title_font_size",
    ("mini_details", "title_color"): "mini_details_title_color",
    ("mini_details", "header_font"): "mini_details_header_font",
    ("mini_details", "header_font_size"): "mini_details_header_font_size",
    ("mini_details", "header_color"): "mini_details_header_color",
    # Mini details text styling (uniform)
    ("mini_details.text", "font_name"): "mini_details_text_font_name",
    ("mini_details.text", "font_color"): "mini_details_text_font_color",
    ("mini_details.text", "font_size"): "mini_details_text_font_size",
    ("mini_details.text", "font_opacity"): "mini_details_text_font_opacity",
    ("mini_details.text", "alignment"): "mini_details_text_alignment",
    ("mini_details.name_text", "font_name"): "mini_details_name_text_font_name",
    ("mini_details.name_text", "font_color"): "mini_details_name_text_font_color",
    ("mini_details.name_text", "font_size"): "mini_details_name_text_font_size",
    ("mini_details.name_text", "font_opacity"): "mini_details_name_text_font_opacity",
    ("mini_details.name_text", "alignment"): "mini_details_name_text_alignment",
    ("mini_details.notes_text", "font_name"): "mini_details_notes_text_font_name",
    ("mini_details.notes_text", "font_color"): "mini_details_notes_text_font_color",
    ("mini_details.notes_text", "font_size"): "mini_details_notes_text_font_size",
    ("mini_details.notes_text", "font_opacity"): "mini_details_notes_text_font_opacity",
    ("mini_details.notes_text", "alignment"): "mini_details_notes_text_alignment",
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
    ("mini_calendar", "grid_line_stroke_dasharray"): "mini_grid_line_stroke_dasharray",
    ("mini_calendar", "cell_box_stroke_dasharray"): "mini_cell_box_stroke_dasharray",
    (
        "mini_calendar",
        "strikethrough_stroke_dasharray",
    ): "mini_strikethrough_stroke_dasharray",
    ("mini_calendar", "hash_line_stroke_dasharray"): "mini_hash_line_stroke_dasharray",
    (
        "mini_calendar",
        "duration_bar_stroke_dasharray",
    ): "mini_duration_bar_stroke_dasharray",
    (
        "mini_calendar",
        "duration_bar_stroke_opacity",
    ): "mini_duration_bar_stroke_opacity",
    (
        "mini_details",
        "separator_stroke_dasharray",
    ): "mini_details_separator_stroke_dasharray",
    ("timeline", "connector_stroke_dasharray"): "timeline_connector_stroke_dasharray",
    (
        "timeline",
        "duration_bracket_stroke_dasharray",
    ): "timeline_duration_bracket_stroke_dasharray",
    # ExcelHeader
    ("excelheader", "font_name"): "excelheader_font_name",
    ("excelheader", "font_size"): "excelheader_font_size",
    ("excelheader", "top_time_bands"): "excelheader_top_time_bands",
    ("excelheader", "vertical_lines"): "excelheader_vertical_lines",
    ("excelheader", "vertical_line_color"): "excelheader_vertical_line_color",
    ("excelheader", "vertical_line_width"): "excelheader_vertical_line_width",
    ("excelheader", "vertical_line_dasharray"): "excelheader_vertical_line_dasharray",
    ("excelheader", "vertical_line_opacity"): "excelheader_vertical_line_opacity",
    ("excelheader", "vertical_line_fill_color"): "excelheader_vertical_line_fill_color",
    ("excelheader", "vertical_line_fill_opacity"): "excelheader_vertical_line_fill_opacity",
    ("excelheader", "band_row_height"): "excelheader_band_row_height",
    ("excelheader", "header_heading_fill_color"): "excelheader_header_heading_fill_color",
    ("excelheader", "header_label_color"): "excelheader_header_label_color",
    ("excelheader", "header_label_align_h"): "excelheader_header_label_align_h",
    ("excelheader", "timeband_fill_color"): "excelheader_timeband_fill_color",
    ("excelheader", "timeband_fill_palette"): "excelheader_timeband_fill_palette",
    ("excelheader", "timeband_label_color"): "excelheader_timeband_label_color",
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
        "colors",
        "mini_calendar",
        "fiscal",
        "mini_details",
        "text_mini",
        "layout",
        "blockplan",
        "excelheader",
        "compact_plan",
    }
)

# Keys that reference font names (for validation)
FONT_KEYS = frozenset({"font_family", "font_name", "number_font", "notes_font"})


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
        """Return names of built-in themes (without .yaml extension)."""
        themes: list[str] = []
        if cls.BUILTIN_THEMES_DIR.exists():
            for f in sorted(cls.BUILTIN_THEMES_DIR.glob("*.yaml")):
                themes.append(f.stem)
        return themes

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

        from config.config import FONT_REGISTRY

        self._validate_fonts(self._theme_data, FONT_REGISTRY)

    def _validate_fonts(
        self,
        data: Any,
        registry: dict[str, str],
        path: str = "",
    ) -> None:
        """Recursively check that font reference values are in FONT_REGISTRY."""
        if isinstance(data, dict):
            for key, value in data.items():
                current_path = f"{path}.{key}" if path else key
                if key in FONT_KEYS and isinstance(value, str):
                    if value not in registry:
                        logger.warning(
                            "Theme font '%s' at '%s' is not in FONT_REGISTRY",
                            value,
                            current_path,
                        )
                else:
                    self._validate_fonts(value, registry, current_path)

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
                ("header_font_size", "mini_details_header_font_size"),
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

        # Normalize weekly day-box hash rule config.
        if config.theme_weekly_hash_rules is not None and not isinstance(
            config.theme_weekly_hash_rules, list
        ):
            logger.warning(
                "Theme: day_box.hash_rules must be a list; got %r",
                type(config.theme_weekly_hash_rules).__name__,
            )
            config.theme_weekly_hash_rules = None
        if config.theme_mini_day_box_hash_rules is not None and not isinstance(
            config.theme_mini_day_box_hash_rules, list
        ):
            logger.warning(
                "Theme: mini_calendar.day_box.hash_rules must be a list; got %r",
                type(config.theme_mini_day_box_hash_rules).__name__,
            )
            config.theme_mini_day_box_hash_rules = None

        # If mini week number label format isn't set, fall back to week_numbers
        if self._resolve_value("mini_calendar", "week_number_label_format") is None:
            wn_format = self._resolve_value("weekly.week_numbers", "label_format")
            if wn_format is not None:
                config.mini_week_number_label_format = wn_format

        # Apply color maps
        self._apply_color_maps(config)

        return config

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

        if "special_day" in colors:
            config.theme_special_day_color = colors["special_day"]

        if "hash_lines" in colors:
            config.theme_hash_line_color = colors["hash_lines"]

        if "resource_groups" in colors and isinstance(colors["resource_groups"], dict):
            config.theme_resource_group_colors = {
                str(k).lower(): v for k, v in colors["resource_groups"].items()
            }

        if "special_day_types" in colors and isinstance(
            colors["special_day_types"], dict
        ):
            config.theme_special_day_type_colors = colors["special_day_types"]

        if "group_colors" in colors and isinstance(colors["group_colors"], list):
            config.group_colors = colors["group_colors"]

        # Holiday colors
        fed = colors.get("federal_holiday", {})
        if isinstance(fed, dict):
            if "color" in fed:
                config.theme_federal_holiday_color = fed["color"]
            if "alpha" in fed:
                config.theme_federal_holiday_alpha = fed["alpha"]

        comp = colors.get("company_holiday", {})
        if isinstance(comp, dict):
            if "color" in comp:
                config.theme_company_holiday_color = comp["color"]
            if "alpha" in comp:
                config.theme_company_holiday_alpha = comp["alpha"]

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
        mc = colors.get("mini_calendar", {})
        if isinstance(mc, dict):
            _MINI_COLOR_FIELDS = {
                "title_color": "theme_mini_title_color",
                "header_color": "theme_mini_header_color",
                "day_color": "theme_mini_day_color",
                "adjacent_month_color": "theme_mini_adjacent_month_color",
                "holiday_color": "theme_mini_holiday_color",
                "nonworkday_fill_color": "theme_mini_nonworkday_fill_color",
                "milestone_color": "theme_mini_milestone_color",
                "week_number_color": "theme_mini_week_number_color",
                "current_day_color": "theme_mini_current_day_color",
            }
            for yaml_key, config_field in _MINI_COLOR_FIELDS.items():
                if yaml_key in mc:
                    setattr(config, config_field, mc[yaml_key])
