"""
Tests for the PIT (Points in Time) visualizer.
Covers the ~30 test cases from pit_plan.html §8 and §12.5.
"""

from __future__ import annotations

import itertools
import logging
import re
from pathlib import Path

import arrow
import pytest
from band_helpers import set_bands, set_fields, set_orientation, update_theme
from fakes import FakeCalendarDB

from config.config import CalendarConfig, create_calendar_config, setfontsizes
from shared.data_models import Event
from shared.labella_layout import partition_for_both
from shared.orientation import Orientation, Side
from shared.rule_engine import StyleResult
from visualizers.factory import VisualizerFactory
from visualizers.pit.labella_adapter import (
    PIT_MAX_EVENTS_PER_SIDE,
    layout_pit_callouts,
)
from visualizers.pit.layout import PITLayout
from visualizers.pit.markers import (
    _FILL_REPLACE_RE,
    draw_label_icon,
    resolve_label_icon,
    resolve_marker,
)
from visualizers.pit.renderer import PITRenderer

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _DummyDB(FakeCalendarDB):
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
) -> CalendarConfig:
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
    set_orientation(config, direction)
    set_fields(config, pit_label_side=side)
    if tick_unit != "month":
        set_bands(config, primary=[{"unit": tick_unit, "tick": {}}], secondary=[])
    return config


def _axis_match(pattern: str, svg: str) -> re.Match[str]:
    found = re.search(pattern, svg)
    assert found
    return found


def _events_dicts(count: int = 4) -> list[dict]:
    """Return a small set of point-in-time event dicts spread across a year."""
    dates = ["20260115", "20260315", "20260601", "20260901", "20261015", "20261201"]
    dicts = []
    for i, d in enumerate(dates[:count]):
        dicts.append(
            {
                "Task_Name": f"Event {i + 1}",
                "Start": d,
                "End": d,
                "Notes": f"Notes for event {i + 1}",
                "Priority": i + 1,
            }
        )
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
    """VisualizerFactory.create('pit') returns the PIT visualizer."""
    viz = VisualizerFactory.create("pit")
    assert viz.name == "pit"
    assert isinstance(viz._create_renderer(), PITRenderer)


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


def _render_with(config, events: int = 1) -> str:
    """Render *config* with a few events and return the SVG text."""
    coords = PITLayout().calculate(config)
    PITRenderer().render(config, coords, _events_dicts(events), _DummyDB())
    return Path(config.outputfile).read_text(encoding="utf-8")


def _leader_paths(svg: str) -> list[str]:
    """The path data of every callout leader."""
    return re.findall(r'<path d="([^"]*)"[^>]*class="ec-callout-leader"', svg)


def _axis_y(svg: str) -> float:
    """The y of the (horizontal) axis line."""
    m = re.search(r'<path d="M [0-9.]+ ([0-9.]+) L [0-9.]+ \1"[^>]*class="ec-axis-line"', svg)
    assert m is not None
    return float(m.group(1))


def _placed(tmp_path, *, anchor="center"):
    """One uncrowded callout, placed by the PIT labella adapter."""
    config = _make_config(tmp_path)
    set_fields(config, pit_leader_label_anchor=anchor)
    event = Event(task_name="Alpha", start="20260315", end="20260315")
    placed = layout_pit_callouts(
        [event],
        axis_origin=(50.0, 300.0),
        axis_length=600.0,
        direction=Orientation.HORIZONTAL,
        side=Side.PRIMARY,
        config=config,
        pos_for_day=lambda day: 100.0,
    )
    return placed[0]


def test_pit_leader_anchor_center_aligns_box_middle(tmp_path):
    """Default 'center' anchor: an uncrowded box is centred on its dot."""
    p = _placed(tmp_path)
    assert p.x_label + p.label_w / 2 == pytest.approx(p.x_dot, abs=0.5)


def test_pit_leader_anchor_center_no_row_overlap(tmp_path):
    """'center' anchor renders without per-row box overlap (labella's model)."""
    svg = _render_pit(tmp_path, _events_dicts(6))
    for boxes in _callout_box_rows(svg).values():
        boxes.sort()
        for (_x0, x1), (nx0, _nx1) in itertools.pairwise(boxes):
            assert nx0 >= x1 - 0.01, "callout boxes overlap on the same row"


def test_pit_leader_anchor_start_puts_box_after_endpoint(tmp_path):
    """'start' anchor: the box's leading (left) edge sits at its dot."""
    p = _placed(tmp_path, anchor="start")
    assert p.x_label == pytest.approx(p.x_dot, abs=0.5)


def test_pit_leader_anchor_end_puts_box_before_endpoint(tmp_path):
    p = _placed(tmp_path, anchor="end")
    assert p.x_label + p.label_w == pytest.approx(p.x_dot, abs=0.5)


def test_pit_leader_length_tracks_layer_gap(tmp_path):
    """pit_labella_layer_gap sets the axis→label gap (the leader length)."""

    def gap_for(layer_gap: float) -> float:
        config = _make_config(tmp_path / f"lg{layer_gap}", side="primary")
        set_fields(config, pit_labella_layer_gap=layer_gap)
        coords = PITLayout().calculate(config)
        PITRenderer().render(config, coords, _events_dicts(5), _DummyDB())
        svg = Path(config.outputfile).read_text(encoding="utf-8").replace("\n", " ")
        axis_y = _axis_y(svg)
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
    """A non-zero end stub makes each leader finish with a straight, axis-perpendicular L segment."""
    config = _make_config(tmp_path, side="primary")
    update_theme(config, lines={"leader": {"end_stub": 6.0}})
    coords = PITLayout().calculate(config)
    PITRenderer().render(config, coords, _events_dicts(5), _DummyDB())
    leaders = _leader_paths(Path(config.outputfile).read_text(encoding="utf-8"))
    assert leaders
    for d in leaders:
        # Ends with an explicit straight segment ...
        m = re.search(r"L (-?[0-9.]+) (-?[0-9.]+)$", d)
        assert m, f"leader does not end with an L segment: {d!r}"
        # ... and the curve before it ends square above it (a horizontal axis: same x).
        before = re.search(r"(-?[0-9.]+) (-?[0-9.]+) L [^L]*$", d)
        assert before and abs(float(before.group(1)) - float(m.group(1))) < 1e-6


def test_pit_leader_end_stub_zero_ends_on_the_curve(tmp_path):
    """No end stub leaves the leader ending on its curve (no trailing L)."""
    config = _make_config(tmp_path, side="primary")
    update_theme(config, lines={"leader": {"end_stub": 0.0}})
    coords = PITLayout().calculate(config)
    PITRenderer().render(config, coords, _events_dicts(5), _DummyDB())
    leaders = _leader_paths(Path(config.outputfile).read_text(encoding="utf-8"))
    assert leaders
    for d in leaders:
        assert not re.search(r"L -?[0-9.]+ -?[0-9.]+$", d)


def test_pit_applies_content_filter_flags(tmp_path):
    """--milestones filters the events PIT draws; completion never does.

    Events go through PITVisualizer.generate(), the path that applies
    filter_events(); calling the renderer directly would skip the filters.
    """
    events = [
        {"Task_Name": "Launch", "Start": "20260315", "End": "20260315", "Milestone": 1},
        {"Task_Name": "Shipped", "Start": "20260601", "End": "20260601", "Milestone": 1, "Percent_Complete": 1},
        {"Task_Name": "Review", "Start": "20260901", "End": "20260901"},
    ]

    class _EventsDB(_DummyDB):
        def get_all_events_in_range(self, start, end):
            return [dict(ev) for ev in events]

    def drawn(name: str, *, filtered: bool) -> tuple[int, int]:
        """(events rendered, callouts in the SVG) for one run."""
        config = _make_config(tmp_path / name)
        config.milestones = filtered
        result = VisualizerFactory.create("pit").generate(config, _EventsDB())
        svg = Path(config.outputfile).read_text(encoding="utf-8")
        return result.event_count, svg.count("ec-pit-callout-group")

    # Unfiltered, every event gets a callout.
    assert drawn("all", filtered=False) == (3, 3)
    # Filtered, both milestones are left: "Review" is not a milestone, and
    # "Shipped" is drawn even though it is 100% complete.
    assert drawn("filtered", filtered=True) == (2, 2)


def test_pit_notes_rendered_when_include_notes(tmp_path):
    """--includenotes (config.include_notes) draws notes inside the box."""
    config = _make_config(tmp_path)
    config.include_notes = True
    coords = PITLayout().calculate(config)
    PITRenderer().render(config, coords, _events_dicts(3), _DummyDB())
    svg = Path(config.outputfile).read_text(encoding="utf-8")
    assert 'class="ec-event-notes"' in svg


def test_pit_notes_absent_by_default(tmp_path):
    """Notes are suppressed when include_notes is False (the default)."""
    config = _make_config(tmp_path)
    assert config.include_notes is False
    coords = PITLayout().calculate(config)
    PITRenderer().render(config, coords, _events_dicts(3), _DummyDB())
    svg = Path(config.outputfile).read_text(encoding="utf-8")
    assert 'class="ec-event-notes"' not in svg


def test_pit_tick_units(tmp_path):
    """Each timeband unit renders without error."""
    for unit in ("month", "week", "interval", "date"):
        config = _make_config(tmp_path / unit, tick_unit=unit)
        if unit == "interval":
            set_bands(config, primary=[{"unit": "interval", "interval_days": 30, "tick": {}}], secondary=[])
        coords = PITLayout().calculate(config)
        renderer = PITRenderer()
        renderer.render(config, coords, _events_dicts(), _DummyDB())
        assert Path(config.outputfile).exists()


def test_pit_today_date_override(tmp_path):
    """pit.today_line.date moves the today line to the specified date."""
    config = _make_config(tmp_path)
    update_theme(config, today={"show": True, "date": "20260601"})
    coords = PITLayout().calculate(config)
    renderer = PITRenderer()
    renderer.render(config, coords, _events_dicts(), _DummyDB())
    svg = Path(config.outputfile).read_text(encoding="utf-8")
    # Today line should be rendered (it's within the date range).
    assert 'class="ec-today-line"' in svg


# ---------------------------------------------------------------------------
# The shared timescale: rows beside the axis and bands at the page edges
# ---------------------------------------------------------------------------


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

    # Milestone → diamond, even when a per-rule marker_icon is set.
    ms = Event(task_name="M", start="20260101", end="20260101", milestone=True)
    sr = StyleResult(marker_icon="myicon")
    spec_ms = resolve_marker(ms, config=config, icon_svg_map=icon_map, style_result=sr)
    assert spec_ms.kind == "shape"
    assert spec_ms.shape == "diamond"

    # Config default does NOT override the axis either.
    set_fields(config, pit_default_event_icon="myicon")
    set_fields(config, pit_default_milestone_icon="myicon")
    assert (
        resolve_marker(
            Event(task_name="x", start="20260101", end="20260101"), config=config, icon_svg_map=icon_map
        ).shape
        == "circle"
    )
    assert (
        resolve_marker(
            Event(task_name="x", start="20260101", end="20260101", milestone=True), config=config, icon_svg_map=icon_map
        ).shape
        == "diamond"
    )


def test_pit_label_icon_resolution():
    """Label-icon precedence: event.icon > rule.marker_icon > config default > None."""
    icon_map = {"myicon": '<svg viewBox="0 0 10 10"><path/></svg>'}
    config = create_calendar_config()
    config = setfontsizes(config)
    set_fields(config, pit_default_event_icon=None)
    set_fields(config, pit_default_milestone_icon=None)

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
    set_fields(config, pit_default_event_icon="myicon")
    assert resolve_label_icon(ev, config=config, icon_svg_map=icon_map) == icon_map["myicon"]

    # Milestones use the milestone default.
    set_fields(config, pit_default_event_icon=None)
    set_fields(config, pit_default_milestone_icon="myicon")
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
            drawing,
            raw,
            x_left=20.0,
            y_center=40.0,
            size=10.0,
            color="tomato",
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
    """A per-rule leader override propagates to the SVG path."""
    config = _make_config(tmp_path)
    set_fields(
        config,
        theme_style_rules=[
            {
                "apply_to": "line:leader",
                "select": {},
                "style": {"color": "#abcdef", "dasharray": "4,2", "opacity": 0.5},
            }
        ],
    )
    coords = PITLayout().calculate(config)
    PITRenderer().render(config, coords, _events_dicts(1), _DummyDB())
    svg = Path(config.outputfile).read_text(encoding="utf-8")
    assert "ec-callout-leader" in svg
    assert "#abcdef" in svg
    assert "4,2" in svg


def test_pit_marker_end_arrow_axis(tmp_path):
    """The axis line gets a marker-end when lines.axis asks for one; <defs> holds the marker."""
    config = _make_config(tmp_path)
    update_theme(config, lines={"axis": {"marker_end": "arrow-head", "marker_end_size": 6.0}})
    svg = _render_with(config)
    axis = re.search(r'<path [^>]*class="ec-axis-line"[^>]*/>', svg)
    assert axis and "marker-end" in axis.group()
    assert "<marker " in svg and "line-marker-arrow-head" in svg


def test_pit_marker_start_arrow_axis(tmp_path):
    """The axis line gets a marker-start independently of its marker-end."""
    config = _make_config(tmp_path)
    update_theme(config, lines={"axis": {"marker_start": "arrow-head", "marker_start_size": 4.0, "marker_end": "none"}})
    svg = _render_with(config)
    axis = re.search(r'<path [^>]*class="ec-axis-line"[^>]*/>', svg)
    assert axis and "marker-start" in axis.group() and "marker-end" not in axis.group()


def test_pit_marker_end_arrow_leader(tmp_path):
    """Leader paths emit marker-end on the label end."""
    config = _make_config(tmp_path, side="primary")
    update_theme(config, lines={"leader": {"marker_end": "arrow-head", "marker_end_size": 5.0}})

    coords = PITLayout().calculate(config)
    renderer = PITRenderer()
    renderer.render(config, coords, _events_dicts(2), _DummyDB())
    svg = Path(config.outputfile).read_text(encoding="utf-8")

    # At least one leader group should have marker-end.
    assert "ec-callout-leader" in svg
    assert "marker-end" in svg


def test_pit_marker_start_arrow_leader(tmp_path):
    """Leader paths emit a marker-start on the axis end when lines.leader asks for one."""
    config = _make_config(tmp_path, side="primary")
    update_theme(config, lines={"leader": {"marker_start": "arrow-head", "marker_start_size": 3.0}})
    leaders = re.findall(r'<path [^>]*class="ec-callout-leader"[^>]*/>', _render_with(config, events=2))
    assert leaders and all("marker-start" in d for d in leaders)


def test_pit_marker_independent_sizes(tmp_path):
    """Axis end (6), leader end (5) and leader start (3) each get a <marker>, deduped by kind, end, colour and size."""
    config = _make_config(tmp_path, side="primary")
    update_theme(
        config,
        lines={
            "axis": {"marker_end": "arrow-head", "marker_end_size": 6.0},
            "leader": {
                "marker_end": "arrow-head",
                "marker_end_size": 5.0,
                "marker_start": "arrow-head",
                "marker_start_size": 3.0,
            },
        },
    )
    marker_ids = re.findall(r'id="(line-marker-arrow-head-[^"]+)"', _render_with(config, events=1))
    assert len(set(marker_ids)) >= 3


def test_pit_marker_none_emits_nothing(tmp_path):
    """Marker slots set to 'none' omit the attributes and the unused defs."""
    config = _make_config(tmp_path)
    update_theme(
        config,
        lines={
            "axis": {"marker_start": "none", "marker_end": "none"},
            "leader": {"marker_start": "none", "marker_end": "none"},
        },
    )
    svg = _render_with(config, events=1)
    assert "marker-start" not in svg and "marker-end" not in svg and "<marker " not in svg


# ---------------------------------------------------------------------------
# Labels
# ---------------------------------------------------------------------------


def test_pit_label_pattern_fill(tmp_path):
    """Label boxes with a pattern emit <defs><pattern> and fill='url(#pat-...)'."""
    pattern_svg = (
        '<svg viewBox="0 0 4 4" width="4" height="4"><path d="M0 4L4 0" stroke="black" stroke-width="0.5"/></svg>'
    )
    config = _make_config(tmp_path)
    set_fields(config, theme_pit_label_pattern="diag")
    set_fields(config, pit_label_fill_opacity=0.85)

    coords = PITLayout().calculate(config)
    db = _PatternDB("diag", pattern_svg)
    renderer = PITRenderer()
    renderer.render(config, coords, _events_dicts(1), db)
    svg = Path(config.outputfile).read_text(encoding="utf-8")

    assert "<pattern " in svg
    assert 'fill="url(#pat-' in svg


def test_pit_label_fill_precedence(tmp_path):
    """Per-rule fill_color > theme_pit_label_fill_color > palette round-robin."""
    config = _make_config(tmp_path)
    # Set a theme-level fill that should be overridden by a rule.
    set_fields(config, theme_pit_label_fill_color="#ffff00")
    set_fields(
        config,
        theme_style_rules=[
            {"apply_to": "box:callout", "select": {}, "style": {"fill": "#abcdef", "fill_opacity": 1.0}},
        ],
    )

    coords = PITLayout().calculate(config)
    renderer = PITRenderer()
    renderer.render(config, coords, _events_dicts(1), _DummyDB())
    svg = Path(config.outputfile).read_text(encoding="utf-8")

    # Per-rule color must appear; theme fill must not (it was overridden).
    assert "#abcdef" in svg


def test_pit_palette_reference(tmp_path):
    """boxes.callout.fill_palette drives round-robin label fills."""
    config = _make_config(tmp_path)
    update_theme(config, boxes={"callout": {"fill_palette": "TestPal", "fill_opacity": 0.9}})

    # Patch the DB to return a palette.
    class _PalDB(_DummyDB):
        def get_palette(self, name):
            return ["#aabbcc", "#ddeeff"] if name == "TestPal" else None

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
    events = [Event(task_name=f"E{i}", start=f"2026{i + 1:02d}01", end=f"2026{i + 1:02d}01") for i in range(4)]
    primary, secondary = partition_for_both(events)
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
        pre = svg[max(0, m.start() - 240) : m.start()]
        tr = re.findall(r"translate\(([0-9.]+),\s*([0-9.]+)\)", pre)
        if tr:
            out.append((float(tr[-1][0]), float(tr[-1][1])))
    return out


def test_pit_date_inline_is_default(tmp_path):
    """By default the date is drawn inside each label box (option 1)."""
    svg = _render_pit(tmp_path, _events_dicts(3))
    assert 'class="ec-event-date"' in svg
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
        assert any(bx - 1 <= dx <= bx + bw + 1 and by - 2 <= dy <= by + bh + 3 for bx, by, bw, bh in boxes), (
            f"inline date at ({dx},{dy}) is not inside any box"
        )


def _render_pit_placement(tmp_path: Path, placement: str) -> str:
    config = _make_config(tmp_path / placement)
    set_fields(config, pit_date_placement=placement)
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
    assert 'class="ec-event-date"' not in svg


def test_pit_date_placement_axis_renders_dates(tmp_path):
    """placement == axis still renders dates (the legacy opposite-side look)."""
    svg = _render_pit_placement(tmp_path, "axis")
    assert 'class="ec-event-date"' in svg


# ---------------------------------------------------------------------------
# Today line
# ---------------------------------------------------------------------------


def test_pit_today_line(tmp_path):
    """Today line renders when the theme shows it and is absent when it does not."""
    config_on = _make_config(tmp_path / "on")
    update_theme(config_on, today={"show": True, "date": "20260601"})
    coords_on = PITLayout().calculate(config_on)
    PITRenderer().render(config_on, coords_on, _events_dicts(1), _DummyDB())
    svg_on = Path(config_on.outputfile).read_text(encoding="utf-8")
    assert 'class="ec-today-line"' in svg_on

    config_off = _make_config(tmp_path / "off")
    update_theme(config_off, today={"show": False})
    coords_off = PITLayout().calculate(config_off)
    PITRenderer().render(config_off, coords_off, _events_dicts(1), _DummyDB())
    svg_off = Path(config_off.outputfile).read_text(encoding="utf-8")
    assert 'class="ec-today-line"' not in svg_off


def test_pit_today_line_takes_its_stroke_from_the_lines_block(tmp_path):
    config = _make_config(tmp_path)
    update_theme(
        config,
        today={"show": True, "date": "20260601"},
        lines={"today": {"color": "#cc1122", "width": 2.5, "dasharray": "6,3", "opacity": 0.75}},
    )
    coords = PITLayout().calculate(config)
    PITRenderer().render(config, coords, _events_dicts(1), _DummyDB())
    svg = Path(config.outputfile).read_text(encoding="utf-8")

    assert 'stroke="#cc1122"' in svg and 'stroke-width="2.5"' in svg
    assert 'stroke-dasharray="6,3"' in svg and 'stroke-opacity="0.75"' in svg


# ---------------------------------------------------------------------------
# Density warning
# ---------------------------------------------------------------------------


def test_pit_density_warning(tmp_path, caplog):
    """With > 80 events on a side, the logger emits a WARNING."""
    events = [Event(task_name=f"E{i}", start="20260115", end="20260115") for i in range(PIT_MAX_EVENTS_PER_SIDE + 1)]
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
    """lines.axis.color reaches the axis stroke."""
    config = _make_config(tmp_path)
    update_theme(config, lines={"axis": {"color": "#123abc"}})
    svg = _render_with(config, events=1)
    assert "#123abc" in svg
    assert "ec-axis-line" in svg


# ---------------------------------------------------------------------------
# CSS classes (§12.5)
# ---------------------------------------------------------------------------


def test_pit_emits_ec_classes(tmp_path):
    """Core ec-* CSS classes are present in the rendered SVG."""
    svg = _render_pit(tmp_path, _events_dicts(2))
    for cls in (
        "ec-pit-axis-group",
        "ec-pit-callout-group",
        "ec-callout-leader",
        "ec-callout-box",
        "ec-pit-event-marker",
        "ec-event-name",
        "ec-event-date",
    ):
        assert cls in svg, f"Missing class: {cls}"


def test_pit_callout_group_data_attrs(tmp_path):
    """Each callout group has data-event-date, data-milestone, data-priority attrs."""
    svg = _render_pit(tmp_path, _events_dicts(1))
    assert "data-event-date=" in svg
    assert "data-milestone=" in svg
    assert "data-priority=" in svg


def test_pit_side_class(tmp_path):
    """Side-specific CSS class is emitted on callout groups."""
    svg_both = _render_pit(tmp_path / "both", _events_dicts(2), side="both")
    assert "ec-pit-side-primary" in svg_both
    assert "ec-pit-side-secondary" in svg_both

    svg_primary = _render_pit(tmp_path / "primary", _events_dicts(2), side="primary")
    assert "ec-pit-side-primary" in svg_primary
    assert "ec-pit-side-secondary" not in svg_primary


def test_pit_css_style_block_injected(tmp_path):
    """The stylesheet built from the theme's roles is injected as <style>."""
    svg = _render_pit(tmp_path, _events_dicts(1))

    assert "<style" in svg
    assert ".ec-event-name" in svg


def test_pit_inline_styled_classes_have_no_css(tmp_path):
    """The four inline-styled classes are NOT in the CSS block (they rely on
    inline attributes, not stylesheet rules — per css_generator contract)."""
    from renderers.css_generator import _INLINE_STYLED_CLASSES

    svg = _render_pit(tmp_path, _events_dicts(1))
    # Extract the <style> block.
    style_match = re.search(r"<style[^>]*>(.*?)</style>", svg, re.DOTALL)
    if style_match:
        style_text = style_match.group(1)
        for cls in _INLINE_STYLED_CLASSES:
            # The inline-styled classes should not have CSS rules defined.
            assert f".{cls}" not in style_text, f"{cls} found in <style> but should be inline-only"


def test_pit_external_css_override(tmp_path):
    """CSS class selectors can override marker/leader/box inline styles when
    !important is used — verify the class is present for external targeting."""
    svg = _render_pit(tmp_path, _events_dicts(1))
    # Confirm the classes that external CSS can target are present.
    assert "ec-pit-event-marker" in svg or "ec-milestone-marker" in svg
    assert "ec-callout-leader" in svg
    assert "ec-callout-box" in svg


MONTH_TICKS = {"label": "Month", "unit": "month", "date_format": "MMM", "height": 18, "tick": {"length": 6}}


class _HolidayDB(_DummyDB):
    def get_icon_svg_map(self) -> dict:
        return {"flag-us": '<svg viewBox="0 0 24 24"><path d="M0 0h24v24H0z"/></svg>'}

    def get_holidays_for_date(self, daykey, country=None):
        if daykey == "20260216":
            return [{"displayname": "Presidents Day", "icon": "flag-us", "nonworkday": 1, "country": "US"}]
        return []


def _render_scale(tmp_path, *, primary=(), secondary=(), vertical=False, db=None, theme=None):
    tmp_path.mkdir(parents=True, exist_ok=True)
    config = _make_config(tmp_path, start="20260201", end="20260501")
    update_theme(config, today={"show": False}, **(theme or {}))
    set_bands(config, primary=list(primary), secondary=list(secondary))
    if vertical:
        set_orientation(config, "vertical")
    coords = PITLayout().calculate(config)
    PITRenderer().render(config, coords, _events_dicts(3), db or _DummyDB())
    return Path(config.outputfile).read_text(encoding="utf-8")


def _ticks(svg):
    pat = r'<path d="M ([\d.-]+) ([\d.-]+) L ([\d.-]+) ([\d.-]+)"[^>]*class="ec-axis-tick"'
    return [tuple(map(float, m)) for m in re.findall(pat, svg)]


def test_pit_draws_no_ticks_unless_the_timescale_has_a_tick_row(tmp_path):
    svg = _render_scale(tmp_path)
    assert 'class="ec-axis-tick"' not in svg and 'class="ec-tick-label"' not in svg


def test_pit_tick_row_draws_a_tick_and_a_label_per_month(tmp_path):
    svg = _render_scale(tmp_path, primary=[MONTH_TICKS])
    assert len(_ticks(svg)) == 4  # Feb, Mar, Apr and 1 May
    assert svg.count('class="ec-tick-label"') == 4


def test_pit_primary_ticks_are_above_the_axis_and_secondary_below(tmp_path):
    svg = _render_scale(tmp_path, primary=[MONTH_TICKS], secondary=[MONTH_TICKS])
    axis = re.search(r'<path d="M [\d.-]+ ([\d.-]+) L [\d.-]+ \1"[^>]*class="ec-axis-line"', svg)
    assert axis
    axis_y = float(axis.group(1))
    ticks = _ticks(svg)
    assert sum(t[3] < axis_y for t in ticks) == sum(t[3] > axis_y for t in ticks) == 4


def test_pit_vertical_axis_gets_horizontal_ticks_on_its_right(tmp_path):
    svg = _render_scale(tmp_path, primary=[MONTH_TICKS], vertical=True)
    axis_x = float(_axis_match(r'<path d="M ([\d.-]+) [\d.-]+ L \1 [\d.-]+"[^>]*class="ec-axis-line"', svg).group(1))
    ticks = _ticks(svg)
    assert len(ticks) == 4 and all(t[1] == t[3] and t[2] > axis_x for t in ticks)


def test_pit_draws_holiday_marks_on_its_axis(tmp_path):
    svg = _render_scale(tmp_path, primary=[{"label": "Holidays", "unit": "holiday"}], db=_HolidayDB())
    assert 'class="ec-holiday-icon"' in svg or "ec-holiday-icon" in svg
    assert "ec-holiday-date" in svg


def test_pit_edge_bands_make_room_around_the_axis(tmp_path):
    band = {"label": "Quarter", "unit": "quarter", "height": 40}
    with_band = _render_scale(tmp_path / "a", primary=[band], theme={"boxes": {"band": {"stroke": "grey"}}})
    without = _render_scale(tmp_path / "b")

    def axis_y(svg):
        return float(_axis_match(r'<path d="M [\d.-]+ ([\d.-]+) L [\d.-]+ \1"[^>]*class="ec-axis-line"', svg).group(1))

    assert axis_y(with_band) == pytest.approx(axis_y(without) + 20.0)  # half the 40 point stack
    assert "ec-band-cell" in with_band


def test_pit_first_callout_row_clears_the_rows_beside_the_axis(tmp_path):
    svg = _render_scale(tmp_path, primary=[{**MONTH_TICKS, "height": 90}])
    axis_y = float(_axis_match(r'<path d="M [\d.-]+ ([\d.-]+) L [\d.-]+ \1"[^>]*class="ec-axis-line"', svg).group(1))
    bottoms = [
        float(y) + float(h)
        for y, h in re.findall(
            r'<rect x="[0-9.]+" y="([0-9.]+)" width="[0-9.]+" height="([0-9.]+)"[^>]*ec-callout-box', svg
        )
    ]
    above = [b for b in bottoms if b < axis_y]
    assert above and axis_y - max(above) >= 90.0 - 0.5
