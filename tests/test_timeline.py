from __future__ import annotations

import itertools
import re
from pathlib import Path
from typing import Any

import arrow
import drawsvg
import pytest
from band_helpers import set_bands, set_fields, set_orientation, update_theme
from fakes import FakeCalendarDB

from config.config import create_calendar_config, setfontsizes
from renderers.text_utils import string_width
from shared.data_models import Event
from shared.orientation import Orientation, Side
from shared.rule_engine import StyleResult
from shared.span import Frame
from shared.wbs_filter import wbs_group
from visualizers.timeline.layout import TimelineLayout
from visualizers.timeline.renderer import (
    TimelineCallout,
    TimelineDuration,
    TimelineRenderer,
)

# The duration layout and drawing take an Frame; these build one.
_FRAME_D0 = arrow.get("20260101", "YYYYMMDD")
_FRAME_D1 = arrow.get("20261231", "YYYYMMDD")


def _hframe(start, end, left: float, right: float, axis_y: float) -> Frame:
    return Frame.over_range(Orientation.HORIZONTAL, start, end, left, right, axis_y)


def _vframe(start, end, top: float, bottom: float, axis_x: float) -> Frame:
    return Frame.over_range(Orientation.VERTICAL, start, end, top, bottom, axis_x)


def _haxis(axis_y: float) -> Frame:
    """A horizontal axis at ``axis_y``, for draw calls that only read the axis line."""
    return _hframe(_FRAME_D0, _FRAME_D1, 0.0, 1.0, axis_y)


def _vaxis(axis_x: float) -> Frame:
    return _vframe(_FRAME_D0, _FRAME_D1, 0.0, 1.0, axis_x)


def _bar_y(renderer, config, item, axis_y: float) -> tuple[float, float]:
    """``(top edge, height)`` of a bar below a horizontal axis at ``axis_y``."""
    near, thickness, _sign = renderer._duration_bar_across(config, item, _haxis(axis_y))
    return near, thickness


class _DummyDB(FakeCalendarDB):
    def get_palette(self, name):
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
                "x": x,
                "y": y,
                "text": text,
                "font": font_name,
                "size": font_size,
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

    def _draw_circle(
        self,
        cx,
        cy,
        radius,
        stroke="black",
        fill="none",
        stroke_width=1.0,
        stroke_opacity=None,
        css_class=None,
    ):
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
        self.text_calls.append({"x": x, "y": y, "text": text, "font": font_name, "size": font_size})


def _boxes_overlap(
    box_a: tuple[float, float, float, float], box_b: tuple[float, float, float, float], pad: float = 0.0
) -> bool:
    ax1, ay1, ax2, ay2 = box_a
    bx1, by1, bx2, by2 = box_b
    return not (ax2 + pad <= bx1 or bx2 + pad <= ax1 or ay2 + pad <= by1 or by2 + pad <= ay1)


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
    update_theme(config, boxes={"default": {"fill": "none"}})
    coords = TimelineLayout().calculate(config)

    renderer = TimelineRenderer()
    renderer.render(config, coords, events=[], db=_DummyDB())

    text = output.read_text(encoding="utf-8")
    assert f'<rect x="0" y="0" width="{config.pageX}" height="{config.pageY}"' not in text


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
    laid_out = renderer._layout_durations(config, durations, _hframe(start, end, axis_left, axis_right, axis_y))

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
    point_events = [Event(task_name=f"E{i}", start="20260215", end="20260215", priority=i) for i in range(6)]
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
        by_layer.setdefault(c.lane, []).append((c.box_x, c.box_x + c.box_width))
    for layer, intervals in by_layer.items():
        intervals.sort()
        for (a_lo, a_hi), (b_lo, b_hi) in itertools.pairwise(intervals):
            assert a_hi <= b_lo + 1e-6, f"Layer {layer}: [{a_lo:.2f},{a_hi:.2f}] overlaps [{b_lo:.2f},{b_hi:.2f}]"


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
def test_timeline_layout_callouts_produces_callouts_for_each_orientation_side(tmp_path, orientation, side):
    """Every orientation × side combo returns one callout per event,
    each carrying both the dot position and a non-empty leader path."""
    config = _base_config(tmp_path / f"timeline_{orientation.value}_{side.value}.svg")
    set_orientation(config, orientation.value)
    set_fields(config, timeline_label_side=side.value)
    renderer = TimelineRenderer()
    renderer._page_width = config.pageX
    renderer._page_height = config.pageY

    start = arrow.get("20260201", "YYYYMMDD")
    end = arrow.get("20260331", "YYYYMMDD")
    events = [Event(task_name=f"E{i}", start=f"202602{10 + i:02d}", end=f"202602{10 + i:02d}") for i in range(8)]
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
        assert c.orientation is orientation

    # The labella strategy is still selectable.
    set_fields(config, timeline_event_placement="labella")
    curved = renderer._layout_callouts(
        config,
        events,
        start,
        end,
        axis_origin=(50.0, 200.0),
        axis_length=500.0,
        orientation=orientation,
        side=side,
    )
    assert len(curved) == len(events)


def test_timeline_duration_dates_share_same_y_and_offset_is_configurable(tmp_path):
    config = _base_config(tmp_path / "timeline_spacing.svg")
    set_fields(config, timeline_duration_offset_y=140.0)
    set_fields(config, timeline_date_format="MMM D")

    renderer = _CaptureTimelineRenderer()
    renderer._page_width = config.pageX
    renderer._page_height = config.pageY

    start = arrow.get("20260101", "YYYYMMDD")
    end = arrow.get("20260331", "YYYYMMDD")
    durations = [Event(task_name="Duration A", start="20260110", end="20260210")]
    laid_out = renderer._layout_durations(config, durations, _hframe(start, end, 50.0, 700.0, 300.0))

    renderer._draw_duration(config, laid_out[0], _haxis(300.0))

    start_label = arrow.get("20260110", "YYYYMMDD").format("MMM D")
    end_label = arrow.get("20260210", "YYYYMMDD").format("MMM D")
    y_start = next(c["y"] for c in renderer.text_calls if c["text"] == start_label)
    y_end = next(c["y"] for c in renderer.text_calls if c["text"] == end_label)
    assert y_start == y_end

    # The duration bar is drawn as the first rect in _draw_duration.
    # In SVG coords bar["y"] is the top edge (smallest y), 140 below axis_y=300.
    bar = renderer.rect_calls[0]
    assert round(bar["y"] - 300.0, 2) == 140.0


def test_timeline_date_format_is_configurable(tmp_path):
    config = _base_config(tmp_path / "timeline_format.svg")
    set_fields(config, timeline_date_format="YYYY-MM-DD")

    renderer = _CaptureTimelineRenderer()
    renderer._page_width = config.pageX
    renderer._page_height = config.pageY

    start = arrow.get("20260101", "YYYYMMDD")
    end = arrow.get("20260331", "YYYYMMDD")
    durations = [Event(task_name="Duration A", start="20260110", end="20260210")]
    laid_out = renderer._layout_durations(config, durations, _hframe(start, end, 50.0, 700.0, 300.0))
    renderer._draw_duration(config, laid_out[0], _haxis(300.0))

    labels = {c["text"] for c in renderer.text_calls}
    assert "2026-01-10" in labels
    assert "2026-02-10" in labels


def test_timeline_marker_defaults_to_filled_circle_and_icon_uses_circle(tmp_path):
    config = _base_config(tmp_path / "timeline_marker.svg")
    set_fields(config, timeline_marker_radius=6.0)
    set_fields(config, timeline_icon_size=12.0)
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
    renderer._icon_svg_map = {"rocket": '<svg viewBox="0 0 24 24"><path d="M2 2h20v20H2z"/></svg>'}
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
    set_fields(config, timeline_name_text_font_size=15.0)
    set_fields(config, timeline_notes_text_font_size=11.0)
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
    set_fields(config, timeline_date_format="YYYYMMDD")
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

    for date_call, callout in ((date_a[0], callout_a), (date_b[0], callout_b)):
        # Right-aligned on the title line, so the anchor sits at the box's
        # right edge and the baseline within its vertical span.
        assert callout.box_x < date_call["x"] <= callout.box_x + callout.box_width
        assert callout.box_y <= date_call["y"] <= callout.box_y + callout.box_height

    # Each date tracks its own box rather than a shared row near the axis.
    assert date_a[0]["x"] != date_b[0]["x"]


def test_timeline_callout_uses_configured_event_box_width_and_height(tmp_path):
    config = _base_config(tmp_path / "timeline_callout_box.svg")
    set_fields(config, timeline_event_box_width=160.0)
    set_fields(config, timeline_event_box_height=72.0)
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
    set_fields(config, timeline_name_text_font_size=13.0)
    set_fields(config, timeline_notes_text_font_size=9.0)
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
    renderer._draw_duration(config, duration, _haxis(300.0))

    name = [c for c in renderer.text_calls if c["text"] == "Imaginary Sprint 4"]
    notes = [c for c in renderer.text_calls if c["text"] == "Execution window"]
    assert name and 0 < name[0]["size"] <= 13.0
    assert notes and 0 < notes[0]["size"] <= 9.0


def test_timeline_duration_uses_configured_box_height_and_text_width(tmp_path):
    """`box_width` is the width the text wants, not a width bars are grown to.

    Bar edges belong to the dates, so a configured width that the date span
    cannot supply makes the bar overflow rather than stretch.
    """
    config = _base_config(tmp_path / "timeline_duration_box.svg")
    set_fields(config, timeline_duration_box_height=34.0)
    set_fields(config, timeline_duration_box_width=140.0)
    renderer = TimelineRenderer()
    renderer._page_width = config.pageX
    renderer._page_height = config.pageY

    start = arrow.get("20260101", "YYYYMMDD")
    end = arrow.get("20260331", "YYYYMMDD")
    durations = [Event(task_name="A", start="20260110", end="20260110", notes="B")]
    laid_out = renderer._layout_durations(config, durations, _hframe(start, end, 60.0, 730.0, 300.0))
    assert len(laid_out) == 1
    assert laid_out[0].min_width == 140.0
    assert (laid_out[0].end_x - laid_out[0].start_x) < 140.0
    assert laid_out[0].text_overflow

    _, _, _, bar_h = renderer._duration_metrics(config)
    assert bar_h == 34.0


def test_timeline_shrinks_text_when_box_constraints_are_tight(tmp_path):
    config = _base_config(tmp_path / "timeline_shrink.svg")
    set_fields(config, timeline_name_text_font_size=18.0)
    set_fields(config, timeline_notes_text_font_size=14.0)
    set_fields(config, timeline_event_box_width=80.0)
    set_fields(config, timeline_event_box_height=30.0)
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
    axis_y = 240.0

    close_events = [Event(task_name=f"Event {i}", start="20260115", end="20260115", priority=i) for i in range(10)]
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

    boxes = [(c.box_x, c.box_y, c.box_x + c.box_width, c.box_y + c.box_height) for c in callouts]
    overlaps = 0
    for i in range(len(boxes)):
        for j in range(i + 1, len(boxes)):
            if _boxes_overlap(boxes[i], boxes[j], pad=2.0):
                overlaps += 1
    # On constrained pages, placement should strongly avoid collisions.
    assert overlaps <= 1


def test_the_timeline_draws_the_shared_today_line(tmp_path):
    output = tmp_path / "timeline_today.svg"
    config = _base_config(output)
    config.adjustedstart = config.userstart = "20260301"
    config.adjustedend = config.userend = "20260331"
    update_theme(config, today={"show": True, "date": "20260315", "label": "Reference Date"})
    coords = TimelineLayout().calculate(config)

    renderer = _CaptureTimelineRenderer()
    renderer.render(config, coords, [], _DummyDB())

    assert output.read_text().count('class="ec-today-line"') == 1
    assert "Reference Date" in [c["text"] for c in renderer.text_calls]


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
        self.icon_calls.append({"icon": icon_name, "x": x, "y": baseline_y, "size": size})
        return True


# ── Callout box cell geometry ──────────────────────────────────────────────
#
# A callout box is a 2x2 grid — the icon over the start date in a narrow
# leading column, the name over the notes in a wide one. Each line is sized
# and centred against its own cell, so a line can never reach into the cell
# below it, and the box is never stretched to hold its text.


def _cell_ink(renderer, config, cell_top, cell_h, font_name, size):
    """Return (top, bottom) of the ink one line puts in its cell."""
    path = renderer._safe_font_path(font_name)
    fitted = renderer._cell_font_size(cell_h, path, size)
    baseline = renderer._cell_baseline(cell_top, cell_h, path, fitted)
    ascent, descent = renderer._ink_extents_pt(path, fitted)
    return baseline - ascent, baseline + descent


@pytest.mark.parametrize("cell_h", [6.0, 9.0, 20.0, 60.0])
def test_a_line_of_text_stays_inside_its_own_cell(tmp_path, cell_h):
    """Ink never escapes the cell, however tight or roomy the row is."""
    config = _base_config(tmp_path / "cell_ink.svg")
    renderer = TimelineRenderer()
    title_size, _notes_size, _date = renderer._callout_metrics(config)

    top, bottom = _cell_ink(
        renderer,
        config,
        100.0,
        cell_h,
        config.get_text_style("ec-event-name").font,
        title_size,
    )
    assert top >= 100.0 - 0.01
    assert bottom <= 100.0 + cell_h + 0.01


def test_a_line_is_centred_in_its_cell(tmp_path):
    """Slack is shared above and below, not dumped under the baseline."""
    config = _base_config(tmp_path / "cell_centre.svg")
    renderer = TimelineRenderer()
    title_size, _notes, _date = renderer._callout_metrics(config)

    top, bottom = _cell_ink(
        renderer,
        config,
        100.0,
        40.0,
        config.get_text_style("ec-event-name").font,
        title_size,
    )
    assert (top - 100.0) == pytest.approx(140.0 - bottom, abs=0.01)


def test_a_short_cell_caps_the_font_size(tmp_path):
    """The box is never stretched, so the text is what gives way."""
    config = _base_config(tmp_path / "cell_cap.svg")
    renderer = TimelineRenderer()
    path = renderer._safe_font_path(config.get_text_style("ec-event-name").font)

    assert renderer._cell_font_size(60.0, path, 12.0) == pytest.approx(12.0)
    assert renderer._cell_font_size(5.0, path, 12.0) < 12.0


def test_the_notes_never_reach_into_the_row_above(tmp_path):
    """Row 2's ink starts below row 1's, whatever the two fonts are."""
    config = _base_config(tmp_path / "cell_rows.svg")
    renderer = TimelineRenderer()
    title_size, notes_size, _date = renderer._callout_metrics(config)
    row_h = 12.0

    _top, name_bottom = _cell_ink(
        renderer,
        config,
        100.0,
        row_h,
        config.get_text_style("ec-event-name").font,
        title_size,
    )
    notes_top, _bottom = _cell_ink(
        renderer,
        config,
        100.0 + row_h,
        row_h,
        config.get_text_style("ec-event-notes").font,
        notes_size,
    )
    assert notes_top >= name_bottom - 0.01


# ── Duration bar connectors ───────────────────────────────────────────────
#
# One leader per bar, at its start date. Both edges are real dates now
# (_layout_durations pads neither), but a second leader would cross every
# bar stacked between the two edges on its way to the axis.


def _duration_connector_xs(config, event, *, axis_left=60.0, axis_right=730.0):
    renderer = _CaptureTimelineRenderer()
    renderer._page_width, renderer._page_height = config.pageX, config.pageY
    start = arrow.get("20260101", "YYYYMMDD")
    end = arrow.get("20260630", "YYYYMMDD")
    laid_out = renderer._layout_durations(config, [event], _hframe(start, end, axis_left, axis_right, 300.0))
    renderer._draw_duration_connectors(config, laid_out[0], _haxis(300.0))
    return laid_out[0], [c["x1"] for c in renderer.line_calls]


def test_a_duration_bar_gets_one_connector_at_its_start_date(tmp_path):
    config = _base_config(tmp_path / "duration_connector.svg")
    event = Event(task_name="Short", start="20260210", end="20260320")

    item, xs = _duration_connector_xs(config, event)
    assert xs == [item.start_x]
    assert item.end_x not in xs


def test_vertical_durations_also_only_connect_at_the_start(tmp_path):
    config = _base_config(tmp_path / "duration_vertical.svg")
    set_orientation(config, "vertical")
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
    renderer._draw_duration_connectors(config, item, _vaxis(100.0))

    assert [c["y1"] for c in renderer.line_calls] == [item.start_y]


# ── Duration bars grouped by WBS ──────────────────────────────────────────
#
# Bars used to run in date order with the palette cycling per bar, so two
# tasks in the same phase looked no more related than two picked at random.
# They now sort by WBS group and every bar in a group takes one color.


def _dur(name, start, end, wbs=None, rollup=False):
    return Event(task_name=name, start=start, end=end, wbs=wbs, rollup=rollup)


def _grouped_bars(config, events):
    renderer = _CaptureTimelineRenderer()
    renderer._page_width, renderer._page_height = config.pageX, config.pageY
    return renderer._layout_durations(
        config,
        events,
        _hframe(arrow.get("20260101", "YYYYMMDD"), arrow.get("20260630", "YYYYMMDD"), 50.0, 700.0, 300.0),
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
    set_fields(config, timeline_wbs_group_depth=2)
    bars = _grouped_bars(config, _phase_events())

    by_group: dict[str, set[str]] = {}
    for bar in bars:
        by_group.setdefault(wbs_group(bar.event.wbs, 2), set()).add(bar.color)
    assert by_group  # sanity: bars were laid out
    for group, colors in by_group.items():
        assert len(colors) == 1, f"{group} drew in {sorted(colors)}"


def test_different_wbs_groups_get_different_colors(tmp_path):
    config = _base_config(tmp_path / "wbs_distinct.svg")
    set_fields(config, timeline_wbs_group_depth=2)
    set_fields(config, timeline_bottom_colors=["red", "green", "blue", "gold"])
    bars = _grouped_bars(config, _phase_events())

    per_group = {wbs_group(b.event.wbs, 2): b.color for b in bars}
    assert len(per_group) == 3  # NP.1, NP.2, NP.3
    assert len(set(per_group.values())) == 3


def test_bars_are_ordered_so_each_group_is_contiguous(tmp_path):
    config = _base_config(tmp_path / "wbs_order.svg")
    set_fields(config, timeline_wbs_group_depth=2)
    bars = _grouped_bars(config, _phase_events())

    groups = [wbs_group(b.event.wbs, 2) for b in bars]
    runs = [g for i, g in enumerate(groups) if i == 0 or groups[i - 1] != g]
    assert runs == sorted(set(groups)), "a group was split by another group"
    # WBS order, not the input order (which led with NP.2).
    assert runs == ["NP.1", "NP.2", "NP.3"]


def test_deeper_codes_fold_into_their_group(tmp_path):
    """NP.2.S4.7 belongs with NP.2.1 at depth 2, not in a group of its own."""
    config = _base_config(tmp_path / "wbs_fold.svg")
    set_fields(config, timeline_wbs_group_depth=2)
    bars = _grouped_bars(config, _phase_events())

    colors = {b.event.task_name: b.color for b in bars if b.event.task_name in ("B build 1", "B build 2")}
    assert len(colors) == 2
    assert len(set(colors.values())) == 1


def test_bars_without_a_wbs_form_a_block_after_the_numbered_ones(tmp_path):
    config = _base_config(tmp_path / "wbs_none.svg")
    set_fields(config, timeline_wbs_group_depth=2)
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
    set_fields(config, timeline_wbs_group_depth=0)
    set_fields(config, timeline_bottom_colors=["red", "green", "blue", "gold"])
    bars = _grouped_bars(config, _phase_events())

    starts = [b.event.start for b in bars]
    assert starts == sorted(starts)
    # Consecutive bars cycle rather than sharing a group color.
    assert bars[0].color != bars[1].color


def test_vertical_duration_bars_group_by_wbs_too(tmp_path):
    config = _base_config(tmp_path / "wbs_vertical.svg")
    set_fields(config, timeline_wbs_group_depth=2)
    set_orientation(config, "vertical")
    renderer = _CaptureTimelineRenderer()
    renderer._page_width, renderer._page_height = config.pageX, config.pageY

    bars = renderer._layout_durations(
        config,
        _phase_events(),
        _vframe(arrow.get("20260101", "YYYYMMDD"), arrow.get("20260630", "YYYYMMDD"), 50.0, 700.0, 200.0),
        Side.PRIMARY,
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
        ("NP", 2, "NP"),  # shorter than the depth → its own group
        (None, 2, ""),  # no WBS → the unnumbered block
        ("", 2, ""),
        ("NP.1", 0, ""),  # depth 0 → grouping off
    ],
)
def test_wbs_group_prefixes(wbs, depth, expected):
    assert wbs_group(wbs, depth) == expected


# ── A rollup leads the bars it summarises ─────────────────────────────────
#
# Greedy first-fit alone put a group's rollup wherever it happened to fit and
# then let its own parts reuse lanes nearer the axis — so the bar that
# summarised a phase was drawn below the phase. A rollup now floors every bar
# sharing its root WBS one lane further out.


def _rollup_phase_events():
    """One rollup per phase, with parts a first-fit pass would sink it under.

    The NP.2 parts start after the NP.1 bars end, so without a floor they
    would reuse NP.1's lanes and sit nearer the axis than NP.2's own rollup.
    """
    return [
        _dur("phase one", "20260202", "20260227", "NP.1", rollup=True),
        _dur("one a", "20260202", "20260213", "NP.1.1"),
        _dur("one b", "20260209", "20260220", "NP.1.2"),
        _dur("phase two", "20260302", "20260327", "NP.2", rollup=True),
        _dur("two a", "20260302", "20260313", "NP.2.1"),
        _dur("two b", "20260309", "20260320", "NP.2.2"),
    ]


def _lanes_by_name(bars):
    return {b.event.task_name: b.lane for b in bars}


def test_a_rollup_sits_nearer_the_axis_than_every_bar_it_summarises(tmp_path):
    config = _base_config(tmp_path / "rollup_lane.svg")
    set_fields(config, timeline_wbs_group_depth=2)
    bars = _grouped_bars(config, _rollup_phase_events())

    by_group: dict[str, list] = {}
    for bar in bars:
        by_group.setdefault(wbs_group(bar.event.wbs, 2), []).append(bar)

    assert len(by_group) == 2
    for group, items in by_group.items():
        rollups = [b.lane for b in items if b.event.rollup]
        parts = [b.lane for b in items if not b.event.rollup]
        assert rollups and parts, f"{group} needs both to be a test"
        assert max(rollups) < min(parts), (
            f"{group}: rollup at lane {max(rollups)} is further out than a part at lane {min(parts)}"
        )


def test_a_part_is_floored_past_its_rollup_rather_than_reusing_a_low_lane(
    tmp_path,
):
    """The specific packing the floor exists to prevent."""
    config = _base_config(tmp_path / "rollup_floor.svg")
    set_fields(config, timeline_wbs_group_depth=2)
    lanes = _lanes_by_name(_grouped_bars(config, _rollup_phase_events()))

    # NP.2's parts start well after NP.1's bars end, so first-fit alone would
    # hand them NP.1's lanes.
    assert lanes["two a"] > lanes["phase two"]
    assert lanes["two b"] > lanes["phase two"]


def test_a_lane_skipped_by_a_floor_is_still_offered_to_other_groups(tmp_path):
    """The floor costs depth only inside the group it applies to."""
    config = _base_config(tmp_path / "rollup_reuse.svg")
    set_fields(config, timeline_wbs_group_depth=2)
    events = _rollup_phase_events() + [
        # No WBS, so no rollup outranks it: it may take any free lane.
        _dur("late loner", "20260601", "20260610"),
    ]
    bars = _grouped_bars(config, events)
    lanes = _lanes_by_name(bars)

    deepest_rollup = max(b.lane for b in bars if b.event.rollup)
    assert lanes["late loner"] <= deepest_rollup


def test_a_rollup_leads_its_group_even_when_its_code_is_not_a_prefix(tmp_path):
    """Ordering cannot rely on the rollup's WBS sorting first.

    A rollup coded NP.1.99 sorts after NP.1.1 by WBS, so only the explicit
    rollup rank keeps its lane known before its parts are placed.
    """
    config = _base_config(tmp_path / "rollup_order.svg")
    set_fields(config, timeline_wbs_group_depth=2)
    bars = _grouped_bars(
        config,
        [
            _dur("part", "20260202", "20260213", "NP.1.1"),
            _dur("summary", "20260202", "20260227", "NP.1.99", rollup=True),
        ],
    )
    assert [b.event.task_name for b in bars] == ["summary", "part"]
    lanes = _lanes_by_name(bars)
    assert lanes["summary"] < lanes["part"]


def test_grouping_off_leaves_the_rollup_rule_inert(tmp_path):
    """Depth 0 means no hierarchy to express, so nothing is floored."""
    config = _base_config(tmp_path / "rollup_depth0.svg")
    set_fields(config, timeline_wbs_group_depth=0)
    # Pure date-order item_placement_order (no "wbs" token), to isolate this
    # test's lane-packing assertion from item_placement_order's default WBS
    # ordering -- every _rollup_phase_events() event has a WBS code, so a
    # wbs-first order would reorder lane assignment before packing even runs.
    set_fields(config, item_placement_order=["start_date"])
    bars = _grouped_bars(config, _rollup_phase_events())

    renderer = _CaptureTimelineRenderer()
    for bar in bars:
        assert renderer._rollup_group(config, bar.event) is None
    # Date order, and the late parts reuse the early lanes as before.
    assert min(b.lane for b in bars if not b.event.rollup) == 0


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
        self.icon_calls.append({"icon": icon_name, "x": x, "y": baseline_y, "size": size, **kwargs})
        return True


def _overflow_setup(tmp_path, name, lanes=6):
    """A config plus `lanes` durations that each need their own lane."""
    config = _base_config(tmp_path / name)
    set_fields(config, default_missing_icon="missing-box")
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
        _hframe(arrow.get("20260101", "YYYYMMDD"), arrow.get("20260630", "YYYYMMDD"), 50.0, 700.0, axis_y),
    )
    return renderer, bars


def test_a_bar_past_the_limit_is_not_drawn(tmp_path):
    config, events = _overflow_setup(tmp_path, "ovf_bar.svg")
    renderer, bars = _lay_out(config, events)
    deep = max(bars, key=lambda b: b.lane)
    bar_y, _bar_h = _bar_y(renderer, config, deep, 300.0)

    renderer.rect_calls.clear()
    renderer._draw_duration(config, deep, _haxis(300.0), limit=(bar_y - 1.0) - (300.0))
    assert renderer.rect_calls == []

    # Same bar, room to spare: it draws.
    renderer._draw_duration(config, deep, _haxis(300.0), limit=(bar_y + 10_000.0) - (300.0))
    assert renderer.rect_calls


def test_the_leader_stops_at_the_limit_and_marks_the_missing_box(tmp_path):
    config, events = _overflow_setup(tmp_path, "ovf_leader.svg")
    renderer, bars = _lay_out(config, events)
    deep = max(bars, key=lambda b: b.lane)
    bar_y, _bar_h = _bar_y(renderer, config, deep, 300.0)
    limit = bar_y - 1.0

    renderer._draw_duration_connectors(config, deep, _haxis(300.0), limit=(limit) - (300.0))

    assert len(renderer.line_calls) == 1
    end_y = renderer.line_calls[0]["y2"]
    assert end_y < bar_y  # pulled back from the missing bar
    assert end_y <= limit  # and inside the drawable area

    assert len(renderer.icon_calls) == 1
    icon = renderer.icon_calls[0]
    assert icon["icon"] == "missing-box"
    assert icon["x"] == pytest.approx(deep.start_x)


def test_a_bar_that_fits_gets_no_missing_marker(tmp_path):
    config, events = _overflow_setup(tmp_path, "ovf_fits.svg")
    renderer, bars = _lay_out(config, events)
    shallow = min(bars, key=lambda b: b.lane)
    bar_y, _bar_h = _bar_y(renderer, config, shallow, 300.0)

    renderer._draw_duration_connectors(config, shallow, _haxis(300.0), limit=(bar_y + 10_000.0) - (300.0))
    assert renderer.icon_calls == []
    assert renderer.line_calls[0]["y2"] == pytest.approx(bar_y)


def test_no_limit_draws_every_bar(tmp_path):
    """--shrink grows the page instead, so nothing is held back."""
    config, events = _overflow_setup(tmp_path, "ovf_none.svg")
    renderer, bars = _lay_out(config, events)
    renderer.rect_calls.clear()
    for bar in bars:
        renderer._draw_duration(config, bar, _haxis(300.0), limit=None)
    # One bar rect each, and no leader was cut short.
    assert len(renderer.rect_calls) == len(bars)
    assert renderer.icon_calls == []


def test_a_theme_without_a_missing_icon_still_clamps_the_leader(tmp_path):
    config, events = _overflow_setup(tmp_path, "ovf_noicon.svg")
    set_fields(config, default_missing_icon=None)
    renderer, bars = _lay_out(config, events)
    deep = max(bars, key=lambda b: b.lane)
    bar_y, _bar_h = _bar_y(renderer, config, deep, 300.0)

    renderer._draw_duration_connectors(config, deep, _haxis(300.0), limit=(bar_y - 1.0) - (300.0))
    assert renderer.icon_calls == []
    assert renderer.line_calls[0]["y2"] < bar_y


def test_a_duration_row_is_just_its_bar(tmp_path):
    """The dates ride inside the bar, so no band is reserved beneath it."""
    config, _events = _overflow_setup(tmp_path, "ovf_dates.svg")
    renderer = _CaptureOverflowRenderer()
    _t, _n, _date_size, bar_h = renderer._duration_metrics(config)
    assert renderer._duration_row_extent(config) == pytest.approx(bar_h)


# ── The duration bar's three-column grid ──────────────────────────────────
#
# The bar carries the callout box's grid with one column more: the event's
# icon over its start date, the name over the notes, and the end date at the
# far end. Nothing is resized to its text — a bar's edges are its dates — so
# a bar too narrow for its text breaks the name over both rows of the middle
# column and condenses every cell of the bar by one shared factor.


def _drawn_duration(tmp_path, name, event, axis_y=300.0):
    config = _base_config(tmp_path / name)
    renderer = _CaptureOverflowRenderer()
    renderer._page_width, renderer._page_height = config.pageX, config.pageY
    bars = renderer._layout_durations(
        config,
        [event],
        _hframe(arrow.get("20260101", "YYYYMMDD"), arrow.get("20260630", "YYYYMMDD"), 50.0, 700.0, axis_y),
    )
    renderer._draw_duration(config, bars[0], _haxis(axis_y))
    return config, renderer, bars[0]


def _date_texts(renderer):
    return [c for c in renderer.text_calls if c.get("css_class") == "ec-duration-date"]


def test_the_start_and_end_dates_are_drawn_inside_the_bar(tmp_path):
    event = Event(task_name="Build", start="20260210", end="20260320")
    config, renderer, bar = _drawn_duration(tmp_path, "in_bar.svg", event)
    bar_y, bar_h = _bar_y(renderer, config, bar, 300.0)

    dates = _date_texts(renderer)
    assert len(dates) == 2
    for date_call in dates:
        assert bar.start_x <= date_call["x"] <= bar.end_x
        assert bar_y <= date_call["y"] <= bar_y + bar_h


def test_the_start_date_sits_at_the_left_end_and_the_end_date_at_the_right(tmp_path):
    event = Event(task_name="Build", start="20260210", end="20260320")
    _config, renderer, bar = _drawn_duration(tmp_path, "in_bar_ends.svg", event)

    start_date, end_date = _date_texts(renderer)
    assert start_date["anchor"] == "start"
    assert end_date["anchor"] == "end"
    assert start_date["x"] == pytest.approx(bar.start_x + 3.0)
    assert end_date["x"] == pytest.approx(bar.end_x - 3.0)
    # Both on the second row, under the icon and the name.
    assert start_date["y"] == pytest.approx(end_date["y"])
    titles = [c for c in renderer.text_calls if c.get("css_class") == "ec-event-name"]
    assert titles and titles[0]["y"] < start_date["y"]


def test_the_name_is_centred_between_the_two_date_columns(tmp_path):
    # Wide enough that nothing is condensed — a bar that overflows hands
    # every cell the same reduced width instead (see the condensing tests).
    event = Event(task_name="Build", start="20260210", end="20260501")
    config, renderer, bar = _drawn_duration(tmp_path, "in_bar_mid.svg", event)
    assert not bar.text_overflow

    title = next(c for c in renderer.text_calls if c.get("css_class") == "ec-event-name")
    assert title["anchor"] == "middle"
    assert title["x"] == pytest.approx((bar.start_x + bar.end_x) / 2.0)
    # Its cell is the middle column, so it never reaches the dates.
    inner_w = (bar.end_x - bar.start_x) - 6.0
    _off, mid = renderer._duration_cell_layout(config, inner_w)[1]
    assert title["max_width"] == pytest.approx(mid)


def test_the_two_side_columns_are_the_same_width(tmp_path):
    config = _base_config(tmp_path / "grid_cols.svg")
    renderer = TimelineRenderer()
    (off1, side1), (off2, mid), (off3, side3) = renderer._duration_cell_layout(config, 200.0)
    assert side1 == side3 == pytest.approx(200.0 * config.theme_v3.timeline.events.icon_column_ratio)
    assert off1 == 0.0 and off3 + side3 == pytest.approx(200.0)
    # The middle column keeps a gap clear of each date column.
    assert off2 == pytest.approx(side1 + 4.0)
    assert side1 + mid + side3 + 8.0 == pytest.approx(200.0)


def test_a_theme_can_widen_a_duration_bar_side_column(tmp_path):
    config = _base_config(tmp_path / "grid_ratio.svg")
    set_fields(config, timeline_duration_icon_column_ratio=0.3)
    renderer = TimelineRenderer()
    (_o1, side), (_o2, mid), (_o3, side3) = renderer._duration_cell_layout(config, 200.0)
    assert side == side3 == pytest.approx(60.0)
    assert mid == pytest.approx(80.0 - 8.0)


def test_the_event_icon_leads_the_row_above_the_start_date(tmp_path):
    event = Event(task_name="Build", start="20260210", end="20260320", icon="rocket")
    config = _base_config(tmp_path / "grid_icon.svg")
    set_fields(config, timeline_duration_icon_visible=True)
    renderer = _CaptureOverflowRenderer()
    renderer._page_width, renderer._page_height = config.pageX, config.pageY
    bars = renderer._layout_durations(
        config,
        [event],
        _hframe(arrow.get("20260101", "YYYYMMDD"), arrow.get("20260630", "YYYYMMDD"), 50.0, 700.0, 300.0),
    )
    renderer._draw_duration(config, bars[0], _haxis(300.0))

    icons = [c for c in renderer.icon_calls if c.get("css_class") == "ec-duration-icon"]
    assert [c["icon"] for c in icons] == ["rocket"]
    start_date = _date_texts(renderer)[0]
    # First column, first row: over the start date, at the bar's left end.
    assert icons[0]["x"] < (bars[0].start_x + bars[0].end_x) / 2.0
    assert icons[0]["y"] < start_date["y"]


def test_a_bar_too_narrow_for_its_dates_overflows_instead_of_growing(tmp_path):
    """A one-day event cannot hold both dates plus its name — and says so."""
    config = _base_config(tmp_path / "in_bar_width.svg")
    renderer = _CaptureOverflowRenderer()
    renderer._page_width, renderer._page_height = config.pageX, config.pageY
    bars = renderer._layout_durations(
        config,
        [Event(task_name="Ship", start="20260210", end="20260210")],
        _hframe(arrow.get("20260101", "YYYYMMDD"), arrow.get("20260630", "YYYYMMDD"), 50.0, 700.0, 300.0),
    )
    bar = bars[0]
    assert bar.end_x - bar.start_x < renderer._duration_full_extent(
        config, bars[0].event, arrow.get("20260101", "YYYYMMDD")
    )
    assert bar.text_overflow


# ── Bar edges line up on their dates ──────────────────────────────────────
#
# A bar too short for its text used to be padded — first rightward, later
# leftward — so two bars sharing a date could still end at different x. The
# bar now spans exactly its dates and overflows its label instead.


class _CaptureCircleRenderer(_CaptureOverflowRenderer):
    """Overflow capture plus the axis markers, which it otherwise swallows."""

    def __init__(self):
        super().__init__()
        self.circle_calls: list[dict] = []

    def _draw_circle(self, cx, cy, radius, *args, **kwargs):
        self.circle_calls.append({"cx": cx, "cy": cy, "radius": radius})


def _aligned_bars(tmp_path, name, events, axis_left=50.0, axis_right=700.0, renderer=None, config=None):
    config = config or _base_config(tmp_path / name)
    renderer = renderer or _CaptureOverflowRenderer()
    renderer._page_width, renderer._page_height = config.pageX, config.pageY
    return (
        config,
        renderer,
        renderer._layout_durations(
            config,
            events,
            _hframe(arrow.get("20260101", "YYYYMMDD"), arrow.get("20260630", "YYYYMMDD"), axis_left, axis_right, 300.0),
        ),
    )


def _day_x(renderer, daykey, axis_left=50.0, axis_right=700.0):
    frame = _hframe(arrow.get("20260101", "YYYYMMDD"), arrow.get("20260630", "YYYYMMDD"), axis_left, axis_right, 0.0)
    return frame.pos(arrow.get(daykey, "YYYYMMDD"))


def test_bars_ending_on_the_same_day_share_a_right_edge(tmp_path):
    """A short bar and a long one, both ending 20 Mar, end at one x."""
    events = [
        Event(task_name="Ship it", start="20260316", end="20260320", wbs="1.1"),
        Event(task_name="Long haul", start="20260210", end="20260320", wbs="1.2"),
    ]
    _config, renderer, bars = _aligned_bars(tmp_path, "aligned_end.svg", events)

    short, long_ = bars
    assert short.end_x == pytest.approx(long_.end_x)
    assert short.end_x == pytest.approx(_day_x(renderer, "20260321"))  # the bar covers its last day's whole cell


def test_bars_starting_on_the_same_day_share_a_left_edge(tmp_path):
    """The same for start dates: no padding is taken out of the left edge."""
    events = [
        Event(task_name="Ship it", start="20260210", end="20260213", wbs="1.1"),
        Event(task_name="Long haul", start="20260210", end="20260501", wbs="1.2"),
    ]
    _config, renderer, bars = _aligned_bars(tmp_path, "aligned_start.svg", events)

    short, long_ = bars
    assert short.start_x == pytest.approx(long_.start_x)
    assert short.start_x == pytest.approx(_day_x(renderer, "20260210"))


def test_a_bar_spans_exactly_its_two_dates(tmp_path):
    events = [Event(task_name="Wide name on a short event", start="20260316", end="20260320")]
    _config, renderer, bars = _aligned_bars(tmp_path, "aligned_x.svg", events)
    bar = bars[0]
    assert bar.start_x == pytest.approx(_day_x(renderer, "20260316"))
    assert bar.end_x == pytest.approx(_day_x(renderer, "20260321"))
    # ...even though the name does not fit in that span.
    assert bar.end_x - bar.start_x < bar.min_width
    assert bar.text_overflow


def test_a_bar_at_the_left_margin_is_not_pushed_right_either(tmp_path):
    """The old fallback grew a bar rightward when the left ran out."""
    events = [Event(task_name="A name much wider than a few days of this axis", start="20260101", end="20260103")]
    _config, renderer, bars = _aligned_bars(tmp_path, "aligned_margin.svg", events)
    bar = bars[0]
    assert bar.start_x == pytest.approx(50.0)
    assert bar.end_x == pytest.approx(_day_x(renderer, "20260104"))


def test_the_axis_marker_sits_on_the_start_date_only(tmp_path):
    """The end date's dot went with the end date's leader.

    Nothing ran from it down to the bar, and once several lanes end on one
    day the dot left on the axis belonged to no bar in particular.
    """
    config, renderer, bars = _aligned_bars(
        tmp_path,
        "aligned_markers.svg",
        [Event(task_name="Ship it", start="20260316", end="20260320")],
        renderer=_CaptureCircleRenderer(),
    )
    renderer._draw_duration(config, bars[0], _haxis(300.0))
    marker_xs = [c["cx"] for c in renderer.circle_calls]
    assert marker_xs == [bars[0].start_x]


def test_a_vertical_bar_also_marks_only_its_start_date(tmp_path):
    config, renderer, bars = _vertical_bars(
        tmp_path,
        "v_markers.svg",
        [Event(task_name="Build", start="20260210", end="20260501")],
        renderer=_CaptureCircleRenderer(),
    )
    renderer._draw_duration(config, bars[0], _vaxis(200.0))
    marker_ys = [c["cy"] for c in renderer.circle_calls]
    assert marker_ys == [bars[0].start_y]


# ── Overflowing a bar's grid ──────────────────────────────────────────────
#
# A bar cannot be widened — its edges are its dates — so a bar too narrow
# for its text spends the middle column's second row on the rest of the
# name instead of the notes, and condenses every cell of the bar by the one
# factor the tightest of them needs.


def _overflow_drawn(tmp_path, name, event, config=None, **cfg):
    config = config or _base_config(tmp_path / name)
    set_fields(config, **cfg)
    config, renderer, bars = _aligned_bars(tmp_path, name, [event], config=config)
    renderer._draw_duration(config, bars[0], _haxis(300.0))
    return config, renderer, bars[0]


def _names(renderer):
    return [c for c in renderer.text_calls if c.get("css_class") == "ec-event-name"]


def test_an_overflowing_bar_draws_no_overflow_icon(tmp_path):
    """The mark is gone: the two-line name says the same thing, legibly."""
    event = Event(task_name="A name much wider than this bar", start="20260316", end="20260410")
    _config, renderer, bar = _overflow_drawn(tmp_path, "ovl_icon.svg", event)
    assert bar.text_overflow
    assert [c for c in renderer.icon_calls if c.get("css_class") == "ec-overflow-icon"] == []


def test_a_bar_with_room_carries_no_overflow_mark(tmp_path):
    event = Event(task_name="Build", start="20260210", end="20260501")
    _config, renderer, bar = _overflow_drawn(tmp_path, "ovl_none.svg", event)
    assert not bar.text_overflow
    assert [c for c in renderer.icon_calls if c.get("css_class") == "ec-overflow-icon"] == []


def test_an_overflowing_name_breaks_over_the_middle_column_two_rows(tmp_path):
    """Half a name reads as a different activity; two lines of it do not."""
    # Wide enough for the icon and the name, too narrow for all of the name
    # plus the two in-bar dates.
    event = Event(task_name="A name much wider than this bar", start="20260316", end="20260410")
    config, renderer, bar = _overflow_drawn(tmp_path, "ovl_name.svg", event)
    assert bar.text_overflow

    names = _names(renderer)
    assert len(names) == 2
    assert " ".join(n["text"] for n in names) == event.task_name  # every word
    assert not any("…" in n["text"] for n in names)
    # Both lines in the middle column, one row above the other.
    assert names[0]["x"] == pytest.approx(names[1]["x"])
    assert names[0]["y"] < names[1]["y"]
    # Full font size, squeezed on X into what the bar has left.
    title_size, _n, _d, _bar_h = renderer._duration_metrics(config)
    assert all(n["size"] == pytest.approx(title_size) for n in names)
    assert all(0 < n["max_width"] <= bar.end_x - bar.start_x for n in names)


def test_the_two_lines_of_a_broken_name_are_balanced(tmp_path):
    """Splitting at the middle word leaves one line long and one short."""
    renderer = TimelineRenderer()
    font_path = renderer._safe_font_path("Roboto")
    first, second = renderer._split_name_two_lines("Integration and acceptance testing", font_path, 10.0)
    assert (first, second) == ("Integration and", "acceptance testing")


def test_a_single_word_name_is_not_broken_in_half(tmp_path):
    renderer = TimelineRenderer()
    assert renderer._split_name_two_lines("Reconciliation", renderer._safe_font_path("Roboto"), 10.0) == (
        "Reconciliation",
        "",
    )


def test_an_overflowing_bar_drops_its_notes_for_the_name(tmp_path):
    """The second row is the rest of the name; the description gives way."""
    event = Event(
        task_name="A name much wider than this bar",
        start="20260316",
        end="20260410",
        notes="notes that will not fit either",
    )
    _config, renderer, _bar = _overflow_drawn(tmp_path, "ovl_dates.svg", event, include_notes=True)
    assert len(_date_texts(renderer)) == 2  # the grid otherwise holds
    assert [c for c in renderer.text_calls if c.get("css_class") == "ec-event-notes"] == []
    assert len(_names(renderer)) == 2


def test_a_bar_with_room_keeps_its_notes(tmp_path):
    event = Event(task_name="Build", start="20260210", end="20260501", notes="a short note")
    _config, renderer, bar = _overflow_drawn(tmp_path, "ovl_keep_notes.svg", event, include_notes=True)
    assert not bar.text_overflow
    notes = [c for c in renderer.text_calls if c.get("css_class") == "ec-event-notes"]
    assert [n["text"] for n in notes] == ["a short note"]
    assert len(_names(renderer)) == 1


def test_everything_in_a_condensed_bar_condenses_by_the_same_factor(tmp_path):
    """One squashed line beside a full-width date read as two typefaces."""
    event = Event(task_name="A name much wider than this bar", start="20260316", end="20260410", icon="rocket")
    _config, renderer, bar = _overflow_drawn(tmp_path, "ovl_uniform.svg", event, timeline_duration_icon_visible=True)
    assert bar.text_overflow

    drawn = [c for c in renderer.text_calls if c.get("css_class") in ("ec-event-name", "ec-duration-date")]
    assert len(drawn) == 4  # two name lines, two dates
    factors = [c["max_width"] / string_width(c["text"], renderer._safe_font_path(c["font"]), c["size"]) for c in drawn]
    assert max(factors) == pytest.approx(min(factors))
    assert min(factors) < 1.0  # it really is condensing

    # ...and the icon narrows with them, on the same axis.
    icon = next(c for c in renderer.icon_calls if c.get("css_class") == "ec-duration-icon")
    assert f"scale({factors[0]:.6f} 1.000000)" in (icon.get("transform") or "")


def test_a_bar_with_room_condenses_nothing(tmp_path):
    event = Event(task_name="Build", start="20260210", end="20260501", icon="rocket")
    _config, renderer, bar = _overflow_drawn(
        tmp_path, "ovl_uncondensed.svg", event, timeline_duration_icon_visible=True
    )
    assert not bar.text_overflow
    icon = next(c for c in renderer.icon_calls if c.get("css_class") == "ec-duration-icon")
    assert icon.get("transform") is None


def test_a_bar_with_room_keeps_its_full_name_and_dates(tmp_path):
    event = Event(task_name="Build", start="20260210", end="20260501")
    _config, renderer, bar = _overflow_drawn(tmp_path, "ovl_wide.svg", event)
    assert not bar.text_overflow

    names = _names(renderer)
    assert names and names[0]["text"] == "Build"
    assert len(_date_texts(renderer)) == 2


def test_a_bar_too_narrow_to_grid_draws_nothing_inside(tmp_path):
    """Every cell would be narrower than its ink, so the rect stands alone."""
    event = Event(task_name="A name much wider than this bar", start="20260316", end="20260320")
    _config, renderer, _bar = _overflow_drawn(tmp_path, "ovl_bare.svg", event)

    assert [c for c in renderer.icon_calls if c.get("css_class") == "ec-overflow-icon"] == []
    assert _names(renderer) == []
    assert _date_texts(renderer) == []


def test_a_hairline_bar_draws_nothing_it_cannot_fit(tmp_path):
    """One day on a six-month axis: no column wide enough to draw into."""
    event = Event(task_name="Ship it", start="20260316", end="20260316")
    _config, renderer, bar = _overflow_drawn(tmp_path, "ovl_hairline.svg", event)
    assert bar.end_x - bar.start_x < 4.0  # one day of a six-month axis
    assert _names(renderer) == []
    assert _date_texts(renderer) == []


def test_the_row_no_longer_reserves_a_band_under_the_bar(tmp_path):
    """Reclaiming that band is what lets the lanes pack tighter."""
    config = _base_config(tmp_path / "in_bar_stride.svg")
    renderer = _CaptureOverflowRenderer()
    renderer._page_width, renderer._page_height = config.pageX, config.pageY
    events = [Event(task_name=f"T{i}", start="20260210", end="20260320", wbs=f"1.{i}") for i in range(3)]
    bars = renderer._layout_durations(
        config,
        events,
        _hframe(arrow.get("20260101", "YYYYMMDD"), arrow.get("20260630", "YYYYMMDD"), 50.0, 700.0, 300.0),
    )
    lanes = sorted({b.lane for b in bars})
    assert len(lanes) >= 2

    _t, _n, date_size, bar_h = renderer._duration_metrics(config)
    lane_gap = max(config.theme_v3.timeline.duration_lane_gap_y, date_size * 0.9)
    y0, _ = _bar_y(renderer, config, bars[0], 300.0)
    y1, _ = _bar_y(renderer, config, next(b for b in bars if b.lane == 1), 300.0)
    assert y1 - y0 == pytest.approx(bar_h + lane_gap)


def test_vertical_bars_carry_their_dates_inside_too(tmp_path):
    config = _base_config(tmp_path / "in_bar_vertical.svg")
    set_orientation(config, "vertical")
    renderer = _CaptureOverflowRenderer()
    renderer._page_width, renderer._page_height = config.pageX, config.pageY
    bars = renderer._layout_durations(
        config,
        [Event(task_name="Build", start="20260210", end="20260320")],
        _vframe(arrow.get("20260101", "YYYYMMDD"), arrow.get("20260630", "YYYYMMDD"), 50.0, 700.0, 200.0),
        Side.PRIMARY,
    )
    renderer._draw_duration(config, bars[0], _vaxis(200.0))

    dates = _date_texts(renderer)
    assert len(dates) == 2
    # Rotated with the label, and pulled in from each along-axis end.
    for date_call in dates:
        assert "rotate(-90" in (date_call.get("transform") or "")
    cx_values = {round(d["x"], 3) for d in dates}
    assert len(cx_values) == 2  # one toward each end, not stacked


# ── Vertical bars align on their dates too ────────────────────────────────
#
# The vertical layout padded a short bar downward long after the horizontal
# one stopped, so its far edge sat on a day the event did not end on.


def _vertical_bars(tmp_path, name, events, config=None, renderer=None):
    config = config or _base_config(tmp_path / name)
    set_orientation(config, "vertical")
    renderer = renderer or _CaptureOverflowRenderer()
    renderer._page_width, renderer._page_height = config.pageX, config.pageY
    return (
        config,
        renderer,
        renderer._layout_durations(
            config,
            events,
            _vframe(arrow.get("20260101", "YYYYMMDD"), arrow.get("20260630", "YYYYMMDD"), 50.0, 700.0, 200.0),
            Side.PRIMARY,
        ),
    )


def _day_y(renderer, daykey, axis_top=50.0, axis_bottom=700.0):
    frame = _vframe(arrow.get("20260101", "YYYYMMDD"), arrow.get("20260630", "YYYYMMDD"), axis_top, axis_bottom, 0.0)
    return frame.pos(arrow.get(daykey, "YYYYMMDD"))


def test_a_vertical_bar_spans_exactly_its_two_dates(tmp_path):
    _config, renderer, bars = _vertical_bars(
        tmp_path,
        "v_span.svg",
        [Event(task_name="A name much longer than four days of this axis", start="20260316", end="20260320")],
    )
    bar = bars[0]
    assert bar.start_y == pytest.approx(_day_y(renderer, "20260316"))
    assert bar.end_y == pytest.approx(_day_y(renderer, "20260321"))
    assert bar.end_y - bar.start_y < bar.min_width
    assert bar.text_overflow


def test_vertical_bars_sharing_a_date_share_an_edge(tmp_path):
    _config, _renderer, bars = _vertical_bars(
        tmp_path,
        "v_share.svg",
        [
            Event(task_name="Ship it", start="20260210", end="20260213", wbs="1.1"),
            Event(task_name="Long haul", start="20260210", end="20260501", wbs="1.2"),
        ],
    )
    short, long_ = bars
    assert short.start_y == pytest.approx(long_.start_y)


def test_an_overflowing_vertical_bar_breaks_its_name_over_two_rows(tmp_path):
    config, renderer, bars = _vertical_bars(
        tmp_path,
        "v_overflow.svg",
        [Event(task_name="A name much longer than this bar", start="20260210", end="20260310")],
    )
    bar = bars[0]
    assert bar.text_overflow
    renderer._draw_duration(config, bar, _vaxis(200.0))

    assert [c for c in renderer.icon_calls if c.get("css_class") == "ec-overflow-icon"] == []

    names = _names(renderer)
    assert len(names) == 2
    assert " ".join(n["text"] for n in names) == "A name much longer than this bar"
    assert all("rotate(-90" in (n.get("transform") or "") for n in names)
    # Condensed along the bar's own axis, which the rotation made x.
    assert all(0 < n["max_width"] <= bar.end_y - bar.start_y for n in names)
    # The two rows run across the bar's thickness, so the lines sit side by
    # side in pre-rotation y.
    assert names[0]["y"] != names[1]["y"]
    # The dates keep their cells: the grid holds, only the room shrinks.
    dates = _date_texts(renderer)
    assert len(dates) == 2
    assert all("rotate(-90" in (d.get("transform") or "") for d in dates)


def test_a_condensed_vertical_bar_condenses_its_icon_along_the_axis(tmp_path):
    """The rows run down the page here, so the squeeze is on y, not x."""
    config, renderer, bars = _vertical_bars(
        tmp_path,
        "v_squeeze.svg",
        [Event(task_name="A name much longer than this bar " * 6, icon="rocket", start="20260210", end="20260310")],
    )
    set_fields(config, timeline_duration_icon_visible=True)
    renderer._draw_duration(config, bars[0], _vaxis(200.0))

    icon = next(c for c in renderer.icon_calls if c.get("css_class") == "ec-duration-icon")
    transform = icon.get("transform") or ""
    assert "scale(1.000000 " in transform


def test_a_vertical_bar_with_room_keeps_its_full_label(tmp_path):
    config, renderer, bars = _vertical_bars(
        tmp_path,
        "v_wide.svg",
        [Event(task_name="Build", start="20260210", end="20260501")],
    )
    assert not bars[0].text_overflow
    renderer._draw_duration(config, bars[0], _vaxis(200.0))
    assert [c for c in renderer.icon_calls if c.get("css_class") == "ec-overflow-icon"] == []
    assert len(_date_texts(renderer)) == 2


# ── Callout box columns ───────────────────────────────────────────────────
#
# The box is two columns: the icon over the date on the left, the name over
# the notes on the right. The date used to be right-aligned on the title
# line and the notes started at the box edge under the icon, so the two text
# lines had different left edges.


def _callout(**overrides):
    kwargs: dict[str, Any] = dict(
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
    assert notes["y"] > name["y"]  # second line


def test_the_date_sits_under_the_icon_on_the_notes_line(tmp_path):
    config, renderer = _drawn_callout(
        tmp_path,
        "callout_date.svg",
        event=Event(
            task_name="Go-Live Event",
            start="20260727",
            end="20260727",
            notes="Public launch announcement",
            icon="rocket",
        ),
    )
    date = _by_class(renderer, "ec-event-date")[0]
    notes = _by_class(renderer, "ec-event-notes")[0]
    assert renderer.icon_calls, "the fixture should draw an icon"
    icon = renderer.icon_calls[0]

    pad = config.theme_v3.timeline.events.inner_pad
    col1_right = 150.0 + pad + (200.0 - 2 * pad) * (config.theme_v3.timeline.events.icon_column_ratio)
    assert date["anchor"] == "start"
    # Both live in column 1 — the icon centred in its cell, the date on the
    # column's left edge.
    assert date["x"] < col1_right
    assert icon["x"] < col1_right
    # Same row, but each line is centred on its own ink, so the two
    # baselines need not coincide.
    row2_top = 230.0 + pad + (30.0 - 2 * pad) / 2.0
    assert row2_top < date["y"] < 230.0 + 30.0
    assert row2_top < notes["y"] < 230.0 + 30.0
    assert date["x"] < notes["x"]  # left of the text column


def test_the_date_is_no_longer_on_the_title_line(tmp_path):
    _config, renderer = _drawn_callout(tmp_path, "callout_notline.svg")
    name = _by_class(renderer, "ec-event-name")[0]
    date = _by_class(renderer, "ec-event-date")[0]
    assert date["y"] != pytest.approx(name["y"])


def test_the_column_split_follows_the_theme_ratio(tmp_path):
    """The icon column is a fixed share of the box, not sized to its text.

    A box is never widened to hold what is in it; over-wide text is
    compressed to the column instead.
    """
    config, renderer = _drawn_callout(
        tmp_path,
        "callout_col.svg",
        event=Event(
            task_name="Go-Live Event",
            start="20260727",
            end="20260727",
            notes="Public launch announcement",
            icon="rocket",
        ),
    )
    date = _by_class(renderer, "ec-event-date")[0]
    notes = _by_class(renderer, "ec-event-notes")[0]
    inner_w = 200.0 - 2 * config.theme_v3.timeline.events.inner_pad

    column = notes["x"] - date["x"]
    assert column == pytest.approx(inner_w * config.theme_v3.timeline.events.icon_column_ratio, abs=0.01)
    # Each line is capped at its own column's width, so nothing overruns.
    assert date["max_width"] == pytest.approx(column, abs=0.01)
    assert notes["max_width"] == pytest.approx(inner_w - column, abs=0.01)


def test_a_callout_without_an_icon_still_lines_its_columns_up(tmp_path):
    _config, renderer = _drawn_callout(
        tmp_path,
        "callout_noicon.svg",
        event=Event(
            task_name="Go-Live Event",
            start="20260727",
            end="20260727",
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
    bar_y, bar_h = _bar_y(renderer, config, deep, 300.0)
    limit = bar_y - 1.0

    renderer._draw_duration_connectors(config, deep, _haxis(300.0), limit=(limit) - (300.0))
    assert renderer.icon_calls[-1]["size"] == pytest.approx(bar_h)

    set_fields(config, default_missing_icon_size=21.0)
    renderer._draw_duration_connectors(config, deep, _haxis(300.0), limit=(limit) - (300.0))
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
        Event(task_name="A gate", start="20260223", end="20260223", wbs="1.2", milestone=True),
        Event(task_name="A note", start="20260225", end="20260225", wbs="1.3"),
        Event(task_name="B build", start="20260302", end="20260320", wbs="2.1"),
        Event(task_name="B gate", start="20260323", end="20260323", wbs="2.2", milestone=True),
        Event(task_name="B note", start="20260325", end="20260325", wbs="2.3"),
    ]


def test_every_item_type_in_a_group_takes_one_color(tmp_path):
    config = _base_config(tmp_path / "wbs_all.svg")
    set_fields(config, timeline_wbs_group_depth=1)
    renderer = _CaptureOverflowRenderer()
    renderer._page_width, renderer._page_height = config.pageX, config.pageY
    events = _mixed_wbs_events()
    start = arrow.get("20260101", "YYYYMMDD")
    end = arrow.get("20260630", "YYYYMMDD")

    group_colors = renderer._wbs_group_colors(config, events)
    points, durations = renderer._split_events(config, events)
    assert points and durations, "the fixture should have both kinds"

    callouts = renderer._layout_callouts(
        config,
        points,
        start,
        end,
        axis_origin=(60.0, 300.0),
        axis_length=670.0,
        orientation=Orientation.HORIZONTAL,
        side=Side.PRIMARY,
        group_colors=group_colors,
    )
    bars = renderer._layout_durations(
        config, durations, _hframe(start, end, 60.0, 730.0, 300.0), group_colors=group_colors
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
    set_fields(config, timeline_wbs_group_depth=1)
    renderer = _CaptureOverflowRenderer()
    renderer._page_width, renderer._page_height = config.pageX, config.pageY
    events = _mixed_wbs_events()
    group_colors = renderer._wbs_group_colors(config, events)
    points, durations = renderer._split_events(config, events)

    callouts = renderer._layout_callouts(
        config,
        points,
        arrow.get("20260101", "YYYYMMDD"),
        arrow.get("20260630", "YYYYMMDD"),
        axis_origin=(60.0, 300.0),
        axis_length=670.0,
        orientation=Orientation.HORIZONTAL,
        side=Side.PRIMARY,
        group_colors=group_colors,
    )
    bars = renderer._layout_durations(
        config,
        durations,
        _hframe(arrow.get("20260101", "YYYYMMDD"), arrow.get("20260630", "YYYYMMDD"), 60.0, 730.0, 300.0),
        group_colors=group_colors,
    )
    milestone = next(c for c in callouts if c.event.task_name == "A gate")
    bar = next(b for b in bars if b.event.task_name == "A plan")
    assert milestone.color == bar.color


def test_a_group_keeps_one_color_on_both_sides_of_the_axis(tmp_path):
    """A group is one color whichever side of the axis its items are on."""
    config = _base_config(tmp_path / "wbs_both.svg")
    set_fields(config, timeline_wbs_group_depth=1)
    renderer = _CaptureOverflowRenderer()
    renderer._page_width, renderer._page_height = config.pageX, config.pageY
    events = [e for e in _mixed_wbs_events() if e.start == e.end]

    group_colors = renderer._wbs_group_colors(config, events)
    callouts = renderer._layout_callouts(
        config,
        events,
        arrow.get("20260101", "YYYYMMDD"),
        arrow.get("20260630", "YYYYMMDD"),
        axis_origin=(60.0, 300.0),
        axis_length=670.0,
        orientation=Orientation.HORIZONTAL,
        side=Side.BOTH,
        group_colors=group_colors,
    )
    by_group: dict[str, set[str]] = {}
    for c in callouts:
        by_group.setdefault(wbs_group(c.event.wbs, 1), set()).add(c.color)
    for colors in by_group.values():
        assert len(colors) == 1


def test_grouping_off_leaves_each_layout_its_own_palette(tmp_path):
    config = _base_config(tmp_path / "wbs_off_all.svg")
    set_fields(config, timeline_wbs_group_depth=0)
    renderer = _CaptureOverflowRenderer()
    assert renderer._wbs_group_colors(config, _mixed_wbs_events()) == {}


def test_the_group_palette_is_the_event_palette(tmp_path):
    """One color per group means one palette: ``palettes.event``."""
    config = _base_config(tmp_path / "wbs_palette.svg")
    set_fields(config, timeline_wbs_group_depth=1)
    set_fields(config, timeline_top_colors=["red", "green"])
    renderer = _CaptureOverflowRenderer()

    colors = renderer._wbs_group_colors(config, _mixed_wbs_events())
    assert set(colors.values()) == {"red", "green"}


# ── Tick-label distance ───────────────────────────────────────────────────
#
# A `timeline.ticks` band could always place its labels with `label_gap` /
# `label_offset_y`. The built-in month ticks hard-coded the distance, so on a
# theme without a ticks band the only lever was `timeline.axis_width`, which
# resizes the tick marks too.


# ── Parity between the two orientations ───────────────────────────────────
#
# A sweep of what one axis direction drew and the other did not. Each of
# these was a horizontal-only behaviour that had no reason to be.


def test_a_vertical_callout_carries_its_start_date(tmp_path):
    """The box reserves the cell either way; it used to leave it empty."""
    config = _base_config(tmp_path / "v_callout_date.svg")
    renderer = _CaptureTimelineRenderer()
    renderer._page_width, renderer._page_height = config.pageX, config.pageY

    item = _callout(orientation=Orientation.VERTICAL)
    renderer._draw_callout_contents(config, item, StyleResult())
    dates = [c for c in renderer.text_calls if c.get("css_class") == "ec-event-date"]
    assert len(dates) == 1
    assert dates[0]["text"] == renderer._callout_date_label(config, item)
    assert dates[0]["text"]


def test_a_vertical_duration_bar_shows_the_event_icon(tmp_path):
    """`timeline.duration_icon_visible` reached only horizontal bars."""
    event = Event(task_name="Build", start="20260210", end="20260501", icon="rocket")
    config = _base_config(tmp_path / "v_bar_icon.svg")
    set_fields(config, timeline_duration_icon_visible=True)
    config, renderer, bars = _vertical_bars(
        tmp_path,
        "v_bar_icon.svg",
        [event],
        config=config,
        renderer=_CaptureOverflowRenderer(),
    )
    assert not bars[0].text_overflow
    renderer._draw_duration(config, bars[0], _vaxis(200.0))

    icons = [c for c in renderer.icon_calls if c.get("css_class") == "ec-duration-icon"]
    assert [c["icon"] for c in icons] == ["rocket"]
    # Upright, in the first column — the bar's start end, over the start date.
    assert icons[0].get("transform") is None
    assert icons[0]["y"] < (bars[0].start_y + bars[0].end_y) / 2.0


def test_a_vertical_duration_bar_leaves_the_icon_out_when_told_to(tmp_path):
    event = Event(task_name="Build", start="20260210", end="20260501", icon="rocket")
    config = _base_config(tmp_path / "v_bar_noicon.svg")
    set_fields(config, timeline_duration_icon_visible=False)
    config, renderer, bars = _vertical_bars(
        tmp_path,
        "v_bar_noicon.svg",
        [event],
        config=config,
        renderer=_CaptureOverflowRenderer(),
    )
    renderer._draw_duration(config, bars[0], _vaxis(200.0))
    assert [c for c in renderer.icon_calls if c.get("css_class") == "ec-duration-icon"] == []


def test_the_callout_stack_is_measured_on_the_side_it_uses(tmp_path):
    renderer = TimelineRenderer()
    low, high = 100.0, 400.0
    # Horizontal: primary is above, i.e. the low side.
    assert renderer._callout_room(Orientation.HORIZONTAL, Side.PRIMARY, low, high) == low
    assert renderer._callout_room(Orientation.HORIZONTAL, Side.SECONDARY, low, high) == high
    # Vertical: primary is the right — the high side.
    assert renderer._callout_room(Orientation.VERTICAL, Side.PRIMARY, low, high) == high
    assert renderer._callout_room(Orientation.VERTICAL, Side.SECONDARY, low, high) == low
    # A stack on each side has to fit the smaller of the two.
    for orient in (Orientation.HORIZONTAL, Orientation.VERTICAL):
        assert renderer._callout_room(orient, Side.BOTH, low, high) == low


# ── The rest of the furniture on a vertical axis ──────────────────────────
#
# Fiscal bands, the today marker, holiday icons and timebands were all
# horizontal-only: the draw pass skipped them outright on a vertical axis.


def _vertical_render_args(config, renderer):
    renderer._page_width, renderer._page_height = config.pageX, config.pageY
    return (
        arrow.get("20260201", "YYYYMMDD"),
        arrow.get("20260430", "YYYYMMDD"),
    )


# ── Sides of a vertical axis ──────────────────────────────────────────────
#
# A horizontal timeline spends its two sides on callouts above and bars
# below. The vertical port put both on whatever side `label_side` named, so
# the bars ended up under the callout boxes.


def test_bars_take_the_side_the_callouts_did_not(tmp_path):
    config = _base_config(tmp_path / "sides.svg")
    renderer = TimelineRenderer()

    set_fields(config, timeline_label_side="primary")
    assert renderer._duration_side(config, Side.PRIMARY) is Side.SECONDARY
    set_fields(config, timeline_label_side="secondary")
    assert renderer._duration_side(config, Side.SECONDARY) is Side.PRIMARY


def test_callouts_on_both_sides_leave_the_bars_on_both(tmp_path):
    """Nothing to be opposite of; the bars keep splitting as they did."""
    config = _base_config(tmp_path / "sides_both.svg")
    assert TimelineRenderer()._duration_side(config, Side.BOTH) is Side.BOTH


def test_a_theme_can_pin_the_bars_to_one_side(tmp_path):
    config = _base_config(tmp_path / "sides_pinned.svg")
    set_fields(config, timeline_duration_side="primary")
    renderer = TimelineRenderer()
    # Same side as the callouts, because the theme asked for it.
    assert renderer._duration_side(config, Side.PRIMARY) is Side.PRIMARY


def test_an_unknown_duration_side_is_rejected(tmp_path):
    config = _base_config(tmp_path / "sides_bad.svg")
    with pytest.raises(ValueError, match="duration_side"):
        update_theme(config, timeline={"duration_side": "sideways"})


def test_a_bare_vertical_axis_is_placed_by_where_the_bars_went(tmp_path):
    """--noevents leaves only the bars, so they get the width.

    The placement used to key off `label_side`, which is where the callouts
    would have gone; once the bars moved to the opposite side that pushed
    them into a tenth of the page.
    """
    config = _base_config(tmp_path / "v_noevents.svg")
    set_orientation(config, "vertical")
    config.includeevents = False
    renderer = _CaptureTimelineRenderer()
    renderer._page_width, renderer._page_height = config.pageX, config.pageY

    coords = {"TimelineArea": (0.0, 0.0, 1000.0, 700.0)}
    renderer._drawing = drawsvg.Drawing(config.pageX, config.pageY)
    renderer._render_content(
        config,
        coords,
        [{"Task_Name": "Build", "Start": "20260210", "End": "20260320", "WBS": "1.1"}],
        _DummyDB(),
    )
    axis = re.findall(r'<path d="M ([\d.-]+) [\d.-]+ L \1 [\d.-]+"[^>]*class="ec-axis-line"', renderer.drawing.as_svg())
    assert axis, "expected a vertical axis line"
    axis_x = float(axis[0])
    bars = [c for c in renderer.rect_calls if c.get("css_class") == "ec-duration-bar"]
    assert bars
    # Bars stack left of the axis, so the axis is over on the right.
    assert axis_x > 700.0
    assert all(b["x"] < axis_x for b in bars)


# ── A horizontal axis spends its sides the way a vertical one does ─────────


def test_horizontal_bars_on_the_primary_side_stack_above_the_axis(tmp_path):
    config = _base_config(tmp_path / "h_bars_above.svg")
    renderer = _CaptureTimelineRenderer()
    renderer._page_width, renderer._page_height = config.pageX, config.pageY
    frame = _hframe(arrow.get("20260101", "YYYYMMDD"), arrow.get("20260630", "YYYYMMDD"), 50.0, 700.0, 300.0)
    events = [
        Event(task_name="Build", start="20260210", end="20260320"),
        Event(task_name="Test", start="20260301", end="20260410"),
    ]
    bars = renderer._layout_durations(config, events, frame, Side.PRIMARY)
    assert {b.lane_side for b in bars} == {Side.PRIMARY}
    for bar in bars:
        renderer._draw_duration(config, bar, frame)
    rects = [r for r in renderer.rect_calls if r.get("css_class") == "ec-duration-bar"]
    assert len(rects) == 2
    assert all(r["y"] + r["h"] < 300.0 for r in rects)


# ── The shared timescale beside and around the axis ────────────────────────
#
# A row with a tick facet draws ticks and labels beside the axis on its side,
# a holiday row draws icons with their dates, and every other row is a band
# at the page edge.  Primary is above a horizontal axis and right of a
# vertical one.

MONTH_TICKS = {"label": "Month", "unit": "month", "date_format": "MMM", "height": 18, "tick": {"length": 6}}


def _render_timescale(tmp_path, *, primary=(), secondary=(), vertical=False, db=None, theme=None, events=()):
    tmp_path.mkdir(parents=True, exist_ok=True)
    output = tmp_path / "timeline_scale.svg"
    config = _base_config(output)
    config.adjustedstart = config.userstart = "20260101"
    config.adjustedend = config.userend = "20260630"
    update_theme(config, today={"show": False}, **(theme or {}))
    set_bands(config, primary=list(primary), secondary=list(secondary))
    if vertical:
        set_orientation(config, "vertical")
    renderer = _CaptureHolidayRenderer()
    renderer.render(config, TimelineLayout().calculate(config), list(events), db or _DummyDB())
    return config, renderer, output.read_text()


def _paths(svg, css_class):
    """``(x1, y1, x2, y2)`` of every straight path of *css_class*."""
    pat = rf'<path d="M ([\d.-]+) ([\d.-]+) L ([\d.-]+) ([\d.-]+)"[^>]*class="{css_class}"'
    return [tuple(map(float, m)) for m in re.findall(pat, svg)]


def _axis(svg):
    (line,) = _paths(svg, "ec-axis-line")
    return line


def test_a_tick_row_draws_a_tick_and_a_label_for_each_month(tmp_path):
    _config, renderer, svg = _render_timescale(tmp_path, primary=[MONTH_TICKS])
    ticks = _paths(svg, "ec-axis-tick")
    assert len(ticks) == 6  # Jan - Jun
    labels = [c["text"] for c in renderer.text_calls if c.get("css_class") == "ec-tick-label"]
    assert labels == ["Jan", "Feb", "Mar", "Apr", "May", "Jun"]


def test_a_primary_tick_row_is_above_a_horizontal_axis_and_a_secondary_one_below(tmp_path):
    _c, _r, svg = _render_timescale(tmp_path, primary=[MONTH_TICKS], secondary=[MONTH_TICKS])
    axis_y = _axis(svg)[1]
    ticks = _paths(svg, "ec-axis-tick")
    assert len(ticks) == 12
    above = [t for t in ticks if t[3] < axis_y]
    below = [t for t in ticks if t[3] > axis_y]
    assert len(above) == len(below) == 6
    assert all(t[1] == axis_y and abs(t[3] - axis_y) == pytest.approx(6.0) for t in ticks)


def test_a_primary_tick_row_is_right_of_a_vertical_axis(tmp_path):
    _c, renderer, svg = _render_timescale(tmp_path, primary=[MONTH_TICKS], vertical=True)
    axis_x = _axis(svg)[0]
    ticks = _paths(svg, "ec-axis-tick")
    assert len(ticks) == 6 and all(t[2] > axis_x and t[1] == t[3] for t in ticks)
    labels = [c for c in renderer.text_calls if c.get("css_class") == "ec-tick-label"]
    assert labels and all(c["x"] > axis_x for c in labels)


def test_holiday_marks_show_each_flag_with_its_date(tmp_path):
    db = _HolidayDB(["20260216", "20260406"])
    _c, renderer, _svg = _render_timescale(tmp_path, primary=[{"label": "Holidays", "unit": "holiday"}], db=db)
    assert [c["icon"] for c in renderer.icon_calls] == ["flag-us", "flag-us"]
    dates = [c["text"] for c in renderer.text_calls if c.get("css_class") == "ec-holiday-date"]
    assert dates == ["2/16", "4/6"]


def test_holiday_marks_can_drop_their_dates_or_vanish(tmp_path):
    db = _HolidayDB(["20260216"])
    rows = [{"label": "Holidays", "unit": "holiday"}]
    _c, no_dates, _s = _render_timescale(tmp_path / "a", primary=rows, db=db, theme={"holidays": {"show_dates": False}})
    assert no_dates.icon_calls and not [c for c in no_dates.text_calls if c.get("css_class") == "ec-holiday-date"]
    _c, none, _s = _render_timescale(tmp_path / "b", primary=rows, db=db, theme={"holidays": {"show_icons": False}})
    assert none.icon_calls == []


def test_holiday_marks_follow_their_side_of_the_axis(tmp_path):
    db = _HolidayDB(["20260216"])
    rows = [{"label": "Holidays", "unit": "holiday"}]
    _c, up, up_svg = _render_timescale(tmp_path / "a", primary=rows, db=db)
    _c, down, down_svg = _render_timescale(tmp_path / "b", secondary=rows, db=db)
    assert (
        up.icon_calls[0]["y"] < _axis(up_svg)[1] < down.icon_calls[0]["y"] - 0
        or down.icon_calls[0]["y"] > _axis(down_svg)[1]
    )
    assert up.icon_calls[0]["y"] < _axis(up_svg)[1]
    assert down.icon_calls[0]["y"] > _axis(down_svg)[1]


def test_rows_without_a_tick_facet_are_bands_at_the_page_edges(tmp_path):
    band = {"label": "Quarter", "unit": "quarter", "height": 14}
    config, renderer, _svg = _render_timescale(tmp_path, primary=[band], secondary=[band])
    area_y, area_h = TimelineLayout().calculate(config)["TimelineArea"][1::2]
    cells = [r for r in renderer.rect_calls if r.get("css_class") == "ec-band-cell"]
    assert min(c["y"] for c in cells) == pytest.approx(area_y)
    assert max(c["y"] + c["h"] for c in cells) == pytest.approx(area_y + area_h)


def test_edge_bands_are_columns_beside_a_vertical_axis(tmp_path):
    band = {"label": "Quarter", "unit": "quarter", "height": 14}
    config, renderer, _svg = _render_timescale(tmp_path, primary=[band], secondary=[band], vertical=True)
    area_x, area_w = TimelineLayout().calculate(config)["TimelineArea"][0::2]
    cells = [r for r in renderer.rect_calls if r.get("css_class") == "ec-band-cell"]
    assert min(c["x"] for c in cells) == pytest.approx(area_x)  # the secondary column, on the left
    assert max(c["x"] + c["w"] for c in cells) == pytest.approx(area_x + area_w)  # the primary column, on the right
    assert all(c["w"] == pytest.approx(14.0) for c in cells)


def test_the_edge_bands_move_the_axis_in_from_the_page_edge(tmp_path):
    band = {"label": "Quarter", "unit": "quarter", "height": 40}
    _c, _r, with_bands = _render_timescale(tmp_path / "a", primary=[band])
    _c, _r, without = _render_timescale(tmp_path / "b")
    # A 40 point stack at the top shrinks the room above the axis, and the axis sits at 44% of what is left.
    assert _axis(with_bands)[1] > _axis(without)[1]


def test_callouts_start_beyond_the_rows_beside_the_axis(tmp_path):
    ev = {"Task_Name": "Go", "Start": "20260301", "End": "20260301", "Milestone": 1}
    _c, renderer, svg = _render_timescale(tmp_path / "a", primary=[MONTH_TICKS], events=[ev])
    axis_y = _axis(svg)[1]
    box = next(r for r in renderer.rect_calls if r.get("css_class") == "ec-callout-box")
    assert axis_y - (box["y"] + box["h"]) >= 18.0 - 0.01  # the month row's height


def test_bars_clear_the_rows_beside_the_axis_on_their_side(tmp_path):
    ev = {"Task_Name": "Build", "Start": "20260210", "End": "20260320", "WBS": "1"}
    holidays = {"label": "Holidays", "unit": "holiday"}
    _c, with_marks, svg = _render_timescale(
        tmp_path / "a", secondary=[holidays], db=_HolidayDB(["20260216"]), events=[ev]
    )
    _c, plain, svg_plain = _render_timescale(tmp_path / "b", events=[ev])
    bar = lambda r: min(b["y"] for b in r.rect_calls if b.get("css_class") == "ec-duration-bar")  # noqa: E731
    assert bar(with_marks) - _axis(svg)[1] >= bar(plain) - _axis(svg_plain)[1]
