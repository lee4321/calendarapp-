from __future__ import annotations

from pathlib import Path

import arrow
import drawsvg
import pytest

from config.config import create_calendar_config, setfontsizes
from renderers.glyph_cache import get_ink_extents
from shared.wbs_filter import wbs_group
from shared.data_models import Event
from visualizers.timeline.layout import TimelineLayout
from shared.orientation import Orientation, Side
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
            {
                "x": x, "y": y, "text": text,
                "font": font_name, "size": font_size,
                **kwargs,
            }
        )

    def _draw_rect(self, x, y, w, h, **kwargs):
        self.rect_calls.append({"x": x, "y": y, "w": w, "h": h, **kwargs})

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
    """Labella VPSC places same-date events on distinct layers — verify
    no two callouts on the same layer overlap along the axis."""
    output = tmp_path / "timeline_overlap.svg"
    config = _base_config(output)

    renderer = TimelineRenderer()
    renderer._page_width = config.pageX
    renderer._page_height = config.pageY

    start = arrow.get("20260101", "YYYYMMDD")
    end = arrow.get("20260331", "YYYYMMDD")
    axis_left = 60.0
    axis_right = 730.0
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
        axis_origin=(axis_left, axis_y),
        axis_length=axis_right - axis_left,
        orientation=Orientation.HORIZONTAL,
        side=Side.PRIMARY,
    )

    # Group by layer; same-layer x-intervals must not overlap.
    assert len(callouts) == len(point_events)
    by_layer: dict[int, list[tuple[float, float]]] = {}
    for c in callouts:
        by_layer.setdefault(c.lane, []).append(
            (c.box_x, c.box_x + c.box_width)
        )
    for layer, intervals in by_layer.items():
        intervals.sort()
        for (a_lo, a_hi), (b_lo, b_hi) in zip(intervals, intervals[1:]):
            assert a_hi <= b_lo + 1e-6, (
                f"Layer {layer}: [{a_lo:.2f},{a_hi:.2f}] "
                f"overlaps [{b_lo:.2f},{b_hi:.2f}]"
            )


@pytest.mark.parametrize(
    ("orientation", "side"),
    [
        (Orientation.HORIZONTAL, Side.PRIMARY),
        (Orientation.HORIZONTAL, Side.SECONDARY),
        (Orientation.HORIZONTAL, Side.BOTH),
        (Orientation.VERTICAL, Side.PRIMARY),
        (Orientation.VERTICAL, Side.SECONDARY),
        (Orientation.VERTICAL, Side.BOTH),
    ],
)
def test_timeline_layout_callouts_produces_callouts_for_each_orientation_side(
    tmp_path, orientation, side
):
    """Every orientation × side combo returns one callout per event,
    each carrying both the dot position and a non-empty leader path."""
    config = _base_config(tmp_path / f"timeline_{orientation.value}_{side.value}.svg")
    config.timeline_orientation = orientation.value
    config.timeline_label_side = side.value
    renderer = TimelineRenderer()
    renderer._page_width = config.pageX
    renderer._page_height = config.pageY

    start = arrow.get("20260201", "YYYYMMDD")
    end = arrow.get("20260331", "YYYYMMDD")
    events = [
        Event(task_name=f"E{i}", start=f"202602{10+i:02d}", end=f"202602{10+i:02d}")
        for i in range(8)
    ]
    callouts = renderer._layout_callouts(
        config,
        events,
        start,
        end,
        axis_origin=(50.0, 200.0),
        axis_length=500.0,
        orientation=orientation,
        side=side,
    )
    assert len(callouts) == len(events)
    for c in callouts:
        assert c.leader_path_d.startswith("M ")
        assert " C " in c.leader_path_d
        assert c.orientation is orientation


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
    expected_min = renderer._min_duration_offset(config, date_size)
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
        x_dot=200.0,
        y_dot=300.0,
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


def test_timeline_callout_date_is_drawn_inside_its_own_box(tmp_path):
    """The date belongs to its callout, not to a band near the axis.

    It used to be drawn at the event's dot, staggered over a fixed number of
    rows by source index: nowhere near its own box, free to collide with a
    neighbour's date, and landing on top of any box in the innermost layer.
    """
    config = _base_config(tmp_path / "timeline_callout_date_rows.svg")
    config.timeline_date_format = "YYYYMMDD"
    renderer = _CaptureTimelineRenderer()

    callout_a = TimelineCallout(
        event=Event(task_name="A", start="20260110", end="20260110"),
        color="gold",
        x_dot=200.0,
        y_dot=300.0,
        lane=0,
        box_x=150.0,
        box_y=230.0,
        box_width=120.0,
        box_height=70.0,
    )
    callout_b = TimelineCallout(
        event=Event(task_name="B", start="20260111", end="20260111"),
        color="gold",
        x_dot=205.0,
        y_dot=300.0,
        lane=0,
        box_x=400.0,
        box_y=220.0,
        box_width=120.0,
        box_height=70.0,
    )
    renderer._draw_callout(config, callout_a, axis_y=300.0)
    renderer._draw_callout(config, callout_b, axis_y=300.0)

    date_a = [c for c in renderer.text_calls if c["text"] == "20260110"]
    date_b = [c for c in renderer.text_calls if c["text"] == "20260111"]
    assert date_a and date_b

    for date, callout in ((date_a[0], callout_a), (date_b[0], callout_b)):
        # Right-aligned on the title line, so the anchor sits at the box's
        # right edge and the baseline within its vertical span.
        assert callout.box_x < date["x"] <= callout.box_x + callout.box_width
        assert callout.box_y <= date["y"] <= callout.box_y + callout.box_height

    # Each date tracks its own box rather than a shared row near the axis.
    assert date_a[0]["x"] != date_b[0]["x"]


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
        axis_origin=(60.0, 400.0),
        axis_length=670.0,
        orientation=Orientation.HORIZONTAL,
        side=Side.PRIMARY,
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
        x_dot=200.0,
        y_dot=300.0,
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
        axis_origin=(axis_left, axis_y),
        axis_length=axis_right - axis_left,
        orientation=Orientation.HORIZONTAL,
        side=Side.PRIMARY,
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


# ── Axis tick labels vs the innermost callout row ──────────────────────────
#
# Month labels are drawn above the axis, and the innermost row of callout
# boxes sits exactly one layer gap above it.  With the theme's gap alone
# (8pt by default) the labels printed inside those boxes.


def test_axis_label_clearance_covers_the_tick_furniture(tmp_path):
    config = _base_config(tmp_path / "clearance.svg")
    renderer = TimelineRenderer()
    start = arrow.get("20260401", "YYYYMMDD")
    end = arrow.get("20260731", "YYYYMMDD")

    clearance = renderer._axis_label_clearance(config, start, end)
    tick_h = renderer._axis_tick_height(config)
    label_size = renderer._axis_tick_label_size(config)

    # Must clear the tick mark plus the label's baseline offset and ascent.
    assert clearance > tick_h + label_size * 1.5
    assert clearance > config.timeline_labella_layer_gap


def test_no_clearance_reserved_when_labels_are_suppressed(tmp_path):
    """Past 18 month ticks _draw_month_ticks draws no labels at all."""
    config = _base_config(tmp_path / "clearance_none.svg")
    renderer = TimelineRenderer()
    clearance = renderer._axis_label_clearance(
        config,
        arrow.get("20200101", "YYYYMMDD"),
        arrow.get("20260101", "YYYYMMDD"),
    )
    assert clearance == 0.0


def test_the_innermost_callout_row_clears_the_axis_labels(tmp_path):
    """End to end: the gap the boxes get is the clearance, not the theme gap."""
    config = _base_config(tmp_path / "clearance_layout.svg")
    renderer = TimelineRenderer()
    renderer._page_width, renderer._page_height = config.pageX, config.pageY

    start = arrow.get("20260401", "YYYYMMDD")
    end = arrow.get("20260731", "YYYYMMDD")
    axis_y = 400.0
    callouts = renderer._layout_callouts(
        config,
        [
            Event(task_name="Alpha", start="20260405", end="20260405"),
            Event(task_name="Beta", start="20260620", end="20260620"),
        ],
        start,
        end,
        axis_origin=(60.0, axis_y),
        axis_length=670.0,
        orientation=Orientation.HORIZONTAL,
        side=Side.PRIMARY,
    )
    assert callouts
    clearance = renderer._axis_label_clearance(config, start, end)
    innermost_bottom = max(c.box_y + c.box_height for c in callouts)
    assert axis_y - innermost_bottom >= clearance - 0.01


class _HolidayDB(_DummyDB):
    """Minimal DB stub: every listed daykey is a nonworkday with an icon."""

    def __init__(self, daykeys: list[str]):
        self._daykeys = set(daykeys)

    def get_holidays_for_date(self, daykey, country=None):
        if daykey not in self._daykeys:
            return []
        return [{"displayname": "Holiday", "icon": "flag-us", "nonworkday": True}]


class _CaptureHolidayRenderer(_CaptureTimelineRenderer):
    def __init__(self):
        super().__init__()
        self.icon_calls: list[dict] = []

    def _draw_icon_svg(self, icon_name, x, baseline_y, size, **kwargs):
        self.icon_calls.append(
            {"icon": icon_name, "x": x, "y": baseline_y, "size": size}
        )
        return True


def test_timeline_prints_the_date_under_each_holiday_icon(tmp_path):
    config = _base_config(tmp_path / "holiday_dates.svg")
    config.country = "US"
    renderer = _CaptureHolidayRenderer()
    renderer._page_width, renderer._page_height = config.pageX, config.pageY

    start = arrow.get("20260101", "YYYYMMDD")
    end = arrow.get("20260630", "YYYYMMDD")
    renderer._draw_holiday_icons(
        config, start, end, 60.0, 730.0, 400.0, _HolidayDB(["20260119", "20260525"])
    )

    assert [c["icon"] for c in renderer.icon_calls] == ["flag-us", "flag-us"]
    dates = [c for c in renderer.text_calls if c["text"] in ("Jan 19", "May 25")]
    assert [d["text"] for d in dates] == ["Jan 19", "May 25"]
    # Each date is centered on its own icon and sits below it.
    for icon, date in zip(renderer.icon_calls, dates):
        assert date["x"] == pytest.approx(icon["x"])
        assert date["y"] > icon["y"]


def test_timeline_holiday_dates_stagger_instead_of_colliding(tmp_path):
    """Back-to-back holidays get their own row rather than one smeared label."""
    config = _base_config(tmp_path / "holiday_stagger.svg")
    config.country = "US"
    renderer = _CaptureHolidayRenderer()
    renderer._page_width, renderer._page_height = config.pageX, config.pageY

    start = arrow.get("20260101", "YYYYMMDD")
    end = arrow.get("20261231", "YYYYMMDD")
    renderer._draw_holiday_icons(
        config, start, end, 60.0, 730.0, 400.0, _HolidayDB(["20260703", "20260704"])
    )

    dates = [c for c in renderer.text_calls if c["text"] in ("Jul 3", "Jul 4")]
    assert len(dates) == 2
    assert dates[0]["y"] < dates[1]["y"]


def test_timeline_holiday_dates_can_be_switched_off(tmp_path):
    config = _base_config(tmp_path / "holiday_no_dates.svg")
    config.country = "US"
    config.timeline_show_holiday_dates = False
    renderer = _CaptureHolidayRenderer()
    renderer._page_width, renderer._page_height = config.pageX, config.pageY

    start = arrow.get("20260101", "YYYYMMDD")
    end = arrow.get("20260630", "YYYYMMDD")
    renderer._draw_holiday_icons(
        config, start, end, 60.0, 730.0, 400.0, _HolidayDB(["20260119"])
    )

    assert len(renderer.icon_calls) == 1
    assert not [c for c in renderer.text_calls if c["text"] == "Jan 19"]


def test_duration_bars_clear_the_holiday_date_band(tmp_path):
    """The date row under the axis must not end up beneath a duration bar."""
    config = _base_config(tmp_path / "holiday_clearance.svg")
    renderer = TimelineRenderer()
    _, _, date_size, _ = renderer._duration_metrics(config)

    with_dates = renderer._min_duration_offset(config, date_size)
    config.timeline_show_holiday_dates = False
    without_dates = renderer._min_duration_offset(config, date_size)

    assert with_dates >= renderer._holiday_band_extent(config)
    assert with_dates > without_dates


# ── Callout box text geometry ─────────────────────────────────────────────
#
# The fitter and the drawing pass used to carry separate formulas: the fitter
# allowed 1.2*title + 1.2*notes + 2, the renderer drew the notes baseline at
# 1.15*title + 1.55*notes and reserved nothing for descenders. A box the
# fitter called a fit still hung the notes' descenders below its bottom edge.


def _ink_bottom(renderer, config, box_height, box_width, title, notes,
                date_reserved=0.0):
    """Return (box_height, lowest inked y) for one callout's text block."""
    title_size, notes_size, _ = renderer._callout_metrics(config)
    title_path = renderer._safe_font_path(config.timeline_name_text_font_name)
    notes_path = renderer._safe_font_path(config.timeline_notes_text_font_name)
    fitted_title, fitted_notes = renderer._fit_box_text_sizes(
        title, notes,
        box_width - 12.0 - date_reserved, box_height,
        title_path, notes_path, title_size, notes_size,
        notes_width=box_width - 12.0,
        height_for=lambda ts, ns, has: renderer._callout_text_geometry(
            box_height, ts, ns, title_path, notes_path, has
        )[2],
    )
    _title_dy, notes_dy, _ = renderer._callout_text_geometry(
        box_height, fitted_title, fitted_notes, title_path, notes_path, True
    )
    descent = get_ink_extents(notes_path)[1] * fitted_notes
    return notes_dy + descent, fitted_notes


@pytest.mark.parametrize(
    "notes",
    [
        "Public launch announcement",          # has a descender
        "jjggppqqyy",                          # nothing but descenders
        "ok",                                  # short enough not to shrink
        "Retrospective and benefits handoff",  # long enough to shrink
    ],
)
def test_callout_notes_descenders_stay_inside_the_box(tmp_path, notes):
    config = _base_config(tmp_path / "callout_descender.svg")
    renderer = TimelineRenderer()
    bottom, _ = _ink_bottom(renderer, config, 24.0, 170.0, "Go-Live Event", notes)
    assert bottom <= 24.0


def test_callout_text_block_is_centred_in_the_box(tmp_path):
    """Slack is shared top and bottom, not dumped below the last line."""
    config = _base_config(tmp_path / "callout_centre.svg")
    renderer = TimelineRenderer()
    title_path = renderer._safe_font_path(config.timeline_name_text_font_name)
    notes_path = renderer._safe_font_path(config.timeline_notes_text_font_name)

    title_dy, notes_dy, required = renderer._callout_text_geometry(
        40.0, 10.0, 8.0, title_path, notes_path, True
    )
    above = title_dy - get_ink_extents(title_path)[0] * 10.0
    below = 40.0 - (notes_dy + get_ink_extents(notes_path)[1] * 8.0)
    assert above == pytest.approx(below, abs=0.01)
    assert required < 40.0


def test_the_fitter_and_the_renderer_agree_on_height(tmp_path):
    """The height the fitter checks is the height the drawn block occupies."""
    config = _base_config(tmp_path / "callout_agree.svg")
    renderer = TimelineRenderer()
    title_path = renderer._safe_font_path(config.timeline_name_text_font_name)
    notes_path = renderer._safe_font_path(config.timeline_notes_text_font_name)

    box_height = 18.0
    title_dy, notes_dy, required = renderer._callout_text_geometry(
        box_height, 10.0, 8.0, title_path, notes_path, True
    )
    drawn_top = title_dy - get_ink_extents(title_path)[0] * 10.0
    drawn_bottom = notes_dy + get_ink_extents(notes_path)[1] * 8.0
    assert required == pytest.approx(drawn_bottom - drawn_top + 3.0, abs=0.01)


def test_notes_are_measured_against_the_whole_inner_box(tmp_path):
    """The date rides the title line, so it must not shrink the notes."""
    config = _base_config(tmp_path / "callout_notes_width.svg")
    renderer = TimelineRenderer()
    notes = "Retrospective and benefits handoff"

    # A wide date reservation on the title line...
    _bottom, with_date = _ink_bottom(
        renderer, config, 24.0, 170.0, "Go-Live", notes, date_reserved=40.0
    )
    # ...must leave the notes at the size they get with no date at all.
    _bottom, without_date = _ink_bottom(
        renderer, config, 24.0, 170.0, "Go-Live", notes, date_reserved=0.0
    )
    assert with_date == pytest.approx(without_date)


def test_a_callout_without_notes_still_places_its_title(tmp_path):
    config = _base_config(tmp_path / "callout_no_notes.svg")
    renderer = TimelineRenderer()
    title_path = renderer._safe_font_path(config.timeline_name_text_font_name)
    notes_path = renderer._safe_font_path(config.timeline_notes_text_font_name)

    title_dy, notes_dy, required = renderer._callout_text_geometry(
        24.0, 10.0, 8.0, title_path, notes_path, False
    )
    assert title_dy == pytest.approx(notes_dy)
    assert title_dy - get_ink_extents(title_path)[0] * 10.0 >= 0.0
    assert required < 24.0


# ── Duration bar connectors ───────────────────────────────────────────────
#
# A bar is widened to whatever its name and notes need (_layout_durations),
# so on a short event the right edge lands on a date the event does not end
# on. Both edges used to get a leader up to the axis, and the one at the
# right edge pointed confidently at the wrong day.


def _duration_connector_xs(config, event, *, axis_left=60.0, axis_right=730.0):
    renderer = _CaptureTimelineRenderer()
    renderer._page_width, renderer._page_height = config.pageX, config.pageY
    start = arrow.get("20260101", "YYYYMMDD")
    end = arrow.get("20260630", "YYYYMMDD")
    laid_out = renderer._layout_durations(
        config, [event], start, end, axis_left, axis_right, 300.0
    )
    renderer._draw_duration_connectors(config, laid_out[0], axis_y=300.0)
    return laid_out[0], [c["x1"] for c in renderer.line_calls]


def test_a_duration_bar_gets_one_connector_at_its_start(tmp_path):
    config = _base_config(tmp_path / "duration_connector.svg")
    event = Event(task_name="Short", start="20260210", end="20260212")

    item, xs = _duration_connector_xs(config, event)
    assert xs == [item.start_x]


def test_no_connector_is_drawn_at_the_padded_end_of_a_bar(tmp_path):
    """The regression: a stretched bar's right edge is not its end date."""
    config = _base_config(tmp_path / "duration_padded.svg")
    # One day long, but a name far too wide for one day's worth of axis.
    event = Event(
        task_name="A name much wider than a single day of this axis",
        start="20260210",
        end="20260210",
    )

    item, xs = _duration_connector_xs(config, event)
    # The bar really was padded, so the two edges disagree...
    assert item.end_x > item.start_x
    # ...and only the honest edge carries a leader.
    assert xs == [item.start_x]
    assert item.end_x not in xs


def test_vertical_durations_also_only_connect_at_the_start(tmp_path):
    config = _base_config(tmp_path / "duration_vertical.svg")
    config.timeline_orientation = "vertical"
    renderer = _CaptureTimelineRenderer()
    renderer._page_width, renderer._page_height = config.pageX, config.pageY

    item = TimelineDuration(
        event=Event(task_name="Short", start="20260210", end="20260212"),
        color="gold",
        start_x=0.0,
        end_x=0.0,
        lane=0,
        start_y=200.0,
        end_y=260.0,
        min_width=0.0,
        orientation=Orientation.VERTICAL,
        lane_side=Side.PRIMARY,
    )
    renderer._draw_duration_connectors_vertical(config, item, axis_x=100.0)

    assert [c["y1"] for c in renderer.line_calls] == [item.start_y]


# ── Duration bars grouped by WBS ──────────────────────────────────────────
#
# Bars used to run in date order with the palette cycling per bar, so two
# tasks in the same phase looked no more related than two picked at random.
# They now sort by WBS group and every bar in a group takes one color.


def _dur(name, start, end, wbs=None):
    return Event(task_name=name, start=start, end=end, wbs=wbs)


def _grouped_bars(config, events):
    renderer = _CaptureTimelineRenderer()
    renderer._page_width, renderer._page_height = config.pageX, config.pageY
    return renderer._layout_durations(
        config,
        events,
        arrow.get("20260101", "YYYYMMDD"),
        arrow.get("20260630", "YYYYMMDD"),
        50.0,
        700.0,
        300.0,
    )


def _phase_events():
    return [
        _dur("B build 1", "20260302", "20260306", "NP.2.1"),
        _dur("A plan 1", "20260202", "20260206", "NP.1.1"),
        _dur("B build 2", "20260309", "20260313", "NP.2.S4.7"),
        _dur("A plan 2", "20260209", "20260213", "NP.1.2"),
        _dur("C ship", "20260401", "20260403", "NP.3"),
    ]


def test_bars_sharing_a_wbs_group_share_a_color(tmp_path):
    config = _base_config(tmp_path / "wbs_color.svg")
    config.timeline_wbs_group_depth = 2
    bars = _grouped_bars(config, _phase_events())

    by_group: dict[str, set[str]] = {}
    for bar in bars:
        by_group.setdefault(wbs_group(bar.event.wbs, 2), set()).add(bar.color)
    assert by_group  # sanity: bars were laid out
    for group, colors in by_group.items():
        assert len(colors) == 1, f"{group} drew in {sorted(colors)}"


def test_different_wbs_groups_get_different_colors(tmp_path):
    config = _base_config(tmp_path / "wbs_distinct.svg")
    config.timeline_wbs_group_depth = 2
    config.timeline_bottom_colors = ["red", "green", "blue", "gold"]
    bars = _grouped_bars(config, _phase_events())

    per_group = {wbs_group(b.event.wbs, 2): b.color for b in bars}
    assert len(per_group) == 3          # NP.1, NP.2, NP.3
    assert len(set(per_group.values())) == 3


def test_bars_are_ordered_so_each_group_is_contiguous(tmp_path):
    config = _base_config(tmp_path / "wbs_order.svg")
    config.timeline_wbs_group_depth = 2
    bars = _grouped_bars(config, _phase_events())

    groups = [wbs_group(b.event.wbs, 2) for b in bars]
    runs = [g for i, g in enumerate(groups) if i == 0 or groups[i - 1] != g]
    assert runs == sorted(set(groups)), "a group was split by another group"
    # WBS order, not the input order (which led with NP.2).
    assert runs == ["NP.1", "NP.2", "NP.3"]


def test_deeper_codes_fold_into_their_group(tmp_path):
    """NP.2.S4.7 belongs with NP.2.1 at depth 2, not in a group of its own."""
    config = _base_config(tmp_path / "wbs_fold.svg")
    config.timeline_wbs_group_depth = 2
    bars = _grouped_bars(config, _phase_events())

    colors = {
        b.event.task_name: b.color
        for b in bars
        if b.event.task_name in ("B build 1", "B build 2")
    }
    assert len(colors) == 2
    assert len(set(colors.values())) == 1


def test_bars_without_a_wbs_form_a_block_after_the_numbered_ones(tmp_path):
    config = _base_config(tmp_path / "wbs_none.svg")
    config.timeline_wbs_group_depth = 2
    events = _phase_events() + [
        _dur("Loose 1", "20260210", "20260214"),
        _dur("Loose 2", "20260220", "20260224"),
    ]
    bars = _grouped_bars(config, events)

    named = [bool(b.event.wbs) for b in bars]
    # Every WBS bar precedes every unnumbered one.
    assert named == sorted(named, reverse=True)
    loose = {b.color for b in bars if not b.event.wbs}
    assert len(loose) == 1


def test_group_depth_zero_restores_date_order_and_per_bar_colors(tmp_path):
    config = _base_config(tmp_path / "wbs_off.svg")
    config.timeline_wbs_group_depth = 0
    config.timeline_bottom_colors = ["red", "green", "blue", "gold"]
    bars = _grouped_bars(config, _phase_events())

    starts = [b.event.start for b in bars]
    assert starts == sorted(starts)
    # Consecutive bars cycle rather than sharing a group color.
    assert bars[0].color != bars[1].color


def test_vertical_duration_bars_group_by_wbs_too(tmp_path):
    config = _base_config(tmp_path / "wbs_vertical.svg")
    config.timeline_wbs_group_depth = 2
    config.timeline_orientation = "vertical"
    renderer = _CaptureTimelineRenderer()
    renderer._page_width, renderer._page_height = config.pageX, config.pageY

    bars = renderer._layout_durations_vertical(
        config,
        _phase_events(),
        arrow.get("20260101", "YYYYMMDD"),
        arrow.get("20260630", "YYYYMMDD"),
        axis_x=200.0,
        axis_top=50.0,
        axis_bottom=700.0,
        side=Side.PRIMARY,
    )
    by_group: dict[str, set[str]] = {}
    for bar in bars:
        by_group.setdefault(wbs_group(bar.event.wbs, 2), set()).add(bar.color)
    assert by_group
    for colors in by_group.values():
        assert len(colors) == 1


@pytest.mark.parametrize(
    "wbs, depth, expected",
    [
        ("NP.3.S1.4", 2, "NP.3"),
        ("NP.3.S1.4", 3, "NP.3.S1"),
        ("NP", 2, "NP"),          # shorter than the depth → its own group
        (None, 2, ""),            # no WBS → the unnumbered block
        ("", 2, ""),
        ("NP.1", 0, ""),          # depth 0 → grouping off
    ],
)
def test_wbs_group_prefixes(wbs, depth, expected):
    assert wbs_group(wbs, depth) == expected


# ── Duration bars that run out of room ────────────────────────────────────
#
# A fixed page can hold fewer duration lanes than the layout produces. The
# bars past the bottom used to be drawn anyway, off the paper, leaving their
# leaders running down to nothing. Now the leader stops at the edge and ends
# in the theme's default_missing_icon, and the bar is not drawn at all.


class _CaptureOverflowRenderer(_CaptureTimelineRenderer):
    def __init__(self):
        super().__init__()
        self.icon_calls: list[dict] = []

    def _draw_icon_svg(self, icon_name, x, baseline_y, size, **kwargs):
        self.icon_calls.append(
            {"icon": icon_name, "x": x, "y": baseline_y, "size": size, **kwargs}
        )
        return True


def _overflow_setup(tmp_path, name, lanes=6):
    """A config plus `lanes` durations that each need their own lane."""
    config = _base_config(tmp_path / name)
    config.default_missing_icon = "missing-box"
    events = [
        Event(
            task_name=f"Task {i}",
            start=f"202601{10 + i:02d}",
            end=f"202601{12 + i:02d}",
            wbs=f"1.{i}",
        )
        for i in range(lanes)
    ]
    return config, events


def _lay_out(config, events, axis_y=300.0):
    renderer = _CaptureOverflowRenderer()
    renderer._page_width, renderer._page_height = config.pageX, config.pageY
    bars = renderer._layout_durations(
        config,
        events,
        arrow.get("20260101", "YYYYMMDD"),
        arrow.get("20260630", "YYYYMMDD"),
        50.0,
        700.0,
        axis_y,
    )
    return renderer, bars


def test_a_bar_past_the_limit_is_not_drawn(tmp_path):
    config, events = _overflow_setup(tmp_path, "ovf_bar.svg")
    renderer, bars = _lay_out(config, events)
    deep = max(bars, key=lambda b: b.lane)
    bar_y, _bar_h = renderer._duration_bar_y(config, deep, 300.0)

    renderer.rect_calls.clear()
    renderer._draw_duration(config, deep, 300.0, limit=bar_y - 1.0)
    assert renderer.rect_calls == []

    # Same bar, room to spare: it draws.
    renderer._draw_duration(config, deep, 300.0, limit=bar_y + 10_000.0)
    assert renderer.rect_calls


def test_the_leader_stops_at_the_limit_and_marks_the_missing_box(tmp_path):
    config, events = _overflow_setup(tmp_path, "ovf_leader.svg")
    renderer, bars = _lay_out(config, events)
    deep = max(bars, key=lambda b: b.lane)
    bar_y, _bar_h = renderer._duration_bar_y(config, deep, 300.0)
    limit = bar_y - 1.0

    renderer._draw_duration_connectors(config, deep, 300.0, limit=limit)

    assert len(renderer.line_calls) == 1
    end_y = renderer.line_calls[0]["y2"]
    assert end_y < bar_y                 # pulled back from the missing bar
    assert end_y <= limit                # and inside the drawable area

    assert len(renderer.icon_calls) == 1
    icon = renderer.icon_calls[0]
    assert icon["icon"] == "missing-box"
    assert icon["x"] == pytest.approx(deep.start_x)


def test_a_bar_that_fits_gets_no_missing_marker(tmp_path):
    config, events = _overflow_setup(tmp_path, "ovf_fits.svg")
    renderer, bars = _lay_out(config, events)
    shallow = min(bars, key=lambda b: b.lane)
    bar_y, _bar_h = renderer._duration_bar_y(config, shallow, 300.0)

    renderer._draw_duration_connectors(config, shallow, 300.0, limit=bar_y + 10_000.0)
    assert renderer.icon_calls == []
    assert renderer.line_calls[0]["y2"] == pytest.approx(bar_y)


def test_no_limit_draws_every_bar(tmp_path):
    """--shrink grows the page instead, so nothing is held back."""
    config, events = _overflow_setup(tmp_path, "ovf_none.svg")
    renderer, bars = _lay_out(config, events)
    renderer.rect_calls.clear()
    for bar in bars:
        renderer._draw_duration(config, bar, 300.0, limit=None)
    # One bar rect each, and no leader was cut short.
    assert len(renderer.rect_calls) == len(bars)
    assert renderer.icon_calls == []


def test_a_theme_without_a_missing_icon_still_clamps_the_leader(tmp_path):
    config, events = _overflow_setup(tmp_path, "ovf_noicon.svg")
    config.default_missing_icon = None
    renderer, bars = _lay_out(config, events)
    deep = max(bars, key=lambda b: b.lane)
    bar_y, _bar_h = renderer._duration_bar_y(config, deep, 300.0)

    renderer._draw_duration_connectors(config, deep, 300.0, limit=bar_y - 1.0)
    assert renderer.icon_calls == []
    assert renderer.line_calls[0]["y2"] < bar_y


def test_a_duration_row_is_just_its_bar(tmp_path):
    """The dates ride inside the bar, so no band is reserved beneath it."""
    config, _events = _overflow_setup(tmp_path, "ovf_dates.svg")
    renderer = _CaptureOverflowRenderer()
    _t, _n, _date_size, bar_h = renderer._duration_metrics(config)
    assert renderer._duration_row_extent(config) == pytest.approx(bar_h)


# ── Start / end dates inside the duration bar ─────────────────────────────
#
# The dates used to sit in a band below the bar, which cost every row an
# extra 2.1 date-heights of vertical space. They now ride inside the bar's
# two ends, on the title's baseline.


def _drawn_duration(tmp_path, name, event, axis_y=300.0):
    config = _base_config(tmp_path / name)
    renderer = _CaptureOverflowRenderer()
    renderer._page_width, renderer._page_height = config.pageX, config.pageY
    bars = renderer._layout_durations(
        config,
        [event],
        arrow.get("20260101", "YYYYMMDD"),
        arrow.get("20260630", "YYYYMMDD"),
        50.0,
        700.0,
        axis_y,
    )
    renderer._draw_duration(config, bars[0], axis_y)
    return config, renderer, bars[0]


def _date_texts(renderer):
    return [c for c in renderer.text_calls if c.get("css_class") == "ec-duration-date"]


def test_the_start_and_end_dates_are_drawn_inside_the_bar(tmp_path):
    event = Event(task_name="Build", start="20260210", end="20260320")
    config, renderer, bar = _drawn_duration(tmp_path, "in_bar.svg", event)
    bar_y, bar_h = renderer._duration_bar_y(config, bar, 300.0)

    dates = _date_texts(renderer)
    assert len(dates) == 2
    for date in dates:
        assert bar.start_x <= date["x"] <= bar.end_x
        assert bar_y <= date["y"] <= bar_y + bar_h


def test_the_start_date_sits_at_the_left_end_and_the_end_date_at_the_right(tmp_path):
    event = Event(task_name="Build", start="20260210", end="20260320")
    config, renderer, bar = _drawn_duration(tmp_path, "in_bar_ends.svg", event)

    start_date, end_date = _date_texts(renderer)
    assert start_date["anchor"] == "start"
    assert end_date["anchor"] == "end"
    assert start_date["x"] == pytest.approx(bar.start_x + 3.0)
    assert end_date["x"] == pytest.approx(bar.end_x - 3.0)
    # Both on one baseline, which is the title's.
    assert start_date["y"] == pytest.approx(end_date["y"])
    titles = [c for c in renderer.text_calls if c.get("css_class") == "ec-event-name"]
    assert titles and titles[0]["y"] == pytest.approx(start_date["y"])


def test_a_bar_is_widened_to_hold_its_dates_and_its_title(tmp_path):
    """A one-day event still has to fit both dates plus its name."""
    config = _base_config(tmp_path / "in_bar_width.svg")
    renderer = _CaptureOverflowRenderer()
    renderer._page_width, renderer._page_height = config.pageX, config.pageY
    bars = renderer._layout_durations(
        config,
        [Event(task_name="Ship", start="20260210", end="20260210")],
        arrow.get("20260101", "YYYYMMDD"),
        arrow.get("20260630", "YYYYMMDD"),
        50.0,
        700.0,
        300.0,
    )
    bar = bars[0]
    _t, _n, date_size, _bar_h = renderer._duration_metrics(config)
    date_font = renderer._safe_font_path(config.timeline_date_font)
    needed = renderer._duration_dates_width("Feb 10", "Feb 10", date_font, date_size)
    assert bar.end_x - bar.start_x >= needed


def test_the_row_no_longer_reserves_a_band_under_the_bar(tmp_path):
    """Reclaiming that band is what lets the lanes pack tighter."""
    config = _base_config(tmp_path / "in_bar_stride.svg")
    renderer = _CaptureOverflowRenderer()
    renderer._page_width, renderer._page_height = config.pageX, config.pageY
    events = [
        Event(task_name=f"T{i}", start="20260210", end="20260320", wbs=f"1.{i}")
        for i in range(3)
    ]
    bars = renderer._layout_durations(
        config, events,
        arrow.get("20260101", "YYYYMMDD"), arrow.get("20260630", "YYYYMMDD"),
        50.0, 700.0, 300.0,
    )
    lanes = sorted({b.lane for b in bars})
    assert len(lanes) >= 2

    _t, _n, date_size, bar_h = renderer._duration_metrics(config)
    lane_gap = max(config.timeline_duration_lane_gap_y, date_size * 0.9)
    y0, _ = renderer._duration_bar_y(config, bars[0], 300.0)
    y1, _ = renderer._duration_bar_y(
        config, next(b for b in bars if b.lane == 1), 300.0
    )
    assert y1 - y0 == pytest.approx(bar_h + lane_gap)


def test_vertical_bars_carry_their_dates_inside_too(tmp_path):
    config = _base_config(tmp_path / "in_bar_vertical.svg")
    config.timeline_orientation = "vertical"
    renderer = _CaptureOverflowRenderer()
    renderer._page_width, renderer._page_height = config.pageX, config.pageY
    bars = renderer._layout_durations_vertical(
        config,
        [Event(task_name="Build", start="20260210", end="20260320")],
        arrow.get("20260101", "YYYYMMDD"),
        arrow.get("20260630", "YYYYMMDD"),
        axis_x=200.0,
        axis_top=50.0,
        axis_bottom=700.0,
        side=Side.PRIMARY,
    )
    renderer._draw_duration_vertical(config, bars[0], 200.0)

    dates = _date_texts(renderer)
    assert len(dates) == 2
    # Rotated with the label, and pulled in from each along-axis end.
    for date in dates:
        assert "rotate(-90" in (date.get("transform") or "")
    cx_values = {round(d["x"], 3) for d in dates}
    assert len(cx_values) == 2      # one toward each end, not stacked


# ── Callout box columns ───────────────────────────────────────────────────
#
# The box is two columns: the icon over the date on the left, the name over
# the notes on the right. The date used to be right-aligned on the title
# line and the notes started at the box edge under the icon, so the two text
# lines had different left edges.


def _callout(**overrides):
    kwargs = dict(
        event=Event(
            task_name="Go-Live Event",
            start="20260727",
            end="20260727",
            notes="Public launch announcement",
        ),
        color="gold",
        x_dot=200.0,
        y_dot=300.0,
        lane=0,
        box_x=150.0,
        box_y=230.0,
        box_width=200.0,
        box_height=30.0,
    )
    kwargs.update(overrides)
    return TimelineCallout(**kwargs)


def _drawn_callout(tmp_path, name, **overrides):
    config = _base_config(tmp_path / name)
    renderer = _CaptureOverflowRenderer()
    renderer._page_width, renderer._page_height = config.pageX, config.pageY
    # An icon only draws when it resolves, and no DB is loaded here.
    renderer._icon_svg_map = {"rocket": '<svg viewBox="0 0 24 24"><path d="M0 0h24v24H0z"/></svg>'}
    renderer._draw_callout(config, _callout(**overrides), axis_y=300.0)
    return config, renderer


def _by_class(renderer, css_class):
    return [c for c in renderer.text_calls if c.get("css_class") == css_class]


def test_the_notes_share_a_left_edge_with_the_name(tmp_path):
    _config, renderer = _drawn_callout(tmp_path, "callout_align.svg")
    name = _by_class(renderer, "ec-event-name")[0]
    notes = _by_class(renderer, "ec-event-notes")[0]
    assert notes["x"] == pytest.approx(name["x"])
    assert notes["y"] > name["y"]        # second line


def test_the_date_sits_under_the_icon_on_the_notes_line(tmp_path):
    _config, renderer = _drawn_callout(
        tmp_path, "callout_date.svg",
        event=Event(
            task_name="Go-Live Event", start="20260727", end="20260727",
            notes="Public launch announcement", icon="rocket",
        ),
    )
    date = _by_class(renderer, "ec-event-date")[0]
    notes = _by_class(renderer, "ec-event-notes")[0]
    assert renderer.icon_calls, "the fixture should draw an icon"
    icon = renderer.icon_calls[0]

    assert date["anchor"] == "start"
    assert date["x"] == pytest.approx(icon["x"])   # same column as the icon
    assert date["y"] == pytest.approx(notes["y"])  # the notes' line
    assert date["x"] < notes["x"]                  # left of the text column


def test_the_date_is_no_longer_on_the_title_line(tmp_path):
    _config, renderer = _drawn_callout(tmp_path, "callout_notline.svg")
    name = _by_class(renderer, "ec-event-name")[0]
    date = _by_class(renderer, "ec-event-date")[0]
    assert date["y"] != pytest.approx(name["y"])


def test_the_left_column_is_as_wide_as_its_widest_occupant(tmp_path):
    """A date wider than the icon widens the column, not the notes' indent."""
    config, renderer = _drawn_callout(
        tmp_path, "callout_col.svg",
        event=Event(
            task_name="Go-Live Event", start="20260727", end="20260727",
            notes="Public launch announcement", icon="rocket",
        ),
    )
    date = _by_class(renderer, "ec-event-date")[0]
    notes = _by_class(renderer, "ec-event-notes")[0]
    column = notes["x"] - date["x"]

    date_size = renderer._callout_metrics(config)[2]
    needed = renderer._callout_date_width(config, date["text"], date_size)
    assert column >= needed - 0.01


def test_a_callout_without_an_icon_still_lines_its_columns_up(tmp_path):
    _config, renderer = _drawn_callout(
        tmp_path, "callout_noicon.svg",
        event=Event(
            task_name="Go-Live Event", start="20260727", end="20260727",
            notes="Public launch announcement",
        ),
    )
    assert renderer.icon_calls == []
    name = _by_class(renderer, "ec-event-name")[0]
    notes = _by_class(renderer, "ec-event-notes")[0]
    date = _by_class(renderer, "ec-event-date")[0]
    assert name["x"] == pytest.approx(notes["x"])
    assert date["x"] < name["x"]


def test_the_overflow_marker_takes_the_configured_missing_icon_size(tmp_path):
    """The marker drawn where a duration bar ran out of room sizes with it."""
    config, events = _overflow_setup(tmp_path, "ovf_size.svg")
    renderer, bars = _lay_out(config, events)
    deep = max(bars, key=lambda b: b.lane)
    bar_y, bar_h = renderer._duration_bar_y(config, deep, 300.0)
    limit = bar_y - 1.0

    renderer._draw_duration_connectors(config, deep, 300.0, limit=limit)
    assert renderer.icon_calls[-1]["size"] == pytest.approx(bar_h)

    config.default_missing_icon_size = 21.0
    renderer._draw_duration_connectors(config, deep, 300.0, limit=limit)
    assert renderer.icon_calls[-1]["size"] == pytest.approx(21.0)


# ── One color per WBS group, chart-wide ───────────────────────────────────
#
# Callouts and duration bars are laid out separately and each used to cycle
# its own palette, so a phase's milestone and its bars were unrelated colors.
# The map is now built once over every item type.


def _mixed_wbs_events():
    """One point event, one milestone and one bar in each of two groups."""
    return [
        Event(task_name="A plan", start="20260202", end="20260220", wbs="1.1"),
        Event(task_name="A gate", start="20260223", end="20260223", wbs="1.2",
              milestone=True),
        Event(task_name="A note", start="20260225", end="20260225", wbs="1.3"),
        Event(task_name="B build", start="20260302", end="20260320", wbs="2.1"),
        Event(task_name="B gate", start="20260323", end="20260323", wbs="2.2",
              milestone=True),
        Event(task_name="B note", start="20260325", end="20260325", wbs="2.3"),
    ]


def test_every_item_type_in_a_group_takes_one_color(tmp_path):
    config = _base_config(tmp_path / "wbs_all.svg")
    config.timeline_wbs_group_depth = 1
    renderer = _CaptureOverflowRenderer()
    renderer._page_width, renderer._page_height = config.pageX, config.pageY
    events = _mixed_wbs_events()
    start = arrow.get("20260101", "YYYYMMDD")
    end = arrow.get("20260630", "YYYYMMDD")

    group_colors = renderer._wbs_group_colors(config, events)
    points, durations = renderer._split_events(config, events)
    assert points and durations, "the fixture should have both kinds"

    callouts = renderer._layout_callouts(
        config, points, start, end,
        axis_origin=(60.0, 300.0), axis_length=670.0,
        orientation=Orientation.HORIZONTAL, side=Side.PRIMARY,
        group_colors=group_colors,
    )
    bars = renderer._layout_durations(
        config, durations, start, end, 60.0, 730.0, 300.0,
        group_colors=group_colors,
    )

    by_group: dict[str, set[str]] = {}
    for item in list(callouts) + list(bars):
        by_group.setdefault(wbs_group(item.event.wbs, 1), set()).add(item.color)
    assert set(by_group) == {"1", "2"}
    for group, colors in by_group.items():
        assert len(colors) == 1, f"group {group} drew in {sorted(colors)}"
    # ...and the two groups are told apart.
    assert len({next(iter(c)) for c in by_group.values()}) == 2


def test_a_milestone_matches_the_bars_in_its_phase(tmp_path):
    config = _base_config(tmp_path / "wbs_ms.svg")
    config.timeline_wbs_group_depth = 1
    renderer = _CaptureOverflowRenderer()
    renderer._page_width, renderer._page_height = config.pageX, config.pageY
    events = _mixed_wbs_events()
    group_colors = renderer._wbs_group_colors(config, events)
    points, durations = renderer._split_events(config, events)

    callouts = renderer._layout_callouts(
        config, points,
        arrow.get("20260101", "YYYYMMDD"), arrow.get("20260630", "YYYYMMDD"),
        axis_origin=(60.0, 300.0), axis_length=670.0,
        orientation=Orientation.HORIZONTAL, side=Side.PRIMARY,
        group_colors=group_colors,
    )
    bars = renderer._layout_durations(
        config, durations,
        arrow.get("20260101", "YYYYMMDD"), arrow.get("20260630", "YYYYMMDD"),
        60.0, 730.0, 300.0, group_colors=group_colors,
    )
    milestone = next(c for c in callouts if c.event.task_name == "A gate")
    bar = next(b for b in bars if b.event.task_name == "A plan")
    assert milestone.color == bar.color


def test_the_secondary_palette_does_not_break_a_group_color(tmp_path):
    """Side.BOTH used to recolor the far side; a group has to survive that."""
    config = _base_config(tmp_path / "wbs_both.svg")
    config.timeline_wbs_group_depth = 1
    config.timeline_bottom_colors = ["magenta", "cyan"]
    renderer = _CaptureOverflowRenderer()
    renderer._page_width, renderer._page_height = config.pageX, config.pageY
    events = [e for e in _mixed_wbs_events() if e.start == e.end]

    group_colors = renderer._wbs_group_colors(config, events)
    callouts = renderer._layout_callouts(
        config, events,
        arrow.get("20260101", "YYYYMMDD"), arrow.get("20260630", "YYYYMMDD"),
        axis_origin=(60.0, 300.0), axis_length=670.0,
        orientation=Orientation.HORIZONTAL, side=Side.BOTH,
        group_colors=group_colors,
    )
    by_group: dict[str, set[str]] = {}
    for c in callouts:
        by_group.setdefault(wbs_group(c.event.wbs, 1), set()).add(c.color)
    for colors in by_group.values():
        assert len(colors) == 1
    assert not ({"magenta", "cyan"} & {c.color for c in callouts})


def test_grouping_off_leaves_each_layout_its_own_palette(tmp_path):
    config = _base_config(tmp_path / "wbs_off_all.svg")
    config.timeline_wbs_group_depth = 0
    renderer = _CaptureOverflowRenderer()
    assert renderer._wbs_group_colors(config, _mixed_wbs_events()) == {}


def test_the_group_palette_comes_from_the_top_colors(tmp_path):
    """One color per group means one palette; top_colors is it."""
    config = _base_config(tmp_path / "wbs_palette.svg")
    config.timeline_wbs_group_depth = 1
    config.timeline_top_colors = ["red", "green"]
    config.timeline_bottom_colors = ["magenta", "cyan"]
    renderer = _CaptureOverflowRenderer()

    colors = renderer._wbs_group_colors(config, _mixed_wbs_events())
    assert set(colors.values()) == {"red", "green"}


# ── Tick-label distance ───────────────────────────────────────────────────
#
# A `timeline.ticks` band could always place its labels with `label_gap` /
# `label_offset_y`. The built-in month ticks hard-coded the distance, so on a
# theme without a ticks band the only lever was `timeline.axis_width`, which
# resizes the tick marks too.


def test_the_tick_label_distance_defaults_to_the_old_formula(tmp_path):
    config = _base_config(tmp_path / "tick_default.svg")
    renderer = TimelineRenderer()
    tick_h = renderer._axis_tick_height(config)
    label_size = renderer._axis_tick_label_size(config)

    assert renderer._tick_label_offset(tick_h, label_size, None, None) == (
        pytest.approx(tick_h + label_size * 1.5)
    )


def test_a_gap_is_measured_from_the_tick_tip(tmp_path):
    """So it moves with tick_length rather than overlapping a long tick."""
    renderer = TimelineRenderer()
    assert renderer._tick_label_offset(8.0, 7.0, 20.0, None) == pytest.approx(28.0)
    assert renderer._tick_label_offset(2.0, 7.0, 20.0, None) == pytest.approx(22.0)


def test_an_offset_is_the_whole_distance_and_wins(tmp_path):
    renderer = TimelineRenderer()
    assert renderer._tick_label_offset(8.0, 7.0, 20.0, 40.0) == pytest.approx(40.0)
    assert renderer._tick_label_offset(8.0, 7.0, None, 40.0) == pytest.approx(40.0)


def test_the_built_in_ticks_read_the_theme_keys(tmp_path):
    config = _base_config(tmp_path / "tick_keys.svg")
    config.timeline_tick_label_gap = 20.0
    renderer = _CaptureTimelineRenderer()
    renderer._page_width, renderer._page_height = config.pageX, config.pageY

    renderer._draw_month_ticks(
        config,
        arrow.get("20260101", "YYYYMMDD"),
        arrow.get("20260430", "YYYYMMDD"),
        60.0, 700.0, 300.0,
    )
    labels = [c for c in renderer.text_calls if c.get("css_class") == "ec-label"]
    assert labels
    tick_h = renderer._axis_tick_height(config)
    assert labels[0]["y"] == pytest.approx(300.0 - (tick_h + 20.0))


def test_the_callout_clearance_follows_the_configured_gap(tmp_path):
    """A wider gap must push the innermost row of boxes out with it."""
    config = _base_config(tmp_path / "tick_clear.svg")
    renderer = TimelineRenderer()
    start = arrow.get("20260101", "YYYYMMDD")
    end = arrow.get("20260430", "YYYYMMDD")

    narrow = renderer._axis_label_clearance(config, start, end)
    config.timeline_tick_label_gap = 40.0
    wide = renderer._axis_label_clearance(config, start, end)
    assert wide > narrow
    assert wide - narrow == pytest.approx(
        40.0 - renderer._axis_tick_label_size(config) * 1.5
    )
