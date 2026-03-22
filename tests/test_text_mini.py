import tempfile
from pathlib import Path

from config.config import create_calendar_config, setfontsizes
from visualizers.text_mini.visualizer import TextMiniCalendarVisualizer


class _FakeDB:
    def __init__(self, events, holidays=None, specials=None):
        self._events = events
        self._holidays = holidays or {}
        self._specials = specials or {}

    def get_all_events_in_range(self, start, end):
        return self._events

    def get_holidays_for_date(self, daykey, country=None):
        return self._holidays.get(daykey, [])

    def get_special_days_for_date(self, daykey):
        return self._specials.get(daykey, [])


def test_text_mini_generates_file_with_symbols():
    config = create_calendar_config()
    config.pageX, config.pageY = 792.0, 1224.0
    config = setfontsizes(config)
    config.userstart = "20260101"
    config.userend = "20260131"
    config.adjustedstart = "20260101"
    config.adjustedend = "20260131"
    config.mini_columns = 1
    config.mini_rows = 1
    config.mini_show_week_numbers = True
    config.rollups = False

    events = [
        {
            "Start": "20260115",
            "End": "20260115",
            "Task_Name": "Milestone 1",
            "Milestone": True,
            "Priority": 1,
        }
    ]
    holidays = {
        "20260107": [{"displayname": "Holiday", "nonworkday": 1}],
    }

    db = _FakeDB(events, holidays=holidays)
    visualizer = TextMiniCalendarVisualizer()

    with tempfile.TemporaryDirectory() as td:
        config.outputfile = str(Path(td) / "mini.txt")
        result = visualizer.generate(config, db)
        content = Path(result.output_path).read_text(encoding="utf-8")

    assert "Milestone 1" in content
    assert "Holiday" in content
