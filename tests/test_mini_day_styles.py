from config.config import create_calendar_config, setfontsizes
from visualizers.mini.day_styles import DayStyleResolver, DayStyle
from visualizers.mini.renderer import MiniCalendarRenderer


class _StubDB:
    def __init__(self, holidays=None, special_days=None):
        self._holidays = holidays or []
        self._special_days = special_days or []

    def get_holidays_for_date(self, daykey, country=None):
        return list(self._holidays)

    def get_special_days_for_date(self, daykey):
        return list(self._special_days)

    def get_all_patterns(self):
        return {
            "brick-wall": '<svg viewBox="0 0 10 10"><rect width="10" height="10" fill="black"/></svg>'
        }


def _config():
    config = create_calendar_config()
    config.pageX, config.pageY = 792.0, 1224.0
    return setfontsizes(config)


def test_mini_circle_milestones_can_be_disabled():
    config = _config()
    config.mini_circle_milestones = False
    style = DayStyleResolver(config, _StubDB()).resolve(
        "20260115",
        [{"Start": "20260115", "End": "20260115", "Milestone": True}],
    )

    assert style.circled is False


def test_mini_style_rules_apply_pattern_decoration():
    config = _config()
    config.theme_style_rules = [
        {
            "name": "milestone-pattern",
            "select": {"milestone": True, "notes": ["launch"]},
            "apply_to": "day_box",
            "style": {
                "pattern": "brick-wall",
                "pattern_color": "gold",
                "pattern_opacity": 0.25,
            },
        }
    ]
    style = DayStyleResolver(config, _StubDB()).resolve(
        "20260115",
        [
            {
                "Start": "20260115",
                "End": "20260115",
                "Task": "Release",
                "Milestone": True,
                "Notes": "Launch prep",
                "Resource_Group": "ENG",
            }
        ],
    )

    assert len(style.hash_decorations) == 1
    assert style.hash_decorations[0].pattern == "brick-wall"
    assert style.hash_decorations[0].color == "gold"
    assert style.hash_decorations[0].opacity == 0.25


def test_mini_circle_stroke_style_is_configurable():
    config = _config()
    config.mini_milestone_stroke_width = 2.5
    config.mini_milestone_stroke_opacity = 0.35

    class _CaptureRenderer(MiniCalendarRenderer):
        def __init__(self):
            super().__init__()
            self.circle_calls = []

        def _draw_circle(self, *args, **kwargs):
            self.circle_calls.append(kwargs)

        def _draw_rect(self, *args, **kwargs):
            return None

        def _draw_text(self, *args, **kwargs):
            return None

        def _draw_icon_svg(self, *args, **kwargs):
            return None

        def _resolve_icon_svg(self, icon_name):
            return None

    renderer = _CaptureRenderer()
    style = DayStyleResolver(config, _StubDB()).resolve(
        "20260115",
        [{"Start": "20260115", "End": "20260115", "Milestone": True}],
    )
    renderer._draw_day_cell(config, 0, 0, 20, 20, 15, style)

    assert renderer.circle_calls
    assert renderer.circle_calls[0]["stroke_width"] == 2.5
    assert renderer.circle_calls[0]["stroke_opacity"] == 0.35


def test_mini_icons_are_centered_vertically():
    config = _config()

    class _CaptureRenderer(MiniCalendarRenderer):
        def __init__(self):
            super().__init__()
            self.icon_calls = []

        def _draw_rect(self, *args, **kwargs):
            return None

        def _draw_text(self, *args, **kwargs):
            return None

        def _draw_line(self, *args, **kwargs):
            return None

        def _draw_icon_svg(self, icon_name, x, baseline_y, size, **kwargs):
            self.icon_calls.append(
                {
                    "icon_name": icon_name,
                    "x": x,
                    "baseline_y": baseline_y,
                    "size": size,
                    **kwargs,
                }
            )
            return True

        def _resolve_icon_svg(self, icon_name):
            return "<svg viewBox='0 0 24 24'></svg>" if icon_name else None

    renderer = _CaptureRenderer()
    cy = 10.0

    replace_style = DayStyle(icon_replace="star")
    renderer._draw_day_cell(config, 0, 0, 20, 20, 15, replace_style)
    replace_call = renderer.icon_calls[0]
    assert replace_call["anchor"] == "middle"
    assert replace_call["baseline_y"] == cy + (replace_call["size"] * 0.30)

    append_style = DayStyle(icon_append="star")
    renderer._draw_day_cell(config, 0, 0, 20, 20, 15, append_style)
    append_call = renderer.icon_calls[1]
    assert append_call["anchor"] == "middle"
    assert append_call["baseline_y"] == cy + (append_call["size"] * 0.30)


def test_mini_event_icon_replaces_day_number():
    config = _config()

    class _CaptureRenderer(MiniCalendarRenderer):
        def __init__(self):
            super().__init__()
            self.text_calls = []
            self.icon_calls = []

        def _draw_rect(self, *args, **kwargs):
            return None

        def _draw_line(self, *args, **kwargs):
            return None

        def _draw_text(self, x, y, text, font_name, font_size, **kwargs):
            self.text_calls.append(text)

        def _draw_icon_svg(self, icon_name, x, baseline_y, size, **kwargs):
            self.icon_calls.append(icon_name)
            return True

        def _resolve_icon_svg(self, icon_name):
            return "<svg viewBox='0 0 24 24'></svg>" if icon_name else None

    style = DayStyleResolver(config, _StubDB()).resolve(
        "20260115",
        [{"Start": "20260115", "End": "20260115", "Icon": "star"}],
    )
    renderer = _CaptureRenderer()
    renderer._draw_day_cell(config, 0, 0, 20, 20, 15, style)

    assert renderer.icon_calls == ["star"]
    assert renderer.text_calls == []


def test_mini_grid_lines_are_inset_to_avoid_bottom_clip():
    config = _config()
    config.mini_grid_lines = True
    config.mini_grid_line_color = "orange"
    config.mini_grid_line_width = 0.5
    config.mini_grid_line_opacity = 0.3

    class _CaptureRenderer(MiniCalendarRenderer):
        def __init__(self):
            super().__init__()
            self.rect_calls = []

        def _draw_rect(self, x, y, w, h, **kwargs):
            self.rect_calls.append({"x": x, "y": y, "w": w, "h": h, **kwargs})

        def _draw_text(self, *args, **kwargs):
            return None

        def _draw_icon_svg(self, *args, **kwargs):
            return None

        def _resolve_icon_svg(self, icon_name):
            return None

    renderer = _CaptureRenderer()
    renderer._draw_day_cell(config, 0, 0, 20, 20, 15, DayStyle())

    grid_rects = [r for r in renderer.rect_calls if r.get("stroke") == "orange"]
    assert len(grid_rects) == 1
    grid = grid_rects[0]
    assert grid["x"] == 0.25
    assert grid["y"] == 0.25
    assert grid["w"] == 19.5
    assert grid["h"] == 19.5
    assert grid["stroke_width"] == 0.5
    assert grid["stroke_opacity"] == 0.3


def test_mini_day_number_digits_are_substituted():
    config = _config()
    config.mini_day_number_digits = ["a", "b", "c", "d", "e", "f", "g", "h", "i", "j"]

    class _CaptureRenderer(MiniCalendarRenderer):
        def __init__(self):
            super().__init__()
            self.text_calls = []

        def _draw_rect(self, *args, **kwargs):
            return None

        def _draw_text(self, x, y, text, font_name, font_size, **kwargs):
            self.text_calls.append(text)

        def _draw_icon_svg(self, *args, **kwargs):
            return None

        def _resolve_icon_svg(self, icon_name):
            return None

    renderer = _CaptureRenderer()
    renderer._draw_day_cell(config, 0, 0, 20, 20, 12, DayStyle())

    assert renderer.text_calls == ["bc"]


def test_mini_day_number_digits_invalid_length_falls_back_to_ascii():
    config = _config()
    config.mini_day_number_digits = ["①", "②", "③"]

    class _CaptureRenderer(MiniCalendarRenderer):
        def __init__(self):
            super().__init__()
            self.text_calls = []

        def _draw_rect(self, *args, **kwargs):
            return None

        def _draw_text(self, x, y, text, font_name, font_size, **kwargs):
            self.text_calls.append(text)

        def _draw_icon_svg(self, *args, **kwargs):
            return None

        def _resolve_icon_svg(self, icon_name):
            return None

    renderer = _CaptureRenderer()
    renderer._draw_day_cell(config, 0, 0, 20, 20, 12, DayStyle())

    assert renderer.text_calls == ["12"]


def test_mini_day_number_glyphs_are_supported():
    config = _config()
    config.mini_day_number_glyphs = [f"G{i}" for i in range(1, 32)]

    class _CaptureRenderer(MiniCalendarRenderer):
        def __init__(self):
            super().__init__()
            self.text_calls = []

        def _draw_rect(self, *args, **kwargs):
            return None

        def _draw_text(self, x, y, text, font_name, font_size, **kwargs):
            self.text_calls.append(text)

        def _draw_icon_svg(self, *args, **kwargs):
            return None

        def _resolve_icon_svg(self, icon_name):
            return None

    renderer = _CaptureRenderer()
    renderer._draw_day_cell(config, 0, 0, 20, 20, 12, DayStyle())

    assert renderer.text_calls == ["G12"]


def test_mini_day_number_glyphs_take_precedence_over_digits():
    config = _config()
    config.mini_day_number_glyphs = [f"G{i}" for i in range(1, 32)]
    config.mini_day_number_digits = ["a", "b", "c", "d", "e", "f", "g", "h", "i", "j"]

    class _CaptureRenderer(MiniCalendarRenderer):
        def __init__(self):
            super().__init__()
            self.text_calls = []

        def _draw_rect(self, *args, **kwargs):
            return None

        def _draw_text(self, x, y, text, font_name, font_size, **kwargs):
            self.text_calls.append(text)

        def _draw_icon_svg(self, *args, **kwargs):
            return None

        def _resolve_icon_svg(self, icon_name):
            return None

    renderer = _CaptureRenderer()
    renderer._draw_day_cell(config, 0, 0, 20, 20, 12, DayStyle())

    assert renderer.text_calls == ["G12"]
