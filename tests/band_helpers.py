"""Test helpers: put timescale rows on a config's version-3.0 theme.

``set_bands`` takes rows the way the retired band dictionaries spelled them
(``date_format``, ``show_every``, ``row_height``, ``fill_color`` ...) so a test
reads as it always did while the config holds a real schema ``Theme``.
"""

from __future__ import annotations

import dataclasses
from typing import Any

from config.theme_loader import load_theme
from config.theme_schema import Theme


def row(band: dict[str, Any]) -> dict[str, Any]:
    """One band dictionary as a timescale row mapping."""
    b = dict(band)
    out: dict[str, Any] = {"unit": b.pop("unit", "date")}
    renames = {
        "label": "label",
        "show_every": "every",
        "row_height": "height",
        "fill_color": "fill",
        "fill_palette": "fill_palette",
        "fill_opacity": "fill_opacity",
        "week_start": "week_start",
        "label_values": "label_values",
        "icon_rules": "icon_rules",
        "icon_height": "icon_height",
        "interval_days": "interval_days",
        "prefix": "prefix",
        "start_index": "start_index",
        "max_index": "max_index",
        "anchor_date": "anchor_date",
        "anchor": "anchor_date",
        "fiscal_year_start_month": "fiscal_year_start_month",
        "target_date": "reference_date",
        "start_date": "reference_date",
        "skip_weekends": "skip_weekends",
        "skip_nonworkdays": "skip_nonworkdays",
    }
    for old, new in renames.items():
        if old in b:
            out[new] = b.pop(old)
    fmt = b.pop("date_format", None) or b.pop("label_format", None)
    b.pop("label_format", None)
    if fmt is not None:
        out["format"] = fmt
    if "stroke_color" in b:
        out["border"] = {"color": b.pop("stroke_color")}
    text = {}
    for old, new in (("font_size", "size"), ("font_color", "color"), ("font", "font")):
        if old in b:
            text[new] = b.pop(old)
    if text:
        out["text"] = text
    if "nonworkdays_only" in b:
        out["holidays"] = {"nonworkdays_only": b.pop("nonworkdays_only")}
    for key in (
        "height",
        "every",
        "format",
        "end_format",
        "fill",
        "vline",
        "vfill",
        "tick",
        "border",
        "text",
        "holidays",
    ):
        if key in b:
            out[key] = b.pop(key)
    b.pop("label_color", None)
    b.pop("label_font_size", None)
    b.pop("label_align_h", None)
    b.pop("label_fill_color", None)
    b.pop("fill_rules", None)
    return out


def theme_with(primary: list | None = None, secondary: list | None = None, **sections: Any) -> Theme:
    data: dict[str, Any] = {"theme": {"name": "t", "version": "3.0"}, **sections}
    data["timescale"] = {
        **sections.get("timescale", {}),
        "primary": [row(b) for b in primary or []],
        "secondary": [row(b) for b in secondary or []],
    }
    return load_theme(data)


def set_bands(config: Any, primary: list | None = None, secondary: list | None = None) -> None:
    """Replace the timescale rows of ``config.theme_v3`` (``None`` leaves that side alone)."""
    data = dataclasses.asdict(config.theme_v3)
    if primary is not None:
        data["timescale"]["primary"] = [row(b) for b in primary]
    if secondary is not None:
        data["timescale"]["secondary"] = [row(b) for b in secondary]
    config.theme_v3 = load_theme(data)


def update_theme(config: Any, **sections: Any) -> None:
    """Merge *sections* (mappings, as in a theme file) into ``config.theme_v3``."""
    data = dataclasses.asdict(config.theme_v3)
    for name, value in sections.items():
        if isinstance(value, dict) and isinstance(data.get(name), dict):
            data[name] = _merge(data[name], value)
        else:
            data[name] = value
    config.theme_v3 = load_theme(data)


def _merge(base: dict, over: dict) -> dict:
    out = dict(base)
    for k, v in over.items():
        out[k] = _merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def set_orientation(config: Any, orientation: Any) -> None:
    """Point ``config.theme_v3``'s axis horizontal or vertical (a string or an ``Orientation``)."""
    update_theme(config, timescale={"axis": {"orientation": getattr(orientation, "value", orientation)}})


#: Config attribute names a test may still pass, and where each now lives in the theme.
_THEME_FIELDS: dict[str, tuple[str, ...]] = {
    "weekly_number_duration_icons": ("durations", "replace_icons_with_numbers"),
    "mini_number_duration_icons": ("durations", "replace_icons_with_numbers"),
    "candybar_number_duration_icons": ("durations", "replace_icons_with_numbers"),
    "timeline_number_duration_icons": ("durations", "replace_icons_with_numbers"),
    "blockplan_number_duration_icons": ("durations", "replace_icons_with_numbers"),
    "gantt_number_duration_icons": ("durations", "replace_icons_with_numbers"),
    "pit_number_duration_icons": ("durations", "replace_icons_with_numbers"),
    "compactplan_number_duration_icons": ("durations", "replace_icons_with_numbers"),
    "excelblockplan_number_duration_icons": ("durations", "replace_icons_with_numbers"),
    "item_placement_order": ("events", "item_placement_order"),
    "event_icon_color": ("icons", "event", "color"),
    "duration_icon_list": ("durations", "number_duration_icons"),
    "duration_icon_size": ("durations", "icon_size"),
    "duration_icon_background_color": ("durations", "icon_background_color"),
    "duration_icon_stroke_color": ("durations", "icon_stroke_color"),
    "timeline_duration_offset_y": ("timeline", "duration_offset_y"),
    "timeline_duration_lane_gap_y": ("timeline", "duration_lane_gap_y"),
    "timeline_label_side": ("timeline", "label_side"),
    "timeline_duration_side": ("timeline", "duration_side"),
    "timeline_labella_layer_gap": ("timeline", "labella", "layer_gap"),
    "timeline_labella_node_height": ("timeline", "labella", "node_height"),
    "timeline_labella_density": ("timeline", "labella", "density"),
    "timeline_labella_min_pos": ("timeline", "labella", "min_pos"),
    "timeline_labella_max_pos": ("timeline", "labella", "max_pos"),
    "timeline_event_box_width": ("timeline", "events", "box_width"),
    "timeline_event_box_height": ("timeline", "events", "box_height"),
    "timeline_event_placement": ("timeline", "events", "placement"),
    "timeline_event_row_gap": ("timeline", "events", "row_gap"),
    "timeline_event_box_gap": ("timeline", "events", "box_gap"),
    "timeline_event_box_pad": ("timeline", "events", "inner_pad"),
    "timeline_event_icon_column_ratio": ("timeline", "events", "icon_column_ratio"),
    "timeline_duration_box_width": ("timeline", "durations", "box_width"),
    "timeline_duration_icon_column_ratio": ("timeline", "durations", "icon_column_ratio"),
    "timeline_duration_box_height": ("timeline", "durations", "box_height"),
    "blockplan_label_column_ratio": ("blockplan", "label_column_ratio"),
    "blockplan_band_label_column_ratio": ("blockplan", "band_label_column_ratio"),
    "blockplan_fiscal_year_start_month": ("fiscal", "year_start_month"),
    "blockplan_show_unmatched_lane": ("blockplan", "show_unmatched_lane"),
    "blockplan_unmatched_lane_name": ("blockplan", "unmatched_lane_name"),
    "blockplan_lane_match_mode": ("blockplan", "lane_match_mode"),
    "blockplan_swimlanes": ("blockplan", "swimlanes"),
    "blockplan_lane_label_align_h": ("blockplan", "lane_label_align_h"),
    "blockplan_lane_label_align_v": ("blockplan", "lane_label_align_v"),
    "blockplan_lane_label_rotation": ("blockplan", "lane_label_rotation"),
    "blockplan_lane_split_ratio": ("blockplan", "lane_split_ratio"),
    "blockplan_duration_bar_height": ("blockplan", "duration_bar_height"),
    "blockplan_duration_row_gap": ("blockplan", "duration_row_gap"),
    "gantt_columns": ("gantt", "columns"),
    "gantt_table_width_ratio": ("gantt", "table_width_ratio"),
    "gantt_row_height": ("gantt", "row_height"),
    "gantt_header_row_height": ("gantt", "header_row_height"),
    "gantt_indent_per_level": ("gantt", "indent_per_level"),
    "gantt_min_day_width": ("gantt", "min_day_width"),
    "gantt_milestone_icon": ("gantt", "marks", "milestone"),
    "gantt_deadline_icon": ("gantt", "marks", "deadline"),
    "gantt_rollup_icon": ("gantt", "marks", "rollup"),
    "gantt_milestone_flag_icon": ("gantt", "marks", "milestone_flag"),
    "gantt_snapped_event_icon": ("gantt", "marks", "snapped_event"),
    "gantt_offchart_dep_icon": ("gantt", "marks", "offchart_dependency"),
    "gantt_link_ref_icon_families": ("gantt", "marks", "link_ref_icon_families"),
    "gantt_link_ref_family_size": ("gantt", "marks", "link_ref_family_size"),
    "gantt_link_ref_max_icons": ("gantt", "marks", "link_ref_max_icons"),
    "gantt_continuation_icon": ("continuation", "icon_after"),
    "gantt_bar_height": ("gantt", "bar_height"),
    "gantt_float_opacity_scale": ("gantt", "float_opacity_scale"),
    "gantt_show_dependencies": ("gantt", "show_dependencies"),
    "include_details_markdown": ("details", "markdown", "enable"),
    "details_md_title_text": ("details", "markdown", "title_text"),
    "details_md_sections": ("details", "markdown", "sections"),
    "details_md_events_section_text": ("details", "markdown", "events_section_text"),
    "details_md_colors_section_text": ("details", "markdown", "colors_section_text"),
    "details_md_symbols_section_text": ("details", "markdown", "symbols_section_text"),
    "details_md_exceptions_section_text": ("details", "markdown", "exceptions_section_text"),
    "details_md_holidays_section_text": ("details", "markdown", "holidays_section_text"),
    "details_md_empty_exceptions_text": ("details", "markdown", "empty_exceptions_text"),
    "details_md_empty_cell_text": ("details", "markdown", "empty_cell_text"),
    "details_md_icon_mode": ("details", "markdown", "icon_mode"),
    "details_md_color_mode": ("details", "markdown", "color_mode"),
    "details_md_group_by": ("details", "markdown", "group_by"),
    "details_md_sort": ("details", "markdown", "sort"),
    "details_md_columns": ("details", "markdown", "columns"),
    "details_md_exception_columns": ("details", "markdown", "exception_columns"),
    "details_md_holiday_columns": ("details", "markdown", "holiday_columns"),
    "include_details_icons": ("details", "icons", "enable"),
    "details_icons_size": ("details", "icons", "size"),
    "include_details_csv": ("details", "csv", "enable"),
    "details_csv_columns": ("details", "csv", "columns"),
    "details_csv_render_columns": ("details", "csv", "render_columns"),
    "compactplan_duration_line_width": ("compact_plan", "duration_line_width"),
    "compactplan_duration_date_column_ratio": ("compact_plan", "duration_date_column_ratio"),
    "compactplan_lane_spacing": ("compact_plan", "lane_spacing"),
    "compactplan_milestone_flag_width": ("compact_plan", "milestone_flag_width"),
    "compactplan_milestone_flag_height": ("compact_plan", "milestone_flag_height"),
    "compactplan_show_milestone_labels": ("compact_plan", "show_milestone_labels"),
    "compactplan_header_bottom_y": ("compact_plan", "header_bottom_y"),
    "compactplan_continuation_legend_text": ("compact_plan", "continuation_legend_text"),
    "compactplan_continuation_before_legend_text": ("compact_plan", "continuation_before_legend_text"),
    "compactplan_show_axis_legend": ("compact_plan", "show_axis_legend"),
    "compactplan_legend_axis_text": ("compact_plan", "legend_axis_text"),
    "compactplan_milestone_icon": ("icons", "milestone", "name"),
    "compactplan_text_font_name": ("text", "event_name", "font"),
    "compactplan_name_text_font_name": ("text", "event_name", "font"),
    "compactplan_name_text_font_size": ("text", "event_name", "size"),
    "compactplan_notes_text_font_name": ("text", "event_notes", "font"),
    "overflow_indicator_icon": ("overflow", "icon"),
    "show_continuation_icon": ("continuation", "show"),
    "continuation_icon_before": ("continuation", "icon_before"),
    "continuation_icon_after": ("continuation", "icon_after"),
    "continuation_icon_height": ("continuation", "icon_height"),
    "continuation_icon_color": ("continuation", "icon_color"),
    "watermark_text": ("watermark", "text"),
    "watermark_font": ("watermark", "font_family"),
    "watermark_font_size": ("watermark", "font_size"),
    "watermark_resize_mode": ("watermark", "resize_mode"),
    "watermark_opacity": ("watermark", "opacity"),
    "watermark_rotation_angle": ("watermark", "rotation_angle"),
    "watermark_image": ("watermark", "image"),
    "watermark_image_rotation_angle": ("watermark", "image_rotation_angle"),
    "fiscal_year_offset": ("fiscal", "year_offset"),
    "mini_show_adjacent": ("mini_calendar", "show_adjacent"),
    "text_mini_cell_width": ("text_mini", "cell_width"),
    "text_mini_month_gap": ("text_mini", "month_gap"),
    "candybar_row_height": ("candybar", "row_height"),
    "candybar_cell_width": ("candybar", "cell_width"),
    "candybar_weeknum_col_ratio": ("candybar", "weeknum_col_ratio"),
    "candybar_month_col_ratio": ("candybar", "month_col_ratio"),
    "candybar_week_start": ("candybar", "week_start"),
    "candybar_suppress_weekends": ("candybar", "suppress_weekends"),
    "candybar_show_week_numbers": ("candybar", "show_week_numbers"),
    "candybar_max_rows_per_page": ("candybar", "max_rows_per_page"),
    "candybar_grid_lines": ("candybar", "grid_lines"),
    "candybar_month_shading": ("candybar", "month_shading"),
    "pit_label_side": ("pit", "label_side"),
    "pit_leader_label_anchor": ("pit", "leader_label_anchor"),
    "pit_labella_layer_gap": ("pit", "labella", "layer_gap"),
    "pit_labella_node_height": ("pit", "labella", "node_height"),
    "pit_labella_density": ("pit", "labella", "density"),
    "pit_label_padding_x": ("pit", "label", "padding_x"),
    "pit_label_padding_y": ("pit", "label", "padding_y"),
    "pit_label_icon_size": ("pit", "label", "icon_size"),
    "pit_label_icon_gap": ("pit", "label", "icon_gap"),
    "pit_date_text_offset": ("pit", "date_offset"),
    "pit_date_placement": ("pit", "date_placement"),
    "mini_title_font_size": ("text", "month_title", "size"),
    "mini_header_font_size": ("text", "label", "size"),
    "mini_cell_font_size": ("text", "day_number", "size"),
    "blockplan_palette": ("palettes", "event"),
    "compactplan_palette": ("palettes", "event"),
    "blockplan_wbs_group_depth": ("durations", "wbs_group_depth"),
    "blockplan_duration_show_start_date": ("durations", "dates", "show_start"),
    "blockplan_duration_show_end_date": ("durations", "dates", "show_end"),
    "blockplan_duration_date_format": ("durations", "dates", "format"),
    "blockplan_duration_icon_visible": ("durations", "show_icons"),
    "compactplan_duration_show_start_date": ("durations", "dates", "show_start"),
    "compactplan_duration_show_end_date": ("durations", "dates", "show_end"),
    "compactplan_duration_date_format": ("durations", "dates", "format"),
    "compactplan_duration_name_color": ("durations", "name_color"),
    "compactplan_duration_date_color": ("durations", "dates", "color"),
    "blockplan_event_show_date": ("events", "date", "show"),
    "blockplan_event_date_format": ("events", "date", "format"),
    "blockplan_marker_radius": ("events", "marker", "radius"),
    "timeline_date_format": ("events", "date", "format"),
    "pit_date_format": ("events", "date", "format"),
    "timeline_marker_radius": ("events", "marker", "radius"),
    "timeline_icon_size": ("icons", "event", "size"),
    "timeline_duration_icon_visible": ("durations", "show_icons"),
    "timeline_wbs_group_depth": ("durations", "wbs_group_depth"),
    "timeline_duration_date_font_size": ("durations", "dates", "font_size"),
    "timeline_top_colors": ("palettes", "event"),
    "timeline_bottom_colors": ("palettes", "event"),
    "timeline_name_text_font_size": ("text", "event_name", "size"),
    "timeline_notes_text_font_size": ("text", "event_notes", "size"),
    "pit_default_event_icon": ("icons", "event", "name"),
    "pit_default_milestone_icon": ("icons", "milestone", "name"),
    "theme_pit_label_pattern": ("boxes", "callout", "pattern"),
    "pit_label_fill_opacity": ("boxes", "callout", "fill_opacity"),
    "theme_pit_label_fill_color": ("boxes", "callout", "fill"),
    "default_missing_icon": ("icons", "missing", "name"),
    "default_missing_icon_size": ("icons", "missing", "size"),
    "default_missing_icon_color": ("icons", "missing", "color"),
    "mini_circle_milestones": ("mini_calendar", "circle_milestones"),
    "mini_event_icon_scale": ("mini_calendar", "event_icon_scale"),
    "mini_event_icon_opacity": ("mini_calendar", "event_icon_opacity"),
    "mini_grid_lines": ("mini_calendar", "grid_lines"),
    "mini_icon_set": ("mini_calendar", "icon_set"),
    "mini_week_number_label_format": ("week_numbers", "label_format"),
    "week_number_label_format": ("week_numbers", "label_format"),
    "fiscal_period_label_format": ("fiscal", "label_format"),
    "fiscal_use_period_colors": ("fiscal", "use_period_colors"),
    "shade_current_day": ("today", "highlight", "show"),
}


def set_fields(config: Any, **values: Any) -> None:
    """``setattr`` each value on *config*; names that moved into the theme update ``theme_v3`` instead."""
    sections: dict[str, Any] = {}
    for key, value in values.items():
        if key == "theme_style_rules":
            sections["style_rules"] = [{"name": f"rule {i}", **rule} for i, rule in enumerate(value)]
            continue
        path = _THEME_FIELDS.get(key)
        if path is None:
            setattr(config, key, value)
            continue
        node = sections
        for part in path[:-1]:
            node = node.setdefault(part, {})
        node[path[-1]] = value
    if sections:
        update_theme(config, **sections)
