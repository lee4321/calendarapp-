"""Tests for the CSS-like theme engine."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
import yaml

from config.config import CalendarConfig, create_calendar_config
from config.theme_engine import ThemeEngine, ThemeError


class TestThemeEngineListing:
    """Tests for listing available themes."""

    def test_list_available_themes_returns_builtin_names(self):
        themes = ThemeEngine.list_available_themes()
        assert "default" in themes
        assert "corporate" in themes
        assert "dark" in themes
        assert "vibrant" in themes

    def test_list_available_themes_returns_sorted(self):
        themes = ThemeEngine.list_available_themes()
        assert themes == sorted(themes)


class TestThemeEngineLoading:
    """Tests for loading themes."""

    def test_load_builtin_theme_by_name(self):
        engine = ThemeEngine()
        engine.load("corporate")
        assert engine.theme_name == "Corporate"

    def test_load_builtin_theme_default(self):
        engine = ThemeEngine()
        engine.load("default")
        assert engine.theme_name == "Default"

    def test_load_nonexistent_theme_raises_error(self):
        engine = ThemeEngine()
        with pytest.raises(ThemeError, match="Theme not found"):
            engine.load("nonexistent_theme_xyz")

    def test_load_custom_yaml_file(self):
        theme_data = {
            "theme": {"name": "Custom Test", "version": "1.0"},
            "base": {"font_family": "Roboto-Bold", "font_color": "red"},
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(theme_data, f)
            f.flush()
            engine = ThemeEngine()
            engine.load(f.name)
            assert engine.theme_name == "Custom Test"

    def test_load_invalid_yaml_raises_error(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("{{invalid yaml: [")
            f.flush()
            engine = ThemeEngine()
            with pytest.raises(ThemeError, match="Invalid YAML"):
                engine.load(f.name)


class TestThemeEngineCascading:
    """Tests for CSS-like cascading resolution."""

    def _make_engine(self, theme_data: dict) -> ThemeEngine:
        """Helper to create a ThemeEngine with given data."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(theme_data, f)
            f.flush()
            engine = ThemeEngine()
            engine.load(f.name)
        return engine

    def test_element_level_overrides_section_level(self):
        """header.left.font_color should override header.font_color."""
        engine = self._make_engine(
            {
                "theme": {"name": "Test"},
                "header": {
                    "font_color": "blue",
                    "left": {"font_color": "red"},
                },
            }
        )
        config = create_calendar_config()
        engine.apply(config)
        assert config.header_left_font_color == "red"

    def test_section_level_overrides_base(self):
        """header.font_color should override base.font_color."""
        engine = self._make_engine(
            {
                "theme": {"name": "Test"},
                "base": {"font_color": "green"},
                "header": {"font_color": "blue"},
            }
        )
        config = create_calendar_config()
        engine.apply(config)
        # header.left inherits from header since no left-specific value
        assert config.header_left_font_color == "blue"

    def test_base_level_applies_when_no_section(self):
        """base.font_name should apply to weekly text when no weekly section."""
        engine = self._make_engine(
            {
                "theme": {"name": "Test"},
                "base": {"font_name": "Roboto-Bold"},
            }
        )
        config = create_calendar_config()
        engine.apply(config)
        assert config.weekly_name_text_font_name == "Roboto-Bold"
        assert config.weekly_notes_text_font_name == "Roboto-Bold"

    def test_section_level_used_when_no_element_level(self):
        """header.font_family applies to header.left when left has no font_family."""
        engine = self._make_engine(
            {
                "theme": {"name": "Test"},
                "header": {
                    "font_family": "Roboto-Bold",
                    "left": {"font_color": "red"},
                },
            }
        )
        config = create_calendar_config()
        engine.apply(config)
        assert config.header_left_font == "Roboto-Bold"
        assert config.header_left_font_color == "red"

    def test_no_theme_data_returns_config_unchanged(self):
        """An empty theme should not modify config defaults."""
        engine = ThemeEngine()
        config = create_calendar_config()
        original_color = config.weekly_name_text_font_color
        engine.apply(config)
        assert config.weekly_name_text_font_color == original_color


class TestThemeEngineApply:
    """Tests for applying theme values to CalendarConfig."""

    def _load_builtin(self, name: str) -> tuple[ThemeEngine, CalendarConfig]:
        engine = ThemeEngine()
        engine.load(name)
        config = create_calendar_config()
        engine.apply(config)
        return engine, config

    def test_corporate_theme_applies_header_color(self):
        _, config = self._load_builtin("corporate")
        assert config.header_left_font_color == "midnightblue"

    def test_dark_theme_applies_day_box_color(self):
        _, config = self._load_builtin("dark")
        assert config.day_box_number_color == "whitesmoke"

    def test_vibrant_theme_applies_event_color(self):
        _, config = self._load_builtin("vibrant")
        assert config.event_icon_color == "deeppink"

    def test_default_theme_matches_original_defaults(self):
        """The default theme should match the original hardcoded values."""
        _, config = self._load_builtin("default")
        assert config.weekly_name_text_font_color == "navy"
        assert config.day_box_number_color == "white"
        assert config.day_box_icon_color == "red"
        assert config.header_left_font_color == "grey"

    def test_day_box_styling_applied(self):
        _, config = self._load_builtin("corporate")
        assert config.day_box_stroke_color == "lightsteelblue"
        assert config.day_box_stroke_opacity == 0.4
        assert config.day_box_stroke_width == 3

    def test_watermark_styling_applied(self):
        _, config = self._load_builtin("dark")
        assert config.watermark_color == "dimgrey"
        assert config.watermark_opacity == 0.15
        assert config.watermark_rotation_angle == 0.0
        assert config.watermark_image_rotation_angle == 0.0

    def test_watermark_rotation_applied_from_theme(self):
        theme_data = {
            "theme": {"name": "WatermarkAngles"},
            "watermark": {
                "text": "CONFIDENTIAL",
                "rotation_angle": 17.5,
                "image_rotation_angle": -22.0,
                "font_size": 144,
                "resize_mode": "stretch",
            },
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(theme_data, f)
            f.flush()
            engine = ThemeEngine()
            engine.load(f.name)
            config = create_calendar_config()
            engine.apply(config)
        assert config.watermark_text == "CONFIDENTIAL"
        assert config.watermark_rotation_angle == 17.5
        assert config.watermark_image_rotation_angle == -22.0
        assert config.watermark_font_size == 144
        assert config.watermark_resize_mode == "stretch"

    def test_base_size_rule_applies_desired_font_size_for_papersize(self):
        theme_data = {
            "theme": {"name": "BaseSizeRule"},
            "base": {
                "size_rule": [
                    {"font_size": 12, "when": {"papersize": ["letter", "ledger"]}},
                    {"font_size": 8, "when": {"papersize": ["3x5", "5x8"]}},
                ]
            },
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(theme_data, f)
            f.flush()
            engine = ThemeEngine()
            engine.load(f.name)
            config = create_calendar_config()
            config.papersize = "Letter"
            engine.apply(config)
        assert config.desired_font_size == 12

    def test_element_size_rule_applies_week_number_font_size(self):
        theme_data = {
            "theme": {"name": "ElementSizeRuleWeekNumbers"},
            "weekly": {
                "week_numbers": {
                    "size_rule": [
                        {"font_size": 14, "when": {"papersize": ["letter"]}},
                    ]
                }
            },
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(theme_data, f)
            f.flush()
            engine = ThemeEngine()
            engine.load(f.name)
            config = create_calendar_config()
            config.papersize = "Letter"
            engine.apply(config)
        assert config.week_number_font_size == 14

    def test_element_size_rule_applies_specific_mini_calendar_sizes(self):
        theme_data = {
            "theme": {"name": "ElementSizeRuleMini"},
            "mini_calendar": {
                "size_rule": [
                    {
                        "title_font_size": 18,
                        "cell_font_size": 10,
                        "when": {"papersize": ["letter"]},
                    },
                ]
            },
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(theme_data, f)
            f.flush()
            engine = ThemeEngine()
            engine.load(f.name)
            config = create_calendar_config()
            config.papersize = "Letter"
            engine.apply(config)
        assert config.mini_title_font_size == 18
        assert config.mini_cell_font_size == 10

    def test_timeline_text_font_sizes_applied_from_theme(self):
        theme_data = {
            "theme": {"name": "TimelineTextSizes"},
            "timeline": {
                "name_text": {"font_size": 16},
                "notes_text": {"font_size": 11},
            },
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(theme_data, f)
            f.flush()
            engine = ThemeEngine()
            engine.load(f.name)
            config = create_calendar_config()
            engine.apply(config)
        assert config.timeline_name_text_font_size == 16
        assert config.timeline_notes_text_font_size == 11

    def test_layout_margin_with_units_sets_side_margins_and_enables_margin(self):
        theme_data = {
            "theme": {"name": "LayoutMargins"},
            "layout": {
                "margin": {
                    "top": "0.5in",
                    "right": "10mm",
                    "bottom": 12,
                    "left": {"value": 0.25, "unit": "in"},
                }
            },
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(theme_data, f)
            f.flush()
            engine = ThemeEngine()
            engine.load(f.name)
            config = create_calendar_config()
            config.include_margin = False
            engine.apply(config)

        assert config.include_margin is True
        assert config.margin_top == 36.0
        assert round(config.margin_right, 3) == round(10 * 72.0 / 25.4, 3)
        assert config.margin_bottom == 12.0
        assert config.margin_left == 18.0

    def test_mini_details_theme_applied(self):
        theme_data = {
            "theme": {"name": "MiniDetails"},
            "mini_details": {
                "title_text": "Details",
                "name_text": {"font_color": "purple"},
                "headers": ["Start", "Name"],
                "column_widths": [0.4, 0.6],
                "output_suffix": "_more",
            },
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(theme_data, f)
            f.flush()
            engine = ThemeEngine()
            engine.load(f.name)
            config = create_calendar_config()
            engine.apply(config)

        assert config.mini_details_title_text == "Details"
        assert config.mini_details_name_text_font_color == "purple"
        assert config.mini_details_headers == ["Start", "Name"]
        assert config.mini_details_column_widths == [0.4, 0.6]
        assert config.mini_details_output_suffix == "_more"

    def test_timeline_theme_applied(self):
        theme_data = {
            "theme": {"name": "Timeline"},
            "timeline": {
                "background_color": "black",
                "axis_color": "white",
                "date_format": "YYYY-MM-DD",
                "tick_label_format": "MMM YYYY",
                "today_date": "2026-03-17",
                "today_label_text": "Reference",
                "today_label_offset_y": 22.0,
                "marker_radius": 6.5,
                "icon_size": 11.0,
                "callout_offset_y": 120,
                "duration_offset_y": 80,
                "duration_lane_gap_y": 14,
                "top_colors": ["red", "blue"],
                "name_text": {"font_name": "Roboto-Bold", "font_color": "gold", "font_size": 14.5},
                "notes_text": {
                    "font_name": "RobotoCondensed-Bold",
                    "font_color": "silver",
                    "font_size": 11.5,
                },
                "date": {"font_family": "Roboto-Bold", "font_color": "orange"},
            },
            "timeline_events": {
                "box_width": 180,
                "box_height": 80,
            },
            "timeline_durations": {
                "box_width": 120,
                "box_height": 36,
            },
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(theme_data, f)
            f.flush()
            engine = ThemeEngine()
            engine.load(f.name)
            config = create_calendar_config()
            engine.apply(config)

        assert config.timeline_background_color == "black"
        assert config.timeline_axis_color == "white"
        assert config.timeline_date_format == "YYYY-MM-DD"
        assert config.timeline_tick_label_format == "MMM YYYY"
        assert config.timeline_today_date == "2026-03-17"
        assert config.timeline_today_label_text == "Reference"
        assert config.timeline_today_label_offset_y == 22.0
        assert config.timeline_marker_radius == 6.5
        assert config.timeline_icon_size == 11.0
        assert config.timeline_callout_offset_y == 120
        assert config.timeline_duration_offset_y == 80
        assert config.timeline_duration_lane_gap_y == 14
        assert config.timeline_top_colors == ["red", "blue"]
        assert config.timeline_name_text_font_name == "Roboto-Bold"
        assert config.timeline_name_text_font_color == "gold"
        assert config.timeline_notes_text_font_name == "RobotoCondensed-Bold"
        assert config.timeline_notes_text_font_color == "silver"
        assert config.timeline_name_text_font_size == 14.5
        assert config.timeline_notes_text_font_size == 11.5
        assert config.timeline_event_box_width == 180
        assert config.timeline_event_box_height == 80
        assert config.timeline_duration_box_width == 120
        assert config.timeline_duration_box_height == 36
        assert config.timeline_date_font == "Roboto-Bold"
        assert config.timeline_date_color == "orange"


class TestThemeEngineColorMaps:
    """Tests for color map overrides."""

    def _load_builtin(self, name: str) -> CalendarConfig:
        engine = ThemeEngine()
        engine.load(name)
        config = create_calendar_config()
        engine.apply(config)
        return config

    def test_month_palette_applied(self):
        config = self._load_builtin("corporate")
        assert config.theme_month_palette == "Blues"

    def test_month_colors_applied_explicit_dict(self):
        """Explicit months: dict (not palette) should populate theme_month_colors."""
        theme_data = {
            "theme": {"name": "Test"},
            "colors": {"months": {1: "aliceblue", "02": "lavender"}},
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(theme_data, f)
            f.flush()
            engine = ThemeEngine()
            engine.load(f.name)
            config = create_calendar_config()
            engine.apply(config)

        assert config.theme_month_colors is not None
        assert config.theme_month_colors["01"] == "aliceblue"
        assert config.theme_month_colors["02"] == "lavender"

    def test_special_day_color_applied(self):
        config = self._load_builtin("dark")
        assert config.theme_special_day_color == "teal"

    def test_hash_line_color_applied(self):
        config = self._load_builtin("corporate")
        assert config.theme_hash_line_color == "lightsteelblue"

    def test_fiscal_period_colors_applied(self):
        theme_data = {
            "theme": {"name": "Test"},
            "colors": {"fiscal_periods": {1: "red", "02": "blue", "13": "green"}},
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(theme_data, f)
            f.flush()
            engine = ThemeEngine()
            engine.load(f.name)
            config = create_calendar_config()
            engine.apply(config)

        assert config.theme_fiscal_period_colors is not None
        assert config.theme_fiscal_period_colors["01"] == "red"
        assert config.theme_fiscal_period_colors["02"] == "blue"
        assert config.theme_fiscal_period_colors["13"] == "green"

    def test_resource_group_colors_applied(self):
        config = self._load_builtin("corporate")
        assert config.theme_resource_group_colors is not None
        assert config.theme_resource_group_colors["a"] == "midnightblue"

    def test_holiday_colors_applied(self):
        config = self._load_builtin("dark")
        assert config.theme_federal_holiday_color == "indianred"
        assert config.theme_federal_holiday_alpha == 0.3
        assert config.theme_company_holiday_color == "darkseagreen"
        assert config.theme_company_holiday_alpha == 0.3

    def test_group_palette_applied(self):
        config = self._load_builtin("vibrant")
        assert config.theme_group_palette == "PairedColor12Steps"

    def test_group_colors_list_overridden_explicit(self):
        """Explicit group_colors: list (not palette) should override config.group_colors."""
        theme_data = {
            "theme": {"name": "Test"},
            "colors": {"group_colors": ["deeppink", "dodgerblue"]},
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(theme_data, f)
            f.flush()
            engine = ThemeEngine()
            engine.load(f.name)
            config = create_calendar_config()
            engine.apply(config)

        assert "deeppink" in config.group_colors

    def test_no_theme_leaves_color_maps_none(self):
        engine = ThemeEngine()
        config = create_calendar_config()
        engine.apply(config)
        assert config.theme_month_colors is None
        assert config.theme_special_day_color is None

    def test_month_color_keys_are_zero_padded_strings(self):
        """YAML might parse '01' as int 1; engine should normalize to '01'."""
        theme_data = {
            "theme": {"name": "Test"},
            "colors": {"months": {1: "lightgrey", 2: "grey", 12: "aliceblue"}},
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(theme_data, f)
            f.flush()
            engine = ThemeEngine()
            engine.load(f.name)
            config = create_calendar_config()
            engine.apply(config)

        assert config.theme_month_colors is not None
        for key in config.theme_month_colors:
            assert isinstance(key, str)
            assert len(key) == 2


class TestStrokeDasharray:
    """Tests for stroke-dasharray theme support."""

    def _apply_theme_data(self, theme_data: dict) -> CalendarConfig:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(theme_data, f)
            f.flush()
            engine = ThemeEngine()
            engine.load(f.name)
            config = create_calendar_config()
            engine.apply(config)
        return config

    def test_day_box_stroke_dasharray_applied_from_theme(self):
        config = self._apply_theme_data(
            {
                "theme": {"name": "Dash"},
                "weekly": {"day_box": {"stroke_dasharray": "5,3"}},
            }
        )
        assert config.day_box_stroke_dasharray == "5,3"

    def test_hash_pattern_applied_from_theme(self):
        config = self._apply_theme_data(
            {
                "theme": {"name": "Pat"},
                "weekly": {"day_box": {"hash_pattern": "brick-wall"}},
            }
        )
        assert config.theme_weekly_hash_pattern == "brick-wall"

    def test_hash_pattern_opacity_applied_from_theme(self):
        config = self._apply_theme_data(
            {
                "theme": {"name": "Pat"},
                "weekly": {"day_box": {"hash_pattern_opacity": 0.2}},
            }
        )
        assert config.hash_pattern_opacity == 0.2

    def test_weekly_hash_rules_applied_from_theme(self):
        rules = [
            {
                "style": 12,
                "color": "gold",
                "min_match": 1,
                "when": {"nonworkday": True, "milestone": True},
            }
        ]
        config = self._apply_theme_data(
            {
                "theme": {"name": "HashRules"},
                "weekly": {"day_box": {"hash_rules": rules}},
            }
        )
        assert config.theme_weekly_hash_rules == rules

    def test_duration_stroke_dasharray_applied_from_theme(self):
        config = self._apply_theme_data(
            {
                "theme": {"name": "Dash"},
                "durations": {"stroke_dasharray": "4,2"},
            }
        )
        assert config.duration_stroke_dasharray == "4,2"

    def test_dasharray_defaults_to_none(self):
        config = create_calendar_config()
        assert config.day_box_stroke_dasharray is None
        assert config.duration_stroke_dasharray is None
        assert config.hash_pattern_opacity == 0.15
        assert config.theme_weekly_hash_pattern is None

    def test_svg_base_draw_rect_emits_dasharray(self):
        """stroke_dasharray should appear in generated SVG rectangle."""
        import drawsvg
        from renderers.svg_base import BaseSVGRenderer

        class _Stub(BaseSVGRenderer):
            def _render_content(self, *a, **kw):
                return 0, []

        renderer = _Stub()
        renderer._page_height = 100
        renderer._page_width = 100
        renderer._drawing = drawsvg.Drawing(100, 100)
        renderer._draw_rect(
            10, 10, 50, 30, fill="red", stroke="blue", stroke_dasharray="6,3"
        )
        svg_text = renderer._drawing.as_svg()
        assert "stroke-dasharray" in svg_text
        assert "6,3" in svg_text

    def test_svg_base_draw_line_emits_dasharray(self):
        """stroke_dasharray should appear in generated SVG line."""
        import drawsvg
        from renderers.svg_base import BaseSVGRenderer

        class _Stub(BaseSVGRenderer):
            def _render_content(self, *a, **kw):
                return 0, []

        renderer = _Stub()
        renderer._page_height = 100
        renderer._page_width = 100
        renderer._drawing = drawsvg.Drawing(100, 100)
        renderer._draw_line(10, 10, 90, 10, stroke="grey", stroke_dasharray="4,2")
        svg_text = renderer._drawing.as_svg()
        assert "stroke-dasharray" in svg_text
        assert "4,2" in svg_text

    def test_svg_base_draw_lines_emits_dasharray(self):
        """stroke_dasharray should appear on the group in generated SVG."""
        import drawsvg
        from renderers.svg_base import BaseSVGRenderer

        class _Stub(BaseSVGRenderer):
            def _render_content(self, *a, **kw):
                return 0, []

        renderer = _Stub()
        renderer._page_height = 100
        renderer._page_width = 100
        renderer._drawing = drawsvg.Drawing(100, 100)
        renderer._draw_lines(
            [(10, 10, 90, 10), (10, 20, 90, 20)], stroke="black", stroke_dasharray="3,3"
        )
        svg_text = renderer._drawing.as_svg()
        assert "stroke-dasharray" in svg_text
        assert "3,3" in svg_text

    def test_none_dasharray_omitted_from_svg(self):
        """When stroke_dasharray is None, it should not appear in SVG output."""
        import drawsvg
        from renderers.svg_base import BaseSVGRenderer

        class _Stub(BaseSVGRenderer):
            def _render_content(self, *a, **kw):
                return 0, []

        renderer = _Stub()
        renderer._page_height = 100
        renderer._page_width = 100
        renderer._drawing = drawsvg.Drawing(100, 100)
        renderer._draw_rect(
            10, 10, 50, 30, fill="red", stroke="blue", stroke_dasharray=None
        )
        svg_text = renderer._drawing.as_svg()
        assert "stroke-dasharray" not in svg_text

    def test_svg_base_draw_text_emits_transform_wrapper(self):
        """_draw_text should wrap generated glyphs when transform is provided."""
        import drawsvg
        from unittest.mock import patch
        from renderers.svg_base import BaseSVGRenderer

        class _Stub(BaseSVGRenderer):
            def _render_content(self, *a, **kw):
                return 0, []

        renderer = _Stub()
        renderer._page_height = 100
        renderer._page_width = 100
        renderer._drawing = drawsvg.Drawing(100, 100)

        with (
            patch("config.config.get_font_path", return_value="fake.ttf"),
            patch(
                "renderers.svg_base.text_to_svg_group", return_value='<g id="glyphs"/>'
            ),
        ):
            renderer._draw_text(
                50,
                50,
                "WM",
                "Roboto-Bold",
                12,
                transform="rotate(30 50 50)",
            )
        svg_text = renderer._drawing.as_svg()
        assert 'transform="rotate(30 50 50)"' in svg_text
        assert 'id="glyphs"' in svg_text

    def test_render_text_watermark_passes_rotation_transform(self):
        """_render_text_watermark should pass rotate(...) for watermark text."""
        import drawsvg
        from unittest.mock import patch
        from renderers.svg_base import BaseSVGRenderer
        from config.config import create_calendar_config

        class _Stub(BaseSVGRenderer):
            def _render_content(self, *a, **kw):
                return 0, []

        renderer = _Stub()
        renderer._page_height = 100
        renderer._page_width = 200
        renderer._drawing = drawsvg.Drawing(200, 100)

        config = create_calendar_config()
        config.pageX = 200
        config.pageY = 100
        config.watermark_text = "WM"
        config.watermark_font_size = 200
        config.watermark_resize_mode = "fit"
        config.watermark_rotation_angle = 30

        with (
            patch("config.config.get_font_path", return_value="fake.ttf"),
            patch("renderers.svg_base.shrinktext", return_value=60),
            patch.object(renderer, "_draw_text") as mock_draw_text,
        ):
            renderer._render_text_watermark(config)

        _, kwargs = mock_draw_text.call_args
        assert kwargs["transform"] == "rotate(30.0 100.0 50.0)"

    def test_render_text_watermark_stretch_mode_applies_scale_transform(self):
        """Stretch mode should apply a scale transform around page center."""
        import drawsvg
        from unittest.mock import patch
        from renderers.svg_base import BaseSVGRenderer
        from config.config import create_calendar_config

        class _Stub(BaseSVGRenderer):
            def _render_content(self, *a, **kw):
                return 0, []

        renderer = _Stub()
        renderer._page_height = 100
        renderer._page_width = 200
        renderer._drawing = drawsvg.Drawing(200, 100)

        config = create_calendar_config()
        config.pageX = 200
        config.pageY = 100
        config.watermark_text = "WM"
        config.watermark_font_size = 200
        config.watermark_resize_mode = "stretch"

        with (
            patch("config.config.get_font_path", return_value="fake.ttf"),
            patch("renderers.svg_base.string_width", return_value=100.0),
            patch(
                "renderers.glyph_cache.get_font_metrics", return_value=(1000, 800, -200)
            ),
            patch.object(renderer, "_draw_text") as mock_draw_text,
        ):
            renderer._render_text_watermark(config)

        _, kwargs = mock_draw_text.call_args
        assert kwargs["transform"] is not None
        assert "scale(" in kwargs["transform"]

    def test_draw_text_applies_x_scale_when_max_width_exceeded(self):
        """_draw_text should inject an X-only scale transform when constrained."""
        import drawsvg
        from unittest.mock import patch
        from renderers.svg_base import BaseSVGRenderer

        class _Stub(BaseSVGRenderer):
            def _render_content(self, *a, **kw):
                return 0, []

        renderer = _Stub()
        renderer._page_height = 100
        renderer._page_width = 200
        renderer._drawing = drawsvg.Drawing(200, 100)

        with (
            patch("config.config.get_font_path", return_value="fake.ttf"),
            patch("renderers.svg_base.string_width", return_value=200.0),
            patch(
                "renderers.svg_base.text_to_svg_group", return_value='<g id="glyphs"/>'
            ),
        ):
            renderer._draw_text(
                10,
                20,
                "Long text",
                "Roboto-Regular",
                12,
                max_width=100.0,
            )

        svg_text = renderer._drawing.as_svg()
        assert "scale(0.500000 1)" in svg_text

    def test_render_decorations_day_name_uses_max_width(self):
        """Day-name labels should pass max_width so X scaling can be applied."""
        import drawsvg
        from unittest.mock import patch
        from renderers.svg_base import BaseSVGRenderer
        from config.config import create_calendar_config

        class _Stub(BaseSVGRenderer):
            def _render_content(self, *a, **kw):
                return 0, []

        renderer = _Stub()
        renderer._page_height = 100
        renderer._page_width = 200
        renderer._drawing = drawsvg.Drawing(200, 100)

        config = create_calendar_config()
        config.day_name_font_size = 24.0
        coordinates = {"Wednesday": (10.0, 80.0, 30.0, 10.0)}

        with patch.object(renderer, "_draw_text") as mock_draw_text:
            renderer._render_decorations(config, coordinates)

        _, kwargs = mock_draw_text.call_args
        assert kwargs["max_width"] == 30.0
        assert kwargs["anchor"] == "middle"

    def test_render_image_watermark_passes_rotation_transform(self):
        """_render_image_watermark should pass rotate(...) to raster imagemarks."""
        import drawsvg
        from unittest.mock import patch
        from renderers.svg_base import BaseSVGRenderer
        from config.config import create_calendar_config

        class _Stub(BaseSVGRenderer):
            def _render_content(self, *a, **kw):
                return 0, []

        renderer = _Stub()
        renderer._page_height = 100
        renderer._page_width = 100
        renderer._drawing = drawsvg.Drawing(100, 100)

        config = create_calendar_config()
        config.pageX = 200
        config.pageY = 100
        config.watermark_image = "/tmp/fake.png"
        config.watermark_image_width = 40
        config.watermark_image_height = 20
        config.watermark_image_rotation_angle = -12

        with (
            patch.object(renderer, "_is_svg", return_value=False),
            patch.object(renderer, "_draw_image") as mock_draw_image,
        ):
            renderer._render_image_watermark(config)

        _, kwargs = mock_draw_image.call_args
        assert kwargs["transform"] == "rotate(-12.0 100.0 50.0)"

    def _make_renderer_config(self, **overrides):
        """Create a config with computed font sizes set for renderer tests."""
        config = create_calendar_config()
        config.weekly_name_text_font_size = 9.0
        config.event_icon_font_size = 9.0
        config.day_box_number_font_size = 13.0
        config.day_box_icon_font_size = 13.0
        for k, v in overrides.items():
            setattr(config, k, v)
        return config

    def test_day_box_renderer_uses_config_stroke_values(self):
        """_draw_day_box passes config stroke_color/opacity/width/dasharray to _draw_rect."""
        import arrow
        import drawsvg
        from unittest.mock import patch
        from visualizers.weekly.renderer import WeeklyCalendarRenderer

        config = self._make_renderer_config(
            day_box_stroke_color="navy",
            day_box_stroke_opacity=0.8,
            day_box_stroke_width=3,
            day_box_stroke_dasharray="4 2",
        )

        renderer = WeeklyCalendarRenderer()
        renderer._page_height = 500
        renderer._page_width = 700
        renderer._drawing = drawsvg.Drawing(700, 500)
        renderer._pattern_svg_cache = {}
        renderer._registered_pattern_ids = set()

        oneday = arrow.Arrow(2026, 2, 24)

        with (
            patch.object(renderer, "_draw_rect") as mock_rect,
            patch.object(renderer, "_draw_text"),
            patch.object(renderer, "_draw_fiscal_label", return_value=0),
            patch.object(renderer, "_draw_week_number_label"),
            patch.object(renderer, "_draw_special_day_title"),
            patch("visualizers.weekly.renderer.string_width", return_value=10),
        ):
            renderer._draw_day_box(config, oneday, 10, 10, 80, 60, False, "", False)

        mock_rect.assert_called_once()
        _, kwargs = mock_rect.call_args
        assert kwargs["stroke"] == "navy"
        assert kwargs["stroke_opacity"] == 0.8
        assert kwargs["stroke_width"] == 3
        assert kwargs["stroke_dasharray"] == "4 2"

    def test_day_box_renderer_uses_config_stroke_defaults(self):
        """Default config stroke values propagate to _draw_rect."""
        import arrow
        import drawsvg
        from unittest.mock import patch
        from visualizers.weekly.renderer import WeeklyCalendarRenderer

        config = self._make_renderer_config()

        renderer = WeeklyCalendarRenderer()
        renderer._page_height = 500
        renderer._page_width = 700
        renderer._drawing = drawsvg.Drawing(700, 500)
        renderer._pattern_svg_cache = {}
        renderer._registered_pattern_ids = set()

        oneday = arrow.Arrow(2026, 2, 24)

        with (
            patch.object(renderer, "_draw_rect") as mock_rect,
            patch.object(renderer, "_draw_text"),
            patch.object(renderer, "_draw_fiscal_label", return_value=0),
            patch.object(renderer, "_draw_week_number_label"),
            patch.object(renderer, "_draw_special_day_title"),
            patch("visualizers.weekly.renderer.string_width", return_value=10),
        ):
            renderer._draw_day_box(config, oneday, 10, 10, 80, 60, False, "", False)

        _, kwargs = mock_rect.call_args
        assert kwargs["stroke"] == config.day_box_stroke_color  # "grey"
        assert kwargs["stroke_opacity"] == config.day_box_stroke_opacity  # 0.25
        assert kwargs["stroke_width"] == config.day_box_stroke_width  # 2
        assert kwargs["stroke_dasharray"] is None


class TestStrokeDasharrayTimelineMini:
    """Tests for stroke-dasharray support in timeline and mini visualizers."""

    def _apply_theme_data(self, theme_data: dict) -> CalendarConfig:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(theme_data, f)
            f.flush()
            engine = ThemeEngine()
            engine.load(f.name)
            config = create_calendar_config()
            engine.apply(config)
        return config

    # ── Timeline theme mappings ──────────────────────────────────────────────

    def test_timeline_axis_stroke_dasharray_applied(self):
        config = self._apply_theme_data(
            {
                "theme": {"name": "T"},
                "timeline": {"axis_stroke_dasharray": "8,4"},
            }
        )
        assert config.timeline_axis_stroke_dasharray == "8,4"

    def test_timeline_tick_stroke_dasharray_applied(self):
        config = self._apply_theme_data(
            {
                "theme": {"name": "T"},
                "timeline": {"tick_stroke_dasharray": "3,3"},
            }
        )
        assert config.timeline_tick_stroke_dasharray == "3,3"

    def test_timeline_today_line_stroke_dasharray_applied(self):
        config = self._apply_theme_data(
            {
                "theme": {"name": "T"},
                "timeline": {"today_line_stroke_dasharray": "6,2"},
            }
        )
        assert config.timeline_today_line_stroke_dasharray == "6,2"

    def test_timeline_label_stroke_dasharray_applied(self):
        config = self._apply_theme_data(
            {
                "theme": {"name": "T"},
                "timeline": {"label_stroke_dasharray": "2,4"},
            }
        )
        assert config.timeline_label_stroke_dasharray == "2,4"

    def test_timeline_duration_bar_stroke_dasharray_applied(self):
        config = self._apply_theme_data(
            {
                "theme": {"name": "T"},
                "timeline": {"duration_bar_stroke_dasharray": "5,5"},
            }
        )
        assert config.timeline_duration_bar_stroke_dasharray == "5,5"

    # ── Mini theme mappings ──────────────────────────────────────────────────

    def test_mini_grid_line_stroke_dasharray_applied(self):
        config = self._apply_theme_data(
            {
                "theme": {"name": "T"},
                "mini_calendar": {"grid_line_stroke_dasharray": "1,2"},
            }
        )
        assert config.mini_grid_line_stroke_dasharray == "1,2"

    def test_mini_grid_line_stroke_style_applied(self):
        config = self._apply_theme_data(
            {
                "theme": {"name": "T"},
                "mini_calendar": {
                    "grid_line_stroke_color": "orange",
                    "grid_line_stroke_width": 0.5,
                    "grid_line_stroke_opacity": 0.3,
                },
            }
        )
        assert config.mini_grid_line_stroke_color == "orange"
        assert config.mini_grid_line_stroke_width == 0.5
        assert config.mini_grid_line_stroke_opacity == 0.3

    def test_mini_day_number_digits_applied(self):
        config = self._apply_theme_data(
            {
                "theme": {"name": "Mini"},
                "mini_calendar": {
                    "day_number_digits": [
                        "a",
                        "b",
                        "c",
                        "d",
                        "e",
                        "f",
                        "g",
                        "h",
                        "i",
                        "j",
                    ]
                },
            }
        )
        assert config.mini_day_number_digits == [
            "a",
            "b",
            "c",
            "d",
            "e",
            "f",
            "g",
            "h",
            "i",
            "j",
        ]

    def test_mini_day_number_glyphs_applied(self):
        glyphs = [f"G{i}" for i in range(1, 32)]
        config = self._apply_theme_data(
            {
                "theme": {"name": "Mini"},
                "mini_calendar": {"day_number_glyphs": glyphs},
            }
        )
        assert config.mini_day_number_glyphs == glyphs

    def test_mini_show_adjacent_applied(self):
        config = self._apply_theme_data(
            {
                "theme": {"name": "Mini"},
                "mini_calendar": {"show_adjacent": False},
            }
        )
        assert config.mini_show_adjacent is False

    def test_mini_milestone_circle_config_applied(self):
        config = self._apply_theme_data(
            {
                "theme": {"name": "Mini"},
                "mini_calendar": {
                    "circle_milestones": False,
                    "milestone_stroke_color": "gold",
                    "milestone_stroke_width": 2.5,
                    "milestone_stroke_opacity": 0.4,
                },
            }
        )
        assert config.mini_circle_milestones is False
        assert config.mini_milestone_stroke_color == "gold"
        assert config.mini_milestone_stroke_width == 2.5
        assert config.mini_milestone_stroke_opacity == 0.4

    def test_mini_day_box_hash_rules_applied_from_theme(self):
        rules = [
            {
                "pattern": "brick-wall",
                "color": "gold",
                "when": {"milestone": True},
            }
        ]
        config = self._apply_theme_data(
            {
                "theme": {"name": "MiniHash"},
                "mini_calendar": {"day_box": {"hash_rules": rules}},
            }
        )
        assert config.theme_mini_day_box_hash_rules == rules

    # ── Defaults are None ────────────────────────────────────────────────────

    def test_timeline_dasharray_fields_default_to_none(self):
        config = create_calendar_config()
        assert config.timeline_axis_stroke_dasharray is None
        assert config.timeline_tick_stroke_dasharray is None
        assert config.timeline_today_line_stroke_dasharray is None
        assert config.timeline_label_stroke_dasharray is None
        assert config.timeline_duration_bar_stroke_dasharray is None

    def test_mini_dasharray_fields_default_to_none(self):
        config = create_calendar_config()
        assert config.mini_grid_line_stroke_dasharray is None
        assert config.mini_grid_line_stroke_color == "lightgrey"
        assert config.mini_grid_line_stroke_width == 0.25
        assert config.mini_grid_line_stroke_opacity == 0.5
        assert config.mini_day_number_glyphs is None
        assert config.mini_day_number_digits is None
        assert config.mini_show_adjacent is True
        assert config.mini_circle_milestones is True
        assert config.mini_milestone_stroke_width == 1.0
        assert config.mini_milestone_stroke_opacity == 1.0
        assert config.theme_mini_day_box_hash_rules is None

    # ── SVG output integration ───────────────────────────────────────────────

    def test_timeline_svg_contains_axis_dasharray(self):
        """Axis stroke-dasharray should appear in generated timeline SVG."""
        from visualizers.timeline.renderer import TimelineRenderer
        from shared.db_access import CalendarDB
        import tempfile, os

        config = create_calendar_config()
        config.start = "20260101"
        config.end = "20260131"
        config.adjustedstart = "20260101"
        config.adjustedend = "20260131"
        config.timeline_axis_stroke_dasharray = "6,3"
        with tempfile.NamedTemporaryFile(suffix=".svg", delete=False) as f:
            config.outputfile = f.name
        try:
            renderer = TimelineRenderer()
            renderer._page_height = config.pageY
            renderer._page_width = config.pageX
            import drawsvg

            renderer._drawing = drawsvg.Drawing(config.pageX, config.pageY)
            renderer._draw_line(
                0,
                50,
                100,
                50,
                stroke=config.timeline_axis_color,
                stroke_dasharray=config.timeline_axis_stroke_dasharray,
            )
            svg_text = renderer._drawing.as_svg()
            assert "stroke-dasharray" in svg_text
            assert "6,3" in svg_text
        finally:
            os.unlink(config.outputfile)

    def test_mini_grid_line_svg_contains_dasharray(self):
        """Mini grid line stroke-dasharray should appear in generated SVG."""
        import drawsvg
        from renderers.svg_base import BaseSVGRenderer

        class _Stub(BaseSVGRenderer):
            def _render_content(self, *a, **kw):
                return 0, []

        renderer = _Stub()
        renderer._page_height = 100
        renderer._page_width = 100
        renderer._drawing = drawsvg.Drawing(100, 100)
        renderer._draw_rect(
            5,
            5,
            20,
            20,
            fill="none",
            stroke="lightgrey",
            stroke_width=0.25,
            stroke_opacity=0.5,
            stroke_dasharray="1,2",
        )
        svg_text = renderer._drawing.as_svg()
        assert "stroke-dasharray" in svg_text
        assert "1,2" in svg_text


def test_blockplan_theme_applied():
    theme_data = {
        "theme": {"name": "BlockplanTheme"},
        "blockplan": {
            "grid_color": "silver",
            "grid_opacity": 0.75,
            "lane_match_mode": "all",
            "show_unmatched_lane": False,
            "vertical_line_color": "orange",
            "vertical_line_width": 2.5,
            "vertical_line_dasharray": "4,2",
            "vertical_line_opacity": 0.6,
            "vertical_lines": [{"band": "Date", "value": "20260205"}],
            "header_font": "Roboto-Bold",
            "header_label_align_h": "right",
            "name_text": {"font_color": "tomato"},
            "event_show_date": True,
            "event_date_font": "Roboto-Bold",
            "event_date_font_size": 11.0,
            "event_date_color": "purple",
            "event_date_format": "MMM D",
            "timeband_fill_palette": ["#111111", "#222222"],
            "swimlanes": [{"name": "Infra", "match": {"resource_groups": ["ops"]}}],
            "top_time_bands": [
                {"label": "PI", "unit": "interval", "interval_days": 70}
            ],
        },
    }
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(theme_data, f)
        f.flush()
        engine = ThemeEngine()
        engine.load(f.name)
        config = create_calendar_config()
        engine.apply(config)

    assert config.blockplan_grid_color == "silver"
    assert config.blockplan_grid_opacity == 0.75
    assert config.blockplan_lane_match_mode == "all"
    assert config.blockplan_show_unmatched_lane is False
    assert config.blockplan_vertical_line_color == "orange"
    assert config.blockplan_vertical_line_width == 2.5
    assert config.blockplan_vertical_line_dasharray == "4,2"
    assert config.blockplan_vertical_line_opacity == 0.6
    assert config.blockplan_vertical_lines == [{"band": "Date", "value": "20260205"}]
    assert config.blockplan_header_font == "Roboto-Bold"
    assert config.blockplan_header_label_align_h == "right"
    assert config.blockplan_name_text_font_color == "tomato"
    assert config.blockplan_event_show_date is True
    assert config.blockplan_event_date_font == "Roboto-Bold"
    assert config.blockplan_event_date_font_size == 11.0
    assert config.blockplan_event_date_color == "purple"
    assert config.blockplan_event_date_format == "MMM D"
    assert config.blockplan_timeband_fill_palette == ["#111111", "#222222"]
    assert config.blockplan_swimlanes == [
        {"name": "Infra", "match": {"resource_groups": ["ops"]}}
    ]
    assert config.blockplan_top_time_bands == [
        {"label": "PI", "unit": "interval", "interval_days": 70}
    ]


class TestThemeEngineValidation:
    """Tests for theme validation."""

    def test_unknown_sections_logged(self, caplog):
        """Unknown sections should produce a warning."""
        theme_data = {
            "theme": {"name": "Test"},
            "unknown_section": {"foo": "bar"},
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(theme_data, f)
            f.flush()
            engine = ThemeEngine()
            with caplog.at_level("WARNING"):
                engine.load(f.name)
            assert "unknown sections" in caplog.text.lower()

    def test_invalid_font_name_logged(self, caplog):
        """Unregistered font names should produce a warning."""
        theme_data = {
            "theme": {"name": "Test"},
            "weekly": {"name_text": {"font_name": "NonexistentFont-Bold"}},
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(theme_data, f)
            f.flush()
            engine = ThemeEngine()
            with caplog.at_level("WARNING"):
                engine.load(f.name)
            assert "NonexistentFont-Bold" in caplog.text
