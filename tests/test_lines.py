"""The shared line engine: routing, stubs, markers and SVG output."""

from __future__ import annotations

import re

import drawsvg
import pytest

from config.theme_schema import LineSpec
from renderers.lines import MarkerRegistry, draw_line, line_path, line_svg, stroke_attrs
from vendor.labella.renderer import hCurveBetween, moveTo, vCurveBetween


def nums(path: str) -> list[float]:
    return [float(x) for x in re.findall(r"-?\d+(?:\.\d+)?", path)]


class TestStraight:
    def test_plain_line(self):
        assert line_path(LineSpec(), (0, 0), (10, 5)) == "M 0 0 L 10 5"

    def test_stubs_run_along_the_headings(self):
        spec = LineSpec(start_stub=4, end_stub=3)
        path = line_path(spec, (0, 0), (0, -50), start_heading=(0, -1), end_heading=(0, 1))
        assert path == "M 0 0 L 0 -4 L 0 -47 L 0 -50"

    def test_stubs_default_to_the_direction_of_travel(self):
        assert line_path(LineSpec(start_stub=5, end_stub=5), (0, 0), (100, 0)) == "M 0 0 L 5 0 L 95 0 L 100 0"

    def test_stubs_are_limited_on_a_short_line(self):
        path = line_path(LineSpec(start_stub=50, end_stub=50), (0, 0), (10, 0))
        assert nums(path) == [0, 0, 4.5, 0, 5.5, 0, 10, 0]

    def test_zero_length_is_a_bare_move(self):
        assert line_path(LineSpec(), (3, 3), (3, 3)) == "M 3 3"


class TestCurve:
    def test_matches_the_labella_horizontal_curve(self):
        spec = LineSpec(route="curve")
        got = line_path(spec, (0, 10), (100, 50), start_heading=(1, 0), end_heading=(-1, 0))
        want = " ".join([moveTo([0, 10]), hCurveBetween([0, 10], [100, 50])])
        assert nums(got) == pytest.approx(nums(want), abs=1e-6)

    def test_matches_the_labella_vertical_curve(self):
        spec = LineSpec(route="curve")
        got = line_path(spec, (20, 0), (60, -80), start_heading=(0, -1), end_heading=(0, 1))
        want = " ".join([moveTo([20, 0]), vCurveBetween([20, 0], [60, -80])])
        assert nums(got) == pytest.approx(nums(want), abs=1e-6)

    def test_stubs_are_straight_segments_around_the_curve(self):
        spec = LineSpec(route="curve", start_stub=4, end_stub=6)
        path = line_path(spec, (0, 0), (100, 40), start_heading=(1, 0), end_heading=(-1, 0))
        assert path.startswith("M 0 0 L 4 0 C ")
        assert path.endswith("L 100 40")
        assert " 94 40 L 100 40" in path  # the curve ends at the end stub's far point

    def test_curve_arrives_square_to_the_end_heading(self):
        spec = LineSpec(route="curve", end_stub=0)
        path = line_path(spec, (0, 0), (100, 40), start_heading=(1, 0), end_heading=(-1, 0))
        *_, _c2x, c2y, _ex, ey = nums(path)
        assert c2y == ey  # the last control point lies on the end heading's axis


class TestMarkers:
    def test_registry_dedupes_and_ignores_none(self):
        reg = MarkerRegistry()
        a = reg.ensure("arrow-head", "red", 6)
        assert reg.ensure("arrow-head", "red", 6) == a
        assert reg.ensure("arrow-head", "blue", 6) != a
        assert reg.ensure("none", "red", 6) is None
        assert reg.ensure("arrow-head", "red", 0) is None
        assert reg.ensure("unknown", "red", 6) is None
        assert len(reg.defs) == 2

    def test_start_and_end_arrows_are_mirror_images(self):
        reg = MarkerRegistry()
        end = reg.ensure("arrow-head", "red", 6)
        start = reg.ensure("arrow-head", "red", 6, at_start=True)
        assert end != start
        assert end and start
        assert 'refX="6"' in reg.defs[end]
        assert 'refX="0"' in reg.defs[start]

    @pytest.mark.parametrize("kind", ["circle", "diamond", "square"])
    def test_shape_markers_centre_on_the_endpoint(self, kind):
        reg = MarkerRegistry()
        marker_id = reg.ensure(kind, "red", 8)
        assert marker_id
        xml = reg.defs[marker_id]
        assert 'refX="4"' in xml and 'refY="4"' in xml


class TestSvg:
    def test_path_carries_every_style(self):
        spec = LineSpec(color="red", width=2, opacity=0.5, dasharray="4,2", marker_end="arrow-head", marker_end_size=5)
        reg = MarkerRegistry()
        svg = line_svg(spec, "M 0 0 L 10 0", reg, css_class="ec-axis-line")
        for want in (
            'stroke="red"',
            'stroke-width="2"',
            'stroke-opacity="0.5"',
            'stroke-dasharray="4,2"',
            'class="ec-axis-line"',
            "marker-end=",
        ):
            assert want in svg
        assert "marker-start" not in svg

    def test_none_and_invisible_lines_draw_nothing(self):
        reg = MarkerRegistry()
        assert line_svg(LineSpec(color="none"), "M 0 0 L 1 1", reg) == ""
        assert line_svg(LineSpec(width=0), "M 0 0 L 1 1", reg) == ""

    def test_stroke_attrs_feed_rects(self):
        assert stroke_attrs(LineSpec(color="blue", width=1.5, opacity=0.3, dasharray="2 2")) == {
            "stroke": "blue",
            "stroke_width": 1.5,
            "stroke_opacity": 0.3,
            "stroke_dasharray": "2 2",
        }


class FakeRenderer:
    def __init__(self):
        self.drawing = drawsvg.Drawing(100, 100)


class TestDraw:
    def test_marker_defs_are_added_once_per_drawing(self):
        r = FakeRenderer()
        spec = LineSpec(marker_end="arrow-head", marker_end_size=6)
        draw_line(r, spec, (0, 0), (10, 0))
        draw_line(r, spec, (0, 5), (10, 5))
        svg = r.drawing.as_svg()
        assert svg.count("<marker ") == 1
        assert svg.count("<path d=") >= 2

    def test_a_new_drawing_gets_its_own_defs(self):
        r = FakeRenderer()
        spec = LineSpec(marker_end="arrow-head", marker_end_size=6)
        draw_line(r, spec, (0, 0), (10, 0))
        r.drawing = drawsvg.Drawing(100, 100)
        draw_line(r, spec, (0, 0), (10, 0))
        assert r.drawing.as_svg().count("<marker ") == 1
