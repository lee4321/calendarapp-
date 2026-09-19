"""Tests for repainting decoration pattern tiles in a rule's color.

Tiles in the ``patterns`` table are monochrome ink on transparent, but
each authoring tool declared that ink differently: a ``fill`` attribute,
an Inkscape ``style="fill:#000000"``, a Serif ``rgb(35,31,32)``, or
``currentColor`` — which inside a ``<pattern>`` def resolves against the
def rather than the filled element, so it never picked up the requested
color at all.  ``colorize_pattern_svg`` normalizes all of those.

These tests pin each source form against the real table, and pin the two
things that must *not* happen: ``fill="none"`` being painted in (which
would fill shapes the artwork leaves hollow), and a wrapper ``stroke``
being added (which would outline shapes that were never stroked).
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

import pytest

from renderers.svg_patterns import (
    colorize_pattern_svg,
    pattern_def_xml,
    pattern_is_recolorable,
)

DB_PATH = Path(__file__).resolve().parent.parent / "calendar.db"


@pytest.fixture(scope="module")
def patterns() -> dict[str, str]:
    """Every row of the shipped ``patterns`` table, by name."""
    if not DB_PATH.exists():
        pytest.skip(f"{DB_PATH} not present")
    con = sqlite3.connect(DB_PATH)
    try:
        return dict(con.execute("SELECT name, svg FROM patterns").fetchall())
    finally:
        con.close()


class TestColorizeSourceForms:
    """Each way a tile in the table declares its ink."""

    def test_literal_black_fill_attribute(self):
        out = colorize_pattern_svg('<rect fill="#000000"/>', "red")
        assert out == '<rect fill="red"/>'

    def test_short_hex_and_named_black(self):
        assert colorize_pattern_svg('<rect fill="#000"/>', "red") == '<rect fill="red"/>'
        assert colorize_pattern_svg('<rect fill="black"/>', "red") == '<rect fill="red"/>'

    def test_black_stroke_attribute(self):
        # No shipped tile needs this today, but it is the same kind of ink.
        assert colorize_pattern_svg('<path stroke="#000000"/>', "red") == '<path stroke="red"/>'

    def test_current_color_fill(self):
        assert colorize_pattern_svg('<svg fill="currentColor">', "red") == '<svg fill="red">'

    def test_current_color_stroke(self):
        assert colorize_pattern_svg('<path stroke="currentColor"/>', "red") == '<path stroke="red"/>'

    def test_inkscape_style_fill(self):
        out = colorize_pattern_svg('<path style="fill:#000000;stroke-width:0.167947"/>', "red")
        assert out == '<path style="fill:red;stroke-width:0.167947"/>'

    def test_serif_style_rgb_triplet(self):
        out = colorize_pattern_svg('<path style="fill:rgb(35,31,32)"/>', "red")
        assert out == '<path style="fill:red"/>'

    def test_style_stroke_declaration(self):
        out = colorize_pattern_svg('<path style="stroke:#000000"/>', "red")
        assert out == '<path style="stroke:red"/>'

    def test_none_color_is_a_no_op(self):
        svg = '<rect fill="#000000"/>'
        assert colorize_pattern_svg(svg, None) == svg


class TestColorizeLeavesAlone:
    """What repainting must not touch."""

    def test_fill_none_stays_hollow(self):
        out = colorize_pattern_svg('<path fill="none" stroke="currentColor"/>', "red")
        assert 'fill="none"' in out
        assert 'stroke="red"' in out

    def test_stroke_none_stays_unstroked(self):
        out = colorize_pattern_svg('<g fill="#000000" stroke="none"/>', "red")
        assert 'stroke="none"' in out
        assert 'fill="red"' in out

    def test_style_fill_none_stays_hollow(self):
        out = colorize_pattern_svg('<path style="fill:none;stroke:#000"/>', "red")
        assert "fill:none" in out
        assert "stroke:red" in out

    @pytest.mark.parametrize(
        "prop",
        [
            "fill-rule:evenodd",
            "fill-opacity:0.5",
            "stroke-width:0.167947",
            "stroke-linejoin:round",
            "stroke-linecap:butt",
            "stroke-miterlimit:4",
            "stroke-dasharray:none",
            "stroke-opacity:1",
        ],
    )
    def test_hyphenated_properties_are_not_paint(self, prop):
        # These share a prefix with fill/stroke but are not colors; rewriting
        # one would corrupt the geometry rather than recolor it.
        out = colorize_pattern_svg(f'<path style="{prop}"/>', "red")
        assert out == f'<path style="{prop}"/>'

    def test_clip_rule_is_untouched(self):
        svg = '<path style="fill-rule:evenodd;clip-rule:evenodd"/>'
        assert colorize_pattern_svg(svg, "red") == svg


class TestPatternDefWrapper:
    """The wrapper <g> that restores paint stripped with the root <svg>."""

    ROOT_ONLY = '<svg viewBox="0 0 16 16" fill="currentColor"><path d="M0 0h8v8H0z"/></svg>'

    def test_root_only_paint_survives_on_the_wrapper(self):
        # extract_pattern_inner drops the <svg>, taking its fill with it, so
        # without the wrapper this tile would render at the UA default.
        xml = pattern_def_xml("pat-x", self.ROOT_ONLY, "red")
        assert 'fill="red"' in xml
        assert "<path" in xml

    def test_wrapper_sets_fill_but_never_stroke(self):
        # An unset stroke defaults to none; setting it on the wrapper would
        # outline every shape in the tile.
        xml = pattern_def_xml("pat-x", self.ROOT_ONLY, "red")
        wrapper = re.search(r"<g [^>]*>", xml)
        assert wrapper, xml
        assert 'fill="red"' in wrapper.group(0)
        assert "stroke=" not in wrapper.group(0)

    def test_no_wrapper_fill_when_no_color_requested(self):
        xml = pattern_def_xml("pat-x", self.ROOT_ONLY, None, target_size=0)
        assert "fill=" not in xml.split("<path")[0]

    def test_wrapper_carries_both_scale_and_fill(self):
        big = '<svg viewBox="0 0 1920 1920" fill="currentColor"><path d="M0 0h8v8H0z"/></svg>'
        xml = pattern_def_xml("pat-x", big, "red", target_size=18.0)
        m = re.search(r"<g [^>]*>", xml)
        assert m, xml
        assert "transform=" in m.group(0)
        assert 'fill="red"' in m.group(0)


class TestAgainstTheShippedTable:
    """The whole point: every tile obeys the color it is given."""

    def test_every_vector_pattern_yields_the_requested_color(self, patterns):
        missed = []
        for name, svg in patterns.items():
            if not pattern_is_recolorable(svg):
                continue
            xml = pattern_def_xml(f"pat-{name}", svg, "red")
            if 'fill="red"' not in xml and "fill:red" not in xml and 'stroke="red"' not in xml:
                missed.append(name)
        assert missed == [], f"{len(missed)} patterns ignore the requested color: {missed[:10]}"

    def test_no_black_ink_survives_recoloring(self, patterns):
        leftover = []
        for name, svg in patterns.items():
            if not pattern_is_recolorable(svg):
                continue
            xml = pattern_def_xml(f"pat-{name}", svg, "red")
            if re.search(r'(fill|stroke)="(#000000|#000|black)"', xml, re.I) or re.search(
                r"(fill|stroke)\s*:\s*(#000000|#000|rgb\(35,31,32\))", xml, re.I
            ):
                leftover.append(name)
        assert leftover == [], f"{len(leftover)} patterns keep black ink: {leftover[:10]}"

    def test_no_current_color_survives_as_paint(self, patterns):
        leftover = []
        for name, svg in patterns.items():
            xml = pattern_def_xml(f"pat-{name}", svg, "red")
            # `color="currentColor"` is a self-referential no-op and is not
            # paint; only fill/stroke would actually draw with it.
            if re.search(r'(fill|stroke)="currentColor"', xml, re.I):
                leftover.append(name)
        assert leftover == [], f"{len(leftover)} patterns keep currentColor paint: {leftover[:10]}"

    def test_hollow_shapes_stay_hollow(self, patterns):
        # dingbat tiles are outline artwork: fill="none" plus a stroke.  If
        # repainting filled them in they would render as solid blobs.
        xml = pattern_def_xml("pat-dingbat16", patterns["dingbat16"], "red")
        assert 'fill="none"' in xml
        assert 'stroke="red"' in xml


class TestPatternIsRecolorable:
    """Raster tiles cannot be repainted and are reported, not fixed."""

    def test_vector_tile_is_recolorable(self):
        assert pattern_is_recolorable('<svg><path fill="#000"/></svg>')

    def test_image_element_is_not(self):
        assert not pattern_is_recolorable('<svg><image xlink:href="x.png"/></svg>')

    def test_inline_data_uri_is_not(self):
        assert not pattern_is_recolorable('<svg><image xlink:href="data:image/png;base64,iVBOR"/></svg>')

    def test_stars65_is_the_only_raster_tile_shipped(self, patterns):
        raster = sorted(n for n, svg in patterns.items() if not pattern_is_recolorable(svg))
        assert raster == ["stars65"]
