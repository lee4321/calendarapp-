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
    def get_holidays_for_date(daykey, country=None):
        return []

    @staticmethod
    def get_special_days_for_date(daykey):
        return []


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


class TestResolveFont:
    def test_explicit_setting_honored(self):
        config = create_calendar_config()
        font = CompactPlanRenderer._resolve_font("AmericanTypewriter-Bold", config)
        assert font == "AmericanTypewriter-Bold"

    def test_unknown_setting_falls_back_to_config_base(self):
        config = create_calendar_config()
        config.compactplan_text_font_name = "AmericanTypewriter-Light"
        font = CompactPlanRenderer._resolve_font("NotARealFont", config)
        assert font == "AmericanTypewriter-Light"

    def test_none_setting_uses_config_base(self):
        config = create_calendar_config()
        config.compactplan_text_font_name = "AmericanTypewriter-Medium"
        font = CompactPlanRenderer._resolve_font(None, config)
        assert font == "AmericanTypewriter-Medium"

    def test_italic_prefers_notes_font(self):
        config = create_calendar_config()
        config.compactplan_notes_text_font_name = "AmericanTypewriter-Cond"
        config.compactplan_text_font_name = "AmericanTypewriter-Bold"
        font = CompactPlanRenderer._resolve_font(None, config, italic=True)
        assert font == "AmericanTypewriter-Cond"

    def test_italic_falls_back_to_base_font(self):
        config = create_calendar_config()
        config.compactplan_notes_text_font_name = None
        config.compactplan_text_font_name = "AmericanTypewriter-Bold"
        font = CompactPlanRenderer._resolve_font(None, config, italic=True)
        assert font == "AmericanTypewriter-Bold"

    def test_safe_fallback_when_nothing_configured(self):
        from config.config import Fonts

        config = create_calendar_config()
        config.compactplan_text_font_name = None
        config.compactplan_notes_text_font_name = None
        font = CompactPlanRenderer._resolve_font(None, config)
        assert font == Fonts.RC_LIGHT


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


# ---------------------------------------------------------------------------
# Icon time-band (unit: "icon")
# ---------------------------------------------------------------------------


class _IconDB(_DummyDB):
    """DB stub that serves a single named icon so icon bands can draw."""

    @staticmethod
    def get_icon_svg_map():
        return {
            "diamond": '<svg viewBox="0 0 24 24"><path d="M12 2L22 12L12 22L2 12Z"/></svg>'
        }


class _IconCaptureRenderer(_CaptureCompactPlanRenderer):
    """Adds icon-draw capture on top of the rect/line/text capture."""

    def __init__(self):
        super().__init__()
        self.icon_calls: list[dict] = []

    def _draw_icon_svg(self, icon_name, x, baseline_y, size, **kwargs):
        self.icon_calls.append(
            {"icon_name": icon_name, "x": x, "y": baseline_y, "size": size, **kwargs}
        )
        return super()._draw_icon_svg(icon_name, x, baseline_y, size, **kwargs)


def _icon_band_config(output: Path):
    config = _base_config(output)
    config.compactplan_time_bands = [
        {
            "label": "Events",
            "unit": "icon",
            "fill_color": "#eeeeee",
            "icon_rules": [
                {"milestone": True, "icon": "diamond", "color": "#4472c4"},
            ],
        }
    ]
    return config


def test_renderer_icon_band_renders(tmp_path):
    """A band with unit: "icon" must render without raising (regression).

    The compactplan call site passes ``css_class`` to the shared
    ``BaseSVGRenderer._draw_icon_band_row`` helper; a helper signature without
    that parameter raises TypeError here.
    """
    output = tmp_path / "compact.svg"
    config = _icon_band_config(output)
    coords = CompactPlanLayout().calculate(config)
    events = [_milestone("Launch", "20260316", group="Team1")]

    renderer = _IconCaptureRenderer()
    renderer.render(config, coords, events, _IconDB())

    assert output.exists()
    drawn = [c for c in renderer.icon_calls if c["icon_name"] == "diamond"]
    assert drawn, "Expected the milestone's icon-band glyph to be drawn"
    assert drawn[0]["color"] == "#4472c4"


def test_renderer_icon_band_cells_carry_band_class(tmp_path):
    """Icon-band cell backgrounds are classed ec-band-cell like other bands."""
    output = tmp_path / "compact.svg"
    config = _icon_band_config(output)
    coords = CompactPlanLayout().calculate(config)

    renderer = _IconCaptureRenderer()
    renderer.render(config, coords, [_milestone("Launch", "20260316")], _IconDB())

    band_rects = [rc for rc in renderer.rect_calls if rc.get("css_class") == "ec-band-cell"]
    assert band_rects, "Expected classed background rects for the icon band"

    # ec-band-cell is a kind: box class — the glyphs must not inherit it, or an
    # external `.ec-band-cell { fill: ... }` rule would recolor them.
    assert all(c.get("css_class") != "ec-band-cell" for c in renderer.icon_calls)


def test_icon_band_row_rects_unclassed_by_default():
    """blockplan / timeline call the helper without css_class — stays unclassed."""
    renderer = _IconCaptureRenderer()
    renderer._draw_rect = lambda *a, **kw: renderer.rect_calls.append(kw)  # type: ignore[method-assign]

    renderer._draw_icon_band_row(
        [(0.0, 10.0, [])], row_y=0.0, row_h=12.0, icon_h=8.0, fill_color="#cccccc"
    )

    assert renderer.rect_calls, "Expected a background rect for the filled cell"
    assert all(rc.get("css_class") is None for rc in renderer.rect_calls)


# ---------------------------------------------------------------------------
# Key page (<output>_key.svg)
# ---------------------------------------------------------------------------


class _PageCaptureRenderer(_CaptureCompactPlanRenderer):
    """Records which drawing -- chart or key page -- each text landed on."""

    def __init__(self):
        super().__init__()
        self.texts_by_drawing: list[tuple[int, str]] = []

    def _draw_text(self, x, y, text, font_name, font_size, **kwargs):
        self.texts_by_drawing.append((id(self._drawing), str(text)))
        super()._draw_text(x, y, text, font_name, font_size, **kwargs)

    def chart_texts(self) -> list[str]:
        # render() leaves the chart's drawing in place once the key is done.
        return [t for d, t in self.texts_by_drawing if d == id(self._drawing)]

    def key_texts(self) -> list[str]:
        return [t for d, t in self.texts_by_drawing if d != id(self._drawing)]


class _HolidayDB(_DummyDB):
    @staticmethod
    def get_holidays_for_date(daykey, country=None):
        if daykey == "20260316":
            return [{"displayname": "Founders Day", "country": "US"}]
        return []


def _render(tmp_path, events, db=None, **overrides):
    output = tmp_path / "compact.svg"
    config = _base_config(output)
    for key, value in overrides.items():
        setattr(config, key, value)
    renderer = _PageCaptureRenderer()
    result = renderer.render(
        config, CompactPlanLayout().calculate(config), events, db or _DummyDB()
    )
    return renderer, result, output


def test_key_is_written_to_its_own_page(tmp_path):
    renderer, result, output = _render(
        tmp_path, [_dur("Sprint 1", "20260309", "20260320", group="Team1")]
    )

    assert (tmp_path / "compact_key.svg").exists()
    assert result.page_count == 2
    assert "Sprint 1" in renderer.key_texts()
    assert "Team1" in renderer.key_texts()


def test_chart_page_carries_no_key(tmp_path):
    """Nothing of the key -- group names, task names, the symbols -- is
    drawn on the chart itself any more."""
    renderer, _, _ = _render(
        tmp_path, [_dur("Sprint 1", "20260309", "20260320", group="Team1")]
    )

    chart = " ".join(renderer.chart_texts())
    assert "Team1" not in chart
    assert "Sprint 1" not in chart
    assert "timeline" not in chart


def test_no_key_page_when_the_legend_is_off(tmp_path):
    _, result, _ = _render(
        tmp_path,
        [_dur("Sprint 1", "20260309", "20260320", group="Team1")],
        compactplan_show_legend=False,
    )

    assert not (tmp_path / "compact_key.svg").exists()
    assert result.page_count == 1


def test_no_key_page_for_an_empty_chart(tmp_path):
    """The symbols alone explain nothing, so an empty chart gets no key."""
    _, result, _ = _render(tmp_path, [])

    assert not (tmp_path / "compact_key.svg").exists()
    assert result.page_count == 1


def test_key_lists_the_details_page_columns(tmp_path):
    """The key is the shared details listing: its columns, its cells."""
    renderer, _, _ = _render(
        tmp_path,
        [
            _dur("Build", "20260309", "20260320", group="Dev"),
            _milestone("Go Live", "20260325", group="Ops"),
        ],
    )

    texts = renderer.key_texts()
    for heading in ("Key", "Start Date", "Name / Description", "Milestone", "Priority", "Group"):
        assert heading in texts
    assert "2026-03-09" in texts
    assert "End: 2026-03-20" in texts  # a duration's end rides under its name
    assert "True" in texts  # the milestone column


def _key_names(renderer, names):
    return [t for t in renderer.key_texts() if t in names]


def test_key_lists_bars_by_group_assignment_then_start_date(tmp_path):
    """Rows of one color sit together: groups in palette order (sorted
    names), each by start date; milestones, which take no color
    assignment, follow."""
    renderer, _, _ = _render(
        tmp_path,
        [
            _dur("B early", "20260309", "20260313", group="Beta"),
            _dur("A late", "20260323", "20260327", group="Alpha"),
            _milestone("Launch", "20260310"),
            _dur("A early", "20260316", "20260320", group="Alpha"),
        ],
    )

    assert _key_names(renderer, {"A early", "A late", "B early", "Launch"}) == [
        "A early", "A late", "B early", "Launch",
    ]


def test_key_lists_color_rule_matches_first_in_rule_order(tmp_path):
    renderer, _, _ = _render(
        tmp_path,
        [
            _dur("Plain", "20260309", "20260313", group="Alpha"),
            _dur("Blue team", "20260310", "20260313", group="Beta"),
            _dur("Urgent", "20260323", "20260327", group="Beta") | {"Priority": 5},
            _dur("Urgent early", "20260316", "20260320", group="Alpha") | {"Priority": 5},
        ],
        compactplan_color_rules=[
            {"name": "urgent", "select": {"priority": 5}, "color": "#aa0000"},
            {"name": "beta", "select": {"resource_group": "Beta"}, "color": "#0000aa"},
        ],
    )

    assert _key_names(renderer, {"Plain", "Blue team", "Urgent", "Urgent early"}) == [
        "Urgent early", "Urgent",  # rule 0, by start date
        "Blue team",               # rule 1
        "Plain",                   # the default, resource-group assignment
    ]


def test_key_clusters_rows_by_the_color_each_bar_was_drawn_in(tmp_path):
    """An event's own Color is part of the default assignment: its row
    joins whichever rows share that color -- a palette slot's, or, for a
    color the assignment never hands out, its own cluster after them."""
    renderer, _, _ = _render(
        tmp_path,
        [
            _dur("Own early", "20260309", "20260313", group="Alpha", color="#abcdef"),
            _dur("Beta own", "20260310", "20260313", group="Beta", color="#abcdef"),
            _dur("Alpha plain", "20260316", "20260320", group="Alpha"),
            _dur("Looks Beta", "20260311", "20260313", group="Alpha", color="#0000bb"),
            _dur("Beta plain", "20260317", "20260320", group="Beta"),
        ],
        compactplan_palette=["#0000aa", "#0000bb"],
    )

    names = {"Own early", "Beta own", "Alpha plain", "Looks Beta", "Beta plain"}
    assert _key_names(renderer, names) == [
        "Alpha plain",               # Alpha's palette color
        "Looks Beta", "Beta plain",  # Beta's palette color, by start date
        "Own early", "Beta own",     # a color only events carry
    ]


def test_key_swatch_carries_the_bar_color(tmp_path):
    """Color attribution survives the move: each activity's row paints a
    swatch in the color its bar was drawn in."""
    _render(
        tmp_path,
        [
            _dur("Alpha work", "20260309", "20260320", group="A", color="#123456"),
            _dur("Beta work", "20260316", "20260327", group="B", color="#abcdef"),
        ],
    )

    key_svg = (tmp_path / "compact_key.svg").read_text()
    assert 'style="stroke:#123456;' in key_svg
    assert 'style="stroke:#abcdef;' in key_svg
    assert key_svg.count('class="ec-legend-swatch"') >= 2


def test_key_swatch_takes_the_palette_color_of_its_group(tmp_path):
    renderer, _, _ = _render(
        tmp_path,
        [_dur("Build", "20260309", "20260320", group="Dev")],
        compactplan_palette=["#0a0b0c"],
    )

    assert 'style="stroke:#0a0b0c;' in (tmp_path / "compact_key.svg").read_text()
    # ...the same color the bar was drawn in on the chart.
    assert any(kw.get("stroke") == "#0a0b0c" for kw in renderer.line_kwargs)


def test_key_marks_a_milestone_with_its_flag_color(tmp_path):
    _render(tmp_path, [_milestone("Go Live", "20260316", color="#fedcba")])

    key_svg = (tmp_path / "compact_key.svg").read_text()
    assert "#fedcba" in key_svg


def test_key_lists_the_holidays_on_the_axis(tmp_path):
    renderer, _, _ = _render(
        tmp_path,
        [_dur("Build", "20260309", "20260320", group="Dev")],
        db=_HolidayDB(),
    )

    texts = renderer.key_texts()
    assert "US - Founders Day" in texts
    assert "Federal Holiday" in texts


def test_key_explains_continuation_only_when_a_bar_continues(tmp_path):
    renderer, _, _ = _render(
        tmp_path, [_dur("Short", "20260309", "20260313", group="A")]
    )
    assert "activity continues" not in renderer.key_texts()
    assert "timeline" in renderer.key_texts()

    renderer, _, _ = _render(
        tmp_path, [_dur("Long", "20260401", "20260515", group="A")]
    )
    assert "activity continues" in renderer.key_texts()


def test_a_long_key_continues_onto_further_pages(tmp_path):
    events = [
        _dur(f"Task {n}", "20260309", "20260313", group=f"G{n % 4}")
        for n in range(120)
    ]
    _, result, _ = _render(tmp_path, events)

    assert (tmp_path / "compact_key_p2.svg").exists()
    assert result.page_count >= 3


def test_chart_page_keeps_the_bottom_rows_icons(tmp_path):
    """With no key beneath it the chart's viewBox ends at its own ink --
    which, for the lowest bar, is its start icon, taller than the bar."""
    import re

    renderer, _, output = _render(
        tmp_path,
        [_dur(f"T{n}", "20260309", "20260320", group="A") for n in range(4)],
        shrink_to_content=True,
    )

    view_box = re.search(r'viewBox="([^"]+)"', output.read_text()).group(1)
    _, top, _, height = (float(v) for v in view_box.split())
    lowest = max(p.row_y for p in renderer._chart_key.placed.values())
    icon_h = renderer._duration_icon_height(renderer._config)
    assert top + height >= lowest + icon_h / 2.0


# ---------------------------------------------------------------------------
# Milestone icons
# ---------------------------------------------------------------------------


class _LabelCaptureRenderer(_IconCaptureRenderer):
    """Adds label positions to the icon capture."""

    def __init__(self):
        super().__init__()
        self.text_calls: list[dict] = []

    def _draw_text(self, x, y, text, font_name, font_size, **kwargs):
        self.text_calls.append({"x": x, "y": y, "text": str(text), **kwargs})
        super()._draw_text(x, y, text, font_name, font_size, **kwargs)


def _milestone_with_icon(icon, color="#2e8b57"):
    event = _milestone("Go Live", "20260316", color=color)
    event["Icon"] = icon
    return event


def _render_milestone(tmp_path, event, **overrides):
    output = tmp_path / "compact.svg"
    config = _base_config(output)
    for key, value in overrides.items():
        setattr(config, key, value)
    renderer = _LabelCaptureRenderer()
    renderer.render(config, CompactPlanLayout().calculate(config), [event], _IconDB())
    return renderer


def _milestone_icons(renderer):
    return [c for c in renderer.icon_calls if c.get("css_class") == "ec-milestone-marker"]


def test_a_milestone_icon_is_drawn_in_place_of_the_pennant(tmp_path):
    """Regression: the chart looked icons up with db.get_icon_svg, which
    CalendarDB does not have, so every milestone drew a flag."""
    renderer = _render_milestone(tmp_path, _milestone_with_icon("diamond"))

    chart_icon = _milestone_icons(renderer)[0]
    assert chart_icon["icon_name"] == "diamond"
    assert chart_icon["color"] == "#2e8b57"  # the milestone's own color
    # The stem stays, so the icon is still planted on its date.
    assert any(abs(x1 - x2) < 0.01 and y1 != y2 for x1, y1, x2, y2 in renderer.line_calls)


def test_the_theme_milestone_icon_applies_when_the_event_names_none(tmp_path):
    renderer = _render_milestone(
        tmp_path, _milestone_with_icon(""), compactplan_milestone_icon="diamond"
    )

    assert [c["icon_name"] for c in _milestone_icons(renderer)][:1] == ["diamond"]


def test_an_unknown_milestone_icon_falls_back_to_the_flag(tmp_path):
    renderer = _render_milestone(tmp_path, _milestone_with_icon("no-such-icon"))

    assert _milestone_icons(renderer) == []


def test_a_milestone_label_starts_past_its_icon(tmp_path):
    renderer = _render_milestone(tmp_path, _milestone_with_icon("diamond"))

    chart_icon = _milestone_icons(renderer)[0]
    label = next(t for t in renderer.text_calls if t["text"] == "Go Live")
    assert label["x"] > chart_icon["x"] + chart_icon["size"]


def test_the_key_marks_a_milestone_with_the_icon_the_chart_drew(tmp_path):
    renderer = _render_milestone(tmp_path, _milestone_with_icon("diamond"))

    # One on the chart, one in the key's mark column.
    assert [c["icon_name"] for c in _milestone_icons(renderer)] == ["diamond", "diamond"]


# ---------------------------------------------------------------------------
# Time bands from the shared catalog: holiday, row_height, show_every
# ---------------------------------------------------------------------------


class _FlagDB(_DummyDB):
    """A public holiday on Mon 16 Mar, an observance on Wed 18 Mar."""

    _ROWS = {
        "20260316": [{"icon": "flag-us", "displayname": "Founders Day", "nonworkday": 1, "country": "US"}],
        "20260318": [{"icon": "flag-ca", "displayname": "Heritage Day", "nonworkday": 0, "country": "CA"}],
    }

    @classmethod
    def get_holidays_for_date(cls, daykey, country=None):
        return cls._ROWS.get(daykey, [])

    @staticmethod
    def get_icon_svg_map():
        square = '<svg viewBox="0 0 24 24"><rect width="24" height="24"/></svg>'
        return {"flag-us": square, "flag-ca": square}


def _render_bands(tmp_path, bands, db=None):
    output = tmp_path / "compact.svg"
    config = _base_config(output)
    config.compactplan_time_bands = bands
    config.compactplan_show_legend = False  # the key's holiday rows draw flags too
    renderer = _IconCaptureRenderer()
    renderer.render(
        config, CompactPlanLayout().calculate(config),
        [_dur("Build", "20260309", "20260320", group="Dev")],
        db or _FlagDB(),
    )
    return renderer


def _band_rects(renderer):
    return [r for r in renderer.rect_calls if r.get("css_class") == "ec-band-cell"]


def test_the_holiday_band_draws_each_holidays_own_flag(tmp_path):
    renderer = _render_bands(tmp_path, [{"unit": "holiday", "label": "Holidays"}])

    flags = {c["icon_name"] for c in renderer.icon_calls}
    assert {"flag-us", "flag-ca"} <= flags
    # A country flag keeps its own colors.
    assert all(c.get("color") is None for c in renderer.icon_calls if c["icon_name"].startswith("flag-"))


def test_the_holiday_band_can_hide_observances(tmp_path):
    renderer = _render_bands(
        tmp_path, [{"unit": "holiday", "label": "Holidays", "nonworkdays_only": True}]
    )

    flags = {c["icon_name"] for c in renderer.icon_calls}
    assert "flag-us" in flags
    assert "flag-ca" not in flags


def test_the_holiday_band_puts_the_flag_on_its_day(tmp_path):
    renderer = _render_bands(tmp_path, [{"unit": "holiday", "label": "Holidays"}])

    us = next(c for c in renderer.icon_calls if c["icon_name"] == "flag-us")
    # Mon 16 Mar is the 6th weekday of a range starting Mon 9 Mar.
    area_x, _, area_w, _ = CompactPlanLayout().calculate(renderer._config)["CompactPlanArea"]
    px_per_day = area_w / 35  # 7 working weeks
    assert area_x + 5 * px_per_day <= us["x"] <= area_x + 6 * px_per_day


def test_each_band_takes_its_own_row_height(tmp_path):
    renderer = _render_bands(
        tmp_path,
        [
            {"unit": "week", "row_height": 30, "fill_color": "#eeeeee"},
            {"unit": "date", "fill_color": "#dddddd"},
        ],
    )

    week = [r for r in _band_rects(renderer) if r["fill"] == "#eeeeee"]
    day = [r for r in _band_rects(renderer) if r["fill"] == "#dddddd"]
    assert {r["h"] for r in week} == {30.0}
    assert {r["h"] for r in day} == {renderer._config.compactplan_band_row_height}
    # The rows stack: the date row starts where the week row ends.
    assert day[0]["y"] == week[0]["y"] + 30.0


def test_show_every_merges_date_cells_within_a_week(tmp_path):
    renderer = _render_bands(
        tmp_path,
        [{"unit": "date", "show_every": 2, "fill_color": "#eeeeee", "alt_fill_color": "#dddddd"}],
    )

    # Seven working weeks of Mon-Tue, Wed-Thu, Fri cells.
    assert len(_band_rects(renderer)) == 7 * 3
    labels = set(renderer.text_values)
    assert {"9", "11", "13"} <= labels  # a merged cell shows its first day
    # Thu 12 and Thu 19 Mar sit in a merged cell; neither date recurs
    # unmerged in April (the 12th and 19th are Sundays).
    assert "12" not in labels and "19" not in labels



# ---------------------------------------------------------------------------
# Theme color rules (compact_plan.color_rules)
# ---------------------------------------------------------------------------


def _bar_strokes(renderer):
    return {
        kw["stroke"] for kw in renderer.line_kwargs if kw.get("css_class") == "ec-duration-bar"
    }


def _render_colored(tmp_path, events, rules):
    renderer, _, _ = _render(tmp_path, events, compactplan_color_rules=rules)
    return renderer


def test_without_color_rules_bars_take_their_group_palette_color(tmp_path):
    renderer, _, _ = _render(
        tmp_path,
        [_dur("Build", "20260309", "20260320", group="Dev")],
        compactplan_palette=["#0a0b0c"],
    )

    assert _bar_strokes(renderer) == {"#0a0b0c"}


def test_a_matching_color_rule_colors_the_bar(tmp_path):
    renderer = _render_colored(
        tmp_path,
        [
            _dur("Urgent", "20260309", "20260320", group="Dev") | {"Priority": 5},
            _dur("Routine", "20260309", "20260320", group="Dev"),
        ],
        [{"select": {"priority_min": 4}, "color": "#aa0000"}],
    )

    palette_color = renderer._config.compactplan_palette[0]
    assert _bar_strokes(renderer) == {"#aa0000", palette_color}


def test_the_first_matching_rule_wins(tmp_path):
    renderer = _render_colored(
        tmp_path,
        [_dur("Urgent", "20260309", "20260320", group="Dev") | {"Priority": 5}],
        [
            {"select": {"priority": 5}, "color": "#aa0000"},
            {"select": {"resource_group": "Dev"}, "color": "#0000aa"},
        ],
    )

    assert _bar_strokes(renderer) == {"#aa0000"}


def test_a_color_rule_beats_the_events_own_color(tmp_path):
    """The event's Color is part of the default assignment the theme's
    conditions replace."""
    renderer = _render_colored(
        tmp_path,
        [_dur("Build", "20260309", "20260320", group="Dev", color="#123456")],
        [{"select": {"resource_group": "Dev"}, "color": "#aa0000"}],
    )

    assert _bar_strokes(renderer) == {"#aa0000"}


def test_an_unmatched_bar_keeps_its_own_color(tmp_path):
    renderer = _render_colored(
        tmp_path,
        [_dur("Build", "20260309", "20260320", group="Dev", color="#123456")],
        [{"select": {"resource_group": "Ops"}, "color": "#aa0000"}],
    )

    assert _bar_strokes(renderer) == {"#123456"}


def test_a_rule_with_no_select_colors_every_bar(tmp_path):
    renderer = _render_colored(
        tmp_path,
        [
            _dur("One", "20260309", "20260320", group="A"),
            _dur("Two", "20260309", "20260320", group="B"),
        ],
        [{"name": "everything", "color": "#777777"}],
    )

    assert _bar_strokes(renderer) == {"#777777"}


def test_the_key_swatch_shows_the_rule_color(tmp_path):
    _render_colored(
        tmp_path,
        [_dur("Urgent", "20260309", "20260320", group="Dev") | {"Priority": 5}],
        [{"select": {"priority": 5}, "color": "#aa0000"}],
    )

    assert 'style="stroke:#aa0000;' in (tmp_path / "compact_key.svg").read_text()


def test_color_rules_load_from_a_theme(tmp_path):
    from config.config import CalendarConfig
    from config.theme_engine import ThemeEngine

    theme = tmp_path / "rules.yaml"
    theme.write_text(
        "compact_plan:\n"
        "  color_rules:\n"
        "    - name: urgent\n"
        "      select: {priority_min: 4}\n"
        "      color: firebrick\n"
    )
    config = CalendarConfig()
    engine = ThemeEngine()
    engine.load(str(theme))
    engine.apply(config)

    assert config.compactplan_color_rules == [
        {"name": "urgent", "select": {"priority_min": 4}, "color": "firebrick"}
    ]


def test_a_rule_color_may_reference_a_palette():
    from config.config import CalendarConfig
    from config.palette_resolver import _resolve_palette_overrides

    class _PaletteDB:
        @staticmethod
        def get_palette(name):
            return ["#111111", "#222222", "#333333"] if name == "Greys" else None

        @staticmethod
        def sample_palette_n(name, n):
            return None

    rules = [{"select": {}, "color": "palette:Greys:1"}, {"select": {}, "color": "red"}]
    config = CalendarConfig()
    config.compactplan_color_rules = rules
    _resolve_palette_overrides(config, _PaletteDB())

    assert [r["color"] for r in config.compactplan_color_rules] == ["#222222", "red"]
    assert rules[0]["color"] == "palette:Greys:1"  # the theme's own list is untouched


class TestColorRuleEngine:
    def _event(self, **fields):
        from shared.data_models import Event

        return Event.from_dict(_dur("T", "20260309", "20260320") | fields)

    def test_returns_the_rule_index_and_color(self):
        from shared.rule_engine import ColorRuleEngine

        engine = ColorRuleEngine([
            {"select": {"priority": 9}, "color": "red"},
            {"select": {"resource_group": "dev"}, "color": "blue"},
        ])

        assert engine.assign(self._event(Resource_Group="Dev")) == (1, "blue")
        assert engine.assign(self._event(Resource_Group="Ops")) is None

    def test_an_unknown_criterion_skips_the_rule_rather_than_matching_all(self, caplog):
        from shared.rule_engine import ColorRuleEngine

        engine = ColorRuleEngine([
            {"name": "typo", "select": {"resouce_group": "Dev"}, "color": "red"},
            {"select": {"resource_group": "Dev"}, "color": "blue"},
        ])

        assert engine.assign(self._event(Resource_Group="Dev")) == (1, "blue")
        assert "resouce_group" in caplog.text

    def test_a_rule_without_a_color_is_skipped(self, caplog):
        from shared.rule_engine import ColorRuleEngine

        engine = ColorRuleEngine([{"select": {}}, "not a rule"])

        assert not engine
        assert engine.assign(self._event()) is None
        assert "no color" in caplog.text
