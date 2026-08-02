"""
Tests for the shared ``--paginate`` behaviour of the sample-sheet generators.

``colorsheet``, ``fontsheet``, ``iconsheet`` and ``palettesheet`` all split
their items into ``columns × rows`` pages and write each page as
``<stem>_pNN.svg``.  These tests pin that shared contract: page counts, file
naming, the single-page filename fallback, and — for the all-palettes sheet —
the packing rule that fills each page with as many *whole* palettes as fit.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from visualizers.sheets import (
    _generate_all_palettes_svg,
    _generate_colorsheet_svg,
    _generate_fontsheet_svg,
    _generate_iconsheet_svg,
    _generate_palette_svg,
)

ICON_SVG = '<svg viewBox="0 0 24 24" fill="none"><path d="M1 1 L23 23" stroke="currentColor"/></svg>'


def _colors(n: int) -> list[dict]:
    """``n`` colour rows spread across the hue circle, as the DB returns them."""
    return [
        {"EN": f"color{i:03d}", "red": (i * 7) % 256, "green": (i * 13) % 256,
         "blue": (i * 29) % 256}
        for i in range(n)
    ]


def _icons(n: int) -> list[dict]:
    return [{"name": f"icon{i:03d}", "svg": ICON_SVG} for i in range(n)]


def _palette(n: int) -> list[str]:
    return [f"#{(i * 7) % 256:02X}{(i * 13) % 256:02X}{(i * 29) % 256:02X}" for i in range(n)]


class SheetPaginationTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.out = Path(self._tmp.name) / "sheet.svg"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    # ----- single-sheet mode (the default) ---------------------------------

    def test_colorsheet_single_sheet_keeps_base_filename(self):
        written = _generate_colorsheet_svg(_colors(30), self.out)
        self.assertEqual(written, [self.out])
        self.assertTrue(self.out.exists())

    def test_palettesheet_single_sheet_keeps_base_filename(self):
        written = _generate_palette_svg("Test", _palette(12), self.out)
        self.assertEqual(written, [self.out])

    # ----- paginated mode ---------------------------------------------------

    def test_colorsheet_paginates_into_numbered_pages(self):
        # 25 colours over 2×3 pages → 6 per page → 5 pages.
        written = _generate_colorsheet_svg(
            _colors(25), self.out, paginate=True, columns=2, rows=3
        )
        self.assertEqual(
            [p.name for p in written],
            [f"sheet_p{i:02d}.svg" for i in range(1, 6)],
        )
        self.assertTrue(all(p.exists() for p in written))

    def test_iconsheet_paginates_into_numbered_pages(self):
        written = _generate_iconsheet_svg(
            _icons(25), self.out, paginate=True, columns=2, rows=3
        )
        self.assertEqual(
            [p.name for p in written],
            [f"sheet_p{i:02d}.svg" for i in range(1, 6)],
        )

    def test_single_page_run_keeps_base_filename(self):
        written = _generate_colorsheet_svg(
            _colors(4), self.out, paginate=True, columns=4, rows=10
        )
        self.assertEqual(written, [self.out])

    def test_paginated_page_shows_name_range_instead_of_count(self):
        written = _generate_colorsheet_svg(
            _colors(6), self.out, title="Colors", paginate=True, columns=3, rows=1
        )
        first = written[0].read_text(encoding="utf-8")
        self.assertIn("(color000 to color002)", first)
        self.assertNotIn("colors)</tspan>", first)

    def test_last_page_holds_the_remainder(self):
        written = _generate_colorsheet_svg(
            _colors(7), self.out, paginate=True, columns=3, rows=1
        )
        self.assertEqual(len(written), 3)
        # The trailing page has one swatch, so its range collapses to one name.
        self.assertIn("(color006)", written[-1].read_text(encoding="utf-8"))

    def test_cell_size_scales_the_swatch_box(self):
        default = _generate_colorsheet_svg(
            _colors(1), self.out, paginate=True, columns=1, rows=1
        )[0].read_text(encoding="utf-8")
        self.assertIn('width="110" height="60"', default)

        sized = _generate_colorsheet_svg(
            _colors(1), self.out, paginate=True, columns=1, rows=1, cell_size=220
        )[0].read_text(encoding="utf-8")
        # Height follows the width so the sheet keeps its aspect ratio.
        self.assertIn('width="220" height="120"', sized)

    # ----- palettesheet: pages pack as many whole palettes as fit -----------

    def test_all_palettes_pack_several_palettes_onto_one_page(self):
        palettes = {"Alpha": _palette(3), "Beta": _palette(4), "Gamma": _palette(2)}
        written = _generate_all_palettes_svg(
            palettes, self.out, paginate=True, columns=12, rows=10
        )
        # Each palette is one swatch row, so all three fit in a 10-row budget.
        self.assertEqual(written, [self.out])
        document = self.out.read_text(encoding="utf-8")
        for name in ("Alpha", "Beta", "Gamma"):
            self.assertIn(f">{name}  <", document)

    def test_all_palettes_break_page_when_budget_is_exhausted(self):
        palettes = {name: _palette(4) for name in ("Alpha", "Beta", "Gamma", "Delta")}
        written = _generate_all_palettes_svg(
            palettes, self.out, paginate=True, columns=4, rows=3
        )
        self.assertEqual(len(written), 2)
        first = written[0].read_text(encoding="utf-8")
        second = written[1].read_text(encoding="utf-8")
        # Alphabetical packing: two whole palettes fit the 3-row budget.
        self.assertIn(">Alpha  <", first)
        self.assertIn(">Beta  <", first)
        self.assertNotIn(">Gamma  <", first)
        self.assertIn(">Gamma  <", second)

    def test_palette_is_never_split_across_pages(self):
        # "Big" alone is taller than the one-row budget; it must still land on a
        # single (taller) page rather than being cut in half.
        palettes = {"Big": _palette(12), "Small": _palette(2)}
        written = _generate_all_palettes_svg(
            palettes, self.out, paginate=True, columns=3, rows=1
        )
        self.assertEqual(len(written), 2)
        big_page = written[0].read_text(encoding="utf-8")
        self.assertIn(">Big  <", big_page)
        self.assertNotIn(">Small  <", big_page)
        # All 12 swatches are on that page.
        self.assertEqual(big_page.count('stroke="#bbbbbb"'), 12)

    def test_all_palettes_single_sheet_is_one_file(self):
        palettes = {"Alpha": _palette(3), "Beta": _palette(4)}
        written = _generate_all_palettes_svg(palettes, self.out)
        self.assertEqual(written, [self.out])


class FontsheetPaginationTests(unittest.TestCase):
    """The fontsheet uses the same page-splitting contract as the other sheets."""

    def setUp(self) -> None:
        from config.config import FONT_REGISTRY

        self._tmp = tempfile.TemporaryDirectory()
        self.out = Path(self._tmp.name) / "sheet.svg"
        self.fonts = dict(sorted(FONT_REGISTRY.items())[:5])

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_single_sheet_keeps_base_filename(self):
        written = _generate_fontsheet_svg(self.fonts, self.out)
        self.assertEqual(written, [self.out])
        self.assertIn("(5 fonts)", self.out.read_text(encoding="utf-8"))

    def test_paginates_into_numbered_pages(self):
        written = _generate_fontsheet_svg(
            self.fonts, self.out, paginate=True, columns=1, rows=2
        )
        self.assertEqual(
            [p.name for p in written],
            ["sheet_p01.svg", "sheet_p02.svg", "sheet_p03.svg"],
        )

    def test_paginated_page_shows_font_name_range(self):
        names = sorted(self.fonts, key=str.lower)
        written = _generate_fontsheet_svg(
            self.fonts, self.out, paginate=True, columns=1, rows=2
        )
        first = written[0].read_text(encoding="utf-8")
        self.assertIn(f"({names[0]} to {names[1]})", first)
        self.assertNotIn("fonts)</tspan>", first)


if __name__ == "__main__":
    unittest.main()
