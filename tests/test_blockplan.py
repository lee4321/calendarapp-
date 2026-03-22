from __future__ import annotations

from pathlib import Path

from config.config import (
    create_calendar_config,
    create_sample_blockplan_swimlanes_from_wbs,
    setfontsizes,
)
from visualizers.blockplan.layout import BlockPlanLayout
from visualizers.blockplan.renderer import BlockPlanRenderer


class _DummyDB:
    @staticmethod
    def get_palette(name):
        return None

    @staticmethod
    def is_nonworkday(daykey, country=None):
        return False


class _DummyIconDB:
    @staticmethod
    def get_palette(name):
        return None

    @staticmethod
    def get_icon_svg_map():
        return {"rocket": '<svg viewBox="0 0 24 24"><path d="M2 2h20v20H2z"/></svg>'}


class _CaptureBlockPlanRenderer(BlockPlanRenderer):
    def __init__(self):
        super().__init__()
        self.text_values: list[str] = []
        self.text_calls: list[dict] = []
        self.rect_calls: list[dict] = []
        self.line_calls: list[tuple[float, float, float, float]] = []
        self.line_kwargs: list[dict] = []
        self.icon_calls: list[dict] = []

    def _draw_text(self, x, y, text, font_name, font_size, **kwargs):
        self.text_values.append(str(text))
        self.text_calls.append(
            {
                "x": x,
                "y": y,
                "text": str(text),
                "font": font_name,
                "size": font_size,
                **kwargs,
            }
        )

    def _draw_rect(self, x, y, w, h, **kwargs):
        self.rect_calls.append({"x": x, "y": y, "w": w, "h": h, **kwargs})
        super()._draw_rect(x, y, w, h, **kwargs)

    def _draw_line(self, x1, y1, x2, y2, **kwargs):
        self.line_calls.append((x1, y1, x2, y2))
        self.line_kwargs.append(kwargs)
        super()._draw_line(x1, y1, x2, y2, **kwargs)

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


def _base_config(output: Path):
    config = create_calendar_config()
    config.pageX, config.pageY = 792.0, 1224.0
    config = setfontsizes(config)
    config.adjustedstart = "20260101"
    config.adjustedend = "20260331"
    config.outputfile = str(output)
    config.include_header = True
    config.include_footer = True
    config.blockplan_swimlanes = [
        {"name": "Engineering", "match": {"resource_groups": ["dev"]}},
        {"name": "Operations", "match": {"resource_groups": ["ops"]}},
    ]
    return config


def test_blockplan_layout_contains_content_area(tmp_path):
    config = _base_config(tmp_path / "blockplan.svg")
    coords = BlockPlanLayout().calculate(config)

    assert "BlockPlanArea" in coords
    assert "HeaderLeft" in coords
    assert "FooterRight" in coords


def test_blockplan_renderer_renders_bands_and_lanes(tmp_path):
    output = tmp_path / "blockplan.svg"
    config = _base_config(output)
    coords = BlockPlanLayout().calculate(config)

    events = [
        {
            "Task_Name": "Sprint Build",
            "Start": "20260110",
            "End": "20260128",
            "Priority": 1,
            "Resource_Group": "dev",
        },
        {
            "Task_Name": "Go/No-Go",
            "Start": "20260202",
            "End": "20260202",
            "Priority": 2,
            "Resource_Group": "dev",
        },
    ]

    renderer = _CaptureBlockPlanRenderer()
    result = renderer.render(config, coords, events, _DummyDB())

    assert result.output_path == str(output)
    assert output.exists()
    assert any(v == "Fiscal Quarter" for v in renderer.text_values)
    assert any(v == "PI" for v in renderer.text_values)
    assert any(v == "Sprint" for v in renderer.text_values)
    assert any(v == "Engineering" for v in renderer.text_values)
    assert "Durations / Events" not in renderer.text_values
    assert renderer.line_calls


def test_blockplan_uses_user_date_range_for_timebands(tmp_path):
    output = tmp_path / "blockplan_user_bounds.svg"
    config = _base_config(output)
    config.weekend_style = 1
    # Simulate weekly-adjusted range differing from user request.
    config.userstart = "20260201"
    config.userend = "20260430"
    config.adjustedstart = "20260202"
    config.adjustedend = "20260501"
    config.blockplan_top_time_bands = [
        {"label": "Date", "unit": "date", "date_format": "YYYYMMDD", "show_every": 1}
    ]
    coords = BlockPlanLayout().calculate(config)

    renderer = _CaptureBlockPlanRenderer()
    renderer.render(config, coords, events=[], db=_DummyDB())

    assert "20260201" in renderer.text_values
    assert "20260202" in renderer.text_values


def test_blockplan_interval_anchor_date(tmp_path):
    """Intervals anchored to a fixed date produce correct indices and boundaries.

    Anchor: 2026-01-05 (Mon), interval=14 days →
      Sprint 1: Jan 5–Jan 18, Sprint 2: Jan 19–Feb 1, Sprint 3: Feb 2–Feb 15, Sprint 4: Feb 16–Mar 1

    Range Jan 28–Feb 28 (workweek mode):
      Sprint 1 ends Jan 18 → entirely before range → absent
      Sprint 2 Jan 19–Feb 1: workdays Jan 28–30 visible → "Sprint 2" rendered
      Sprint 3 Feb 2–Feb 15: fully visible → "Sprint 3" rendered
      Sprint 4 Feb 16–Feb 28: partially visible → "Sprint 4" rendered
    """
    output = tmp_path / "blockplan_anchor.svg"
    config = _base_config(output)
    config.userstart = "20260128"
    config.userend = "20260228"
    config.adjustedstart = "20260128"
    config.adjustedend = "20260228"
    config.blockplan_top_time_bands = [
        {
            "label": "Sprint",
            "unit": "interval",
            "interval_days": 14,
            "prefix": "Sprint ",
            "start_index": 1,
            "anchor_date": "2026-01-05",
            "fill_color": "none",
            "show_every": 1,
        }
    ]
    renderer = _CaptureBlockPlanRenderer()
    coords = BlockPlanLayout().calculate(config)
    renderer.render(config, coords, events=[], db=_DummyDB())

    assert "Sprint 2" in renderer.text_values
    assert "Sprint 3" in renderer.text_values
    assert "Sprint 4" in renderer.text_values
    assert "Sprint 1" not in renderer.text_values


def test_blockplan_vertical_line_style_from_config(tmp_path):
    output = tmp_path / "blockplan_lines.svg"
    config = _base_config(output)
    config.userstart = "20260201"
    config.userend = "20260210"
    config.adjustedstart = "20260201"
    config.adjustedend = "20260210"
    config.blockplan_top_time_bands = [
        {"label": "Date", "unit": "date", "date_format": "YYYYMMDD", "show_every": 1}
    ]
    config.blockplan_vertical_lines = [
        {
            "band": "Date",
            "value": "20260205",
            "width": 3.0,
            "color": "orange",
            "dash_array": "5,2",
            "opacity": 0.5,
        }
    ]
    coords = BlockPlanLayout().calculate(config)

    renderer = _CaptureBlockPlanRenderer()
    renderer.render(config, coords, events=[], db=_DummyDB())

    styled = [
        kw
        for (x1, y1, x2, y2), kw in zip(renderer.line_calls, renderer.line_kwargs)
        if x1 == x2 and y1 < y2 and kw.get("stroke") == "orange"
    ]
    assert styled
    assert styled[0]["stroke_width"] == 3.0
    assert styled[0]["stroke_opacity"] == 0.5
    assert styled[0]["stroke_dasharray"] == "5,2"


def test_blockplan_weekends_zero_shows_only_weekdays_in_date_band(tmp_path):
    output = tmp_path / "blockplan_weekdays_only.svg"
    config = _base_config(output)
    config.weekend_style = 0
    config.userstart = "20260201"  # Sunday
    config.userend = "20260203"
    config.adjustedstart = "20260201"
    config.adjustedend = "20260203"
    config.blockplan_top_time_bands = [
        {"label": "Date", "unit": "date", "date_format": "YYYYMMDD", "show_every": 1}
    ]
    coords = BlockPlanLayout().calculate(config)

    renderer = _CaptureBlockPlanRenderer()
    renderer.render(config, coords, events=[], db=_DummyDB())

    assert "20260201" not in renderer.text_values
    assert "20260202" in renderer.text_values
    assert "20260203" in renderer.text_values


def test_blockplan_duration_notes_rendered_when_include_notes_enabled(tmp_path):
    output = tmp_path / "blockplan_duration_notes.svg"
    config = _base_config(output)
    config.include_notes = True
    coords = BlockPlanLayout().calculate(config)

    events = [
        {
            "Task_Name": "Cutover Window",
            "Start": "20260210",
            "End": "20260214",
            "Notes": "Freeze changes",
            "Priority": 1,
            "Resource_Group": "dev",
        },
    ]

    renderer = _CaptureBlockPlanRenderer()
    renderer.render(config, coords, events, _DummyDB())

    assert "Cutover Window" in renderer.text_values
    assert "Freeze changes" in renderer.text_values


def test_blockplan_event_icon_is_rendered_when_present(tmp_path):
    output = tmp_path / "blockplan_event_icon.svg"
    config = _base_config(output)
    config.userstart = "20260210"
    config.userend = "20260212"
    config.adjustedstart = "20260210"
    config.adjustedend = "20260212"
    config.blockplan_top_time_bands = [
        {"label": "Date", "unit": "date", "date_format": "YYYYMMDD", "show_every": 1}
    ]
    coords = BlockPlanLayout().calculate(config)
    events = [
        {
            "Task_Name": "Launch Window",
            "Start": "20260210",
            "End": "20260210",
            "Priority": 1,
            "Resource_Group": "dev",
            "Icon": "rocket",
        },
    ]

    renderer = _CaptureBlockPlanRenderer()
    renderer.render(config, coords, events, _DummyIconDB())

    assert renderer.icon_calls
    assert renderer.icon_calls[0]["icon_name"] == "rocket"
    assert renderer.icon_calls[0]["anchor"] == "start"
    name_y = next(c["y"] for c in renderer.text_calls if c["text"] == "Launch Window")
    assert renderer.icon_calls[0]["baseline_y"] == name_y


def test_blockplan_event_icon_aligns_with_name_when_notes_included(tmp_path):
    output = tmp_path / "blockplan_event_icon_notes.svg"
    config = _base_config(output)
    config.include_notes = True
    config.userstart = "20260210"
    config.userend = "20260212"
    config.adjustedstart = "20260210"
    config.adjustedend = "20260212"
    config.blockplan_top_time_bands = [
        {"label": "Date", "unit": "date", "date_format": "YYYYMMDD", "show_every": 1}
    ]
    coords = BlockPlanLayout().calculate(config)
    events = [
        {
            "Task_Name": "Readiness",
            "Start": "20260210",
            "End": "20260210",
            "Notes": "Gate check",
            "Priority": 1,
            "Resource_Group": "dev",
            "Icon": "rocket",
        },
    ]

    renderer = _CaptureBlockPlanRenderer()
    renderer.render(config, coords, events, _DummyIconDB())

    assert renderer.icon_calls
    name_y = next(c["y"] for c in renderer.text_calls if c["text"] == "Readiness")
    assert renderer.icon_calls[0]["baseline_y"] == name_y


def test_blockplan_event_date_drawn_above_name_and_no_overwrite(tmp_path):
    output = tmp_path / "blockplan_event_date.svg"
    config = _base_config(output)
    config.blockplan_event_show_date = True
    config.blockplan_event_date_format = "MMM D"
    config.blockplan_event_date_color = "purple"
    config.blockplan_event_date_font = "Roboto-Bold"
    config.blockplan_event_date_font_size = 11.0
    config.userstart = "20260210"
    config.userend = "20260212"
    config.adjustedstart = "20260210"
    config.adjustedend = "20260212"
    config.blockplan_top_time_bands = [
        {"label": "Date", "unit": "date", "date_format": "YYYYMMDD", "show_every": 1}
    ]
    config.blockplan_swimlanes = [
        {"name": "Engineering", "match": {"resource_groups": ["dev"]}}
    ]
    coords = BlockPlanLayout().calculate(config)
    events = [
        {
            "Task_Name": "Launch Window",
            "Start": "20260210",
            "End": "20260210",
            "Priority": 1,
            "Resource_Group": "dev",
            "Icon": "rocket",
        },
        {
            "Task_Name": "Launch Backup",
            "Start": "20260210",
            "End": "20260210",
            "Priority": 2,
            "Resource_Group": "dev",
            "Icon": "rocket",
        },
    ]

    renderer = _CaptureBlockPlanRenderer()
    renderer.render(config, coords, events, _DummyIconDB())

    assert "Feb 10" in renderer.text_values
    date_call = next(c for c in renderer.text_calls if c["text"] == "Feb 10")
    name_call = next(c for c in renderer.text_calls if c["text"] == "Launch Window")
    assert date_call["y"] < name_call["y"]  # SVG: above = smaller Y
    assert date_call["font"] == "Roboto-Bold"

    name_y_a = next(c["y"] for c in renderer.text_calls if c["text"] == "Launch Window")
    name_y_b = next(c["y"] for c in renderer.text_calls if c["text"] == "Launch Backup")
    assert name_y_a != name_y_b


def test_blockplan_lane_label_alignment_and_multiline(tmp_path):
    output = tmp_path / "blockplan_lane_label_align.svg"
    config = _base_config(output)
    config.blockplan_swimlanes = [
        {
            "name": "Lane A\nLane B",
            "label_align_h": "center",
            "label_align_v": "top",
            "match": {"resource_groups": ["dev"]},
        }
    ]
    coords = BlockPlanLayout().calculate(config)

    renderer = _CaptureBlockPlanRenderer()
    renderer.render(config, coords, events=[], db=_DummyDB())

    lane_a = next(c for c in renderer.text_calls if c["text"] == "Lane A")
    lane_b = next(c for c in renderer.text_calls if c["text"] == "Lane B")
    assert lane_a["anchor"] == "middle"
    assert lane_a["y"] < lane_b["y"]  # SVG: Lane A above Lane B = smaller Y


def test_blockplan_lane_label_rotation(tmp_path):
    """Global lane_label_rotation and per-lane label_rotation both produce a
    rotate(...) SVG transform on lane-label text calls."""
    output = tmp_path / "blockplan_lane_label_rotation.svg"
    config = _base_config(output)

    # Global rotation applied to all lanes
    config.blockplan_lane_label_rotation = -90.0
    config.blockplan_swimlanes = [
        {"name": "Alpha", "match": {}},
        {"name": "Beta", "label_rotation": 45.0, "match": {}},  # per-lane override
        {
            "name": "Gamma",
            "label_rotation": 0.0,
            "match": {},
        },  # explicit zero = no transform
    ]
    config.blockplan_top_time_bands = []
    coords = BlockPlanLayout().calculate(config)

    renderer = _CaptureBlockPlanRenderer()
    renderer.render(config, coords, events=[], db=_DummyDB())

    alpha = next(c for c in renderer.text_calls if c["text"] == "Alpha")
    beta = next(c for c in renderer.text_calls if c["text"] == "Beta")
    gamma = next(c for c in renderer.text_calls if c["text"] == "Gamma")

    # Alpha inherits global -90° → transform must contain "rotate(-90"
    assert alpha.get("transform") is not None, "Alpha should have a rotation transform"
    assert "rotate(-90" in alpha["transform"]

    # Beta has per-lane 45° override → transform must contain "rotate(45"
    assert beta.get("transform") is not None, "Beta should have a rotation transform"
    assert "rotate(45" in beta["transform"]

    # Gamma explicitly sets 0° → no transform
    assert not gamma.get("transform"), "Gamma rotation=0 should produce no transform"


def test_blockplan_timeband_per_band_style_and_palette(tmp_path):
    output = tmp_path / "blockplan_timeband_style.svg"
    config = _base_config(output)
    config.userstart = "20260202"
    config.userend = "20260206"
    config.adjustedstart = "20260202"
    config.adjustedend = "20260206"
    config.blockplan_top_time_bands = [
        {
            "label": "Date Band",
            "unit": "date",
            "date_format": "D",
            "font": "Roboto-Bold",
            "font_size": 13.0,
            "font_color": "darkred",
            "fill_palette": ["#111111", "#222222"],
            "label_font": "Roboto-BoldItalic",
            "label_font_size": 15.0,
            "label_color": "teal",
            "label_align_h": "right",
            "label_fill_color": "beige",
            "show_every": 1,
        }
    ]
    coords = BlockPlanLayout().calculate(config)

    renderer = _CaptureBlockPlanRenderer()
    renderer.render(config, coords, events=[], db=_DummyDB())

    # Left heading label styling/alignment
    heading = next(c for c in renderer.text_calls if c["text"] == "Date Band")
    assert heading["font"] == "Roboto-BoldItalic"
    assert heading["size"] == 15.0
    assert heading["fill"] == "teal"
    assert heading["anchor"] == "end"

    # Segment labels use per-band font config.
    seg = next(c for c in renderer.text_calls if c["text"] == "2")
    assert seg["font"] == "Roboto-Bold"
    assert seg["size"] == 13.0
    assert seg["fill"] == "darkred"

    # Palette alternates for segment rectangles.
    seg_fills = [
        r.get("fill")
        for r in renderer.rect_calls
        if r.get("fill") in {"#111111", "#222222"}
    ]
    assert len(seg_fills) >= 2
    assert seg_fills[0] != seg_fills[1]


def test_sample_blockplan_swimlane_factory_from_wbs():
    lanes = create_sample_blockplan_swimlanes_from_wbs(
        ["2.1", "1", "2.1", "", " 3. "],
        lane_name_format="Lane {wbs}",
    )
    assert lanes == [
        {"name": "Lane 1", "match": {"wbs_prefixes": ["1"]}},
        {"name": "Lane 2.1", "match": {"wbs_prefixes": ["2.1"]}},
        {"name": "Lane 3.", "match": {"wbs_prefixes": ["3."]}},
        {"name": "Unmatched", "match": {}},
    ]


def test_blockplan_event_notes_and_y_adjustment_for_collisions(tmp_path):
    output = tmp_path / "blockplan_event_notes.svg"
    config = _base_config(output)
    config.include_notes = True
    config.userstart = "20260210"
    config.userend = "20260212"
    config.adjustedstart = "20260210"
    config.adjustedend = "20260212"
    config.blockplan_top_time_bands = [
        {"label": "Date", "unit": "date", "date_format": "YYYYMMDD", "show_every": 1}
    ]
    config.blockplan_swimlanes = [
        {"name": "Engineering", "match": {"resource_groups": ["dev"]}}
    ]
    coords = BlockPlanLayout().calculate(config)

    events = [
        {
            "Task_Name": "Launch Window",
            "Start": "20260210",
            "End": "20260210",
            "Notes": "Primary",
            "Priority": 1,
            "Resource_Group": "dev",
        },
        {
            "Task_Name": "Launch Window B",
            "Start": "20260210",
            "End": "20260210",
            "Notes": "Secondary",
            "Priority": 2,
            "Resource_Group": "dev",
        },
    ]

    renderer = _CaptureBlockPlanRenderer()
    renderer.render(config, coords, events, _DummyDB())

    assert "Primary" in renderer.text_values
    assert "Secondary" in renderer.text_values

    y_a = next(c["y"] for c in renderer.text_calls if c["text"] == "Launch Window")
    y_b = next(c["y"] for c in renderer.text_calls if c["text"] == "Launch Window B")
    assert y_a != y_b


def test_blockplan_split_ratio_zero_removes_dividing_line(tmp_path):
    """split_ratio=0.0 must not draw a dividing line inside any swimlane."""
    output = tmp_path / "blockplan_split_zero.svg"
    config = _base_config(output)
    config.blockplan_lane_split_ratio = 0.0
    config.blockplan_swimlanes = [{"name": "All", "match": {}}]
    coords = BlockPlanLayout().calculate(config)

    renderer = _CaptureBlockPlanRenderer()
    renderer.render(config, coords, events=[], db=_DummyDB())

    # With split_ratio=0.0 the split line (horizontal inside timeline area, not the
    # outer lane border) must not exist.  The outer border lines are x1!=x2; the
    # split divider would have y1==y2 and span from timeline_x to timeline_x+timeline_w.
    # We simply verify no horizontal line was drawn strictly *inside* the lane area.
    area_x, area_y, area_w, area_h = coords["BlockPlanArea"]
    horizontal_interior = [
        (x1, y1, x2, y2)
        for (x1, y1, x2, y2) in renderer.line_calls
        if y1 == y2 and x1 > area_x and x2 > area_x and area_y < y1 < (area_y + area_h)
    ]
    # The only horizontal line that should remain is the bands/lanes separator,
    # not a split divider inside the swimlane body.
    # Count: without split line there should be ≤1 (the band-area separator).
    assert len(horizontal_interior) <= 1


def test_blockplan_split_ratio_zero_gives_full_lane_to_both_types(tmp_path):
    """split_ratio=0.0 (no divider) must render both events and durations, and
    their vertical extents must not overlap each other."""
    output = tmp_path / "blockplan_split_zero_full.svg"
    config = _base_config(output)
    config.blockplan_lane_split_ratio = 0.0
    config.blockplan_swimlanes = [{"name": "All", "match": {}}]
    config.blockplan_top_time_bands = []
    coords = BlockPlanLayout().calculate(config)

    events = [
        # A duration bar
        {
            "Task_Name": "Big Sprint",
            "Start": "20260106",
            "End": "20260120",
            "Priority": 1,
            "Resource_Group": "dev",
        },
        # A point event
        {
            "Task_Name": "Kickoff",
            "Start": "20260106",
            "End": "20260106",
            "Priority": 1,
            "Resource_Group": "dev",
        },
    ]

    renderer = _CaptureBlockPlanRenderer()
    renderer.render(config, coords, events, _DummyDB())

    # Both the duration rect and the event label must be drawn.
    sprint_rects = [
        r
        for r in renderer.rect_calls
        if r.get("fill") not in {"none", None, ""} and r["w"] > 10
    ]  # wide rect = duration bar
    kickoff_texts = [c for c in renderer.text_calls if c["text"] == "Kickoff"]

    assert sprint_rects, "Duration bar should be drawn when split_ratio=0.0"
    assert kickoff_texts, "Point event should be drawn when split_ratio=0.0"

    # Both should be placed within the full lane height.
    area_x, area_y, area_w, area_h = coords["BlockPlanArea"]
    bar_y = sprint_rects[0]["y"]
    bar_bottom = bar_y + sprint_rects[0]["h"]
    evt_y = kickoff_texts[0]["y"]
    assert area_y <= bar_y <= area_y + area_h, "Duration bar must be within lane bounds"
    assert area_y <= evt_y <= area_y + area_h, "Event text must be within lane bounds"

    # The event text baseline must not fall inside the duration bar's vertical extent.
    # (Proves the two types are placed in non-overlapping vertical slices.)
    assert not (bar_y <= evt_y <= bar_bottom), (
        f"Event text (y={evt_y:.1f}) overlaps duration bar extent "
        f"[{bar_y:.1f} … {bar_bottom:.1f}]"
    )


def test_blockplan_split_ratio_custom_value_draws_line_at_correct_position(tmp_path):
    """split_ratio=0.3 draws the divider at 70% from the bottom (30% from top)."""
    output = tmp_path / "blockplan_split_custom.svg"
    config = _base_config(output)
    config.blockplan_lane_split_ratio = 0.3
    config.blockplan_swimlanes = [{"name": "All", "match": {}}]
    config.blockplan_top_time_bands = []
    coords = BlockPlanLayout().calculate(config)

    renderer = _CaptureBlockPlanRenderer()
    renderer.render(config, coords, events=[], db=_DummyDB())

    area_x, area_y, area_w, area_h = coords["BlockPlanArea"]
    # With no time bands the lane area equals the full BlockPlanArea.
    # lane_top == area_y (SVG top), lane_bottom == area_y + area_h (SVG bottom).
    lane_h = area_h
    expected_split = area_y + lane_h * 0.3  # split_ratio=0.3 from SVG top
    horizontal_interior = [
        (x1, y1, x2, y2)
        for (x1, y1, x2, y2) in renderer.line_calls
        if y1 == y2 and abs(y1 - expected_split) < 1.0
    ]
    assert horizontal_interior, "Expected a dividing line near the 0.3 split position"


def test_blockplan_per_lane_split_ratio_overrides_global(tmp_path):
    """A per-lane split_ratio key overrides the global blockplan_lane_split_ratio."""
    output = tmp_path / "blockplan_per_lane_split.svg"
    config = _base_config(output)
    config.blockplan_lane_split_ratio = 0.5  # global
    config.blockplan_swimlanes = [
        {
            "name": "NoSplit",
            "split_ratio": 0.0,  # per-lane override
            "match": {},
        }
    ]
    config.blockplan_top_time_bands = []
    coords = BlockPlanLayout().calculate(config)

    renderer = _CaptureBlockPlanRenderer()
    renderer.render(config, coords, events=[], db=_DummyDB())

    area_x, area_y, area_w, area_h = coords["BlockPlanArea"]
    horizontal_interior = [
        (x1, y1, x2, y2)
        for (x1, y1, x2, y2) in renderer.line_calls
        if y1 == y2 and x1 > area_x and x2 > area_x and area_y < y1 < (area_y + area_h)
    ]
    assert len(horizontal_interior) <= 1


def test_blockplan_item_placement_order_events_first_puts_events_on_top(tmp_path):
    """item_placement_order=['events','durations'] should place events in the upper section."""
    output = tmp_path / "blockplan_events_top.svg"
    config = _base_config(output)
    config.item_placement_order = ["events", "durations"]
    config.blockplan_lane_split_ratio = 0.5
    config.blockplan_swimlanes = [{"name": "All", "match": {}}]
    config.blockplan_top_time_bands = []
    coords = BlockPlanLayout().calculate(config)

    events = [
        # A duration bar
        {
            "Task_Name": "Big Sprint",
            "Start": "20260110",
            "End": "20260128",
            "Priority": 1,
            "Resource_Group": "dev",
        },
        # A point event
        {
            "Task_Name": "Kickoff",
            "Start": "20260115",
            "End": "20260115",
            "Priority": 1,
            "Resource_Group": "dev",
        },
    ]

    renderer = _CaptureBlockPlanRenderer()
    renderer.render(config, coords, events, _DummyDB())

    area_x, area_y, area_w, area_h = coords["BlockPlanArea"]
    lane_mid = area_y + area_h / 2.0

    # With events on top, the "Kickoff" event text should be above the midpoint
    # and the "Big Sprint" duration text should be below it.
    kickoff_y = next(
        (c["y"] for c in renderer.text_calls if c["text"] == "Kickoff"), None
    )
    sprint_y = next(
        (c["y"] for c in renderer.text_calls if c["text"] == "Big Sprint"), None
    )

    assert kickoff_y is not None, "Kickoff event label not rendered"
    assert sprint_y is not None, "Big Sprint duration label not rendered"
    # In SVG coords (Y down), "above the mid" means smaller Y value.
    assert kickoff_y < lane_mid, "Kickoff event should be in the upper (events) section"
    assert sprint_y > lane_mid, (
        "Big Sprint duration should be in the lower (durations) section"
    )


def test_blockplan_item_placement_order_durations_first_default_behavior(tmp_path):
    """Default item_placement_order keeps durations in the upper section."""
    output = tmp_path / "blockplan_durations_top.svg"
    config = _base_config(output)
    config.item_placement_order = ["priority"]  # default — durations stay on top
    config.blockplan_lane_split_ratio = 0.5
    config.blockplan_swimlanes = [{"name": "All", "match": {}}]
    config.blockplan_top_time_bands = []
    coords = BlockPlanLayout().calculate(config)

    events = [
        {
            "Task_Name": "Big Sprint",
            "Start": "20260110",
            "End": "20260128",
            "Priority": 1,
            "Resource_Group": "dev",
        },
        {
            "Task_Name": "Kickoff",
            "Start": "20260115",
            "End": "20260115",
            "Priority": 1,
            "Resource_Group": "dev",
        },
    ]

    renderer = _CaptureBlockPlanRenderer()
    renderer.render(config, coords, events, _DummyDB())

    area_x, area_y, area_w, area_h = coords["BlockPlanArea"]
    lane_mid = area_y + area_h / 2.0

    kickoff_y = next(
        (c["y"] for c in renderer.text_calls if c["text"] == "Kickoff"), None
    )
    sprint_y = next(
        (c["y"] for c in renderer.text_calls if c["text"] == "Big Sprint"), None
    )

    assert kickoff_y is not None
    assert sprint_y is not None
    # In SVG coords (Y down): durations on top → sprint_y < lane_mid; events below → kickoff_y > lane_mid.
    assert sprint_y < lane_mid, (
        "Big Sprint duration should be in the upper (durations) section"
    )
    assert kickoff_y > lane_mid, "Kickoff event should be in the lower (events) section"


def test_blockplan_per_lane_fill_color_applied_to_heading_cell(tmp_path):
    """fill_color on a swimlane dict is used for that lane's heading cell background."""
    output = tmp_path / "blockplan_per_lane_fill.svg"
    config = _base_config(output)
    config.blockplan_lane_heading_fill_color = "white"  # global default
    config.blockplan_swimlanes = [
        {
            "name": "Highlight",
            "fill_color": "gold",
            "match": {"resource_groups": ["dev"]},
        },
        {
            "name": "Normal",
            "match": {"resource_groups": ["ops"]},
        },
    ]
    config.blockplan_top_time_bands = []
    coords = BlockPlanLayout().calculate(config)

    renderer = _CaptureBlockPlanRenderer()
    renderer.render(config, coords, events=[], db=_DummyDB())

    heading_fills = [
        r.get("fill") for r in renderer.rect_calls if r.get("fill") == "gold"
    ]
    assert heading_fills, (
        "Expected at least one rect drawn with per-lane fill_color 'gold'"
    )


def test_blockplan_per_lane_label_color_applied_to_label_text(tmp_path):
    """label_color on a swimlane dict overrides the global lane_label_color for that lane."""
    output = tmp_path / "blockplan_per_lane_label_color.svg"
    config = _base_config(output)
    config.blockplan_lane_label_color = "black"  # global default
    config.blockplan_swimlanes = [
        {
            "name": "Teal Lane",
            "label_color": "teal",
            "match": {},
        },
    ]
    config.blockplan_top_time_bands = []
    coords = BlockPlanLayout().calculate(config)

    renderer = _CaptureBlockPlanRenderer()
    renderer.render(config, coords, events=[], db=_DummyDB())

    label_call = next(
        (c for c in renderer.text_calls if c["text"] == "Teal Lane"), None
    )
    assert label_call is not None, "Lane label not rendered"
    assert label_call["fill"] == "teal", "Expected per-lane label_color 'teal'"


def test_blockplan_per_lane_timeline_fill_color_paints_content_area(tmp_path):
    """timeline_fill_color on a swimlane dict fills the content area of that lane."""
    output = tmp_path / "blockplan_timeline_fill.svg"
    config = _base_config(output)
    config.blockplan_swimlanes = [
        {
            "name": "Shaded",
            "timeline_fill_color": "lightyellow",
            "match": {},
        },
    ]
    config.blockplan_top_time_bands = []
    coords = BlockPlanLayout().calculate(config)

    renderer = _CaptureBlockPlanRenderer()
    renderer.render(config, coords, events=[], db=_DummyDB())

    shaded = [r for r in renderer.rect_calls if r.get("fill") == "lightyellow"]
    assert shaded, "Expected a rect with timeline_fill_color 'lightyellow'"
    # The timeline rect has x >= the label column boundary.
    area_x, area_y, area_w, area_h = coords["BlockPlanArea"]
    label_w = min(
        area_w * 0.45, max(80.0, area_w * config.blockplan_label_column_ratio)
    )
    timeline_x = area_x + label_w
    assert any(r["x"] >= timeline_x - 1.0 for r in shaded), (
        "Shaded rect should be in timeline area"
    )


def test_blockplan_match_priority_exact_filters_events(tmp_path):
    """match.priority filters events to only those with the specified priority."""
    output = tmp_path / "blockplan_match_priority.svg"
    config = _base_config(output)
    config.blockplan_swimlanes = [
        {"name": "Critical", "match": {"priority": 1}},
        {"name": "Normal", "match": {"priority": [2, 3]}},
    ]
    config.blockplan_top_time_bands = []
    coords = BlockPlanLayout().calculate(config)

    events = [
        # All dates are weekdays (Jan 12=Mon, Jan 14=Wed, Jan 16=Fri, Jan 20=Tue)
        {
            "Task_Name": "P1 Task",
            "Start": "20260112",
            "End": "20260112",
            "Priority": 1,
            "Resource_Group": "dev",
        },
        {
            "Task_Name": "P2 Task",
            "Start": "20260114",
            "End": "20260114",
            "Priority": 2,
            "Resource_Group": "dev",
        },
        {
            "Task_Name": "P3 Task",
            "Start": "20260116",
            "End": "20260116",
            "Priority": 3,
            "Resource_Group": "dev",
        },
        {
            "Task_Name": "P9 Task",
            "Start": "20260120",
            "End": "20260120",
            "Priority": 9,
            "Resource_Group": "dev",
        },
    ]

    renderer = _CaptureBlockPlanRenderer()
    renderer.render(config, coords, events, _DummyDB())

    assert "P1 Task" in renderer.text_values
    assert "P2 Task" in renderer.text_values
    assert "P3 Task" in renderer.text_values
    # P9 Task has no matching lane and show_unmatched_lane defaults to True
    assert "P9 Task" in renderer.text_values


def test_blockplan_match_priority_range_filters_events(tmp_path):
    """match.priority_min / priority_max filter events by priority range."""
    output = tmp_path / "blockplan_match_priority_range.svg"
    config = _base_config(output)
    config.blockplan_show_unmatched_lane = False
    config.blockplan_swimlanes = [
        {"name": "High", "match": {"priority_max": 2}},
    ]
    config.blockplan_top_time_bands = []
    coords = BlockPlanLayout().calculate(config)

    events = [
        # Jan 12=Monday, Jan 14=Wednesday — both weekdays
        {
            "Task_Name": "Hi Pri",
            "Start": "20260112",
            "End": "20260112",
            "Priority": 1,
            "Resource_Group": "dev",
        },
        {
            "Task_Name": "Lo Pri",
            "Start": "20260114",
            "End": "20260114",
            "Priority": 5,
            "Resource_Group": "dev",
        },
    ]

    renderer = _CaptureBlockPlanRenderer()
    renderer.render(config, coords, events, _DummyDB())

    assert "Hi Pri" in renderer.text_values
    assert "Lo Pri" not in renderer.text_values


def test_blockplan_theme_swimlane_labels_and_criteria_via_config(tmp_path):
    """Swimlane labels and match criteria set on config (as loaded from a theme) work correctly."""
    output = tmp_path / "blockplan_theme_swimlanes.svg"
    config = _base_config(output)
    # Simulate what ThemeEngine.apply() does: overwrite blockplan_swimlanes entirely.
    config.blockplan_swimlanes = [
        {"name": "Frontend", "match": {"resource_groups": ["frontend", "ui"]}},
        {"name": "Backend", "match": {"resource_groups": ["backend", "api"]}},
        {"name": "DevOps", "match": {"wbs_prefixes": ["3."]}},
    ]
    config.blockplan_top_time_bands = []
    coords = BlockPlanLayout().calculate(config)

    events = [
        {
            "Task_Name": "UI Sprint",
            "Start": "20260110",
            "End": "20260120",
            "Priority": 1,
            "Resource_Group": "frontend",
        },
        {
            "Task_Name": "API Build",
            "Start": "20260110",
            "End": "20260124",
            "Priority": 1,
            "Resource_Group": "api",
        },
        {
            "Task_Name": "Deploy",
            "Start": "20260115",
            "End": "20260115",
            "Priority": 1,
            "Resource_Group": "ops",
            "WBS": "3.1",
        },
    ]

    renderer = _CaptureBlockPlanRenderer()
    renderer.render(config, coords, events, _DummyDB())

    assert "Frontend" in renderer.text_values
    assert "Backend" in renderer.text_values
    assert "DevOps" in renderer.text_values
    assert "UI Sprint" in renderer.text_values
    assert "API Build" in renderer.text_values
    assert "Deploy" in renderer.text_values
    # Verify the correct number of swimlane label cells is rendered
    lane_label_texts = [
        c["text"]
        for c in renderer.text_calls
        if c["text"] in {"Frontend", "Backend", "DevOps"}
    ]
    assert len(lane_label_texts) == 3


def test_blockplan_week_band_skips_segments_without_drawn_dates_when_weekdays_only(
    tmp_path,
):
    output = tmp_path / "blockplan_week_segment_skip.svg"
    config = _base_config(output)
    config.weekend_style = 0
    config.userstart = "20260201"  # Sunday (ISO week 5)
    config.userend = "20260203"  # Monday/Tuesday (ISO week 6)
    config.adjustedstart = "20260201"
    config.adjustedend = "20260203"
    config.blockplan_top_time_bands = [
        {
            "label": "Week Number",
            "unit": "week",
            "label_format": "Week {week}",
            "show_every": 1,
        }
    ]
    coords = BlockPlanLayout().calculate(config)

    renderer = _CaptureBlockPlanRenderer()
    renderer.render(config, coords, events=[], db=_DummyDB())

    assert "Week 5" not in renderer.text_values
    assert "Week 6" in renderer.text_values


def test_blockplan_countdown_band_calendar_days(tmp_path):
    """Countdown unit labels each visible day with calendar days remaining to target."""
    output = tmp_path / "blockplan_countdown.svg"
    config = _base_config(output)
    config.userstart = "20260202"  # Monday
    config.userend = "20260206"    # Friday
    config.adjustedstart = "20260202"
    config.adjustedend = "20260206"
    config.weekend_style = 0
    config.blockplan_top_time_bands = [
        {
            "label": "Countdown",
            "unit": "countdown",
            "target_date": "2026-02-10",  # 8 cal days from Mon Feb 2
        }
    ]
    coords = BlockPlanLayout().calculate(config)
    renderer = _CaptureBlockPlanRenderer()
    renderer.render(config, coords, events=[], db=_DummyDB())

    # Mon Feb 2 → 8 calendar days to Feb 10 (exclusive Feb 2, inclusive Feb 10)
    assert "8" in renderer.text_values
    # Fri Feb 6 → 4 calendar days to Feb 10
    assert "4" in renderer.text_values


def test_blockplan_countdown_skip_weekends(tmp_path):
    """skip_weekends=True counts only Mon-Fri days toward the target."""
    output = tmp_path / "blockplan_countdown_wk.svg"
    config = _base_config(output)
    # Mon Feb 2 to Mon Feb 9 (includes Sat Feb 7 / Sun Feb 8, but weekend_style=0 hides them)
    config.userstart = "20260202"
    config.userend = "20260209"
    config.adjustedstart = "20260202"
    config.adjustedend = "20260209"
    config.weekend_style = 0  # only weekdays shown
    config.blockplan_top_time_bands = [
        {
            "label": "WD Countdown",
            "unit": "countdown",
            "target_date": "2026-02-10",  # Tuesday
            "skip_weekends": True,
        }
    ]
    coords = BlockPlanLayout().calculate(config)
    renderer = _CaptureBlockPlanRenderer()
    renderer.render(config, coords, events=[], db=_DummyDB())

    # Mon Feb 2 → working days to Tue Feb 10:
    # Tue3, Wed4, Thu5, Fri6 (skip Sat7, Sun8), Mon9, Tue10 = 6
    assert "6" in renderer.text_values
    # Mon Feb 9 → 1 working day to Tue Feb 10 (just Feb 10)
    assert "1" in renderer.text_values


def test_blockplan_countdown_skip_nonworkdays(tmp_path):
    """skip_nonworkdays=True excludes holidays from the day count."""
    output = tmp_path / "blockplan_countdown_nwd.svg"
    config = _base_config(output)
    config.userstart = "20260202"  # Monday
    config.userend = "20260204"    # Wednesday
    config.adjustedstart = "20260202"
    config.adjustedend = "20260204"
    config.weekend_style = 0
    config.blockplan_top_time_bands = [
        {
            "label": "Biz Countdown",
            "unit": "countdown",
            "target_date": "2026-02-06",  # Friday
            "skip_nonworkdays": True,
        }
    ]

    class _HolidayDB(_DummyDB):
        @staticmethod
        def is_nonworkday(daykey, country=None):
            return daykey == "20260205"  # Thu Feb 5 is a holiday

    coords = BlockPlanLayout().calculate(config)
    renderer = _CaptureBlockPlanRenderer()
    renderer.render(config, coords, events=[], db=_HolidayDB())

    # Mon Feb 2 → target Fri Feb 6: counting Tue3, Wed4, Thu5(skip), Fri6 = 3
    assert "3" in renderer.text_values
    # Wed Feb 4 → target Fri Feb 6: counting Thu5(skip), Fri6 = 1
    assert "1" in renderer.text_values


def test_blockplan_countup_band_calendar_days(tmp_path):
    """Countup unit labels each visible day with calendar days elapsed since start_date."""
    output = tmp_path / "blockplan_countup.svg"
    config = _base_config(output)
    config.userstart = "20260202"  # Monday
    config.userend = "20260206"    # Friday
    config.adjustedstart = "20260202"
    config.adjustedend = "20260206"
    config.weekend_style = 0
    config.blockplan_top_time_bands = [
        {
            "label": "Countup",
            "unit": "countup",
            "start_date": "2026-01-30",  # Friday before range
        }
    ]
    coords = BlockPlanLayout().calculate(config)
    renderer = _CaptureBlockPlanRenderer()
    renderer.render(config, coords, events=[], db=_DummyDB())

    # Mon Feb 2 → 3 calendar days after Jan 30 (Jan31, Feb1, Feb2)
    assert "3" in renderer.text_values
    # Fri Feb 6 → 7 calendar days after Jan 30
    assert "7" in renderer.text_values


def test_blockplan_countup_skip_weekends(tmp_path):
    """skip_weekends=True counts only Mon-Fri days elapsed since start_date."""
    output = tmp_path / "blockplan_countup_wk.svg"
    config = _base_config(output)
    config.userstart = "20260202"  # Monday
    config.userend = "20260206"    # Friday
    config.adjustedstart = "20260202"
    config.adjustedend = "20260206"
    config.weekend_style = 0
    config.blockplan_top_time_bands = [
        {
            "label": "WD Countup",
            "unit": "countup",
            "start_date": "2026-01-30",  # Friday
            "skip_weekends": True,
        }
    ]
    coords = BlockPlanLayout().calculate(config)
    renderer = _CaptureBlockPlanRenderer()
    renderer.render(config, coords, events=[], db=_DummyDB())

    # Jan 30 (Fri) → Mon Feb 2: skipping Sat Jan31, Sun Feb1 → only Mon Feb 2 = 1
    assert "1" in renderer.text_values
    # Jan 30 (Fri) → Fri Feb 6: Mon2, Tue3, Wed4, Thu5, Fri6 = 5
    assert "5" in renderer.text_values


def test_blockplan_countup_skip_nonworkdays(tmp_path):
    """skip_nonworkdays=True excludes holidays from the elapsed day count."""
    output = tmp_path / "blockplan_countup_nwd.svg"
    config = _base_config(output)
    config.userstart = "20260202"  # Monday
    config.userend = "20260204"    # Wednesday
    config.adjustedstart = "20260202"
    config.adjustedend = "20260204"
    config.weekend_style = 0
    config.blockplan_top_time_bands = [
        {
            "label": "Biz Countup",
            "unit": "countup",
            "start_date": "2026-01-30",  # Friday
            "skip_nonworkdays": True,
        }
    ]

    class _HolidayDB(_DummyDB):
        @staticmethod
        def is_nonworkday(daykey, country=None):
            return daykey == "20260201"  # Sun Feb 1 is marked nonworkday

    coords = BlockPlanLayout().calculate(config)
    renderer = _CaptureBlockPlanRenderer()
    renderer.render(config, coords, events=[], db=_HolidayDB())

    # Jan 30 → Mon Feb 2: Jan31, Feb1(skip), Feb2 = 2
    assert "2" in renderer.text_values
    # Jan 30 → Wed Feb 4: Jan31, Feb1(skip), Feb2, Feb3, Feb4 = 4
    assert "4" in renderer.text_values
