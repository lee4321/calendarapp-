"""A pattern tile's own ids must not collide with another tile's.

Tiles are authored as standalone documents, but `extract_pattern_inner`
inlines their content into one shared `<defs>`. The 112 EMF-derived
`stars*` tiles each carry the same six ids -- `defs2`, `layer1`, `base`,
`grid8`, `metadata5` and the empty hatch-base `EMFhbasepattern` -- so a
sheet of 24 of them used to emit 24 copies of each.

No shipped tile references its own ids, so the collision was invalid
markup rather than a wrong render. These tests pin the scoping that keeps
it that way, and in particular that a tile which *does* reference its own
ids keeps resolving to its own copy.
"""

from __future__ import annotations

import collections
import re
import sqlite3
from pathlib import Path

import pytest

from renderers.svg_patterns import pattern_def_xml, scope_pattern_ids

DB_PATH = Path(__file__).resolve().parent.parent / "calendar.db"


@pytest.fixture(scope="module")
def patterns() -> dict[str, str]:
    if not DB_PATH.exists():
        pytest.skip(f"{DB_PATH} not present")
    con = sqlite3.connect(DB_PATH)
    try:
        return dict(con.execute("SELECT name, svg FROM patterns").fetchall())
    finally:
        con.close()


def _ids(xml: str) -> list[str]:
    return re.findall(r'\bid="([^"]+)"', xml)


def _refs(xml: str) -> list[str]:
    return [m[0] or m[1] for m in re.findall(r'url\(\s*#([^)\s]+)\s*\)|(?:xlink:)?href="#([^"]+)"', xml)]


class TestScopePatternIds:
    def test_declarations_are_prefixed(self):
        out = scope_pattern_ids('<g id="layer1"/>', "pat-x-red")
        assert out == '<g id="pat-x-red-layer1"/>'

    def test_url_references_follow_their_target(self):
        out = scope_pattern_ids('<defs><linearGradient id="g1"/></defs><rect fill="url(#g1)"/>', "pat-x-red")
        assert 'id="pat-x-red-g1"' in out
        assert "url(#pat-x-red-g1)" in out
        assert "url(#g1)" not in out

    def test_xlink_href_references_follow_their_target(self):
        out = scope_pattern_ids('<path id="p"/><use xlink:href="#p"/>', "pat-x-red")
        assert 'xlink:href="#pat-x-red-p"' in out

    def test_plain_href_references_follow_their_target(self):
        out = scope_pattern_ids('<path id="p"/><use href="#p"/>', "pat-x-red")
        assert 'href="#pat-x-red-p"' in out

    def test_reference_to_an_undeclared_id_is_left_alone(self):
        # A reference out to the containing document must keep resolving.
        out = scope_pattern_ids('<g id="a"/><rect fill="url(#outside)"/>', "pat-x-red")
        assert "url(#outside)" in out

    def test_content_without_ids_is_returned_unchanged(self):
        svg = '<path d="M0 0h8v8H0z"/>'
        assert scope_pattern_ids(svg, "pat-x-red") == svg

    def test_similar_id_names_are_not_confused(self):
        # A naive per-id string replace would rewrite `layer1` inside
        # `layer10`, producing `s-layer10` twice and losing one element.
        out = scope_pattern_ids('<g id="layer1"/><g id="layer10"/><rect fill="url(#layer10)"/>', "s")
        assert _ids(out) == ["s-layer1", "s-layer10"]
        assert "url(#s-layer10)" in out

    def test_scoping_is_idempotent_under_distinct_scopes(self):
        once = scope_pattern_ids('<g id="a"/>', "one")
        twice = scope_pattern_ids(once, "two")
        assert twice == '<g id="two-one-a"/>'


class TestPatternDefScoping:
    def test_def_xml_scopes_with_the_def_id(self, patterns):
        xml = pattern_def_xml("pat-stars1-red", patterns["stars1"], "red")
        assert 'id="pat-stars1-red-EMFhbasepattern"' in xml
        assert 'id="EMFhbasepattern"' not in xml

    def test_two_tiles_no_longer_collide(self, patterns):
        a = pattern_def_xml("pat-stars1-red", patterns["stars1"], "red")
        b = pattern_def_xml("pat-stars10-red", patterns["stars10"], "red")
        assert set(_ids(a)).isdisjoint(_ids(b))

    def test_the_same_tile_in_two_colors_does_not_collide(self, patterns):
        a = pattern_def_xml("pat-stars1-red", patterns["stars1"], "red")
        b = pattern_def_xml("pat-stars1-blue", patterns["stars1"], "blue")
        assert set(_ids(a)).isdisjoint(_ids(b))

    def test_whole_table_in_one_document_has_no_duplicate_ids(self, patterns):
        ids: list[str] = []
        for name, svg in patterns.items():
            ids += _ids(pattern_def_xml(f"pat-{name}-c", svg, "c"))
        dupes = {k: v for k, v in collections.Counter(ids).items() if v > 1}
        assert dupes == {}, f"{len(dupes)} ids collide across the table: {list(dupes)[:5]}"

    def test_no_reference_is_left_dangling(self, patterns):
        for name, svg in patterns.items():
            xml = pattern_def_xml(f"pat-{name}-c", svg, "c")
            declared = set(_ids(xml))
            for ref in _refs(xml):
                assert ref in declared, f"{name}: dangling reference #{ref}"
