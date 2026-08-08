"""Gantt chart marks: bars, progress, float, brackets, milestones, today line.

Drawing is captured rather than rasterized: each test asserts on the
primitives the renderer emitted, keyed by their `ec-*` class.
"""

from __future__ import annotations

import pytest

from config.config import create_calendar_config, setfontsizes
from visualizers.gantt.details import (
    KIND_CLIPPED_END,
    KIND_CLIPPED_START,
    KIND_HIDDEN_HOLIDAY,
    KIND_SNAPPED_EVENT,
    KIND_UNDRAWN,
)
from visualizers.gantt.layout import GanttLayout
from visualizers.gantt.renderer import GanttRenderer


class _DummyDB:
    """The minimum surface classify_day and the icon cache need."""

    holidays: set[str] = set()

    @staticmethod
    def get_palette(name):
        return None

    @staticmethod
    def get_icon_svg_map():
        return {
            name: '<svg viewBox="0 0 24 24"><path d="M2 2h20v20H2z"/></svg>'
            for name in (
                "diamond-fill", "square-fill", "check",
                "arrow-left-circle", "arrow-bar-left", "arrow-bar-right",
                "crosssquare",
            )
        }

    @classmethod
    def is_government_nonworkday(cls, daykey, country=None):
        return daykey in cls.holidays

    @staticmethod
    def get_special_days_for_date(daykey):
        return []


class _CaptureRenderer(GanttRenderer):
    """Records primitives instead of drawing them."""

    def __init__(self):
        super().__init__()
        self.rects: list[dict] = []
        self.lines: list[dict] = []
        self.polylines: list[dict] = []
        self.icons: list[dict] = []
        self.texts: list[dict] = []

    def _draw_rect(self, x, y, w, h, **kwargs):
        self.rects.append({"x": x, "y": y, "w": w, "h": h, **kwargs})

    def _draw_line(self, x1, y1, x2, y2, **kwargs):
        self.lines.append({"x1": x1, "y1": y1, "x2": x2, "y2": y2, **kwargs})

    def _draw_lines(self, segments, **kwargs):
        self.polylines.append({"segments": list(segments), **kwargs})

    def _draw_text(self, x, y, text, font_name, font_size, **kwargs):
        self.texts.append({"x": x, "y": y, "text": str(text), **kwargs})

    def _draw_icon_svg(self, icon_name, x, baseline_y, size, **kwargs):
        self.icons.append(
            {"icon": icon_name, "x": x, "y": baseline_y, "size": size, **kwargs}
        )
        return True

    def _load_icon_svg_cache(self, db):
        pass

    # Convenience accessors -------------------------------------------------

    def of_class(self, collection, css_class):
        return [item for item in collection if item.get("css_class") == css_class]


def render(events, *, start="20260202", end="20260213", weekend_style=0, db=None,
           **config_overrides):
    """Render *events* over a short range; return the capturing renderer."""
    config = create_calendar_config()
    config.pageX, config.pageY = 1000.0, 400.0
    config.papersize = "Letter"
    config.weekend_style = weekend_style
    config.userstart, config.userend = start, end
    config.adjustedstart, config.adjustedend = start, end
    config.include_header = False
    config.include_footer = False
    config.gantt_show_today_line = False
    for key, value in config_overrides.items():
        setattr(config, key, value)
    config = setfontsizes(config)

    renderer = _CaptureRenderer()
    coords = GanttLayout().calculate(config)
    renderer._render_content(config, coords, events, db or _DummyDB())
    # Expected geometry is derived from the layout, never re-derived from
    # page size — margins are not zero.
    renderer.chart_x, _y, renderer.chart_w, _h = coords["GanttChartBody"]
    renderer.table_x = coords["GanttTableBody"][0]
    renderer.day_w = renderer.chart_w / 10
    return renderer


def task(**overrides) -> dict:
    """One events-table row, in the PascalCase shape the DB returns."""
    row = {
        "Task_Name": "Task", "Start": "20260203", "End": "20260205",
        "WBS": "1", "Status": "active", "Percent_Complete": 0.0,
        "Rollup": 0, "Milestone": 0,
    }
    row.update(overrides)
    return row


# ── Duration bars ─────────────────────────────────────────────────────────


def test_a_task_draws_one_duration_bar():
    renderer = render([task()])
    bars = renderer.of_class(renderer.rects, "ec-duration-bar")
    assert len(bars) == 1
    assert bars[0]["w"] > 0


def test_the_bar_spans_working_columns_only():
    """Mon-Mon is 6 working columns of the 10 in this range."""
    renderer = render([task(Start="20260202", End="20260209")])
    bar = renderer.of_class(renderer.rects, "ec-duration-bar")[0]
    assert bar["w"] == pytest.approx(renderer.day_w * 6)


def test_a_single_day_event_is_one_column_wide():
    renderer = render([task(Start="20260203", End="20260203")])
    bar = renderer.of_class(renderer.rects, "ec-duration-bar")[0]
    assert bar["w"] == pytest.approx(renderer.day_w)


def test_the_event_color_wins_over_the_theme_default():
    renderer = render([task(Color="rebeccapurple")])
    assert renderer.of_class(renderer.rects, "ec-duration-bar")[0]["fill"] == (
        "rebeccapurple"
    )


def test_a_style_rule_wins_over_the_event_color():
    """style_rules govern bar appearance (requirement §38)."""
    rule = {
        "apply_to": "box:duration",
        "select": {"resource_group": "Delivery"},
        "style": {"fill": "crimson", "fill_opacity": 0.5},
    }
    renderer = render(
        [task(Color="rebeccapurple", Resource_Group="Delivery")],
        theme_style_rules=[rule],
    )
    bar = renderer.of_class(renderer.rects, "ec-duration-bar")[0]
    assert bar["fill"] == "crimson"
    assert bar["fill_opacity"] == pytest.approx(0.5)


def test_a_style_rule_that_does_not_match_leaves_the_bar_alone():
    rule = {
        "apply_to": "box:duration",
        "select": {"resource_group": "Engineering"},
        "style": {"fill": "crimson"},
    }
    renderer = render(
        [task(Color="rebeccapurple", Resource_Group="Delivery")],
        theme_style_rules=[rule],
    )
    assert renderer.of_class(renderer.rects, "ec-duration-bar")[0]["fill"] == (
        "rebeccapurple"
    )


# ── Progress ──────────────────────────────────────────────────────────────


def test_percent_complete_draws_a_proportional_line():
    renderer = render([task(Percent_Complete=0.5)])
    bar = renderer.of_class(renderer.rects, "ec-duration-bar")[0]
    line = renderer.of_class(renderer.lines, "ec-progress-line")[0]
    assert line["x2"] - line["x1"] == pytest.approx(bar["w"] / 2)


def test_full_completion_reaches_the_end_of_the_bar():
    renderer = render([task(Percent_Complete=1.0)])
    bar = renderer.of_class(renderer.rects, "ec-duration-bar")[0]
    line = renderer.of_class(renderer.lines, "ec-progress-line")[0]
    assert line["x2"] == pytest.approx(bar["x"] + bar["w"])


def test_no_progress_line_at_zero_percent():
    renderer = render([task(Percent_Complete=0.0)])
    assert renderer.of_class(renderer.lines, "ec-progress-line") == []


def test_progress_defaults_to_black():
    renderer = render([task(Percent_Complete=0.5)])
    assert renderer.of_class(renderer.lines, "ec-progress-line")[0]["stroke"] == "black"


# ── Float windows ─────────────────────────────────────────────────────────


def test_float_dates_draw_bars_at_reduced_opacity():
    renderer = render([
        task(
            Start="20260204", End="20260206",
            Earliest_Start_Date="20260202", Latest_End_Date="20260210",
        )
    ])
    floats = renderer.of_class(renderer.rects, "ec-float-bar")
    assert len(floats) == 2
    assert all(f["fill_opacity"] < 1.0 for f in floats)


def test_no_float_bars_without_float_dates():
    renderer = render([task()])
    assert renderer.of_class(renderer.rects, "ec-float-bar") == []


# ── Rollups and milestones ────────────────────────────────────────────────


def test_a_rollup_draws_a_bracket_and_no_bar():
    renderer = render([task(Rollup=1, Percent_Complete=0.5)])
    assert renderer.of_class(renderer.rects, "ec-duration-bar") == []
    assert len(renderer.of_class(renderer.polylines, "ec-rollup-bracket")) == 1


def test_the_bracket_faces_downward_at_both_ends():
    renderer = render([task(Rollup=1)])
    segments = renderer.of_class(renderer.polylines, "ec-rollup-bracket")[0]["segments"]
    left, top, right = segments
    assert left[0] == left[2]          # vertical at the start
    assert top[1] == top[3]            # horizontal across the span
    assert right[0] == right[2]        # vertical at the end
    assert left[1] > left[3]           # ends drop below the top bar


def test_a_rollup_gets_no_progress_or_float():
    renderer = render([
        task(Rollup=1, Percent_Complete=0.9, Earliest_Start_Date="20260202")
    ])
    assert renderer.of_class(renderer.lines, "ec-progress-line") == []
    assert renderer.of_class(renderer.rects, "ec-float-bar") == []


def test_a_milestone_draws_its_marker_and_no_bar():
    renderer = render([task(Milestone=1)])
    assert renderer.of_class(renderer.rects, "ec-duration-bar") == []
    markers = renderer.of_class(renderer.icons, "ec-milestone-marker")
    assert len(markers) == 1
    assert markers[0]["icon"] == "diamond-fill"


def test_the_milestone_anchors_on_the_end_date():
    """Start and end differ, so the anchor choice is observable."""
    renderer = render([task(Milestone=1, Start="20260203", End="20260210")])
    marker = renderer.of_class(renderer.icons, "ec-milestone-marker")[0]
    # 10 Feb is the 7th working column (index 6); the glyph centers on it.
    assert marker["x"] == pytest.approx(
        renderer.chart_x + renderer.day_w * 6.5
    )


# ── Deadlines ─────────────────────────────────────────────────────────────


def test_a_deadline_draws_its_icon():
    renderer = render([task(Deadline="20260211")])
    icons = [i for i in renderer.icons if i["icon"] == "square-fill"]
    assert len(icons) == 1


def test_a_deadline_outside_the_range_draws_nothing():
    renderer = render([task(Deadline="20260601")])
    assert [i for i in renderer.icons if i["icon"] == "square-fill"] == []


# ── Clipping, snapping and the exception log ──────────────────────────────


def test_a_bar_past_the_end_gets_a_continuation_icon_and_a_log_entry():
    renderer = render([task(Start="20260210", End="20260601")])
    assert any(i["icon"] == "arrow-bar-right" for i in renderer.icons)
    assert [e.kind for e in renderer.exceptions] == [KIND_CLIPPED_END]


def test_a_bar_before_the_start_gets_a_continuation_icon_and_a_log_entry():
    renderer = render([task(Start="20251201", End="20260204")])
    assert any(i["icon"] == "arrow-bar-left" for i in renderer.icons)
    assert [e.kind for e in renderer.exceptions] == [KIND_CLIPPED_START]


def test_a_span_covering_the_whole_range_reports_both_ends():
    renderer = render([task(Start="20250101", End="20270101")])
    kinds = {e.kind for e in renderer.exceptions}
    assert kinds == {KIND_CLIPPED_START, KIND_CLIPPED_END}


def test_a_weekend_event_snaps_forward_with_an_icon_and_a_log_entry():
    """Sat 7 Feb is not a column under weekend_style 0 (answer 22)."""
    renderer = render([task(Start="20260207", End="20260207")])
    assert any(i["icon"] == "arrow-left-circle" for i in renderer.icons)
    entries = [e for e in renderer.exceptions if e.kind == KIND_SNAPPED_EVENT]
    assert len(entries) == 1
    assert entries[0].datekey == "20260207"


def test_the_same_event_needs_no_snapping_when_weekends_are_shown():
    renderer = render([task(Start="20260207", End="20260207")], weekend_style=1)
    assert [e for e in renderer.exceptions if e.kind == KIND_SNAPPED_EVENT] == []


def test_a_task_hidden_entirely_by_the_weekend_is_reported_not_drawn():
    renderer = render([task(Start="20260207", End="20260208")])
    assert renderer.of_class(renderer.rects, "ec-duration-bar") == []
    assert [e.kind for e in renderer.exceptions] == [KIND_UNDRAWN]


def test_a_holiday_hidden_with_its_weekend_is_reported():
    class _HolidayDB(_DummyDB):
        holidays = {"20260208"}  # a Sunday

    renderer = render([task()], db=_HolidayDB())
    entries = [e for e in renderer.exceptions if e.kind == KIND_HIDDEN_HOLIDAY]
    assert [e.datekey for e in entries] == ["20260208"]


def test_holidays_on_working_days_are_shaded_not_reported():
    class _HolidayDB(_DummyDB):
        holidays = {"20260204"}  # a Wednesday

    renderer = render([task()], db=_HolidayDB())
    assert [e for e in renderer.exceptions if e.kind == KIND_HIDDEN_HOLIDAY] == []


# ── Today line ────────────────────────────────────────────────────────────


def test_the_today_line_draws_at_the_configured_date():
    renderer = render(
        [task()], gantt_show_today_line=True, gantt_today_date="20260205"
    )
    lines = renderer.of_class(renderer.lines, "ec-today-line")
    assert len(lines) == 1
    assert lines[0]["x1"] == pytest.approx(renderer.chart_x + renderer.day_w * 3)


def test_a_today_date_outside_the_range_draws_nothing():
    renderer = render(
        [task()], gantt_show_today_line=True, gantt_today_date="20270101"
    )
    assert renderer.of_class(renderer.lines, "ec-today-line") == []


def test_the_today_line_can_be_switched_off():
    renderer = render(
        [task()], gantt_show_today_line=False, gantt_today_date="20260205"
    )
    assert renderer.of_class(renderer.lines, "ec-today-line") == []


def test_a_today_date_on_a_hidden_day_snaps_to_the_next_column():
    renderer = render(
        [task()], gantt_show_today_line=True, gantt_today_date="20260207"
    )
    lines = renderer.of_class(renderer.lines, "ec-today-line")
    assert lines[0]["x1"] == pytest.approx(renderer.chart_x + renderer.day_w * 5)
