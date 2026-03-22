import unittest

from shared.db_access import CalendarDB
from config.config import setfontsizes, create_calendar_config, resolve_page_margins


class TestPaperSizesFromDB(unittest.TestCase):
    """Test loading paper sizes from the database."""

    def setUp(self):
        self.db = CalendarDB("calendar.db")

    def test_get_paper_sizes_returns_dict(self):
        sizes = self.db.get_paper_sizes()
        self.assertIsInstance(sizes, dict)
        self.assertGreater(len(sizes), 0)

    def test_letter_size_present(self):
        sizes = self.db.get_paper_sizes()
        self.assertIn("Letter", sizes)
        w, h = sizes["Letter"]
        self.assertAlmostEqual(w, 612.0, places=0)
        self.assertAlmostEqual(h, 792.0, places=0)

    def test_tabloid_normalized_to_portrait(self):
        """Tabloid is landscape=1 in DB; should be normalized to portrait."""
        sizes = self.db.get_paper_sizes()
        self.assertIn("Tabloid", sizes)
        w, h = sizes["Tabloid"]
        # Portrait-canonical: width < height
        self.assertLess(w, h)

    def test_all_sizes_portrait_canonical(self):
        """All sizes should have width <= height after normalization."""
        sizes = self.db.get_paper_sizes()
        for name, (w, h) in sizes.items():
            self.assertLessEqual(w, h, f"{name}: width {w} > height {h}")

    def test_get_paper_size_names(self):
        names = self.db.get_paper_size_names()
        self.assertIsInstance(names, list)
        self.assertIn("Letter", names)
        self.assertIn("A4", names)

    def test_get_paper_sizes_grouped(self):
        groups = self.db.get_paper_sizes_grouped()
        self.assertIsInstance(groups, dict)
        self.assertIn("US Common", groups)
        # Each group entry should be (name, w, h)
        for name, w, h in groups["US Common"]:
            self.assertIsInstance(name, str)
            self.assertGreater(w, 0)
            self.assertGreater(h, 0)


class TestFormulaFontSizes(unittest.TestCase):
    """Test formula-based font sizing."""

    def test_letter_portrait_sizes_reasonable(self):
        config = create_calendar_config()
        config.pageX, config.pageY = 612.0, 792.0
        config.papersize = "Letter"
        config.orientation = "portrait"
        config = setfontsizes(config)

        self.assertGreater(config.event_text_font_size, 0.0)
        self.assertGreater(config.header_left_font_size, config.event_text_font_size)

    def test_tabloid_portrait_sizes_larger_than_letter(self):
        letter_config = create_calendar_config()
        letter_config.pageX, letter_config.pageY = 612.0, 792.0
        letter_config = setfontsizes(letter_config)

        tabloid_config = create_calendar_config()
        tabloid_config.pageX, tabloid_config.pageY = 792.0, 1224.0
        tabloid_config = setfontsizes(tabloid_config)

        self.assertGreater(
            tabloid_config.event_text_font_size,
            letter_config.event_text_font_size,
        )
        self.assertGreater(
            tabloid_config.watermark_size,
            letter_config.watermark_size,
        )

    def test_tiny_paper_hits_minimum(self):
        tiny = create_calendar_config()
        tiny.pageX, tiny.pageY = 100.0, 150.0
        tiny = setfontsizes(tiny)

        tinier = create_calendar_config()
        tinier.pageX, tinier.pageY = 50.0, 75.0
        tinier = setfontsizes(tinier)
        # Both should settle at the configured minimum floor.
        self.assertEqual(tiny.event_text_font_size, tinier.event_text_font_size)

    def test_huge_paper_hits_maximum(self):
        huge = create_calendar_config()
        huge.pageX, huge.pageY = 5000.0, 7000.0
        huge = setfontsizes(huge)

        huger = create_calendar_config()
        huger.pageX, huger.pageY = 10000.0, 14000.0
        huger = setfontsizes(huger)
        # Both should settle at the configured maximum cap.
        self.assertEqual(huge.event_text_font_size, huger.event_text_font_size)

    def test_layout_percentages_set(self):
        config = create_calendar_config()
        config.pageX, config.pageY = 612.0, 792.0
        config = setfontsizes(config)

        other = create_calendar_config()
        other.pageX, other.pageY = 792.0, 1224.0
        other = setfontsizes(other)

        self.assertGreater(config.week_number_percent, 0.0)
        self.assertGreater(config.margin_percent, 0.0)
        self.assertGreater(config.color_key_percent, 0.0)
        # Percent policies are set in setfontsizes() and should be invariant
        # across page sizes.
        self.assertEqual(config.week_number_percent, other.week_number_percent)
        self.assertEqual(config.margin_percent, other.margin_percent)
        self.assertEqual(config.color_key_percent, other.color_key_percent)

    def test_desired_font_size_scales_event_text_size(self):
        config = create_calendar_config()
        config.pageX, config.pageY = 612.0, 792.0
        config.desired_font_size = 12.0
        config = setfontsizes(config)
        self.assertAlmostEqual(config.event_text_font_size, 12.0, places=2)

    def test_resolve_page_margins_uses_side_overrides(self):
        config = create_calendar_config()
        config.pageX, config.pageY = 612.0, 792.0
        config.include_margin = False
        config.margin_left = 10.0
        config.margin_right = 20.0
        config.margin_top = 30.0
        config.margin_bottom = 40.0

        m = resolve_page_margins(config)
        self.assertEqual(m["left"], 10.0)
        self.assertEqual(m["right"], 20.0)
        self.assertEqual(m["top"], 30.0)
        self.assertEqual(m["bottom"], 40.0)
        self.assertEqual(m["usable_width"], 582.0)
        self.assertEqual(m["usable_height"], 722.0)


if __name__ == "__main__":
    unittest.main()
