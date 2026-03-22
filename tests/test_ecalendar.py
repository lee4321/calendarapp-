import unittest
import tempfile
import yaml

import arrow

from config.config import create_calendar_config
from config.theme_engine import ThemeEngine
from ecalendar import _reapply_post_theme_cli_overrides
from shared.date_utils import calc_calendar_range
from argparse import Namespace


class TestCalendarRange(unittest.TestCase):
    def test_workweek_adjustments(self):
        config = create_calendar_config()
        config.weekend_style = 0

        calc_calendar_range(config, "20250108", "20250116")  # Wed to Thu

        self.assertEqual(config.adjustedstart, "20250106")  # Monday
        self.assertEqual(config.adjustedend, "20250117")  # Friday
        self.assertEqual(config.numberofweeks, 2)

    def test_sunday_start_adjustments(self):
        config = create_calendar_config()
        config.weekend_style = 1

        calc_calendar_range(config, "20250108", "20250116")  # Wed to Thu

        self.assertEqual(config.adjustedstart, "20250105")  # Sunday
        self.assertEqual(config.adjustedend, "20250118")  # Saturday
        self.assertEqual(config.numberofweeks, 2)

    def test_reversed_dates_are_swapped(self):
        config = create_calendar_config()
        config.weekend_style = 1

        calc_calendar_range(config, "20250116", "20250108")

        self.assertEqual(config.adjustedstart, "20250105")
        self.assertEqual(config.adjustedend, "20250118")

    def test_cli_mini_no_adjacent_overrides_theme(self):
        config = create_calendar_config()
        engine = ThemeEngine()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(
                {
                    "theme": {"name": "Mini"},
                    "mini_calendar": {"show_adjacent": True},
                },
                f,
            )
            f.flush()
            engine.load(f.name)
        engine.apply(config)
        args = Namespace(mini_no_adjacent=True)

        _reapply_post_theme_cli_overrides(args, config)

        self.assertFalse(config.mini_show_adjacent)


if __name__ == "__main__":
    unittest.main()
