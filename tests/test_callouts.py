"""Leader geometry and style, shared by the timeline and the pit."""

from __future__ import annotations

from config.theme_loader import load_theme
from shared.callouts import leader_ends, leader_style
from shared.orientation import Orientation, Side

FONT = "OfficinaSans-Book"


def theme(**sections):
    data = {"theme": {"name": "t", "version": "3.0"}, "fonts": {"family": FONT}, **sections}
    return load_theme(data, font_registry={FONT})


H, V = Orientation.HORIZONTAL, Orientation.VERTICAL


class TestEnds:
    def test_a_box_over_its_dot_gets_a_perpendicular_leader_to_its_bottom_edge(self):
        ends = leader_ends((100, 300), (80, 250, 50, 30), Side.PRIMARY, H)
        assert ends.start == (100, 300) and ends.end == (100, 280)
        assert ends.start_heading == (0, -1) and ends.end_heading == (0, 1)

    def test_below_the_axis_the_near_edge_is_the_top(self):
        ends = leader_ends((100, 300), (80, 320, 50, 30), Side.SECONDARY, H)
        assert ends.end == (100, 320)
        assert ends.start_heading == (0, 1) and ends.end_heading == (0, -1)

    def test_a_nudged_box_pulls_the_leader_to_its_nearest_corner(self):
        right = leader_ends((100, 300), (120, 250, 50, 30), Side.PRIMARY, H)
        left = leader_ends((100, 300), (20, 250, 50, 30), Side.PRIMARY, H)
        assert right.end == (120, 280) and left.end == (70, 280)

    def test_a_vertical_axis_swaps_the_roles_of_x_and_y(self):
        primary = leader_ends((300, 100), (320, 80, 50, 30), Side.PRIMARY, V)
        assert primary.end == (320, 100) and primary.start_heading == (1, 0) and primary.end_heading == (-1, 0)
        secondary = leader_ends((300, 100), (230, 80, 50, 30), Side.SECONDARY, V)
        assert secondary.end == (280, 100) and secondary.start_heading == (-1, 0)

    def test_a_box_with_no_extent_ends_where_it_sits(self):
        """An unplaced callout: the leader runs to the edge of the room."""
        assert leader_ends((100, 300), (100, 200, 0, 0), Side.PRIMARY, H).end == (100, 200)


class TestStyle:
    def test_the_side_recolours_the_base_leader(self):
        t = theme(
            lines={"leader": {"width": 2.0}, "leader_primary": {"color": "red"}, "leader_secondary": {"color": "blue"}}
        )
        up, down = leader_style(t, Side.PRIMARY), leader_style(t, Side.SECONDARY)
        assert (up.color, down.color) == ("red", "blue")
        assert up.width == down.width == 2.0

    def test_a_side_without_a_colour_keeps_the_base_colour(self):
        t = theme(lines={"leader": {"color": "grey"}, "leader_primary": {}})
        assert leader_style(t, Side.PRIMARY).color == "grey"

    def test_a_rule_override_wins_and_numbers_may_be_strings(self):
        t = theme()
        spec = leader_style(t, Side.PRIMARY, {"color": "#abcdef", "dasharray": "4,2", "opacity": "0.5", "ignored": 1})
        assert (spec.color, spec.dasharray, spec.opacity) == ("#abcdef", "4,2", 0.5)

    def test_the_schema_leader_is_a_curve_with_square_stubs(self):
        spec = leader_style(theme(), Side.PRIMARY)
        assert spec.route == "curve" and spec.start_stub > 0 and spec.end_stub > 0
