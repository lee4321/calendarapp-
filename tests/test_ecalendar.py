import unittest

from config.config import create_calendar_config
from shared.date_utils import calc_calendar_range


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


if __name__ == "__main__":
    unittest.main()
