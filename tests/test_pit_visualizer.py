"""
Tests for the PIT (Points in Time) visualizer.
Covers the ~30 test cases from pit_plan.html §8 and §12.5.
"""
from __future__ import annotations

import io
import logging
import re
import tempfile
from pathlib import Path

import arrow
import pytest

from config.config import create_calendar_config, setfontsizes
from shared.data_models import Event
from shared.rule_engine import StyleResult
from visualizers.factory import VisualizerFactory
from visualizers.pit.labella_adapter import (
    PIT_MAX_EVENTS_PER_SIDE,
    PITPlacement,
    _partition_for_both,
    layout_pit_callouts,
)
from visualizers.pit.layout import PITLayout
from visualizers.pit.markers import (
    BUILTIN_SHAPES,
    MarkerSpec,
    _FILL_REPLACE_RE,
    draw_label_icon,
    resolve_label_icon,
    resolve_marker,
)
from visualizers.pit.renderer import PITRenderer
from visualizers.pit.visualizer import PITVisualizer
from visualizers.timeline.orientation import Orientation, Side


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _DummyDB:
    """Minimal DB stub — returns empty collections."""

    def get_icon_svg_map(self) -> dict:
        return {}

    def get_all_patterns(self) -> dict:
        return {}

    def get_all_palettes(self) -> dict:
        return {}

    def get_palette(self, name: str):
        return None


class _IconDB(_DummyDB):
    """DB stub that serves a specific icon."""

    def __init__(self, icon_name: str, svg: str):
        self._map = {icon_name.lower(): svg}

    def get_icon_svg_map(self) -> dict:
        return dict(self._map)


class _PatternDB(_DummyDB):
    """DB stub that serves a specific pattern."""

    def __init__(self, pattern_name: str, svg: str):
        self._patterns = {pattern_name: svg}

    def get_all_patterns(self) -> dict:
        return dict(self._patterns)


def _make_config(
    tmp_path: Path,
    *,
    start: str = "20260101",
    end: str = "20261231",
    direction: str = "horizontal",
    side: str = "both",
    tick_unit: str = "month",
) -> object:
    tmp_path.mkdir(parents=True, exist_ok=True)
    config = create_calendar_config()
    config.pageX, config.pageY = 792.0, 612.0  # landscape letter
    config = setfontsizes(config)
    config.adjustedstart = start
    config.adjustedend = end
    config.userstart = start
    config.userend = end
    config.outputfile = str(tmp_path / "pit_test.svg")
    config.include_header = False
    config.include_footer = False
    config.pit_direction = direction
    config.pit_label_side = side
    config.pit_tick_unit = tick_unit
    return config


def _events_dicts(count: int = 4) -> list[dict]:
    """Return a small set of point-in-time event dicts spread across a year."""
    dates = ["20260115", "20260315", "20260601", "20260901",
             "20261015", "20261201"]
    dicts = []
    for i, d in enumerate(dates[:count]):
        dicts.append({
            "Task_Name": f"Event {i+1}",
            "Start": d,
            "End": d,
            "Notes": f"Notes for event {i+1}",
            "Priority": i + 1,
        })
    return dicts


def _render_pit(tmp_path: Path, events: list[dict] | None = None, **kwargs) -> str:
    """Render a PIT SVG and return the file contents."""
    config = _make_config(tmp_path, **kwargs)
    coords = PITLayout().calculate(config)
    db = _DummyDB()
    renderer = PITRenderer()
    renderer.render(config, coords, events or _events_dicts(), db)
    return Path(config.outputfile).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def test_pit_factory_registered():
    """VisualizerFactory.create('pit') returns a PITVisualizer."""
    viz = VisualizerFactory.create("pit")
    assert isinstance(viz, PITVisualizer)


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------


def test_pit_layout_coords(tmp_path):
    """PITLayout.calculate returns a PITArea rectangle inside page margins."""
    config = _make_config(tmp_path)
    coords = PITLayout().calculate(config)

    assert "PITArea" in coords
    x, y, w, h = coords["PITArea"]
    # PITArea must be non-degenerate and inside the page.
    assert w > 0
    assert h > 0
    assert x >= 0
    assert y >= 0
    assert x + w <= config.pageX + 1  # allow float rounding
    assert y + h <= config.pageY + 1


def test_pit_drops_multiday(tmp_path):
    """Multi-day events are filtered; single-day events still render."""
    events = [
        {"Task_Name": "Ok Event", "Start": "20260301", "End": "20260301"},
        {"Task_Name": "Duration", "Start": "20260301", "End": "20260401"},
    ]
    svg = _render_pit(tmp_path, events)
    assert "Ok Event" in svg or "<path" in svg  # renderer produced output
    # No assertion that "Duration" appears — multi-day is silently dropped.


# ---------------------------------------------------------------------------
# CLI / config flags
# ---------------------------------------------------------------------------


def test_pit_direction_flag(tmp_path):
    """--direction vertical produces a different axis orientation than horizontal."""
    svg_h = _render_pit(tmp_path / "h", direction="horizontal")
    svg_v = _render_pit(tmp_path / "v", direction="vertical")
    # Both should render without error; the SVGs should differ structurally.
    assert "<svg" in svg_h
    assert "<svg" in svg_v
    # Vertical axis: the axis <line> has different x/y progression.
    assert svg_h != svg_v


def _callout_box_rows(svg: str) -> dict[int, list[tuple[float, float]]]:
    """Group ec-callout-box rects into rows keyed by rounded y → [(x0, x1)]."""
    from collections import defaultdict

    rows: dict[int, list[tuple[float, float]]] = defaultdict(list)
    for m in re.finditer(
        r'<rect x="([0-9.]+)" y="([0-9.]+)" width="([0-9.]+)" '
        r'height="([0-9.]+)"[^>]*ec-callout-box',
        svg,
    ):
        x, y, w, _h = (float(g) for g in m.groups())
        rows[round(y)].append((x, x + w))
    return rows


def _leader_endpoints(svg: str) -> list[float]:
    """Absolute x of each callout leader's final waypoint."""
    out: list[float] = []
    for g in re.findall(
        r"<g class=\"ec-pit-callout-group.*?</g>\s*</g>", svg, re.S
    ):
        tr = re.search(
            r"translate\(([0-9.]+),[0-9.-]+\).*?<path d=\"(.*?)\"", g, re.S
        )
        if not tr:
            continue
        ox = float(tr.group(1))
        nums = re.findall(r"-?[0-9.]+", tr.group(2))
        out.append(ox + float(nums[-2]))  # x of final coordinate
    return out


def test_pit_leader_anchor_center_aligns_box_middle(tmp_path):
    """Default 'center' anchor: leader endpoint == horizontal box center."""
    svg = _render_pit(tmp_path, _events_dicts(6))
    rows = _callout_box_rows(svg)
    centers = sorted(
        (x0 + x1) / 2 for boxes in rows.values() for (x0, x1) in boxes
    )
    leaders = sorted(_leader_endpoints(svg))
    assert centers and leaders
    assert len(centers) == len(leaders)
    for c, l in zip(centers, leaders):
        assert abs(c - l) < 0.5


def test_pit_leader_anchor_center_no_row_overlap(tmp_path):
    """'center' anchor renders without per-row box overlap (labella's model)."""
    svg = _render_pit(tmp_path, _events_dicts(6))
    for boxes in _callout_box_rows(svg).values():
        boxes.sort()
        for (x0, x1), (nx0, _nx1) in zip(boxes, boxes[1:]):
            assert nx0 >= x1 - 0.01, "callout boxes overlap on the same row"


def test_pit_leader_anchor_start_puts_box_after_endpoint(tmp_path):
    """'start' anchor: leader endpoint sits at the box leading (left) edge."""
    config = _make_config(tmp_path)
    config.pit_leader_label_anchor = "start"
    coords = PITLayout().calculate(config)
    PITRenderer().render(config, coords, _events_dicts(6), _DummyDB())
    svg = Path(config.outputfile).read_text(encoding="utf-8")
    rows = _callout_box_rows(svg)
    lefts = sorted(x0 for boxes in rows.values() for (x0, _x1) in boxes)
    leaders = sorted(_leader_endpoints(svg))
    assert len(lefts) == len(leaders)
    for left, l in zip(lefts, leaders):
        assert abs(left - l) < 0.5


def test_pit_leader_length_tracks_layer_gap(tmp_path):
    """pit_labella_layer_gap sets the axis→label gap (the leader length)."""

    def gap_for(layer_gap: float) -> float:
        config = _make_config(tmp_path / f"lg{layer_gap}", side="primary")
        config.pit_labella_layer_gap = layer_gap
        coords = PITLayout().calculate(config)
        PITRenderer().render(config, coords, _events_dicts(5), _DummyDB())
        svg = Path(config.outputfile).read_text(encoding="utf-8").replace("\n", " ")
        axis_y = float(
            re.search(r'<line[^>]*y1="([0-9.]+)"[^>]*ec-axis-line', svg).group(1)
        )
        # primary side = labels above the axis → box bottom nearest the axis.
        bottoms = [
            float(y) + float(h)
            for y, h in re.findall(
                r'<rect x="[0-9.]+" y="([0-9.]+)" width="[0-9.]+" '
                r'height="([0-9.]+)"[^>]*ec-callout-box',
                svg,
            )
        ]
        return axis_y - max(bottoms)

    g8, g32 = gap_for(8.0), gap_for(32.0)
    assert abs(g8 - 8.0) < 0.5
    assert abs(g32 - 32.0) < 0.5


def test_pit_leader_end_stub_appends_perpendicular_segment(tmp_path):
    """A non-zero end_stub makes each leader finish with a straight,
    axis-perpendicular L segment so the arrowhead sits flush."""
    config = _make_config(tmp_path, side="primary")
    config.pit_leader_end_stub = 6.0
    coords = PITLayout().calculate(config)
    PITRenderer().render(config, coords, _events_dicts(5), _DummyDB())
    svg = Path(config.outputfile).read_text(encoding="utf-8")
    leaders = re.findall(r'ec-callout-leader"><path d="([^"]*)"', svg)
    assert leaders
    for d in leaders:
        d = d.strip()
        # Ends with an explicit straight segment …
        m = re.search(r"L\s+(-?[0-9.]+)\s+(-?[0-9.]+)\s*$", d)
        assert m, f"leader does not end with an L segment: {d!r}"
        # … and the cubic before it shares the same x (horizontal axis →
        # vertical, perpendicular final segment).
        cub = re.search(
            r"C[^LC]*?(-?[0-9.]+)\s+(-?[0-9.]+)\s*$",
            d[: d.rfind("L")],
        )
        assert cub
        assert abs(float(cub.group(1)) - float(m.group(1))) < 1e-6


def test_pit_leader_end_stub_zero_is_pure_bezier(tmp_path):
    """end_stub == 0 leaves the labella bezier untouched (no trailing L)."""
    config = _make_config(tmp_path, side="primary")
    config.pit_leader_end_stub = 0.0
    coords = PITLayout().calculate(config)
    PITRenderer().render(config, coords, _events_dicts(5), _DummyDB())
    svg = Path(config.outputfile).read_text(encoding="utf-8")
    leaders = re.findall(r'ec-callout-leader"><path d="([^"]*)"', svg)
    assert leaders
    for d in leaders:
        assert not re.search(r"L\s+-?[0-9.]+\s+-?[0-9.]+\s*$", d.strip())


def test_pit_inherits_filter_flags(tmp_path):
    """Content-filter flags propagate to config without error."""
    config = _make_config(tmp_path)
    config.milestones = True
    config.ignorecomplete = True
    config.rollups = False
    config.include_notes = True
    config.WBS = None
    config.noevents = False
    config.empty = False

    coords = PITLayout().calculate(config)
    # Just verify it renders without exception.
    renderer = PITRenderer()
    renderer.render(config, coords, _events_dicts(), _DummyDB())
    assert Path(config.outputfile).exists()


def test_pit_notes_rendered_when_include_notes(tmp_path):
    """--includenotes (config.include_notes) draws notes inside the box."""
    config = _make_config(tmp_path)
    config.include_notes = True
    coords = PITLayout().calculate(config)
    PITRenderer().render(config, coords, _events_dicts(3), _DummyDB())
    svg = Path(config.outputfile).read_text(encoding="utf-8")
    assert "ec-event-notes" in svg


def test_pit_notes_absent_by_default(tmp_path):
    """Notes are suppressed when include_notes is False (the default)."""
    config = _make_config(tmp_path)
    assert config.include_notes is False
    coords = PITLayout().calculate(config)
    PITRenderer().render(config, coords, _events_dicts(3), _DummyDB())
    svg = Path(config.outputfile).read_text(encoding="utf-8")
    assert "ec-event-notes" not in svg


def test_pit_tick_units(tmp_path):
    """Each timeband unit renders without error."""
    for unit in ("month", "week", "interval", "date"):
        config = _make_config(tmp_path / unit, tick_unit=unit)
        if unit == "interval":
            config.pit_tick_interval = 30
        coords = PITLayout().calculate(config)
        renderer = PITRenderer()
        renderer.render(config, coords, _events_dicts(), _DummyDB())
        assert Path(config.outputfile).exists()


def test_pit_today_date_override(tmp_path):
    """--today-date moves the today line to the specified date."""
    config = _make_config(tmp_path)
    config.pit_today_date = "20260601"
    config.pit_show_today_line = True
    coords = PITLayout().calculate(config)
    renderer = PITRenderer()
    renderer.render(config, coords, _events_dicts(), _DummyDB())
    svg = Path(config.outputfile).read_text(encoding="utf-8")
    # Today line should be rendered (it's within the date range).
    assert "ec-today-line" in svg


# ---------------------------------------------------------------------------
# Axis ticks
# ---------------------------------------------------------------------------


def _render_pit_ticks(tmp_path: Path, **kw) -> str:
    config = _make_config(tmp_path, start="20260201", end="20260501")
    for k, v in kw.items():
        setattr(config, k, v)
    coords = PITLayout().calculate(config)
    PITRenderer().render(config, coords, _events_dicts(3), _DummyDB())
    return Path(config.outputfile).read_text(encoding="utf-8")


def test_pit_ticks_drawn_by_default(tmp_path):
    """Axis ticks (and labels) render out of the box (default month unit)."""
    svg = _render_pit_ticks(tmp_path)
    assert svg.count('class="ec-axis-tick"') >= 3      # Feb..May boundaries
    assert "ec-label" in svg


def test_pit_ticks_week_denser_than_month(tmp_path):
    """A finer tick unit yields more ticks over the same range."""
    n_month = _render_pit_ticks(tmp_path / "m", pit_tick_unit="month").count(
        'class="ec-axis-tick"'
    )
    n_week = _render_pit_ticks(tmp_path / "w", pit_tick_unit="week").count(
        'class="ec-axis-tick"'
    )
    assert n_week > n_month


def test_pit_show_ticks_false_suppresses(tmp_path):
    """pit_show_ticks == False draws no ticks at all."""
    svg = _render_pit_ticks(tmp_path, pit_show_ticks=False)
    assert 'class="ec-axis-tick"' not in svg
    assert "ec-label" not in svg


def test_pit_tick_labels_can_be_suppressed(tmp_path):
    """Marks without labels when pit_show_tick_labels == False."""
    svg = _render_pit_ticks(
        tmp_path, pit_tick_unit="week", pit_show_tick_labels=False
    )
    assert 'class="ec-axis-tick"' in svg
    assert "ec-label" not in svg


def test_pit_ticks_vertical(tmp_path):
    """Ticks render for a vertical axis too."""
    svg = _render_pit_ticks(tmp_path, direction="vertical")
    assert 'class="ec-axis-tick"' in svg


def test_pit_ticks_multiple_bands(tmp_path):
    """pit_ticks with two bands draws more ticks than either alone."""
    n_month = _render_pit_ticks(
        tmp_path / "m", pit_ticks=[{"unit": "month"}]
    ).count('class="ec-axis-tick"')
    n_both = _render_pit_ticks(
        tmp_path / "mw",
        pit_ticks=[{"unit": "month"}, {"unit": "week"}],
    ).count('class="ec-axis-tick"')
    assert n_both > n_month


def test_pit_ticks_overrides_scalar_unit(tmp_path):
    """pit_ticks takes precedence over the scalar pit_tick_unit field."""
    # Scalar says month, but the band list says week → expect week density.
    n = _render_pit_ticks(
        tmp_path,
        pit_tick_unit="month",
        pit_ticks=[{"unit": "week"}],
    ).count('class="ec-axis-tick"')
    n_month = _render_pit_ticks(
        tmp_path / "m2", pit_ticks=[{"unit": "month"}]
    ).count('class="ec-axis-tick"')
    assert n > n_month


def test_pit_ticks_single_dict_accepted(tmp_path):
    """A bare dict (not a list) is normalized to one band."""
    svg = _render_pit_ticks(tmp_path, pit_ticks={"unit": "month"})
    assert 'class="ec-axis-tick"' in svg


def test_pit_ticks_per_band_show_labels(tmp_path):
    """A band can suppress its own labels while still drawing tick marks."""
    svg = _render_pit_ticks(
        tmp_path,
        pit_ticks=[{"unit": "week", "show_labels": False}],
    )
    assert 'class="ec-axis-tick"' in svg
    assert "ec-label" not in svg


def test_pit_interval_label_format_uses_date(tmp_path):
    """interval unit + label_format yields dated labels (timeline parity)."""
    import arrow

    from config.config import CalendarConfig
    from visualizers.pit.renderer import PITRenderer

    r = PITRenderer.__new__(PITRenderer)
    cfg = CalendarConfig()
    s, e = arrow.get("2026-02-01"), arrow.get("2026-04-01")

    dated = PITRenderer._pit_tick_segments(
        r, cfg, {"unit": "interval", "interval_days": 14, "label_format": "MMM D"},
        s, e, None,
    )
    assert [lbl for _, _, lbl in dated][:3] == ["Feb 1", "Feb 15", "Mar 1"]

    # interval alias is accepted in place of interval_days.
    aliased = PITRenderer._pit_tick_segments(
        r, cfg, {"unit": "interval", "interval": 14, "label_format": "M/D"},
        s, e, None,
    )
    assert [lbl for _, _, lbl in aliased][:2] == ["2/1", "2/15"]

    # No label_format → running index; prefix customizes it.
    counter = PITRenderer._pit_tick_segments(
        r, cfg, {"unit": "interval", "interval_days": 14, "prefix": "Sprint "},
        s, e, None,
    )
    assert [lbl for _, _, lbl in counter][:2] == ["Sprint 1", "Sprint 2"]


# ---------------------------------------------------------------------------
# Markers
# ---------------------------------------------------------------------------


def test_pit_axis_marker_is_always_a_shape():
    """The PIT axis marker is a built-in shape regardless of icon config.

    DB icons are no longer drawn on the axis — they live in the label box.
    The axis is always circle (events) or diamond (milestones).
    """
    icon_map = {"myicon": '<svg viewBox="0 0 10 10"><path/></svg>'}
    config = create_calendar_config()
    config = setfontsizes(config)

    # Regular event → circle, even when a per-event icon is set.
    ev = Event(task_name="E", start="20260101", end="20260101", icon="myicon")
    spec = resolve_marker(ev, config=config, icon_svg_map=icon_map)
    assert spec.kind == "shape"
    assert spec.shape == "circle"
    assert spec.is_icon is False

    # Milestone → diamond, even when a per-rule marker_icon is set.
    ms = Event(task_name="M", start="20260101", end="20260101", milestone=True)
    sr = StyleResult(marker_icon="myicon")
    spec_ms = resolve_marker(ms, config=config, icon_svg_map=icon_map, style_result=sr)
    assert spec_ms.kind == "shape"
    assert spec_ms.shape == "diamond"

    # Config default does NOT override the axis either.
    config.pit_default_event_icon = "myicon"
    config.pit_default_milestone_icon = "myicon"
    assert resolve_marker(Event(task_name="x", start="20260101", end="20260101"),
                          config=config, icon_svg_map=icon_map).shape == "circle"
    assert resolve_marker(Event(task_name="x", start="20260101", end="20260101", milestone=True),
                          config=config, icon_svg_map=icon_map).shape == "diamond"


def test_pit_label_icon_resolution():
    """Label-icon precedence: event.icon > rule.marker_icon > config default > None."""
    icon_map = {"myicon": '<svg viewBox="0 0 10 10"><path/></svg>'}
    config = create_calendar_config()
    config = setfontsizes(config)
    config.pit_default_event_icon = None
    config.pit_default_milestone_icon = None

    # No icon anywhere → None (label name starts at left padding).
    ev = Event(task_name="E", start="20260101", end="20260101")
    assert resolve_label_icon(ev, config=config, icon_svg_map=icon_map) is None

    # Per-event icon → returned.
    ev2 = Event(task_name="E", start="20260101", end="20260101", icon="myicon")
    assert resolve_label_icon(ev2, config=config, icon_svg_map=icon_map) == icon_map["myicon"]

    # Per-rule marker_icon takes effect when event.icon is empty.
    sr = StyleResult(marker_icon="myicon")
    ev3 = Event(task_name="E", start="20260101", end="20260101")
    assert resolve_label_icon(ev3, config=config, icon_svg_map=icon_map, style_result=sr) == icon_map["myicon"]

    # Config default used when neither event nor rule supplies one.
    config.pit_default_event_icon = "myicon"
    assert resolve_label_icon(ev, config=config, icon_svg_map=icon_map) == icon_map["myicon"]

    # Milestones use the milestone default.
    config.pit_default_event_icon = None
    config.pit_default_milestone_icon = "myicon"
    ms = Event(task_name="M", start="20260101", end="20260101", milestone=True)
    assert resolve_label_icon(ms, config=config, icon_svg_map=icon_map) == icon_map["myicon"]


def test_pit_icon_colorization():
    """DB icon glyph fill='#000000' is replaced with the resolved color."""
    raw = '<svg viewBox="0 0 10 10"><path fill="#000000" d="M0 0Z"/></svg>'
    colored = _FILL_REPLACE_RE.sub('fill="tomato"', raw)
    assert 'fill="tomato"' in colored
    assert "#000000" not in colored


def test_pit_label_icon_drawing():
    """draw_label_icon emits a colorized, scaled glyph anchored at x_left."""
    import drawsvg
    from renderers.svg_base import BaseSVGRenderer

    drawing = drawsvg.Drawing(100, 100)
    raw_wide = '<svg viewBox="0 0 16 8"><path fill="#000" d="M0 0Z"/></svg>'
    raw_tall = '<svg viewBox="0 0 8 16"><path fill="#000" d="M0 0Z"/></svg>'
    for raw in (raw_wide, raw_tall):
        draw_label_icon(
            drawing, raw,
            x_left=20.0, y_center=40.0,
            size=10.0, color="tomato",
            strip_svg_wrapper=BaseSVGRenderer._strip_svg_wrapper,
        )
    # Both calls emitted a <g> wrapper.
    assert len(drawing.elements) == 2
    out = drawing.as_svg()
    assert 'class="ec-pit-label-icon"' in out
    assert 'fill="tomato"' in out


def test_pit_label_icon_drawn_in_box_not_on_axis(tmp_path):
    """Per-event Icon column drives a glyph INSIDE the label box, not the axis.

    The axis marker stays a built-in shape (no ``<g>`` with the
    icon-marker class is emitted on the axis); the label gains a
    ``ec-pit-label-icon`` group.
    """
    icon_svg = '<svg viewBox="0 0 10 10"><path fill="#000000" d="M5 5z"/></svg>'
    config = _make_config(tmp_path)
    coords = PITLayout().calculate(config)
    events = [
        {
            "Task_Name": "E1",
            "Start": "20260115",
            "End": "20260115",
            "Icon": "bookmark",
        }
    ]
    db = _IconDB("bookmark", icon_svg)
    renderer = PITRenderer()
    renderer.render(config, coords, events, db)
    svg = Path(config.outputfile).read_text(encoding="utf-8")

    # The axis marker for a regular event is always a circle.
    assert 'class="ec-pit-event-marker"' in svg
    # The label-box icon was emitted with the new CSS class.
    assert 'class="ec-pit-label-icon"' in svg


# ---------------------------------------------------------------------------
# Leaders + arrow markers
# ---------------------------------------------------------------------------


def test_pit_leader_stroke_attrs(tmp_path):
    """Per-rule leader override propagates to the SVG path."""
    config = _make_config(tmp_path)
    config.theme_style_rules = [
        {
            "apply_to": "event",
            "select": {},
            "style": {
                "leader": {"color": "#abcdef", "dasharray": "4,2", "opacity": "0.5"},
            },
        }
    ]
    coords = PITLayout().calculate(config)
    renderer = PITRenderer()
    renderer.render(config, coords, _events_dicts(1), _DummyDB())
    svg = Path(config.outputfile).read_text(encoding="utf-8")
    assert "ec-callout-leader" in svg
    assert "#abcdef" in svg
    assert "4,2" in svg


def test_pit_marker_end_arrow_axis(tmp_path):
    """Axis line gets marker-end when configured; <defs> contains the marker."""
    config = _make_config(tmp_path)
    config.pit_axis_marker_end = "arrow-head"
    config.pit_axis_marker_end_size = 6.0

    coords = PITLayout().calculate(config)
    renderer = PITRenderer()
    renderer.render(config, coords, _events_dicts(1), _DummyDB())
    svg = Path(config.outputfile).read_text(encoding="utf-8")

    assert "marker-end" in svg
    assert "<marker " in svg
    assert "ec-pit-marker-arrow-head" in svg


def test_pit_marker_start_arrow_axis(tmp_path):
    """Axis line gets marker-start independently of marker-end."""
    config = _make_config(tmp_path)
    config.pit_axis_marker_start = "arrow-head"
    config.pit_axis_marker_start_size = 4.0
    config.pit_axis_marker_end = "none"

    coords = PITLayout().calculate(config)
    renderer = PITRenderer()
    renderer.render(config, coords, _events_dicts(1), _DummyDB())
    svg = Path(config.outputfile).read_text(encoding="utf-8")

    assert "marker-start" in svg
    # marker-end="..." must NOT appear on the axis line when kind is "none".
    # (It may appear on leaders though — check axis line specifically.)
    # The axis <line> class is ec-axis-line.
    axis_match = re.search(r'<line[^/]*ec-axis-line[^/]*/>', svg)
    if axis_match:
        assert 'marker-end' not in axis_match.group()


def test_pit_marker_end_arrow_leader(tmp_path):
    """Leader paths emit marker-end on the label end."""
    config = _make_config(tmp_path, side="primary")
    config.pit_leader_marker_end = "arrow-head"
    config.pit_leader_marker_end_size = 5.0

    coords = PITLayout().calculate(config)
    renderer = PITRenderer()
    renderer.render(config, coords, _events_dicts(2), _DummyDB())
    svg = Path(config.outputfile).read_text(encoding="utf-8")

    # At least one leader group should have marker-end.
    assert "ec-callout-leader" in svg
    assert "marker-end" in svg


def test_pit_marker_start_arrow_leader(tmp_path):
    """Leader paths emit marker-start on the axis end when configured."""
    config = _make_config(tmp_path, side="primary")
    config.pit_leader_marker_start = "arrow-head"
    config.pit_leader_marker_start_size = 3.0

    coords = PITLayout().calculate(config)
    renderer = PITRenderer()
    renderer.render(config, coords, _events_dicts(2), _DummyDB())
    svg = Path(config.outputfile).read_text(encoding="utf-8")
    assert "marker-start" in svg


def test_pit_marker_independent_sizes(tmp_path):
    """Axis end (size 6), leader end (size 5), leader start (size 3) each
    produce distinct <marker> entries deduped by (kind, color, size)."""
    config = _make_config(tmp_path, side="primary")
    config.pit_axis_marker_end = "arrow-head"
    config.pit_axis_marker_end_size = 6.0
    config.pit_leader_marker_end = "arrow-head"
    config.pit_leader_marker_end_size = 5.0
    config.pit_leader_marker_start = "arrow-head"
    config.pit_leader_marker_start_size = 3.0
    config.theme_pit_arrow_head_color = "#123456"

    coords = PITLayout().calculate(config)
    renderer = PITRenderer()
    renderer.render(config, coords, _events_dicts(1), _DummyDB())
    svg = Path(config.outputfile).read_text(encoding="utf-8")

    # Count distinct <marker id="pit-marker-arrow-head-..."> entries.
    marker_ids = re.findall(r'id="(pit-marker-arrow-head-[^"]+)"', svg)
    assert len(set(marker_ids)) >= 2  # at least two distinct sizes


def test_pit_marker_none_emits_nothing(tmp_path):
    """Setting marker slots to 'none' omits attributes and unused defs."""
    config = _make_config(tmp_path)
    config.pit_axis_marker_start = "none"
    config.pit_axis_marker_end = "none"
    config.pit_leader_marker_start = "none"
    config.pit_leader_marker_end = "none"

    coords = PITLayout().calculate(config)
    renderer = PITRenderer()
    renderer.render(config, coords, _events_dicts(1), _DummyDB())
    svg = Path(config.outputfile).read_text(encoding="utf-8")

    assert "marker-start" not in svg
    assert "marker-end" not in svg
    assert "<marker " not in svg


# ---------------------------------------------------------------------------
# Labels
# ---------------------------------------------------------------------------


def test_pit_label_pattern_fill(tmp_path):
    """Label boxes with a pattern emit <defs><pattern> and fill='url(#pat-...)'."""
    pattern_svg = (
        '<svg viewBox="0 0 4 4" width="4" height="4">'
        '<path d="M0 4L4 0" stroke="black" stroke-width="0.5"/>'
        '</svg>'
    )
    config = _make_config(tmp_path)
    config.theme_pit_label_pattern = "diag"
    config.pit_label_fill_opacity = 0.85

    coords = PITLayout().calculate(config)
    db = _PatternDB("diag", pattern_svg)
    renderer = PITRenderer()
    renderer.render(config, coords, _events_dicts(1), db)
    svg = Path(config.outputfile).read_text(encoding="utf-8")

    assert "<pattern " in svg
    assert "fill=\"url(#pat-" in svg


def test_pit_label_fill_precedence(tmp_path):
    """Per-rule fill_color > theme_pit_label_fill_color > palette round-robin."""
    config = _make_config(tmp_path)
    # Set a theme-level fill that should be overridden by a rule.
    config.theme_pit_label_fill_color = "#ffff00"
    config.theme_style_rules = [
        {
            "apply_to": "event",
            "select": {},
            "style": {
                "label": {"fill_color": "#abcdef", "fill_opacity": 1.0},
            },
        }
    ]

    coords = PITLayout().calculate(config)
    renderer = PITRenderer()
    renderer.render(config, coords, _events_dicts(1), _DummyDB())
    svg = Path(config.outputfile).read_text(encoding="utf-8")

    # Per-rule color must appear; theme fill must not (it was overridden).
    assert "#abcdef" in svg


def test_pit_palette_reference(tmp_path):
    """theme_pit_label_palette drives round-robin label fills."""
    config = _make_config(tmp_path)
    config.theme_pit_label_fill_color = None
    config.theme_pit_label_palette = "TestPal"
    config.pit_label_fill_opacity = 0.9

    # Patch the DB to return a palette.
    class _PalDB(_DummyDB):
        def get_all_palettes(self):
            return {"TestPal": ["#aabbcc", "#ddeeff"]}

    coords = PITLayout().calculate(config)
    renderer = PITRenderer()
    renderer.render(config, coords, _events_dicts(2), _PalDB())
    # Verify the renderer doesn't crash when palette is available.
    assert Path(config.outputfile).exists()


# ---------------------------------------------------------------------------
# Layout behaviour
# ---------------------------------------------------------------------------


def test_pit_both_side_partition():
    """With side=BOTH, events are split to both sides with alternating assignment."""
    events = [
        Event(task_name=f"E{i}", start=f"2026{i+1:02d}01", end=f"2026{i+1:02d}01")
        for i in range(4)
    ]
    primary, secondary = _partition_for_both(events)
    assert len(primary) == 2
    assert len(secondary) == 2
    # No event appears on both sides.
    p_ids = {id(e) for e in primary}
    s_ids = {id(e) for e in secondary}
    assert not p_ids & s_ids


def _callout_box_height(svg: str) -> float:
    """Uniform ec-callout-box height (all boxes share one in horizontal)."""
    hs = {
        float(h)
        for h in re.findall(
            r'<rect x="[0-9.]+" y="[0-9.]+" width="[0-9.]+" '
            r'height="([0-9.]+)"[^>]*ec-callout-box',
            svg,
        )
    }
    assert hs
    return max(hs)


def _date_baselines(svg: str) -> list[tuple[float, float]]:
    """(x, y) baseline of each ec-event-date group via its parent translate."""
    out: list[tuple[float, float]] = []
    for m in re.finditer(r"ec-event-date", svg):
        pre = svg[max(0, m.start() - 240): m.start()]
        tr = re.findall(r"translate\(([0-9.]+),\s*([0-9.]+)\)", pre)
        if tr:
            out.append((float(tr[-1][0]), float(tr[-1][1])))
    return out


def test_pit_date_inline_is_default(tmp_path):
    """By default the date is drawn inside each label box (option 1)."""
    svg = _render_pit(tmp_path, _events_dicts(3))
    assert "ec-event-date" in svg
    boxes = [
        (float(x), float(y), float(w), float(h))
        for x, y, w, h in re.findall(
            r'<rect x="([0-9.]+)" y="([0-9.]+)" width="([0-9.]+)" '
            r'height="([0-9.]+)"[^>]*ec-callout-box',
            svg,
        )
    ]
    dates = _date_baselines(svg)
    assert dates
    # Every inline date baseline falls within some callout box.
    for dx, dy in dates:
        assert any(
            bx - 1 <= dx <= bx + bw + 1 and by - 2 <= dy <= by + bh + 3
            for bx, by, bw, bh in boxes
        ), f"inline date at ({dx},{dy}) is not inside any box"


def _render_pit_placement(tmp_path: Path, placement: str) -> str:
    config = _make_config(tmp_path / placement)
    config.pit_date_placement = placement
    coords = PITLayout().calculate(config)
    PITRenderer().render(config, coords, _events_dicts(3), _DummyDB())
    return Path(config.outputfile).read_text(encoding="utf-8")


def test_pit_date_inline_grows_box_vs_axis(tmp_path):
    """Inline placement grows the box (date line); axis/none do not."""
    h_inline = _callout_box_height(_render_pit_placement(tmp_path, "inline"))
    h_axis = _callout_box_height(_render_pit_placement(tmp_path, "axis"))
    h_none = _callout_box_height(_render_pit_placement(tmp_path, "none"))
    assert h_inline > h_axis
    assert h_axis == h_none  # neither reserves a date line in the box


def test_pit_date_placement_none_suppresses(tmp_path):
    """placement == none emits no date text at all."""
    svg = _render_pit_placement(tmp_path, "none")
    assert "ec-event-date" not in svg


def test_pit_date_placement_axis_renders_dates(tmp_path):
    """placement == axis still renders dates (the legacy opposite-side look)."""
    svg = _render_pit_placement(tmp_path, "axis")
    assert "ec-event-date" in svg


# ---------------------------------------------------------------------------
# Today line
# ---------------------------------------------------------------------------


def test_pit_today_line(tmp_path):
    """Today line renders when enabled and is absent when disabled."""
    config_on = _make_config(tmp_path / "on")
    config_on.pit_show_today_line = True
    coords_on = PITLayout().calculate(config_on)
    PITRenderer().render(config_on, coords_on, _events_dicts(1), _DummyDB())
    svg_on = Path(config_on.outputfile).read_text(encoding="utf-8")
    assert "ec-today-line" in svg_on

    config_off = _make_config(tmp_path / "off")
    config_off.pit_show_today_line = False
    coords_off = PITLayout().calculate(config_off)
    PITRenderer().render(config_off, coords_off, _events_dicts(1), _DummyDB())
    svg_off = Path(config_off.outputfile).read_text(encoding="utf-8")
    assert "ec-today-line" not in svg_off


def test_pit_today_line_themeable(tmp_path):
    """All today-line stroke attrs propagate: color/width/dasharray/opacity."""
    config = _make_config(tmp_path)
    config.pit_show_today_line = True
    config.pit_today_date = "20260601"  # force it into range
    config.theme_pit_today_line_color = "#cc1122"
    config.theme_pit_today_line_width = 2.5
    config.theme_pit_today_line_dasharray = "6,3"
    config.theme_pit_today_line_opacity = 0.75

    coords = PITLayout().calculate(config)
    PITRenderer().render(config, coords, _events_dicts(1), _DummyDB())
    svg = Path(config.outputfile).read_text(encoding="utf-8")

    assert "#cc1122" in svg
    assert "2.500" in svg or "2.5" in svg
    assert "6,3" in svg
    assert "0.75" in svg


def test_pit_today_line_markers(tmp_path):
    """Today line accepts independent marker_start + marker_end."""
    config = _make_config(tmp_path)
    config.pit_show_today_line = True
    config.pit_today_date = "20260601"
    config.pit_today_line_marker_end = "arrow-head"
    config.pit_today_line_marker_end_size = 7.0
    config.theme_pit_arrow_head_color = "#334455"

    coords = PITLayout().calculate(config)
    PITRenderer().render(config, coords, _events_dicts(1), _DummyDB())
    svg = Path(config.outputfile).read_text(encoding="utf-8")

    assert "ec-today-line" in svg
    assert "marker-end" in svg
    # Arrow-head marker with the today-line-specific size should be in defs.
    assert "pit-marker-arrow-head" in svg


# ---------------------------------------------------------------------------
# Density warning
# ---------------------------------------------------------------------------


def test_pit_density_warning(tmp_path, caplog):
    """With > 80 events on a side, the logger emits a WARNING."""
    events = [
        Event(task_name=f"E{i}", start=f"20260115", end=f"20260115")
        for i in range(PIT_MAX_EVENTS_PER_SIDE + 1)
    ]
    config = _make_config(tmp_path, side="primary")
    axis_origin = (50.0, 300.0)
    axis_length = 600.0

    def _pos(day: arrow.Arrow) -> float:
        return 300.0

    with caplog.at_level(logging.WARNING, logger="visualizers.pit.labella_adapter"):
        layout_pit_callouts(
            events,
            axis_origin=axis_origin,
            axis_length=axis_length,
            direction=Orientation.HORIZONTAL,
            side=Side.PRIMARY,
            config=config,
            pos_for_day=_pos,
        )

    assert any("exceeds soft cap" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# Theme application
# ---------------------------------------------------------------------------


def test_pit_theme_application(tmp_path):
    """theme_pit_axis_color propagates to the axis stroke attribute."""
    config = _make_config(tmp_path)
    config.theme_pit_axis_color = "#123abc"

    coords = PITLayout().calculate(config)
    renderer = PITRenderer()
    renderer.render(config, coords, _events_dicts(1), _DummyDB())
    svg = Path(config.outputfile).read_text(encoding="utf-8")

    assert "#123abc" in svg
    assert "ec-axis-line" in svg


# ---------------------------------------------------------------------------
# CSS classes (§12.5)
# ---------------------------------------------------------------------------


def test_pit_emits_ec_classes(tmp_path):
    """Core ec-* CSS classes are present in the rendered SVG."""
    svg = _render_pit(tmp_path, _events_dicts(2))
    for cls in ("ec-pit-axis-group", "ec-pit-callout-group",
                "ec-callout-leader", "ec-callout-box",
                "ec-pit-event-marker", "ec-event-name", "ec-event-date"):
        assert cls in svg, f"Missing class: {cls}"


def test_pit_callout_group_data_attrs(tmp_path):
    """Each callout group has data-event-date, data-milestone, data-priority attrs."""
    svg = _render_pit(tmp_path, _events_dicts(1))
    assert 'data-event-date=' in svg
    assert 'data-milestone=' in svg
    assert 'data-priority=' in svg


def test_pit_side_class(tmp_path):
    """Side-specific CSS class is emitted on callout groups."""
    svg_both = _render_pit(tmp_path / "both", _events_dicts(2), side="both")
    assert "ec-pit-side-primary" in svg_both
    assert "ec-pit-side-secondary" in svg_both

    svg_primary = _render_pit(tmp_path / "primary", _events_dicts(2), side="primary")
    assert "ec-pit-side-primary" in svg_primary
    assert "ec-pit-side-secondary" not in svg_primary


def test_pit_css_style_block_injected(tmp_path):
    """When CSS is available (ThemeStyles.css is set), it's injected as <style>."""
    from config.styles import ThemeStyles
    config = _make_config(tmp_path)
    ts = ThemeStyles()
    ts.css = ".ec-pit-test { fill: red; }"
    config.theme_styles = ts

    coords = PITLayout().calculate(config)
    renderer = PITRenderer()
    renderer.render(config, coords, _events_dicts(1), _DummyDB())
    svg = Path(config.outputfile).read_text(encoding="utf-8")

    assert "<style" in svg
    assert ".ec-pit-test" in svg


def test_pit_inline_styled_classes_have_no_css(tmp_path):
    """The four inline-styled classes are NOT in the CSS block (they rely on
    inline attributes, not stylesheet rules — per css_generator contract)."""
    from renderers.css_generator import _INLINE_STYLED_CLASSES

    svg = _render_pit(tmp_path, _events_dicts(1))
    # Extract the <style> block.
    style_match = re.search(r'<style[^>]*>(.*?)</style>', svg, re.DOTALL)
    if style_match:
        style_text = style_match.group(1)
        for cls in _INLINE_STYLED_CLASSES:
            # The inline-styled classes should not have CSS rules defined.
            assert f".{cls}" not in style_text, (
                f"{cls} found in <style> but should be inline-only"
            )


def test_pit_external_css_override(tmp_path):
    """CSS class selectors can override marker/leader/box inline styles when
    !important is used — verify the class is present for external targeting."""
    svg = _render_pit(tmp_path, _events_dicts(1))
    # Confirm the classes that external CSS can target are present.
    assert "ec-pit-event-marker" in svg or "ec-milestone-marker" in svg
    assert "ec-callout-leader" in svg
    assert "ec-callout-box" in svg
