from __future__ import annotations

from pathlib import Path

import arrow
import drawsvg
import pytest

from config.config import create_calendar_config, setfontsizes
from shared.data_models import Event
from visualizers.timeline.layout import TimelineLayout
from visualizers.timeline.renderer import (
    TimelineCallout,
    TimelineDuration,
    TimelineRenderer,
)


class _DummyDB:
    @staticmethod
    def get_palette(name):
        return None


class _CaptureTimelineRenderer(TimelineRenderer):
    def __init__(self):
        super().__init__()
        self.text_calls: list[dict] = []
        self.rect_calls: list[dict] = []
        self.line_calls: list[dict] = []

    def _draw_text(self, x, y, text, font_name, font_size, **kwargs):
        self.text_calls.append(
            {"x": x, "y": y, "text": text, "font": font_name, "size": font_size}
        )

    def _draw_rect(self, x, y, w, h, **kwargs):
        self.rect_calls.append({"x": x, "y": y, "w": w, "h": h})

    def _draw_line(self, x1, y1, x2, y2, **kwargs):
        self.line_calls.append({"x1": x1, "y1": y1, "x2": x2, "y2": y2})

    def _draw_circle(self, *args, **kwargs):
        return None


class _CaptureMarkerRenderer(TimelineRenderer):
    def __init__(self):
        super().__init__()
        self.circle_calls: list[dict] = []
        self.text_calls: list[dict] = []

    def _draw_circle(self, cx, cy, radius, fill, stroke, stroke_width):
        self.circle_calls.append(
            {
                "cx": cx,
                "cy": cy,
                "radius": radius,
                "fill": fill,
                "stroke": stroke,
                "stroke_width": stroke_width,
            }
        )

    def _draw_text(self, x, y, text, font_name, font_size, **kwargs):
        self.text_calls.append(
            {"x": x, "y": y, "text": text, "font": font_name, "size": font_size}
        )


def _base_config(output: Path):
    config = create_calendar_config()
    config.pageX, config.pageY = 792.0, 1224.0
    config = setfontsizes(config)
    config.adjustedstart = "20260101"
    config.adjustedend = "20260630"
    config.outputfile = str(output)
    config.include_header = True
    config.include_footer = True
    return config


def test_timeline_layout_contains_content_area(tmp_path):
    config = _base_config(tmp_path / "timeline.svg")
    coords = TimelineLayout().calculate(config)

    assert "TimelineArea" in coords
    assert "HeaderLeft" in coords
    assert "FooterRight" in coords


def test_timeline_renderer_generates_svg(tmp_path):
    output = tmp_path / "timeline.svg"
    config = _base_config(output)
    coords = TimelineLayout().calculate(config)

    events = [
        {
            "Task_Name": "Performance Test Start",
            "Start": "20260115",
            "End": "20260115",
            "Notes": "Everything ready to conduct tests",
            "Priority": 1,
        },
        {
            "Task_Name": "First QA Test Results",
            "Start": "20260303",
            "End": "20260303",
            "Notes": "Application duplication verified",
            "Priority": 2,
        },
        {
            "Task_Name": "PROD Ready",
            "Start": "20260630",
            "End": "20260630",
            "Notes": "PROD environment built and tested",
            "Priority": 3,
        },
    ]

    renderer = TimelineRenderer()
    result = renderer.render(config, coords, events, _DummyDB())

    assert result.output_path == str(output)
    assert output.exists()
    text = output.read_text(encoding="utf-8")
    assert "<svg" in text
    assert "<path" in text


def test_timeline_background_none_is_transparent(tmp_path):
    output = tmp_path / "timeline_transparent.svg"
    config = _base_config(output)
    config.timeline_background_color = "none"
    coords = TimelineLayout().calculate(config)

    renderer = TimelineRenderer()
    renderer.render(config, coords, events=[], db=_DummyDB())

    text = output.read_text(encoding="utf-8")
    assert (
        f'<rect x="0" y="0" width="{config.pageX}" height="{config.pageY}"' not in text
    )


def test_timeline_duration_bars_use_start_end_alignment(tmp_path):
    output = tmp_path / "timeline_duration.svg"
    config = _base_config(output)

    renderer = TimelineRenderer()
    renderer._page_width = config.pageX
    renderer._page_height = config.pageY

    start = arrow.get("20260101", "YYYYMMDD")
    end = arrow.get("20260630", "YYYYMMDD")
    axis_left = 50.0
    axis_right = 700.0
    axis_y = 300.0

    durations = [
        Event(task_name="A", start="20260110", end="20260210"),
        Event(task_name="B", start="20260301", end="20260401"),
    ]
    laid_out = renderer._layout_durations(
        config, durations, start, end, axis_left, axis_right, axis_y
    )

    assert len(laid_out) == 2
    assert laid_out[0].start_x < laid_out[0].end_x
    assert laid_out[1].start_x < laid_out[1].end_x
    assert laid_out[0].lane == 0
    assert laid_out[1].lane == 0


def test_timeline_callouts_do_not_overlap_for_close_dates(tmp_path):
    output = tmp_path / "timeline_overlap.svg"
    config = _base_config(output)

    renderer = TimelineRenderer()
    renderer._page_width = config.pageX
    renderer._page_height = config.pageY

    start = arrow.get("20260101", "YYYYMMDD")
    end = arrow.get("20260331", "YYYYMMDD")
    axis_left = 60.0
    axis_right = 730.0
    area_x = 36.0
    area_w = 720.0
    area_h = 800.0
    axis_y = 400.0

    # Same/close-day events are worst-case for overlap.
    point_events = [
        Event(task_name=f"E{i}", start="20260215", end="20260215", priority=i)
        for i in range(6)
    ]
    callouts = renderer._layout_callouts(
        config,
        point_events,
        start,
        end,
        axis_left,
        axis_right,
        area_x,
        area_x + area_w,
        axis_y,
        area_h,
    )

    boxes = [
        (c.box_x, c.box_y, c.box_x + c.box_width, c.box_y + c.box_height)
        for c in callouts
    ]
    for i in range(len(boxes)):
        for j in range(i + 1, len(boxes)):
            assert not renderer._boxes_overlap(boxes[i], boxes[j], pad=2.0)


def test_timeline_duration_dates_share_same_y_and_offset_is_configurable(tmp_path):
    config = _base_config(tmp_path / "timeline_spacing.svg")
    config.timeline_duration_offset_y = 140.0

    renderer = _CaptureTimelineRenderer()
    renderer._page_width = config.pageX
    renderer._page_height = config.pageY

    start = arrow.get("20260101", "YYYYMMDD")
    end = arrow.get("20260331", "YYYYMMDD")
    durations = [Event(task_name="Duration A", start="20260110", end="20260210")]
    laid_out = renderer._layout_durations(
        config, durations, start, end, 50.0, 700.0, 300.0
    )

    renderer._draw_duration(config, laid_out[0], axis_y=300.0)

    start_label = arrow.get("20260110", "YYYYMMDD").format("MMM D")
    end_label = arrow.get("20260210", "YYYYMMDD").format("MMM D")
    y_start = next(c["y"] for c in renderer.text_calls if c["text"] == start_label)
    y_end = next(c["y"] for c in renderer.text_calls if c["text"] == end_label)
    assert y_start == y_end

    # The duration bar is drawn as the first rect in _draw_duration.
    # In SVG coords bar["y"] is the top edge (smallest y), 140 below axis_y=300.
    bar = renderer.rect_calls[0]
    assert round(bar["y"] - 300.0, 2) == 140.0


def test_timeline_duration_minimum_offset_exceeds_timeline_date_height(tmp_path):
    config = _base_config(tmp_path / "timeline_min_spacing.svg")
    config.timeline_duration_offset_y = 1.0  # Intentionally below minimum

    renderer = _CaptureTimelineRenderer()
    renderer._page_width = config.pageX
    renderer._page_height = config.pageY

    start = arrow.get("20260101", "YYYYMMDD")
    end = arrow.get("20260331", "YYYYMMDD")
    durations = [Event(task_name="Duration A", start="20260110", end="20260120")]
    laid_out = renderer._layout_durations(
        config, durations, start, end, 50.0, 700.0, 300.0
    )

    renderer._draw_duration(config, laid_out[0], axis_y=300.0)

    _, _, date_size, _ = renderer._duration_metrics(config)
    expected_min = renderer._min_duration_offset(date_size)
    # In SVG coords bar["y"] is the top edge (smallest y), expected_min below axis_y=300.
    bar = renderer.rect_calls[0]
    assert round(bar["y"] - 300.0, 2) == round(expected_min, 2)
    assert expected_min > date_size


def test_timeline_month_ticks_default_to_first_of_month_inside_range(tmp_path):
    config = _base_config(tmp_path / "timeline_ticks.svg")
    renderer = _CaptureTimelineRenderer()
    renderer._page_width = config.pageX
    renderer._page_height = config.pageY

    start = arrow.get("20260115", "YYYYMMDD")
    end = arrow.get("20260320", "YYYYMMDD")
    renderer._draw_month_ticks(config, start, end, 50.0, 700.0, 300.0)

    labels = [c["text"] for c in renderer.text_calls]
    assert "Feb 1" in labels
    assert "Mar 1" in labels
    assert "Jan 1" not in labels


def test_timeline_date_format_is_configurable(tmp_path):
    config = _base_config(tmp_path / "timeline_format.svg")
    config.timeline_date_format = "YYYY-MM-DD"

    renderer = _CaptureTimelineRenderer()
    renderer._page_width = config.pageX
    renderer._page_height = config.pageY

    start = arrow.get("20260101", "YYYYMMDD")
    end = arrow.get("20260331", "YYYYMMDD")
    durations = [Event(task_name="Duration A", start="20260110", end="20260210")]
    laid_out = renderer._layout_durations(
        config, durations, start, end, 50.0, 700.0, 300.0
    )
    renderer._draw_duration(config, laid_out[0], axis_y=300.0)

    labels = {c["text"] for c in renderer.text_calls}
    assert "2026-01-10" in labels
    assert "2026-02-10" in labels


def test_timeline_marker_defaults_to_filled_circle_and_icon_uses_circle(tmp_path):
    config = _base_config(tmp_path / "timeline_marker.svg")
    config.timeline_marker_radius = 6.0
    config.timeline_icon_size = 12.0
    renderer = _CaptureMarkerRenderer()

    renderer._draw_timeline_marker(
        config,
        x=100.0,
        y=200.0,
        color="deepskyblue",
        icon_name=None,
    )
    assert renderer.circle_calls
    assert renderer.circle_calls[-1]["fill"] == "deepskyblue"
    assert renderer.circle_calls[-1]["radius"] == 6.0

    renderer._drawing = drawsvg.Drawing(200, 200)
    renderer._icon_svg_map = {
        "rocket": '<svg viewBox="0 0 24 24"><path d="M2 2h20v20H2z"/></svg>'
    }
    renderer._draw_timeline_marker(
        config,
        x=120.0,
        y=220.0,
        color="tomato",
        icon_name="rocket",
    )
    assert renderer.circle_calls[-1]["fill"] == "none"
    assert renderer.circle_calls[-1]["stroke"] == "tomato"
    assert renderer.text_calls == []


def test_timeline_callout_uses_configured_event_name_and_notes_font_sizes(tmp_path):
    config = _base_config(tmp_path / "timeline_callout_sizes.svg")
    config.timeline_name_text_font_size = 15.0
    config.timeline_notes_text_font_size = 11.0
    renderer = _CaptureTimelineRenderer()

    event = Event(task_name="Launch", start="20260110", end="20260110", notes="Go live")
    callout = TimelineCallout(
        event=event,
        color="gold",
        x=200.0,
        lane=0,
        box_x=150.0,
        box_y=230.0,
        box_width=120.0,
        box_height=70.0,
    )
    renderer._draw_callout(config, callout, axis_y=300.0)

    launch = [c for c in renderer.text_calls if c["text"] == "Launch"]
    notes = [c for c in renderer.text_calls if c["text"] == "Go live"]
    assert launch and launch[0]["size"] == 15.0
    assert notes and notes[0]["size"] == 11.0


def test_timeline_callout_dates_stagger_by_row_to_reduce_overwrite(tmp_path):
    config = _base_config(tmp_path / "timeline_callout_date_rows.svg")
    config.timeline_date_format = "YYYYMMDD"
    renderer = _CaptureTimelineRenderer()

    callout_a = TimelineCallout(
        event=Event(task_name="A", start="20260110", end="20260110"),
        color="gold",
        x=200.0,
        lane=0,
        box_x=150.0,
        box_y=230.0,
        box_width=120.0,
        box_height=70.0,
        date_row=0,
    )
    callout_b = TimelineCallout(
        event=Event(task_name="B", start="20260111", end="20260111"),
        color="gold",
        x=205.0,
        lane=0,
        box_x=155.0,
        box_y=220.0,
        box_width=120.0,
        box_height=70.0,
        date_row=1,
    )
    renderer._draw_callout(config, callout_a, axis_y=300.0)
    renderer._draw_callout(config, callout_b, axis_y=300.0)

    date_a = [c for c in renderer.text_calls if c["text"] == "20260110"]
    date_b = [c for c in renderer.text_calls if c["text"] == "20260111"]
    assert date_a and date_b
    assert date_a[0]["y"] != date_b[0]["y"]


def test_timeline_callout_connector_uses_orthogonal_segments(tmp_path):
    config = _base_config(tmp_path / "timeline_orthogonal_connector.svg")
    renderer = _CaptureTimelineRenderer()

    callout = TimelineCallout(
        event=Event(task_name="A", start="20260110", end="20260110"),
        color="gold",
        x=100.0,
        lane=0,
        box_x=150.0,
        box_y=200.0,
        box_width=120.0,
        box_height=70.0,
        date_row=0,
    )
    renderer._draw_callout_connector(config, callout, axis_y=300.0)

    assert len(renderer.line_calls) >= 2
    first = renderer.line_calls[0]
    assert first["x1"] == first["x2"] == callout.x
    assert first["y1"] == 300.0  # connector intersects timeline at event date

    vlines = [l for l in renderer.line_calls if l["x1"] == l["x2"]]
    hlines = [l for l in renderer.line_calls if l["y1"] == l["y2"]]
    assert vlines
    assert hlines
    assert any(l["y1"] == callout.box_y for l in hlines)
    assert any(l["x2"] == callout.box_x or l["x1"] == callout.box_x for l in hlines)


def test_timeline_callout_connector_avoids_other_event_rectangles(tmp_path):
    config = _base_config(tmp_path / "timeline_connector_avoid_boxes.svg")
    renderer = _CaptureTimelineRenderer()

    target = TimelineCallout(
        event=Event(task_name="Target", start="20260110", end="20260110"),
        color="gold",
        x=200.0,
        lane=0,
        box_x=250.0,
        box_y=150.0,
        box_width=120.0,
        box_height=70.0,
        date_row=0,
    )
    blocker = TimelineCallout(
        event=Event(task_name="Blocker", start="20260111", end="20260111"),
        color="tomato",
        x=180.0,
        lane=0,
        box_x=170.0,
        box_y=200.0,
        box_width=60.0,
        box_height=55.0,  # Blocks direct vertical connector, but does not overlap target box
        date_row=1,
    )
    callouts = [target, blocker]
    renderer._draw_callout_connector(config, target, axis_y=300.0, callouts=callouts)

    # Ensure every connector segment avoids the blocker rectangle.
    blocker_rect = (
        blocker.box_x,
        blocker.box_y,
        blocker.box_x + blocker.box_width,
        blocker.box_y + blocker.box_height,
    )
    for seg in renderer.line_calls:
        hit = renderer._segment_intersects_rect(
            (seg["x1"], seg["y1"], seg["x2"], seg["y2"]),
            blocker_rect,
            pad=0.0,
        )
        assert not hit


def test_timeline_callout_connector_offsets_x_by_date_row(tmp_path):
    config = _base_config(tmp_path / "timeline_connector_x_offset.svg")
    renderer = _CaptureTimelineRenderer()

    callout = TimelineCallout(
        event=Event(task_name="Target", start="20260110", end="20260110"),
        color="gold",
        x=200.0,
        lane=0,
        box_x=140.0,
        box_y=150.0,
        box_width=120.0,
        box_height=70.0,
        date_row=1,
    )
    renderer._draw_callout_connector(config, callout, axis_y=300.0, callouts=[callout])

    # First segment must anchor on exact event date x.
    assert renderer.line_calls
    first = renderer.line_calls[0]
    assert first["x1"] == first["x2"] == 200.0
    assert first["y1"] == 300.0

    # A non-zero date row should create a horizontal elbow offset between axis and box.
    elbow_h = [
        l
        for l in renderer.line_calls
        if l["y1"] == l["y2"] and l["y1"] < 300.0 and l["y1"] > callout.box_y
    ]
    assert elbow_h
    assert any(l["x1"] != l["x2"] for l in elbow_h)


def test_timeline_callout_uses_configured_event_box_width_and_height(tmp_path):
    config = _base_config(tmp_path / "timeline_callout_box.svg")
    config.timeline_event_box_width = 160.0
    config.timeline_event_box_height = 72.0
    renderer = TimelineRenderer()
    renderer._page_width = config.pageX
    renderer._page_height = config.pageY

    start = arrow.get("20260101", "YYYYMMDD")
    end = arrow.get("20260131", "YYYYMMDD")
    callouts = renderer._layout_callouts(
        config,
        [Event(task_name="Event", start="20260110", end="20260110")],
        start,
        end,
        60.0,
        730.0,
        36.0,
        756.0,
        400.0,
        800.0,
    )
    assert len(callouts) == 1
    assert callouts[0].box_width == 160.0
    assert callouts[0].box_height == 72.0


def test_timeline_duration_uses_configured_name_and_notes_font_sizes(tmp_path):
    config = _base_config(tmp_path / "timeline_duration_sizes.svg")
    config.timeline_name_text_font_size = 13.0
    config.timeline_notes_text_font_size = 9.0
    config.include_notes = True
    renderer = _CaptureTimelineRenderer()

    event = Event(
        task_name="Imaginary Sprint 4",
        start="20260330",
        end="20260410",
        notes="Execution window",
    )
    duration = TimelineDuration(
        event=event,
        color="gold",
        start_x=250.0,
        end_x=410.0,
        lane=0,
        min_width=40.0,
    )
    renderer._draw_duration(config, duration, axis_y=300.0)

    name = [c for c in renderer.text_calls if c["text"] == "Imaginary Sprint 4"]
    notes = [c for c in renderer.text_calls if c["text"] == "Execution window"]
    assert name and 0 < name[0]["size"] <= 13.0
    assert notes and 0 < notes[0]["size"] <= 9.0


def test_timeline_duration_uses_configured_box_height_and_min_width(tmp_path):
    config = _base_config(tmp_path / "timeline_duration_box.svg")
    config.timeline_duration_box_height = 34.0
    config.timeline_duration_box_width = 140.0
    renderer = TimelineRenderer()
    renderer._page_width = config.pageX
    renderer._page_height = config.pageY

    start = arrow.get("20260101", "YYYYMMDD")
    end = arrow.get("20260331", "YYYYMMDD")
    durations = [Event(task_name="A", start="20260110", end="20260110", notes="B")]
    laid_out = renderer._layout_durations(
        config, durations, start, end, 60.0, 730.0, 300.0
    )
    assert len(laid_out) == 1
    assert (laid_out[0].end_x - laid_out[0].start_x) >= 140.0

    _, _, _, bar_h = renderer._duration_metrics(config)
    assert bar_h == 34.0


def test_timeline_shrinks_text_when_box_constraints_are_tight(tmp_path):
    config = _base_config(tmp_path / "timeline_shrink.svg")
    config.timeline_name_text_font_size = 18.0
    config.timeline_notes_text_font_size = 14.0
    config.timeline_event_box_width = 80.0
    config.timeline_event_box_height = 30.0
    renderer = _CaptureTimelineRenderer()

    event = Event(
        task_name="Very long launch name",
        start="20260110",
        end="20260110",
        notes="Long detail notes line",
    )
    callout = TimelineCallout(
        event=event,
        color="gold",
        x=200.0,
        lane=0,
        box_x=150.0,
        box_y=220.0,
        box_width=80.0,
        box_height=30.0,
    )
    renderer._draw_callout(config, callout, axis_y=300.0)

    # The configured bases are 18/14; tight box should force smaller render sizes.
    used = [c["size"] for c in renderer.text_calls if c["text"]]
    assert used
    assert min(used) < 14.0
    assert max(used) < 18.0


def test_timeline_callouts_avoid_overlap_on_small_page(tmp_path):
    output = tmp_path / "timeline_small.svg"
    config = _base_config(output)
    config.pageX, config.pageY = 360.0, 520.0
    config = setfontsizes(config)

    renderer = TimelineRenderer()
    renderer._page_width = config.pageX
    renderer._page_height = config.pageY

    start = arrow.get("20260101", "YYYYMMDD")
    end = arrow.get("20260131", "YYYYMMDD")
    axis_left = 36.0
    axis_right = 324.0
    area_x = 18.0
    area_w = 324.0
    area_h = 380.0
    axis_y = 240.0

    close_events = [
        Event(task_name=f"Event {i}", start="20260115", end="20260115", priority=i)
        for i in range(10)
    ]
    callouts = renderer._layout_callouts(
        config,
        close_events,
        start,
        end,
        axis_left,
        axis_right,
        area_x,
        area_x + area_w,
        axis_y,
        area_h,
    )

    boxes = [
        (c.box_x, c.box_y, c.box_x + c.box_width, c.box_y + c.box_height)
        for c in callouts
    ]
    overlaps = 0
    for i in range(len(boxes)):
        for j in range(i + 1, len(boxes)):
            if renderer._boxes_overlap(boxes[i], boxes[j], pad=2.0):
                overlaps += 1
    # On constrained pages, placement should strongly avoid collisions.
    assert overlaps <= 1


def test_timeline_today_uses_configured_date_and_label(tmp_path):
    config = _base_config(tmp_path / "timeline_today.svg")
    config.timeline_today_date = "2026-03-15"
    config.timeline_today_label_text = "Reference Date"

    renderer = _CaptureTimelineRenderer()
    renderer._page_width = config.pageX
    renderer._page_height = config.pageY
    renderer._draw_today_marker(
        config,
        start=arrow.get("20260301", "YYYYMMDD"),
        end=arrow.get("20260331", "YYYYMMDD"),
        axis_left=50.0,
        axis_right=700.0,
        axis_y=300.0,
        area_y=20.0,
        area_h=300.0,
    )

    labels = [c["text"] for c in renderer.text_calls]
    assert "Reference Date" in labels


def test_timeline_today_label_stays_within_svg_bounds(tmp_path):
    config = _base_config(tmp_path / "timeline_today_bounds.svg")
    config.timeline_today_date = "2026-03-15"
    config.timeline_today_label_text = "Today Label"
    config.timeline_today_label_offset_y = 1000.0  # force upper clamp

    renderer = _CaptureTimelineRenderer()
    renderer._page_width = 200.0
    renderer._page_height = 120.0
    config.pageX, config.pageY = 200.0, 120.0
    config = setfontsizes(config)
    config.timeline_today_date = "2026-03-15"
    config.timeline_today_label_text = "Today Label"
    config.timeline_today_label_offset_y = 1000.0

    renderer._draw_today_marker(
        config,
        start=arrow.get("20260301", "YYYYMMDD"),
        end=arrow.get("20260331", "YYYYMMDD"),
        axis_left=20.0,
        axis_right=180.0,
        axis_y=60.0,
        area_y=0.0,
        area_h=120.0,
    )

    label_call = next(c for c in renderer.text_calls if c["text"] == "Today Label")
    assert 0.0 <= label_call["y"] <= config.pageY


# ---------------------------------------------------------------------------
# Today-line length and direction tests
# ---------------------------------------------------------------------------


def _today_line_call(renderer: _CaptureTimelineRenderer) -> dict:
    """Return the vertical line call that represents the today marker."""
    # The today line is drawn as a vertical line (x1 == x2) that is not a tick.
    # Tick lines are short; the today line spans the configured portion of the area.
    vertical = [c for c in renderer.line_calls if c["x1"] == c["x2"]]
    assert vertical, "Expected at least one vertical line call for the today marker"
    # Pick the tallest vertical span (today line is typically the longest).
    return max(vertical, key=lambda c: abs(c["y2"] - c["y1"]))


def _draw_today(config, direction=None, length=None):
    """Helper: run _draw_today_marker with given config overrides and return renderer."""
    if direction is not None:
        config.timeline_today_line_direction = direction
    if length is not None:
        config.timeline_today_line_length = length

    renderer = _CaptureTimelineRenderer()
    renderer._page_width = config.pageX
    renderer._page_height = config.pageY
    renderer._draw_today_marker(
        config,
        start=arrow.get("20260301", "YYYYMMDD"),
        end=arrow.get("20260331", "YYYYMMDD"),
        axis_left=50.0,
        axis_right=700.0,
        axis_y=300.0,
        area_y=20.0,
        area_h=580.0,
    )
    return renderer


def test_today_line_direction_both_full_span(tmp_path):
    """Default 'both' with length=0 spans full area."""
    config = _base_config(tmp_path / "out.svg")
    config.timeline_today_date = "2026-03-15"
    renderer = _draw_today(config, direction="both", length=0.0)
    line = _today_line_call(renderer)
    assert min(line["y1"], line["y2"]) == pytest.approx(20.0)  # area_top (small SVG y)
    assert max(line["y1"], line["y2"]) == pytest.approx(
        600.0
    )  # area_bottom (large SVG y)


def test_today_line_direction_above_full_span(tmp_path):
    """'above' with length=0 goes from area top to axis_y (SVG: top = small y)."""
    config = _base_config(tmp_path / "out.svg")
    config.timeline_today_date = "2026-03-15"
    renderer = _draw_today(config, direction="above", length=0.0)
    line = _today_line_call(renderer)
    assert min(line["y1"], line["y2"]) == pytest.approx(20.0)  # area_top (small SVG y)
    assert max(line["y1"], line["y2"]) == pytest.approx(300.0)  # axis_y


def test_today_line_direction_below_full_span(tmp_path):
    """'below' with length=0 goes from axis_y to area bottom (SVG: bottom = large y)."""
    config = _base_config(tmp_path / "out.svg")
    config.timeline_today_date = "2026-03-15"
    renderer = _draw_today(config, direction="below", length=0.0)
    line = _today_line_call(renderer)
    assert min(line["y1"], line["y2"]) == pytest.approx(300.0)  # axis_y
    assert max(line["y1"], line["y2"]) == pytest.approx(
        600.0
    )  # area_bottom (large SVG y)


def test_today_line_explicit_length_both(tmp_path):
    """Explicit length with 'both' splits half above, half below axis."""
    config = _base_config(tmp_path / "out.svg")
    config.timeline_today_date = "2026-03-15"
    renderer = _draw_today(config, direction="both", length=100.0)
    line = _today_line_call(renderer)
    assert min(line["y1"], line["y2"]) == pytest.approx(250.0)  # axis_y - 50
    assert max(line["y1"], line["y2"]) == pytest.approx(350.0)  # axis_y + 50


def test_today_line_explicit_length_above(tmp_path):
    """Explicit length with 'above' extends upward from axis_y (SVG: to smaller y)."""
    config = _base_config(tmp_path / "out.svg")
    config.timeline_today_date = "2026-03-15"
    renderer = _draw_today(config, direction="above", length=80.0)
    line = _today_line_call(renderer)
    assert min(line["y1"], line["y2"]) == pytest.approx(220.0)  # axis_y - 80
    assert max(line["y1"], line["y2"]) == pytest.approx(300.0)  # axis_y


def test_today_line_explicit_length_below(tmp_path):
    """Explicit length with 'below' extends downward from axis_y (SVG: to larger y)."""
    config = _base_config(tmp_path / "out.svg")
    config.timeline_today_date = "2026-03-15"
    renderer = _draw_today(config, direction="below", length=60.0)
    line = _today_line_call(renderer)
    assert min(line["y1"], line["y2"]) == pytest.approx(300.0)  # axis_y
    assert max(line["y1"], line["y2"]) == pytest.approx(360.0)  # axis_y + 60


def test_today_line_clamped_to_area(tmp_path):
    """A length that exceeds the area is clamped to the area boundaries."""
    config = _base_config(tmp_path / "out.svg")
    config.timeline_today_date = "2026-03-15"
    # area_y=20, area_h=580 → area_bottom=600 (SVG). axis_y=300. length=9999 → exceeds area.
    renderer = _draw_today(config, direction="both", length=9999.0)
    line = _today_line_call(renderer)
    assert min(line["y1"], line["y2"]) >= 20.0
    assert max(line["y1"], line["y2"]) <= 600.0
