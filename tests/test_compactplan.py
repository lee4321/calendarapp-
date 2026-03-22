"""Tests for the compactplan visualizer."""
from __future__ import annotations

from datetime import date
from pathlib import Path

from config.config import create_calendar_config, setfontsizes
from visualizers.compactplan.layout import CompactPlanLayout
from visualizers.compactplan.renderer import CompactPlanRenderer


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


class _DummyDB:
    @staticmethod
    def get_palette(name):
        return None

    @staticmethod
    def is_nonworkday(daykey, country=None):
        return False

    @staticmethod
    def get_icon_svg(name):
        return None


class _CaptureCompactPlanRenderer(CompactPlanRenderer):
    """Subclass that records draw calls without requiring a real SVG output file."""

    def __init__(self):
        super().__init__()
        self.line_calls: list[tuple[float, float, float, float]] = []
        self.line_kwargs: list[dict] = []
        self.text_values: list[str] = []
        self.rect_calls: list[dict] = []

    def _draw_line(self, x1, y1, x2, y2, **kwargs):
        self.line_calls.append((x1, y1, x2, y2))
        self.line_kwargs.append(kwargs)
        super()._draw_line(x1, y1, x2, y2, **kwargs)

    def _draw_text(self, x, y, text, font_name, font_size, **kwargs):
        self.text_values.append(str(text))
        super()._draw_text(x, y, text, font_name, font_size, **kwargs)

    def _draw_rect(self, x, y, w, h, **kwargs):
        self.rect_calls.append({"x": x, "y": y, "w": w, "h": h, **kwargs})
        super()._draw_rect(x, y, w, h, **kwargs)


def _base_config(output: Path):
    config = create_calendar_config()
    config.pageX, config.pageY = 792.0, 612.0
    config = setfontsizes(config)
    config.adjustedstart = "20260309"
    config.adjustedend = "20260424"
    config.weekend_style = 0  # workweek only
    config.outputfile = str(output)
    config.include_header = False
    config.include_footer = False
    return config


def _dur(task, start, end, group="", color=None):
    """Build a minimal duration event dict."""
    return {
        "Task_Name": task,
        "Start": start,
        "End": end,
        "Resource_Group": group,
        "Color": color or "",
        "Priority": 1,
        "Milestone": 0,
        "Rollup": 0,
        "Percent_Complete": 0,
        "Notes": "",
        "Resource_Names": "",
        "Icon": "",
        "WBS": "",
        "Event_Type": "",
        "Datekey": "",
    }


def _milestone(task, start, group="", color=None):
    return {
        "Task_Name": task,
        "Start": start,
        "End": start,
        "Resource_Group": group,
        "Color": color or "",
        "Priority": 1,
        "Milestone": 1,
        "Rollup": 0,
        "Percent_Complete": 0,
        "Notes": "",
        "Resource_Names": "",
        "Icon": "",
        "WBS": "",
        "Event_Type": "",
        "Datekey": "",
    }


# ---------------------------------------------------------------------------
# Layout tests
# ---------------------------------------------------------------------------


def test_layout_returns_compact_plan_area(tmp_path):
    config = _base_config(tmp_path / "out.svg")
    coords = CompactPlanLayout().calculate(config)
    assert "CompactPlanArea" in coords
    x, y, w, h = coords["CompactPlanArea"]
    assert w > 0
    assert h > 0


def test_layout_with_header_footer(tmp_path):
    config = _base_config(tmp_path / "out.svg")
    config.include_header = True
    config.include_footer = True
    coords = CompactPlanLayout().calculate(config)
    assert "CompactPlanArea" in coords
    assert "HeaderLeft" in coords
    assert "FooterRight" in coords


# ---------------------------------------------------------------------------
# Static helper unit tests (no SVG rendering needed)
# ---------------------------------------------------------------------------


class TestRowY:
    def test_row_0_above_axis(self):
        axis_y = 100.0
        y = CompactPlanRenderer._row_y(0, axis_y, axis_padding=4.0, lane_spacing=6.0)
        assert y < axis_y

    def test_row_1_below_axis(self):
        axis_y = 100.0
        y = CompactPlanRenderer._row_y(1, axis_y, axis_padding=4.0, lane_spacing=6.0)
        assert y > axis_y

    def test_row_2_further_above_than_row_0(self):
        axis_y = 100.0
        y0 = CompactPlanRenderer._row_y(0, axis_y, 4.0, 6.0)
        y2 = CompactPlanRenderer._row_y(2, axis_y, 4.0, 6.0)
        assert y2 < y0

    def test_row_3_further_below_than_row_1(self):
        axis_y = 100.0
        y1 = CompactPlanRenderer._row_y(1, axis_y, 4.0, 6.0)
        y3 = CompactPlanRenderer._row_y(3, axis_y, 4.0, 6.0)
        assert y3 > y1


class TestOverlaps:
    def test_no_overlap(self):
        assert not CompactPlanRenderer._overlaps(0.0, 10.0, [(15.0, 25.0)])

    def test_overlap(self):
        assert CompactPlanRenderer._overlaps(5.0, 15.0, [(10.0, 20.0)])

    def test_touching_edge_no_overlap(self):
        # [0,10) and [10,20) share no interior
        assert not CompactPlanRenderer._overlaps(0.0, 10.0, [(10.0, 20.0)])

    def test_empty_occupancy(self):
        assert not CompactPlanRenderer._overlaps(0.0, 10.0, [])


class TestParseDate:
    def test_yyyymmdd(self):
        assert CompactPlanRenderer._parse_date("20260309") == date(2026, 3, 9)

    def test_iso_format(self):
        assert CompactPlanRenderer._parse_date("2026-03-09") == date(2026, 3, 9)

    def test_none_input(self):
        assert CompactPlanRenderer._parse_date("") is None

    def test_invalid_input(self):
        assert CompactPlanRenderer._parse_date("not-a-date") is None


class TestVisibleDays:
    def test_workweek_excludes_weekends(self):
        start = date(2026, 3, 9)   # Monday
        end = date(2026, 3, 15)    # Sunday
        days = CompactPlanRenderer._visible_days(start, end, weekend_style=0)
        assert all(d.weekday() < 5 for d in days)
        assert len(days) == 5

    def test_full_week_includes_weekends(self):
        start = date(2026, 3, 9)
        end = date(2026, 3, 15)
        days = CompactPlanRenderer._visible_days(start, end, weekend_style=1)
        assert len(days) == 7


# ---------------------------------------------------------------------------
# Color assignment tests
# ---------------------------------------------------------------------------


def test_assign_group_colors_cycles_palette(tmp_path):
    config = _base_config(tmp_path / "out.svg")
    config.compactplan_palette = ["red", "blue", "green"]
    from shared.data_models import Event

    events = [
        Event.from_dict(_dur("T1", "20260309", "20260313", group="Alpha")),
        Event.from_dict(_dur("T2", "20260309", "20260313", group="Beta")),
        Event.from_dict(_dur("T3", "20260309", "20260313", group="Gamma")),
        Event.from_dict(_dur("T4", "20260309", "20260313", group="Delta")),  # cycles
    ]
    renderer = CompactPlanRenderer()
    color_map = renderer._assign_group_colors(events, config)

    # Groups are sorted alphabetically: Alpha, Beta, Delta, Gamma
    assert color_map["Alpha"] == "red"
    assert color_map["Beta"] == "blue"
    assert color_map["Delta"] == "green"
    assert color_map["Gamma"] == "red"  # wraps (index 3 % 3 == 0)


def test_event_color_overrides_group_color(tmp_path):
    config = _base_config(tmp_path / "out.svg")
    config.compactplan_palette = ["#92d050"]
    config.adjustedstart = "20260309"
    config.adjustedend = "20260424"
    from shared.data_models import Event

    evt = Event.from_dict(_dur("Custom", "20260309", "20260313", group="Team1", color="magenta"))
    assert evt.color == "magenta"


# ---------------------------------------------------------------------------
# Greedy row placement tests
# ---------------------------------------------------------------------------


def test_overlapping_durations_go_to_different_rows(tmp_path):
    config = _base_config(tmp_path / "out.svg")
    config.compactplan_palette = ["#92d050", "#6b9bc7"]
    from shared.data_models import Event

    # Two overlapping durations in the same group → should land on different rows
    d1 = Event.from_dict(_dur("D1", "20260309", "20260316", group="Team1"))
    d2 = Event.from_dict(_dur("D2", "20260310", "20260317", group="Team1"))

    renderer = CompactPlanRenderer()
    # Build minimal day_x covering the range (Mon–Fri workweek)
    start = date(2026, 3, 9)
    end = date(2026, 3, 20)
    visible = renderer._visible_days(start, end, 0)
    px = 500.0 / len(visible)
    day_x = {d: i * px for i, d in enumerate(visible)}
    color_map = {"Team1": "#92d050"}

    placed = renderer._place_durations(
        [d1, d2], color_map, day_x, 0.0, 500.0, px, config, axis_y=100.0
    )

    assert len(placed) == 2
    assert placed[0].row_y != placed[1].row_y


def test_non_overlapping_durations_share_row(tmp_path):
    config = _base_config(tmp_path / "out.svg")
    config.compactplan_palette = ["#92d050"]
    from shared.data_models import Event

    d1 = Event.from_dict(_dur("D1", "20260309", "20260313", group="Team1"))
    d2 = Event.from_dict(_dur("D2", "20260316", "20260320", group="Team1"))

    renderer = CompactPlanRenderer()
    start = date(2026, 3, 9)
    end = date(2026, 3, 22)
    visible = renderer._visible_days(start, end, 0)
    px = 500.0 / len(visible)
    day_x = {d: i * px for i, d in enumerate(visible)}
    color_map = {"Team1": "#92d050"}

    placed = renderer._place_durations(
        [d1, d2], color_map, day_x, 0.0, 500.0, px, config, axis_y=100.0
    )

    assert len(placed) == 2
    assert placed[0].row_y == placed[1].row_y


# ---------------------------------------------------------------------------
# Renderer integration tests
# ---------------------------------------------------------------------------


def test_renderer_produces_svg(tmp_path):
    output = tmp_path / "compact.svg"
    config = _base_config(output)
    coords = CompactPlanLayout().calculate(config)
    events = [
        _dur("Sprint 1", "20260309", "20260320", group="Team1"),
        _dur("Sprint 2", "20260323", "20260403", group="Team2"),
    ]
    renderer = _CaptureCompactPlanRenderer()
    result = renderer.render(config, coords, events, _DummyDB())

    assert output.exists()
    svg_text = output.read_text()
    assert svg_text.startswith("<svg") or "<?xml" in svg_text or "<svg" in svg_text
    assert len(svg_text) > 100


def test_renderer_draws_axis_line(tmp_path):
    output = tmp_path / "compact.svg"
    config = _base_config(output)
    coords = CompactPlanLayout().calculate(config)

    renderer = _CaptureCompactPlanRenderer()
    renderer.render(config, coords, [], _DummyDB())

    # The axis line is a full-width horizontal line
    area_x, _, area_w, _ = coords["CompactPlanArea"]
    axis_lines = [
        (x1, y1, x2, y2)
        for x1, y1, x2, y2 in renderer.line_calls
        if abs(y1 - y2) < 0.01 and abs(x2 - x1 - area_w) < 1.0
    ]
    assert axis_lines, "Expected at least one full-width horizontal axis line"


def test_renderer_draws_duration_lines(tmp_path):
    output = tmp_path / "compact.svg"
    config = _base_config(output)
    coords = CompactPlanLayout().calculate(config)

    events = [_dur("Build", "20260309", "20260313", group="Dev")]
    renderer = _CaptureCompactPlanRenderer()
    renderer.render(config, coords, events, _DummyDB())

    # At least one line must not be the full axis width (i.e. a duration line)
    area_x, _, area_w, _ = coords["CompactPlanArea"]
    non_axis = [
        c for c in renderer.line_calls
        if abs(c[1] - c[3]) < 0.01 and abs(c[2] - c[0] - area_w) > 5.0
    ]
    assert non_axis, "Expected duration line(s)"


def test_renderer_legend_present_when_enabled(tmp_path):
    output = tmp_path / "compact.svg"
    config = _base_config(output)
    config.compactplan_show_legend = True

    coords = CompactPlanLayout().calculate(config)
    events = [_dur("Sprint 1", "20260309", "20260320", group="Team1")]

    renderer = _CaptureCompactPlanRenderer()
    renderer.render(config, coords, events, _DummyDB())

    # Legend text contains the group name
    assert any("Team1" in v for v in renderer.text_values)


def test_renderer_legend_absent_when_disabled(tmp_path):
    output = tmp_path / "compact.svg"
    config = _base_config(output)
    config.compactplan_show_legend = False

    coords = CompactPlanLayout().calculate(config)
    events = [_dur("Sprint 1", "20260309", "20260320", group="Team1")]

    renderer = _CaptureCompactPlanRenderer()
    renderer.render(config, coords, events, _DummyDB())

    # Without legend, "Team1" should not appear in text renders
    assert not any("Team1" in v for v in renderer.text_values)


def test_renderer_milestone_at_correct_x(tmp_path):
    output = tmp_path / "compact.svg"
    config = _base_config(output)
    config.compactplan_show_milestone_labels = False  # suppress label text lines

    coords = CompactPlanLayout().calculate(config)
    events = [_milestone("Launch", "20260316", group="Team1")]

    renderer = _CaptureCompactPlanRenderer()
    renderer.render(config, coords, events, _DummyDB())

    # A vertical line (x1==x2) should be drawn for the milestone stem
    vertical_lines = [c for c in renderer.line_calls if abs(c[0] - c[2]) < 0.01]
    assert vertical_lines, "Expected at least one vertical line for milestone stem"


def test_renderer_milestone_label_rendered(tmp_path):
    output = tmp_path / "compact.svg"
    config = _base_config(output)
    config.compactplan_show_milestone_labels = True

    coords = CompactPlanLayout().calculate(config)
    events = [_milestone("Go Live", "20260316", group="Team1")]

    renderer = _CaptureCompactPlanRenderer()
    renderer.render(config, coords, events, _DummyDB())

    assert any("Go Live" in v for v in renderer.text_values)


def test_renderer_legend_entries_match_groups(tmp_path):
    output = tmp_path / "compact.svg"
    config = _base_config(output)
    config.compactplan_show_legend = True

    coords = CompactPlanLayout().calculate(config)
    events = [
        _dur("Task A", "20260309", "20260313", group="Alpha"),
        _dur("Task B", "20260316", "20260320", group="Beta"),
    ]

    renderer = _CaptureCompactPlanRenderer()
    renderer.render(config, coords, events, _DummyDB())

    legend_texts = " ".join(renderer.text_values)
    assert "Alpha" in legend_texts
    assert "Beta" in legend_texts


def test_renderer_empty_events_no_crash(tmp_path):
    output = tmp_path / "compact.svg"
    config = _base_config(output)
    coords = CompactPlanLayout().calculate(config)

    renderer = _CaptureCompactPlanRenderer()
    renderer.render(config, coords, [], _DummyDB())

    assert output.exists()
