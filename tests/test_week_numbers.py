import arrow

from config.config import create_calendar_config, setfontsizes
from shared.fiscal_calendars import FiscalPeriodInfo
from visualizers.weekly.renderer import WeeklyCalendarRenderer
from visualizers.mini.renderer import MiniCalendarRenderer


class _CaptureRenderer(WeeklyCalendarRenderer):
    def __init__(self):
        super().__init__()
        self.text_calls = []
        self.text_detail_calls = []

    def _draw_text(self, x, y, text, font_name, font_size, **kwargs):
        self.text_calls.append(text)
        self.text_detail_calls.append(
            {
                "x": x,
                "y": y,
                "text": text,
                "font_name": font_name,
                "font_size": font_size,
                **kwargs,
            }
        )

    def _draw_rect(self, *args, **kwargs):
        pass

    def _draw_hash_lines(self, *args, **kwargs):
        pass


class _MiniDetailsRenderer(MiniCalendarRenderer):
    def __init__(self):
        super().__init__()
        self.text_calls = []
        self.saved_paths = []

    def _create_drawing(self, config):
        class _StubDrawing:
            def __init__(self, owner):
                self._owner = owner

            def append(self, _):
                return None

            def append_title(self, _):
                return None

            def save_svg(self, path):
                self._owner.saved_paths.append(path)

        return _StubDrawing(self)

    def _add_desc(self, config):
        return None

    def _render_decorations(self, config, coordinates):
        return None

    def _draw_text(self, x, y, text, font_name, font_size, **kwargs):
        self.text_calls.append(text)

    def _draw_line(self, *args, **kwargs):
        return None


def _base_config():
    config = create_calendar_config()
    config.pageX, config.pageY = 792.0, 1224.0
    config = setfontsizes(config)
    config.include_week_numbers = True
    config.week_number_mode = "iso"
    return config


def test_week_number_drawn_on_week_start_sunday():
    config = _base_config()
    config.weekend_style = 1  # Sunday start
    renderer = _CaptureRenderer()

    oneday = arrow.get("20250105", "YYYYMMDD")  # Sunday
    renderer._draw_day_box(
        config,
        oneday,
        X=0,
        Y=0,
        W=100,
        H=100,
        daytitle=False,
        dayicon="",
        shadespecialday=False,
    )

    assert any(text.startswith("W") for text in renderer.text_calls)


def test_week_number_not_drawn_on_non_start_day():
    config = _base_config()
    config.weekend_style = 1  # Sunday start
    renderer = _CaptureRenderer()

    oneday = arrow.get("20250107", "YYYYMMDD")  # Tuesday
    renderer._draw_day_box(
        config,
        oneday,
        X=0,
        Y=0,
        W=100,
        H=100,
        daytitle=False,
        dayicon="",
        shadespecialday=False,
    )

    assert not any(text.startswith("W") for text in renderer.text_calls)


def test_week_number_drawn_in_left_margin_when_present():
    config = _base_config()
    config.weekend_style = 1  # Sunday start
    config.include_margin = True
    config.margin_left = 20.0
    renderer = _CaptureRenderer()

    oneday = arrow.get("20250105", "YYYYMMDD")  # Sunday
    renderer._draw_day_box(
        config,
        oneday,
        X=100,
        Y=0,
        W=100,
        H=100,
        daytitle=False,
        dayicon="",
        shadespecialday=False,
    )

    week_calls = [
        c for c in renderer.text_detail_calls if str(c.get("text", "")).startswith("W")
    ]
    assert week_calls
    week = week_calls[0]
    assert week["x"] == 98.0
    assert week.get("anchor") == "end"


def test_week_number_formatting_applied():
    config = _base_config()
    config.weekend_style = 1  # Sunday start
    config.week_number_label_format = "WK{num}"
    renderer = _CaptureRenderer()

    oneday = arrow.get("20250105", "YYYYMMDD")  # Sunday
    renderer._draw_day_box(
        config,
        oneday,
        X=0,
        Y=0,
        W=100,
        H=100,
        daytitle=False,
        dayicon="",
        shadespecialday=False,
    )

    assert "WK1" in renderer.text_calls


def test_fiscal_label_formatting_applied():
    config = _base_config()
    config.weekend_style = 1
    config.fiscal_show_period_labels = True
    config.fiscal_show_quarter_labels = True
    config.fiscal_period_label_format = "{year_label}{quarter_label}{period_short}"

    info = FiscalPeriodInfo(
        fiscal_year=2025,
        fiscal_quarter=1,
        fiscal_period=1,
        fiscal_week=1,
        period_name="Period 1",
        period_short_name="P1",
        is_period_start=True,
        is_quarter_start=True,
        is_fiscal_year_start=True,
    )
    config.fiscal_lookup = {"20250105": info}

    renderer = _CaptureRenderer()
    oneday = arrow.get("20250105", "YYYYMMDD")
    renderer._draw_day_box(
        config,
        oneday,
        X=0,
        Y=0,
        W=100,
        H=100,
        daytitle=False,
        dayicon="",
        shadespecialday=False,
    )

    assert "FY25Q1P1" in "".join(renderer.text_calls)


def test_mini_week_number_formatting_applied():
    config = _base_config()
    config.mini_week_number_label_format = "WN{num}"

    renderer = _CaptureRenderer()
    mini = MiniCalendarRenderer()
    mini._draw_text = renderer._draw_text  # capture
    mini._draw_week_number(config, x=0, y=0, w=10, h=10, wn_value=7)

    assert "WN7" in renderer.text_calls


def test_fiscal_period_end_label_applied():
    config = _base_config()
    config.weekend_style = 1
    config.fiscal_show_period_labels = True
    config.fiscal_period_end_label_format = "END{period_short}"

    info_p1 = FiscalPeriodInfo(
        fiscal_year=2025,
        fiscal_quarter=1,
        fiscal_period=1,
        fiscal_week=1,
        period_name="Period 1",
        period_short_name="P1",
        is_period_start=False,
        is_quarter_start=False,
        is_fiscal_year_start=False,
    )
    info_p2 = FiscalPeriodInfo(
        fiscal_year=2025,
        fiscal_quarter=1,
        fiscal_period=2,
        fiscal_week=2,
        period_name="Period 2",
        period_short_name="P2",
        is_period_start=True,
        is_quarter_start=False,
        is_fiscal_year_start=False,
    )
    config.fiscal_lookup = {
        "20250111": info_p1,
        "20250112": info_p2,
    }

    renderer = _CaptureRenderer()
    oneday = arrow.get("20250111", "YYYYMMDD")
    renderer._draw_day_box(
        config,
        oneday,
        X=0,
        Y=0,
        W=100,
        H=100,
        daytitle=False,
        dayicon="",
        shadespecialday=False,
    )

    assert "ENDP1" in renderer.text_calls


def test_mini_details_svg_generated():
    config = _base_config()
    config.include_mini_details = True
    config.outputfile = "mini.svg"

    renderer = _MiniDetailsRenderer()
    renderer._render_details_svg(
        config,
        coordinates={},
        events=[
            {
                "Start": "20260101",
                "End": "20260103",
                "Task_Name": "Task A",
                "Milestone": False,
                "Priority": 1,
                "Resource_Group": "B",
                "Notes": "Note",
            }
        ],
    )

    assert any("Event Details" in text for text in renderer.text_calls)
    assert renderer.saved_paths and renderer.saved_paths[0].endswith("_details.svg")
